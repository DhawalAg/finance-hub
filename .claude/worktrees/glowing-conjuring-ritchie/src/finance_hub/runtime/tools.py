"""Runtime tools that are useful before finance domain slices are implemented."""
from __future__ import annotations

from finance_hub.runtime.registry import tool
from finance_hub.store import connection


@tool(name="health", description="Report finance-hub store status to confirm the tool runtime is wired.")
def health() -> dict:
    return {"db": str(connection.DB_PATH), "tables": connection.status()}
