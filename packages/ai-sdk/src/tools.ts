// MailFlat tool suite — Vercel AI SDK için 6 araçlık set (createInbox, listInboxes,
// readMessages, waitForOtp, sendEmail, deleteInbox).
//
// @mailflat/sdk client'ının üstüne ince bir katman; tüm HTTP/iş mantığı orada (DRY).
// Üretilen araç nesneleri hem AI SDK v3/v4 (`parameters`) hem v5 (`inputSchema`) ile uyumlu
// olacak şekilde her iki anahtarı da taşır → `ai` paketine doğrudan import bağımlılığı yok
// (yalnızca kullanıcının generateText çağrısında peer dependency olarak gerekir).
//
// Connected to:
//   - depends on: @mailflat/sdk (MailFlat client), zod (şema)
//   - used by:    index.ts, kullanıcı kodu (generateText({ tools: { ...mailflatToolSuite(...) } }))
//
// Key export: mailflatToolSuite(options) → araç nesneleri sözlüğü

import { EncryptedInboxError, MailFlat, MailFlatError, OTPTimeoutError } from "@mailflat/sdk";
import { z } from "zod";

export interface ToolSuiteOptions {
  /** MailFlat hesap API key'i (mf_live_...). Verilmezse MAILFLAT_API_KEY env okunur. */
  apiKey?: string;
  /** API kökü (varsayılan https://mailflat.net). Self-host/test için override. */
  baseUrl?: string;
  /** Hazır bir MailFlat client enjekte et (testler / paylaşımlı client için). */
  client?: MailFlat;
}

// Vercel AI SDK aracının yapısı. `parameters` (v3/v4) ve `inputSchema` (v5) aynı şemayı
// işaret eder; generateText hangi sürümdeyse kendi anahtarını okur, diğerini yok sayar.
export interface MailFlatTool {
  description: string;
  parameters: z.ZodTypeAny;
  inputSchema: z.ZodTypeAny;
  execute: (args: any) => Promise<any>;
}

function defineTool(
  description: string,
  schema: z.ZodTypeAny,
  execute: (args: any) => Promise<any>,
): MailFlatTool {
  return { description, parameters: schema, inputSchema: schema, execute };
}

// MailFlatError'ı modelin işleyebileceği düz bir sonuca çevirir (atmak yerine).
async function guarded<T>(fn: () => Promise<T>): Promise<T | { error: string }> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof MailFlatError) return { error: err.message };
    throw err;
  }
}

/**
 * MailFlat araçlarını Vercel AI SDK'nın `generateText`/`streamText` `tools` alanına yaymak
 * için hazır nesneler döndürür.
 *
 * @example
 * const result = await generateText({
 *   model: openai("gpt-4o"),
 *   tools: { ...mailflatToolSuite({ apiKey: process.env.MAILFLAT_KEY }) },
 *   prompt: "Register on staging.io, get the OTP code and submit it.",
 * });
 */
export function mailflatToolSuite(options: ToolSuiteOptions = {}): Record<string, MailFlatTool> {
  const client =
    options.client ?? new MailFlat({ apiKey: options.apiKey, baseUrl: options.baseUrl });

  return {
    createInbox: defineTool(
      "Create a real, working disposable email inbox and return its address. Use this when you need an email to sign up for a service or receive a verification code. Messages auto-purge after the plan's retention window.",
      z.object({
        prefix: z
          .string()
          .optional()
          .describe("Optional left-hand prefix for the address (e.g. 'signup'). Random if omitted."),
        label: z
          .string()
          .optional()
          .describe("Optional human label to remember what this inbox is for."),
        retentionHours: z
          .number()
          .int()
          .positive()
          .optional()
          .describe("Optional retention in hours; capped at your plan's maximum if higher."),
      }),
      ({ prefix, label, retentionHours }) =>
        guarded(async () => {
          const inbox = await client.create({ prefix, label, retentionHours });
          return inbox.raw;
        }),
    ),

    listInboxes: defineTool(
      "List all inboxes currently available to this API key.",
      z.object({}),
      () =>
        guarded(async () => {
          const inboxes = await client.list();
          return { inboxes: inboxes.map((i) => i.raw) };
        }),
    ),

    readMessages: defineTool(
      "Read every message in the given inbox address (newest first).",
      z.object({
        address: z.string().describe("The full inbox address to read, e.g. signup-8f3@mailflat.net."),
      }),
      ({ address }) =>
        guarded(async () => {
          const messages = await client.inbox(address).messages();
          return { emails: messages.map((m) => m.raw) };
        }),
    ),

    waitForOtp: defineTool(
      "Poll an inbox until a one-time verification code (OTP) arrives, then return it. Use right after submitting a sign-up form.",
      z.object({
        address: z.string().describe("The inbox address to poll for the OTP."),
        timeout: z
          .number()
          .int()
          .positive()
          .optional()
          .describe("Maximum milliseconds to wait before giving up (default 30000)."),
      }),
      async ({ address, timeout }) => {
        try {
          const otp = await client.inbox(address).waitForOtp({ timeout });
          return { otp };
        } catch (err) {
          if (err instanceof OTPTimeoutError) return { otp: null, error: "timeout" };
          if (err instanceof EncryptedInboxError)
            return { otp: null, encrypted: true, error: err.message };
          if (err instanceof MailFlatError) return { otp: null, error: err.message };
          throw err;
        }
      },
    ),

    sendEmail: defineTool(
      "Send an email FROM the given inbox address (DKIM-signed via MailFlat's mail servers). Use for replies or outbound automation.",
      z.object({
        address: z.string().describe("The inbox address to send from (must belong to this API key)."),
        to: z.string().describe("Recipient email address."),
        subject: z.string().optional().describe("Email subject line."),
        body: z.string().optional().describe("Plain-text body."),
        html: z.string().optional().describe("Optional HTML body."),
      }),
      ({ address, to, subject, body, html }) =>
        guarded(() => client.inbox(address).send(to, { subject, body, html })),
    ),

    deleteInbox: defineTool(
      "Delete an inbox and all its messages by address. Irreversible.",
      z.object({
        address: z.string().describe("The inbox address to delete."),
      }),
      ({ address }) => guarded(() => client.inbox(address).delete()),
    ),
  };
}
