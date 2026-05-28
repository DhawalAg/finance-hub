"""MCP surface over the tool registry — the same capabilities, exposed to agents.

Run (stdio): python mcp_server.py
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from core import registry

registry.load_all()

mcp = FastMCP("hub-hub")

for t in registry.all_tools().values():
    mcp.add_tool(t.fn, name=t.name, description=t.description)


if __name__ == "__main__":
    mcp.run()
