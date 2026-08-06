// @mailflat/sdk — the official JS/TS client for automation-friendly email inboxes.
//
// `npm i @mailflat/sdk` → `import { MailFlat } from "@mailflat/sdk"`.
//
// Connected to:
//   - depends on: client.ts, inbox.ts, errors.ts, types.ts, version.ts
//   - used by:    user code, @mailflat/ai-sdk
//
// Key export: MailFlat (+ Inbox, tipler, hatalar, redactSecrets)

export { MailFlat } from "./client";
export type { MailFlatOptions } from "./client";
export { Inbox } from "./inbox";
export { redactSecrets, SECRET_NAME_PARTS } from "./redact";
export { replySubject } from "./types";
export type {
  Message,
  Attachment,
  SpamReport,
  Direction,
  CreateInboxOptions,
  ReadOptions,
  ReplyOptions,
  WaitOptions,
  SendOptions,
} from "./types";
export {
  MailFlatError,
  AuthenticationError,
  PermissionError,
  NotFoundError,
  RateLimitError,
  APIError,
  OTPTimeoutError,
  EncryptedInboxError,
} from "./errors";

// Single version source: version.ts (client.ts reads it for the User-Agent too).
export { VERSION } from "./version";
