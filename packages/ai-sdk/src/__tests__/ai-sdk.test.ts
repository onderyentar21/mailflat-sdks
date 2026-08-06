// @mailflat/ai-sdk tests — a real MailFlat client with an injected mock fetch verifies that
// every tool's execute() makes the right /api/v1 call and returns the result.
//
// Covers: the tool set, parameters/inputSchema symmetry for each, execute behaviour
// (create/list/read/send/delete + waitForOtp success/timeout/encrypted) and the error guard.

import { MailFlat } from "@mailflat/sdk";
import { describe, expect, it, vi } from "vitest";
import { mailflatToolSuite } from "../index";

const ADDR = "signup-test@x7k2m.mailflat.net";

function jsonResponse(status: number, body: any): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Build a client that uses the given handler as its fetch, then a tool suite on top.
function makeSuite(handler: (url: string, init: RequestInit) => Response) {
  const fetchMock = vi.fn(async (url: any, init: any) => handler(String(url), init));
  const client = new MailFlat({ apiKey: "mf_test_x", fetch: fetchMock as any, maxRetries: 0 });
  return { suite: mailflatToolSuite({ client }), fetchMock };
}

describe("suite shape", () => {
  it("exposes the 11 expected tools with matching parameters/inputSchema", () => {
    const { suite } = makeSuite(() => jsonResponse(200, {}));
    expect(Object.keys(suite).sort()).toEqual(
      [
        "createInbox",
        "listInboxes",
        "readMessages",
        "waitForOtp",
        "waitForMessage",
        "sendEmail",
        "reply",
        "markRead",
        "burnInbox",
        "deleteInbox",
        "deleteMessage",
      ].sort(),
    );
    for (const tool of Object.values(suite)) {
      expect(tool.description).toBeTruthy();
      // v3/v4 (parameters) and v5 (inputSchema) must point at the same schema.
      expect(tool.parameters).toBe(tool.inputSchema);
      expect(typeof tool.execute).toBe("function");
    }
  });
});

describe("createInbox", () => {
  it("POSTs /api/v1/inboxes and returns inbox.raw", async () => {
    const { suite } = makeSuite((url, init) => {
      expect(init.method).toBe("POST");
      expect(url).toBe("https://mailflat.net/api/v1/inboxes");
      expect(JSON.parse(init.body as string)).toEqual({ label: "deep-research" });
      return jsonResponse(200, { ok: true, address: ADDR, name: "deep-research", retention_hours: 2 });
    });
    const res = await suite.createInbox.execute({ label: "deep-research" });
    expect(res.address).toBe(ADDR);
    expect(res.name).toBe("deep-research");
  });
});

describe("listInboxes", () => {
  it("GETs /api/v1/inboxes and returns { inboxes }", async () => {
    const { suite } = makeSuite((url, init) => {
      expect(init.method).toBe("GET");
      expect(url).toBe("https://mailflat.net/api/v1/inboxes");
      return jsonResponse(200, { ok: true, inboxes: [{ address: ADDR }] });
    });
    const res = await suite.listInboxes.execute({});
    expect(res.inboxes).toHaveLength(1);
    expect(res.inboxes[0].address).toBe(ADDR);
  });
});

describe("readMessages", () => {
  it("GETs messages and returns { emails }", async () => {
    const { suite } = makeSuite((url) => {
      // The default is incoming mail only, so the URL carries a direction filter.
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}/messages?direction=in`);
      return jsonResponse(200, { ok: true, emails: [{ id: 1, subject: "Hi", otp_code: "123456" }] });
    });
    const res = await suite.readMessages.execute({ address: ADDR });
    expect(res.emails).toHaveLength(1);
    expect(res.emails[0].subject).toBe("Hi");
  });
});

describe("waitForOtp", () => {
  it("returns the OTP when it arrives", async () => {
    const { suite } = makeSuite((url) => {
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}/latest?direction=in`);
      return jsonResponse(200, { email: { otp_code: "987654" } });
    });
    const res = await suite.waitForOtp.execute({ address: ADDR, timeout: 5000 });
    expect(res.otp).toBe("987654");
  });

  it("returns { error: 'timeout' } when nothing arrives", async () => {
    const { suite } = makeSuite(() => jsonResponse(200, { email: null }));
    const res = await suite.waitForOtp.execute({ address: ADDR, timeout: 0 });
    expect(res.otp).toBeNull();
    expect(res.error).toBe("timeout");
  });

  it("flags encrypted inboxes", async () => {
    const { suite } = makeSuite(() => jsonResponse(200, { encrypted: true, note: "E2E inbox" }));
    const res = await suite.waitForOtp.execute({ address: ADDR, timeout: 5000 });
    expect(res.otp).toBeNull();
    expect(res.encrypted).toBe(true);
  });
});

describe("sendEmail", () => {
  it("POSTs /send with the payload", async () => {
    const { suite } = makeSuite((url, init) => {
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}/send`);
      expect(JSON.parse(init.body as string)).toEqual({ to: "x@y.com", subject: "Hi", body: "Yo" });
      return jsonResponse(200, { ok: true, status: "sent" });
    });
    const res = await suite.sendEmail.execute({ address: ADDR, to: "x@y.com", subject: "Hi", body: "Yo" });
    expect(res.status).toBe("sent");
  });
});

describe("deleteInbox", () => {
  it("DELETEs the inbox", async () => {
    const { suite } = makeSuite((url, init) => {
      expect(init.method).toBe("DELETE");
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}`);
      return jsonResponse(200, { ok: true });
    });
    const res = await suite.deleteInbox.execute({ address: ADDR });
    expect(res.ok).toBe(true);
  });
});

describe("error guard", () => {
  it("returns { error } instead of throwing on 401", async () => {
    const { suite } = makeSuite(() => jsonResponse(401, { detail: "Invalid API key" }));
    const res = await suite.createInbox.execute({ label: "x" });
    expect(res.error).toContain("Invalid API key");
  });
});

// The tools the leak test actually calls — the coverage check derives from HERE, not from a
// hand-written list. A new tool that is not added here turns the coverage test red.
function leakRuns(suite: Record<string, any>): Array<[string, Promise<any>]> {
  return [
    ["createInbox", suite.createInbox.execute({ label: "leak" })],
    ["listInboxes", suite.listInboxes.execute({})],
    ["readMessages", suite.readMessages.execute({ address: ADDR })],
    ["waitForOtp", suite.waitForOtp.execute({ address: ADDR, timeout: 1 })],
    ["waitForMessage", suite.waitForMessage.execute({ address: ADDR, timeout: 1 })],
    ["sendEmail", suite.sendEmail.execute({ address: ADDR, to: "x@example.com", subject: "s", body: "b" })],
    ["reply", suite.reply.execute({ address: ADDR, messageId: 1, body: "ok" })],
    ["markRead", suite.markRead.execute({ address: ADDR, messageId: 1 })],
    ["burnInbox", suite.burnInbox.execute({ address: ADDR })],
    ["deleteMessage", suite.deleteMessage.execute({ address: ADDR, messageId: 1 })],
    ["deleteInbox", suite.deleteInbox.execute({ address: ADDR })],
  ];
}

// ================================================== secret redaction (B-055)
describe("secret redaction", () => {
  // Tool output goes into the MODEL's context, and from there into prompt logs and AI SDK
  // telemetry. createInbox used to return the backend payload as-is, and listInboxes dumped
  // every inbox key on the account in a single call.

  it("🔒 no tool output carries an inbox api key", async () => {
    const { suite } = makeSuite((url) => {
      if (url.endsWith("/api/v1/inboxes")) {
        return jsonResponse(200, {
          ok: true, address: ADDR, name: "leak", retention_hours: 2,
          api_key: "mf_sk_should_never_reach_the_model",
          inboxes: [{ address: ADDR, api_key: "mf_sk_one" }, { address: "b@x.net", api_key: "mf_sk_two" }],
        });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { ok: true, emails: [{ id: 1, subject: "Verify", otp_code: "424242" }] });
      }
      if (url.includes("/latest")) {
        return jsonResponse(200, { ok: true, email: { id: 1, subject: "Verify", otp_code: "424242" } });
      }
      return jsonResponse(200, { ok: true, api_key: "mf_sk_from_a_write_endpoint" });
    });

    for (const [name, run] of leakRuns(suite)) {
      const blob = JSON.stringify(await run);
      expect(blob, `${name} leaked an inbox key`).not.toContain("mf_sk_");
      expect(blob, `${name} kept an api_key field`).not.toContain("api_key");
    }
  });

  it("🔒 every tool in the suite is covered by the leak test above", () => {
    // Coverage is compared against the tools the leak test REALLY calls, not a hand-written
    // list. The previous version used a literal: updating that list turned the test green
    // while the new tool was never executed.
    const { suite } = makeSuite(() => jsonResponse(200, {}));
    const covered = leakRuns(suite).map(([name]) => name);
    expect(covered.sort()).toEqual(Object.keys(suite).sort());
  });

  it("keeps what the agent needs (address, retention, otp)", async () => {
    const { suite } = makeSuite((url) => {
      if (url.includes("/latest")) {
        return jsonResponse(200, { ok: true, email: { id: 1, subject: "Verify", otp_code: "424242" } });
      }
      return jsonResponse(200, { ok: true, address: ADDR, retention_hours: 2, api_key: "mf_sk_x" });
    });

    const created: any = await suite.createInbox.execute({ label: "keeps" });
    expect(created.address).toBe(ADDR);
    expect(created.retention_hours).toBe(2);

    const otp: any = await suite.waitForOtp.execute({ address: ADDR, timeout: 1 });
    expect(otp.otp).toBe("424242");   // the field is `otp` here (`otp_code` in MCP)
  });

  it("the SDK itself still exposes the key to code", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { ok: true, address: ADDR, api_key: "mf_sk_visible" }));
    const client = new MailFlat({ apiKey: "mf_test_x", fetch: fetchMock as any, maxRetries: 0 });
    const inbox = await client.create({ label: "sdk-side" });
    expect(inbox.apiKey ?? inbox.raw.api_key).toBe("mf_sk_visible");
  });
});
