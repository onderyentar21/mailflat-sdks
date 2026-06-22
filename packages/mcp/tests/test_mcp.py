"""MailFlat MCP tool testleri — SDK + httpx.MockTransport ile gerçek /api/v1 taklit edilir.

server._client'ı, MockTransport'a bağlı bir `mailflat.MailFlat` döndürecek şekilde
monkeypatch eder; böylece backend olmadan 6 aracı uçtan uca test eder (DRY: araçlar SDK'yı çağırır).

Connected to:
  - tests: mailflat_mcp.server (FastMCP tools) → mailflat SDK → /api/v1 (mock)
"""
import httpx
import pytest
from mailflat import MailFlat

from mailflat_mcp import server

ADDR = "agent-7f3@x7k2m.mailflat.net"


class FakeBackend:
    """Minimal /api/v1 in-memory backend — gerçek yanıt şekillerini taklit eder."""

    def __init__(self):
        self.inboxes = {}   # address -> meta
        self.emails = {}    # address -> [serialized email]

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        method = req.method
        if method == "POST" and path == "/api/v1/inboxes":
            import json
            body = json.loads(req.content or b"{}")
            label = body.get("label") or "agent"
            ret = min(body.get("retention_hours") or 2, 2)  # Free plan tavanı = 2h
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
            return httpx.Response(200, json={"ok": True, "emails": self.emails.get(addr, [])})
        if method == "GET" and path.endswith("/latest"):
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/latest", 1)[0]
            msgs = self.emails.get(addr, [])
            return httpx.Response(200, json={"ok": True, "email": msgs[0] if msgs else None})
        if method == "POST" and path.endswith("/send"):
            import json
            addr = path.split("/api/v1/inboxes/")[1].rsplit("/send", 1)[0]
            body = json.loads(req.content or b"{}")
            self.emails.setdefault(addr, []).insert(0, {
                "id": 99, "direction": "out", "to_address": body["to"],
                "subject": body.get("subject"), "body_text": body.get("body"),
                "otp_code": None, "is_encrypted": False})
            return httpx.Response(200, json={"ok": True, "message": f"Sent to {body['to']}"})
        if method == "DELETE" and path.startswith("/api/v1/inboxes/"):
            addr = path.split("/api/v1/inboxes/")[1]
            self.inboxes.pop(addr, None)
            return httpx.Response(200, json={"ok": True, "message": "Inbox deleted"})
        return httpx.Response(404, json={"detail": "not found"})

    def deliver(self, address, **email):
        """Gelen mail simülasyonu (en başa ekle = en yeni)."""
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
    out = server.wait_for_otp(addr, timeout=0)  # mail yok → timeout
    assert out["otp_code"] is None
    assert out["error"] == "timeout"


def test_mcp_send_email(patched):
    addr = server.create_inbox(label="sender")["address"]
    res = server.send_email(addr, to="customer@example.com", subject="Hi", body="Hello from agent")
    assert res.get("ok") is True
    out = [e for e in server.read_messages(addr)["emails"] if e["direction"] == "out"]
    assert len(out) == 1 and out[0]["to_address"] == "customer@example.com"


def test_mcp_create_inbox_retention(patched):
    assert server.create_inbox(label="ret-ok", retention_hours=1)["retention_hours"] == 1
    assert server.create_inbox(label="ret-cap", retention_hours=48)["retention_hours"] == 2


def test_mcp_delete_inbox(patched):
    addr = server.create_inbox(label="to-delete")["address"]
    assert any(i["address"] == addr for i in server.list_inboxes()["inboxes"])
    server.delete_inbox(addr)
    assert not any(i["address"] == addr for i in server.list_inboxes()["inboxes"])


def test_mcp_six_tools_registered():
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"create_inbox", "list_inboxes", "read_messages",
                     "wait_for_otp", "send_email", "delete_inbox"}
