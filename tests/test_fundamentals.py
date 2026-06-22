"""Slice 6 — fundamentals screening pack (fin_fundamentals).

Covers the acceptance criteria:
- migration creates `fin_fundamentals` with the envelope columns;
- EODHD + Alpha Vantage adapters normalize recorded fixtures into the envelope,
  and EODHD->Alpha Vantage spillover is exercised;
- aggregator data is graded `screening`, the CSV/manual override path works, and
  missing fields surface explicit availability (never zero).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from finance_hub.envelope import DECISION, SCREENING
from finance_hub.market_data import fundamentals as F
from finance_hub.store import connection, migrations

FIXTURES = Path(__file__).parent / "fixtures" / "fundamentals"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    return p


# --- migration -----------------------------------------------------------


class TestMigration:
    def test_table_exists_with_envelope_columns(self, db_path):
        with connection.connect() as conn:
            cols = {c["name"]: c for c in conn.execute(
                "PRAGMA table_info(fin_fundamentals)"
            )}
        for required in ("ticker", "field", "as_of", "value", "unit",
                         "source", "grade", "fetched_at", "source_ref"):
            assert required in cols, f"missing column {required}"
        # source/grade/as_of are NOT NULL (required envelope provenance).
        assert cols["source"]["notnull"] == 1
        assert cols["grade"]["notnull"] == 1
        assert cols["as_of"]["notnull"] == 1

    def test_grade_check_constraint(self, db_path):
        import sqlite3

        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_fundamentals "
                    "(ticker, field, as_of, source, grade, fetched_at) "
                    "VALUES ('AAPL','ps','2026-05-30','eodhd','bogus','2026-06-22')"
                )

    def test_primary_key_includes_source(self, db_path):
        # Same ticker/field/as_of from two sources coexist (vendors never merge).
        with connection.connect() as conn:
            for src in ("eodhd", "alpha_vantage"):
                conn.execute(
                    "INSERT INTO fin_fundamentals "
                    "(ticker, field, as_of, value, source, grade, fetched_at) "
                    "VALUES ('AAPL','ps','2026-05-30','7.4',?, 'screening','2026-06-22')",
                    (src,),
                )
            conn.commit()
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_fundamentals WHERE ticker='AAPL' AND field='ps'"
            ).fetchone()[0]
        assert n == 2


# --- normalization contract ----------------------------------------------


class TestEODHDNormalization:
    def test_stock_fields_normalized_as_screening_envelopes(self):
        got = {f.field: f for f in F.normalize_eodhd(load("eodhd_aapl"))}
        assert got[F.REVENUE_GROWTH].value == "0.081"
        assert got[F.PROFITABILITY].value == "0.252"
        assert got[F.PS].value == "7.43"
        assert got[F.FORWARD_PS].value == "6.95"
        assert got[F.EV_EBITDA].value == "22.31"
        assert got[F.TOTAL_DEBT].value == "104500000000"
        assert got[F.TOTAL_CASH].value == "29900000000"
        assert got[F.NEXT_EARNINGS_DATE].value == "2026-07-30"
        # Every aggregator value is screening-grade, sourced, and dated.
        for f in got.values():
            assert f.grade == SCREENING
            assert f.source == "eodhd"
            assert f.as_of == "2026-05-30"

    def test_etf_fields_normalized(self):
        got = {f.field: f for f in F.normalize_eodhd(load("eodhd_spy"))}
        assert got[F.EXPENSE_RATIO].value == "0.0009"
        assert got[F.AUM].value == "612000000000"
        assert got[F.PERF_1Y].value == "0.146"
        holdings = json.loads(got[F.TOP_HOLDINGS].value)
        assert "NVDA.US" in holdings
        assert F.SECTOR_EXPOSURE in got
        for f in got.values():
            assert f.grade == SCREENING


class TestAlphaVantageNormalization:
    def test_stock_overview_normalized(self):
        got = {f.field: f for f in F.normalize_alpha_vantage(load("alpha_vantage_aapl"))}
        assert got[F.PS].value == "7.51"
        assert got[F.EV_EBITDA].value == "22.10"
        assert got[F.REVENUE_GROWTH].value == "0.079"
        assert got[F.PROFITABILITY].value == "0.248"
        for f in got.values():
            assert f.grade == SCREENING
            assert f.source == "alpha_vantage"
            assert f.as_of == "2026-03-31"
        # AV OVERVIEW omits forward P/S and balance-sheet debt/cash.
        assert F.FORWARD_PS not in got
        assert F.TOTAL_DEBT not in got

    def test_etf_profile_normalized(self):
        got = {f.field: f for f in F.normalize_alpha_vantage(load("alpha_vantage_spy"))}
        assert got[F.EXPENSE_RATIO].value == "0.0009"
        assert got[F.AUM].value == "612000000000"
        assert F.TOP_HOLDINGS in got
        assert F.SECTOR_EXPOSURE in got


# --- spillover -----------------------------------------------------------


class TestSpillover:
    def test_uses_eodhd_until_quota_then_alpha_vantage(self):
        eodhd = F.EODHDAdapter(responses={"AAPL": load("eodhd_aapl")}, daily_limit=1)
        av = F.AlphaVantageAdapter(responses={"AAPL": load("alpha_vantage_aapl")})
        provider = F.SpilloverFundamentalsProvider(primary=eodhd, fallback=av)

        first = provider.fetch_fundamentals("AAPL")
        assert all(f.source == "eodhd" for f in first)

        # EODHD's 1-request budget is spent; spillover routes to Alpha Vantage.
        second = provider.fetch_fundamentals("AAPL")
        assert second  # not empty
        assert all(f.source == "alpha_vantage" for f in second)

    def test_adapter_raises_quota_exhausted_directly(self):
        eodhd = F.EODHDAdapter(responses={"AAPL": load("eodhd_aapl")}, daily_limit=0)
        with pytest.raises(F.QuotaExhausted):
            eodhd.fetch_fundamentals("AAPL")


# --- CSV / manual override -----------------------------------------------


class TestManualOverride:
    def test_csv_parses_into_fundamentals(self):
        text = (
            "ticker,field,value,unit,as_of,grade,source_ref\n"
            "AAPL,forward_ps,6.80,x,2026-06-01,screening,\n"
            "NVDA,profitability,0.55,ratio,2026-06-01,decision,10-K-2026\n"
        )
        pairs = F.parse_csv_overrides(text)
        by_ticker = {(t, f.field): f for t, f in pairs}
        assert by_ticker[("AAPL", "forward_ps")].value == "6.80"
        assert by_ticker[("AAPL", "forward_ps")].grade == SCREENING
        # A manual sheet may assert decision grade for a filing-grounded figure.
        nvda = by_ticker[("NVDA", "profitability")]
        assert nvda.grade == DECISION
        assert nvda.source_ref == "10-K-2026"

    def test_manual_override_wins_over_provider(self, db_path):
        prov = F.normalize_eodhd(load("eodhd_aapl"))
        F.store_fundamentals(_conn := connection.connect(), "AAPL", prov,
                             fetched_at="2026-06-22T00:00:00Z")
        _conn.close()
        # Manual override for the same field, older as_of but override source.
        _, manual = F.parse_csv_overrides(
            "ticker,field,value,unit,as_of\nAAPL,ps,9.99,x,2026-01-01\n"
        )[0]
        with connection.connect() as conn:
            F.store_fundamentals(conn, "AAPL", [manual], fetched_at="2026-06-22T00:00:00Z")
            cells = F.screen_fundamentals(conn, "AAPL", [F.PS], now=date(2026, 6, 22),
                                          max_age_days=10_000)
        assert cells[F.PS].value == "9.99"
        assert cells[F.PS].envelope.source == "manual"


# --- availability (never zero) -------------------------------------------


class TestAvailability:
    def _store_aapl(self, conn):
        F.store_fundamentals(conn, "AAPL", F.normalize_eodhd(load("eodhd_aapl")),
                             fetched_at="2026-06-22T00:00:00Z")

    def test_present_field_is_available(self, db_path):
        with connection.connect() as conn:
            self._store_aapl(conn)
            cells = F.screen_fundamentals(conn, "AAPL", [F.PS], now=date(2026, 6, 22))
        assert cells[F.PS].availability == F.AVAILABLE
        assert cells[F.PS].value == "7.43"

    def test_absent_field_is_missing_not_zero(self, db_path):
        # AV-shaped store has no forward_ps; request it -> missing, value None.
        with connection.connect() as conn:
            F.store_fundamentals(conn, "AAPL",
                                 F.normalize_alpha_vantage(load("alpha_vantage_aapl")),
                                 fetched_at="2026-06-22T00:00:00Z")
            cells = F.screen_fundamentals(conn, "AAPL", [F.FORWARD_PS], now=date(2026, 6, 22))
        assert cells[F.FORWARD_PS].availability == F.MISSING
        assert cells[F.FORWARD_PS].value is None  # never coerced to zero

    def test_stale_when_older_than_max_age(self, db_path):
        with connection.connect() as conn:
            self._store_aapl(conn)  # as_of 2026-05-30
            cells = F.screen_fundamentals(conn, "AAPL", [F.PS], now=date(2026, 12, 1),
                                          max_age_days=30)
        assert cells[F.PS].availability == F.STALE
        assert cells[F.PS].value == "7.43"  # value kept, just flagged

    def test_not_configured_when_no_provider_and_no_data(self, db_path):
        with connection.connect() as conn:
            cells = F.screen_fundamentals(conn, "ZZZZ", [F.PS], now=date(2026, 6, 22),
                                          configured=False)
        assert cells[F.PS].availability == F.NOT_CONFIGURED
        assert cells[F.PS].value is None

    def test_zero_sentinel_not_stored_as_value(self):
        # An empty/NA provider field is dropped, not stored as a zero.
        raw = {"General": {"Type": "Common Stock", "UpdatedAt": "2026-05-30"},
               "Highlights": {"PriceSalesTTM": "", "ProfitMargin": "N/A"}}
        assert F.normalize_eodhd(raw) == []


# --- storage idempotency -------------------------------------------------


class TestStorage:
    def test_rerun_upserts_not_duplicates(self, db_path):
        rows = F.normalize_eodhd(load("eodhd_aapl"))
        with connection.connect() as conn:
            F.store_fundamentals(conn, "AAPL", rows, fetched_at="2026-06-22T00:00:00Z")
            F.store_fundamentals(conn, "AAPL", rows, fetched_at="2026-06-23T00:00:00Z")
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_fundamentals WHERE ticker='AAPL' AND field='ps'"
            ).fetchone()[0]
            fetched = conn.execute(
                "SELECT fetched_at FROM fin_fundamentals WHERE ticker='AAPL' AND field='ps'"
            ).fetchone()[0]
        assert n == 1  # upsert, not duplicate
        assert fetched == "2026-06-23T00:00:00Z"  # refreshed in place
