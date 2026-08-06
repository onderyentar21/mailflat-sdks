"""Strips secret fields from agent tool output (B-055).

Why it exists: `create_inbox` and `list_inboxes` used to return the backend payload as-is,
and that payload carried a per-inbox `api_key` (`mf_sk_...`). Tool output goes into the
MODEL's context, and from there into prompt logs, tracing tools (LangSmith, AI SDK
telemetry), error reports and the model's own later answers. `list_inboxes` leaked every
inbox key on the account in a single call.

The split is deliberate:
  - **SDK = code surface.** `Inbox.api_key` stays; code a human wrote may use it.
  - **Tool = model surface.** Everything passing through here is redacted.

Redaction is **name-based, not value-based**: scanning message bodies for strings starting
with `mf_` would corrupt a legitimate email that happens to discuss a test key. Matching on
the field name is both exact and harmless.

Connected to:
  - imports from: —
  - imported by:  mailflat.langchain and this package's tests. Within the repo,
    `packages/mcp` (mailflat-mcp, a separate PyPI package) also imports it — that package
    is not bundled here, so the reference is repo-level.

Key exports:
  - `redact_secrets(value)` — copy of the input with secret fields removed
  - `SECRET_NAME_PARTS` — which field names count as secrets
"""
from __future__ import annotations

from typing import Any

#: A field is dropped when its normalised name CONTAINS one of these.
#: Kept deliberately narrow: `token` is absent on purpose — fields like a domain
#: `verify_token` are harmless and sometimes useful, and `otp` is the very thing the agent
#: is after. None of the three below is ever useful to a model.
SECRET_NAME_PARTS = ("apikey", "secret", "password")


def _normalise(key: Any) -> str:
    return str(key).replace("_", "").replace("-", "").lower()


def _is_secret(key: Any) -> bool:
    name = _normalise(key)
    return any(part in name for part in SECRET_NAME_PARTS)


def redact_secrets(value: Any) -> Any:
    """Return a copy of `value` with secret fields removed. The input is not modified.

    dict → secret keys dropped, remaining values cleaned recursively
    list/tuple → every element cleaned (returned as a list; JSON carries a list anyway)
    anything else → returned unchanged
    """
    if isinstance(value, dict):
        return {k: redact_secrets(v) for k, v in value.items() if not _is_secret(k)}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(v) for v in value]
    return value
