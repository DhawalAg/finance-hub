"""``finance.prices(...)`` — on-demand price envelopes.

Slice 3 (PRD #1, issue #5) consumer seam:

- Returns a ``PriceEnvelope`` per ticker (never a vendor payload, never a
  bare scalar).
- Caches within ``max_age_minutes`` (default 1440 = 1 day) — fresh bars
  in ``fin_price_bars`` are used without a provider round-trip.
- ``price_overrides`` short-circuit the provider; the override is *not*
  written into the canonical provider series.
- Misses fail loud, naming the offending tickers.
- Non-USD suffix tickers (``.L``, ``.TO``, ``.HK``, ...) are rejected.
- Re-fetching the same ``(ticker, session_date, source)`` is an
  idempotent no-op.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import pytest

from finance_hub import factories
from finance_hub.market_data import tools as md
from finance_hub.market_data.tools import (
    DailyBarEnvelope,
    PriceEnvelope,
    PriceFetchError,
    UnsupportedTickerError,
    prices,
)
from finance_hub.store import connection, migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    yield p


class FixedClock:
    def __init__(self, instant: datetime):
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


@dataclass
class RecordedProvider:
    """Fake PriceProvider that records its calls and returns canned bars."""

    bars_by_ticker: dict[str, list[DailyBarEnvelope]]
    calls: list[tuple[tuple[str, ...], Optional[date], Optional[date]]] = None
    source: str = "yfinance"

    def __post_init__(self):
        if self.calls is None:
            self.calls = []

    def fetch_daily_bars(self, tickers, *, start=None, end=None):
        self.calls.append((tuple(tickers), start, end))
        out: list[DailyBarEnvelope] = []
        for t in tickers:
            out.extend(self.bars_by_ticker.get(t, []))
        return out


def _make_bar(
    ticker: str,
    session_date: str,
    close_micros: int = 150_000_000,
    *,
    adj_close_micros: Optional[int] = None,
    source: str = "yfinance",
    first_fetched_at: str = "2026-06-21T10:00:00Z",
    last_refreshed_at: str = "2026-06-21T10:00:00Z",
) -> DailyBarEnvelope:
    return DailyBarEnvelope(
        ticker=ticker,
        session_date=session_date,
        open_micros=close_micros,
        high_micros=close_micros,
        low_micros=close_micros,
        close_micros=close_micros,
        adj_close_micros=adj_close_micros if adj_close_micros is not None else close_micros,
        volume=1_000_000,
        currency="USD",
        source=source,
        first_fetched_at=first_fetched_at,
        last_refreshed_at=last_refreshed_at,
    )


@pytest.fixture(autouse=True)
def _reset_factories():
    factories.reset()
    yield
    factories.reset()


class TestPriceOverrides:
    def test_override_returns_is_override_envelope(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        # No provider configured — overrides must not call it.
        result = prices(["FOO"], as_of=date(2026, 6, 22), price_overrides={"FOO": "12.34"})
        env = result["FOO"]
        assert isinstance(env, PriceEnvelope)
        assert env.is_override is True
        assert env.value_micros == 12_340_000
        assert env.source == "override"
        assert env.currency == "USD"
        assert env.session_date == "2026-06-22"

    def test_override_is_not_persisted(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        prices(["FOO"], as_of=date(2026, 6, 22), price_overrides={"FOO": "12.34"})
        with connection.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_price_bars WHERE ticker='FOO'"
            ).fetchone()[0]
        assert n == 0


class TestCacheBehavior:
    def test_uses_cached_bar_within_max_age(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(bars_by_ticker={})
        factories.set_price_provider(provider)
        with connection.connect() as conn:
            conn.execute(
                """
                INSERT INTO fin_price_bars
                    (ticker, session_date, close_micros, adj_close_micros, currency,
                     source, first_fetched_at, last_refreshed_at)
                VALUES ('AAPL', '2026-06-20', 150000000, 150500000, 'USD',
                        'yfinance', '2026-06-22T08:00:00Z', '2026-06-22T08:00:00Z')
                """
            )
        result = prices(["AAPL"], as_of=date(2026, 6, 22))
        env = result["AAPL"]
        assert env.value_micros == 150_000_000
        assert env.is_override is False
        assert env.session_date == "2026-06-20"
        assert env.source == "yfinance"
        assert provider.calls == []  # cache hit, no provider round-trip

    def test_stale_bar_triggers_refresh(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        # Cached bar last refreshed 3 days ago — older than max_age 1440 minutes.
        with connection.connect() as conn:
            conn.execute(
                """
                INSERT INTO fin_price_bars
                    (ticker, session_date, close_micros, currency, source,
                     first_fetched_at, last_refreshed_at)
                VALUES ('AAPL', '2026-06-18', 100000000, 'USD', 'yfinance',
                        '2026-06-19T12:00:00Z', '2026-06-19T12:00:00Z')
                """
            )
        provider = RecordedProvider(
            bars_by_ticker={
                "AAPL": [
                    _make_bar(
                        "AAPL", "2026-06-22", close_micros=160_000_000,
                        last_refreshed_at="2026-06-22T12:00:00Z",
                        first_fetched_at="2026-06-22T12:00:00Z",
                    ),
                ]
            }
        )
        factories.set_price_provider(provider)
        result = prices(["AAPL"], as_of=date(2026, 6, 22))
        env = result["AAPL"]
        assert env.value_micros == 160_000_000
        assert env.session_date == "2026-06-22"
        assert len(provider.calls) == 1

    def test_persists_fetched_bars(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(
            bars_by_ticker={
                "AAPL": [
                    _make_bar("AAPL", "2026-06-22", close_micros=160_000_000),
                    _make_bar("AAPL", "2026-06-21", close_micros=159_000_000),
                ]
            }
        )
        factories.set_price_provider(provider)
        prices(["AAPL"], as_of=date(2026, 6, 22))
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT session_date, close_micros FROM fin_price_bars "
                "WHERE ticker='AAPL' ORDER BY session_date"
            ).fetchall()
        assert [(r["session_date"], r["close_micros"]) for r in rows] == [
            ("2026-06-21", 159_000_000),
            ("2026-06-22", 160_000_000),
        ]

    def test_fetch_is_idempotent(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(
            bars_by_ticker={
                "AAPL": [_make_bar("AAPL", "2026-06-22", close_micros=160_000_000)]
            }
        )
        factories.set_price_provider(provider)
        prices(["AAPL"], as_of=date(2026, 6, 22), max_age_minutes=0)
        prices(["AAPL"], as_of=date(2026, 6, 22), max_age_minutes=0)
        with connection.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_price_bars "
                "WHERE ticker='AAPL' AND session_date='2026-06-22' AND source='yfinance'"
            ).fetchone()[0]
        assert n == 1

    def test_fetches_1y_window(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(
            bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]}
        )
        factories.set_price_provider(provider)
        prices(["AAPL"], as_of=date(2026, 6, 22))
        (_tickers, start, end) = provider.calls[0]
        assert end == date(2026, 6, 22)
        assert (date(2026, 6, 22) - start).days == 365


class TestPriceField:
    def test_adj_close_field(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        with connection.connect() as conn:
            conn.execute(
                """
                INSERT INTO fin_price_bars
                    (ticker, session_date, close_micros, adj_close_micros, currency,
                     source, first_fetched_at, last_refreshed_at)
                VALUES ('AAPL', '2026-06-20', 150000000, 145000000, 'USD',
                        'yfinance', '2026-06-22T08:00:00Z', '2026-06-22T08:00:00Z')
                """
            )
        result = prices(["AAPL"], as_of=date(2026, 6, 22), price_field="adj_close")
        assert result["AAPL"].value_micros == 145_000_000
        assert result["AAPL"].price_field == "adj_close"


class TestFailLoud:
    def test_provider_miss_raises_naming_tickers(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(bars_by_ticker={"AAPL": [_make_bar("AAPL", "2026-06-22")]})
        factories.set_price_provider(provider)
        with pytest.raises(PriceFetchError) as exc:
            prices(["AAPL", "ZZZZ"], as_of=date(2026, 6, 22))
        assert "ZZZZ" in str(exc.value)
        # Tickers that *were* sourced shouldn't be in the message.
        assert exc.value.missing_tickers == ("ZZZZ",)


class TestTickerValidation:
    @pytest.mark.parametrize("ticker", ["BP.L", "SHOP.TO", "0700.HK", "TSLA.PA", "SAP.DE"])
    def test_non_usd_suffix_rejected(self, ticker, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        with pytest.raises(UnsupportedTickerError) as exc:
            prices([ticker], as_of=date(2026, 6, 22))
        assert ticker in str(exc.value)

    def test_us_class_share_dot_is_allowed(self, db_path):
        """BRK.B and similar US-class shares carry a dot but are USD-listed."""
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(
            bars_by_ticker={"BRK.B": [_make_bar("BRK.B", "2026-06-22", close_micros=400_000_000)]}
        )
        factories.set_price_provider(provider)
        result = prices(["BRK.B"], as_of=date(2026, 6, 22))
        assert result["BRK.B"].value_micros == 400_000_000


class TestHistoryWaiver:
    def test_short_history_records_waiver(self, db_path):
        """Newer tickers / IPOs return < 1y of bars; record an explicit waiver."""
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        provider = RecordedProvider(
            bars_by_ticker={"IPONEW": [_make_bar("IPONEW", "2026-06-22", close_micros=20_000_000)]}
        )
        factories.set_price_provider(provider)
        result = prices(["IPONEW"], as_of=date(2026, 6, 22))
        assert result["IPONEW"].history_waiver is True

    def test_full_year_history_no_waiver(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        bars = [
            _make_bar("AAPL", f"2025-06-{d:02d}", close_micros=150_000_000)
            for d in range(23, 30)
        ] + [
            _make_bar("AAPL", "2026-06-22", close_micros=160_000_000)
        ]
        provider = RecordedProvider(bars_by_ticker={"AAPL": bars})
        factories.set_price_provider(provider)
        result = prices(["AAPL"], as_of=date(2026, 6, 22))
        assert result["AAPL"].history_waiver is False


class TestPriceEnvelopeShape:
    def test_envelope_carries_provenance(self, db_path):
        factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        with connection.connect() as conn:
            conn.execute(
                """
                INSERT INTO fin_price_bars
                    (ticker, session_date, close_micros, adj_close_micros, currency,
                     source, first_fetched_at, last_refreshed_at)
                VALUES ('AAPL', '2026-06-20', 150000000, 150500000, 'USD',
                        'yfinance', '2026-06-22T08:00:00Z', '2026-06-22T08:00:00Z')
                """
            )
        env = prices(["AAPL"], as_of=date(2026, 6, 22))["AAPL"]
        assert env.ticker == "AAPL"
        assert env.currency == "USD"
        assert env.grade == "screening"
        assert env.last_refreshed_at == "2026-06-22T08:00:00Z"
        assert env.is_override is False
        assert env.stale is False
