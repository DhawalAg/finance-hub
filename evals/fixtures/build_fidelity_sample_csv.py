"""Fixture builder for 'fidelity_sample_csv' (used by R1, spec §5.2).

Builds an empty, freshly-migrated SQLite DB and places the sample CSV at
fixture/fidelity_sample.csv in the trial dir. No data is pre-seeded — CSV
import is the action under test.
"""
from __future__ import annotations

import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_CSV_SOURCE = _REPO_ROOT / "tests" / "fixtures" / "fidelity_positions_sample.csv"


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the fidelity_sample_csv fixture into trial_dir.

    Creates:
      trial_dir/db.sqlite                     — freshly migrated, empty SQLite DB
      trial_dir/workspace/                    — empty workspace dir
      trial_dir/fixture/fidelity_sample.csv   — the sample Fidelity CSV

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "workspace").mkdir(exist_ok=True)
    (trial_dir / "fixture").mkdir(exist_ok=True)

    shutil.copy2(_CSV_SOURCE, trial_dir / "fixture" / "fidelity_sample.csv")

    db_path = trial_dir / "db.sqlite"
    _run_migrations(db_path)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(trial_dir / "workspace"),
    }


def _run_migrations(db_path: Path) -> None:
    """Run finance-hub migrations against a fresh DB at db_path."""
    from finance_hub.store import connection, migrations

    old_db_path = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    try:
        migrations.run()
    finally:
        connection.DB_PATH = old_db_path
        connection._migrated_paths = set(old_migrated)
