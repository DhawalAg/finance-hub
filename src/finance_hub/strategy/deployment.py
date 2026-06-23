"""Pure deployment-plan arithmetic — the deterministic draft engine core.

No DB, no clock, no provider access: the registered ``generate_deployment_plan``
wrapper loads state, calls ``compute_recommendation_lines`` here, then persists
the result. Keeping the math pure is what makes the decision matrix
(bucket splitting, min-line rollup, line caps, exclusions, unallocated
reasons, concentration warnings) testable without a database.

Money is integer micro-dollars throughout (1 USD = 1_000_000 micros) so
allocation arithmetic is exact — never float dollars. Weights for
proportioning come from sleeve target basis points (10_000 = 100%).

Ranking is **explicit factors**, never a blended score: each funded line
carries the factor values that ordered it (target underweight, research
conviction, evidence completeness, concentration headroom). ``risk_mode``
is intentionally absent from every function here — posture never touches
allocation math or gates (PRD story 51).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

# Codified warning/block codes (PRD story 80 + §68 concentration defaults).
MARKET_DATA_MISSING = "MARKET_DATA_MISSING"
UNKNOWN_SLEEVE_EXPOSURE = "UNKNOWN_SLEEVE_EXPOSURE"
SINGLE_TICKER_CONCENTRATION = "SINGLE_TICKER_CONCENTRATION"
SLEEVE_OVER_TARGET = "SLEEVE_OVER_TARGET"

_FULL_ALLOCATION_BPS = 10_000
_BUCKETS = ("dca", "one_time")


@dataclass(frozen=True)
class CandidateInput:
    """One strategy-eligible instrument, with the evidence the planner loaded."""

    ticker: str
    sleeve_key: str
    sleeve_target_bps: int
    instrument_role: Optional[str]
    conviction: Optional[int]
    hard_cap_bps: Optional[int]
    dca_eligible: bool
    one_time_eligible: bool
    has_price: bool
    current_mv_micros: int = 0
    dca_gaps: tuple[str, ...] = ()
    one_time_gaps: tuple[str, ...] = ()
    excluded: bool = False


@dataclass(frozen=True)
class PlanPolicy:
    """Effective policy snapshot used for one plan (PRD story 89)."""

    minimum_line_micros: int = 100_000_000  # $100
    max_dca_lines: int = 5
    max_one_time_lines: int = 3
    single_ticker_warn_pct: Decimal = Decimal("10")
    sleeve_over_target_pp: Decimal = Decimal("5")
    unknown_sleeve_warning_pct: Decimal = Decimal("5")
    unknown_sleeve_block_pct: Decimal = Decimal("15")

    def as_dict(self) -> dict:
        return {
            "minimum_line_amount": _micros_to_str(self.minimum_line_micros),
            "minimum_line_micros": self.minimum_line_micros,
            "max_dca_lines": self.max_dca_lines,
            "max_one_time_lines": self.max_one_time_lines,
            "single_ticker_warn_pct": str(self.single_ticker_warn_pct),
            "sleeve_over_target_pp": str(self.sleeve_over_target_pp),
            "unknown_sleeve_warning_pct": str(self.unknown_sleeve_warning_pct),
            "unknown_sleeve_block_pct": str(self.unknown_sleeve_block_pct),
        }


@dataclass
class Line:
    bucket: str
    ticker: str
    sleeve_key: str
    amount_micros: int
    rank: int
    ranked_factors: list[dict]
    rationale: Optional[str] = None
    # Assigned by the wrapper once the plan id is known.
    line_id: Optional[str] = None


@dataclass
class UnallocatedReason:
    ticker: Optional[str]
    reason: str
    amount_micros: int


@dataclass
class BucketResult:
    bucket: str
    budget_micros: int
    allocated_micros: int
    unallocated_micros: int
    lines: list[Line] = field(default_factory=list)
    unallocated_reasons: list[UnallocatedReason] = field(default_factory=list)


@dataclass
class Warning:
    code: str
    severity: str
    ticker: Optional[str]
    message: str


@dataclass
class WatchlistEntry:
    ticker: str
    reason: str
    detail: Optional[str] = None


@dataclass
class PlanComputation:
    buckets: dict[str, BucketResult]
    warnings: list[Warning]
    watchlist: list[WatchlistEntry]


def _micros_to_str(micros: int) -> str:
    return str(Decimal(micros) / 1_000_000)


def _eligible_for(candidate: CandidateInput, bucket: str) -> bool:
    ready = candidate.dca_eligible if bucket == "dca" else candidate.one_time_eligible
    return ready and candidate.has_price and not candidate.excluded


def _rank_key(c: CandidateInput, sleeve_current_bps: dict[str, int]):
    """Order candidates best-first by explicit, inspectable factors.

    Primary: sleeve target underweight (most-underweight first). Then
    higher research conviction, then ticker for a stable tie-break. No
    blended score — the same ordering is reproduced by ``_ranked_factors``.
    """
    underweight = c.sleeve_target_bps - sleeve_current_bps.get(c.sleeve_key, 0)
    conviction = c.conviction if c.conviction is not None else 0
    return (-underweight, -conviction, c.ticker)


def _ranked_factors(
    c: CandidateInput,
    bucket: str,
    sleeve_current_bps: dict[str, int],
) -> list[dict]:
    underweight_bps = c.sleeve_target_bps - sleeve_current_bps.get(c.sleeve_key, 0)
    gaps = c.dca_gaps if bucket == "dca" else c.one_time_gaps
    return [
        {
            "factor": "target_underweight",
            "detail": f"sleeve {c.sleeve_key!r} underweight by "
            f"{_bps_to_pct_str(underweight_bps)}pp",
            "value_bps": underweight_bps,
        },
        {
            "factor": "research_conviction",
            "detail": "no conviction recorded"
            if c.conviction is None
            else f"conviction {c.conviction}/5",
            "value": c.conviction,
        },
        {
            "factor": "evidence_gates_cleared",
            "detail": "evidence complete for bucket"
            if not gaps
            else f"remaining gaps: {', '.join(gaps)}",
            "value": not gaps,
        },
    ]


def _bps_to_pct_str(bps: int) -> str:
    return str(Decimal(bps) / 100)


def _proportional_amounts(budget: int, weights: list[int]) -> list[int]:
    """Floor-allocate ``budget`` across ``weights`` (sleeve target bps).

    Falls back to an even split when every weight is zero, so a sleeve
    with a 0% target can still receive a meaningful line if it is the
    only eligible candidate.
    """
    total = sum(weights)
    if total <= 0:
        n = len(weights)
        return [budget // n for _ in weights] if n else []
    return [budget * w // total for w in weights]


def _allocate_bucket(
    *,
    bucket: str,
    budget: int,
    candidates: list[CandidateInput],
    sleeve_current_bps: dict[str, int],
    policy: PlanPolicy,
) -> tuple[BucketResult, list[WatchlistEntry]]:
    """Split one bucket budget into lines, honouring caps and the min line.

    Selection: rank, take the line cap, then iteratively drop the
    lowest-ranked funded candidate while any proportional amount falls
    below ``minimum_line_amount`` — the dropped share rolls into the
    survivors (or, if none survive, into bucket-unallocated cash). This
    is "leave cash unallocated rather than force weak buys" made
    deterministic.
    """
    result = BucketResult(
        bucket=bucket, budget_micros=budget, allocated_micros=0, unallocated_micros=budget
    )
    watchlist: list[WatchlistEntry] = []
    if budget <= 0:
        return result, watchlist

    eligible = [c for c in candidates if _eligible_for(c, bucket)]
    eligible.sort(key=lambda c: _rank_key(c, sleeve_current_bps))

    cap = policy.max_dca_lines if bucket == "dca" else policy.max_one_time_lines
    funded = eligible[:cap]
    for c in eligible[cap:]:
        watchlist.append(
            WatchlistEntry(
                ticker=c.ticker,
                reason="beyond_line_cap",
                detail=f"eligible for {bucket} but ranked below the "
                f"{cap}-line cap",
            )
        )

    min_micros = policy.minimum_line_micros
    selected = list(funded)
    amounts: list[int] = []
    while selected:
        amounts = _proportional_amounts(
            budget, [max(c.sleeve_target_bps, 0) for c in selected]
        )
        smallest = min(amounts)
        if smallest >= min_micros:
            break
        # Drop the sub-minimum line itself (the weak buy), not the
        # lowest-ranked survivor — its share rolls into the candidates that
        # clear the bar. Tie-break to the lowest-ranked among equal shares
        # so the drop is deterministic.
        drop_idx = max(i for i, a in enumerate(amounts) if a == smallest)
        dropped = selected.pop(drop_idx)
        result.unallocated_reasons.append(
            UnallocatedReason(
                ticker=dropped.ticker,
                reason="below_minimum_line_amount",
                amount_micros=0,
            )
        )
        watchlist.append(
            WatchlistEntry(
                ticker=dropped.ticker,
                reason="below_minimum_line_amount",
                detail=f"share fell below the "
                f"{_micros_to_str(min_micros)} minimum line",
            )
        )
    else:
        amounts = []

    allocated = 0
    for rank, (c, amt) in enumerate(zip(selected, amounts), start=1):
        amt = _apply_hard_cap(c, amt, budget, result)
        if amt < min_micros:
            # A hard-cap trim can push a line back under the minimum; rather
            # than force a weak buy, leave it unallocated.
            result.unallocated_reasons.append(
                UnallocatedReason(
                    ticker=c.ticker,
                    reason="below_minimum_line_amount_after_cap",
                    amount_micros=amt,
                )
            )
            continue
        result.lines.append(
            Line(
                bucket=bucket,
                ticker=c.ticker,
                sleeve_key=c.sleeve_key,
                amount_micros=amt,
                rank=rank,
                ranked_factors=_ranked_factors(c, bucket, sleeve_current_bps),
                rationale=_line_rationale(c, bucket),
            )
        )
        allocated += amt

    result.allocated_micros = allocated
    result.unallocated_micros = budget - allocated
    if result.unallocated_micros > 0 and not result.unallocated_reasons:
        # No line ever cleared the gates — leave the whole budget unallocated
        # rather than force a buy. A small leftover when lines *did* fund is
        # just floor-division rounding.
        reason = "no_eligible_candidate" if not result.lines else "rounding_remainder"
        result.unallocated_reasons.append(
            UnallocatedReason(
                ticker=None,
                reason=reason,
                amount_micros=result.unallocated_micros,
            )
        )
    return result, watchlist


def _apply_hard_cap(
    c: CandidateInput, amount: int, budget: int, result: BucketResult
) -> int:
    """Trim a line so the ticker's post-buy value respects its hard cap.

    A hard cap (when the user supplied one in the strategy) is enforced,
    not merely warned: the excess rolls into bucket-unallocated cash. The
    denominator is the existing portfolio value approximated as the
    bucket's own deployed budget plus current holding — conservative and
    deterministic without needing post-buy totals to converge.
    """
    if c.hard_cap_bps is None:
        return amount
    denom = budget + c.current_mv_micros
    max_value = denom * c.hard_cap_bps // _FULL_ALLOCATION_BPS
    allowed = max(0, max_value - c.current_mv_micros)
    if amount > allowed:
        result.unallocated_reasons.append(
            UnallocatedReason(
                ticker=c.ticker,
                reason="hard_cap",
                amount_micros=amount - allowed,
            )
        )
        return allowed
    return amount


def _line_rationale(c: CandidateInput, bucket: str) -> str:
    if bucket == "one_time":
        return (
            f"one-time buy: {c.ticker} clears the higher one-time evidence bar "
            f"(valuation/fundamental context + why-now)"
        )
    return f"DCA buy: {c.ticker} clears the minimum evidence pack for its sleeve"


def compute_recommendation_lines(
    *,
    candidates: list[CandidateInput],
    dca_budget_micros: int,
    one_time_budget_micros: int,
    portfolio_total_micros: int,
    sleeve_current_micros: dict[str, int],
    unknown_sleeve_micros: int,
    policy: PlanPolicy,
) -> PlanComputation:
    """Produce DCA + one-time lines, unallocated cash, warnings, watchlist.

    The two buckets have *separate* budgets and *separate* eligibility
    gates — no blended allocation. A ticker eligible for both appears as
    two independent lines with distinct rationale.
    """
    sleeve_current_bps = _sleeve_bps(sleeve_current_micros, portfolio_total_micros)

    buckets: dict[str, BucketResult] = {}
    watchlist: list[WatchlistEntry] = []
    for bucket, budget in (
        ("dca", dca_budget_micros),
        ("one_time", one_time_budget_micros),
    ):
        res, wl = _allocate_bucket(
            bucket=bucket,
            budget=budget,
            candidates=candidates,
            sleeve_current_bps=sleeve_current_bps,
            policy=policy,
        )
        buckets[bucket] = res
        watchlist.extend(wl)

    # User exclusions: visible in watchlist context, never a buy line.
    for c in candidates:
        if c.excluded:
            watchlist.append(
                WatchlistEntry(
                    ticker=c.ticker,
                    reason="excluded_by_user",
                    detail="removed from buy lines by exclude_tickers",
                )
            )

    warnings = _concentration_warnings(
        buckets=buckets,
        candidates=candidates,
        portfolio_total_micros=portfolio_total_micros,
        sleeve_current_micros=sleeve_current_micros,
        unknown_sleeve_micros=unknown_sleeve_micros,
        policy=policy,
    )
    warnings.extend(
        _market_data_warnings(candidates=candidates)
    )
    return PlanComputation(buckets=buckets, warnings=warnings, watchlist=watchlist)


def _sleeve_bps(
    sleeve_current_micros: dict[str, int], total: int
) -> dict[str, int]:
    if total <= 0:
        return {k: 0 for k in sleeve_current_micros}
    return {k: v * _FULL_ALLOCATION_BPS // total for k, v in sleeve_current_micros.items()}


def _market_data_warnings(*, candidates: list[CandidateInput]) -> list[Warning]:
    warnings: list[Warning] = []
    for c in candidates:
        if c.excluded:
            continue
        if (c.dca_eligible or c.one_time_eligible) and not c.has_price:
            warnings.append(
                Warning(
                    code=MARKET_DATA_MISSING,
                    severity="warning",
                    ticker=c.ticker,
                    message=(
                        f"{c.ticker} is strategy-eligible and evidence-complete but "
                        "has no stored price; it cannot be funded without grounded "
                        "market data"
                    ),
                )
            )
    return warnings


def _concentration_warnings(
    *,
    buckets: dict[str, BucketResult],
    candidates: list[CandidateInput],
    portfolio_total_micros: int,
    sleeve_current_micros: dict[str, int],
    unknown_sleeve_micros: int,
    policy: PlanPolicy,
) -> list[Warning]:
    by_ticker = {c.ticker: c for c in candidates}
    buy_by_ticker: dict[str, int] = {}
    buy_by_sleeve: dict[str, int] = {}
    total_buys = 0
    for res in buckets.values():
        for line in res.lines:
            buy_by_ticker[line.ticker] = buy_by_ticker.get(line.ticker, 0) + line.amount_micros
            buy_by_sleeve[line.sleeve_key] = (
                buy_by_sleeve.get(line.sleeve_key, 0) + line.amount_micros
            )
            total_buys += line.amount_micros

    denom = portfolio_total_micros + total_buys
    warnings: list[Warning] = []
    if denom <= 0:
        return warnings

    warn_threshold = policy.single_ticker_warn_pct / 100
    for ticker in sorted(buy_by_ticker):
        c = by_ticker.get(ticker)
        if c is not None and c.hard_cap_bps is not None:
            # An explicit hard cap is enforced in allocation; no soft warning.
            continue
        current = c.current_mv_micros if c is not None else 0
        post = Decimal(current + buy_by_ticker[ticker]) / denom
        if post > warn_threshold:
            warnings.append(
                Warning(
                    code=SINGLE_TICKER_CONCENTRATION,
                    severity="warning",
                    ticker=ticker,
                    message=(
                        f"post-buy weight of {ticker} would be "
                        f"{_fmt_pct(post)}%, above the "
                        f"{policy.single_ticker_warn_pct}% single-ticker threshold"
                    ),
                )
            )

    target_bps = {c.sleeve_key: c.sleeve_target_bps for c in candidates}
    sleeve_over_pp = policy.sleeve_over_target_pp / 100
    for sleeve in sorted(buy_by_sleeve):
        current = sleeve_current_micros.get(sleeve, 0)
        post = Decimal(current + buy_by_sleeve[sleeve]) / denom
        target = Decimal(target_bps.get(sleeve, 0)) / _FULL_ALLOCATION_BPS
        if post > target + sleeve_over_pp:
            warnings.append(
                Warning(
                    code=SLEEVE_OVER_TARGET,
                    severity="warning",
                    ticker=None,
                    message=(
                        f"post-buy weight of sleeve {sleeve!r} would be "
                        f"{_fmt_pct(post)}%, above its "
                        f"{_fmt_pct(target)}% target + "
                        f"{policy.sleeve_over_target_pp}pp"
                    ),
                )
            )

    if portfolio_total_micros > 0 and unknown_sleeve_micros > 0:
        unknown_pct = Decimal(unknown_sleeve_micros) / portfolio_total_micros * 100
        if unknown_pct >= policy.unknown_sleeve_warning_pct:
            warnings.append(
                Warning(
                    code=UNKNOWN_SLEEVE_EXPOSURE,
                    severity="warning",
                    ticker=None,
                    message=(
                        f"{_fmt_pct(unknown_pct / 100)}% of the portfolio sits in "
                        "holdings with no mapped strategy sleeve"
                    ),
                )
            )
    return warnings


def _fmt_pct(fraction: Decimal) -> str:
    return str((fraction * 100).quantize(Decimal("0.01")))
