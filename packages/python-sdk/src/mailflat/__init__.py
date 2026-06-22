"""MailFlat Python SDK — disposable, otomasyon-dostu e-posta inbox'ları için resmi client.

`pip install mailflat` → `from mailflat import MailFlat`.

Connected to:
  - imports from: mailflat.client, mailflat.inbox, mailflat.errors
  - imported by:  kullanıcı kodu, mailflat-mcp, mailflat.langchain

Key exports:
  - `MailFlat` — client
  - `Inbox`, `Message` — domain tipleri
  - hata tipleri: `MailFlatError`, `AuthenticationError`, `PermissionError`,
    `NotFoundError`, `RateLimitError`, `APIError`, `OTPTimeoutError`, `EncryptedInboxError`
"""
from __future__ import annotations

from .client import MailFlat
from .errors import (
    APIError,
    AuthenticationError,
    EncryptedInboxError,
    MailFlatError,
    NotFoundError,
    OTPTimeoutError,
    PermissionError,
    RateLimitError,
)
from .inbox import Inbox, Message

__version__ = "0.2.0"

__all__ = [
    "MailFlat",
    "Inbox",
    "Message",
    "MailFlatError",
    "AuthenticationError",
    "PermissionError",
    "NotFoundError",
    "RateLimitError",
    "APIError",
    "OTPTimeoutError",
    "EncryptedInboxError",
    "__version__",
]
