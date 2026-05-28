"""Thin SQLite store shared across hubs. Start simple; swap the backend later if needed."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("HUB_DB", Path(__file__).resolve().parent.parent / "hub.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    dossier TEXT
);
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    company TEXT,
    network_degree INTEGER,
    handles TEXT,        -- json
    dossier TEXT
);
CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    channel TEXT,
    angle TEXT,
    draft TEXT,
    status TEXT,
    created_at TEXT,
    FOREIGN KEY (person_id) REFERENCES people(id)
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    entity_type TEXT,    -- 'company' | 'person'
    entity_id INTEGER,
    url TEXT,
    title TEXT,
    fetched_at TEXT
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
        tables = ["companies", "people", "outreach", "sources"]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
