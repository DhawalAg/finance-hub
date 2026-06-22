"""Provider and clock factory — the testability seam.

Capabilities resolve their providers (and the current ``now``) through
this module so tests can inject fakes without monkey-patching network
clients or the system clock. Production wiring registers real adapters
once at startup (selected by config/param); tests call ``set_*`` /
``reset()`` per case.

Protocol shapes are intentionally informal here (duck-typed). The
contracts live in the slices that own them:

- ``PriceProvider.fetch_daily_bars(tickers, *, start=None, end=None)``
  returns ``DailyBarEnvelope`` rows (market-data slice).
- ``FundamentalsProvider.fetch_fundamentals(ticker)`` returns a
  graded-provenance ``Envelope`` (market-data slice).
- ``Clock.now()`` returns a timezone-aware ``datetime``.

Convention: planning/validation helpers receive ``now`` / ``as_of``
explicitly. They never read the clock inside their bodies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


_price_provider: Optional[Any] = None
_fundamentals_provider: Optional[Any] = None
_clock: Clock = _SystemClock()


def set_price_provider(provider: Any) -> None:
    global _price_provider
    _price_provider = provider


def set_fundamentals_provider(provider: Any) -> None:
    global _fundamentals_provider
    _fundamentals_provider = provider


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def get_price_provider() -> Any:
    if _price_provider is None:
        raise LookupError(
            "no PriceProvider configured; call factories.set_price_provider(...) "
            "or wire the real adapter at startup"
        )
    return _price_provider


def get_fundamentals_provider() -> Any:
    if _fundamentals_provider is None:
        raise LookupError(
            "no FundamentalsProvider configured; call "
            "factories.set_fundamentals_provider(...) or wire the real adapter at startup"
        )
    return _fundamentals_provider


def get_clock() -> Clock:
    return _clock


def reset() -> None:
    """Clear injected providers and restore the system clock."""
    global _price_provider, _fundamentals_provider, _clock
    _price_provider = None
    _fundamentals_provider = None
    _clock = _SystemClock()
