"""Finance-owned migration runner.

Finance owns its own migration state in ``fin_schema_migrations`` — *not*
the database-global ``PRAGMA user_version`` — because ``hub.db`` may be
shared with non-finance state in the future.

The version column is INTEGER (an ordered version model), aligning with
the specs. Each entry in ``MIGRATIONS`` is ``(version, sql)`` and is
applied in version order, inside a transaction, and recorded only on
success. Re-running ``run()`` is a no-op: already-applied versions are
skipped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from finance_hub.store import connection

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS fin_schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE fin_themes (
          key          TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          description  TEXT,
          status       TEXT NOT NULL DEFAULT 'exploring',
          parent_key   TEXT,
          note_path    TEXT,
          created_at   TEXT NOT NULL,
          updated_at   TEXT NOT NULL,
          FOREIGN KEY (parent_key) REFERENCES fin_themes(key),
          CHECK (status IN ('exploring','watching','archived'))
        );

        CREATE TABLE fin_instruments (
          ticker          TEXT PRIMARY KEY,
          type            TEXT NOT NULL DEFAULT 'stock',
          instrument_role TEXT NOT NULL,
          display_name    TEXT,
          note_path       TEXT,
          created_at      TEXT NOT NULL,
          updated_at      TEXT NOT NULL,
          CHECK (type IN ('stock','etf')),
          CHECK (instrument_role IN ('broad_market_etf','theme_etf','single_stock'))
        );

        CREATE TABLE fin_theme_instruments (
          theme_key       TEXT NOT NULL,
          ticker          TEXT NOT NULL,
          status          TEXT NOT NULL DEFAULT 'candidate',
          role            TEXT,
          conviction      INTEGER,
          conviction_note TEXT,
          note            TEXT,
          added_at        TEXT NOT NULL,
          updated_at      TEXT NOT NULL,
          PRIMARY KEY (theme_key, ticker),
          FOREIGN KEY (theme_key) REFERENCES fin_themes(key),
          FOREIGN KEY (ticker) REFERENCES fin_instruments(ticker),
          CHECK (status IN ('candidate','watching','approved','rejected')),
          CHECK (conviction IS NULL OR conviction BETWEEN 1 AND 5),
          CHECK (conviction IS NULL OR
                 (conviction_note IS NOT NULL AND length(trim(conviction_note)) > 0))
        );

        CREATE TABLE fin_research_sources (
          id                INTEGER PRIMARY KEY,
          url               TEXT NOT NULL UNIQUE,
          title             TEXT,
          publisher         TEXT,
          source_type       TEXT,
          published_on      TEXT,
          trusted           INTEGER NOT NULL DEFAULT 0,
          first_accessed_at TEXT NOT NULL,
          last_accessed_at  TEXT NOT NULL,
          CHECK (trusted IN (0,1))
        );

        CREATE TABLE fin_research_source_links (
          source_id    INTEGER NOT NULL,
          scope        TEXT NOT NULL,
          key          TEXT NOT NULL,
          note         TEXT,
          status       TEXT NOT NULL DEFAULT 'active',
          review_after TEXT,
          reviewed_at  TEXT,
          linked_at    TEXT NOT NULL,
          PRIMARY KEY (source_id, scope, key),
          FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
          CHECK (scope IN ('instrument','theme')),
          CHECK (status IN ('active','superseded','archived'))
        );

        CREATE INDEX idx_fin_research_source_links_review
          ON fin_research_source_links(status, review_after);

        CREATE TABLE fin_events (
          id             INTEGER PRIMARY KEY,
          scope          TEXT NOT NULL,
          key            TEXT NOT NULL,
          event_type     TEXT NOT NULL,
          event_date     TEXT NOT NULL,
          date_precision TEXT NOT NULL DEFAULT 'date',
          timing         TEXT NOT NULL DEFAULT 'unknown',
          status         TEXT NOT NULL DEFAULT 'scheduled',
          source_id      INTEGER NOT NULL,
          note           TEXT,
          recorded_at    TEXT NOT NULL,
          updated_at     TEXT NOT NULL,
          FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
          UNIQUE (scope, key, event_type, event_date),
          CHECK (scope IN ('instrument','theme')),
          CHECK (event_type IN ('earnings','ex_dividend')),
          CHECK (date_precision IN ('date','tentative')),
          CHECK (timing IN ('before_market','after_market','during_market','unknown')),
          CHECK (status IN ('scheduled','completed','cancelled'))
        );
        """,
    ),
]


def _applied_versions(conn) -> set[int]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_schema_migrations'"
    ).fetchone()
    if row is None:
        return set()
    return {r[0] for r in conn.execute("SELECT version FROM fin_schema_migrations")}


def run() -> None:
    """Apply every pending migration in order. Idempotent."""
    with connection.connect() as conn:
        for version, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
            applied = _applied_versions(conn)
            if version in applied:
                continue
            try:
                conn.execute("BEGIN")
                conn.executescript(sql)
                # Migration 1 creates the table; only record once it exists.
                if _table_exists(conn, "fin_schema_migrations"):
                    conn.execute(
                        "INSERT INTO fin_schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(timezone.utc).isoformat()),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def ensure_schema() -> None:
    """Backwards-compatible alias for ``run()``."""
    run()
