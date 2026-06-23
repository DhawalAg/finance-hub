"""Output-mode ladder + freshness/staleness + graceful degradation (issue #12).

Tests the decision matrix for generate_deployment_plan: freshness bands drive
DCA/one-time behavior, portfolio_changed_after_snapshot forces advisory_only +
downgrade to allocation_review, unknown-sleeve block threshold (15%) forces
allocation_review, and watchlist_review emits MARKET_DATA_MISSING.

All tests use a fixed clock (2026-06-23) and directly-seeded DB state.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.helpers import FixedClock
from finance_hub import factories
from finance_hub.research import tools as research
from finance_hub.strategy import tools as strategy
from finance_hub.store import connection, migrations

_NOW = "2026-06-23T12:00:00+00:00"
_TODAY = "2026-06-23"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "plan.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)))
    migrations.run()
    yield p
    factories.reset()


# ---------------------------------------------------------------------------
# seeding helpers
# ---------------------------------------------------------------------------


def _seed_research(*, with_thesis=True, with_fundamentals=False):
    research.set_theme(key="core", display_name="Core")
    research.map_instruments(
        theme_key="core",
        instruments=[
            {
                "ticker": "VTI",
                "type": "etf",
                "instrument_role": "broad_market_etf",
                "status": "approved",
                "rationale": "broad base",
            },
            {
                "ticker": "NVDA",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "conviction": 5,
                "conviction_note": "GPU leader",
                "rationale": "core thesis",
            },
        ],
    )
    if with_thesis:
        research.set_research_note(scope="instrument", key="NVDA", body="thesis")
        src = research.upsert_source(url="https://example.com/nvda", title="NVDA")
        research.link_source(source_id=src["id"], scope="instrument", key="NVDA")
    if with_fundamentals:
        _insert_fundamentals("NVDA")
        _insert_fundamentals("VTI")


def _insert_fundamentals(ticker):
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_fundamentals "
            "(ticker, field, as_of, value, unit, source, grade, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ticker, "ps_ratio", "2026-06-20", "20", "x", "eodhd", "screening", _NOW),
        )
        conn.commit()


def _promote_and_activate(*, core_pct=60, ai_pct=40):
    strategy.promote_to_strategy(
        version_id="strat_v1",
        status="active",
        confirm=True,
        sleeves=[
            {"sleeve_key": "broad", "target_weight_pct": core_pct},
            {"sleeve_key": "ai", "target_weight_pct": ai_pct},
        ],
        instruments=[
            {"ticker": "VTI", "primary_sleeve_key": "broad"},
            {
                "ticker": "NVDA",
                "primary_sleeve_key": "ai",
                "source_theme_key": "core",
            },
        ],
    )


def _seed_snapshot(positions=None, snapshot_id="snap_1", as_of="2026-06-20"):
    if positions is None:
        positions = [("VTI", "1000", True), ("NVDA", "500", True)]
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_portfolio_snapshots "
            "(snapshot_id, as_of, source_adapter, source_file, created_at) "
            "VALUES (?,?,?,?,?)",
            (snapshot_id, as_of, "fidelity_csv", "/tmp/x.csv", _NOW),
        )
        for i, (ticker, mv, supported) in enumerate(positions):
            mv_micros = None if mv is None else int(float(mv) * 1_000_000)
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, ticker, name, asset_type, "
                " quantity, market_value_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot_id, "Brokerage", "brokerage", ticker, ticker,
                    "stock", "1", mv_micros, "USD", 1 if supported else 0,
                    f"hash_{snapshot_id}_{i}",
                ),
            )
        conn.commit()
    return snapshot_id


def _seed_price(ticker, close="100.00"):
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_price_bars "
            "(ticker, session_date, close_micros, currency, source, "
            " first_fetched_at, last_refreshed_at) VALUES (?,?,?,?,?,?,?)",
            (ticker, "2026-06-22", int(float(close) * 1_000_000), "USD", "yfinance",
             _NOW, _NOW),
        )
        conn.commit()


def _seed_all(*, with_thesis=True, with_fundamentals=False, positions=None,
              prices=("VTI", "NVDA"), core_pct=60, ai_pct=40,
              snapshot_as_of="2026-06-20", snapshot_id="snap_1"):
    _seed_research(with_thesis=with_thesis, with_fundamentals=with_fundamentals)
    _promote_and_activate(core_pct=core_pct, ai_pct=ai_pct)
    snap = _seed_snapshot(positions=positions, snapshot_id=snapshot_id,
                          as_of=snapshot_as_of)
    for t in prices:
        _seed_price(t)
    return snap


def _gen(snap, **over):
    kwargs = dict(
        portfolio_snapshot_id=snap,
        strategy_version_id="strat_v1",
        deployable_cash="10000",
        dca_budget="1000",
        one_time_buy_budget="0",
    )
    kwargs.update(over)
    return strategy.generate_deployment_plan(**kwargs)


# ---------------------------------------------------------------------------
# freshness bands drive one-time eligibility
# ---------------------------------------------------------------------------


class TestFreshnessBandBehavior:
    def test_fresh_snapshot_produces_deployment_draft(self):
        # 3 days old (2026-06-20 → 2026-06-23) → fresh
        snap = _seed_all(snapshot_as_of="2026-06-20")
        out = _gen(snap, dca_budget="1000")
        assert out["output_mode"] == "deployment_draft"
        assert out["status"] in ("proposed", "proposed_with_warnings")
        assert not any(
            w["code"] in (
                "PORTFOLIO_SNAPSHOT_STALE",
                "PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME",
            )
            for w in out["warnings"]
        )

    def test_mildly_stale_snapshot_warns_but_allows_one_time(self):
        # 10 days old → mildly_stale: warning emitted, one_time NOT blocked
        snap = _seed_all(with_fundamentals=True, snapshot_as_of="2026-06-13")
        out = _gen(snap, dca_budget="500", one_time_buy_budget="500")
        assert out["output_mode"] == "deployment_draft"
        assert any(w["code"] == "PORTFOLIO_SNAPSHOT_STALE" for w in out["warnings"])
        # one_time budget should be allocated (fundamentals available)
        assert out["buckets"]["one_time"]["allocated_micros"] > 0

    def test_stale_snapshot_blocks_one_time_without_confirm(self):
        # 20 days old (2026-06-03 → 2026-06-23) → stale: one_time blocked
        snap = _seed_all(with_fundamentals=True, snapshot_as_of="2026-06-03")
        out = _gen(snap, dca_budget="500", one_time_buy_budget="500")
        assert out["output_mode"] == "deployment_draft"
        assert any(w["code"] == "PORTFOLIO_SNAPSHOT_STALE" for w in out["warnings"])
        # one_time budget forced to 0 → unallocated
        assert out["buckets"]["one_time"]["unallocated_micros"] == 500_000_000

    def test_stale_snapshot_allows_one_time_with_confirm(self):
        # Same stale snapshot but with confirm_stale_one_time=True
        snap = _seed_all(with_fundamentals=True, snapshot_as_of="2026-06-03")
        out = _gen(snap, dca_budget="0", one_time_buy_budget="1000",
                   confirm_stale_one_time=True)
        assert any(l["bucket"] == "one_time" for l in out["lines"])

    def test_too_old_snapshot_blocks_one_time_permanently(self):
        # 35 days old (2026-05-19 → 2026-06-23) → too_stale_for_one_time
        snap = _seed_all(with_fundamentals=True, snapshot_as_of="2026-05-19")
        out = _gen(snap, dca_budget="500", one_time_buy_budget="500",
                   confirm_stale_one_time=True)  # confirm is ignored for >30 days
        assert any(
            w["code"] == "PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME"
            for w in out["warnings"]
        )
        # one_time budget still unallocated — too old, confirm can't override
        assert out["buckets"]["one_time"]["unallocated_micros"] == 500_000_000

    def test_freshness_band_stored_on_plan(self):
        snap = _seed_all(snapshot_as_of="2026-06-20")
        out = _gen(snap, dca_budget="1000")
        stored = strategy.get_deployment_plan(plan_id=out["plan_id"])
        assert stored["snapshot_freshness_band"] == "fresh"
        assert stored["snapshot_days_old"] == 3


# ---------------------------------------------------------------------------
# portfolio_changed_after_snapshot forces advisory_only + allocation_review
# ---------------------------------------------------------------------------


class TestPortfolioChangedDowngrade:
    def test_changed_downgrades_to_allocation_review(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000", portfolio_changed_after_snapshot=True)
        assert out["output_mode"] == "allocation_review"
        assert out["status"] == "advisory_only"

    def test_changed_emits_portfolio_changed_warning(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000", portfolio_changed_after_snapshot=True)
        assert any(
            w["code"] == "PORTFOLIO_CHANGED_AFTER_SNAPSHOT" for w in out["warnings"]
        )

    def test_changed_reports_deployment_draft_as_blocked(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000", portfolio_changed_after_snapshot=True)
        assert "deployment_draft" in out["blocked_output_modes"]

    def test_changed_plan_stored_with_advisory_only_status(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000", portfolio_changed_after_snapshot=True)
        stored = strategy.get_deployment_plan(plan_id=out["plan_id"])
        assert stored["status"] == "advisory_only"
        assert stored["output_mode"] == "allocation_review"
        assert stored["portfolio_changed_after_snapshot"] == 1


# ---------------------------------------------------------------------------
# unknown-sleeve block threshold (15%) forces allocation_review
# ---------------------------------------------------------------------------


class TestUnknownSleeveBlock:
    def test_heavy_unknown_sleeve_blocks_deployment_draft(self):
        # TSLA not in strategy → 90% of portfolio in unknown sleeve → > 15% block
        snap = _seed_all(positions=[("VTI", "100", True), ("TSLA", "900", True)])
        out = _gen(snap, dca_budget="1000")
        assert out["output_mode"] == "allocation_review"

    def test_heavy_unknown_sleeve_emits_block_severity(self):
        snap = _seed_all(positions=[("VTI", "100", True), ("TSLA", "900", True)])
        out = _gen(snap, dca_budget="1000")
        block_warnings = [
            w for w in out["warnings"]
            if w["code"] == "UNKNOWN_SLEEVE_EXPOSURE" and w["severity"] == "block"
        ]
        assert block_warnings

    def test_moderate_unknown_sleeve_warns_but_keeps_deployment_draft(self):
        # 900 VTI + 50 TSLA → ~5.3% unknown → warning only, not block
        snap = _seed_all(positions=[("VTI", "900", True), ("TSLA", "50", True)])
        out = _gen(snap, dca_budget="1000")
        assert out["output_mode"] == "deployment_draft"
        # UNKNOWN_SLEEVE_EXPOSURE should appear as a warning (not block)
        warn_codes = [w for w in out["warnings"]
                      if w["code"] == "UNKNOWN_SLEEVE_EXPOSURE"]
        if warn_codes:
            assert all(w["severity"] == "warning" for w in warn_codes)

    def test_unknown_sleeve_below_warning_pct_no_warning(self):
        # Tiny unknown sleeve: 5 TSLA in 1000 portfolio = 0.5% → no warning
        snap = _seed_all(positions=[("VTI", "1000", True), ("TSLA", "5", True)])
        out = _gen(snap, dca_budget="1000")
        assert not any(
            w["code"] == "UNKNOWN_SLEEVE_EXPOSURE" for w in out["warnings"]
        )

    def test_unknown_sleeve_effective_values_stored_on_plan(self):
        snap = _seed_all(positions=[("VTI", "100", True), ("TSLA", "900", True)])
        out = _gen(snap, dca_budget="1000")
        assert out["effective_policy"]["unknown_sleeve_warning_pct"] == "5"
        assert out["effective_policy"]["unknown_sleeve_block_pct"] == "15"


# ---------------------------------------------------------------------------
# watchlist_review mode
# ---------------------------------------------------------------------------


class TestWatchlistReviewMode:
    def test_watchlist_review_requested_explicitly(self):
        snap = _seed_all(prices=[])  # no prices seeded
        out = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            requested_output_mode="watchlist_review",
        )
        assert out["output_mode"] == "watchlist_review"

    def test_watchlist_review_emits_market_data_missing(self):
        snap = _seed_all(prices=[])  # no prices → MARKET_DATA_MISSING expected
        out = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            requested_output_mode="watchlist_review",
        )
        market_data_warnings = [
            w for w in out["warnings"] if w["code"] == "MARKET_DATA_MISSING"
        ]
        assert market_data_warnings

    def test_watchlist_review_has_no_dollar_lines(self):
        snap = _seed_all(prices=[])
        out = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            requested_output_mode="watchlist_review",
        )
        assert out["lines"] == []

    def test_watchlist_review_includes_research_candidates(self):
        snap = _seed_all(prices=[])
        out = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            requested_output_mode="watchlist_review",
        )
        # candidates section lists research instruments with their status
        assert "candidates" in out
        tickers = {c["ticker"] for c in out["candidates"]}
        assert "VTI" in tickers
        assert "NVDA" in tickers

    def test_watchlist_review_no_price_claims(self):
        # watchlist_review must not fabricate price or valuation claims
        snap = _seed_all(prices=[])
        out = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            requested_output_mode="watchlist_review",
        )
        for c in out.get("candidates", []):
            assert "price" not in c or c["price"] is None


# ---------------------------------------------------------------------------
# output mode requested stronger than achievable → downgrade
# ---------------------------------------------------------------------------


class TestOutputModeDowngradeMatrix:
    def test_deployment_draft_achieved_when_no_issues(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000")
        assert out["output_mode"] == "deployment_draft"
        assert out["blocked_output_modes"] == []

    def test_watchlist_review_achievable_when_portfolio_changed(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000",
                   portfolio_changed_after_snapshot=True,
                   requested_output_mode="watchlist_review")
        # watchlist_review is weaker than allocation_review → no downgrade needed
        assert out["output_mode"] == "watchlist_review"
        assert "deployment_draft" not in out["blocked_output_modes"]

    def test_blocked_output_modes_stored_on_plan(self):
        snap = _seed_all()
        out = _gen(snap, dca_budget="1000", portfolio_changed_after_snapshot=True)
        stored = strategy.get_deployment_plan(plan_id=out["plan_id"])
        import json
        blocked = json.loads(stored["blocked_output_modes"])
        assert "deployment_draft" in blocked
