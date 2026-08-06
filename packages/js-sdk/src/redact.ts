// Strips secret fields from agent tool output (B-055).
//
// Why it exists: `createInbox` and `listInboxes` returned the backend payload as-is, and that
// payload carried a per-inbox `api_key` (`mf_sk_…`). Tool output goes into the MODEL's
// context, and from there into prompt logs, AI SDK telemetry, error reports and the model's
// own later answers. `listInboxes` leaked every inbox key on the account in a single call.
//
// The split is deliberate:
//   - SDK = code surface. `Inbox.apiKey` stays; code a human wrote may use it.
//   - Tool = model surface. Everything passing through here is redacted.
//
// Redaction is NAME-based, not value-based: scanning message bodies for strings starting with
// `mf_` would corrupt a legitimate email that happens to discuss a test key.
//
// Connected to:
//   - used by:    @mailflat/ai-sdk tools, user code
//   - depends on: nothing (pure)
//
// Key exports:
//   - `redactSecrets(value)` — deep copy with secret fields removed
//   - `SECRET_NAME_PARTS` — which field names count as secrets

export const SECRET_NAME_PARTS = ["apikey", "secret", "password"] as const;

const normalise = (key: string): string => key.replace(/[_-]/g, "").toLowerCase();

const isSecret = (key: string): boolean => {
  const name = normalise(key);
  return SECRET_NAME_PARTS.some((part) => name.includes(part));
};

/** A copy of `value` with secret fields removed. The input is never modified. */
export function redactSecrets<T>(value: T): T {
  if (Array.isArray(value)) return value.map((v) => redactSecrets(v)) as unknown as T;

  // `null` is also typeof "object" — and we do not want to clone classes like Date/Error.
  if (value !== null && typeof value === "object" && (value as object).constructor === Object) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (!isSecret(k)) out[k] = redactSecrets(v);
    }
    return out as unknown as T;
  }

  return value;
}
