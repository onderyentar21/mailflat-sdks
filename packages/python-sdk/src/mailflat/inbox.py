"""Inbox + Message — high-level operations on one MailFlat inbox and its messages.

`Inbox` is returned by the `MailFlat` client and carries the read, wait, send and delete
methods. `Message` is the typed form of an /api/v1 email payload.

Connected to:
  - imports from: mailflat.errors
  - imported by:  mailflat.client, mailflat.__init__

Key exports:
  - `Inbox` — `.address`, `.messages()`, `.latest()`, `.wait_for_message()`,
    `.wait_for_otp()`, `.send()`, `.mark_read()`, `.burn()`, `.download_attachment()`
  - `Message` — `.otp`, `.subject`, `.text`, `.html`, `.links`, `.attachments`, `.spam`, ...
  - `Attachment` — `.filename`, `.size_bytes`, `.download()`
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from email.utils import parseaddr

from .errors import EncryptedInboxError, MailFlatError, OTPTimeoutError

if TYPE_CHECKING:  # avoid a circular import (type hint only)
    from .client import MailFlat

# Direction filters (server contract). "in" is the default: for an agent, "did a message
# arrive?" cannot be answered by mail the agent itself sent.
DIRECTIONS = ("in", "out", "all")


def _reply_subject(subject: str | None) -> str:
    """`Re:` prefix without doubling it up.

    Mail clients also use the subject when threading, so "Re: Re: Re: x" and a bare subject
    both risk breaking the conversation apart.
    """
    text = (subject or "").strip()
    if not text:
        return "Re:"
    return text if text.lower().startswith("re:") else f"Re: {text}"


def _check_direction(direction: str) -> str:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS!r}, got {direction!r}")
    return direction


@dataclass
class Attachment:
    """Attachment metadata. The bytes are fetched on demand with `.download()`.

    Contents are never included in a message listing: a single 5 MB attachment would make
    the list unusable, so the bytes live behind a separate request.
    """

    id: int | None = None
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    is_encrypted: bool = False
    truncated: bool = False  # True → file exceeded the storage cap; bytes were never stored
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _message: "Message | None" = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attachment":
        return cls(
            id=data.get("id"),
            filename=data.get("filename"),
            content_type=data.get("content_type"),
            size_bytes=data.get("size_bytes"),
            is_encrypted=bool(data.get("is_encrypted")),
            truncated=bool(data.get("truncated")),
            raw=data,
        )

    def download(self) -> bytes:
        """Download this attachment's bytes.

        Raises `MailFlatError` when the attachment is not attached to a message, when the
        file was too large to store (`truncated`), or when the inbox is end-to-end encrypted
        (the server cannot decrypt it).
        """
        if self._message is None or self._message._inbox is None or self.id is None:
            raise MailFlatError(
                "This attachment isn't attached to a message. "
                "Use inbox.download_attachment(message_id, attachment_id) instead."
            )
        if self.truncated:
            raise MailFlatError(f"Attachment {self.filename!r} was too large to store")
        return self._message._inbox.download_attachment(self._message.id, self.id)


@dataclass
class Message:
    """A single email — the typed form of the /api/v1 payload."""

    id: int | None = None
    sender: str | None = None
    subject: str | None = None
    text: str | None = None            # body_text
    html: str | None = None            # body_html
    otp: str | None = None             # otp_code (when the server extracted one)
    tag: str | None = None
    to_address: str | None = None
    is_encrypted: bool = False
    direction: str | None = None       # "in" | "out"
    is_read: bool = False
    send_status: str | None = None
    send_error: str | None = None
    received_at: str | None = None
    # URLs found in the body (HTML hrefs first, then plain text). Verification-link flows
    # read this instead of parsing the body themselves.
    links: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    # {score, required, is_spam, rules, scanner}, or None when the message was NOT SCANNED
    # (not the same as a score of 0.0).
    # NOTE: spam scanning is currently disabled on mailflat.net, so in practice this is
    # None for every message today. The field is wired end to end and will start carrying
    # data as soon as scanning is switched back on.
    spam: dict[str, Any] | None = None
    # Raw message headers (Message-ID lives here — needed for threading and dedup).
    # None on encrypted inboxes: headers carry the Subject, so they go inside the envelope.
    headers: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    # The Inbox this message came from (powers msg.delete()). Filled in by
    # Inbox.messages() / latest() / wait_*.
    _inbox: "Inbox | None" = field(default=None, repr=False, compare=False)

    def delete(self) -> dict[str, Any]:
        """Delete this message (the inbox itself stays)."""
        if self._inbox is None or self.id is None:
            raise ValueError(
                "This message isn't attached to an inbox (or has no id). "
                "Use inbox.delete_message(message_id) instead."
            )
        return self._inbox.delete_message(self.id)

    def header(self, name: str, default: Any = None) -> Any:
        """Look up a header case-insensitively, e.g. `msg.header("message-id")`.

        Header names are case-insensitive per RFC 5322, but `headers` is a plain dict whose
        keys come straight off the wire — the real key is `Message-ID`, so
        `headers["Message-Id"]` raises KeyError. Use this instead of indexing.
        """
        if not self.headers:
            return default
        target = name.replace("_", "-").lower()
        for key, value in self.headers.items():
            if str(key).lower() == target:
                return value
        return default

    @property
    def message_id(self) -> str | None:
        """This message's `Message-ID`, or None when headers were not stored."""
        return self.header("message-id")

    @property
    def reply_to_address(self) -> str | None:
        """Where a reply should actually go: `Reply-To`, else `From`, else the envelope sender.

        `.sender` is the SMTP envelope sender (MAIL FROM). For transactional mail that is
        usually a bounce address such as `bounces+abc@sendgrid.net`, so replying to it reaches
        a bounce processor rather than a person. RFC 5322 says a reply goes to `Reply-To` when
        present and to `From` otherwise; the envelope address is only a last resort.
        """
        for name in ("reply-to", "from"):
            value = self.header(name)
            if isinstance(value, list):
                value = value[0] if value else None
            if value:
                addr = parseaddr(str(value))[1]
                if addr and "@" in addr:
                    return addr
        return self.sender

    def reply(self, body: str = "", *, html: str | None = None,
              subject: str | None = None) -> dict[str, Any]:
        """Reply to this message, keeping it in the same conversation.

        Fills in what a reply needs and is easy to get wrong by hand: the recipient, an
        `Re:` subject that is not doubled up, and the `In-Reply-To` / `References` headers
        Gmail and Outlook use to thread. Without those headers a reply shows up as a separate
        conversation, which is what a hand-rolled `send()` produces.

        The recipient comes from `reply_to_address`, not from `.sender`: the envelope sender of
        transactional mail is usually a bounce address, so `send(to=msg.sender, ...)` quietly
        delivers the reply to a machine.
        """
        if self._inbox is None:
            raise ValueError(
                "This message isn't attached to an inbox. Use inbox.send(...) instead."
            )
        target = self.reply_to_address
        if not target:
            raise ValueError("This message has no sender to reply to.")
        return self._inbox.send(
            target,
            subject=subject if subject is not None else _reply_subject(self.subject),
            body=body,
            html=html,
            in_reply_to=self.message_id,
        )

    def mark_read(self) -> dict[str, Any]:
        """Mark this message as read, so the next poll can skip it."""
        if self._inbox is None or self.id is None:
            raise ValueError(
                "This message isn't attached to an inbox (or has no id). "
                "Use inbox.mark_read(message_id) instead."
            )
        return self._inbox.mark_read(self.id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        msg = cls(
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
            links=list(data.get("links") or []),
            spam=data.get("spam"),
            headers=data.get("headers"),
            raw=data,
        )
        msg.attachments = [Attachment.from_dict(a) for a in (data.get("attachments") or [])]
        for att in msg.attachments:
            att._message = msg
        return msg


class Inbox:
    """Operations on a single MailFlat inbox.

    Obtained from `MailFlat.create()` / `.list()` / `.inbox(address)` rather than
    constructed directly.
    """

    def __init__(self, client: "MailFlat", address: str, **meta: Any) -> None:
        self._client = client
        self.address: str = address
        # Extra fields carried by the create/list response, when present.
        self.name: str | None = meta.get("name")
        self.api_key: str | None = meta.get("api_key")  # per-inbox key (mf_sk_...)
        self.retention_hours: int | None = meta.get("retention_hours")
        self.encrypted: bool = bool(meta.get("encrypted"))
        self.via_api: bool | None = meta.get("via_api")
        self.created_at: str | None = meta.get("created_at")
        # The full backend payload (symmetric with Message.raw) — used by the MCP/agent layer.
        self.raw: dict[str, Any] = {"address": address, **meta}

    def __repr__(self) -> str:
        return f"<Inbox {self.address!r}>"

    # ----------------------------------------------------------------- okuma
    def _wrap(self, data: dict[str, Any]) -> Message:
        """Convert an API payload into a Message and attach this inbox (for msg.delete())."""
        m = Message.from_dict(data)
        m._inbox = self
        return m

    def messages(self, *, direction: str = "in") -> list[Message]:
        """Return this inbox's messages, newest first.

        `direction` defaults to `"in"`: received mail only. Pass `"out"` for mail you sent
        from this address, or `"all"` for both.
        """
        _check_direction(direction)
        res = self._client._get(
            f"/api/v1/inboxes/{self.address}/messages?direction={direction}")
        return [self._wrap(e) for e in (res.get("emails") or [])]

    def latest(self, *, direction: str = "in") -> Message | None:
        """Return the most recent message, or None when the inbox is empty.

        Defaults to received mail. Before 0.4.0 this also returned mail you had just sent,
        which made `send()` followed by `wait_for_message()` return your own message.
        """
        _check_direction(direction)
        res = self._client._get(
            f"/api/v1/inboxes/{self.address}/latest?direction={direction}")
        email = res.get("email")
        return self._wrap(email) if email else None

    def wait_for_message(
        self, *, timeout: float = 30, poll_interval: float = 1.0, direction: str = "in"
    ) -> Message:
        """Poll until a message arrives and return it.

        Only received mail counts by default, so an agent can `send()` to a peer and then
        wait for the reply without immediately matching its own outgoing message.

        Raises `OTPTimeoutError` on timeout, `EncryptedInboxError` on an E2E inbox.
        """
        _check_direction(direction)
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            res = self._client._get(
                f"/api/v1/inboxes/{self.address}/latest?direction={direction}")
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
        """Poll until an OTP arrives and return the code.

        Raises `OTPTimeoutError` on timeout, `EncryptedInboxError` on an E2E inbox.

        If mail did arrive but no code could be extracted from it, the timeout error says so
        and quotes the newest message, so you can read `inbox.latest().text` yourself instead
        of hunting for a delivery problem that does not exist.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        seen: dict[str, Any] | None = None      # newest INCOMING mail, code or not
        while True:
            res = self._client._get(f"/api/v1/inboxes/{self.address}/latest?direction=in")
            if res.get("encrypted"):
                raise EncryptedInboxError(
                    res.get("note") or "This inbox is end-to-end encrypted; "
                    "OTP cannot be read via the API."
                )
            email = res.get("email") or {}
            otp = email.get("otp_code")
            if otp:
                return otp
            if email:
                seen = email
            if time.monotonic() >= deadline:
                raise OTPTimeoutError(self._otp_timeout_message(timeout, seen))
            time.sleep(poll_interval)

    def _otp_timeout_message(self, timeout: float, seen: dict[str, Any] | None) -> str:
        """Build a timeout message that distinguishes "nothing arrived" from "no code in it".

        These are completely different problems and used to produce the same sentence: the
        user went looking for a delivery failure while the message was sitting in the inbox
        with a code the parser did not recognise.
        """
        if not seen:
            return f"No message arrived for {self.address} within {timeout}s"
        subject = (seen.get("subject") or "(no subject)").strip()
        snippet = " ".join((seen.get("body_text") or "").split())[:120]
        return (
            f"Mail arrived for {self.address} but no OTP could be extracted from it "
            f"within {timeout}s. Newest message: {subject!r}"
            + (f" — {snippet!r}" if snippet else "")
            + ". Read inbox.latest().text and parse the code yourself, "
            "and please report the format so we can support it."
        )

    def download_attachment(self, message_id: int, attachment_id: int) -> bytes:
        """Download one attachment's bytes.

        Metadata already ships with each message (`msg.attachments`); this fetches the file
        itself. Prefer `msg.attachments[0].download()`.
        """
        resp = self._client._get_bytes(
            f"/api/v1/inboxes/{self.address}/messages/{message_id}/attachments/{attachment_id}"
        )
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            # On an encrypted inbox the server cannot decrypt: it returns the envelope
            # JSON rather than the bytes.
            raise EncryptedInboxError(
                "This inbox is end-to-end encrypted; the server cannot decrypt this attachment."
            )
        return resp.content

    # ----------------------------------------------------------------- yazma
    def send(
        self, to: str, *, subject: str = "", body: str = "", html: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send mail from this inbox's address (DKIM-signed, through our own MTA).

        Pass `in_reply_to` (a `Message-ID`) to keep the mail in an existing conversation;
        without it the recipient's client starts a new thread. `Message.reply()` fills this
        in for you.

        Not retried on gateway errors: a retried send can deliver the same mail twice.
        """
        payload: dict[str, Any] = {"to": to, "subject": subject, "body": body}
        if html is not None:
            payload["html"] = html
        if in_reply_to is not None:
            payload["in_reply_to"] = in_reply_to
        return self._client._post(f"/api/v1/inboxes/{self.address}/send", payload)

    def mark_read(self, message_id: int) -> dict[str, Any]:
        """Mark one message as read.

        Lets an agent poll for *new* mail instead of re-reading the whole inbox and
        tracking state on its own.
        """
        return self._client._post(
            f"/api/v1/inboxes/{self.address}/messages/{message_id}/read", idempotent=True)

    def burn(self) -> dict[str, Any]:
        """Delete every message in this inbox and keep the address.

        Useful between test scenarios: the address stays registered wherever you used it.
        """
        return self._client._post(f"/api/v1/inboxes/{self.address}/burn", idempotent=True)

    def delete(self) -> dict[str, Any]:
        """Delete this inbox and all of its messages. Cannot be undone."""
        return self._client._delete(f"/api/v1/inboxes/{self.address}")

    def delete_message(self, message_id: int) -> dict[str, Any]:
        """Delete a single message; the inbox stays. Backs `Message.delete()`."""
        return self._client._delete(
            f"/api/v1/inboxes/{self.address}/messages/{message_id}")
