# @mailflat/sdk

Official TypeScript/JavaScript client for [MailFlat](https://mailflat.net): disposable,
automation-friendly email inboxes with **one-line OTP retrieval**. Zero dependencies — uses
the platform `fetch` (Node 18+, modern browsers, edge runtimes).

```bash
npm i @mailflat/sdk
```

## Quickstart

```ts
import { MailFlat } from "@mailflat/sdk";

const mailflat = new MailFlat({ apiKey: process.env.MAILFLAT_API_KEY });

// 1 · spin up a disposable inbox
const inbox = await mailflat.create({ label: "signup-test" });
console.log(inbox.address); // → signup-test-8f3@x7k2m.mailflat.net

// 2 · your app/browser submits the form using inbox.address ...

// 3 · grab the OTP (polls until it arrives or times out)
const otp = await inbox.waitForOtp({ timeout: 30000 });
console.log(otp); // → "123456"

// inbox auto-clears in 2h — no cleanup needed (or call inbox.delete())
```

## For AI agents

```ts
const inbox = await mailflat.create({ label: "deep-research" });
await browser.fill("#email", inbox.address);
await browser.click("Sign up");

const otp = await inbox.waitForOtp({ timeout: 30000 });
await browser.fill("#code", otp);
```

## API

### `new MailFlat(options)`
`{ apiKey?, baseUrl?, timeout?, maxRetries? }`. `apiKey` falls back to `process.env.MAILFLAT_API_KEY`.
Use `baseUrl` for self-hosted / BYOD deployments (default `https://mailflat.net`).

- `create(opts) => Promise<Inbox>` — open a new inbox. `createInbox(opts)` is an alias.
  `opts`: `{ prefix?, label?, subdomain?, domain?, retentionHours? }`.
- `list() => Promise<Inbox[]>` — inboxes opened with this key.
- `inbox(address) => Inbox` — attach to an existing address without a network call.

### `Inbox`
- `.address` — the email address.
- `.messages() => Promise<Message[]>` — all messages, newest first.
- `.latest() => Promise<Message | null>` — most recent message.
- `.waitForOtp({ timeout?, pollInterval? }) => Promise<string>` — poll until an OTP arrives; returns the code. `timeout` is in **ms** (default 30000).
- `.waitForMessage({ timeout?, pollInterval? }) => Promise<Message>` — poll until any message arrives.
- `.send(to, { subject?, body?, html? }) => Promise<...>` — send a DKIM-signed email from this inbox.
- `.delete() => Promise<...>` — delete the inbox and all its messages.

### `Message`
`.otp`, `.subject`, `.sender`, `.text`, `.html`, `.toAddress`, `.direction`, `.receivedAt`, `.raw`.

## Errors

All errors extend `MailFlatError`: `AuthenticationError` (401), `PermissionError` (403),
`NotFoundError` (404), `RateLimitError` (429), `APIError` (other), `OTPTimeoutError`
(no OTP before timeout), `EncryptedInboxError` (the inbox is end-to-end encrypted, so the
server cannot read its contents — use a non-encrypted inbox for agent automation).

## License

MIT
