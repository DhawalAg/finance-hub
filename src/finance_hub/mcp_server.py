"""MCP surface over the tool registry — the same capabilities, exposed to agents.

Run (stdio): finance-mcp
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from finance_hub.runtime import registry

registry.load_all()

mcp = FastMCP("finance-hub")

for t in registry.all_tools().values():
    mcp.add_tool(t.fn, name=t.name, description=t.description)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
