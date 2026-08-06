// Does the published version match what the package reports — guards against B-052.
//
// Same rationale as js-sdk/src/__tests__/version.test.ts: `VERSION` is a literal baked into
// the bundle, so comparing it to package.json is the only guard.
//
// Connected to:
//   - exercises: ../index.ts (VERSION) ↔ ../../package.json (version)
//
// Running it: cd packages/ai-sdk && npm test

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { VERSION } from "../index";

const pkg = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));

describe("VERSION", () => {
  it("🔒 is exactly the version in package.json", () => {
    expect(VERSION).toBe(pkg.version);
  });

  it("looks like a release number", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+(-.+)?$/);
  });
});
