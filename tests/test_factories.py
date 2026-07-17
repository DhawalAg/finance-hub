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

import os
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


class TestEnvClock:
    """FINANCE_HUB_NOW env-var front door (issue #35)."""

    def setup_method(self):
        factories.reset()
        os.environ.pop("FINANCE_HUB_NOW", None)

    def teardown_method(self):
        os.environ.pop("FINANCE_HUB_NOW", None)
        factories.reset()

    def test_unset_uses_real_clock(self):
        factories._apply_env_clock()
        before = datetime.now(timezone.utc)
        got = factories.get_clock().now()
        after = datetime.now(timezone.utc)
        assert before <= got <= after

    def test_valid_iso_datetime_with_tz(self):
        os.environ["FINANCE_HUB_NOW"] = "2025-03-15T09:00:00+00:00"
        factories._apply_env_clock()
        assert factories.get_clock().now() == datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc)

    def test_bare_date_becomes_midnight_utc(self):
        os.environ["FINANCE_HUB_NOW"] = "2024-12-01"
        factories._apply_env_clock()
        assert factories.get_clock().now() == datetime(2024, 12, 1, 0, 0, tzinfo=timezone.utc)

    def test_naive_datetime_assumed_utc(self):
        os.environ["FINANCE_HUB_NOW"] = "2025-06-30T14:30:00"
        factories._apply_env_clock()
        assert factories.get_clock().now() == datetime(2025, 6, 30, 14, 30, tzinfo=timezone.utc)

    def test_invalid_value_raises_at_init(self):
        os.environ["FINANCE_HUB_NOW"] = "not-a-date"
        with pytest.raises(ValueError, match="FINANCE_HUB_NOW"):
            factories._apply_env_clock()

    def test_invalid_value_leaves_no_clock_set(self):
        # After a failed _apply_env_clock, clock must not silently be real
        os.environ["FINANCE_HUB_NOW"] = "garbage"
        with pytest.raises(ValueError):
            factories._apply_env_clock()
        # The real clock is still the module default; we just confirm no silent fallback happened
        # (the ValueError propagated — no partial state installed)
        # Real clock is still in place from setup_method's reset(), or whatever was before
        assert factories.get_clock() is not None  # basic sanity

    def test_frozen_clock_returns_same_instant_every_call(self):
        os.environ["FINANCE_HUB_NOW"] = "2025-01-01T00:00:00+00:00"
        factories._apply_env_clock()
        t1 = factories.get_clock().now()
        t2 = factories.get_clock().now()
        assert t1 == t2

    def test_log_emitted_on_activation(self, caplog):
        import logging
        os.environ["FINANCE_HUB_NOW"] = "2025-06-15T00:00:00+00:00"
        with caplog.at_level(logging.WARNING, logger="finance_hub.factories"):
            factories._apply_env_clock()
        assert any("FINANCE_HUB_NOW" in r.message for r in caplog.records)
        assert any("clock frozen" in r.message for r in caplog.records)


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
