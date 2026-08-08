"""Transport RULES, with no I/O — the one place the sync and async clients must agree.

Why this module exists: the SDK has two clients now (`MailFlat`, `AsyncMailFlat`). If each
carried its own copy of "is this retriable", "how long do I wait", "which exception does a
403 become", the two would drift the first time one of them is touched — and the drift
would be invisible, because both would still pass their own tests.

B-055 is the scar: `waitForOtp` existed on both surfaces but only one of them went through
`guarded()`. A name-by-name comparison said the surfaces matched. Behaviour did not.

So the clients differ ONLY in how they wait (`time.sleep` vs `await asyncio.sleep`) and how
they issue the request. Every decision lives here.

Connected to:
  - imports from: mailflat.errors
  - imported by:  mailflat.client (sync), mailflat.aio (async)

Key exports:
  - `RETRY_STATUSES` / `IDEMPOTENT_METHODS` / `MAX_BACKOFF`
  - `retry_after_seconds(headers)` — `Retry-After` in seconds, or None
  - `should_retry(...)` — the retry decision, POST excluded on purpose
  - `backoff_delay(attempt, retry_after)` — how long to wait before the next attempt
  - `interpret(status_code, data)` — raises the right error, or returns the payload
"""
from __future__ import annotations

from typing import Any, Mapping

from .errors import MailFlatError, raise_for_status

RETRY_STATUSES = {429, 502, 503, 504}

# Only side-effect-free (idempotent) methods are retried. POST is deliberately excluded:
# if the MTA accepts a /send and the gateway then returns 504, a retry delivers THE SAME
# MAIL TWICE and the user never finds out. POST stays single-shot until we support
# Idempotency-Key. (B-058 — the Java SDK still has this bug as B-066.)
IDEMPOTENT_METHODS = {"GET", "HEAD", "DELETE"}

MAX_BACKOFF = 8.0


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Parse the `Retry-After` header (seconds form). Returns None when absent/unparsable.

    Coming back after 1s when the server said "wait 12s" both earns another 429 and
    stretches the rate-limit window.
    """
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        # The HTTP-date form is valid but rare; rather than guess, fall back to our backoff.
        return None


def should_retry(status_code: int, method: str, idempotent: bool | None,
                 attempt: int, max_retries: int) -> bool:
    """Retry this request? `idempotent=True` overrides the method rule.

    mark_read/burn are POSTs but repeating them is harmless (same end state). It is never
    passed for send: a repeated send delivers the same mail twice.
    """
    if status_code not in RETRY_STATUSES or attempt >= max_retries:
        return False
    if idempotent is None:
        return method.upper() in IDEMPOTENT_METHODS
    return bool(idempotent)


def backoff_delay(attempt: int, retry_after: float | None) -> float:
    """Seconds to wait before attempt N. The server's `Retry-After` wins when it sent one."""
    delay = retry_after if retry_after is not None else min(2 ** attempt * 0.5, MAX_BACKOFF)
    return min(delay, MAX_BACKOFF)


def error_detail(data: Any) -> str:
    """Pull the human-readable reason out of an error body."""
    if isinstance(data, dict):
        return data.get("detail") or data.get("error") or ""
    return ""


def interpret(status_code: int, data: Any, *, retry_after: float | None = None) -> dict:
    """Turn a finished response into a payload — or the right exception.

    The `2xx + {"error": ...}` branch is a safety net, not theory: an endpoint that answers
    200 with an error body would otherwise look like success to every caller.
    """
    if status_code >= 400:
        raise_for_status(status_code, error_detail(data), retry_after=retry_after)
    if isinstance(data, dict) and data.get("error"):
        raise MailFlatError(data["error"], status_code=status_code)
    return data if isinstance(data, dict) else {}
