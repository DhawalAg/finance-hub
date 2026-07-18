"""yfinance ``PriceProvider`` adapter (L0 ingestion).

The free first-choice price implementation (acquisition spec §2). It pulls
daily bars with ``interval="1d"`` and ``auto_adjust=False`` so the adapter
sees both the raw, unadjusted ``Close`` (the planner/valuation anchor) and
the vendor-adjusted ``Adj Close`` (the return-math field), then normalizes
them into ``DailyBarEnvelope`` rows. Swapping to Polygon / Massive later is
a new adapter registered through ``factories`` — no consumer change.

Provider floats never reach storage: every price is parsed through
``Decimal`` into integer micro-dollars. The actual network client is
injected (``downloader``) so the normalization contract is testable from a
recorded fixture without a network round-trip.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from finance_hub.market_data.tools import PRICE_SCALE, DailyBarEnvelope

SOURCE = "yfinance"

_FIELDS = ("Open", "High", "Low", "Close", "Adj Close", "Volume")


def _price_to_micros(value: Any) -> Optional[int]:
    """Parse a provider price through ``Decimal`` into integer micro-dollars.

    Goes via ``str`` first so we never inherit a float's binary noise, and
    rounds half-up to the micro. Returns ``None`` for missing values.
    """
    if value is None:
        return None
    dec = Decimal(str(value))
    if dec.is_nan():
        return None
    return int((dec * PRICE_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


def _to_volume(value: Any) -> Optional[int]:
    if value is None:
        return None
    dec = Decimal(str(value))
    if dec.is_nan():
        return None
    return int(dec)


def _ticker_frame(df, ticker: str):
    """Return the per-ticker sub-frame (handles flat or MultiIndex columns)."""
    columns = df.columns
    if getattr(columns, "nlevels", 1) > 1:
        # yfinance returns (field, ticker) columns; the ticker can sit in
        # either level depending on group_by — pick whichever level has it.
        for level in range(columns.nlevels):
            if ticker in columns.get_level_values(level):
                return df.xs(ticker, axis=1, level=level)
        return None
    return df


def _normalize_frame(df, ticker: str, *, now_iso: str) -> list[DailyBarEnvelope]:
    sub = _ticker_frame(df, ticker)
    if sub is None or len(sub) == 0:
        return []
    bars: list[DailyBarEnvelope] = []
    for index, row in sub.iterrows():
        close_micros = _price_to_micros(row.get("Close"))
        if close_micros is None:
            continue  # no settled close → not a usable bar
        session = index.date() if hasattr(index, "date") else index
        session_date = session.isoformat() if isinstance(session, date) else str(session)
        bars.append(
            DailyBarEnvelope(
                ticker=ticker,
                session_date=session_date,
                open_micros=_price_to_micros(row.get("Open")),
                high_micros=_price_to_micros(row.get("High")),
                low_micros=_price_to_micros(row.get("Low")),
                close_micros=close_micros,
                adj_close_micros=_price_to_micros(row.get("Adj Close")),
                volume=_to_volume(row.get("Volume")),
                currency="USD",
                source=SOURCE,
                first_fetched_at=now_iso,
                last_refreshed_at=now_iso,
            )
        )
    return bars


class YFinanceProvider:
    """Normalizes yfinance daily bars into ``DailyBarEnvelope`` rows."""

    source = SOURCE

    def __init__(
        self,
        *,
        downloader: Optional[Callable[..., Any]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._downloader = downloader
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _download(self, tickers, start, end):
        if self._downloader is not None:
            return self._downloader(tickers, start=start, end=end)
        import yfinance as yf  # imported lazily; optional 'market-data' extra

        return yf.download(
            list(tickers),
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

    def fetch_daily_bars(self, tickers, *, start=None, end=None) -> list[DailyBarEnvelope]:
        df = self._download(tickers, start, end)
        now_iso = self._now().isoformat()
        out: list[DailyBarEnvelope] = []
        for ticker in tickers:
            out.extend(_normalize_frame(df, ticker, now_iso=now_iso))
        return out
