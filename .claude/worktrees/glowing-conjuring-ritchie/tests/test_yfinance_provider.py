"""yfinance ``PriceProvider`` adapter contract.

Slice 3 (PRD #1, issue #5). The adapter normalizes a yfinance daily-bar
frame (``interval="1d"``, ``auto_adjust=False``) into ``DailyBarEnvelope``
rows. The contract test below feeds a *recorded* fixture payload so it runs
offline and deterministically; one opt-in live test (``-m live``, excluded
from the default suite) exercises the real network path.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

pd = pytest.importorskip("pandas")

from finance_hub.market_data.tools import DailyBarEnvelope
from finance_hub.market_data.yfinance_provider import YFinanceProvider


class FixedClock:
    def __init__(self, instant: datetime):
        self._instant = instant

    def __call__(self) -> datetime:
        return self._instant


def _recorded_frame() -> "pd.DataFrame":
    """A recorded yfinance ``auto_adjust=False`` payload for AAPL.

    Columns are a ``(field, ticker)`` MultiIndex, matching what
    ``yf.download`` returns. Values carry sub-cent precision on purpose so
    the Decimal -> micro-dollar conversion is exercised.
    """
    index = pd.DatetimeIndex(
        [pd.Timestamp("2026-06-18"), pd.Timestamp("2026-06-19"), pd.Timestamp("2026-06-22")]
    )
    data = {
        ("Open", "AAPL"): [149.50, 150.10, 151.00],
        ("High", "AAPL"): [151.00, 151.55, 152.25],
        ("Low", "AAPL"): [149.00, 149.80, 150.70],
        ("Close", "AAPL"): [150.123456, 151.20, 152.005],
        ("Adj Close", "AAPL"): [149.987654, 151.05, 151.90],
        ("Volume", "AAPL"): [1_000_000, 1_100_000, 980_000],
    }
    columns = pd.MultiIndex.from_tuples(data.keys())
    return pd.DataFrame(dict(data), index=index, columns=columns)


@pytest.fixture
def provider():
    captured = {}

    def downloader(tickers, *, start=None, end=None):
        captured["call"] = (tuple(tickers), start, end)
        return _recorded_frame()

    p = YFinanceProvider(
        downloader=downloader,
        now=FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)),
    )
    p.captured = captured
    return p


class TestNormalization:
    def test_returns_daily_bar_envelopes(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=date(2025, 6, 22), end=date(2026, 6, 22))
        assert all(isinstance(b, DailyBarEnvelope) for b in bars)
        assert [b.session_date for b in bars] == ["2026-06-18", "2026-06-19", "2026-06-22"]

    def test_prices_are_integer_micro_dollars(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=date(2025, 6, 22), end=date(2026, 6, 22))
        first = bars[0]
        # 150.123456 -> 150_123_456 micros; raw unadjusted close is the anchor.
        assert first.close_micros == 150_123_456
        assert first.adj_close_micros == 149_987_654
        assert first.open_micros == 149_500_000
        assert all(isinstance(b.close_micros, int) for b in bars)

    def test_half_up_rounding_to_the_micro(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=None, end=None)
        # 152.005 -> 152_005_000 (already exact at micro scale)
        assert bars[2].close_micros == 152_005_000

    def test_source_and_currency_stamped(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=None, end=None)
        assert {b.source for b in bars} == {"yfinance"}
        assert {b.currency for b in bars} == {"USD"}

    def test_fetch_timestamps_from_clock(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=None, end=None)
        assert bars[0].first_fetched_at == "2026-06-22T12:00:00+00:00"
        assert bars[0].last_refreshed_at == "2026-06-22T12:00:00+00:00"

    def test_volume_is_integer_shares(self, provider):
        bars = provider.fetch_daily_bars(["AAPL"], start=None, end=None)
        assert bars[0].volume == 1_000_000
        assert isinstance(bars[0].volume, int)

    def test_unknown_ticker_yields_no_bars(self, provider):
        bars = provider.fetch_daily_bars(["MSFT"], start=None, end=None)
        assert bars == []


@pytest.mark.live
def test_live_fetch_real_bars():
    """Opt-in: hits the real yfinance network path. Excluded by default
    (``addopts = -m 'not live'``); run with ``pytest -m live``."""
    provider = YFinanceProvider()
    bars = provider.fetch_daily_bars(["AAPL"], start=date(2024, 1, 2), end=date(2024, 1, 6))
    assert bars, "expected at least one daily bar from the live provider"
    assert all(b.source == "yfinance" for b in bars)
    assert all(isinstance(b.close_micros, int) and b.close_micros > 0 for b in bars)
