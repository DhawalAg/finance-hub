"""Core (cross-hub) tools."""
from __future__ import annotations

from core import store
from core.registry import tool


@tool(name="health", description="Report store status (row counts per table) to confirm the spine is wired.")
def health() -> dict:
    return {"db": str(store.DB_PATH), "tables": store.status()}
