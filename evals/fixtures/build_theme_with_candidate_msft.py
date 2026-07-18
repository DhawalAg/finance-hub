"""Fixture builder for 'theme_with_candidate_msft' (used by R11).

Seeds a theme (theme_r11 / Cloud Growth) with MSFT as a candidate instrument
that has not yet been reviewed. The conviction-note validation trial begins from
this state: the agent attempts review without a note (triggering the error) and
then retries with the note.
"""
from __future__ import annotations

from pathlib import Path


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the theme_with_candidate_msft fixture into trial_dir.

    Seed steps (all via real tool calls):
      1. migrations.run() on a fresh DB
      2. set_theme(key='theme_r11', display_name='Cloud Growth', status='watching')
      3. map_instruments for MSFT (stock / single_stock, status=candidate)

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.store import migrations
    from evals.fixtures._helpers import use_db

    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    factories.reset()

    try:
        with use_db(db_path):
            migrations.run()

            research.set_theme(key="theme_r11", display_name="Cloud Growth", status="watching")
            research.map_instruments(
                theme_key="theme_r11",
                instruments=[{
                    "ticker": "MSFT",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "display_name": "Microsoft Corp",
                }],
            )
    finally:
        factories.reset()

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
