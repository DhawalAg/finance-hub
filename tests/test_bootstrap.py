"""Tests for bootstrap: .env loading and lazy price-provider auto-wiring.

Deterministic suite (no network). The live twin verifies a real yfinance fetch.
"""
from __future__ import annotations

import os
import sys

import pytest

from finance_hub import factories
from finance_hub import bootstrap as bootstrap_module
from finance_hub.market_data.yfinance_provider import YFinanceProvider


class TestProviderAutoWiring:
    def setup_method(self):
        factories.reset()
        os.environ.pop("FINANCE_HUB_PRICE_PROVIDER", None)

    def teardown_method(self):
        factories.reset()
        os.environ.pop("FINANCE_HUB_PRICE_PROVIDER", None)

    def test_default_registers_yfinance_factory(self):
        """No env var → bootstrap registers a yfinance factory."""
        bootstrap_module.bootstrap()
        provider = factories.get_price_provider()
        assert isinstance(provider, YFinanceProvider)

    def test_explicit_yfinance_registers_factory(self):
        os.environ["FINANCE_HUB_PRICE_PROVIDER"] = "yfinance"
        bootstrap_module.bootstrap()
        provider = factories.get_price_provider()
        assert isinstance(provider, YFinanceProvider)

    def test_none_leaves_provider_unconfigured(self):
        os.environ["FINANCE_HUB_PRICE_PROVIDER"] = "none"
        bootstrap_module.bootstrap()
        with pytest.raises(LookupError):
            factories.get_price_provider()

    def test_unknown_provider_raises_value_error(self):
        os.environ["FINANCE_HUB_PRICE_PROVIDER"] = "polygon"
        with pytest.raises(ValueError, match="Unknown FINANCE_HUB_PRICE_PROVIDER"):
            bootstrap_module.bootstrap()

    def test_factory_is_lazy_before_first_get(self):
        """After bootstrap(), the provider is NOT instantiated until get_price_provider()."""
        bootstrap_module.bootstrap()
        # The cached instance should still be None — factory registered but not yet called.
        assert factories._price_provider is None
        # First get triggers instantiation.
        factories.get_price_provider()
        assert factories._price_provider is not None

    def test_reset_clears_registered_factory(self):
        """factories.reset() should wipe any registered factory so a fresh bootstrap is needed."""
        bootstrap_module.bootstrap()
        factories.reset()
        with pytest.raises(LookupError):
            factories.get_price_provider()

    def test_factory_cached_after_first_get(self):
        """Subsequent get_price_provider() calls return the same instance."""
        bootstrap_module.bootstrap()
        first = factories.get_price_provider()
        second = factories.get_price_provider()
        assert first is second

    def test_set_price_provider_overrides_factory(self):
        """Calling set_price_provider() with a real instance takes precedence over any factory."""

        class _Stub:
            def fetch_daily_bars(self, tickers, *, start=None, end=None):
                return []

        stub = _Stub()
        bootstrap_module.bootstrap()  # registers yfinance factory
        factories.set_price_provider(stub)  # override with stub
        assert factories.get_price_provider() is stub


class TestLoadDotenv:
    def test_load_dotenv_reads_file(self, tmp_path, monkeypatch):
        """load_dotenv() reads key=value from the .env file into os.environ."""
        env_file = tmp_path / ".env"
        env_file.write_text("_TEST_BOOTSTRAP_VAR=hello_world\n")
        monkeypatch.delenv("_TEST_BOOTSTRAP_VAR", raising=False)
        monkeypatch.delenv("FINANCE_HUB_ENV", raising=False)
        monkeypatch.chdir(tmp_path)

        bootstrap_module.load_dotenv()

        assert os.environ.get("_TEST_BOOTSTRAP_VAR") == "hello_world"
        monkeypatch.delenv("_TEST_BOOTSTRAP_VAR", raising=False)

    def test_finance_hub_env_overrides_dotenv_path(self, tmp_path, monkeypatch):
        """FINANCE_HUB_ENV points to an alternate .env file."""
        custom = tmp_path / "custom.env"
        custom.write_text("_TEST_BOOTSTRAP_CUSTOM=overridden\n")
        monkeypatch.setenv("FINANCE_HUB_ENV", str(custom))
        monkeypatch.delenv("_TEST_BOOTSTRAP_CUSTOM", raising=False)

        bootstrap_module.load_dotenv()

        assert os.environ.get("_TEST_BOOTSTRAP_CUSTOM") == "overridden"
        monkeypatch.delenv("_TEST_BOOTSTRAP_CUSTOM", raising=False)


class TestFundamentalsAutoWiring:
    """bootstrap() wires the fundamentals provider from EODHD/Alpha Vantage keys."""

    _KEYS = ("EODHD_API_KEY", "ALPHA_VANTAGE_API_KEY", "FINANCE_HUB_PRICE_PROVIDER")

    def setup_method(self):
        factories.reset()
        for k in self._KEYS:
            os.environ.pop(k, None)

    def teardown_method(self):
        factories.reset()
        for k in self._KEYS:
            os.environ.pop(k, None)

    def test_no_keys_leaves_fundamentals_unconfigured(self):
        bootstrap_module.bootstrap()
        with pytest.raises(LookupError):
            factories.get_fundamentals_provider()

    def test_eodhd_key_wires_live_eodhd(self):
        from finance_hub.market_data.fundamentals_http import LiveEODHDProvider

        os.environ["EODHD_API_KEY"] = "eodhd-key"
        bootstrap_module.bootstrap()
        provider = factories.get_fundamentals_provider()
        assert isinstance(provider, LiveEODHDProvider)
        assert provider.api_key == "eodhd-key"

    def test_alpha_vantage_only_wires_live_alpha_vantage(self):
        from finance_hub.market_data.fundamentals_http import LiveAlphaVantageProvider

        os.environ["ALPHA_VANTAGE_API_KEY"] = "av-key"
        bootstrap_module.bootstrap()
        provider = factories.get_fundamentals_provider()
        assert isinstance(provider, LiveAlphaVantageProvider)

    def test_both_keys_wire_spillover_eodhd_then_alpha_vantage(self):
        from finance_hub.market_data.fundamentals import SpilloverFundamentalsProvider
        from finance_hub.market_data.fundamentals_http import (
            LiveAlphaVantageProvider,
            LiveEODHDProvider,
        )

        os.environ["EODHD_API_KEY"] = "eodhd-key"
        os.environ["ALPHA_VANTAGE_API_KEY"] = "av-key"
        bootstrap_module.bootstrap()
        provider = factories.get_fundamentals_provider()
        assert isinstance(provider, SpilloverFundamentalsProvider)
        assert isinstance(provider.primary, LiveEODHDProvider)
        assert isinstance(provider.fallback, LiveAlphaVantageProvider)


@pytest.mark.live
def test_live_yfinance_fetch_via_bootstrap():
    """Bootstrap wires yfinance; real SPY fetch returns bars."""
    try:
        factories.reset()
        os.environ.pop("FINANCE_HUB_PRICE_PROVIDER", None)
        bootstrap_module.bootstrap()
        provider = factories.get_price_provider()
        bars = provider.fetch_daily_bars(["SPY"], start="2026-06-01", end="2026-06-05")
        assert len(bars) > 0
        assert bars[0].ticker == "SPY"
    finally:
        factories.reset()
        os.environ.pop("FINANCE_HUB_PRICE_PROVIDER", None)
