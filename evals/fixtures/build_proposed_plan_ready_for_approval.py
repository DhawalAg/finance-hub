"""Fixture builder for 'proposed_plan_ready_for_approval' (used by R6, spec §5.2).

Extends dca_ready_deployment (R5) and adds a pre-generated plan:
  - All R5 state but with r6 IDs (theme_r6, strat_r6_v1, snap_r6_fixture)
  - fin_deployment_plans: plan_r6_fixture (status=proposed, approvable=True)
  - workspace/drafts/: draft memo written by generate_deployment_plan
  - workspace/approved/: empty (memo not yet written — writing is the trial action)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from evals.fixtures._common import seed_context
from evals.fixtures.build_dca_ready_deployment import (
    _make_provider,
    _seed_research,
    _seed_strategy,
    import_snapshot_with_id,
)

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
_PRICE_AS_OF = date(2026, 6, 20)


def _generate_plan_with_id(strategy, snap_id: str, strat_id: str, plan_suffix: str) -> dict:
    """Call generate_deployment_plan with uuid patched to get a known plan_id."""
    mock_uuid = MagicMock()
    mock_uuid.hex = plan_suffix  # hex[:12] returns suffix as-is when len < 12
    target = "finance_hub.strategy.tools.uuid.uuid4"
    with patch(target, return_value=mock_uuid):
        return strategy.generate_deployment_plan(
            portfolio_snapshot_id=snap_id,
            strategy_version_id=strat_id,
            deployable_cash="1000",
            dca_budget="1000",
            one_time_buy_budget="0",
        )


def build(trial_dir: Path) -> dict[str, str]:
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)
    (workspace / "approved").mkdir(parents=True, exist_ok=True)

    db_path = trial_dir / "db.sqlite"

    with seed_context(db_path, workspace, _NOW, _make_provider()):
        from finance_hub.store import migrations
        from finance_hub.research import tools as research
        from finance_hub.strategy import tools as strategy
        from finance_hub.market_data.tools import snapshot

        migrations.run()
        _seed_research(research, theme_key="theme_r6")
        _seed_strategy(strategy, version_id="strat_r6_v1", theme_key="theme_r6")
        import_snapshot_with_id("r6_fixture")
        snapshot(["VTI", "AAPL", "QQQ", "SPY"], as_of=_PRICE_AS_OF)

        plan = _generate_plan_with_id(
            strategy,
            snap_id="snap_r6_fixture",
            strat_id="strat_r6_v1",
            plan_suffix="r6_fixture",
        )
        assert plan["plan_id"] == "plan_r6_fixture", (
            f"UUID patch failed: got {plan['plan_id']!r}"
        )

        readiness = strategy.plan_readiness_check(plan_id="plan_r6_fixture")
        assert readiness["approvable"] is True, (
            f"plan_r6_fixture is not approvable: {readiness}"
        )

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
