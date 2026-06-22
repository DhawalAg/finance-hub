"""Portfolio weight math with unsupported-holding semantics.

Spec (strategy §3):
- Unsupported holdings *with* a market value count toward portfolio value,
  sleeve exposure, and concentration, but are ineligible for buy lines.
- Unsupported holdings *lacking* a market value surface a warning and are
  excluded from weight math.
"""
from __future__ import annotations

from finance_hub.strategy.portfolio_weights import (
    PositionInput,
    UNSUPPORTED_HOLDING_MISSING_VALUE,
    compute_portfolio_weights,
)


def _pos(
    *,
    ticker: str | None,
    market_value_micros: int | None,
    is_supported: bool,
    asset_type: str = "etf",
) -> PositionInput:
    return PositionInput(
        ticker=ticker,
        asset_type=asset_type,
        market_value_micros=market_value_micros,
        is_supported=is_supported,
    )


class TestSupportedHoldingsOnly:
    def test_weights_sum_to_one(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="SPY", market_value_micros=4_000_000_000, is_supported=True),
            ]
        )
        assert result.total_value_micros == 10_000_000_000
        weights = {w.ticker: w.weight for w in result.weights}
        assert weights["VTI"] == 0.6
        assert weights["SPY"] == 0.4
        assert result.warnings == []


class TestUnsupportedWithMarketValueCountsButIneligible:
    def test_total_includes_unsupported_value(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="BTC", market_value_micros=4_000_000_000, is_supported=False, asset_type="crypto"),
            ]
        )
        assert result.total_value_micros == 10_000_000_000

    def test_unsupported_position_marked_ineligible_but_carries_weight(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="BTC", market_value_micros=4_000_000_000, is_supported=False, asset_type="crypto"),
            ]
        )
        by_ticker = {w.ticker: w for w in result.weights}
        assert by_ticker["BTC"].weight == 0.4
        assert by_ticker["BTC"].is_eligible_for_buy is False
        assert by_ticker["VTI"].is_eligible_for_buy is True

    def test_unsupported_with_value_emits_no_warning(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="BTC", market_value_micros=4_000_000_000, is_supported=False, asset_type="crypto"),
            ]
        )
        assert UNSUPPORTED_HOLDING_MISSING_VALUE not in [w.code for w in result.warnings]


class TestUnsupportedWithoutMarketValueExcludedWithWarning:
    def test_excluded_from_total_and_weights(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="SPY", market_value_micros=4_000_000_000, is_supported=True),
                _pos(ticker="MYSTERY", market_value_micros=None, is_supported=False, asset_type="bond"),
            ]
        )
        # Mystery position contributes nothing to the denominator.
        assert result.total_value_micros == 10_000_000_000
        tickers = {w.ticker for w in result.weights}
        assert "MYSTERY" not in tickers

    def test_emits_warning_with_ticker(self):
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="MYSTERY", market_value_micros=None, is_supported=False, asset_type="bond"),
            ]
        )
        warnings = [w for w in result.warnings if w.code == UNSUPPORTED_HOLDING_MISSING_VALUE]
        assert len(warnings) == 1
        assert warnings[0].ticker == "MYSTERY"


class TestSupportedHoldingMissingValueExcludedWithWarning:
    def test_supported_missing_value_excluded_and_warned(self):
        # A "supported" position with no market value can't contribute to
        # weight math either; same warning applies.
        result = compute_portfolio_weights(
            [
                _pos(ticker="VTI", market_value_micros=6_000_000_000, is_supported=True),
                _pos(ticker="AAPL", market_value_micros=None, is_supported=True, asset_type="stock"),
            ]
        )
        assert result.total_value_micros == 6_000_000_000
        warnings = [w for w in result.warnings if w.code == UNSUPPORTED_HOLDING_MISSING_VALUE]
        assert any(w.ticker == "AAPL" for w in warnings)


class TestEmptyPortfolio:
    def test_zero_total_no_division_errors(self):
        result = compute_portfolio_weights([])
        assert result.total_value_micros == 0
        assert result.weights == []
        assert result.warnings == []
