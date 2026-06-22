// @mailflat/ai-sdk testleri — enjekte edilen mock fetch'li gerçek MailFlat client ile
// her aracın execute()'unun doğru /api/v1 çağrısını yaptığı ve sonucu döndürdüğü doğrulanır.
//
// Kapsam: 6 aracın varlığı + her birinin parameters/inputSchema simetrisi + execute davranışı
// (create/list/read/send/delete + waitForOtp başarı/timeout/şifreli) + hata guard'ı.

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

// Verilen handler'ı fetch olarak kullanan client → tool suite kurar.
function makeSuite(handler: (url: string, init: RequestInit) => Response) {
  const fetchMock = vi.fn(async (url: any, init: any) => handler(String(url), init));
  const client = new MailFlat({ apiKey: "mf_test_x", fetch: fetchMock as any, maxRetries: 0 });
  return { suite: mailflatToolSuite({ client }), fetchMock };
}

describe("suite shape", () => {
  it("exposes the 6 expected tools with matching parameters/inputSchema", () => {
    const { suite } = makeSuite(() => jsonResponse(200, {}));
    expect(Object.keys(suite).sort()).toEqual(
      ["createInbox", "deleteInbox", "listInboxes", "readMessages", "sendEmail", "waitForOtp"].sort(),
    );
    for (const tool of Object.values(suite)) {
      expect(tool.description).toBeTruthy();
      // v3/v4 (parameters) ve v5 (inputSchema) aynı şemayı işaret etmeli.
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
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}/messages`);
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
      expect(url).toBe(`https://mailflat.net/api/v1/inboxes/${ADDR}/latest`);
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
