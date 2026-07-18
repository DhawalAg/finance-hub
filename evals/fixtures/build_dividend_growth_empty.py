"""Fixture builder for 'dividend_growth_empty' (used by R2, spec §5.2).

Builds a freshly-migrated SQLite DB with no themes or instruments pre-seeded.
The agent creates theme + instruments + reviews from scratch.
"""
from __future__ import annotations

from pathlib import Path


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the dividend_growth_empty fixture into trial_dir.

    Creates:
      trial_dir/db.sqlite     — freshly migrated, empty SQLite DB
      trial_dir/workspace/    — empty workspace dir

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    _run_migrations(db_path)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }


def _run_migrations(db_path: Path) -> None:
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
