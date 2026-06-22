// MailFlat SDK tipleri — Message + opsiyon arayüzleri.
//
// Connected to:
//   - used by:    client.ts, inbox.ts, index.ts
//
// Key export: Message, CreateInboxOptions, WaitOptions, SendOptions

export interface Message {
  id?: number;
  sender?: string;
  subject?: string;
  text?: string; // body_text
  html?: string; // body_html
  otp?: string; // otp_code (sunucu çıkardıysa)
  tag?: string;
  toAddress?: string; // to_address
  isEncrypted?: boolean;
  direction?: string; // "in" | "out"
  isRead?: boolean;
  sendStatus?: string;
  sendError?: string;
  receivedAt?: string;
  raw: Record<string, any>; // backend serialize çıktısının tamamı
}

export interface CreateInboxOptions {
  prefix?: string;
  label?: string;
  subdomain?: string; // mailflat.net alt alanı (boşsa rastgele)
  domain?: string; // BYOD doğrulanmış kendi domain'in
  retentionHours?: number;
}

export interface WaitOptions {
  timeout?: number; // ms (varsayılan 30000)
  pollInterval?: number; // ms (varsayılan 1000)
}

export interface SendOptions {
  subject?: string;
  body?: string;
  html?: string;
}

// /api/v1 e-posta serialize çıktısını (snake_case) Message'a (camelCase) çevirir.
export function toMessage(d: Record<string, any>): Message {
  return {
    id: d.id,
    sender: d.sender,
    subject: d.subject,
    text: d.body_text,
    html: d.body_html,
    otp: d.otp_code,
    tag: d.tag,
    toAddress: d.to_address,
    isEncrypted: Boolean(d.is_encrypted),
    direction: d.direction,
    isRead: Boolean(d.is_read),
    sendStatus: d.send_status,
    sendError: d.send_error,
    receivedAt: d.received_at,
    raw: d,
  };
}
