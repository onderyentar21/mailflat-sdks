"""mailflat.langchain testleri — enjekte edilen mock client ile MailFlatToolkit araçları.

`langchain-core` kuruluysa çalışır (yoksa atlanır). Her aracın doğru /api/v1 çağrısını yapıp
beklenen sonucu döndürdüğü, toolkit'in 6 LangChain BaseTool ürettiği doğrulanır.

Connected to:
  - imports from: mailflat (SDK), mailflat.langchain, httpx
"""
from __future__ import annotations

import json

import httpx
import pytest

pytest.importorskip("langchain_core")  # extra kurulu değilse bu modülü atla

from mailflat import MailFlat
from mailflat.langchain import MailFlatToolkit

ADDR = "signup-test@x7k2m.mailflat.net"


def make_toolkit(handler) -> MailFlatToolkit:
    """Verilen handler ile MockTransport kullanan bir MailFlatToolkit kurar."""
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        transport=transport, base_url="https://mailflat.net", headers={"X-API-Key": "mf_test_x"}
    )
    return MailFlatToolkit(client=MailFlat(api_key="mf_test_x", http_client=http))


def _tools_by_name(toolkit: MailFlatToolkit) -> dict:
    return {t.name: t for t in toolkit.get_tools()}


# --------------------------------------------------------------------- shape
def test_get_tools_returns_six_named_tools():
    toolkit = make_toolkit(lambda req: httpx.Response(200, json={}))
    tools = _tools_by_name(toolkit)
    assert set(tools) == {
        "create_inbox",
        "list_inboxes",
        "read_messages",
        "wait_for_otp",
        "send_email",
        "delete_inbox",
    }
    # Her araç bir açıklama + çağrılabilir args schema taşımalı (LangChain BaseTool).
    for tool in tools.values():
        assert tool.description
        assert tool.args_schema is not None


# -------------------------------------------------------------------- create
def test_create_inbox():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path == "/api/v1/inboxes"
        assert json.loads(req.content) == {"label": "deep-research"}
        return httpx.Response(200, json={"ok": True, "address": ADDR, "name": "deep-research"})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["create_inbox"].invoke({"label": "deep-research"})
    assert out["address"] == ADDR


# ---------------------------------------------------------------------- list
def test_list_inboxes():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v1/inboxes"
        return httpx.Response(200, json={"ok": True, "inboxes": [{"address": ADDR}]})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["list_inboxes"].invoke({})
    assert out["inboxes"][0]["address"] == ADDR


# --------------------------------------------------------------------- read
def test_read_messages():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/api/v1/inboxes/{ADDR}/messages"
        return httpx.Response(200, json={"ok": True, "emails": [{"id": 1, "subject": "Hi"}]})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["read_messages"].invoke({"address": ADDR})
    assert out["emails"][0]["subject"] == "Hi"


# ------------------------------------------------------------------ wait_otp
def test_wait_for_otp_success():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/api/v1/inboxes/{ADDR}/latest"
        return httpx.Response(200, json={"email": {"otp_code": "987654"}})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["wait_for_otp"].invoke({"address": ADDR, "timeout": 5})
    assert out["otp_code"] == "987654"


def test_wait_for_otp_timeout():
    handler = lambda req: httpx.Response(200, json={"email": None})
    tools = _tools_by_name(make_toolkit(handler))
    out = tools["wait_for_otp"].invoke({"address": ADDR, "timeout": 0})
    assert out["otp_code"] is None and out["error"] == "timeout"


def test_wait_for_otp_encrypted():
    handler = lambda req: httpx.Response(200, json={"encrypted": True, "note": "E2E inbox"})
    tools = _tools_by_name(make_toolkit(handler))
    out = tools["wait_for_otp"].invoke({"address": ADDR, "timeout": 5})
    assert out["otp_code"] is None and out["encrypted"] is True


# --------------------------------------------------------------------- send
def test_send_email():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/api/v1/inboxes/{ADDR}/send"
        assert json.loads(req.content) == {"to": "x@y.com", "subject": "Hi", "body": "Yo"}
        return httpx.Response(200, json={"ok": True, "status": "sent"})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["send_email"].invoke(
        {"address": ADDR, "to": "x@y.com", "subject": "Hi", "body": "Yo"}
    )
    assert out["status"] == "sent"


# ------------------------------------------------------------------- delete
def test_delete_inbox():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        assert req.url.path == f"/api/v1/inboxes/{ADDR}"
        return httpx.Response(200, json={"ok": True})

    tools = _tools_by_name(make_toolkit(handler))
    out = tools["delete_inbox"].invoke({"address": ADDR})
    assert out["ok"] is True


# ----------------------------------------------------------------- err guard
def test_error_returned_not_raised():
    handler = lambda req: httpx.Response(401, json={"detail": "Invalid API key"})
    tools = _tools_by_name(make_toolkit(handler))
    out = tools["create_inbox"].invoke({"label": "x"})
    assert "Invalid API key" in out["error"]
