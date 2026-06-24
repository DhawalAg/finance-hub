"""Finance-owned migration runner.

- `fin_schema_migrations.version` is INTEGER (not the skeleton's TEXT).
- Migrations apply in order and are idempotent (re-run is a no-op).
- `PRAGMA foreign_keys = ON` is set on every connection; FK/CHECK
  violations fail loudly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from finance_hub.store import connection, migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    return p


class TestMigrationTable:
    def test_version_column_is_integer(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = conn.execute("PRAGMA table_info(fin_schema_migrations)").fetchall()
        version_col = next(c for c in cols if c["name"] == "version")
        assert version_col["type"].upper() == "INTEGER"
        assert version_col["pk"] == 1

    def test_records_applied_versions(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            applied = [r["version"] for r in conn.execute(
                "SELECT version FROM fin_schema_migrations ORDER BY version"
            )]
        assert applied == sorted(applied)
        assert applied  # at least migration 1 ran
        assert all(isinstance(v, int) for v in applied)


class TestIdempotency:
    def test_rerun_is_noop(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            first = conn.execute("SELECT version FROM fin_schema_migrations").fetchall()
        migrations.run()
        migrations.run()
        with connection.connect() as conn:
            third = conn.execute("SELECT version FROM fin_schema_migrations").fetchall()
        assert [r["version"] for r in first] == [r["version"] for r in third]

    def test_applies_only_missing_migrations(self, db_path, monkeypatch):
        extra = (99, "CREATE TABLE fin_test_extra (id INTEGER PRIMARY KEY);")
        original = list(migrations.MIGRATIONS)
        monkeypatch.setattr(migrations, "MIGRATIONS", original)
        migrations.run()
        # add a new migration; only the new one should apply
        monkeypatch.setattr(migrations, "MIGRATIONS", [*original, extra])
        migrations.run()
        with connection.connect() as conn:
            applied = [r["version"] for r in conn.execute(
                "SELECT version FROM fin_schema_migrations ORDER BY version"
            )]
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
        assert 99 in applied
        assert "fin_test_extra" in tables


class TestForeignKeysEnforced:
    def test_pragma_on_every_connection(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_fk_violation_fails_loudly(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.executescript(
                "CREATE TABLE _parent (id INTEGER PRIMARY KEY);"
                "CREATE TABLE _child (id INTEGER PRIMARY KEY, "
                " parent_id INTEGER NOT NULL REFERENCES _parent(id));"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO _child (id, parent_id) VALUES (1, 999)")

    def test_check_violation_fails_loudly(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "CREATE TABLE _c (id INTEGER PRIMARY KEY, n INTEGER NOT NULL CHECK (n > 0))"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO _c (id, n) VALUES (1, -1)")


class TestAutoMigrateOnConnect:
    """A fresh install must work without a separate migrate step: the first
    connect() applies pending migrations so any tool can write immediately."""

    def test_connect_applies_migrations_without_explicit_run(self, db_path):
        # No migrations.run() / init() call — connect() must self-bootstrap.
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='fin_portfolio_snapshots'"
            ).fetchone()
        assert row is not None, "connect() should have created the schema"

    def test_write_tool_path_works_on_fresh_db(self, db_path):
        # Mirrors what an ingestion/strategy tool does: connect then insert.
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES ('s1', '2026-06-24T00:00:00Z', 'test', 'f.csv', '2026-06-24T00:00:00Z')"
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM fin_portfolio_snapshots").fetchone()[0]
        assert count == 1

    def test_migration_runner_does_not_recurse(self, db_path):
        # connect() inside the migration runner must not trigger another pass.
        connection.connect().close()
        with connection.connect() as conn:
            applied = conn.execute(
                "SELECT COUNT(*) FROM fin_schema_migrations"
            ).fetchone()[0]
        assert applied == len(migrations.MIGRATIONS)


class TestNoGlobalUserVersion:
    def test_user_version_not_used_as_state(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            uv = conn.execute("PRAGMA user_version").fetchone()[0]
        assert uv == 0
