"""Startup wiring: .env loading + lazy price-provider registration.

Call load_dotenv() then bootstrap() once from each entry point (CLI, MCP server).
load_dotenv() must run first so FINANCE_HUB_PRICE_PROVIDER is in os.environ
before bootstrap() reads it.
"""
from __future__ import annotations

import os


def load_dotenv() -> None:
    """Load .env (or FINANCE_HUB_ENV path) into the process environment.

    Variables already present in the environment are NOT overwritten, so
    a caller who exports them explicitly always wins.

    When no explicit path is given, searches upward from the current working
    directory (usecwd=True) so the CLI and MCP server find the .env wherever
    the user launched them from.
    """
    from dotenv import find_dotenv, load_dotenv as _load_dotenv

    env_path = os.environ.get("FINANCE_HUB_ENV")
    if env_path:
        _load_dotenv(dotenv_path=env_path, override=False)
    else:
        found = find_dotenv(usecwd=True)
        _load_dotenv(dotenv_path=found or None, override=False)


def bootstrap() -> None:
    """Register provider factories from environment variables.

    FINANCE_HUB_PRICE_PROVIDER semantics:
      unset / "yfinance" → lazy yfinance factory (import deferred until first use)
      "none"             → leave price provider unconfigured
      other              → ValueError

    Must be called after load_dotenv() so the env var is visible.
    """
    from finance_hub import factories

    provider_name = os.environ.get("FINANCE_HUB_PRICE_PROVIDER")

    if provider_name == "none":
        pass
    elif provider_name is None or provider_name == "yfinance":
        def _build_yfinance() -> object:
            from finance_hub.market_data.yfinance_provider import YFinanceProvider
            return YFinanceProvider()

        factories.set_price_provider_factory(_build_yfinance)
    else:
        raise ValueError(
            f"Unknown FINANCE_HUB_PRICE_PROVIDER={provider_name!r}. "
            "Known values: 'yfinance', 'none'."
        )

    _bootstrap_fundamentals(factories)


def _bootstrap_fundamentals(factories) -> None:
    """Wire the live fundamentals provider from API keys, if any are set.

    ALPHA_VANTAGE_API_KEY is the free fundamentals runner (25 calls/day).
    EODHD_API_KEY is the *paid* upgrade — EODHD's free tier excludes
    fundamentals — so when it is present it runs primary (richer pack) and
    spills to Alpha Vantage on quota exhaustion. Wiring:

      Alpha Vantage only    → LiveAlphaVantageProvider  (the free default)
      EODHD only            → LiveEODHDProvider          (paid)
      EODHD + Alpha Vantage → SpilloverFundamentalsProvider(EODHD → Alpha Vantage)
      neither               → leave unconfigured (reads surface 'not_configured')

    Providers use stdlib HTTP and are cheap to construct, so an instance is
    registered directly (no lazy factory needed, unlike the yfinance import).
    """
    eodhd_key = (os.environ.get("EODHD_API_KEY") or "").strip()
    alpha_key = (os.environ.get("ALPHA_VANTAGE_API_KEY") or "").strip()
    if not eodhd_key and not alpha_key:
        return

    from finance_hub.market_data.fundamentals import SpilloverFundamentalsProvider
    from finance_hub.market_data.fundamentals_http import (
        LiveAlphaVantageProvider,
        LiveEODHDProvider,
    )

    if eodhd_key and alpha_key:
        provider = SpilloverFundamentalsProvider(
            primary=LiveEODHDProvider(api_key=eodhd_key),
            fallback=LiveAlphaVantageProvider(api_key=alpha_key),
        )
    elif eodhd_key:
        provider = LiveEODHDProvider(api_key=eodhd_key)
    else:
        provider = LiveAlphaVantageProvider(api_key=alpha_key)

    factories.set_fundamentals_provider(provider)
