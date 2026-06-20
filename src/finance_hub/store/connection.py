"""Thin SQLite store for finance-hub."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("FINANCE_HUB_DB", Path.cwd() / "finance-hub.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fin_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


def status() -> dict:
    """Counts per table — used by the health tool to confirm the spine is wired."""
    init()
    with connect() as conn:
        tables = ["fin_schema_migrations"]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
