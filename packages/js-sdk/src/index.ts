// @mailflat/sdk — disposable, otomasyon-dostu e-posta inbox'ları için resmi JS/TS client.
//
// `npm i @mailflat/sdk` → `import { MailFlat } from "@mailflat/sdk"`.
//
// Connected to:
//   - depends on: client.ts, inbox.ts, errors.ts, types.ts
//   - used by:    kullanıcı kodu, @mailflat/ai-sdk
//
// Key export: MailFlat (+ Inbox, tipler, hatalar)

export { MailFlat } from "./client";
export type { MailFlatOptions } from "./client";
export { Inbox } from "./inbox";
export type { Message, CreateInboxOptions, WaitOptions, SendOptions } from "./types";
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

export const VERSION = "0.1.0";
