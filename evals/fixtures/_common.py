"""Shared seeding infrastructure for eval fixture builders (R2-R12).

Provides:
  seed_context()  — context manager that saves/restores all process-global
                    state touched during fixture seeding (DB path, workspace
                    env, memo root, clock, price provider).
  _FixedProvider  — canned price-bar provider for snapshot() seeding.
  daily_bars()    — generates N consecutive daily bars ending on a given date.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
_CSV_SOURCE = _REPO_ROOT / "tests" / "fixtures" / "fidelity_positions_sample.csv"


class _FixedClock:
    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


@dataclass
class _FixedProvider:
    """Returns canned price bars; no network calls."""

    bars_by_ticker: dict
    source: str = "yfinance"

    def fetch_daily_bars(self, tickers, *, start=None, end=None):
        out = []
        for t in tickers:
            out.extend(self.bars_by_ticker.get(t, []))
        return out


def _make_bar(ticker: str, session_date: str, close_micros: int, now_str: str) -> Any:
    from finance_hub.market_data.tools import DailyBarEnvelope
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
        source="yfinance",
        first_fetched_at=now_str,
        last_refreshed_at=now_str,
    )


def daily_bars(
    ticker: str,
    close_micros: int,
    now_str: str,
    end_date: date,
    days: int = 60,
) -> list:
    """Generate `days` consecutive daily bars ending on end_date."""
    result = []
    for i in range(days - 1, -1, -1):
        d = (end_date - timedelta(days=i)).isoformat()
        result.append(_make_bar(ticker, d, close_micros, now_str))
    return result


@contextmanager
def seed_context(
    db_path: Path,
    workspace: Path,
    clock: datetime,
    price_provider: Optional[Any] = None,
):
    """Save/restore all globals; set up db_path + workspace for seeding.

    Inside the context:
      - connection.DB_PATH  → db_path
      - os.environ FINANCE_HUB_WORKSPACE → str(workspace)
      - memo.WORKSPACE_ROOT → workspace
      - factories clock     → _FixedClock(clock)
      - factories provider  → price_provider (if given)
    All state is restored on exit whether or not the body raises.
    """
    from finance_hub.store import connection
    from finance_hub.strategy import memo
    from finance_hub import factories

    old_db_path = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    old_ws_env = os.environ.get("FINANCE_HUB_WORKSPACE")
    old_memo_root = memo.WORKSPACE_ROOT
    old_clock = factories._clock
    old_provider = factories._price_provider
    old_factory = factories._price_provider_factory

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    os.environ["FINANCE_HUB_WORKSPACE"] = str(workspace)
    memo.WORKSPACE_ROOT = workspace
    factories.set_clock(_FixedClock(clock))
    if price_provider is not None:
        factories.set_price_provider(price_provider)

    try:
        yield
    finally:
        connection.DB_PATH = old_db_path
        connection._migrated_paths = set(old_migrated)
        if old_ws_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_ws_env
        memo.WORKSPACE_ROOT = old_memo_root
        factories._clock = old_clock
        factories._price_provider = old_provider
        factories._price_provider_factory = old_factory
