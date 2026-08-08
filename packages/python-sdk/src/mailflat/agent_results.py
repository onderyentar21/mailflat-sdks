"""The shape a MODEL sees when it asks "did my mail actually go out?".

`send()` is asynchronous (the endpoint answers 202 Accepted), so every model surface needs
a way to ask about delivery afterwards. Code surfaces raise exceptions for that; a model
surface hands the model a dictionary and the model decides what to do next. Those
dictionaries are built HERE, once, so the MCP server and both LangChain toolkits cannot
drift apart — the same reason `should_retry`/`backoff_delay` live in `_http.py`.

⚠️ The dangerous branch is the TIMEOUT, not the failure. A timeout means "still queued,
the queue is still retrying" — it does NOT mean the mail was lost. A model that reads a
timeout as failure will send the mail a second time, so the payload says `delivered: false`
without ever saying "failed", and states outright that resending is wrong.

Connected to:
  - imports from: mailflat.redact
  - imported by:  mailflat.langchain (both toolkits), mailflat_mcp.server

Key exports:
  - `SEND_RESULT_KEYS` — the keys every surface must return (cross-surface parity lock)
  - `SEND_QUEUED_NOTE` / `SEND_FAILED_NOTE` — the sentences the model reads
  - `sent_result()`, `queued_result()`, `failed_result()` — the three outcomes
"""
from __future__ import annotations

from typing import Any

from .redact import redact_secrets

#: Every `wait_until_sent` result carries exactly these keys, on every surface. A model
#: that learned to read one surface can read the others; a test compares this tuple with
#: what the TypeScript surface returns.
SEND_RESULT_KEYS = ("status", "delivered", "timed_out", "message", "note")

#: Shown when the mail is still queued. The last sentence is the point of the whole module.
#:
#: Written WITHOUT the word "fail" on purpose, and locked that way by test. The first draft
#: opened with "This is NOT a failure" — accurate, but it puts the very word we are trying
#: to keep out of the model's head into the payload, and negations are the first thing a
#: model skims past. Saying what is true ("still on its way") beats denying what is false.
SEND_QUEUED_NOTE = (
    "Still queued when the timeout elapsed. The queue keeps retrying with backoff, so this "
    "mail is still on its way. Do NOT send it again — a duplicate would reach the recipient "
    "twice. Ask again later, or subscribe to the message.delivered webhook."
)

#: Shown when the queue gave up. Here resending after fixing the cause IS the right move.
SEND_FAILED_NOTE = (
    "Delivery permanently failed and the queue will not retry. Read `error` for the "
    "reason (a rejection from the recipient's mail server, an unknown mailbox, and so on). "
    "Fix the cause before sending again."
)


def sent_result(message: Any) -> dict[str, Any]:
    """The mail reached a final, successful state.

    `unsigned` counts as delivered: it means the mail went out without a DKIM signature,
    not that it stayed behind. Reporting it as undelivered would make an agent resend a
    mail the recipient already has.
    """
    return redact_secrets({
        "status": message.send_status,
        "delivered": True,
        "timed_out": False,
        "message": message.raw,
        "note": "",
    })


def queued_result(error: Any) -> dict[str, Any]:
    """We stopped waiting; the queue did not. Built from a `SendTimeoutError`."""
    return {
        "status": error.status or "queued",
        "delivered": False,
        "timed_out": True,
        "message": None,
        "note": SEND_QUEUED_NOTE,
    }


def failed_result(error: Any) -> dict[str, Any]:
    """Delivery is over and it did not work. Built from a `SendFailedError`.

    Carries an extra `error` key on top of `SEND_RESULT_KEYS`: the reason is the only
    thing that lets the caller decide whether a corrected resend makes sense.
    """
    return {
        "status": error.status or "failed",
        "delivered": False,
        "timed_out": False,
        "message": None,
        "note": SEND_FAILED_NOTE,
        "error": str(error),
    }
