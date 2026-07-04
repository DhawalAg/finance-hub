"""Compact fundamentals screening pack (Slice 6).

A provider-backed cache for one-time-buy eligibility, with honest grading and
honest availability. The pieces:

- **Normalizers** turn a recorded provider response (EODHD / Alpha Vantage)
  into a list of :class:`Fundamental` records, each carrying a graded-provenance
  :class:`~finance_hub.envelope.Envelope`. Aggregator data is graded
  ``screening`` — never ``decision`` — because only filing-grounded figures may
  drive a decision (see acquisition spec §2).
- **Adapters** wrap the normalizers behind the ``FundamentalsProvider`` seam and
  model the free-tier daily quota. EODHD is the default runner; when its quota
  is exhausted it raises :class:`QuotaExhausted` so a
  :class:`SpilloverFundamentalsProvider` can fall back to Alpha Vantage.
- **CSV/manual** intake is an override + bootstrap path only.
- **Storage + read** persist envelopes to ``fin_fundamentals`` and render every
  requested field as an explicit availability
  (``available | missing | stale | not_configured``) — a gap is never zero.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from finance_hub.envelope import SCREENING, Envelope

# --- field vocabulary ----------------------------------------------------

# Stocks: growth, profitability, valuation multiples, balance-sheet context,
# and the next earnings date when available.
REVENUE_GROWTH = "revenue_growth"
EARNINGS_GROWTH = "earnings_growth"
PROFITABILITY = "profitability"
OPERATING_MARGIN = "operating_margin"
RETURN_ON_EQUITY = "return_on_equity"
RETURN_ON_ASSETS = "return_on_assets"
GROSS_PROFIT = "gross_profit"
PS = "ps"
FORWARD_PS = "forward_ps"
PE = "pe_ratio"
FORWARD_PE = "forward_pe"
PEG = "peg_ratio"
PRICE_TO_BOOK = "price_to_book"
EV_EBITDA = "ev_ebitda"
EV_REVENUE = "ev_revenue"
MARKET_CAP = "market_cap"
REVENUE_TTM = "revenue_ttm"
EBITDA = "ebitda"
EPS = "eps"
BOOK_VALUE = "book_value"
SHARES_OUTSTANDING = "shares_outstanding"
DIVIDEND_YIELD = "dividend_yield"
DIVIDEND_PER_SHARE = "dividend_per_share"
EX_DIVIDEND_DATE = "ex_dividend_date"
BETA = "beta"
WEEK52_HIGH = "week52_high"
WEEK52_LOW = "week52_low"
MA_50 = "ma_50"
MA_200 = "ma_200"
ANALYST_TARGET_PRICE = "analyst_target_price"
ANALYST_RATING = "analyst_rating"
SECTOR = "sector"
INDUSTRY = "industry"
LATEST_QUARTER = "latest_quarter"
TOTAL_DEBT = "total_debt"
TOTAL_CASH = "total_cash"
NEXT_EARNINGS_DATE = "next_earnings_date"

STOCK_FIELDS = (
    # growth
    REVENUE_GROWTH, EARNINGS_GROWTH,
    # profitability / returns
    PROFITABILITY, OPERATING_MARGIN, RETURN_ON_EQUITY, RETURN_ON_ASSETS, GROSS_PROFIT,
    # valuation multiples
    PS, FORWARD_PS, PE, FORWARD_PE, PEG, PRICE_TO_BOOK, EV_EBITDA, EV_REVENUE,
    # size / scale
    MARKET_CAP, REVENUE_TTM, EBITDA, EPS, BOOK_VALUE, SHARES_OUTSTANDING,
    # dividend
    DIVIDEND_YIELD, DIVIDEND_PER_SHARE, EX_DIVIDEND_DATE,
    # risk / technical anchors
    BETA, WEEK52_HIGH, WEEK52_LOW, MA_50, MA_200,
    # analyst
    ANALYST_TARGET_PRICE, ANALYST_RATING,
    # balance-sheet context (provider-dependent; absent from AV free OVERVIEW)
    TOTAL_DEBT, TOTAL_CASH, NEXT_EARNINGS_DATE,
    # classification / context
    SECTOR, INDUSTRY, LATEST_QUARTER,
)

# ETFs: expense ratio, top holdings, sector exposure, AUM, 1y performance.
EXPENSE_RATIO = "expense_ratio"
TOP_HOLDINGS = "top_holdings"
SECTOR_EXPOSURE = "sector_exposure"
AUM = "aum"
PERF_1Y = "perf_1y"

ETF_FIELDS = (
    EXPENSE_RATIO,
    TOP_HOLDINGS,
    SECTOR_EXPOSURE,
    AUM,
    PERF_1Y,
)

# --- units ---------------------------------------------------------------

RATIO = "ratio"  # dimensionless ratio, e.g. a margin, YoY growth, yield, beta
MULTIPLE = "x"  # valuation multiple, e.g. P/S, P/E, PEG, EV/EBITDA
USD = "USD"
COUNT = "count"  # a bare count, e.g. shares outstanding
DATE = "date"
TEXT = "text"  # a categorical string, e.g. sector / industry
JSON = "json"  # structured text payload (holdings, sector weights, rating spread)

# --- availability vocabulary ---------------------------------------------

AVAILABLE = "available"
MISSING = "missing"
STALE = "stale"
NOT_CONFIGURED = "not_configured"

# A screening value older than this is reported STALE rather than AVAILABLE.
DEFAULT_MAX_AGE_DAYS = 120

# Sources that are treated as a manual override (they win over provider rows).
MANUAL_SOURCES = frozenset({"manual", "csv"})


class QuotaExhausted(Exception):
    """Raised by a provider adapter when its free-tier daily quota is spent.

    The spillover provider catches this to fall through to the next runner.
    """


@dataclass(frozen=True)
class Fundamental:
    """One normalized field with its graded-provenance envelope."""

    field: str
    envelope: Envelope
    unit: Optional[str] = None
    source_ref: Optional[str] = None

    @property
    def value(self) -> Any:
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


@dataclass(frozen=True)
class Cell:
    """A field's read-side view: an availability plus, when present, the value.

    ``envelope`` is ``None`` for ``missing`` / ``not_configured`` — the absence
    of a value is reported as absence, never coerced to zero. A ``stale`` cell
    keeps its envelope so a caller can show the value while flagging the age.
    """

    field: str
    availability: str
    envelope: Optional[Envelope] = None
    unit: Optional[str] = None

    @property
    def value(self) -> Any:
        return self.envelope.value if self.envelope is not None else None


# --- numeric coercion ----------------------------------------------------


def _to_decimal_str(value: Any) -> Optional[str]:
    """Coerce a provider scalar to a canonical decimal string, or ``None``.

    Provider floats are parsed through ``Decimal`` (never stored as floats);
    empty/``None``/sentinel values become ``None`` so the field surfaces as a
    gap rather than a bogus zero.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.upper() in {"NA", "N/A", "NONE", "-"}:
            return None
    else:
        text = repr(value) if isinstance(value, float) else str(value)
    try:
        return str(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _dig(payload: dict, *path: str) -> Any:
    cur: Any = payload
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _is_etf(general_type: Any) -> bool:
    return isinstance(general_type, str) and general_type.strip().upper() == "ETF"


# --- normalizers ---------------------------------------------------------


def _scalar(field: str, raw: Any, *, unit: str, source: str, as_of: str,
            source_ref: Optional[str] = None) -> Optional[Fundamental]:
    text = _to_decimal_str(raw)
    if text is None:
        return None
    env = Envelope(value=text, source=source, grade=SCREENING, as_of=as_of)
    return Fundamental(field=field, envelope=env, unit=unit, source_ref=source_ref)


def _structured(field: str, raw: Any, *, source: str, as_of: str) -> Optional[Fundamental]:
    if raw is None or (isinstance(raw, (dict, list)) and len(raw) == 0):
        return None
    env = Envelope(
        value=json.dumps(raw, sort_keys=True, separators=(",", ":")),
        source=source,
        grade=SCREENING,
        as_of=as_of,
    )
    return Fundamental(field=field, envelope=env, unit=JSON)


_TEXT_SENTINELS = frozenset({"", "-", "na", "n/a", "none", "null", "0000-00-00"})


def _text(field: str, raw: Any, *, unit: str, source: str, as_of: str) -> Optional[Fundamental]:
    """Normalize a categorical string or date field, skipping sentinels.

    Used for non-numeric facts (sector, industry) and date fields (ex-dividend,
    latest quarter) where ``_scalar``'s decimal coercion does not apply. A
    provider sentinel (empty, ``-``, ``None``, ``0000-00-00``) surfaces as a gap.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _TEXT_SENTINELS:
        return None
    env = Envelope(value=text, source=source, grade=SCREENING, as_of=as_of)
    return Fundamental(field=field, envelope=env, unit=unit)


def normalize_eodhd(raw: dict, *, source: str = "eodhd") -> list[Fundamental]:
    """Normalize a recorded EODHD fundamentals response into envelopes."""
    as_of = _dig(raw, "General", "UpdatedAt") or date.today().isoformat()

    out: list[Optional[Fundamental]] = []
    if _is_etf(_dig(raw, "General", "Type")):
        etf = raw.get("ETF_Data") or {}
        out += [
            _scalar(EXPENSE_RATIO, etf.get("NetExpenseRatio"), unit=RATIO,
                    source=source, as_of=as_of),
            _scalar(AUM, etf.get("TotalAssets"), unit=USD, source=source, as_of=as_of),
            _scalar(PERF_1Y, _dig(etf, "Performance", "Returns_1Y"), unit=RATIO,
                    source=source, as_of=as_of),
            _structured(TOP_HOLDINGS, etf.get("Top_10_Holdings"), source=source, as_of=as_of),
            _structured(SECTOR_EXPOSURE, etf.get("Sector_Weights"), source=source, as_of=as_of),
        ]
    else:
        highlights = raw.get("Highlights") or {}
        valuation = raw.get("Valuation") or {}
        # Most recent quarterly balance sheet entry, if present.
        quarters = _dig(raw, "Financials", "Balance_Sheet", "quarterly") or {}
        latest_bs = {}
        if isinstance(quarters, dict) and quarters:
            latest_bs = quarters[max(quarters)]
        out += [
            _scalar(REVENUE_GROWTH, highlights.get("QuarterlyRevenueGrowthYOY"),
                    unit=RATIO, source=source, as_of=as_of),
            _scalar(PROFITABILITY, highlights.get("ProfitMargin"), unit=RATIO,
                    source=source, as_of=as_of),
            _scalar(PS, highlights.get("PriceSalesTTM"), unit=MULTIPLE,
                    source=source, as_of=as_of),
            _scalar(FORWARD_PS, valuation.get("ForwardPriceSalesTTM"), unit=MULTIPLE,
                    source=source, as_of=as_of),
            _scalar(EV_EBITDA, valuation.get("EnterpriseValueEbitda"), unit=MULTIPLE,
                    source=source, as_of=as_of),
            _scalar(TOTAL_DEBT, latest_bs.get("shortLongTermDebtTotal"), unit=USD,
                    source=source, as_of=as_of),
            _scalar(TOTAL_CASH, latest_bs.get("cash"), unit=USD, source=source, as_of=as_of),
            _earnings_date(NEXT_EARNINGS_DATE, _dig(raw, "Earnings", "next_date"),
                           source=source, as_of=as_of),
        ]
    return [f for f in out if f is not None]


def normalize_alpha_vantage(raw: dict, *, source: str = "alpha_vantage") -> list[Fundamental]:
    """Normalize a recorded Alpha Vantage response into envelopes.

    Stocks use the flat ``OVERVIEW`` shape; ETFs use ``ETF_PROFILE``. Alpha
    Vantage's free OVERVIEW omits several fields EODHD carries (forward P/S,
    balance-sheet debt/cash, next earnings date); those simply do not appear,
    and surface downstream as ``missing`` rather than zero.
    """
    asset_type = raw.get("AssetType") or raw.get("asset_type")
    if _is_etf(asset_type) or "net_expense_ratio" in raw or "net_assets" in raw:
        as_of = raw.get("LatestQuarter") or date.today().isoformat()
        out = [
            _scalar(EXPENSE_RATIO, raw.get("net_expense_ratio"), unit=RATIO,
                    source=source, as_of=as_of),
            _scalar(AUM, raw.get("net_assets"), unit=USD, source=source, as_of=as_of),
            _structured(TOP_HOLDINGS, raw.get("holdings"), source=source, as_of=as_of),
            _structured(SECTOR_EXPOSURE, raw.get("sectors"), source=source, as_of=as_of),
        ]
        return [f for f in out if f is not None]

    as_of = raw.get("LatestQuarter") or date.today().isoformat()

    def num(field: str, key: str, unit: str) -> Optional[Fundamental]:
        return _scalar(field, raw.get(key), unit=unit, source=source, as_of=as_of)

    def txt(field: str, key: str, unit: str) -> Optional[Fundamental]:
        return _text(field, raw.get(key), unit=unit, source=source, as_of=as_of)

    # One OVERVIEW call carries ~55 fields; harvest the screening-relevant set so
    # each request maximizes stored evidence. Facts only — no thresholds/verdicts.
    out = [
        # growth
        num(REVENUE_GROWTH, "QuarterlyRevenueGrowthYOY", RATIO),
        num(EARNINGS_GROWTH, "QuarterlyEarningsGrowthYOY", RATIO),
        # profitability / returns
        num(PROFITABILITY, "ProfitMargin", RATIO),
        num(OPERATING_MARGIN, "OperatingMarginTTM", RATIO),
        num(RETURN_ON_EQUITY, "ReturnOnEquityTTM", RATIO),
        num(RETURN_ON_ASSETS, "ReturnOnAssetsTTM", RATIO),
        num(GROSS_PROFIT, "GrossProfitTTM", USD),
        # valuation multiples (AV OVERVIEW omits ForwardPriceToSalesTTM → gap)
        num(PS, "PriceToSalesRatioTTM", MULTIPLE),
        num(FORWARD_PS, "ForwardPriceToSalesTTM", MULTIPLE),
        num(PE, "PERatio", MULTIPLE),
        num(FORWARD_PE, "ForwardPE", MULTIPLE),
        num(PEG, "PEGRatio", MULTIPLE),
        num(PRICE_TO_BOOK, "PriceToBookRatio", MULTIPLE),
        num(EV_EBITDA, "EVToEBITDA", MULTIPLE),
        num(EV_REVENUE, "EVToRevenue", MULTIPLE),
        # size / scale
        num(MARKET_CAP, "MarketCapitalization", USD),
        num(REVENUE_TTM, "RevenueTTM", USD),
        num(EBITDA, "EBITDA", USD),
        num(EPS, "DilutedEPSTTM", USD),
        num(BOOK_VALUE, "BookValue", USD),
        num(SHARES_OUTSTANDING, "SharesOutstanding", COUNT),
        # dividend
        num(DIVIDEND_YIELD, "DividendYield", RATIO),
        num(DIVIDEND_PER_SHARE, "DividendPerShare", USD),
        txt(EX_DIVIDEND_DATE, "ExDividendDate", DATE),
        # risk / technical anchors
        num(BETA, "Beta", RATIO),
        num(WEEK52_HIGH, "52WeekHigh", USD),
        num(WEEK52_LOW, "52WeekLow", USD),
        num(MA_50, "50DayMovingAverage", USD),
        num(MA_200, "200DayMovingAverage", USD),
        # analyst
        num(ANALYST_TARGET_PRICE, "AnalystTargetPrice", USD),
        _analyst_rating(raw, source=source, as_of=as_of),
        # classification / context
        txt(SECTOR, "Sector", TEXT),
        txt(INDUSTRY, "Industry", TEXT),
        txt(LATEST_QUARTER, "LatestQuarter", DATE),
    ]
    return [f for f in out if f is not None]


def _analyst_rating(raw: dict, *, source: str, as_of: str) -> Optional[Fundamental]:
    """Fold AV's five analyst-rating counts into one structured field.

    Stored as a JSON spread of counts (strong_buy … strong_sell) — the raw
    distribution, not a derived recommendation. Returns ``None`` if AV supplied
    none of the counts.
    """
    keys = {
        "strong_buy": "AnalystRatingStrongBuy",
        "buy": "AnalystRatingBuy",
        "hold": "AnalystRatingHold",
        "sell": "AnalystRatingSell",
        "strong_sell": "AnalystRatingStrongSell",
    }
    spread = {}
    for out_key, raw_key in keys.items():
        val = _to_decimal_str(raw.get(raw_key))
        if val is not None:
            spread[out_key] = int(Decimal(val))
    return _structured(ANALYST_RATING, spread or None, source=source, as_of=as_of)


def _earnings_date(field: str, raw: Any, *, source: str, as_of: str) -> Optional[Fundamental]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    env = Envelope(value=raw.strip(), source=source, grade=SCREENING, as_of=as_of)
    return Fundamental(field=field, envelope=env, unit=DATE)


# --- provider adapters ---------------------------------------------------


@dataclass
class _RecordedAdapter:
    """Base for fixture-backed adapters with a free-tier daily quota.

    ``responses`` maps ticker -> recorded provider payload. ``daily_limit`` is
    the free-tier request budget (EODHD: 20/day); once spent the next fetch
    raises :class:`QuotaExhausted` instead of returning data.
    """

    responses: dict[str, dict]
    source: str = ""
    daily_limit: Optional[int] = None
    _calls: int = 0

    def _normalize(self, raw: dict) -> list[Fundamental]:  # pragma: no cover
        raise NotImplementedError

    def fetch_fundamentals(self, ticker: str) -> list[Fundamental]:
        if self.daily_limit is not None and self._calls >= self.daily_limit:
            raise QuotaExhausted(f"{self.source} daily free-tier quota exhausted")
        self._calls += 1
        raw = self.responses.get(ticker)
        if raw is None:
            return []
        return self._normalize(raw)


@dataclass
class EODHDAdapter(_RecordedAdapter):
    """Default free fundamentals runner (EODHD, 20 requests/day free tier)."""

    source: str = "eodhd"

    def _normalize(self, raw: dict) -> list[Fundamental]:
        return normalize_eodhd(raw, source=self.source)


@dataclass
class AlphaVantageAdapter(_RecordedAdapter):
    """Spillover fundamentals runner once EODHD's free tier is exhausted."""

    source: str = "alpha_vantage"

    def _normalize(self, raw: dict) -> list[Fundamental]:
        return normalize_alpha_vantage(raw, source=self.source)


@dataclass
class SpilloverFundamentalsProvider:
    """Try the primary runner; fall back to the next on :class:`QuotaExhausted`."""

    primary: Any
    fallback: Any

    def fetch_fundamentals(self, ticker: str) -> list[Fundamental]:
        try:
            return self.primary.fetch_fundamentals(ticker)
        except QuotaExhausted:
            return self.fallback.fetch_fundamentals(ticker)


# --- CSV / manual override path ------------------------------------------


def parse_csv_overrides(text: str) -> list[tuple[str, Fundamental]]:
    """Parse a CSV override/bootstrap sheet into ``(ticker, Fundamental)`` pairs.

    Columns: ``ticker,field,value,unit,as_of`` plus optional ``grade``,
    ``source``, ``source_ref``. ``grade`` defaults to ``screening``; a manual
    sheet may assert ``decision`` only when the value is filing-grounded, so the
    column is honored but not assumed.
    """
    out: list[tuple[str, Fundamental]] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        ticker = (row.get("ticker") or "").strip()
        field = (row.get("field") or "").strip()
        value = (row.get("value") or "").strip()
        if not ticker or not field or value == "":
            continue
        grade = (row.get("grade") or SCREENING).strip() or SCREENING
        source = (row.get("source") or "manual").strip() or "manual"
        env = Envelope(value=value, source=source, grade=grade,
                       as_of=(row.get("as_of") or "").strip())
        out.append((ticker, Fundamental(
            field=field,
            envelope=env,
            unit=(row.get("unit") or None) or None,
            source_ref=(row.get("source_ref") or None) or None,
        )))
    return out


# --- storage -------------------------------------------------------------


def store_fundamentals(conn, ticker: str, fundamentals: Iterable[Fundamental],
                       *, fetched_at: str) -> int:
    """Upsert envelopes into ``fin_fundamentals``. Idempotent on the PK.

    Returns the number of rows written. Re-running a fetch for the same
    ``(ticker, field, as_of, source)`` refreshes the value in place rather than
    duplicating it.
    """
    n = 0
    for f in fundamentals:
        value = f.envelope.value
        text = value if isinstance(value, str) else json.dumps(value)
        conn.execute(
            """
            INSERT INTO fin_fundamentals
                (ticker, field, as_of, value, unit, source, grade, fetched_at, source_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, field, as_of, source) DO UPDATE SET
                value      = excluded.value,
                unit       = excluded.unit,
                grade      = excluded.grade,
                fetched_at = excluded.fetched_at,
                source_ref = excluded.source_ref
            """,
            (ticker, f.field, f.envelope.as_of, text, f.unit, f.envelope.source,
             f.envelope.grade, fetched_at, f.source_ref),
        )
        n += 1
    conn.commit()
    return n


def _row_rank(row) -> tuple:
    """Sort key for picking the row that wins for a field.

    A manual override wins over a provider row; among the rest the freshest
    ``as_of`` wins, then decision over screening. Higher tuple sorts later, so
    we pick ``max``.
    """
    is_manual = 1 if row["source"] in MANUAL_SOURCES else 0
    grade_rank = 1 if row["grade"] == "decision" else 0
    return (is_manual, row["as_of"], grade_rank)


def _latest_row(conn, ticker: str, field: str):
    rows = conn.execute(
        "SELECT * FROM fin_fundamentals WHERE ticker = ? AND field = ?",
        (ticker, field),
    ).fetchall()
    if not rows:
        return None
    return max(rows, key=_row_rank)


def _days_between(as_of: str, now: date) -> Optional[int]:
    try:
        d = date.fromisoformat(as_of[:10])
    except ValueError:
        return None
    return (now - d).days


def screen_fundamentals(conn, ticker: str, fields: Iterable[str], *, now: date,
                        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                        configured: bool = True) -> dict[str, Cell]:
    """Render each requested field as an explicit availability.

    ``available`` — a fresh stored value; ``stale`` — a stored value older than
    ``max_age_days`` (envelope kept); ``missing`` — the provider was queried but
    did not supply this field; ``not_configured`` — no provider is wired and no
    value is stored. A gap is never reported as a value.
    """
    cells: dict[str, Cell] = {}
    for field in fields:
        row = _latest_row(conn, ticker, field)
        if row is None:
            availability = MISSING if configured else NOT_CONFIGURED
            cells[field] = Cell(field=field, availability=availability)
            continue
        env = Envelope(value=row["value"], source=row["source"],
                       grade=row["grade"], as_of=row["as_of"])
        age = _days_between(row["as_of"], now)
        if age is not None and age > max_age_days:
            cells[field] = Cell(field=field, availability=STALE, envelope=env, unit=row["unit"])
        else:
            cells[field] = Cell(field=field, availability=AVAILABLE, envelope=env, unit=row["unit"])
    return cells
