"""MailFlat SDK error types — maps HTTP status codes to meaningful Python exceptions.

Connected to:
  - imported by:  mailflat.client, mailflat.inbox, mailflat.__init__

Key exports:
  - `MailFlatError` — base class for every SDK error
  - `AuthenticationError` — 401 (missing/invalid API key)
  - `MailFlatPermissionError` — 403 (key does not own this inbox)
  - `NotFoundError` — 404
  - `RateLimitError` — 429 (carries `retry_after` when the server sent it)
  - `APIError` — any other 4xx/5xx
  - `OTPTimeoutError` — wait_for_otp / wait_for_message timed out
  - `EncryptedInboxError` — end-to-end encrypted inbox cannot be read through the API
"""
from __future__ import annotations


class MailFlatError(Exception):
    """Base class for every MailFlat SDK error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthenticationError(MailFlatError):
    """401 — the API key is missing or invalid."""


class MailFlatPermissionError(MailFlatError):
    """403 — this API key does not own that inbox."""


# Backwards compatibility: up to 0.3.3 this class was named `PermissionError` and SHADOWED
# the built-in. Someone writing `except PermissionError` in a module that never imported the
# SDK would catch the built-in and miss ours (or the reverse) — a silent, hard-to-diagnose
# bug. The old name stays as an alias so existing code keeps working.
PermissionError = MailFlatPermissionError  # noqa: A001 - deprecated alias, kept for compatibility


class NotFoundError(MailFlatError):
    """404 — the resource does not exist."""


class RateLimitError(MailFlatError):
    """429 — rate limit exceeded.

    `retry_after` holds the server's `Retry-After` value in seconds when it sent one,
    so callers can wait exactly as long as the server asked instead of guessing.
    """

    def __init__(self, message: str, *, status_code: int | None = None,
                 retry_after: float | None = None) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


class APIError(MailFlatError):
    """An unexpected 4xx/5xx response."""


class OTPTimeoutError(MailFlatError):
    """No OTP (or message) arrived before the timeout elapsed."""


class EncryptedInboxError(MailFlatError):
    """The inbox is end-to-end encrypted, so the server cannot read its contents."""


def raise_for_status(status_code: int, detail: str, *, retry_after: float | None = None) -> None:
    """Raise the matching `MailFlatError` subclass for an HTTP status code."""
    if status_code == 401:
        raise AuthenticationError(detail or "Invalid or missing API key", status_code=status_code)
    if status_code == 403:
        raise MailFlatPermissionError(
            detail or "This API key does not own that inbox", status_code=status_code)
    if status_code == 404:
        raise NotFoundError(detail or "Not found", status_code=status_code)
    if status_code == 429:
        raise RateLimitError(detail or "Rate limit exceeded", status_code=status_code,
                             retry_after=retry_after)
    raise APIError(detail or f"Request failed with status {status_code}", status_code=status_code)
