"""Thin SQLite store for finance-hub.

Every connection enables `PRAGMA foreign_keys = ON` so FK and CHECK
violations fail loudly rather than silently corrupting state.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("FINANCE_HUB_DB", Path.cwd() / "finance-hub.db"))

# DB paths whose schema has already been ensured this process, so we apply
# migrations once per path on first connect rather than on every connection.
_migrated_paths: set[str] = set()


def connect() -> sqlite3.Connection:
    """Open a connection, applying any pending migrations on first use.

    The schema is ensured once per DB path so a fresh install just works: the
    first tool to touch the store migrates it, with no separate setup step.
    """
    _ensure_schema()
    return _open()


def _open() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema() -> None:
    """Apply pending migrations the first time this DB path is opened.

    The path is marked ready *before* run() so the connections opened by the
    migration runner itself don't recurse into another migration pass. On
    failure the mark is cleared so a later connect retries.
    """
    key = str(DB_PATH)
    if key in _migrated_paths:
        return
    from finance_hub.store import migrations

    _migrated_paths.add(key)
    try:
        migrations.run()
    except Exception:
        _migrated_paths.discard(key)
        raise


def init() -> None:
    """Apply finance-owned migrations against the configured DB."""
    _ensure_schema()


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
