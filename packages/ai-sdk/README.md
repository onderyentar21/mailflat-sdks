# @mailflat/ai-sdk

[MailFlat](https://mailflat.net) tool suite for the [Vercel AI SDK](https://sdk.vercel.ai).
Give any model real, working disposable inboxes — it can create addresses, read mail, and
pull one-time verification codes on its own.

```bash
npm i @mailflat/ai-sdk
```

`ai` (the Vercel AI SDK) is a peer dependency — install it in your app if you haven't already.

## Quickstart

```ts
import { mailflatToolSuite } from "@mailflat/ai-sdk";
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";

const result = await generateText({
  model: openai("gpt-4o"),
  tools: {
    ...mailflatToolSuite({ apiKey: process.env.MAILFLAT_KEY }),
  },
  maxSteps: 10,
  prompt: "Register on staging.io, get the OTP code from the email, and submit it.",
});
```

`mailflatToolSuite()` returns a dictionary of tools you spread into `tools`. It works with
both the v3/v4 (`parameters`) and v5 (`inputSchema`) tool shapes — no version pin needed.

## Tools

| Tool | What it does |
|---|---|
| `createInbox` | Create a disposable inbox → returns its address. `{ prefix?, label?, retentionHours? }` |
| `listInboxes` | List inboxes available to this API key. |
| `readMessages` | Read every message in an inbox (newest first). `{ address }` |
| `waitForOtp` | Poll until an OTP arrives, then return it. `{ address, timeout? }` (ms) |
| `sendEmail` | Send a DKIM-signed email from an inbox. `{ address, to, subject?, body?, html? }` |
| `deleteInbox` | Delete an inbox and all its messages. `{ address }` |

Tool errors are returned to the model as `{ error: "..." }` (rather than thrown) so the agent
can recover; `waitForOtp` also returns `{ otp: null, error: "timeout" }` or
`{ otp: null, encrypted: true }` when relevant.

## Options

`mailflatToolSuite({ apiKey?, baseUrl?, client? })`

- `apiKey` — MailFlat account key (`mf_live_...`). Falls back to `MAILFLAT_API_KEY`.
- `baseUrl` — API root, default `https://mailflat.net` (override for self-hosted / BYOD).
- `client` — inject a ready [`@mailflat/sdk`](https://www.npmjs.com/package/@mailflat/sdk)
  `MailFlat` instance to share configuration.

## License

MIT
