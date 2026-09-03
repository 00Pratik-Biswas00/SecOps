"""Run the MCP server over stdio (for Gemini/ADK clients)."""

import asyncio

from app.mcp.tools import mcp


def main():
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
