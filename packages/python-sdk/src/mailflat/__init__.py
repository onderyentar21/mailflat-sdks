"""MailFlat Python SDK — the official client for automation-friendly email inboxes.

`pip install mailflat` → `from mailflat import MailFlat`.

Connected to:
  - imports from: mailflat.client, mailflat.inbox, mailflat.errors
  - imported by:  user code, mailflat-mcp, mailflat.langchain

Key exports:
  - `MailFlat` — client
  - `Inbox`, `Message`, `Attachment` — domain types
  - errors: `MailFlatError`, `AuthenticationError`, `MailFlatPermissionError`,
    `NotFoundError`, `RateLimitError`, `APIError`, `OTPTimeoutError`, `EncryptedInboxError`
  - `redact_secrets()` — strips secret fields from agent tool output (used by MCP/LangChain)
"""
from __future__ import annotations

from .client import MailFlat
from .errors import (
    APIError,
    AuthenticationError,
    EncryptedInboxError,
    MailFlatError,
    MailFlatPermissionError,
    NotFoundError,
    OTPTimeoutError,
    PermissionError,
    RateLimitError,
)
from .inbox import Attachment, Inbox, Message
from .redact import redact_secrets

# The package's ONLY version source — pyproject.toml reads it via [tool.hatch.version].
# Releasing = bump this line and nothing else.
__version__ = "0.6.1"

__all__ = [
    "MailFlat",
    "Inbox",
    "Message",
    "Attachment",
    "MailFlatError",
    "AuthenticationError",
    "MailFlatPermissionError",
    "PermissionError",  # deprecated alias of MailFlatPermissionError
    "NotFoundError",
    "RateLimitError",
    "APIError",
    "OTPTimeoutError",
    "EncryptedInboxError",
    "redact_secrets",
    "__version__",
]
