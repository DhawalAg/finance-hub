"""Provider/clock testability seam.

A single overridable factory module resolves PriceProvider /
FundamentalsProvider and a Clock. Real adapters are selected by
config/param; tests inject fakes without touching the network or the
system clock.

Convention (enforced by usage, not by the factory itself): planning and
validation helpers receive `now` / `as_of` explicitly; they never read
`datetime.utcnow()` inside their bodies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from finance_hub import factories
from finance_hub.envelope import SCREENING, Envelope


# --- fakes ---------------------------------------------------------------


@dataclass
class FakePriceProvider:
    label: str = "fake-price"

    def fetch_daily_bars(self, tickers, *, start=None, end=None):
        return [{"ticker": t, "close": "100.00", "source": self.label} for t in tickers]


@dataclass
class FakeFundamentalsProvider:
    label: str = "fake-fundamentals"

    def fetch_fundamentals(self, ticker):
        return Envelope(
            value={"revenue_growth": "0.10"},
            source=self.label,
            grade=SCREENING,
            as_of="2026-06-01",
        )


class FixedClock:
    def __init__(self, instant: datetime):
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


# --- factories -----------------------------------------------------------


class TestFactoryOverrides:
    def setup_method(self):
        factories.reset()

    def teardown_method(self):
        factories.reset()

    def test_default_price_provider_raises_until_configured(self):
        with pytest.raises(LookupError):
            factories.get_price_provider()

    def test_set_price_provider(self):
        fake = FakePriceProvider("yfinance-fake")
        factories.set_price_provider(fake)
        assert factories.get_price_provider() is fake

    def test_set_fundamentals_provider(self):
        fake = FakeFundamentalsProvider("eodhd-fake")
        factories.set_fundamentals_provider(fake)
        assert factories.get_fundamentals_provider() is fake

    def test_clock_default_is_real_utc(self):
        before = datetime.now(timezone.utc)
        got = factories.get_clock().now()
        after = datetime.now(timezone.utc)
        assert before <= got <= after

    def test_fixed_clock_injection(self):
        fixed = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        factories.set_clock(FixedClock(fixed))
        assert factories.get_clock().now() == fixed

    def test_reset_restores_defaults(self):
        factories.set_price_provider(FakePriceProvider())
        factories.set_fundamentals_provider(FakeFundamentalsProvider())
        factories.set_clock(FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)))
        factories.reset()
        with pytest.raises(LookupError):
            factories.get_price_provider()
        with pytest.raises(LookupError):
            factories.get_fundamentals_provider()
        # Real clock returns again after reset.
        assert isinstance(factories.get_clock().now(), datetime)


class TestUsePriceProviderFromTest:
    """Smoke check: a downstream consumer can call the provider via the
    factory without touching the network or naming a concrete adapter.
    """

    def setup_method(self):
        factories.reset()

    def teardown_method(self):
        factories.reset()

    def test_inject_and_consume(self):
        factories.set_price_provider(FakePriceProvider("pretend-yf"))
        provider = factories.get_price_provider()
        bars = provider.fetch_daily_bars(["AAPL"])
        assert bars[0]["ticker"] == "AAPL"
        assert bars[0]["source"] == "pretend-yf"
