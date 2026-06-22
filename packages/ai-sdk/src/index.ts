// @mailflat/ai-sdk — Vercel AI SDK için MailFlat tool suite.
//
// `npm i @mailflat/ai-sdk` → `import { mailflatToolSuite } from "@mailflat/ai-sdk"`.
// `ai` (Vercel AI SDK) peer dependency'dir; tool nesneleri generateText/streamText'in
// `tools` alanına yayılır.
//
// Connected to:
//   - depends on: tools.ts (→ @mailflat/sdk, zod)
//   - used by:    kullanıcı kodu (Vercel AI SDK ajanları)
//
// Key export: mailflatToolSuite (+ tipler)

export { mailflatToolSuite } from "./tools";
export type { ToolSuiteOptions, MailFlatTool } from "./tools";

export const VERSION = "0.1.0";
