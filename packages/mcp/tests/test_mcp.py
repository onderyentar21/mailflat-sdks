"""MailFlat MCP tool tests — real /api/v1 faked through the SDK + httpx.MockTransport.

Monkeypatches `server._client` to return a `mailflat.MailFlat` bound to a MockTransport, so
every tool is exercised end to end without a backend (the tools call the SDK, DRY).

Connected to:
  - tests: mailflat_mcp.server (FastMCP tools) → mailflat SDK → /api/v1 (mock)
"""
import httpx
import pytest
from mailflat import MailFlat

from mailflat_mcp import server

ADDR = "agent-7f3@x7k2m.mailflat.net"


class FakeBackend:
    """Minimal in-memory /api/v1 backend — mirrors the real response shapes."""

    def __init__(self):
        self.sent = []      # every /send body (did in_reply_to actually go out?)
        self.inboxes = {}   # address -> meta
        self.emails = {}    # address -> [serialized email]

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        method = req.method
        if method == "POST" and path == "/api/v1/inboxes":
            import json
            body = json.loads(req.content or b"{}")
            label = body.get("label") or "agent"
            ret = min(body.get("retention_hours") or 2, 2)  # Free plan ceiling = 2h
            meta = {"ok": True, "address": ADDR, "api_key": "mf_sk_1",
                    "name": label, "retention_hours": ret}
            self.inboxes[ADDR] = meta
            self.emails.setdefault(ADDR, [])
            return httpx.Response(200, json=meta)
        if method == "GET" and path == "/api/v1/inboxes":
            return httpx.Response(200, json={"ok": True, "inboxes": [
                {"address": a, "via_api": True, **m} for a, m in self.inboxes.items()]})
        if method == "GET" and path.endswith("/messages"):
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/messages", 1)[0]
            return httpx.Response(200, json={"ok": True, "emails": self._filtered(addr, req)})
        if method == "GET" and path.endswith("/latest"):
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/latest", 1)[0]
            msgs = self._filtered(addr, req)
            return httpx.Response(200, json={"ok": True, "email": msgs[0] if msgs else None})
        if method == "POST" and path.endswith("/read"):
            addr = path.split("/api/v1/inboxes/")[1].split("/messages/")[0]
            mid = int(path.rsplit("/messages/", 1)[1].rsplit("/read", 1)[0])
            for e in self.emails.get(addr, []):
                if e.get("id") == mid:
                    e["is_read"] = True
                    return httpx.Response(200, json={"ok": True})
            return httpx.Response(400, json={"detail": "Email not found"})
        if method == "POST" and path.endswith("/burn"):
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/burn", 1)[0]
            n = len(self.emails.get(addr, []))
            self.emails[addr] = []
            return httpx.Response(200, json={"ok": True, "burned": n})
        if method == "POST" and path.endswith("/send"):
            import json
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/send", 1)[0]
            body = json.loads(req.content or b"{}")
            self.sent.append(body)
            self.emails.setdefault(addr, []).insert(0, {
                "id": 99, "direction": "out", "to_address": body["to"],
                "subject": body.get("subject"), "body_text": body.get("body"),
                "otp_code": None, "is_encrypted": False,
                "cc": body.get("cc", []), "bcc": body.get("bcc", []),
                "headers": {"In-Reply-To": body["in_reply_to"]} if body.get("in_reply_to") else None})
            # 202, not 200 — the real endpoint ACCEPTS the mail and delivers it on a queue.
            # A fake answering 200 would let a client that chokes on 202 pass here (B-059:
            # a fake that does not mimic the real contract passes tests for the wrong reason).
            return httpx.Response(202, json={"ok": True, "queued": True, "message_id": 99,
                                             "message": f"Accepted for delivery to {body['to']}"})
        if method == "DELETE" and path.startswith("/api/v1/inboxes/"):
            addr = path.split("/api/v1/inboxes/")[1]
            self.inboxes.pop(addr, None)
            return httpx.Response(200, json={"ok": True, "message": "Inbox deleted"})
        return httpx.Response(404, json={"detail": "not found"})

    def _filtered(self, addr: str, req: httpx.Request) -> list:
        """The real backend's `direction` contract — this fake used to IGNORE it.

        The result: a test looking for outgoing mail stayed green even after `read_messages`
        defaulted to "in", so it was validating the fake rather than the code. When a fake
        does not mirror reality, its green proves nothing.
        """
        direction = req.url.params.get("direction", "in")
        if direction not in ("in", "out", "all"):
            raise AssertionError(f"invalid direction reached the backend: {direction!r}")
        msgs = self.emails.get(addr, [])
        if direction == "all":
            return msgs
        return [e for e in msgs if e.get("direction") == direction]

    def deliver(self, address, **email):
        """Simulate an incoming message (insert at the front = newest)."""
        base = {"id": 1, "direction": "in", "is_encrypted": False, "otp_code": None}
        self.emails.setdefault(address, []).insert(0, {**base, **email})


@pytest.fixture
def patched(monkeypatch):
    backend = FakeBackend()

    def fake_client():
        http = httpx.Client(transport=httpx.MockTransport(backend.handler),
                            base_url="https://mailflat.net",
                            headers={"X-API-Key": "mf_test"})
        return MailFlat(api_key="mf_test", http_client=http)

    monkeypatch.setattr(server, "_client", fake_client)
    return backend


def test_mcp_full_flow(patched):
    res = server.create_inbox(label="mcp-test")
    addr = res["address"]
    assert addr.endswith(".mailflat.net")
    assert res["retention_hours"] == 2

    # gelen OTP maili + wait_for_otp
    patched.deliver(addr, sender="stripe", subject="Verify", body_text="code 246813", otp_code="246813")
    out = server.wait_for_otp(addr, timeout=3)
    assert out["otp_code"] == "246813"
    assert out["email"]["subject"] == "Verify"

    # read_messages + list_inboxes
    assert len(server.read_messages(addr)["emails"]) == 1
    assert any(i["address"] == addr for i in server.list_inboxes()["inboxes"])


def test_mcp_wait_for_otp_timeout(patched):
    addr = server.create_inbox(label="empty")["address"]
    with pytest.raises(Exception, match="No message arrived"):
        server.wait_for_otp(addr, timeout=0)   # no mail → the call FAILS (isError)


def test_mcp_send_email(patched):
    addr = server.create_inbox(label="sender")["address"]
    res = server.send_email(addr, to="customer@example.com", subject="Hi", body="Hello from agent")
    assert res.get("ok") is True
    # Outgoing mail must now be requested EXPLICITLY — the default is incoming only.
    out = server.read_messages(addr, direction="out")["emails"]
    assert len(out) == 1 and out[0]["to_address"] == "customer@example.com"
    # …and the default read does NOT see it, so an agent cannot mistake its own mail for a reply.
    assert server.read_messages(addr)["emails"] == []


def test_mcp_send_email_passes_cc_and_bcc_through(patched):
    """cc/bcc reach the wire under their real names — a rename here fails as a 422."""
    addr = server.create_inbox(label="cc-sender")["address"]
    server.send_email(addr, to="a@example.com", body="hi",
                      cc=["watcher@example.com"], bcc=["secret@example.com"])
    body = patched.sent[-1]
    assert body["cc"] == ["watcher@example.com"]
    assert body["bcc"] == ["secret@example.com"]


def test_mcp_reply_passes_cc_and_bcc_through(patched):
    addr = server.create_inbox(label="cc-replier")["address"]
    patched.deliver(addr, id=77, sender="human@gmail.com", subject="Q",
                    body_text="?", headers={"Message-ID": "<q@gmail.com>"})
    server.reply(addr, 77, body="a", cc=["boss@example.com"], bcc=["audit@example.com"])
    body = patched.sent[-1]
    assert body["cc"] == ["boss@example.com"] and body["bcc"] == ["audit@example.com"]
    assert body["in_reply_to"] == "<q@gmail.com>"      # still threaded


def test_model_facing_tools_take_no_attachments():
    """🔒 K7: file bytes must never cross the MODEL surface.

    cc/bcc are addresses — short strings a model can reasonably choose. An attachment is
    bytes: it would have to pass through the model's context, costing tokens and being
    plainly impossible for a multi-megabyte file. Files are attached from the SDK
    (`inbox.send(..., attachments=[...])`), which is code, not a model decision.
    """
    import inspect
    for tool in (server.send_email, server.reply):
        params = inspect.signature(tool).parameters
        assert "attachments" not in params, f"{tool.__name__} exposes attachments to the model"
        assert "cc" in params and "bcc" in params, f"{tool.__name__} is missing cc/bcc"


def test_mcp_wait_for_message_ignores_own_outbound(patched):
    """The agent-to-agent pattern: write to a peer, await the reply — not your own message."""
    addr = server.create_inbox(label="peer")["address"]
    server.send_email(addr, to="peer@example.com", subject="ping", body="hi")
    with pytest.raises(Exception, match="No message arrived"):
        server.wait_for_message(addr, timeout=0)

    patched.deliver(addr, sender="peer@example.com", subject="pong", body_text="hey")
    got = server.wait_for_message(addr, timeout=3)
    assert got["email"]["subject"] == "pong"


def test_mcp_mark_read_actually_marks(patched):
    """A secret-free output is not enough — did the field actually change?"""
    addr = server.create_inbox(label="reader")["address"]
    patched.deliver(addr, id=7, sender="s", subject="unread", body_text="x")
    assert server.read_messages(addr)["emails"][0].get("is_read") is not True

    assert server.mark_read(addr, 7).get("ok") is True
    assert server.read_messages(addr)["emails"][0]["is_read"] is True
    # a missing message must FAIL (isError), never silently succeed
    with pytest.raises(Exception, match="not found"):
        server.mark_read(addr, 999)


def test_mcp_burn_empties_inbox_but_keeps_address(patched):
    addr = server.create_inbox(label="burner")["address"]
    patched.deliver(addr, id=1, subject="one")
    patched.deliver(addr, id=2, subject="two")
    assert server.burn_inbox(addr)["burned"] == 2
    assert server.read_messages(addr)["emails"] == []
    # the address SURVIVES — that is what separates burn from delete_inbox
    assert any(i["address"] == addr for i in server.list_inboxes()["inboxes"])


def test_mcp_invalid_direction_is_reported_not_swallowed(patched):
    addr = server.create_inbox(label="baddir")["address"]
    with pytest.raises(Exception, match="direction"):
        server.read_messages(addr, direction="sideways")


def test_mcp_create_inbox_retention(patched):
    assert server.create_inbox(label="ret-ok", retention_hours=1)["retention_hours"] == 1
    assert server.create_inbox(label="ret-cap", retention_hours=48)["retention_hours"] == 2


def test_mcp_delete_inbox(patched):
    addr = server.create_inbox(label="to-delete")["address"]
    assert any(i["address"] == addr for i in server.list_inboxes()["inboxes"])
    server.delete_inbox(addr)
    assert not any(i["address"] == addr for i in server.list_inboxes()["inboxes"])


def test_mcp_delete_message(patched):
    addr = server.create_inbox(label="msg-del")["address"]
    # patched mock: calls the delete_message endpoint (the delete itself may be a no-op here)
    res = server.delete_message(addr, 1)
    assert "error" not in res


def test_mcp_tools_registered():
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"create_inbox", "list_inboxes", "read_messages",
                     "wait_for_otp", "wait_for_message", "send_email", "reply",
                     "mark_read", "burn_inbox", "delete_inbox", "delete_message"}


def test_mcp_reply_threads_instead_of_starting_a_new_conversation(patched):
    """🔒 reply must differ from send_email: recipient, Re: subject and thread headers filled in.

    The leak test cannot prove this — a tool that returns an error also "leaks no secret".
    So this checks the BODY that was actually sent.
    """
    addr = server.create_inbox(label="replier")["address"]
    patched.deliver(addr, id=42, sender="human@gmail.com", subject="Question",
                    body_text="can you help?", headers={"Message-ID": "<abc@mail.gmail.com>"})

    res = server.reply(addr, 42, body="sure")
    assert "error" not in res, res

    body = patched.sent[-1]
    assert body["to"] == "human@gmail.com"
    assert body["subject"] == "Re: Question"
    assert body["in_reply_to"] == "<abc@mail.gmail.com>"


def test_mcp_reply_reports_a_missing_message(patched):
    addr = server.create_inbox(label="noreply")["address"]
    with pytest.raises(Exception, match="not found"):
        server.reply(addr, 999, body="x")


def test_tool_failures_raise_so_mcp_marks_them_as_errors(patched):
    """🔒 A failed tool must RAISE — MCP reports `isError` only for raised calls.

    Fifth external review: every failure came back as a normal result carrying
    `{"error": ...}`, so a client saw 4/4 failures as successful calls and the model had no
    protocol-level signal that anything went wrong.
    """
    import asyncio
    from mcp.server.fastmcp.exceptions import ToolError

    addr = server.create_inbox(label="errs")["address"]
    for call in (lambda: server.mark_read(addr, 999),
                 lambda: server.reply(addr, 999, body="x"),
                 lambda: server.read_messages(addr, direction="sideways"),
                 lambda: server.wait_for_otp(addr, timeout=0)):
        with pytest.raises(Exception):
            call()

    # …and going through FastMCP the raise becomes a ToolError, which is what carries isError.
    async def via_protocol():
        with pytest.raises(ToolError):
            await server.mcp.call_tool("mark_read", {"address": addr, "message_id": 999})
    asyncio.run(via_protocol())


def test_server_reports_its_own_version_not_the_mcp_library(patched):
    """🔒 serverInfo said "1.29.0" — the `mcp` library version, not ours."""
    from mailflat_mcp import __version__
    assert getattr(server.mcp._mcp_server, "version", None) == __version__
    assert __version__ != "1.29.0"
