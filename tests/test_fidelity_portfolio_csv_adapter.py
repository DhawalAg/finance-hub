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
from finance_hub.strategy.portfolio_snapshot import (
    FidelityPortfolioCsvAdapter,
    parse_date_downloaded,
)

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "fidelity_positions_sample.csv"


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
    def test_international_ticker_marked_ineligible(self, db_path, tmp_path):
        # Tickers with "." (non-USD listings) are unsupported regardless of asset type.
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,SPY.L,"SPDR S&P 500 ETF Trust",5,$400.00,$2000.00,$1800.00,Cash\n',
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
        assert pos["market_value_micros"] == 2_000_000_000

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


class TestAssetTypeInferredFromDescription:
    def test_etf_inferred_from_description_not_type_column(self, db_path, tmp_path):
        # Type=Margin (real account-registration value); ETF still detected from description.
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,"Rollover IRA",VTI,"Vanguard Total Stock Market ETF",5,$200.00,$1000.00,$800.00,Margin\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT asset_type, account_registration FROM fin_portfolio_positions"
                " WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["asset_type"] == "etf"
        assert pos["account_registration"] == "margin"

    def test_stock_inferred_when_no_etf_in_description(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT asset_type FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["asset_type"] == "stock"

    def test_fcash_ticker_classified_as_cash(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,FCASH**,"HELD IN FCASH","500.00",$1.00,$500.00,,Cash\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT asset_type FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["asset_type"] == "cash"

    def test_pending_activity_row_skipped(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + 'X1,Brokerage,,"Pending activity",,,,,Cash\n',
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

    def test_pending_activity_in_symbol_column_skipped(self, db_path, tmp_path):
        # Real Fidelity exports put "Pending activity" in the Symbol column
        # with an empty Description (the prior test covered the inverse).
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + 'X1,Individual,Pending activity,,,,,$2.32,,,,,,,,,\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-23T18:29:00-04:00"
        )
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT ticker FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchall()
        tickers = {r["ticker"] for r in rows}
        assert tickers == {"AAPL"}
        assert "Pending activity" not in tickers

    def test_account_registration_stored_from_type_column(self, db_path, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n',
        )
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv, as_of="2026-06-22T10:00:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT account_registration FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        assert pos["account_registration"] == "cash"


class TestParseDateDownloaded:
    def test_am_time(self):
        dt = parse_date_downloaded("Date downloaded Jun-22-2026 10:30 a.m. ET")
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 22
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.tzname() in {"EDT", "EST", "America/New_York", "UTC-04:00", "UTC-05:00"}

    def test_pm_time(self):
        dt = parse_date_downloaded("Date downloaded Dec-31-2026 2:00 p.m. ET")
        assert dt.year == 2026
        assert dt.month == 12
        assert dt.day == 31
        assert dt.hour == 14
        assert dt.minute == 0

    def test_noon_pm(self):
        dt = parse_date_downloaded("Date downloaded Jan-01-2026 12:00 p.m. ET")
        assert dt.hour == 12

    def test_midnight_am(self):
        dt = parse_date_downloaded("Date downloaded Jan-01-2026 12:00 a.m. ET")
        assert dt.hour == 0

    def test_quoted_line(self):
        dt = parse_date_downloaded('"Date downloaded Jun-22-2026 10:30 a.m. ET"')
        assert dt.year == 2026
        assert dt.month == 6

    def test_meridiem_without_trailing_period(self):
        # Real Fidelity exports write "p.m"/"a.m" with no trailing period.
        dt = parse_date_downloaded("Date downloaded Jun-23-2026 6:29 p.m ET")
        assert (dt.year, dt.month, dt.day) == (2026, 6, 23)
        assert dt.hour == 18
        assert dt.minute == 29

    def test_am_without_trailing_period(self):
        dt = parse_date_downloaded('"Date downloaded Jun-23-2026 9:05 a.m ET"')
        assert dt.hour == 9
        assert dt.minute == 5


class TestRealSampleFixture:
    def test_etf_positions_classified_correctly(self, db_path):
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            FIXTURE_CSV, as_of="2026-06-22T10:30:00-04:00"
        )
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT ticker, asset_type, is_supported FROM fin_portfolio_positions"
                " WHERE snapshot_id=? ORDER BY ticker",
                (snapshot_id,),
            ).fetchall()
        by_ticker = {r["ticker"]: dict(r) for r in rows if r["ticker"]}
        assert by_ticker["VTI"]["asset_type"] == "etf"
        assert by_ticker["VTI"]["is_supported"] == 1
        assert by_ticker["QQQ"]["asset_type"] == "etf"
        assert by_ticker["QQQ"]["is_supported"] == 1
        assert by_ticker["AAPL"]["asset_type"] == "stock"
        assert by_ticker["AAPL"]["is_supported"] == 1

    def test_fcash_classified_as_cash(self, db_path):
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            FIXTURE_CSV, as_of="2026-06-22T10:30:00-04:00"
        )
        with connection.connect() as conn:
            pos = conn.execute(
                "SELECT asset_type, is_supported, cash_value_micros"
                " FROM fin_portfolio_positions WHERE snapshot_id=? AND ticker='FCASH**'",
                (snapshot_id,),
            ).fetchone()
        assert pos["asset_type"] == "cash"
        assert pos["is_supported"] == 0
        assert pos["cash_value_micros"] == 1_234_560_000

    def test_pending_activity_not_persisted(self, db_path):
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            FIXTURE_CSV, as_of="2026-06-22T10:30:00-04:00"
        )
        with connection.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()[0]
        # VTI, AAPL, QQQ, FCASH** — Pending activity and disclaimer rows are skipped
        assert count == 4

    def test_account_registration_stored(self, db_path):
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            FIXTURE_CSV, as_of="2026-06-22T10:30:00-04:00"
        )
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT ticker, account_registration FROM fin_portfolio_positions"
                " WHERE snapshot_id=? AND ticker IS NOT NULL ORDER BY ticker",
                (snapshot_id,),
            ).fetchall()
        reg = {r["ticker"]: r["account_registration"] for r in rows}
        assert reg["AAPL"] == "cash"
        assert reg["QQQ"] == "margin"
        assert reg["VTI"] == "cash"

    def test_disclaimer_and_date_rows_not_persisted(self, db_path):
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            FIXTURE_CSV, as_of="2026-06-22T10:30:00-04:00"
        )
        with connection.connect() as conn:
            names = conn.execute(
                "SELECT name FROM fin_portfolio_positions WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchall()
        all_names = [r["name"] for r in names]
        assert not any("data and information" in (n or "").lower() for n in all_names)
        assert not any("date downloaded" in (n or "").lower() for n in all_names)
