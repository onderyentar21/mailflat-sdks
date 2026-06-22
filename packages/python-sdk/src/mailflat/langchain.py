"""MailFlat LangChain entegrasyonu — `MailFlatToolkit` + 6 araçlık LangChain tool seti.

`mailflat` SDK'sının üstüne ince bir LangChain kabuğu; tüm HTTP/iş mantığı client'ta (DRY).
`langchain-core` opsiyonel bağımlılıktır → `pip install mailflat[langchain]`.

Kullanım:
    from mailflat.langchain import MailFlatToolkit
    toolkit = MailFlatToolkit(api_key=env("MAILFLAT_KEY"))
    tools = toolkit.get_tools()   # create_inbox, list_inboxes, read_messages,
                                  # wait_for_otp, send_email, delete_inbox

Connected to:
  - imports from: mailflat.client (MailFlat), langchain_core.tools (StructuredTool)
  - imported by:  kullanıcı kodu (LangChain ajanları)

Key exports:
  - `MailFlatToolkit(api_key=..., base_url=...)` — `.get_tools()` → list[BaseTool]
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from langchain_core.tools import BaseTool, StructuredTool
except ImportError as exc:  # langchain-core kurulu değil → açıklayıcı hata
    raise ImportError(
        "MailFlat's LangChain integration requires 'langchain-core'. "
        "Install it with:  pip install mailflat[langchain]"
    ) from exc

from .client import DEFAULT_BASE_URL, MailFlat
from .errors import EncryptedInboxError, MailFlatError, OTPTimeoutError

if TYPE_CHECKING:
    from collections.abc import Sequence


class MailFlatToolkit:
    """MailFlat araçlarını bir LangChain ajanına bağlamak için toolkit.

    >>> from mailflat.langchain import MailFlatToolkit
    >>> toolkit = MailFlatToolkit(api_key="mf_live_...")
    >>> tools = toolkit.get_tools()
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: MailFlat | None = None,
    ) -> None:
        # client enjeksiyonu testleri kolaylaştırır; yoksa api_key ile kurulur.
        self._client = client or MailFlat(api_key=api_key, base_url=base_url)

    # ------------------------------------------------------------------ tools
    def get_tools(self) -> "Sequence[BaseTool]":
        """6 MailFlat aracını LangChain `BaseTool` listesi olarak döndürür."""
        client = self._client

        def create_inbox(prefix: str = "", label: str = "", retention_hours: int = 0) -> dict:
            """Create a real disposable email inbox and return its address.

            Args:
                prefix: Optional left-hand prefix (e.g. 'signup'); random if empty.
                label: Optional human label to remember what this inbox is for.
                retention_hours: Optional retention in hours; 0 = your plan's max,
                    values above your plan are capped.
            """
            try:
                inbox = client.create(
                    prefix=prefix or None,
                    label=label or None,
                    retention_hours=retention_hours if retention_hours and retention_hours > 0 else None,
                )
                return inbox.raw
            except MailFlatError as e:
                return {"error": str(e)}

        def list_inboxes() -> dict:
            """List all inboxes available to this API key."""
            try:
                return {"ok": True, "inboxes": [i.raw for i in client.list()]}
            except MailFlatError as e:
                return {"error": str(e)}

        def read_messages(address: str) -> dict:
            """Read all messages in the given inbox address (newest first).

            Args:
                address: The full inbox address, e.g. signup-8f3@mailflat.net.
            """
            try:
                return {"ok": True, "emails": [m.raw for m in client.inbox(address).messages()]}
            except MailFlatError as e:
                return {"error": str(e)}

        def wait_for_otp(address: str, timeout: int = 30) -> dict:
            """Poll the inbox until a one-time verification code (OTP) arrives.

            Args:
                address: The inbox address to poll.
                timeout: Maximum seconds to wait before giving up (default 30).
            """
            try:
                inbox = client.inbox(address)
                otp = inbox.wait_for_otp(timeout=timeout)
                latest = inbox.latest()
                return {"otp_code": otp, "email": latest.raw if latest else None}
            except OTPTimeoutError:
                return {"otp_code": None, "error": "timeout"}
            except EncryptedInboxError as e:
                return {"otp_code": None, "encrypted": True, "error": str(e)}
            except MailFlatError as e:
                return {"otp_code": None, "error": str(e)}

        def send_email(
            address: str, to: str, subject: str = "", body: str = "", html: str = ""
        ) -> dict:
            """Send an email FROM the given inbox address (DKIM-signed via MailFlat's MTA).

            Args:
                address: The inbox address to send from (must belong to this API key).
                to: Recipient email address.
                subject: Email subject line.
                body: Plain-text body.
                html: Optional HTML body.
            """
            try:
                return client.inbox(address).send(to, subject=subject, body=body, html=html or None)
            except MailFlatError as e:
                return {"error": str(e)}

        def delete_inbox(address: str) -> dict:
            """Delete an inbox and all its messages by address. Irreversible.

            Args:
                address: The inbox address to delete.
            """
            try:
                return client.inbox(address).delete()
            except MailFlatError as e:
                return {"error": str(e)}

        funcs: list[Any] = [
            create_inbox,
            list_inboxes,
            read_messages,
            wait_for_otp,
            send_email,
            delete_inbox,
        ]
        # from_function tip ipuçları + docstring'den args_schema'yı kendisi çıkarır
        # (pydantic v1/v2 sürüm farkı bu yolla atlanır).
        return [StructuredTool.from_function(func=f) for f in funcs]
