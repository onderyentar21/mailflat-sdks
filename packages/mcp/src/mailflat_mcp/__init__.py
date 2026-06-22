"""MailFlat MCP server paketi — `mailflat` SDK üstünde MCP tool seti.

`uvx mailflat-mcp` ile çalışır; Claude Desktop / Cursor / agent framework'lerine
disposable inbox araçları açar.

Connected to:
  - imports from: mailflat_mcp.server
  - imported by:  console script `mailflat-mcp`, MCP client'lar

Key exports:
  - `mcp` — FastMCP instance
  - `main()` — stdio server giriş noktası
"""
from .server import main, mcp

__version__ = "0.1.0"

__all__ = ["mcp", "main", "__version__"]
