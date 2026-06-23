"""Migration creating the versioned strategy model (strategy spec §4, ADR 0003).

- ``fin_strategy_versions`` carries ``version_id``, ``status`` (draft |
  active | archived), and audit stamps. A partial unique index makes at
  most one ``active`` version enforceable.
- ``fin_strategy_sleeves`` owns target weights (basis points so the
  "sum to 100%" check is exact integer arithmetic) and optional hard caps.
- ``fin_strategy_instruments`` maps each eligible ticker to exactly one
  primary sleeve (composite PK) within a version, with a composite FK so
  the primary sleeve must exist in that same version.
"""
from __future__ import annotations

import sqlite3

import pytest

from finance_hub.store import connection, migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    return p


def _cols(conn, table):
    return {r["name"]: r for r in conn.execute(f"PRAGMA table_info({table})")}


def _make_version(conn, version_id="strat_v1", status="draft"):
    conn.execute(
        "INSERT INTO fin_strategy_versions "
        "(version_id, label, status, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (version_id, "v1", status, None, "2026-06-23T00:00:00+00:00",
         "2026-06-23T00:00:00+00:00"),
    )


def _make_sleeve(conn, version_id="strat_v1", sleeve_key="core", bps=10000):
    conn.execute(
        "INSERT INTO fin_strategy_sleeves "
        "(version_id, sleeve_key, display_name, target_weight_bps, hard_cap_bps, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (version_id, sleeve_key, "Core", bps, None, "2026-06-23T00:00:00+00:00"),
    )


class TestStrategyTables:
    def test_all_tables_exist(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            names = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        for t in (
            "fin_strategy_versions",
            "fin_strategy_sleeves",
            "fin_strategy_instruments",
        ):
            assert t in names, f"missing table: {t}"

    def test_version_columns(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_strategy_versions")
        for required in ("version_id", "status", "created_at", "updated_at"):
            assert required in cols
        assert cols["version_id"]["pk"] == 1

    def test_status_check_rejects_unknown(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                _make_version(conn, status="bogus")

    def test_only_one_active_version(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _make_version(conn, "strat_v1", status="active")
            with pytest.raises(sqlite3.IntegrityError):
                _make_version(conn, "strat_v2", status="active")

    def test_many_drafts_allowed(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _make_version(conn, "strat_v1", status="draft")
            _make_version(conn, "strat_v2", status="draft")
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_strategy_versions WHERE status='draft'"
            ).fetchone()[0]
        assert n == 2


class TestSleeveAndInstrumentConstraints:
    def test_sleeve_pk_blocks_duplicate(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _make_version(conn)
            _make_sleeve(conn, sleeve_key="core")
            with pytest.raises(sqlite3.IntegrityError):
                _make_sleeve(conn, sleeve_key="core")

    def test_instrument_one_primary_sleeve_per_ticker(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _make_version(conn)
            _make_sleeve(conn, sleeve_key="core")
            _make_sleeve(conn, sleeve_key="growth", bps=0)
            conn.execute(
                "INSERT INTO fin_strategy_instruments "
                "(version_id, ticker, primary_sleeve_key, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("strat_v1", "VTI", "core", "2026-06-23T00:00:00+00:00"),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_strategy_instruments "
                    "(version_id, ticker, primary_sleeve_key, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    ("strat_v1", "VTI", "growth", "2026-06-23T00:00:00+00:00"),
                )

    def test_instrument_sleeve_must_exist_in_version(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _make_version(conn)
            _make_sleeve(conn, sleeve_key="core")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_strategy_instruments "
                    "(version_id, ticker, primary_sleeve_key, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    ("strat_v1", "VTI", "missing", "2026-06-23T00:00:00+00:00"),
                )
