"""Thin SQLite store for finance-hub.

Every connection enables `PRAGMA foreign_keys = ON` so FK and CHECK
violations fail loudly rather than silently corrupting state.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("FINANCE_HUB_DB", Path.cwd() / "finance-hub.db"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    """Apply finance-owned migrations against the configured DB."""
    # Imported lazily to avoid a circular import at module load.
    from finance_hub.store import migrations

    migrations.run()


def status() -> dict:
    """Counts per table — used by the health tool to confirm the spine is wired."""
    init()
    with connect() as conn:
        tables = [
            "fin_schema_migrations",
            "fin_fundamentals",
            "fin_fetch_log",
            "fin_metrics",
            "fin_deployment_plans",
        ]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
