"""Deployment plan storage migrations (issues #11 and #12).

Migration 9 creates the plan tables; migration 10 recreates fin_deployment_plans
with extended output_mode / status CHECKs and the Slice-10 freshness/mode columns.
Tests assert constraints and new columns exist and are enforced.
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
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


class TestPlanTables:
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
            "fin_deployment_plans",
            "fin_deployment_plan_lines",
            "fin_deployment_plan_warnings",
            "fin_deployment_plan_evidence",
        ):
            assert t in names, f"missing table: {t}"

    def test_header_has_effective_policy_snapshot(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_deployment_plans")
        assert "effective_policy" in cols
        assert {"dca_budget_micros", "one_time_buy_budget_micros",
                "total_unallocated_micros", "strategy_version_id"} <= cols

    def test_line_bucket_check(self, db_path):
        migrations.run()
        _seed_plan(db_path)
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_deployment_plan_lines "
                    "(line_id, plan_id, bucket, ticker, amount_micros, rank, "
                    " ranked_factors, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("L1", "plan_1", "weekly", "VTI", 100, 1, "[]", "now"),
                )

    def test_warning_severity_check(self, db_path):
        migrations.run()
        _seed_plan(db_path)
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_deployment_plan_warnings "
                    "(plan_id, code, severity, message) VALUES (?,?,?,?)",
                    ("plan_1", "X", "fatal", "msg"),
                )

    def test_evidence_type_check(self, db_path):
        migrations.run()
        _seed_plan(db_path)
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_deployment_plan_evidence "
                    "(plan_id, evidence_type, ref_table, ref_key) VALUES (?,?,?,?)",
                    ("plan_1", "rumor", "t", "k"),
                )


class TestSlice10Schema:
    def test_freshness_columns_exist(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = _cols(conn, "fin_deployment_plans")
        assert "snapshot_freshness_band" in cols
        assert "snapshot_days_old" in cols
        assert "portfolio_changed_after_snapshot" in cols
        assert "blocked_output_modes" in cols

    def test_extended_output_mode_values_accepted(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES ('snap_1','2026-06-20','x','/f','now')"
            )
            for mode in ("watchlist_review", "allocation_review", "deployment_draft"):
                conn.execute(
                    "INSERT INTO fin_deployment_plans "
                    "(plan_id, output_mode, status, portfolio_snapshot_id, "
                    " benchmark_ticker, risk_mode, "
                    " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros, "
                    " effective_policy, created_at) "
                    "VALUES (?,?,'proposed','snap_1','SPY','balanced',0,0,0,'{}','now')",
                    (f"plan_{mode}", mode),
                )
            conn.commit()

    def test_invalid_output_mode_rejected(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES ('snap_2','2026-06-20','x','/f','now')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_deployment_plans "
                    "(plan_id, output_mode, status, portfolio_snapshot_id, "
                    " benchmark_ticker, risk_mode, "
                    " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros, "
                    " effective_policy, created_at) "
                    "VALUES ('plan_bad','weekly_summary','proposed','snap_2',"
                    "'SPY','balanced',0,0,0,'{}','now')"
                )

    def test_extended_status_values_accepted(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES ('snap_3','2026-06-20','x','/f','now')"
            )
            for st in ("proposed", "proposed_with_warnings", "advisory_only",
                       "blocked", "approved", "rejected", "superseded"):
                conn.execute(
                    "INSERT INTO fin_deployment_plans "
                    "(plan_id, output_mode, status, portfolio_snapshot_id, "
                    " benchmark_ticker, risk_mode, "
                    " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros, "
                    " effective_policy, created_at) "
                    "VALUES (?,'deployment_draft',?,'snap_3','SPY','balanced',0,0,0,'{}','now')",
                    (f"plan_st_{st}", st),
                )
            conn.commit()

    def test_portfolio_snapshot_id_is_nullable(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_deployment_plans "
                "(plan_id, output_mode, status, "
                " benchmark_ticker, risk_mode, "
                " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros, "
                " effective_policy, created_at) "
                "VALUES ('plan_null_snap','watchlist_review','proposed',"
                "'SPY','balanced',0,0,0,'{}','now')"
            )
            conn.commit()


def _seed_plan(db_path):
    """A minimal snapshot + strategy + plan header so FK inserts can attach."""
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_portfolio_snapshots "
            "(snapshot_id, as_of, source_adapter, source_file, created_at) "
            "VALUES ('snap_1','2026-06-20','x','/f','now')"
        )
        conn.execute(
            "INSERT INTO fin_strategy_versions "
            "(version_id, status, created_at, updated_at) "
            "VALUES ('strat_1','active','now','now')"
        )
        conn.execute(
            "INSERT INTO fin_deployment_plans "
            "(plan_id, output_mode, status, portfolio_snapshot_id, "
            " strategy_version_id, benchmark_ticker, risk_mode, "
            " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros, "
            " effective_policy, created_at) "
            "VALUES ('plan_1','deployment_draft','proposed','snap_1','strat_1',"
            "'SPY','balanced',0,0,0,'{}','now')"
        )
        conn.commit()
