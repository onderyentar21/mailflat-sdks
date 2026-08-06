// MailFlat tool suite for the Vercel AI SDK — createInbox, listInboxes, readMessages,
// waitForOtp, waitForMessage, sendEmail, markRead, burnInbox, deleteInbox, deleteMessage.
//
// A thin layer over the @mailflat/sdk client; all HTTP and behaviour live there (DRY).
//
// Connected to:
//   - depends on: @mailflat/sdk (MailFlat client + redactSecrets), zod (schemas)
//   - used by:    index.ts, user code (generateText({ tools: { ...mailflatToolSuite(...) } }))
//
// Key export: mailflatToolSuite(options) → dictionary of tool objects

import { EncryptedInboxError, MailFlat, MailFlatError, OTPTimeoutError, redactSecrets } from "@mailflat/sdk";
import { z } from "zod";

export interface ToolSuiteOptions {
  /** MailFlat account API key (mf_live_...). Falls back to the MAILFLAT_API_KEY env var. */
  apiKey?: string;
  /** API root (defaults to https://mailflat.net). Override for self-hosted or test setups. */
  baseUrl?: string;
  /** Inject an existing MailFlat client (for tests or a shared client). */
  client?: MailFlat;
}

// Shape of a Vercel AI SDK tool. `parameters` (v3/v4) and `inputSchema` (v5) point at the
// same schema; generateText reads whichever key its version knows and ignores the other.
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

// Turns a MailFlatError into a plain result the model can act on (instead of throwing) AND
// redacts the output. Redaction lives HERE on purpose: every tool passes through this point,
// including the one added tomorrow, so nobody can forget to call `redactSecrets`.
async function guarded<T>(fn: () => Promise<T>): Promise<T | { error: string }> {
  try {
    return redactSecrets(await fn());
  } catch (err) {
    if (err instanceof MailFlatError) return { error: err.message };
    throw err;
  }
}

/**
 * Returns ready-made tool objects to spread into the Vercel AI SDK's `generateText` /
 * `streamText` `tools` field.
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
      "Read messages in the given inbox address (newest first). Returns received mail by default.",
      z.object({
        address: z.string().describe("The full inbox address to read, e.g. signup-8f3@mailflat.net."),
        direction: z
          .enum(["in", "out", "all"])
          .optional()
          .describe(
            "'in' (default) for received mail, 'out' for mail sent from this address, 'all' for both.",
          ),
      }),
      ({ address, direction }) =>
        guarded(async () => {
          const messages = await client.inbox(address).messages({ direction });
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
          // This tool handles its own error branches, so it does NOT pass through
          // `guarded()` → redaction is applied by hand. Today it returns only a string; if a
          // message body is added here tomorrow (as in the MCP server), the leak must not
          // silently come back.
          return redactSecrets({ otp });
        } catch (err) {
          if (err instanceof OTPTimeoutError) return { otp: null, error: "timeout" };
          if (err instanceof EncryptedInboxError)
            return { otp: null, encrypted: true, error: err.message };
          if (err instanceof MailFlatError) return { otp: null, error: err.message };
          throw err;
        }
      },
    ),

    waitForMessage: defineTool(
      "Poll an inbox until a NEW message arrives, then return it. Only received mail counts, so you can send to someone and wait for their reply without matching your own message.",
      z.object({
        address: z.string().describe("The inbox address to poll."),
        timeout: z
          .number()
          .int()
          .positive()
          .optional()
          .describe("Maximum milliseconds to wait before giving up (default 30000)."),
      }),
      async ({ address, timeout }) => {
        try {
          const msg = await client.inbox(address).waitForMessage({ timeout });
          // Same reason as waitForOtp: it handles its own error branches, so it does not
          // pass through guarded() and redaction is applied by hand.
          return redactSecrets({ email: msg.raw });
        } catch (err) {
          if (err instanceof OTPTimeoutError) return { email: null, error: "timeout" };
          if (err instanceof EncryptedInboxError)
            return { email: null, encrypted: true, error: err.message };
          if (err instanceof MailFlatError) return { email: null, error: err.message };
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

    reply: defineTool(
      "Reply to a message so it stays in the SAME conversation. Prefer this over sendEmail when answering: it fills in the recipient, an 'Re:' subject and the threading headers. A plain sendEmail starts a new conversation in the recipient's client, which does not look like a reply.",
      z.object({
        address: z.string().describe("The inbox address that holds the message."),
        messageId: z.number().describe("The id of the message to answer."),
        body: z.string().optional().describe("Plain-text reply body."),
        html: z.string().optional().describe("Optional HTML body."),
      }),
      ({ address, messageId, body, html }) =>
        guarded(async () => {
          const inbox = client.inbox(address);
          const messages = await inbox.messages({ direction: "all" });
          const target = messages.find((m) => m.id === messageId);
          if (!target) return { error: `Message ${messageId} not found in ${address}` };
          return target.reply!(body ?? "", { html });
        }),
    ),

    markRead: defineTool(
      "Mark one message as read so later polls can skip it.",
      z.object({
        address: z.string().describe("The inbox address that holds the message."),
        messageId: z.number().describe("The id of the message to mark as read."),
      }),
      ({ address, messageId }) => guarded(() => client.inbox(address).markRead(messageId)),
    ),

    burnInbox: defineTool(
      "Delete every message in an inbox but KEEP the address. Use between scenarios so the address stays registered wherever you already used it.",
      z.object({
        address: z.string().describe("The inbox address to empty."),
      }),
      ({ address }) => guarded(() => client.inbox(address).burn()),
    ),

    deleteInbox: defineTool(
      "Delete an inbox and all its messages by address. Irreversible.",
      z.object({
        address: z.string().describe("The inbox address to delete."),
      }),
      ({ address }) => guarded(() => client.inbox(address).delete()),
    ),

    deleteMessage: defineTool(
      "Delete a single message in an inbox by its id (the inbox itself stays).",
      z.object({
        address: z.string().describe("The inbox address that holds the message."),
        messageId: z.number().describe("The id of the message to delete."),
      }),
      ({ address, messageId }) => guarded(() => client.inbox(address).deleteMessage(messageId)),
    ),
  };
}
