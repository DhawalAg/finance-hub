"""Market-data consumer seam: ``finance.prices(...)``.

Slice 3 / acquisition Slice 1 (A) — PRD #1, issue #5. The planner and
research layers read grounded daily prices through this module, never a
vendor API or a bare scalar. The shape of the contract:

- ``PriceProvider.fetch_daily_bars(tickers, *, start=None, end=None)`` is
  the L0 ingestion seam (a yfinance adapter ships in
  ``yfinance_provider``); it returns ``DailyBarEnvelope`` rows that this
  module persists into ``fin_price_bars``.
- ``finance.prices(...)`` is the L1 consumer seam; it returns a
  ``PriceEnvelope`` per ticker derived from the stored bars.

Behaviour pinned by the acquisition spec (§2, §7):

- Cache within ``max_age_minutes`` (default ``1440`` = 1 day). A bar whose
  ``last_refreshed_at`` is within the window is served without a provider
  round-trip.
- A manual ``price_overrides`` entry short-circuits the provider and is
  *never* written into the canonical provider series.
- Interactive misses fail loud, naming the missing tickers.
- Non-USD listings (suffixes ``.L``, ``.TO``, ``.HK``, ...) are rejected.
- ~1y of daily history is fetched when available; a newer ticker / IPO
  with a short window records an explicit history-availability waiver.
- Money is integer micro-dollars parsed via ``Decimal`` (never a float).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from finance_hub import factories, money
from finance_hub.store import connection

PRICE_SCALE = 1_000_000
DEFAULT_MAX_AGE_MINUTES = 1440
HISTORY_WINDOW_DAYS = 365
# A returned series whose earliest bar lands within this many days of the
# requested 1y start counts as "full history"; anything shorter records a
# waiver (new tickers / IPOs / freshly listed ETFs).
HISTORY_GAP_TOLERANCE_DAYS = 14

# yfinance-style exchange suffixes that denote non-USD listings. US class
# shares also carry a dot (BRK.B, BF.B) but are USD-listed, so we reject by
# an explicit foreign-exchange blocklist rather than "has a dot".
_NON_USD_SUFFIXES = frozenset(
    {
        "L", "TO", "V", "NE", "CN",          # London, Toronto, TSXV, NEO, CSE
        "HK", "SS", "SZ", "T", "TW", "TWO",  # Hong Kong, Shanghai, Shenzhen, Tokyo, Taiwan
        "KS", "KQ", "SI", "KL", "JK", "BK",  # Korea, Singapore, Malaysia, Jakarta, Bangkok
        "NS", "BO", "AX", "NZ",              # India (NSE/BSE), Australia, New Zealand
        "PA", "DE", "F", "AS", "BR", "MI",   # Paris, Xetra, Frankfurt, Amsterdam, Brussels, Milan
        "MC", "MA", "SW", "ST", "OL", "HE",  # Madrid, Spain, Swiss, Stockholm, Oslo, Helsinki
        "CO", "VI", "LS", "IR", "AT",        # Copenhagen, Vienna, Lisbon, Ireland, Athens
        "SA", "MX", "BA", "SN",              # Sao Paulo, Mexico, Buenos Aires, Santiago
        "JO", "TA", "SR", "QA", "KW",        # Johannesburg, Tel Aviv, Saudi, Qatar, Kuwait
    }
)


class UnsupportedTickerError(ValueError):
    """Raised for a non-USD listing we cannot price in v1 (USD-only)."""


class PriceFetchError(RuntimeError):
    """Raised when interactive pricing cannot source one or more tickers."""

    def __init__(self, missing_tickers):
        self.missing_tickers = tuple(missing_tickers)
        joined = ", ".join(self.missing_tickers)
        super().__init__(f"could not source a price for: {joined}")


@dataclass(frozen=True)
class DailyBarEnvelope:
    """A normalized daily bar as produced by a ``PriceProvider`` adapter."""

    ticker: str
    session_date: str
    open_micros: Optional[int]
    high_micros: Optional[int]
    low_micros: Optional[int]
    close_micros: int
    adj_close_micros: Optional[int]
    volume: Optional[int]
    currency: str
    source: str
    first_fetched_at: str
    last_refreshed_at: str


@dataclass(frozen=True)
class FetchOutcome:
    """One per-ticker result of a snapshot fetch (the trip-wire record).

    ``status`` is ``"ok"`` (bars stored), ``"empty"`` (provider sourced no
    bars), or ``"error"`` (the fetch raised or the ticker was rejected).
    Both ``empty`` and ``error`` log ``ok=0`` to ``fin_fetch_log``; the
    distinction is kept here so a caller can tell a degraded provider from a
    delisted/unsupported ticker.
    """

    ticker: str
    status: str
    bars_written: int
    error: Optional[str]


@dataclass(frozen=True)
class SnapshotResult:
    """Summary of a ``snapshot()`` run over a universe of tickers."""

    as_of: str
    source: str
    outcomes: tuple[FetchOutcome, ...]

    @property
    def ok(self) -> tuple[FetchOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "ok")

    @property
    def failures(self) -> tuple[FetchOutcome, ...]:
        """Non-success outcomes (``empty`` + ``error``) — the trip-wire set."""
        return tuple(o for o in self.outcomes if o.status != "ok")

    @property
    def failure_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return len(self.failures) / len(self.outcomes)


@dataclass(frozen=True)
class PriceEnvelope:
    """Consumer-sized projection of a stored bar (never a bare scalar)."""

    ticker: str
    value_micros: int
    currency: str
    price_field: str
    session_date: str
    source: str
    grade: str
    last_refreshed_at: str
    is_override: bool
    stale: bool
    history_waiver: bool


def _validate_ticker(ticker: str) -> None:
    if "." in ticker:
        suffix = ticker.rsplit(".", 1)[1].upper()
        if suffix in _NON_USD_SUFFIXES:
            raise UnsupportedTickerError(
                f"{ticker!r} is a non-USD listing (exchange suffix '.{suffix}'); "
                "finance-hub v1 prices USD listings only"
            )


def _parse_instant(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z'."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _age_minutes(last_refreshed_at: str, now: datetime) -> float:
    refreshed = _parse_instant(last_refreshed_at)
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=timezone.utc)
    return (now - refreshed).total_seconds() / 60.0


def _latest_bar(conn, ticker: str, source: str, as_of: date):
    return conn.execute(
        """
        SELECT * FROM fin_price_bars
        WHERE ticker = ? AND source = ? AND session_date <= ?
        ORDER BY session_date DESC LIMIT 1
        """,
        (ticker, source, as_of.isoformat()),
    ).fetchone()


def _earliest_session(conn, ticker: str, source: str, as_of: date) -> Optional[str]:
    row = conn.execute(
        """
        SELECT MIN(session_date) AS earliest FROM fin_price_bars
        WHERE ticker = ? AND source = ? AND session_date <= ?
        """,
        (ticker, source, as_of.isoformat()),
    ).fetchone()
    return row["earliest"] if row else None


def _persist_bars(conn, bars) -> None:
    """Idempotent upsert on ``(ticker, session_date, source)``.

    A same-key re-fetch is a no-op for ``close`` (the immutable session
    fact) and only refreshes the back-adjustable fields + timestamp.
    ``first_fetched_at`` is preserved from the original insert.
    """
    for bar in bars:
        conn.execute(
            """
            INSERT INTO fin_price_bars
                (ticker, session_date, open_micros, high_micros, low_micros,
                 close_micros, adj_close_micros, volume, currency, source,
                 first_fetched_at, last_refreshed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, session_date, source) DO UPDATE SET
                open_micros       = excluded.open_micros,
                high_micros       = excluded.high_micros,
                low_micros        = excluded.low_micros,
                close_micros      = excluded.close_micros,
                adj_close_micros  = excluded.adj_close_micros,
                volume            = excluded.volume,
                last_refreshed_at = excluded.last_refreshed_at
            """,
            (
                bar.ticker, bar.session_date, bar.open_micros, bar.high_micros,
                bar.low_micros, bar.close_micros, bar.adj_close_micros, bar.volume,
                bar.currency, bar.source, bar.first_fetched_at, bar.last_refreshed_at,
            ),
        )


def _history_waiver(conn, ticker: str, source: str, as_of: date) -> bool:
    """True when the local series falls short of ~1y of history."""
    earliest = _earliest_session(conn, ticker, source, as_of)
    if earliest is None:
        return True
    start = as_of - timedelta(days=HISTORY_WINDOW_DAYS)
    gap = (date.fromisoformat(earliest) - start).days
    return gap > HISTORY_GAP_TOLERANCE_DAYS


def _bar_to_envelope(conn, row, *, source: str, price_field: str, as_of: date,
                     now: datetime, max_age_minutes: int) -> PriceEnvelope:
    value_micros = row["adj_close_micros"] if price_field == "adj_close" else row["close_micros"]
    if value_micros is None:
        value_micros = row["close_micros"]
    stale = _age_minutes(row["last_refreshed_at"], now) > max_age_minutes
    return PriceEnvelope(
        ticker=row["ticker"],
        value_micros=value_micros,
        currency=row["currency"],
        price_field=price_field,
        session_date=row["session_date"],
        source=source,
        grade="screening",  # price-derived values are reliable but not primary-source
        last_refreshed_at=row["last_refreshed_at"],
        is_override=False,
        stale=stale,
        history_waiver=_history_waiver(conn, row["ticker"], source, as_of),
    )


def _override_envelope(ticker: str, raw_value: str, *, price_field: str,
                       session_date: str, now: datetime) -> PriceEnvelope:
    return PriceEnvelope(
        ticker=ticker,
        value_micros=money.to_micro_dollars(raw_value),
        currency="USD",
        price_field=price_field,
        session_date=session_date,
        source="override",
        grade="screening",
        last_refreshed_at=now.isoformat(),
        is_override=True,
        stale=False,
        history_waiver=False,
    )


def prices(
    tickers,
    *,
    as_of: Optional[date] = None,
    price_field: str = "close",
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    price_overrides: Optional[dict] = None,
) -> dict:
    """Return a ``PriceEnvelope`` per ticker.

    Cache-first: a fresh local bar (within ``max_age_minutes``) is served
    without touching the provider. Stale or absent tickers trigger a single
    provider fetch over the ~1y window, the returned bars are upserted, and
    envelopes are rebuilt from the stored series. ``price_overrides`` bypass
    the provider entirely and are not persisted. Interactive misses fail
    loud, naming the offending tickers.
    """
    if price_field not in ("close", "adj_close"):
        raise ValueError(f"price_field must be 'close' or 'adj_close', got {price_field!r}")
    overrides = dict(price_overrides or {})

    now = factories.get_clock().now()
    if as_of is None:
        as_of = now.date()

    for ticker in tickers:
        _validate_ticker(ticker)

    result: dict[str, PriceEnvelope] = {}
    to_fetch: list[str] = []

    with connection.connect() as conn:
        source = _provider_source()
        for ticker in tickers:
            if ticker in overrides:
                result[ticker] = _override_envelope(
                    ticker, overrides[ticker], price_field=price_field,
                    session_date=as_of.isoformat(), now=now,
                )
                continue
            row = _latest_bar(conn, ticker, source, as_of)
            if row is not None and _age_minutes(row["last_refreshed_at"], now) <= max_age_minutes:
                result[ticker] = _bar_to_envelope(
                    conn, row, source=source, price_field=price_field,
                    as_of=as_of, now=now, max_age_minutes=max_age_minutes,
                )
            else:
                to_fetch.append(ticker)

        if to_fetch:
            provider = factories.get_price_provider()
            start = as_of - timedelta(days=HISTORY_WINDOW_DAYS)
            bars = provider.fetch_daily_bars(tuple(to_fetch), start=start, end=as_of)
            _persist_bars(conn, bars)
            conn.commit()

            missing: list[str] = []
            for ticker in to_fetch:
                row = _latest_bar(conn, ticker, source, as_of)
                if row is None:
                    missing.append(ticker)
                    continue
                result[ticker] = _bar_to_envelope(
                    conn, row, source=source, price_field=price_field,
                    as_of=as_of, now=now, max_age_minutes=max_age_minutes,
                )
            if missing:
                raise PriceFetchError(missing)

    return result


def _log_fetch(conn, ticker: str, attempted_at: str, source: str, *,
               ok: int, error: Optional[str]) -> None:
    conn.execute(
        """
        INSERT INTO fin_fetch_log (ticker, attempted_at, source, ok, error)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticker, attempted_at, source, ok, error),
    )


def _default_universe(conn) -> list[str]:
    """Derive the snapshot universe from stored facts.

    Per the acquisition spec (D4) the first snapshot universe is *approved
    strategy sleeve instruments ∪ current holdings*. The strategy layer is
    not built yet, so this resolves to the current holdings only — the
    supported, tickered positions of the most recent immutable portfolio
    snapshot. The strategy-sleeve union folds in once that slice lands; the
    research watchlist stays on-demand (never auto-priced here).
    """
    snap = conn.execute(
        "SELECT snapshot_id FROM fin_portfolio_snapshots "
        "ORDER BY as_of DESC, created_at DESC LIMIT 1"
    ).fetchone()
    if snap is None:
        return []
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM fin_portfolio_positions "
        "WHERE snapshot_id = ? AND ticker IS NOT NULL AND is_supported = 1 "
        "ORDER BY ticker",
        (snap["snapshot_id"],),
    ).fetchall()
    return [r["ticker"] for r in rows]


def _snapshot_one(conn, provider, ticker: str, *, source: str, start: date,
                  as_of: date, attempted_at: str) -> FetchOutcome:
    """Fetch + persist one ticker, log-and-continue on any failure.

    A bad ticker (provider error, rejected listing, or an empty result)
    records ``ok=0`` to ``fin_fetch_log`` and returns a non-``ok`` outcome
    rather than aborting the surrounding batch.
    """
    try:
        _validate_ticker(ticker)
        bars = provider.fetch_daily_bars((ticker,), start=start, end=as_of)
    except Exception as exc:  # noqa: BLE001 — log-and-continue is the contract
        error_msg = str(exc)
        _log_fetch(conn, ticker, attempted_at, source, ok=0, error=error_msg)
        return FetchOutcome(ticker=ticker, status="error", bars_written=0, error=error_msg)

    if not bars:
        error_msg = "provider returned no bars"
        _log_fetch(conn, ticker, attempted_at, source, ok=0, error=error_msg)
        return FetchOutcome(ticker=ticker, status="empty", bars_written=0, error=error_msg)

    _persist_bars(conn, bars)
    _log_fetch(conn, ticker, attempted_at, source, ok=1, error=None)
    return FetchOutcome(ticker=ticker, status="ok", bars_written=len(bars), error=None)


def snapshot(
    tickers=None,
    *,
    as_of: Optional[date] = None,
) -> SnapshotResult:
    """Batch-acquire daily bars for a universe of tickers.

    Loops the universe through the ``PriceProvider`` seam (one isolated
    fetch per ticker so a single failure can't poison the batch), upserts
    the returned bars into ``fin_price_bars`` on the same write path as
    ``prices()``, and records every per-ticker outcome to ``fin_fetch_log``
    — the reliability trip-wire counter. Failures are logged and surfaced
    in the returned :class:`SnapshotResult`, never silently swallowed.

    ``tickers`` defaults to the current-holdings universe (see
    :func:`_default_universe`). Re-running is idempotent for bars (the
    ``(ticker, session_date, source)`` upsert key); ``fin_fetch_log`` is
    append-only so the trip-wire history is preserved.
    """
    now = factories.get_clock().now()
    if as_of is None:
        as_of = now.date()
    attempted_at = now.isoformat()
    provider = factories.get_price_provider()
    source = _provider_source()
    start = as_of - timedelta(days=HISTORY_WINDOW_DAYS)

    outcomes: list[FetchOutcome] = []
    with connection.connect() as conn:
        universe = list(tickers) if tickers is not None else _default_universe(conn)
        for ticker in universe:
            outcomes.append(
                _snapshot_one(
                    conn, provider, ticker, source=source, start=start,
                    as_of=as_of, attempted_at=attempted_at,
                )
            )
        conn.commit()

    return SnapshotResult(as_of=as_of.isoformat(), source=source, outcomes=tuple(outcomes))


def _provider_source() -> str:
    """The vendor key for the active series (defaults to yfinance).

    ``source`` is part of the ``fin_price_bars`` key — never mix vendors in
    one series — so cache reads must look under the same source the provider
    writes. We read it off the configured provider when present.
    """
    try:
        provider = factories.get_price_provider()
    except LookupError:
        return "yfinance"
    return getattr(provider, "source", "yfinance")
