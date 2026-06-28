"""Inbox + Message — bir MailFlat inbox'ı ve mesajları üzerindeki yüksek seviye işlemler.

`Inbox`, `MailFlat` client tarafından döndürülür; mesaj okuma, OTP bekleme, gönderme ve
silme metodlarını taşır. `Message`, /api/v1 e-posta yanıtının tiplenmiş hâlidir.

Connected to:
  - imports from: mailflat.errors
  - imported by:  mailflat.client, mailflat.__init__

Key exports:
  - `Inbox` — `.address`, `.messages()`, `.latest()`, `.wait_for_otp()`, `.send()`, `.delete()`
  - `Message` — `.otp`, `.subject`, `.text`, `.html`, `.sender`, ...
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .errors import EncryptedInboxError, OTPTimeoutError

if TYPE_CHECKING:  # döngüsel import'tan kaçın (sadece tip ipucu)
    from .client import MailFlat


@dataclass
class Message:
    """Tek bir e-posta — /api/v1 serialize çıktısının tiplenmiş hâli."""

    id: int | None = None
    sender: str | None = None
    subject: str | None = None
    text: str | None = None            # body_text
    html: str | None = None            # body_html
    otp: str | None = None             # otp_code (sunucu çıkardıysa)
    tag: str | None = None
    to_address: str | None = None
    is_encrypted: bool = False
    direction: str | None = None       # "in" | "out"
    is_read: bool = False
    send_status: str | None = None
    send_error: str | None = None
    received_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    # Bu mesajı döndüren Inbox (msg.delete() şekeri için). Inbox.messages()/latest()/wait_* doldurur.
    _inbox: "Inbox | None" = field(default=None, repr=False, compare=False)

    def delete(self) -> dict[str, Any]:
        """Bu maili sil (inbox kalır). Mesaj bir Inbox'tan geldiyse çalışır."""
        if self._inbox is None or self.id is None:
            raise ValueError(
                "This message isn't attached to an inbox (or has no id). "
                "Use inbox.delete_message(message_id) instead."
            )
        return self._inbox.delete_message(self.id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            id=data.get("id"),
            sender=data.get("sender"),
            subject=data.get("subject"),
            text=data.get("body_text"),
            html=data.get("body_html"),
            otp=data.get("otp_code"),
            tag=data.get("tag"),
            to_address=data.get("to_address"),
            is_encrypted=bool(data.get("is_encrypted")),
            direction=data.get("direction"),
            is_read=bool(data.get("is_read")),
            send_status=data.get("send_status"),
            send_error=data.get("send_error"),
            received_at=data.get("received_at"),
            raw=data,
        )


class Inbox:
    """Tek bir disposable inbox üzerindeki işlemler.

    Doğrudan oluşturmak yerine `MailFlat.create()` / `.list()` / `.inbox(address)` ile alınır.
    """

    def __init__(self, client: "MailFlat", address: str, **meta: Any) -> None:
        self._client = client
        self.address: str = address
        # create/list yanıtından gelen ek alanlar (varsa)
        self.name: str | None = meta.get("name")
        self.api_key: str | None = meta.get("api_key")  # per-inbox key (mf_sk_...)
        self.retention_hours: int | None = meta.get("retention_hours")
        self.encrypted: bool = bool(meta.get("encrypted"))
        self.via_api: bool | None = meta.get("via_api")
        self.created_at: str | None = meta.get("created_at")
        # backend yanıtının tamamı (Message.raw ile simetrik) — MCP/agent katmanı için.
        self.raw: dict[str, Any] = {"address": address, **meta}

    def __repr__(self) -> str:
        return f"<Inbox {self.address!r}>"

    # ----------------------------------------------------------------- okuma
    def _wrap(self, data: dict[str, Any]) -> Message:
        """API mail dict'ini Message'a çevirir + bu inbox ref'ini iliştirir (msg.delete() için)."""
        m = Message.from_dict(data)
        m._inbox = self
        return m

    def messages(self) -> list[Message]:
        """Inbox'taki tüm mesajları (yeniden eskiye) döndürür."""
        res = self._client._get(f"/api/v1/inboxes/{self.address}/messages")
        return [self._wrap(e) for e in (res.get("emails") or [])]

    def latest(self) -> Message | None:
        """En son mesajı döndürür (yoksa None)."""
        res = self._client._get(f"/api/v1/inboxes/{self.address}/latest")
        email = res.get("email")
        return self._wrap(email) if email else None

    def wait_for_message(
        self, *, timeout: float = 30, poll_interval: float = 1.0
    ) -> Message:
        """Yeni bir mesaj gelene kadar poll'lar; gelince `Message` döndürür.

        timeout aşılırsa `OTPTimeoutError`, inbox E2E şifreliyse `EncryptedInboxError`.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            res = self._client._get(f"/api/v1/inboxes/{self.address}/latest")
            if res.get("encrypted"):
                raise EncryptedInboxError(
                    res.get("note") or "This inbox is end-to-end encrypted; "
                    "use a non-encrypted inbox for agent automation."
                )
            email = res.get("email")
            if email:
                return self._wrap(email)
            if time.monotonic() >= deadline:
                raise OTPTimeoutError(
                    f"No message arrived for {self.address} within {timeout}s"
                )
            time.sleep(poll_interval)

    def wait_for_otp(self, *, timeout: float = 30, poll_interval: float = 1.0) -> str:
        """OTP kodu gelene kadar poll'lar ve kodu (str) döndürür.

        timeout aşılırsa `OTPTimeoutError`, inbox E2E şifreliyse `EncryptedInboxError`.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            res = self._client._get(f"/api/v1/inboxes/{self.address}/latest")
            if res.get("encrypted"):
                raise EncryptedInboxError(
                    res.get("note") or "This inbox is end-to-end encrypted; "
                    "OTP cannot be read via the API."
                )
            email = res.get("email") or {}
            otp = email.get("otp_code")
            if otp:
                return otp
            if time.monotonic() >= deadline:
                raise OTPTimeoutError(
                    f"No OTP arrived for {self.address} within {timeout}s"
                )
            time.sleep(poll_interval)

    # ----------------------------------------------------------------- yazma
    def send(
        self, to: str, *, subject: str = "", body: str = "", html: str | None = None
    ) -> dict[str, Any]:
        """Bu inbox adresinden mail gönderir (DKIM imzalı, kendi MTA'mız üzerinden)."""
        payload: dict[str, Any] = {"to": to, "subject": subject, "body": body}
        if html is not None:
            payload["html"] = html
        return self._client._post(f"/api/v1/inboxes/{self.address}/send", payload)

    def delete(self) -> dict[str, Any]:
        """Inbox'u ve tüm mesajlarını siler. Geri alınamaz."""
        return self._client._delete(f"/api/v1/inboxes/{self.address}")

    def delete_message(self, message_id: int) -> dict[str, Any]:
        """Inbox'taki TEK bir maili siler (inbox kalır). `Message.delete()` bunu çağırır."""
        return self._client._delete(f"/api/v1/inboxes/{self.address}/messages/{message_id}")
