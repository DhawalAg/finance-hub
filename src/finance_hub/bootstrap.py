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
        return

    if provider_name is None or provider_name == "yfinance":
        def _build_yfinance() -> object:
            from finance_hub.market_data.yfinance_provider import YFinanceProvider
            return YFinanceProvider()

        factories.set_price_provider_factory(_build_yfinance)
    else:
        raise ValueError(
            f"Unknown FINANCE_HUB_PRICE_PROVIDER={provider_name!r}. "
            "Known values: 'yfinance', 'none'."
        )
