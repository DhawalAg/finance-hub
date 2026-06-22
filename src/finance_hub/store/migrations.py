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
