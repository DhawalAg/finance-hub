"""Fixture builder for 'instrument_candidate_aapl' (used by R3, spec §5.2).

Seeds:
  - fin_themes: theme_r3 (status=watching, display_name='Quality Growth')
  - fin_theme_instruments: AAPL attached to theme_r3 with status=candidate
  - workspace/research/instruments/: empty directory (agent writes AAPL.md)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from evals.fixtures._common import seed_context

_CLOCK = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def build(trial_dir: Path) -> dict[str, str]:
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

    db_path = trial_dir / "db.sqlite"

    with seed_context(db_path, workspace, _CLOCK):
        from finance_hub.store import migrations
        migrations.run()

        from finance_hub.research import tools as research
        research.set_theme(key="theme_r3", display_name="Quality Growth", status="watching")
        research.map_instruments(
            theme_key="theme_r3",
            instruments=[
                {
                    "ticker": "AAPL",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "display_name": "Apple Inc",
                },
            ],
        )

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
