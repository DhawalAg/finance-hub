"""Portfolio weight math over canonical snapshot positions.

Pure helper — no DB access. Callers load positions from
``fin_portfolio_positions`` and pass them in as ``PositionInput`` rows.

Spec (strategy §3, ADR 0004):

- Unsupported holdings *with* a market value count toward portfolio value,
  sleeve exposure, and concentration. They are ineligible for buy lines
  (``is_eligible_for_buy = False``) but still carry a weight so real
  exposure is reflected.
- Unsupported holdings *lacking* a market value are excluded from weight
  math entirely and surface a ``UNSUPPORTED_HOLDING_MISSING_VALUE``
  warning so the user isn't shown silently wrong weights.
- A *supported* holding that happens to be missing a market value gets
  the same treatment (excluded + warning); the symmetry keeps the
  denominator honest regardless of why the value is absent.

Weights are returned as plain floats — call sites format them; they
don't carry envelopes because they're a derived property of one snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

UNSUPPORTED_HOLDING_MISSING_VALUE = "UNSUPPORTED_HOLDING_MISSING_VALUE"


@dataclass(frozen=True)
class PositionInput:
    ticker: Optional[str]
    asset_type: str
    market_value_micros: Optional[int]
    is_supported: bool


@dataclass(frozen=True)
class PositionWeight:
    ticker: Optional[str]
    market_value_micros: int
    weight: float
    is_eligible_for_buy: bool


@dataclass(frozen=True)
class WeightWarning:
    code: str
    ticker: Optional[str]
    message: str


@dataclass(frozen=True)
class PortfolioWeightResult:
    total_value_micros: int
    weights: list[PositionWeight]
    warnings: list[WeightWarning]


def compute_portfolio_weights(positions: Sequence[PositionInput]) -> PortfolioWeightResult:
    counted: list[PositionInput] = []
    warnings: list[WeightWarning] = []

    for p in positions:
        if p.market_value_micros is None:
            warnings.append(
                WeightWarning(
                    code=UNSUPPORTED_HOLDING_MISSING_VALUE,
                    ticker=p.ticker,
                    message=(
                        f"holding {p.ticker or '<unknown>'} lacks a market value "
                        "and is excluded from portfolio weight math"
                    ),
                )
            )
            continue
        counted.append(p)

    total = sum(p.market_value_micros for p in counted)  # type: ignore[misc]
    weights = [
        PositionWeight(
            ticker=p.ticker,
            market_value_micros=p.market_value_micros,  # type: ignore[arg-type]
            weight=(p.market_value_micros / total) if total else 0.0,  # type: ignore[operator]
            is_eligible_for_buy=p.is_supported,
        )
        for p in counted
    ]
    return PortfolioWeightResult(
        total_value_micros=total,
        weights=weights,
        warnings=warnings,
    )
