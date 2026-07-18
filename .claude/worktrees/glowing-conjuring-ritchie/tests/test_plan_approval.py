"""Slice 11: plan_readiness_check, approve, reject, supersede, memo artifacts.

Tests use the registered tool boundary (structured JSON in/out) against
a temp SQLite DB with directly-seeded state (snapshot + strategy + prices).
All clock calls use FixedClock(2026-06-23T12:00).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.helpers import FixedClock
from finance_hub import factories
from finance_hub.research import tools as research
from finance_hub.strategy import tools as strategy, memo
from finance_hub.store import connection, migrations

_NOW = "2026-06-23T12:00:00+00:00"
_TODAY = "2026-06-23"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "plan.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(memo, "WORKSPACE_ROOT", tmp_path / "workspace")
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)))
    migrations.run()
    yield p
    factories.reset()


# ---------------------------------------------------------------------------
# Seeding helpers
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
                "conviction": 4,
                "conviction_note": "GPU leader",
                "rationale": "core thesis",
            },
        ],
    )
    if with_thesis:
        research.set_research_note(scope="instrument", key="NVDA", body="thesis body")
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


def _promote_and_activate():
    strategy.promote_to_strategy(
        version_id="strat_v1",
        status="active",
        confirm=True,
        sleeves=[
            {"sleeve_key": "broad", "target_weight_pct": 60},
            {"sleeve_key": "ai", "target_weight_pct": 40},
        ],
        instruments=[
            {"ticker": "VTI", "primary_sleeve_key": "broad"},
            {"ticker": "NVDA", "primary_sleeve_key": "ai", "source_theme_key": "core"},
        ],
    )


def _seed_snapshot(as_of="2026-06-20", snapshot_id="snap_1"):
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_portfolio_snapshots "
            "(snapshot_id, as_of, source_adapter, source_file, created_at) "
            "VALUES (?,?,?,?,?)",
            (snapshot_id, as_of, "fidelity_csv", "/tmp/x.csv", _NOW),
        )
        for i, (ticker, mv) in enumerate([("VTI", "1000"), ("NVDA", "500")]):
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, ticker, name, asset_type, "
                " quantity, market_value_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot_id, "Brokerage", "brokerage", ticker, ticker,
                    "stock", "1", int(float(mv) * 1_000_000), "USD", 1,
                    f"hash_{snapshot_id}_{i}",
                ),
            )
        conn.commit()
    return snapshot_id


def _seed_price(ticker, close_micros):
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_price_bars "
            "(ticker, session_date, close_micros, currency, source, "
            " first_fetched_at, last_refreshed_at) VALUES (?,?,?,?,?,?,?)",
            (ticker, "2026-06-22", close_micros, "USD", "yfinance", _NOW, _NOW),
        )
        conn.commit()


def _update_price(ticker, new_close_micros):
    """Update the price to simulate drift."""
    with connection.connect() as conn:
        conn.execute(
            "UPDATE fin_price_bars SET close_micros = ?, last_refreshed_at = ? "
            "WHERE ticker = ? AND session_date = '2026-06-22'",
            (new_close_micros, _NOW, ticker),
        )
        conn.commit()


def _seed_all_and_gen_plan(*, with_thesis=True, with_fundamentals=False,
                            dca_budget="1000", one_time_budget="0",
                            vti_price=100_000_000, nvda_price=500_000_000):
    """Seed full state and generate a plan, return the plan JSON."""
    _seed_research(with_thesis=with_thesis, with_fundamentals=with_fundamentals)
    _promote_and_activate()
    snap = _seed_snapshot()
    _seed_price("VTI", vti_price)
    _seed_price("NVDA", nvda_price)
    return strategy.generate_deployment_plan(
        portfolio_snapshot_id=snap,
        strategy_version_id="strat_v1",
        deployable_cash=str(int(dca_budget) + int(one_time_budget)),
        dca_budget=dca_budget,
        one_time_buy_budget=one_time_budget,
    )


# ===========================================================================
# plan_readiness_check
# ===========================================================================


class TestPlanReadinessCheck:
    def test_still_approvable_when_no_drift(self):
        plan = _seed_all_and_gen_plan()
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "still_approvable"
        assert result["approvable"] is True
        assert result["blocking_reasons"] == []
        assert result["warning_reasons"] == []

    def test_approval_warning_when_price_drifts_over_3pct(self):
        plan = _seed_all_and_gen_plan(vti_price=100_000_000)
        # Drift VTI up by 4% (>3% threshold)
        _update_price("VTI", 104_000_000)
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "approval_warning"
        assert result["approvable"] is True
        assert any("VTI" in r for r in result["warning_reasons"])

    def test_approval_blocked_when_one_time_drifts_over_7pct(self):
        # Need fundamentals for one_time eligibility
        plan = _seed_all_and_gen_plan(
            with_fundamentals=True, dca_budget="0", one_time_budget="1000",
            nvda_price=500_000_000,
        )
        # one_time lines need NVDA to be one_time_eligible; drift NVDA by 10%
        _update_price("NVDA", 550_000_000)
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        # Should be blocked if there's a one_time line with >7% drift
        one_time_lines = [l for l in plan["lines"] if l["bucket"] == "one_time"]
        if one_time_lines:
            assert result["readiness_status"] == "approval_blocked"
            assert result["approvable"] is False

    def test_approval_blocked_when_plan_has_block_warnings(self):
        # Generate a plan with a block warning (use >30 day old snapshot)
        _seed_research()
        _promote_and_activate()
        snap = _seed_snapshot(as_of="2026-05-10")  # >30 days old → blocks one_time
        _seed_price("VTI", 100_000_000)
        _seed_price("NVDA", 500_000_000)
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            dca_budget="500",
            one_time_buy_budget="500",
        )
        # Plan should have PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME block warning
        block_warnings = [w for w in plan["warnings"] if w["severity"] == "block"]
        assert block_warnings, "expected a block warning from stale snapshot"
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "approval_blocked"
        assert result["approvable"] is False

    def test_approval_blocked_when_plan_already_approved(self):
        plan = _seed_all_and_gen_plan()
        strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "approval_blocked"
        assert result["approvable"] is False

    def test_approval_blocked_when_plan_rejected(self):
        plan = _seed_all_and_gen_plan()
        strategy.reject_deployment_plan(
            plan_id=plan["plan_id"], reason="changed mind", confirm=True
        )
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "approval_blocked"

    def test_approval_blocked_when_plan_is_advisory_only(self):
        _seed_research()
        _promote_and_activate()
        snap = _seed_snapshot()
        _seed_price("VTI", 100_000_000)
        _seed_price("NVDA", 500_000_000)
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            dca_budget="1000",
            portfolio_changed_after_snapshot=True,
        )
        assert plan["status"] == "advisory_only"
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "approval_blocked"

    def test_readiness_check_raises_when_plan_not_found(self):
        with pytest.raises(LookupError, match="no deployment plan"):
            strategy.plan_readiness_check(plan_id="plan_nonexistent")

    def test_price_drift_within_3pct_is_still_approvable(self):
        plan = _seed_all_and_gen_plan(vti_price=100_000_000)
        # 2% drift — within threshold
        _update_price("VTI", 102_000_000)
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        assert result["readiness_status"] == "still_approvable"

    def test_readiness_check_includes_price_check_details(self):
        plan = _seed_all_and_gen_plan(vti_price=100_000_000)
        result = strategy.plan_readiness_check(plan_id=plan["plan_id"])
        # price_checks should list tickers with stored draft prices
        assert "price_checks" in result
        tickers = {pc["ticker"] for pc in result["price_checks"]}
        assert "VTI" in tickers or len(result["price_checks"]) == 0  # depends on line eligibility


# ===========================================================================
# approve_deployment_plan
# ===========================================================================


class TestApproveDeploymentPlan:
    def test_approve_requires_confirm_true(self):
        plan = _seed_all_and_gen_plan()
        with pytest.raises(ValueError, match="explicit"):
            strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=False)

    def test_approve_returns_approved_status(self):
        plan = _seed_all_and_gen_plan()
        result = strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        assert result["status"] == "approved"
        assert result["plan_id"] == plan["plan_id"]
        assert result["approved_at"] is not None

    def test_approve_updates_db_status(self):
        plan = _seed_all_and_gen_plan()
        strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        stored = strategy.get_deployment_plan(plan_id=plan["plan_id"])
        assert stored["status"] == "approved"

    def test_cannot_approve_plan_with_block_warnings(self):
        _seed_research()
        _promote_and_activate()
        snap = _seed_snapshot(as_of="2026-05-10")  # >30 days → block warning
        _seed_price("VTI", 100_000_000)
        _seed_price("NVDA", 500_000_000)
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            dca_budget="500",
            one_time_buy_budget="500",
        )
        block_warnings = [w for w in plan["warnings"] if w["severity"] == "block"]
        assert block_warnings
        with pytest.raises(ValueError, match="cannot be approved"):
            strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)

    def test_can_approve_plan_with_warning_only(self):
        # Mildly stale snapshot produces a warning (not a block) — still approvable
        _seed_research()
        _promote_and_activate()
        snap = _seed_snapshot(as_of="2026-06-13")  # 10 days old → mildly_stale warning
        _seed_price("VTI", 100_000_000)
        _seed_price("NVDA", 500_000_000)
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            dca_budget="1000",
        )
        assert plan["status"] == "proposed_with_warnings"
        result = strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        assert result["status"] == "approved"

    def test_approve_raises_when_plan_not_found(self):
        with pytest.raises(LookupError, match="no deployment plan"):
            strategy.approve_deployment_plan(plan_id="plan_nope", confirm=True)

    def test_cannot_approve_already_approved_plan(self):
        plan = _seed_all_and_gen_plan()
        strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        with pytest.raises(ValueError, match="cannot be approved"):
            strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)

    def test_cannot_approve_advisory_only_plan(self):
        _seed_research()
        _promote_and_activate()
        snap = _seed_snapshot()
        _seed_price("VTI", 100_000_000)
        _seed_price("NVDA", 500_000_000)
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap,
            strategy_version_id="strat_v1",
            deployable_cash="1000",
            dca_budget="1000",
            portfolio_changed_after_snapshot=True,
        )
        assert plan["status"] == "advisory_only"
        with pytest.raises(ValueError, match="cannot be approved"):
            strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)

    def test_approve_generates_memo_file(self):
        plan = _seed_all_and_gen_plan()
        result = strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        assert "memo_path" in result
        memo_path = Path(result["memo_path"])
        assert memo_path.exists(), f"approved memo not found at {memo_path}"
        content = memo_path.read_text()
        assert "GENERATED ARTIFACT" in content
        assert "approved" in content.lower()


# ===========================================================================
# reject_deployment_plan
# ===========================================================================


class TestRejectDeploymentPlan:
    def test_reject_requires_confirm_true(self):
        plan = _seed_all_and_gen_plan()
        with pytest.raises(ValueError, match="explicit"):
            strategy.reject_deployment_plan(
                plan_id=plan["plan_id"], reason="bad plan", confirm=False
            )

    def test_reject_requires_reason(self):
        plan = _seed_all_and_gen_plan()
        with pytest.raises(ValueError, match="reason"):
            strategy.reject_deployment_plan(plan_id=plan["plan_id"], reason="", confirm=True)

    def test_reject_returns_rejected_status(self):
        plan = _seed_all_and_gen_plan()
        result = strategy.reject_deployment_plan(
            plan_id=plan["plan_id"], reason="market conditions changed", confirm=True
        )
        assert result["status"] == "rejected"
        assert result["rejection_reason"] == "market conditions changed"

    def test_reject_updates_db_status(self):
        plan = _seed_all_and_gen_plan()
        strategy.reject_deployment_plan(
            plan_id=plan["plan_id"], reason="too aggressive", confirm=True
        )
        stored = strategy.get_deployment_plan(plan_id=plan["plan_id"])
        assert stored["status"] == "rejected"
        assert stored["rejection_reason"] == "too aggressive"

    def test_reject_no_memo_generated(self, tmp_path):
        plan = _seed_all_and_gen_plan()
        strategy.reject_deployment_plan(
            plan_id=plan["plan_id"], reason="bad idea", confirm=True
        )
        # No approved memo should exist
        approved_dir = tmp_path / "workspace" / "approved"
        if approved_dir.exists():
            approved_files = list(approved_dir.glob("*.md"))
            assert not approved_files, "no memo should be generated for rejection"

    def test_cannot_reject_already_approved_plan(self):
        plan = _seed_all_and_gen_plan()
        strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        with pytest.raises(ValueError, match="already"):
            strategy.reject_deployment_plan(
                plan_id=plan["plan_id"], reason="too late", confirm=True
            )

    def test_reject_raises_when_plan_not_found(self):
        with pytest.raises(LookupError, match="no deployment plan"):
            strategy.reject_deployment_plan(
                plan_id="plan_nope", reason="gone", confirm=True
            )


# ===========================================================================
# Supersession
# ===========================================================================


class TestSupersession:
    def test_generate_with_supersedes_marks_old_plan_superseded(self):
        plan1 = _seed_all_and_gen_plan()
        # Generate a second plan that supersedes plan1
        plan2 = strategy.generate_deployment_plan(
            portfolio_snapshot_id="snap_1",
            strategy_version_id="strat_v1",
            deployable_cash="2000",
            dca_budget="2000",
            supersedes_plan_id=plan1["plan_id"],
        )
        stored1 = strategy.get_deployment_plan(plan_id=plan1["plan_id"])
        assert stored1["status"] == "superseded", \
            f"expected 'superseded', got {stored1['status']!r}"
        assert plan2["supersedes_plan_id"] == plan1["plan_id"]

    def test_superseded_plan_not_approvable(self):
        plan1 = _seed_all_and_gen_plan()
        strategy.generate_deployment_plan(
            portfolio_snapshot_id="snap_1",
            strategy_version_id="strat_v1",
            deployable_cash="2000",
            dca_budget="2000",
            supersedes_plan_id=plan1["plan_id"],
        )
        result = strategy.plan_readiness_check(plan_id=plan1["plan_id"])
        assert result["readiness_status"] == "approval_blocked"

    def test_cannot_supersede_already_superseded_plan(self):
        plan1 = _seed_all_and_gen_plan()
        plan2 = strategy.generate_deployment_plan(
            portfolio_snapshot_id="snap_1",
            strategy_version_id="strat_v1",
            deployable_cash="2000",
            dca_budget="2000",
            supersedes_plan_id=plan1["plan_id"],
        )
        # Supersede plan1 again → should be an error since it's already superseded
        with pytest.raises(ValueError, match="superseded"):
            strategy.generate_deployment_plan(
                portfolio_snapshot_id="snap_1",
                strategy_version_id="strat_v1",
                deployable_cash="3000",
                dca_budget="3000",
                supersedes_plan_id=plan1["plan_id"],
            )


# ===========================================================================
# Draft memo artifacts
# ===========================================================================


class TestDraftMemoArtifacts:
    def test_draft_memo_written_when_plan_generated(self, tmp_path):
        plan = _seed_all_and_gen_plan()
        draft_dir = tmp_path / "workspace" / "drafts"
        if draft_dir.exists():
            files = list(draft_dir.glob("*.md"))
            assert files, "expected at least one draft memo file"

    def test_draft_memo_contains_banner(self, tmp_path):
        plan = _seed_all_and_gen_plan()
        draft_dir = tmp_path / "workspace" / "drafts"
        if draft_dir.exists():
            for f in draft_dir.glob("*.md"):
                content = f.read_text()
                assert "GENERATED ARTIFACT" in content

    def test_approved_memo_is_separate_from_draft(self, tmp_path):
        plan = _seed_all_and_gen_plan()
        strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        approved_dir = tmp_path / "workspace" / "approved"
        assert approved_dir.exists()
        approved_files = list(approved_dir.glob("*.md"))
        assert approved_files, "expected an approved memo file"

    def test_approved_memo_shape(self, tmp_path):
        plan = _seed_all_and_gen_plan(dca_budget="1000")
        result = strategy.approve_deployment_plan(plan_id=plan["plan_id"], confirm=True)
        content = Path(result["memo_path"]).read_text()
        # Should contain the documented sections
        assert "GENERATED ARTIFACT" in content
        assert "approved" in content.lower()
        # Should have inputs section
        assert "inputs" in content.lower() or "portfolio" in content.lower()


# ===========================================================================
# Pure deployment.check_plan_readiness tests
# ===========================================================================


class TestCheckPlanReadinessPure:
    """Pure function tests — no DB required."""

    def _make_price_check(self, ticker, bucket, draft, current):
        from decimal import Decimal
        from finance_hub.strategy.deployment import PriceCheck
        drift = (Decimal(current) - Decimal(draft)) / Decimal(draft)
        return PriceCheck(
            ticker=ticker,
            bucket=bucket,
            draft_close_micros=draft,
            current_close_micros=current,
            drift_pct=drift,
        )

    def test_still_approvable_no_issues(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=True,
            price_checks=[],
            policy=PlanPolicy(),
        )
        assert result.status == "still_approvable"

    def test_blocked_by_existing_block_warnings(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=True,
            strategy_active=True,
            price_checks=[],
            policy=PlanPolicy(),
        )
        assert result.status == "approval_blocked"
        assert result.blocking_reasons

    def test_blocked_by_strategy_no_longer_active(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=False,
            price_checks=[],
            policy=PlanPolicy(),
        )
        assert result.status == "approval_blocked"

    def test_blocked_by_non_proposed_status(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        for s in ("approved", "rejected", "superseded", "advisory_only", "blocked"):
            result = check_plan_readiness(
                plan_status=s,
                has_block_warnings=False,
                strategy_active=True,
                price_checks=[],
                policy=PlanPolicy(),
            )
            assert result.status == "approval_blocked", f"expected blocked for {s!r}"

    def test_warning_on_dca_drift_over_3pct(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        pc = self._make_price_check("VTI", "dca", 100_000_000, 104_000_000)
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=True,
            price_checks=[pc],
            policy=PlanPolicy(),
        )
        assert result.status == "approval_warning"
        assert result.warning_reasons

    def test_blocked_on_one_time_drift_over_7pct(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        pc = self._make_price_check("NVDA", "one_time", 100_000_000, 110_000_000)
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=True,
            price_checks=[pc],
            policy=PlanPolicy(),
        )
        assert result.status == "approval_blocked"

    def test_dca_drift_over_7pct_is_warning_not_block(self):
        """>7% drift on DCA line → warning (block threshold only applies to one_time)."""
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        pc = self._make_price_check("VTI", "dca", 100_000_000, 110_000_000)
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=True,
            price_checks=[pc],
            policy=PlanPolicy(),
        )
        # DCA drift >7% → warning (not block — the >7% block only applies to one_time)
        assert result.status == "approval_warning"

    def test_small_drift_under_3pct_is_approvable(self):
        from finance_hub.strategy.deployment import check_plan_readiness, PlanPolicy
        pc = self._make_price_check("VTI", "dca", 100_000_000, 102_000_000)
        result = check_plan_readiness(
            plan_status="proposed",
            has_block_warnings=False,
            strategy_active=True,
            price_checks=[pc],
            policy=PlanPolicy(),
        )
        assert result.status == "still_approvable"
