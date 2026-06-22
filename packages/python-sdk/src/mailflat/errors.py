"""MailFlat SDK hata tipleri — HTTP durum kodlarını anlamlı Python exception'larına çevirir.

Connected to:
  - imported by:  mailflat.client, mailflat.inbox, mailflat.__init__

Key exports:
  - `MailFlatError` — tüm SDK hatalarının tabanı
  - `AuthenticationError` — 401 (geçersiz/eksik API key)
  - `PermissionError` — 403 (key bu inbox'a sahip değil)
  - `NotFoundError` — 404
  - `RateLimitError` — 429
  - `APIError` — diğer 4xx/5xx
  - `OTPTimeoutError` — wait_for_otp süre aşımı
  - `EncryptedInboxError` — E2E inbox içeriği API'den okunamaz
"""
from __future__ import annotations


class MailFlatError(Exception):
    """Tüm MailFlat SDK hatalarının tabanı."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthenticationError(MailFlatError):
    """401 — API key eksik veya geçersiz."""


class PermissionError(MailFlatError):  # noqa: A001 - kasıtlı, SDK kapsamında net isim
    """403 — API key bu inbox'a sahip değil."""


class NotFoundError(MailFlatError):
    """404 — kaynak bulunamadı."""


class RateLimitError(MailFlatError):
    """429 — rate limit aşıldı."""


class APIError(MailFlatError):
    """Beklenmeyen 4xx/5xx yanıtı."""


class OTPTimeoutError(MailFlatError):
    """wait_for_otp verilen süre içinde OTP bulamadı."""


class EncryptedInboxError(MailFlatError):
    """Inbox uçtan uca şifreli — sunucu içeriği okuyamaz, OTP/gövde API'den alınamaz."""


def raise_for_status(status_code: int, detail: str) -> None:
    """HTTP durum kodunu uygun MailFlatError alt tipine çevirip fırlatır."""
    if status_code == 401:
        raise AuthenticationError(detail or "Invalid or missing API key", status_code=status_code)
    if status_code == 403:
        raise PermissionError(detail or "This API key does not own that inbox", status_code=status_code)
    if status_code == 404:
        raise NotFoundError(detail or "Not found", status_code=status_code)
    if status_code == 429:
        raise RateLimitError(detail or "Rate limit exceeded", status_code=status_code)
    raise APIError(detail or f"Request failed with status {status_code}", status_code=status_code)
