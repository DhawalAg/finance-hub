"""Fixture builder for 'skill_workflow_stub' (used by C8, spec §5.2, ADR 0006).

Placeholder fixture for the first ADR-0005 skill eval task. Builds a DB with
two unreviewed candidate instruments in a research theme — the workflow a
research-prioritization skill would orchestrate.

Per ADR 0006: tasks grade workflows, not skills; this task tests the
research-priorities → candidate-review workflow that a skill would automate.
The bar is definition + witnessed run (pass irrelevant at Phase 4 frontier).

What the fixture contains:
  - fin_themes: theme_c8 (status=watching, display_name="Skill Workflow Queue")
  - fin_theme_instruments: VTI + AAPL both at status='candidate' (unreviewed)
  - fin_strategy_versions: 0 rows (no promotion yet)
  - workspace/: empty research dir

The agent's task: use finance.research_priorities to identify what needs
research attention, review at least one candidate via finance.review_instrument,
and report what actions are needed to prepare the queue for promotion.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

VERSION = "1"

_NOW = "2026-06-23T12:00:00+00:00"


class _FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the skill_workflow_stub fixture into trial_dir."""
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    _setup_db(db_path, workspace)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }


def _setup_db(db_path: Path, workspace: Path) -> None:
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.store import connection, migrations

    now_dt = datetime.fromisoformat(_NOW)
    old_db = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    old_clock = factories._clock
    old_workspace_env = os.environ.get("FINANCE_HUB_WORKSPACE")

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    factories.set_clock(_FixedClock(now_dt))
    os.environ["FINANCE_HUB_WORKSPACE"] = str(workspace)

    try:
        migrations.run()

        (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

        # Theme with two candidates not yet reviewed
        research.set_theme(key="theme_c8", display_name="Skill Workflow Queue")
        research.map_instruments(
            theme_key="theme_c8",
            instruments=[
                {
                    "ticker": "VTI",
                    "type": "etf",
                    "instrument_role": "broad_market_etf",
                    "status": "candidate",
                    "display_name": "Vanguard Total Stock Market ETF",
                    "conviction": None,
                    "rationale": "Broad market baseline candidate",
                },
                {
                    "ticker": "AAPL",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "status": "candidate",
                    "display_name": "Apple Inc",
                    "conviction": None,
                    "rationale": "Quality franchise candidate for single-stock sleeve",
                },
            ],
        )

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
        if old_workspace_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_workspace_env
