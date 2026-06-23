"""Tests for the finance.import_portfolio_csv registered tool.

Tests run through the registry seam (registry.get(name).fn(**kwargs)) so
they validate the wiring end-to-end, not just the underlying adapter.

Default suite: deterministic, no network, uses the sanitized fixture CSV.
Live suite (-m live): tests against a real Fidelity CSV path from
FINANCE_HUB_TEST_FIDELITY_CSV (skipped if the env var is not set).
"""
from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

from finance_hub.runtime import registry
from finance_hub.store import connection, migrations

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "fidelity_positions_sample.csv"


@pytest.fixture(autouse=True)
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    registry.load_all()
    return p


def _write_csv(tmp_path: Path, body: str, name: str = "positions.csv") -> Path:
    csv = tmp_path / name
    csv.write_text(dedent(body).lstrip())
    return csv


HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Current Value,Cost Basis Total,Type\n"
)


class TestAutoDateExtraction:
    def test_auto_as_of_from_date_downloaded_line(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + '\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        assert result["as_of"] == "2026-06-22T10:30:00-04:00"
        assert result["as_of_source"] == "csv_download_timestamp"

    def test_explicit_as_of_overrides_csv_timestamp(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        override = "2026-06-20T09:00:00-04:00"
        result = registry.get("finance.import_portfolio_csv").fn(
            csv_path=str(csv), as_of=override
        )
        assert result["as_of"] == override
        assert result["as_of_source"] == "explicit_override"

    def test_error_when_no_timestamp_and_no_as_of(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n',
        )
        with pytest.raises(ValueError, match="no.*as_of"):
            registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))


class TestRichSummary:
    def test_returns_snapshot_id(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        assert result["snapshot_id"].startswith("snap_")

    def test_supported_bucket_contains_stock_and_etf(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + 'X1,Brokerage,VTI,"Vanguard Total Stock Market ETF",5,$242.00,$1210.00,$1000.00,Cash\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        supported = result["buckets"]["supported"]
        assert set(supported["tickers"]) == {"AAPL", "VTI"}
        assert supported["count"] == 2

    def test_cash_bucket_contains_fcash(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,FCASH**,"HELD IN FCASH","500.00",$1.00,$500.00,,Cash\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        cash = result["buckets"]["cash"]
        assert "FCASH**" in cash["tickers"]
        assert cash["count"] == 1

    def test_unsupported_bucket_contains_international_tickers(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,SPY.L,"SPDR S&P 500 ETF Trust",5,$400.00,$2000.00,$1800.00,Cash\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        unsupported = result["buckets"]["unsupported"]
        assert "SPY.L" in unsupported["tickers"]
        assert unsupported["count"] == 1

    def test_skipped_bucket_counts_pending_rows(self, tmp_path):
        csv = _write_csv(
            tmp_path,
            HEADER
            + 'X1,Brokerage,AAPL,"Apple Inc",10,$190.00,$1900.00,$1500.00,Cash\n'
            + 'X1,Brokerage,,"Pending activity",,,,,,\n'
            + '"Date downloaded Jun-22-2026 10:30 a.m. ET"\n',
        )
        result = registry.get("finance.import_portfolio_csv").fn(csv_path=str(csv))
        skipped = result["buckets"]["skipped"]
        assert skipped["count"] == 1


class TestRealSampleFixture:
    def test_import_fixture_via_registry_seam(self):
        """Import the real-sample fixture through the registry and validate summary."""
        result = registry.get("finance.import_portfolio_csv").fn(
            csv_path=str(FIXTURE_CSV)
        )
        assert result["snapshot_id"].startswith("snap_")
        assert result["as_of_source"] == "csv_download_timestamp"
        # The fixture has "Date downloaded Jun-22-2026 10:30 a.m. ET"
        assert "2026-06-22" in result["as_of"]

        supported = result["buckets"]["supported"]
        assert set(supported["tickers"]) >= {"VTI", "AAPL", "QQQ"}
        assert supported["count"] >= 3

        cash = result["buckets"]["cash"]
        assert "FCASH**" in cash["tickers"]

        skipped = result["buckets"]["skipped"]
        assert skipped["count"] >= 1  # Pending activity row

    def test_explicit_as_of_overrides_fixture_timestamp(self):
        override = "2026-06-20T09:00:00-04:00"
        result = registry.get("finance.import_portfolio_csv").fn(
            csv_path=str(FIXTURE_CSV), as_of=override
        )
        assert result["as_of"] == override
        assert result["as_of_source"] == "explicit_override"


@pytest.mark.live
def test_live_fidelity_csv(tmp_path):
    """Import a real Fidelity CSV from FINANCE_HUB_TEST_FIDELITY_CSV.

    Run with: pytest -m live
    Skipped if the env var is not set.
    """
    live_path = os.environ.get("FINANCE_HUB_TEST_FIDELITY_CSV")
    if not live_path:
        pytest.skip("FINANCE_HUB_TEST_FIDELITY_CSV not set")
    result = registry.get("finance.import_portfolio_csv").fn(csv_path=live_path)
    assert result["snapshot_id"].startswith("snap_")
    assert result["as_of_source"] == "csv_download_timestamp"
    assert result["buckets"]["supported"]["count"] >= 0
