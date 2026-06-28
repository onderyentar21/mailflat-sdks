// Inbox — tek bir MailFlat inbox'ı üzerindeki yüksek seviye işlemler.
//
// MailFlat client tarafından döndürülür; mesaj okuma, OTP bekleme, gönderme, silme.
//
// Connected to:
//   - used by:    client.ts (oluşturur), kullanıcı kodu
//   - depends on: types.ts, errors.ts, client.ts (tip)
//
// Key export: Inbox

import { EncryptedInboxError, OTPTimeoutError } from "./errors";
import type { MailFlat } from "./client";
import { type Message, type SendOptions, type WaitOptions, toMessage } from "./types";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

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

  // API mail dict'ini Message'a çevirir + msg.delete() şekerini iliştirir.
  private _wrap(d: Record<string, any>): Message {
    const m = toMessage(d);
    m.delete = () => this.deleteMessage(m.id as number);
    return m;
  }

  // Inbox'taki tüm mesajları (yeniden eskiye) döndürür.
  async messages(): Promise<Message[]> {
    const res = await this.client._get(`/api/v1/inboxes/${this.address}/messages`);
    return ((res.emails as any[]) || []).map((e) => this._wrap(e));
  }

  // En son mesajı döndürür (yoksa null).
  async latest(): Promise<Message | null> {
    const res = await this.client._get(`/api/v1/inboxes/${this.address}/latest`);
    return res.email ? this._wrap(res.email) : null;
  }

  // Yeni bir mesaj gelene kadar poll'lar; gelince Message döndürür.
  async waitForMessage(opts: WaitOptions = {}): Promise<Message> {
    const timeout = opts.timeout ?? 30000;
    const pollInterval = opts.pollInterval ?? 1000;
    const deadline = Date.now() + Math.max(0, timeout);
    for (;;) {
      const res = await this.client._get(`/api/v1/inboxes/${this.address}/latest`);
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

  // OTP kodu gelene kadar poll'lar ve kodu (string) döndürür.
  async waitForOtp(opts: WaitOptions = {}): Promise<string> {
    const timeout = opts.timeout ?? 30000;
    const pollInterval = opts.pollInterval ?? 1000;
    const deadline = Date.now() + Math.max(0, timeout);
    for (;;) {
      const res = await this.client._get(`/api/v1/inboxes/${this.address}/latest`);
      if (res.encrypted) {
        throw new EncryptedInboxError(
          res.note || "This inbox is end-to-end encrypted; OTP cannot be read via the API.",
        );
      }
      const otp = res.email?.otp_code;
      if (otp) return otp as string;
      if (Date.now() >= deadline) {
        throw new OTPTimeoutError(`No OTP arrived for ${this.address} within ${timeout}ms`);
      }
      await sleep(pollInterval);
    }
  }

  // Bu inbox adresinden mail gönderir (DKIM imzalı, kendi MTA'mız üzerinden).
  async send(to: string, opts: SendOptions = {}): Promise<Record<string, any>> {
    const payload: Record<string, any> = {
      to,
      subject: opts.subject ?? "",
      body: opts.body ?? "",
    };
    if (opts.html != null) payload.html = opts.html;
    return this.client._post(`/api/v1/inboxes/${this.address}/send`, payload);
  }

  // Inbox'u ve tüm mesajlarını siler. Geri alınamaz.
  async delete(): Promise<Record<string, any>> {
    return this.client._delete(`/api/v1/inboxes/${this.address}`);
  }

  // Inbox'taki TEK bir maili siler (inbox kalır). message.delete() bunu çağırır.
  async deleteMessage(messageId: number): Promise<Record<string, any>> {
    return this.client._delete(`/api/v1/inboxes/${this.address}/messages/${messageId}`);
  }
}
