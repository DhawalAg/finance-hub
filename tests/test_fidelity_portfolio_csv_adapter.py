"""Fidelity positions CSV -> canonical portfolio snapshot.

The adapter writes immutable ``fin_portfolio_snapshots`` /
``fin_portfolio_positions`` rows. The same CSV imported twice yields two
distinct snapshots; ``source_row_hash`` dedupes duplicate lines inside a
single import; account type is captured.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from finance_hub.store import connection, migrations
from finance_hub.strategy.portfolio_snapshot import FidelityPortfolioCsvAdapter


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    return p


def _write_csv(tmp_path: Path, body: str, name: str = "positions.csv") -> Path:
    csv = tmp_path / name
    csv.write_text(dedent(body).lstrip())
    return csv


HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Current Value,Cost Basis Total,Type\n"
)


class TestImportCreatesSnapshot:
    def test_returns_snapshot_id(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,"Roth IRA",VTI,Vanguard Total Stock Market ETF,10,$200.00,$2000.00,$1500.00,ETF\n',
        )
        adapter = FidelityPortfolioCsvAdapter()
        snapshot_id = adapter.import_csv(csv, as_of="2026-06-22T10:00:00-04:00")
        assert snapshot_id

        with connection.connect() as conn:
            row = conn.execute(
                "SELECT * FROM fin_portfolio_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert row is not None
        assert row["source_adapter"] == "fidelity_csv"
        assert row["source_file"] == str(csv)
        assert row["as_of"] == "2026-06-22T10:00:00-04:00"

    def test_persists_canonical_position_fields(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,"Roth IRA",VTI,Vanguard Total Stock Market ETF,10,$200.00,"$2,000.00","$1,500.00",ETF\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT * FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["account_name"] == "Roth IRA"
        assert pos["account_type"] == "roth_ira"
        assert pos["ticker"] == "VTI"
        assert pos["asset_type"] == "etf"
        assert pos["quantity"] == "10"
        assert pos["market_value_micros"] == 2_000_000_000
        assert pos["cost_basis_micros"] == 1_500_000_000
        assert pos["currency"] == "USD"
        assert pos["is_supported"] == 1
        assert pos["source_row_hash"]


class TestImmutability:
    def test_reimport_yields_distinct_snapshot(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,SPY,SPDR S&P 500,5,$400.00,$2000.00,$1800.00,ETF\n',
        )
        adapter = FidelityPortfolioCsvAdapter()
        a = adapter.import_csv(csv, as_of="2026-06-22T10:00:00-04:00")
        b = adapter.import_csv(csv, as_of="2026-06-23T10:00:00-04:00")
        assert a != b

        with connection.connect() as conn:
            snapshots = conn.execute("SELECT snapshot_id FROM fin_portfolio_snapshots").fetchall()
            first_rows = conn.execute(
                "SELECT * FROM fin_portfolio_positions WHERE snapshot_id=? ORDER BY position_id",
                (a,),
            ).fetchall()
        assert {r["snapshot_id"] for r in snapshots} == {a, b}
        # prior snapshot rows unchanged
        assert len(first_rows) == 1
        assert first_rows[0]["ticker"] == "SPY"


class TestSourceRowHashDedupes:
    def test_duplicate_lines_collapse_within_one_import(self, db_path, tmp_path):
        # Two identical lines in one file → one persisted position.
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,SPY,SPDR S&P 500,5,$400.00,$2000.00,$1800.00,ETF\n'
            + 'X1,Brokerage,SPY,SPDR S&P 500,5,$400.00,$2000.00,$1800.00,ETF\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()[0]
        assert count == 1


class TestAccountTypeCaptured:
    def test_normalizes_account_types(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,"Roth IRA",VTI,Vanguard Total Stock,10,$200.00,$2000.00,$1500.00,ETF\n'
            + 'X2,"Rollover IRA",VTI,Vanguard Total Stock,5,$200.00,$1000.00,$800.00,ETF\n'
            + 'X3,"Individual Brokerage",VTI,Vanguard Total Stock,3,$200.00,$600.00,$500.00,ETF\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT account_name, account_type FROM fin_portfolio_positions"
                " WHERE snapshot_id=? ORDER BY account_name",
                (snapshot_id,),
            ).fetchall()
        types = {r["account_name"]: r["account_type"] for r in rows}
        assert types["Roth IRA"] == "roth_ira"
        assert types["Rollover IRA"] == "ira"
        assert types["Individual Brokerage"] == "brokerage"


class TestUnsupportedHoldings:
    def test_unsupported_with_market_value_marked_ineligible(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,BTC,Bitcoin,1,$50000.00,$50000.00,$30000.00,Crypto\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT * FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["is_supported"] == 0
        assert pos["market_value_micros"] == 50_000_000_000

    def test_cash_position_captured_as_cash_value(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,FCASH**,FIDELITY GOVERNMENT CASH RESERVES,1234.56,$1.00,"$1,234.56",,Cash\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT * FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["asset_type"] == "cash"
        assert pos["is_supported"] == 0
        assert pos["cash_value_micros"] == 1_234_560_000
