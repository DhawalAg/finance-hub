"""L2 metrics evidence pack (Slice 5).

The v1 metrics pack computed *our way* from stored daily bars (``adj_close``),
so candidate eligibility can cite grounded metrics rather than a model's
freehand guess. The pieces:

- **Pure metric math** — windowed returns, realized (annualized) volatility,
  max / current drawdown, and 52-week-position context — operates on a plain
  price series and owns the bulk of the test surface (no DB, no clock).
- **Benchmark context** defaults to ``SPY`` (overridable per plan via
  ``benchmark_ticker``); every benchmark-derived value carries the benchmark
  ticker so a relative metric is always attributable.
- **Storage** appends to ``fin_metrics`` keyed by ``as_of`` — the metric itself
  forms an analyzable series, so recomputing a later trading day adds rows
  rather than overwriting history. Each value carries the graded-provenance
  envelope (``source`` / ``grade``); price-derived metrics are ``screening``.

A metric we cannot compute (too little history, a degenerate flat range, a zero
divisor) is *omitted* — never stored as a bogus zero. Absence is reported as
absence, mirroring the prices/fundamentals slices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, NamedTuple, Optional, Sequence

from finance_hub.envelope import SCREENING, Envelope

PRICE_SCALE = 1_000_000  # micro-dollars per dollar (matches fin_price_bars)

# Default benchmark for relative context (one benchmark per plan in v1).
DEFAULT_BENCHMARK = "SPY"

# Trading days per year — the annualization factor for realized volatility.
TRADING_DAYS_PER_YEAR = 252

# Calendar-day lookbacks per return window. Calendar days (not a bar count) so
# the "as-of" lookup is robust to weekend/holiday gaps in the series.
WINDOW_DAYS = {"1m": 30, "3m": 91, "6m": 182, "1y": 365}
RETURN_WINDOWS = ("1m", "3m", "6m", "1y")

# The risk/position metrics are computed over ~1 year of daily history.
RISK_WINDOW = "1y"
RISK_WINDOW_DAYS = 365

# --- metric vocabulary ---------------------------------------------------

RET = "ret"
RET_VS_BENCHMARK = "ret_vs_benchmark"
VOL = "vol"
MAX_DRAWDOWN = "max_drawdown"
CURRENT_DRAWDOWN = "current_drawdown"
POS_52W = "pos_52w"

# --- scope vocabulary ----------------------------------------------------

TICKER = "ticker"
SLEEVE = "sleeve"
PORTFOLIO = "portfolio"


class PricePoint(NamedTuple):
    """One dated price in a series (``price`` is a plain dollar float)."""

    session_date: date
    price: float


@dataclass(frozen=True)
class MetricValue:
    """One computed metric with its graded-provenance envelope.

    ``benchmark_ticker`` is set only for benchmark-derived values (relative
    returns); it is ``None`` for absolute, single-instrument metrics.
    """

    scope: str
    key: str
    metric: str
    window: str
    envelope: Envelope
    benchmark_ticker: Optional[str] = None

    @property
    def value(self) -> float:
        return self.envelope.value

    @property
    def source(self) -> str:
        return self.envelope.source

    @property
    def grade(self) -> str:
        return self.envelope.grade

    @property
    def as_of(self) -> str:
        return self.envelope.as_of


# --- series helpers ------------------------------------------------------


def _sorted(series: Iterable[PricePoint]) -> list[PricePoint]:
    return sorted(series, key=lambda p: p.session_date)


def _as_of_point(series: Sequence[PricePoint], as_of: date) -> Optional[PricePoint]:
    """The latest point on or before ``as_of`` (the anchor for returns)."""
    prior = [p for p in series if p.session_date <= as_of]
    return prior[-1] if prior else None


def _window_points(series: Sequence[PricePoint], as_of: date, window_days: int) -> list[PricePoint]:
    start = as_of - timedelta(days=window_days)
    return [p for p in series if start <= p.session_date <= as_of]


# --- pure metric math ----------------------------------------------------


def simple_return(series: Iterable[PricePoint], as_of: date, lookback_days: int) -> Optional[float]:
    """Simple return from the price ``lookback_days`` ago to the ``as_of`` price.

    The past anchor is the latest bar on or before ``as_of - lookback_days``.
    Returns ``None`` when the series does not reach back that far (an explicit
    history gap) or the past price is zero — never a fabricated zero.
    """
    pts = _sorted(series)
    anchor = _as_of_point(pts, as_of)
    if anchor is None:
        return None
    target = as_of - timedelta(days=lookback_days)
    past = [p for p in pts if p.session_date <= target]
    if not past:
        return None
    past_price = past[-1].price
    if past_price == 0:
        return None
    return anchor.price / past_price - 1.0


def daily_returns(series: Sequence[PricePoint]) -> list[float]:
    """Consecutive-bar simple returns (a zero prior price is skipped)."""
    out: list[float] = []
    for prev, cur in zip(series, series[1:]):
        if prev.price == 0:
            continue
        out.append(cur.price / prev.price - 1.0)
    return out


def realized_volatility(
    series: Iterable[PricePoint],
    *,
    as_of: Optional[date] = None,
    window_days: Optional[int] = None,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> Optional[float]:
    """Annualized realized volatility: sample stdev of daily returns × √N.

    Optionally restricted to a trailing window (``as_of`` + ``window_days``).
    Needs at least two daily returns; otherwise ``None``.
    """
    pts = _sorted(series)
    if window_days is not None and as_of is not None:
        pts = _window_points(pts, as_of, window_days)
    rets = daily_returns(pts)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(variance) * math.sqrt(trading_days)


def max_drawdown(series: Iterable[PricePoint]) -> Optional[float]:
    """Largest peak-to-trough decline over the series (a non-positive float)."""
    pts = _sorted(series)
    if not pts:
        return None
    peak = pts[0].price
    worst = 0.0
    for p in pts:
        if p.price > peak:
            peak = p.price
        if peak > 0:
            dd = p.price / peak - 1.0
            if dd < worst:
                worst = dd
    return worst


def current_drawdown(series: Iterable[PricePoint]) -> Optional[float]:
    """Latest price vs the running peak (a non-positive float; 0 at a high)."""
    pts = _sorted(series)
    if not pts:
        return None
    peak = max(p.price for p in pts)
    if peak <= 0:
        return None
    return pts[-1].price / peak - 1.0


def position_52w(
    series: Iterable[PricePoint],
    as_of: date,
    *,
    window_days: int = RISK_WINDOW_DAYS,
) -> Optional[float]:
    """Where the latest price sits in its 52-week high-low range, in ``[0, 1]``.

    ``0`` = at the window low, ``1`` = at the window high. A degenerate flat
    window (high == low) has no range and returns ``None`` rather than a
    misleading midpoint.
    """
    pts = _window_points(_sorted(series), as_of, window_days)
    if not pts:
        return None
    high = max(p.price for p in pts)
    low = min(p.price for p in pts)
    if high == low:
        return None
    return (pts[-1].price - low) / (high - low)


# --- evidence-pack assembly ----------------------------------------------


def _metric(scope: str, key: str, metric: str, window: str, value: Optional[float],
            *, source: str, as_of: str, benchmark_ticker: Optional[str] = None
            ) -> Optional[MetricValue]:
    if value is None:
        return None
    env = Envelope(value=value, source=source, grade=SCREENING, as_of=as_of)
    return MetricValue(scope=scope, key=key, metric=metric, window=window,
                       envelope=env, benchmark_ticker=benchmark_ticker)


def compute_ticker_metrics(
    series: Iterable[PricePoint],
    *,
    ticker: str,
    as_of: date,
    source: str,
    benchmark_series: Optional[Iterable[PricePoint]] = None,
    benchmark_ticker: Optional[str] = None,
) -> list[MetricValue]:
    """Compute the v1 evidence pack for one ticker from its ``adj_close`` series.

    Produces windowed returns (1m/3m/6m/1y), annualized realized volatility,
    max/current drawdown, and 52-week position. When a ``benchmark_series`` is
    supplied, benchmark-relative returns are added, each carrying
    ``benchmark_ticker`` (defaulting to ``SPY``). Metrics that cannot be
    computed from the available history are omitted, not zero-filled.
    """
    pts = _sorted(series)
    as_of_str = as_of.isoformat()
    out: list[Optional[MetricValue]] = []

    ticker_rets: dict[str, Optional[float]] = {}
    for window in RETURN_WINDOWS:
        r = simple_return(pts, as_of, WINDOW_DAYS[window])
        ticker_rets[window] = r
        out.append(_metric(TICKER, ticker, RET, window, r, source=source, as_of=as_of_str))

    out.append(_metric(
        TICKER, ticker, VOL, RISK_WINDOW,
        realized_volatility(pts, as_of=as_of, window_days=RISK_WINDOW_DAYS),
        source=source, as_of=as_of_str,
    ))
    out.append(_metric(
        TICKER, ticker, MAX_DRAWDOWN, RISK_WINDOW,
        max_drawdown(_window_points(pts, as_of, RISK_WINDOW_DAYS)),
        source=source, as_of=as_of_str,
    ))
    out.append(_metric(
        TICKER, ticker, CURRENT_DRAWDOWN, RISK_WINDOW,
        current_drawdown(_window_points(pts, as_of, RISK_WINDOW_DAYS)),
        source=source, as_of=as_of_str,
    ))
    out.append(_metric(
        TICKER, ticker, POS_52W, RISK_WINDOW,
        position_52w(pts, as_of),
        source=source, as_of=as_of_str,
    ))

    if benchmark_series is not None:
        bench_ticker = benchmark_ticker or DEFAULT_BENCHMARK
        bench_pts = _sorted(benchmark_series)
        for window in RETURN_WINDOWS:
            tr = ticker_rets[window]
            br = simple_return(bench_pts, as_of, WINDOW_DAYS[window])
            rel = None if (tr is None or br is None) else tr - br
            out.append(_metric(
                TICKER, ticker, RET_VS_BENCHMARK, window, rel,
                source=source, as_of=as_of_str, benchmark_ticker=bench_ticker,
            ))

    return [m for m in out if m is not None]


# --- bars → series -------------------------------------------------------


def series_from_bars(conn, ticker: str, source: str, as_of: date) -> list[PricePoint]:
    """Load the ``adj_close`` series for a ticker from ``fin_price_bars``.

    Falls back to ``close_micros`` when a bar's ``adj_close`` is null (a bar is
    never dropped for a missing adjustment). Bars after ``as_of`` are excluded
    so a metric only sees information available on its trading day.
    """
    rows = conn.execute(
        """
        SELECT session_date, adj_close_micros, close_micros
        FROM fin_price_bars
        WHERE ticker = ? AND source = ? AND session_date <= ?
        ORDER BY session_date
        """,
        (ticker, source, as_of.isoformat()),
    ).fetchall()
    out: list[PricePoint] = []
    for row in rows:
        micros = row["adj_close_micros"]
        if micros is None:
            micros = row["close_micros"]
        out.append(PricePoint(date.fromisoformat(row["session_date"]), micros / PRICE_SCALE))
    return out


# --- storage -------------------------------------------------------------


def store_metrics(conn, metrics: Iterable[MetricValue]) -> int:
    """Append metric rows into ``fin_metrics``; returns the row count written.

    Append-by-``as_of``: a different ``as_of`` lands a new row (history is never
    overwritten), while recomputing the *same* trading day refreshes the value
    in place so a re-run stays idempotent.
    """
    n = 0
    for m in metrics:
        conn.execute(
            """
            INSERT INTO fin_metrics
                (scope, key, metric, window, as_of, value, source, grade, benchmark_ticker)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (scope, key, metric, window, as_of) DO UPDATE SET
                value            = excluded.value,
                source           = excluded.source,
                grade            = excluded.grade,
                benchmark_ticker = excluded.benchmark_ticker
            """,
            (m.scope, m.key, m.metric, m.window, m.envelope.as_of,
             m.envelope.value, m.envelope.source, m.envelope.grade, m.benchmark_ticker),
        )
        n += 1
    conn.commit()
    return n
