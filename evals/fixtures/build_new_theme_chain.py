"""Fixture builder for 'new_theme_chain' (used by C6, spec §5.2).

Builds a fresh DB with price bars and a portfolio snapshot but no themes,
instruments, or strategy. The agent builds everything from scratch:
  1. Create a theme via finance.set_theme
  2. Add instruments via finance.map_instruments
  3. Review + approve via finance.review_instrument
  4. Promote to strategy via finance.promote_to_strategy
  5. Generate a DCA plan via finance.generate_deployment_plan

What the fixture contains:
  - fin_themes: 0 rows (no themes — agent creates them)
  - fin_instruments: 0 rows (no instruments — agent maps them)
  - fin_strategy_versions: 0 rows (no strategy — agent promotes)
  - fin_price_bars: VTI ($242.00, 2026-06-22) + AAPL ($185.00, 2026-06-22)
  - fin_portfolio_snapshots: snap_c6_fixture (as_of 2026-06-20T16:00:00+00:00)
  - fin_portfolio_positions: VTI (25 sh, $6,052.50) + AAPL (10 sh, $1,850.00)
  - workspace/: empty research dir

Price bars and snapshot are pre-seeded so the agent can call
generate_deployment_plan after completing the research → promotion chain.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

VERSION = "1"

_NOW = "2026-06-23T12:00:00+00:00"
_SNAP_AS_OF = "2026-06-20T16:00:00+00:00"
_PRICE_DATE = "2026-06-22"


class _FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def _pos_hash(account_name: str, ticker: str, quantity: str, market_value: str = "", cost_basis: str = "") -> str:
    payload = "|".join((account_name, ticker, quantity, market_value, cost_basis))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the new_theme_chain fixture into trial_dir."""
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

        # Workspace research dirs (empty — agent creates notes as part of the chain)
        (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

        # Price bars for VTI + AAPL (required for plan generation at the end of the chain)
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_price_bars "
                "(ticker, session_date, close_micros, currency, source, "
                " first_fetched_at, last_refreshed_at) VALUES (?,?,?,?,?,?,?)",
                ("VTI", _PRICE_DATE, 242_000_000, "USD", "fixture", _NOW, _NOW),
            )
            conn.execute(
                "INSERT INTO fin_price_bars "
                "(ticker, session_date, close_micros, currency, source, "
                " first_fetched_at, last_refreshed_at) VALUES (?,?,?,?,?,?,?)",
                ("AAPL", _PRICE_DATE, 185_000_000, "USD", "fixture", _NOW, _NOW),
            )
            conn.commit()

        # Portfolio snapshot + positions (required for plan generation)
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES (?,?,?,?,?)",
                ("snap_c6_fixture", _SNAP_AS_OF, "fidelity_csv", "fixture/c6.csv", _NOW),
            )
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, account_registration, "
                " ticker, name, asset_type, quantity, market_value_micros, "
                " cost_basis_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("snap_c6_fixture", "Individual Brokerage", "brokerage", "cash",
                 "VTI", "Vanguard Total Stock Market ETF", "etf", "25",
                 6052500000, 4800000000, "USD", 1,
                 _pos_hash("Individual Brokerage", "VTI", "25", "6052.50", "4800.00")),
            )
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, account_registration, "
                " ticker, name, asset_type, quantity, market_value_micros, "
                " cost_basis_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("snap_c6_fixture", "Individual Brokerage", "brokerage", "cash",
                 "AAPL", "Apple Inc", "stock", "10",
                 1850000000, 1500000000, "USD", 1,
                 _pos_hash("Individual Brokerage", "AAPL", "10", "1850.00", "1500.00")),
            )
            conn.commit()

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
        if old_workspace_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_workspace_env
