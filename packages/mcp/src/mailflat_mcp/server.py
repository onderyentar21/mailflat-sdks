"""MailFlat MCP server — GPT/Claude/Cursor/LangChain için 6 araçlık tool seti.

`mailflat` Python SDK'sının üstüne ince bir MCP kabuğu; HTTP/iş mantığı SDK'da (DRY).
Auth: `MAILFLAT_API_KEY` env (dashboard'dan alınan `mf_live_...`).

Çalıştırma:
    uvx mailflat-mcp                 # PyPI'den, izolasyonlu
    MAILFLAT_API_KEY=mf_live_... uvx mailflat-mcp

Connected to:
  - depends on: mailflat (SDK), mcp (FastMCP)
  - used by:    Claude Desktop / Cursor / herhangi bir MCP client

Key exports (MCP tools):
  - create_inbox(prefix?, label?, retention_hours?)
  - list_inboxes()
  - read_messages(address)
  - wait_for_otp(address, timeout=30)
  - send_email(address, to, subject?, body?, html?)
  - delete_inbox(address)
"""
import os

from mcp.server.fastmcp import FastMCP

from mailflat import EncryptedInboxError, MailFlat, MailFlatError, OTPTimeoutError

mcp = FastMCP("mailflat")


def _client() -> MailFlat:
    """SDK client (MAILFLAT_API_KEY ile). Testlerde monkeypatch edilir."""
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
            return inbox.raw
    except MailFlatError as e:
        return {"error": str(e)}


@mcp.tool()
def list_inboxes() -> dict:
    """List all inboxes available to this API key."""
    try:
        with _client() as c:
            return {"ok": True, "inboxes": [i.raw for i in c.list()]}
    except MailFlatError as e:
        return {"error": str(e)}


@mcp.tool()
def read_messages(address: str) -> dict:
    """Read all messages in the given inbox address."""
    try:
        with _client() as c:
            return {"ok": True, "emails": [m.raw for m in c.inbox(address).messages()]}
    except MailFlatError as e:
        return {"error": str(e)}


@mcp.tool()
def wait_for_otp(address: str, timeout: int = 30) -> dict:
    """Poll the inbox until an OTP code arrives (or timeout). Returns {otp_code, email}."""
    try:
        with _client() as c:
            inbox = c.inbox(address)
            otp = inbox.wait_for_otp(timeout=timeout)
            latest = inbox.latest()
            return {"otp_code": otp, "email": latest.raw if latest else None}
    except OTPTimeoutError:
        return {"otp_code": None, "error": "timeout"}
    except EncryptedInboxError as e:
        return {"otp_code": None, "encrypted": True, "error": str(e)}
    except MailFlatError as e:
        return {"otp_code": None, "error": str(e)}


@mcp.tool()
def send_email(address: str, to: str, subject: str = "", body: str = "", html: str = "") -> dict:
    """Send an email FROM the given inbox address (DKIM-signed via MailFlat's MTA).
    Use for replies or outbound automation. `html` is optional."""
    try:
        with _client() as c:
            return c.inbox(address).send(to, subject=subject, body=body, html=html or None)
    except MailFlatError as e:
        return {"error": str(e)}


@mcp.tool()
def delete_inbox(address: str) -> dict:
    """Delete an inbox and all its messages by address. Irreversible."""
    try:
        with _client() as c:
            return c.inbox(address).delete()
    except MailFlatError as e:
        return {"error": str(e)}


def main():
    mcp.run()  # stdio transport (MCP client'lar buna bağlanır)


if __name__ == "__main__":
    main()
