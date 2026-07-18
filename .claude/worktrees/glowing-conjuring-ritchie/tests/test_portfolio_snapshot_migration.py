"""Migration creating immutable canonical portfolio snapshot tables (ADR 0004).

- ``fin_portfolio_snapshots`` carries ``snapshot_id``, ``as_of``,
  ``source_adapter``, ``source_file`` (and a ``created_at`` audit stamp).
- ``fin_portfolio_positions`` carries one row per imported position with
  account name/type, ticker, name, asset_type, quantity, market_value,
  cost_basis, cash_value, currency, and ``source_row_hash``.
- Each position references a snapshot via FK; ``source_row_hash`` is
  unique within a snapshot so re-imports inside one snapshot dedupe
  rather than double-write.
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


class TestSnapshotTable:
    def test_table_exists(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_portfolio_snapshots'"
            ).fetchone()
        assert row is not None

    def test_required_columns(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_portfolio_snapshots")
        for required in ("snapshot_id", "as_of", "source_adapter", "source_file"):
            assert required in cols, f"missing column: {required}"

    def test_snapshot_id_is_primary_key(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_portfolio_snapshots")
        assert cols["snapshot_id"]["pk"] == 1


class TestPositionsTable:
    def test_table_exists(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_portfolio_positions'"
            ).fetchone()
        assert row is not None

    def test_required_columns(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_portfolio_positions")
        required = {
            "snapshot_id",
            "account_name",
            "account_type",
            "ticker",
            "name",
            "asset_type",
            "quantity",
            "market_value_micros",
            "cost_basis_micros",
            "cash_value_micros",
            "currency",
            "is_supported",
            "source_row_hash",
        }
        missing = required - cols.keys()
        assert not missing, f"missing columns: {missing}"

    def test_fk_to_snapshots_enforced(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO fin_portfolio_positions (
                        snapshot_id, account_name, account_type, ticker, name,
                        asset_type, quantity, market_value_micros, cost_basis_micros,
                        cash_value_micros, currency, is_supported, source_row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "nonexistent_snapshot",
                        "Brokerage",
                        "brokerage",
                        "VTI",
                        "Vanguard Total Stock Market",
                        "etf",
                        "10",
                        2_000_000_000,
                        None,
                        None,
                        "USD",
                        1,
                        "rowhash1",
                    ),
                )

    def test_source_row_hash_unique_within_snapshot(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots (snapshot_id, as_of, source_adapter, source_file, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                ("snap_1", "2026-06-22", "fidelity_csv", "/tmp/p.csv", "2026-06-22T00:00:00+00:00"),
            )
            base = (
                "snap_1", "Brokerage", "brokerage", "VTI", "Vanguard Total Stock Market",
                "etf", "10", 2_000_000_000, None, None, "USD", 1, "rowhash1",
            )
            conn.execute(
                """
                INSERT INTO fin_portfolio_positions (
                    snapshot_id, account_name, account_type, ticker, name,
                    asset_type, quantity, market_value_micros, cost_basis_micros,
                    cash_value_micros, currency, is_supported, source_row_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                base,
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO fin_portfolio_positions (
                        snapshot_id, account_name, account_type, ticker, name,
                        asset_type, quantity, market_value_micros, cost_basis_micros,
                        cash_value_micros, currency, is_supported, source_row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    base,
                )

    def test_same_row_hash_allowed_across_snapshots(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            for snap_id in ("snap_a", "snap_b"):
                conn.execute(
                    "INSERT INTO fin_portfolio_snapshots (snapshot_id, as_of, source_adapter, source_file, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (snap_id, "2026-06-22", "fidelity_csv", "/tmp/p.csv", "2026-06-22T00:00:00+00:00"),
                )
                conn.execute(
                    """
                    INSERT INTO fin_portfolio_positions (
                        snapshot_id, account_name, account_type, ticker, name,
                        asset_type, quantity, market_value_micros, cost_basis_micros,
                        cash_value_micros, currency, is_supported, source_row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap_id, "Brokerage", "brokerage", "VTI", "Vanguard Total Stock Market",
                        "etf", "10", 2_000_000_000, None, None, "USD", 1, "rowhash1",
                    ),
                )
            count = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_positions WHERE source_row_hash='rowhash1'"
            ).fetchone()[0]
        assert count == 2
