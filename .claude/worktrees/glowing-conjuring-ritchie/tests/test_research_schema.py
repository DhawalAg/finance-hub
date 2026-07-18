"""Slice 1 schema: fin_themes, fin_instruments, fin_theme_instruments,
fin_research_sources, fin_research_source_links (indexed on review_after),
and fin_events.

Tables, CHECK constraints, and FK relationships are pinned here because
later research tool tests assume them; if the migration shape drifts,
these tests fail loud rather than letting downstream tools silently
accept bad rows.
"""
from __future__ import annotations

import sqlite3

import pytest

from finance_hub.store import connection, migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "research.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    return p


def _columns(conn, table):
    return {r["name"]: r for r in conn.execute(f"PRAGMA table_info({table})")}


class TestTablesExist:
    def test_all_research_tables_created(self, db):
        with connection.connect() as conn:
            names = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        for required in (
            "fin_themes",
            "fin_instruments",
            "fin_theme_instruments",
            "fin_research_sources",
            "fin_research_source_links",
            "fin_events",
        ):
            assert required in names, f"missing table {required}"

    def test_review_after_index_exists(self, db):
        with connection.connect() as conn:
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
        assert "idx_fin_research_source_links_review" in indexes


class TestThemeConstraints:
    def test_status_check(self, db):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_themes (key, display_name, status, created_at, updated_at) "
                    "VALUES ('t1','T1','garbage','2026-01-01','2026-01-01')"
                )

    def test_parent_fk_enforced(self, db):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_themes (key, display_name, status, parent_key, created_at, updated_at) "
                    "VALUES ('child','Child','exploring','no-such-parent','2026-01-01','2026-01-01')"
                )

    def test_self_nesting_allowed_with_real_parent(self, db):
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_themes (key, display_name, status, created_at, updated_at) "
                "VALUES ('compute','Compute','exploring','2026-01-01','2026-01-01')"
            )
            conn.execute(
                "INSERT INTO fin_themes (key, display_name, status, parent_key, created_at, updated_at) "
                "VALUES ('model-providers','Model Providers','exploring','compute','2026-01-01','2026-01-01')"
            )


class TestInstrumentConstraints:
    def test_type_check(self, db):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_instruments (ticker, type, instrument_role, created_at, updated_at) "
                    "VALUES ('AAPL','crypto','single_stock','2026-01-01','2026-01-01')"
                )

    def test_role_check(self, db):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_instruments (ticker, type, instrument_role, created_at, updated_at) "
                    "VALUES ('AAPL','stock','mystery_role','2026-01-01','2026-01-01')"
                )


class TestThemeInstrumentConstraints:
    def _seed(self, conn):
        conn.execute(
            "INSERT INTO fin_themes (key, display_name, status, created_at, updated_at) "
            "VALUES ('compute','Compute','exploring','2026-01-01','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO fin_instruments (ticker, type, instrument_role, created_at, updated_at) "
            "VALUES ('NVDA','stock','single_stock','2026-01-01','2026-01-01')"
        )

    def test_lifecycle_status_check(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_theme_instruments "
                    "(theme_key, ticker, status, added_at, updated_at) "
                    "VALUES ('compute','NVDA','dunno','2026-01-01','2026-01-01')"
                )

    def test_conviction_range_check(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_theme_instruments "
                    "(theme_key, ticker, status, conviction, conviction_note, added_at, updated_at) "
                    "VALUES ('compute','NVDA','candidate',9,'note','2026-01-01','2026-01-01')"
                )

    def test_conviction_requires_note(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_theme_instruments "
                    "(theme_key, ticker, status, conviction, added_at, updated_at) "
                    "VALUES ('compute','NVDA','candidate',3,'2026-01-01','2026-01-01')"
                )

    def test_theme_fk_enforced(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_theme_instruments "
                    "(theme_key, ticker, status, added_at, updated_at) "
                    "VALUES ('no-theme','NVDA','candidate','2026-01-01','2026-01-01')"
                )

    def test_instrument_fk_enforced(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_theme_instruments "
                    "(theme_key, ticker, status, added_at, updated_at) "
                    "VALUES ('compute','ZZZZ','candidate','2026-01-01','2026-01-01')"
                )


class TestSourceConstraints:
    def test_url_unique(self, db):
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_research_sources "
                "(url, title, first_accessed_at, last_accessed_at) "
                "VALUES ('https://example.com/a','A','2026-01-01','2026-01-01')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_research_sources "
                    "(url, title, first_accessed_at, last_accessed_at) "
                    "VALUES ('https://example.com/a','also A','2026-02-01','2026-02-01')"
                )


class TestSourceLinkConstraints:
    def _seed(self, conn):
        conn.execute(
            "INSERT INTO fin_research_sources "
            "(url, title, first_accessed_at, last_accessed_at) "
            "VALUES ('https://example.com/a','A','2026-01-01','2026-01-01')"
        )
        sid = conn.execute("SELECT id FROM fin_research_sources").fetchone()["id"]
        conn.execute(
            "INSERT INTO fin_themes (key, display_name, status, created_at, updated_at) "
            "VALUES ('compute','Compute','exploring','2026-01-01','2026-01-01')"
        )
        return sid

    def test_scope_check(self, db):
        with connection.connect() as conn:
            sid = self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_research_source_links "
                    "(source_id, scope, key, status, linked_at) "
                    "VALUES (?,'rogue','compute','active','2026-01-01')",
                    (sid,),
                )

    def test_status_check(self, db):
        with connection.connect() as conn:
            sid = self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_research_source_links "
                    "(source_id, scope, key, status, linked_at) "
                    "VALUES (?,'theme','compute','deleted','2026-01-01')",
                    (sid,),
                )

    def test_source_fk_enforced(self, db):
        with connection.connect() as conn:
            self._seed(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_research_source_links "
                    "(source_id, scope, key, status, linked_at) "
                    "VALUES (9999,'theme','compute','active','2026-01-01')"
                )
