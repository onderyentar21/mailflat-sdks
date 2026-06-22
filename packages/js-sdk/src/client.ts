// MailFlat client — /api/v1 otomasyon API'sinin ince, tiplenmiş JS/TS sarmalayıcısı.
//
// Tek hesap API key'i (X-API-Key) ile inbox açar, listeler, mail/OTP okur, mail gönderir.
// Global fetch kullanır (Node 18+ / modern tarayıcılar) — sıfır bağımlılık.
//
// Connected to:
//   - used by:    index.ts, kullanıcı kodu, @mailflat/ai-sdk
//   - depends on: inbox.ts, errors.ts, types.ts
//
// Key export: MailFlat

import { MailFlatError, raiseForStatus } from "./errors";
import { Inbox } from "./inbox";
import type { CreateInboxOptions } from "./types";

const DEFAULT_BASE_URL = "https://mailflat.net";
const RETRY_STATUSES = new Set([429, 502, 503, 504]);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export interface MailFlatOptions {
  apiKey?: string;
  baseUrl?: string;
  timeout?: number; // ms (her istek için)
  maxRetries?: number;
  fetch?: typeof fetch; // testler için enjekte edilebilir
}

export class MailFlat {
  readonly apiKey: string;
  readonly baseUrl: string;
  private timeout: number;
  private maxRetries: number;
  private _fetch: typeof fetch;

  constructor(opts: MailFlatOptions = {}) {
    const apiKey =
      opts.apiKey ??
      (typeof process !== "undefined" ? process.env?.MAILFLAT_API_KEY : undefined);
    if (!apiKey) {
      throw new MailFlatError(
        "An API key is required. Pass new MailFlat({ apiKey }) or set MAILFLAT_API_KEY.",
      );
    }
    this.apiKey = apiKey;
    this.baseUrl = (opts.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeout = opts.timeout ?? 30000;
    this.maxRetries = Math.max(0, opts.maxRetries ?? 2);
    const f = opts.fetch ?? (typeof fetch !== "undefined" ? fetch : undefined);
    if (!f) {
      throw new MailFlatError(
        "No fetch implementation found. Use Node 18+ or pass { fetch } in options.",
      );
    }
    this._fetch = f;
  }

  // -------------------------------------------------------------- HTTP iç
  async _request(method: string, path: string, body?: Record<string, any>): Promise<any> {
    let attempt = 0;
    for (;;) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeout);
      let resp: Response;
      try {
        resp = await this._fetch(`${this.baseUrl}${path}`, {
          method,
          headers: {
            "X-API-Key": this.apiKey,
            ...(body ? { "Content-Type": "application/json" } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });
      } catch (err: any) {
        clearTimeout(timer);
        throw new MailFlatError(`Network error: ${err?.message ?? err}`);
      }
      clearTimeout(timer);

      if (RETRY_STATUSES.has(resp.status) && attempt < this.maxRetries) {
        attempt += 1;
        await sleep(Math.min(2 ** attempt * 500, 4000)); // 1s, 2s, ... backoff
        continue;
      }

      let data: any = {};
      try {
        data = await resp.json();
      } catch {
        data = {};
      }

      if (resp.status >= 400) {
        const detail =
          (data && (data.detail || data.error)) || `Request failed with status ${resp.status}`;
        raiseForStatus(resp.status, detail);
      }
      if (data && typeof data === "object" && data.error) {
        throw new MailFlatError(data.error, resp.status);
      }
      return data ?? {};
    }
  }

  _get(path: string) {
    return this._request("GET", path);
  }
  _post(path: string, body: Record<string, any>) {
    return this._request("POST", path, body);
  }
  _delete(path: string) {
    return this._request("DELETE", path);
  }

  // -------------------------------------------------------------- public
  // Yeni bir disposable inbox açar ve Inbox döndürür.
  async create(opts: CreateInboxOptions = {}): Promise<Inbox> {
    const payload: Record<string, any> = {};
    if (opts.prefix != null) payload.prefix = opts.prefix;
    if (opts.label != null) payload.label = opts.label;
    if (opts.subdomain != null) payload.subdomain = opts.subdomain;
    if (opts.domain != null) payload.domain = opts.domain;
    if (opts.retentionHours != null) payload.retention_hours = opts.retentionHours;
    const res = await this._post("/api/v1/inboxes", payload);
    const { address, ...meta } = res;
    return new Inbox(this, address, meta);
  }

  // Landing snippet'leriyle uyum için alias.
  createInbox(opts: CreateInboxOptions = {}): Promise<Inbox> {
    return this.create(opts);
  }

  // Bu API key ile açılmış (agent) inbox'ları döndürür.
  async list(): Promise<Inbox[]> {
    const res = await this._get("/api/v1/inboxes");
    return ((res.inboxes as any[]) || []).map((i) => {
      const { address, ...meta } = i;
      return new Inbox(this, address, meta);
    });
  }

  // Var olan bir adrese (API çağrısı yapmadan) bağlan.
  inbox(address: string): Inbox {
    return new Inbox(this, address);
  }
}
