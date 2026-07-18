"""Fixture builder for 'fetch_fundamentals_fixture' (used by C1, spec §5.2).

Builds a fresh SQLite DB with AAPL registered as a candidate instrument, and
places a recorded EODHD fundamentals fixture at fixture/eodhd_responses.json.
The FINANCE_HUB_FUNDAMENTALS_FIXTURE env var wires the EODHDAdapter so that
finance.fetch_fundamentals works without a live API key during the trial.

fin_fundamentals is intentionally empty — fetching and storing fundamentals is
the action under test for C1.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_EODHD_AAPL = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_aapl.json"
_NOW = "2026-06-23T12:00:00+00:00"


class _FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the fetch_fundamentals_fixture into trial_dir.

    Creates:
      trial_dir/db.sqlite                          — freshly migrated DB, AAPL candidate
      trial_dir/workspace/                         — empty workspace
      trial_dir/fixture/eodhd_responses.json       — recorded EODHD responses for AAPL

    Returns env overrides:
      FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE, FINANCE_HUB_FUNDAMENTALS_FIXTURE
    """
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)
    fixture_dir = trial_dir / "fixture"
    fixture_dir.mkdir(exist_ok=True)

    responses = {"AAPL": json.loads(_EODHD_AAPL.read_text())}
    responses_path = fixture_dir / "eodhd_responses.json"
    responses_path.write_text(json.dumps(responses))

    db_path = trial_dir / "db.sqlite"
    _setup_db(db_path)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
        "FINANCE_HUB_FUNDAMENTALS_FIXTURE": str(responses_path),
    }


def _setup_db(db_path: Path) -> None:
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.store import connection, migrations

    now_dt = datetime.fromisoformat(_NOW)
    old_db = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    old_clock = factories._clock

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    factories.set_clock(_FixedClock(now_dt))

    try:
        migrations.run()
        research.set_theme(key="theme_c1", display_name="Market Data Candidates")
        research.map_instruments(
            theme_key="theme_c1",
            instruments=[{
                "ticker": "AAPL",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "candidate",
                "display_name": "Apple Inc",
            }],
        )
    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
