"""``finance.snapshot()`` — batch universe acquisition + fetch log.

Slice 4 / acquisition Slice 2 (B) — PRD #1, issue #6. Building on the
on-demand price path (Slice 3 / A), ``snapshot()`` loops the evidence
universe through the ``PriceProvider`` seam to populate/refresh
``fin_price_bars`` and records each per-ticker outcome to ``fin_fetch_log``.

Pinned behaviour (acquisition spec §3, §6, §7):

- A multi-ticker universe is fetched, stored, and refreshed idempotently
  (re-running must not double-write bars — the ``(ticker, session_date,
  source)`` upsert key handles that).
- Each fetch records an outcome to ``fin_fetch_log`` (success / failure /
  empty) — the reliability trip-wire counter.
- Failures for individual tickers are logged and surfaced *without*
  aborting the whole batch (log-and-continue, not fail-loud).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import pytest

from finance_hub import factories
from finance_hub.market_data.tools import (
    DailyBarEnvelope,
    SnapshotResult,
    snapshot,
)
from finance_hub.store import connection, migrations
from tests.helpers import FixedClock


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    yield p


@pytest.fixture(autouse=True)
def _reset_factories():
    factories.reset()
    yield
    factories.reset()


def _make_bar(
    ticker: str,
    session_date: str,
    close_micros: int = 150_000_000,
    *,
    source: str = "yfinance",
    first_fetched_at: str = "2026-06-22T12:00:00Z",
    last_refreshed_at: str = "2026-06-22T12:00:00Z",
) -> DailyBarEnvelope:
    return DailyBarEnvelope(
        ticker=ticker,
        session_date=session_date,
        open_micros=close_micros,
        high_micros=close_micros,
        low_micros=close_micros,
        close_micros=close_micros,
        adj_close_micros=close_micros,
        volume=1_000_000,
        currency="USD",
        source=source,
        first_fetched_at=first_fetched_at,
        last_refreshed_at=last_refreshed_at,
    )


@dataclass
class FlakyProvider:
    """Fake PriceProvider: serves canned bars, raises for ``fail_tickers``."""

    bars_by_ticker: dict
    fail_tickers: frozenset = frozenset()
    source: str = "yfinance"
    calls: list = field(default_factory=list)

    def fetch_daily_bars(self, tickers, *, start=None, end=None):
        self.calls.append(tuple(tickers))
        out = []
        for t in tickers:
            if t in self.fail_tickers:
                raise RuntimeError(f"provider boom for {t}")
            out.extend(self.bars_by_ticker.get(t, []))
        return out


def _set(clock_instant, provider):
    factories.set_clock(FixedClock(clock_instant))
    factories.set_price_provider(provider)


_NOW = datetime(2026, 6, 22, 20, 0, tzinfo=timezone.utc)
_AS_OF = date(2026, 6, 22)


class TestUniverseLoop:
    def test_stores_bars_for_every_ticker(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={
                "AAPL": [_make_bar("AAPL", "2026-06-22", 160_000_000)],
                "MSFT": [_make_bar("MSFT", "2026-06-22", 420_000_000)],
                "SPY": [_make_bar("SPY", "2026-06-22", 540_000_000)],
            }
        )
        _set(_NOW, provider)
        result = snapshot(["AAPL", "MSFT", "SPY"], as_of=_AS_OF)
        assert isinstance(result, SnapshotResult)
        assert {o.ticker for o in result.ok} == {"AAPL", "MSFT", "SPY"}
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM fin_price_bars ORDER BY ticker"
            ).fetchall()
        assert [r["ticker"] for r in rows] == ["AAPL", "MSFT", "SPY"]

    def test_fetches_each_ticker_over_1y_window(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]}
        )
        _set(_NOW, provider)
        snapshot(["AAPL"], as_of=_AS_OF)
        # One isolated call per ticker (so one failure can't poison a batch).
        assert provider.calls == [("AAPL",)]

    def test_idempotent_rerun_does_not_double_write_bars(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22", 160_000_000)]}
        )
        _set(_NOW, provider)
        snapshot(["AAPL"], as_of=_AS_OF)
        snapshot(["AAPL"], as_of=_AS_OF)
        with connection.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_price_bars "
                "WHERE ticker='AAPL' AND session_date='2026-06-22' AND source='yfinance'"
            ).fetchone()[0]
        assert n == 1


class TestFetchLog:
    def test_success_recorded(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]}
        )
        _set(_NOW, provider)
        snapshot(["AAPL"], as_of=_AS_OF)
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT ticker, source, ok, error FROM fin_fetch_log WHERE ticker='AAPL'"
            ).fetchone()
        assert row["ok"] == 1
        assert row["source"] == "yfinance"
        assert row["error"] is None

    def test_each_run_appends_to_log(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]}
        )
        _set(_NOW, provider)
        snapshot(["AAPL"], as_of=_AS_OF)
        snapshot(["AAPL"], as_of=_AS_OF)
        with connection.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_fetch_log WHERE ticker='AAPL'"
            ).fetchone()[0]
        # Log is append-only — it's the reliability trip-wire history.
        assert n == 2


class TestLogAndContinue:
    def test_one_failure_does_not_abort_batch(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={
                "AAPL": [_make_bar("AAPL", "2026-06-22", 160_000_000)],
                "MSFT": [_make_bar("MSFT", "2026-06-22", 420_000_000)],
            },
            fail_tickers=frozenset({"BADX"}),
        )
        _set(_NOW, provider)
        result = snapshot(["AAPL", "BADX", "MSFT"], as_of=_AS_OF)
        # The healthy tickers were still stored.
        with connection.connect() as conn:
            stored = {
                r["ticker"]
                for r in conn.execute("SELECT DISTINCT ticker FROM fin_price_bars")
            }
        assert stored == {"AAPL", "MSFT"}
        # The failure surfaces in the result (not silently swallowed).
        failed = {o.ticker for o in result.failures}
        assert failed == {"BADX"}
        assert any(o.status == "error" for o in result.outcomes if o.ticker == "BADX")

    def test_failure_is_logged_with_error(self, db_path):
        provider = FlakyProvider(
            bars_by_ticker={}, fail_tickers=frozenset({"BADX"})
        )
        _set(_NOW, provider)
        snapshot(["BADX"], as_of=_AS_OF)
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT ok, error FROM fin_fetch_log WHERE ticker='BADX'"
            ).fetchone()
        assert row["ok"] == 0
        assert "boom" in row["error"]

    def test_empty_fetch_is_an_outcome_not_a_crash(self, db_path):
        provider = FlakyProvider(bars_by_ticker={})  # provider sources nothing
        _set(_NOW, provider)
        result = snapshot(["GHOST"], as_of=_AS_OF)
        outcome = next(o for o in result.outcomes if o.ticker == "GHOST")
        assert outcome.status == "empty"
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT ok FROM fin_fetch_log WHERE ticker='GHOST'"
            ).fetchone()
        assert row["ok"] == 0

    def test_non_usd_ticker_logged_not_raised(self, db_path):
        provider = FlakyProvider(bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]})
        _set(_NOW, provider)
        # A non-USD suffix would fail-loud interactively, but a batch snapshot
        # logs-and-continues so one bad universe entry can't abort the run.
        result = snapshot(["BP.L", "AAPL"], as_of=_AS_OF)
        statuses = {o.ticker: o.status for o in result.outcomes}
        assert statuses["BP.L"] == "error"
        assert statuses["AAPL"] == "ok"


class TestDefaultUniverse:
    def test_defaults_to_current_holdings(self, db_path):
        # Seed an immutable portfolio snapshot with two supported holdings.
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES ('snap1', '2026-06-20', 'fidelity_csv', 'pos.csv', '2026-06-20T00:00:00Z')"
            )
            for tkr in ("AAPL", "VOO"):
                conn.execute(
                    "INSERT INTO fin_portfolio_positions "
                    "(snapshot_id, account_name, account_type, ticker, asset_type, "
                    " currency, is_supported, source_row_hash) "
                    "VALUES ('snap1', 'brokerage', 'brokerage', ?, 'stock', 'USD', 1, ?)",
                    (tkr, f"hash-{tkr}"),
                )
            conn.commit()
        provider = FlakyProvider(
            bars_by_ticker={
                "AAPL": [_make_bar("AAPL", "2026-06-22")],
                "VOO": [_make_bar("VOO", "2026-06-22")],
            }
        )
        _set(_NOW, provider)
        result = snapshot(as_of=_AS_OF)  # no explicit universe
        assert {o.ticker for o in result.ok} == {"AAPL", "VOO"}
