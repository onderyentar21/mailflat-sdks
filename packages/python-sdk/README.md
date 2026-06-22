# MailFlat — Python SDK

Official Python client for [MailFlat](https://mailflat.net): disposable, automation-friendly
email inboxes with **one-line OTP retrieval**. Spin up a real inbox, read the verification
code your app just sent, and move on — no flaky polling, no shared mailbox state.

```bash
pip install mailflat
```

## Quickstart

```python
from mailflat import MailFlat

mf = MailFlat(api_key="mf_live_...")  # or set MAILFLAT_API_KEY

# 1 · spin up a disposable inbox
inbox = mf.create(label="signup-test")
print(inbox.address)            # → signup-test-8f3@x7k2m.mailflat.net

# 2 · your app/browser submits the form using inbox.address ...

# 3 · grab the OTP (polls until it arrives or times out)
otp = inbox.wait_for_otp(timeout=30)
print(otp)                      # → "123456"

# inbox auto-clears in 2h — no cleanup needed (or call inbox.delete())
```

## For AI agents

Hand an agent one API key and it spins up real inboxes on demand:

```python
mf = MailFlat()  # reads MAILFLAT_API_KEY

inbox = mf.create(label="deep-research")
browser.fill("#email", inbox.address)
browser.click("Sign up")

otp = inbox.wait_for_otp(timeout=30)
browser.fill("#code", otp)
```

## API

### `MailFlat(api_key=None, *, base_url="https://mailflat.net", timeout=30.0, max_retries=2)`
Client. `api_key` falls back to the `MAILFLAT_API_KEY` environment variable. Use `base_url`
for self-hosted / BYOD deployments. Supports use as a context manager (`with MailFlat() as mf:`).

- `create(*, prefix=None, label=None, subdomain=None, domain=None, retention_hours=None) -> Inbox`
  — open a new inbox. `create_inbox(...)` is an alias.
- `list() -> list[Inbox]` — inboxes opened with this key.
- `inbox(address) -> Inbox` — attach to an existing address without a network call.

### `Inbox`
- `.address` — the email address.
- `.messages() -> list[Message]` — all messages, newest first.
- `.latest() -> Message | None` — most recent message.
- `.wait_for_otp(*, timeout=30, poll_interval=1.0) -> str` — poll until an OTP arrives; returns the code.
- `.wait_for_message(*, timeout=30, poll_interval=1.0) -> Message` — poll until any message arrives.
- `.send(to, *, subject="", body="", html=None) -> dict` — send a DKIM-signed email from this inbox.
- `.delete() -> dict` — delete the inbox and all its messages.

### `Message`
`.otp`, `.subject`, `.sender`, `.text`, `.html`, `.to_address`, `.direction`, `.received_at`, `.raw`.

## Errors

All errors subclass `MailFlatError`: `AuthenticationError` (401), `PermissionError` (403),
`NotFoundError` (404), `RateLimitError` (429), `APIError` (other), `OTPTimeoutError`
(no OTP before timeout), `EncryptedInboxError` (the inbox is end-to-end encrypted, so the
server cannot read its contents — use a non-encrypted inbox for agent automation).

## License

MIT
