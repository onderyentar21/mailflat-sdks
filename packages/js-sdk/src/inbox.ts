// Inbox — high-level operations on a single MailFlat inbox.
//
// Returned by the MailFlat client: read messages, wait for OTP, send, mark read, burn, delete.
//
// Connected to:
//   - used by:    client.ts (creates it), user code
//   - depends on: types.ts, errors.ts, client.ts (type only)
//
// Key export: Inbox

import { EncryptedInboxError, MailFlatError, OTPTimeoutError } from "./errors";
import type { MailFlat } from "./client";
import {
  DIRECTIONS,
  type Direction,
  type Message,
  type ReadOptions,
  type ReplyOptions,
  type SendOptions,
  type WaitOptions,
  replySubject,
  toMessage,
} from "./types";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function checkDirection(direction: Direction): Direction {
  if (!DIRECTIONS.includes(direction)) {
    throw new MailFlatError(
      `direction must be one of ${DIRECTIONS.join(", ")} — got "${direction}"`,
    );
  }
  return direction;
}

export class Inbox {
  readonly address: string;
  readonly name?: string;
  readonly apiKey?: string; // per-inbox key (mf_sk_...)
  readonly retentionHours?: number;
  readonly encrypted: boolean;
  readonly raw: Record<string, any>;

  constructor(
    private client: MailFlat,
    address: string,
    meta: Record<string, any> = {},
  ) {
    this.address = address;
    this.name = meta.name;
    this.apiKey = meta.api_key;
    this.retentionHours = meta.retention_hours;
    this.encrypted = Boolean(meta.encrypted);
    this.raw = { address, ...meta };
  }

  // Wraps an API payload into a Message and attaches the delete/markRead/download helpers.
  // (header() is attached here too — see types.ts for why indexing headers is unsafe.)
  private _wrap(d: Record<string, any>): Message {
    const m = toMessage(d);
    m.delete = () => this.deleteMessage(m.id as number);
    m.markRead = () => this.markRead(m.id as number);
    m.reply = (body = "", opts: ReplyOptions = {}) => {
      // Reply-To / From, not the envelope sender: MAIL FROM is a bounce address on most
      // transactional mail, so replying there never reaches a person.
      const target = m.replyToAddress;
      if (!target) throw new MailFlatError("This message has no sender to reply to.");
      return this.send(target, {
        subject: opts.subject ?? replySubject(m.subject),
        body,
        html: opts.html,
        inReplyTo: m.messageId,
      });
    };
    for (const att of m.attachments) {
      att.download = () => {
        if (att.truncated) {
          throw new MailFlatError(`Attachment "${att.filename}" was too large to store`);
        }
        return this.downloadAttachment(m.id as number, att.id as number);
      };
    }
    return m;
  }

  /**
   * Return this inbox's messages, newest first.
   * Defaults to received mail; pass `{ direction: "out" }` or `"all"` for the rest.
   */
  async messages(opts: ReadOptions = {}): Promise<Message[]> {
    const direction = checkDirection(opts.direction ?? "in");
    const res = await this.client._get(
      `/api/v1/inboxes/${this.address}/messages?direction=${direction}`,
    );
    return ((res.emails as any[]) || []).map((e) => this._wrap(e));
  }

  /**
   * Return the most recent message, or null when there is none.
   * Before 0.3.0 this also returned mail you had just sent, which made `send()` followed
   * by `waitForMessage()` match your own outgoing message.
   */
  async latest(opts: ReadOptions = {}): Promise<Message | null> {
    const direction = checkDirection(opts.direction ?? "in");
    const res = await this.client._get(
      `/api/v1/inboxes/${this.address}/latest?direction=${direction}`,
    );
    return res.email ? this._wrap(res.email) : null;
  }

  /**
   * Poll until a message arrives and return it. Only received mail counts by default,
   * so an agent can send to a peer and wait for the reply without matching its own message.
   */
  async waitForMessage(opts: WaitOptions = {}): Promise<Message> {
    const timeout = opts.timeout ?? 30000;
    const pollInterval = opts.pollInterval ?? 1000;
    const direction = checkDirection(opts.direction ?? "in");
    const deadline = Date.now() + Math.max(0, timeout);
    for (;;) {
      const res = await this.client._get(
        `/api/v1/inboxes/${this.address}/latest?direction=${direction}`,
      );
      if (res.encrypted) {
        throw new EncryptedInboxError(
          res.note ||
            "This inbox is end-to-end encrypted; use a non-encrypted inbox for agent automation.",
        );
      }
      if (res.email) return this._wrap(res.email);
      if (Date.now() >= deadline) {
        throw new OTPTimeoutError(`No message arrived for ${this.address} within ${timeout}ms`);
      }
      await sleep(pollInterval);
    }
  }

  /**
   * Poll until a one-time code arrives and return it.
   *
   * If mail did arrive but no code could be extracted from it, the timeout error says so and
   * quotes the newest message, so you can read `inbox.latest()` yourself instead of hunting
   * for a delivery problem that does not exist.
   */
  async waitForOtp(opts: WaitOptions = {}): Promise<string> {
    const timeout = opts.timeout ?? 30000;
    const pollInterval = opts.pollInterval ?? 1000;
    const deadline = Date.now() + Math.max(0, timeout);
    let seen: Record<string, any> | null = null; // newest incoming mail, code or not
    for (;;) {
      const res = await this.client._get(`/api/v1/inboxes/${this.address}/latest?direction=in`);
      if (res.encrypted) {
        throw new EncryptedInboxError(
          res.note || "This inbox is end-to-end encrypted; OTP cannot be read via the API.",
        );
      }
      const otp = res.email?.otp_code;
      if (otp) return otp as string;
      if (res.email) seen = res.email;
      if (Date.now() >= deadline) {
        throw new OTPTimeoutError(this._otpTimeoutMessage(timeout, seen));
      }
      await sleep(pollInterval);
    }
  }

  /**
   * Distinguishes "nothing arrived" from "no code in what arrived". These are completely
   * different problems and used to produce the same sentence.
   */
  private _otpTimeoutMessage(timeout: number, seen: Record<string, any> | null): string {
    if (!seen) return `No message arrived for ${this.address} within ${timeout}ms`;
    const subject = (seen.subject || "(no subject)").trim();
    const snippet = String(seen.body_text || "").split(/\s+/).join(" ").slice(0, 120);
    return (
      `Mail arrived for ${this.address} but no OTP could be extracted from it within ` +
      `${timeout}ms. Newest message: ${JSON.stringify(subject)}` +
      (snippet ? ` — ${JSON.stringify(snippet)}` : "") +
      ". Read inbox.latest() and parse the code yourself, and please report the format so we " +
      "can support it."
    );
  }

  /**
   * Download one attachment's bytes. Metadata already ships with each message
   * (`msg.attachments`); prefer `msg.attachments[0].download()`.
   */
  async downloadAttachment(messageId: number, attachmentId: number): Promise<Uint8Array> {
    return this.client._getBytes(
      `/api/v1/inboxes/${this.address}/messages/${messageId}/attachments/${attachmentId}`,
    );
  }

  /**
   * Send mail from this inbox's address (DKIM-signed, through MailFlat's own MTA).
   *
   * Pass `inReplyTo` (a Message-ID) to keep the mail in an existing conversation; without it
   * the recipient's client starts a new thread. `message.reply()` fills this in for you.
   *
   * Not retried on gateway errors: a retried send can deliver the same mail twice.
   */
  async send(to: string, opts: SendOptions = {}): Promise<Record<string, any>> {
    const payload: Record<string, any> = {
      to,
      subject: opts.subject ?? "",
      body: opts.body ?? "",
    };
    if (opts.html != null) payload.html = opts.html;
    if (opts.inReplyTo != null) payload.in_reply_to = opts.inReplyTo;
    return this.client._post(`/api/v1/inboxes/${this.address}/send`, payload);
  }

  /** Mark one message as read, so the next poll can skip it. */
  async markRead(messageId: number): Promise<Record<string, any>> {
    return this.client._post(`/api/v1/inboxes/${this.address}/messages/${messageId}/read`, {}, true);
  }

  /** Delete every message in this inbox and keep the address. */
  async burn(): Promise<Record<string, any>> {
    return this.client._post(`/api/v1/inboxes/${this.address}/burn`, {}, true);
  }

  /** Delete this inbox and all of its messages. Cannot be undone. */
  async delete(): Promise<Record<string, any>> {
    return this.client._delete(`/api/v1/inboxes/${this.address}`);
  }

  /** Delete a single message; the inbox stays. Backs `message.delete()`. */
  async deleteMessage(messageId: number): Promise<Record<string, any>> {
    return this.client._delete(`/api/v1/inboxes/${this.address}/messages/${messageId}`);
  }
}
