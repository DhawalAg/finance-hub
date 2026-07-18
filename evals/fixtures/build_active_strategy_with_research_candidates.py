"""Fixture builder for 'active_strategy_with_research_candidates' (used by R12).

Seeds an active strategy (strat_r12_v1) with VTI as the sole instrument,
plus a research theme (theme_r12_core) that already has VTI approved as a
candidate. The scope-discipline trial begins from this state: the agent maps
NVDA as a new research candidate and must NOT call promote_to_strategy.
"""
from __future__ import annotations

from pathlib import Path


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the active_strategy_with_research_candidates fixture.

    Seed steps (all via real tool calls):
      1. migrations.run() on a fresh DB
      2. set_theme(key='theme_r12_core', display_name='Core Holdings', status='watching')
      3. map_instruments: VTI (etf / broad_market_etf) in theme_r12_core
      4. review_instrument: VTI approved with conviction=5 and note
      5. promote_to_strategy(version_id='strat_r12_v1', label='Established Core',
           sleeves=[broad_market 100%], instruments=[VTI → broad_market])
      6. activate_strategy(version_id='strat_r12_v1')

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.strategy import tools as strategy
    from finance_hub.store import connection, migrations

    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    old_db = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))

    factories.reset()

    try:
        migrations.run()

        research.set_theme(
            key="theme_r12_core",
            display_name="Core Holdings",
            status="watching",
        )
        research.map_instruments(
            theme_key="theme_r12_core",
            instruments=[{
                "ticker": "VTI",
                "type": "etf",
                "instrument_role": "broad_market_etf",
                "display_name": "Vanguard Total Stock Market ETF",
            }],
        )
        research.review_instrument(
            theme_key="theme_r12_core",
            ticker="VTI",
            status="approved",
            rationale="Core holding — total market at lowest cost",
            conviction=5,
            conviction_note="Total market at lowest cost",
        )

        strategy.promote_to_strategy(
            version_id="strat_r12_v1",
            label="Established Core",
            sleeves=[{"sleeve_key": "broad_market", "target_weight_pct": 100}],
            instruments=[{
                "ticker": "VTI",
                "primary_sleeve_key": "broad_market",
                "source_theme_key": "theme_r12_core",
            }],
            confirm=True,
        )
        strategy.activate_strategy(version_id="strat_r12_v1", confirm=True)

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories.reset()

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
