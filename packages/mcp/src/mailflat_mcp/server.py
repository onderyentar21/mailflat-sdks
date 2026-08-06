"""MailFlat MCP server — an 11-tool set for GPT/Claude/Cursor/LangChain.

A thin MCP shell over the `mailflat` Python SDK; HTTP and behaviour live in the SDK.
Auth: `MAILFLAT_API_KEY` env var (the `mf_live_...` key from your dashboard).

Running it:
    uvx mailflat-mcp                 # from PyPI, in an isolated environment
    MAILFLAT_API_KEY=mf_live_... uvx mailflat-mcp

Connected to:
  - depends on: mailflat (SDK), mcp (FastMCP)
  - used by:    Claude Desktop / Cursor / any MCP client

⚠️ Failures RAISE (`ToolError`) rather than returning `{"error": ...}`: MCP marks a raised
tool call with `isError`, and a client that only sees a JSON body treats a returned error as a
successful call. The message carries the detail the model needs to recover.

⚠️ Tool output goes through `redact_secrets()`: the per-inbox `api_key` in a backend
response must never reach the model's context (and from there prompt logs) — see B-055.

Key exports (MCP tools):
  - create_inbox(prefix?, label?, retention_hours?)
  - list_inboxes()
  - read_messages(address, direction="in")
  - wait_for_otp(address, timeout=30)
  - wait_for_message(address, timeout=30)
  - send_email(address, to, subject?, body?, html?)
  - reply(address, message_id, body?, html?)
  - mark_read(address, message_id)
  - burn_inbox(address)
  - delete_inbox(address)
  - delete_message(address, message_id)
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from mailflat import EncryptedInboxError, MailFlat, MailFlatError, OTPTimeoutError, redact_secrets

from ._version import __version__

mcp = FastMCP("mailflat")
# FastMCP has no `version=` parameter, so the underlying server reports the `mcp` LIBRARY
# version in `serverInfo` — a client asking which MailFlat server it is talking to was told
# "1.29.0". Set it on the low-level server the SDK builds for us. Guarded because this reaches
# past the documented surface: a future `mcp` release may move the attribute, and an MCP server
# that refuses to start is far worse than one reporting the wrong version.
try:  # pragma: no cover - depends on the installed mcp version
    mcp._mcp_server.version = __version__
except Exception:  # noqa: BLE001 - never let cosmetics break startup
    pass


def _client() -> MailFlat:
    """SDK client built from MAILFLAT_API_KEY. Monkeypatched in tests."""
    return MailFlat(
        api_key=os.environ.get("MAILFLAT_API_KEY") or "",
        base_url=os.environ.get("MAILFLAT_API_URL", "https://mailflat.net"),
    )


@mcp.tool()
def create_inbox(prefix: str = "", label: str = "", retention_hours: int = 0) -> dict:
    """Create a real disposable email inbox. Returns the inbox address.
    `retention_hours` is optional (0 = your plan's max); requests above your plan are capped."""
    try:
        with _client() as c:
            inbox = c.create(
                prefix=prefix or None,
                label=label or None,
                retention_hours=retention_hours if retention_hours and retention_hours > 0 else None,
            )
            return redact_secrets(inbox.raw)
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def list_inboxes() -> dict:
    """List all inboxes available to this API key."""
    try:
        with _client() as c:
            return redact_secrets({"ok": True, "inboxes": [i.raw for i in c.list()]})
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def read_messages(address: str, direction: str = "in") -> dict:
    """Read messages in the given inbox address (newest first).

    `direction` is "in" for received mail (default), "out" for mail sent from this
    address, or "all" for both. Received mail is the default so that a reply you are
    waiting for is not confused with a message you just sent."""
    try:
        with _client() as c:
            msgs = c.inbox(address).messages(direction=direction)
            return redact_secrets({"ok": True, "emails": [m.raw for m in msgs]})
    except ValueError as e:      # invalid direction — caught before any network call
        raise ToolError(str(e)) from e
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def wait_for_otp(address: str, timeout: int = 30) -> dict:
    """Poll the inbox until an OTP code arrives (or timeout). Returns {otp_code, email}."""
    try:
        with _client() as c:
            inbox = c.inbox(address)
            otp = inbox.wait_for_otp(timeout=timeout)
            latest = inbox.latest()
            return redact_secrets({"otp_code": otp, "email": latest.raw if latest else None})
    except OTPTimeoutError as e:
        # The SDK's timeout text distinguishes "nothing arrived" from "mail arrived but no code
        # could be extracted" and quotes the message — that sentence is what lets the model
        # recover, so it must reach it as the error itself.
        raise ToolError(str(e)) from e
    except EncryptedInboxError as e:
        raise ToolError(str(e)) from e
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def wait_for_message(address: str, timeout: int = 30) -> dict:
    """Poll the inbox until a new message ARRIVES (or timeout). Returns {email}.

    Only received mail counts, so you can send to a peer and then wait for their reply
    without matching your own outgoing message."""
    try:
        with _client() as c:
            msg = c.inbox(address).wait_for_message(timeout=timeout)
            return redact_secrets({"ok": True, "email": msg.raw})
    except OTPTimeoutError as e:
        raise ToolError(str(e)) from e
    except EncryptedInboxError as e:
        raise ToolError(str(e)) from e
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def send_email(address: str, to: str, subject: str = "", body: str = "", html: str = "") -> dict:
    """Send an email FROM the given inbox address (DKIM-signed via MailFlat's MTA).
    Use for replies or outbound automation. `html` is optional."""
    try:
        with _client() as c:
            return redact_secrets(c.inbox(address).send(to, subject=subject, body=body, html=html or None))
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def reply(address: str, message_id: int, body: str = "", html: str = "") -> dict:
    """Reply to a message so it stays in the SAME conversation.

    Prefer this over send_email when answering: it fills in the recipient, an `Re:` subject
    and the threading headers. A plain send_email starts a new conversation in the
    recipient's client, which does not look like a reply."""
    try:
        with _client() as c:
            inbox = c.inbox(address)
            target = next((m for m in inbox.messages(direction="all") if m.id == message_id), None)
            if target is None:
                raise ToolError(f"Message {message_id} not found in {address}")
            return redact_secrets(target.reply(body, html=html or None))
    except MailFlatError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def mark_read(address: str, message_id: int) -> dict:
    """Mark one message as read so later polls can skip it."""
    try:
        with _client() as c:
            return redact_secrets(c.inbox(address).mark_read(message_id))
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def burn_inbox(address: str) -> dict:
    """Delete every message in an inbox but KEEP the address.

    Use between scenarios: the address stays registered wherever you already used it."""
    try:
        with _client() as c:
            return redact_secrets(c.inbox(address).burn())
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def delete_inbox(address: str) -> dict:
    """Delete an inbox and all its messages by address. Irreversible."""
    try:
        with _client() as c:
            return redact_secrets(c.inbox(address).delete())
    except MailFlatError as e:
        raise ToolError(str(e)) from e

@mcp.tool()
def delete_message(address: str, message_id: int) -> dict:
    """Delete a single message in an inbox by its id (the inbox itself stays)."""
    try:
        with _client() as c:
            return redact_secrets(c.inbox(address).delete_message(message_id))
    except MailFlatError as e:
        raise ToolError(str(e)) from e

def main():
    mcp.run()  # stdio transport (MCP clients connect to this)


if __name__ == "__main__":
    main()
