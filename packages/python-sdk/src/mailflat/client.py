"""MailFlat client — /api/v1 otomasyon API'sinin ince, tiplenmiş Python sarmalayıcısı.

Tek hesap API key'i (X-API-Key) ile inbox açar, listeler, mail/OTP okur ve mail gönderir.
Tüm üst katmanlar (MCP, LangChain) bu client'ı çağırır → tek kaynak.

Connected to:
  - imports from: mailflat.inbox, mailflat.errors (+ httpx)
  - imported by:  mailflat.__init__

Key exports:
  - `MailFlat(api_key=..., base_url=...)` — client
  - `.create(...) / .create_inbox(...)` — yeni inbox → `Inbox`
  - `.list()` — `Inbox` listesi
  - `.inbox(address)` — mevcut adrese bağlan
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .errors import MailFlatError, raise_for_status
from .inbox import Inbox

DEFAULT_BASE_URL = "https://mailflat.net"
_RETRY_STATUSES = {429, 502, 503, 504}


class MailFlat:
    """MailFlat otomasyon API client'ı.

    >>> from mailflat import MailFlat
    >>> mf = MailFlat(api_key="mf_live_...")
    >>> inbox = mf.create(label="signup-test")
    >>> inbox.address
    'signup-test-...@mailflat.net'
    >>> otp = inbox.wait_for_otp(timeout=30)
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        api_key = api_key or os.environ.get("MAILFLAT_API_KEY")
        if not api_key:
            raise MailFlatError(
                "An API key is required. Pass MailFlat(api_key=...) or set MAILFLAT_API_KEY."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(0, max_retries)
        # http_client enjeksiyonu testleri (httpx.MockTransport) kolaylaştırır.
        self._http = http_client or httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    # --------------------------------------------------------------- context
    def __enter__(self) -> "MailFlat":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --------------------------------------------------------------- HTTP iç
    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                resp = self._http.request(method, path, json=json)
            except httpx.HTTPError as exc:  # ağ/timeout
                raise MailFlatError(f"Network error: {exc}") from exc

            if resp.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                attempt += 1
                time.sleep(min(2 ** attempt * 0.5, 4.0))  # 1s, 2s, ... backoff
                continue

            try:
                data = resp.json()
            except ValueError:
                data = {}

            if resp.status_code >= 400:
                detail = ""
                if isinstance(data, dict):
                    detail = data.get("detail") or data.get("error") or ""
                raise_for_status(resp.status_code, detail)

            if isinstance(data, dict) and data.get("error"):  # güvenlik: 200 + error
                raise MailFlatError(data["error"], status_code=resp.status_code)
            return data if isinstance(data, dict) else {}

    def _get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json=json)

    def _delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path)

    # --------------------------------------------------------------- public
    def create(
        self,
        *,
        prefix: str | None = None,
        label: str | None = None,
        subdomain: str | None = None,
        domain: str | None = None,
        retention_hours: int | None = None,
    ) -> Inbox:
        """Yeni bir disposable inbox açar ve `Inbox` döndürür.

        - prefix: adresin local kısmı (boşsa rastgele `agent-...`)
        - label: inbox'a verilen isim (UI'da görünür; bazı planlarda yok sayılır)
        - subdomain: mailflat.net alt alanı (boşsa rastgele)
        - domain: BYOD doğrulanmış kendi domain'in (örn. acme.com)
        - retention_hours: mesaj saklama süresi (boş → plan varsayılanı; plan max'ı ile sınırlı)
        """
        payload: dict[str, Any] = {}
        if prefix is not None:
            payload["prefix"] = prefix
        if label is not None:
            payload["label"] = label
        if subdomain is not None:
            payload["subdomain"] = subdomain
        if domain is not None:
            payload["domain"] = domain
        if retention_hours is not None:
            payload["retention_hours"] = retention_hours
        res = self._post("/api/v1/inboxes", payload)
        return Inbox(self, res["address"], **{k: v for k, v in res.items() if k != "address"})

    # Landing snippet'leriyle birebir uyum için alias.
    create_inbox = create

    def list(self) -> list[Inbox]:
        """Bu API key ile açılmış (agent) inbox'ları döndürür."""
        res = self._get("/api/v1/inboxes")
        return [
            Inbox(self, i["address"], **{k: v for k, v in i.items() if k != "address"})
            for i in (res.get("inboxes") or [])
        ]

    def inbox(self, address: str) -> Inbox:
        """Var olan bir adrese (API çağrısı yapmadan) bağlan."""
        return Inbox(self, address)
