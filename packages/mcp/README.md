# MailFlat — MCP server

Native [Model Context Protocol](https://modelcontextprotocol.io) server for
[MailFlat](https://mailflat.net). Gives Claude Desktop, Cursor, or any MCP client
**disposable inbox tooling** — create inboxes, wait for OTP codes, send DKIM-signed mail,
and clean up. Built on the [`mailflat`](https://pypi.org/project/mailflat/) Python SDK.

## Run

```bash
# zero-install, isolated (recommended)
MAILFLAT_API_KEY=mf_live_… uvx mailflat-mcp

# or install it
pipx install mailflat-mcp
MAILFLAT_API_KEY=mf_live_… mailflat-mcp
```

## Claude Desktop / Cursor config

Add to `claude_desktop_config.json` (or your client's MCP config):

```json
{
  "mcpServers": {
    "mailflat": {
      "command": "uvx",
      "args": ["mailflat-mcp"],
      "env": { "MAILFLAT_API_KEY": "mf_live_..." }
    }
  }
}
```

Get your API key from the [MailFlat dashboard](https://mailflat.net) → Agents.

## Tools (6)

| Tool | What it does |
|---|---|
| `create_inbox(prefix?, label?, retention_hours?)` | Open a disposable inbox; `retention_hours` capped by your plan |
| `list_inboxes()` | All inboxes this key can see |
| `read_messages(address)` | Read every message in an inbox |
| `wait_for_otp(address, timeout=30)` | Poll until an OTP arrives, then return it |
| `send_email(address, to, subject?, body?, html?)` | Send a DKIM-signed mail from the inbox |
| `delete_inbox(address)` | Delete the inbox and its messages |

## Configuration

- `MAILFLAT_API_KEY` — your account API key (required).
- `MAILFLAT_API_URL` — override the API base (default `https://mailflat.net`; for self-hosted / BYOD).

## License

MIT
