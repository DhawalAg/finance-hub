"""Fixture builder for 'dca_ready_no_fundamentals' (used by C7, spec §5.2).

Builds a DB with VTI + AAPL DCA-eligible but NO fundamentals rows.
This fixture is the negative counterpart to one_time_ready_deployment (C3):
- Same research, strategy, snapshot, and price structure as C3.
- fin_fundamentals is intentionally empty — no provider data exists.
  A one-time buy recommendation requires fundamentals; the agent must refuse
  or report MISSING_FUNDAMENTALS rather than inventing valuation data.

Components:
- Approved instruments in theme_c7: VTI (broad_market_etf) + AAPL (single_stock)
- AAPL: thesis note + two source links (DCA eligibility maintained)
- Active strategy strat_c7_v1: VTI (broad_market 70%) + AAPL (single_stock 30%)
- Portfolio snapshot snap_c7_fixture with VTI + AAPL positions
- Price bars for VTI + AAPL (DCA plan generation requires prices)
- fin_fundamentals: 0 rows (no one-time eligibility)
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
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
    """Materialise the dca_ready_no_fundamentals fixture into trial_dir.

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
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
    from finance_hub.strategy import tools as strategy
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

        # 1. Research: theme + approved instruments
        research.set_theme(key="theme_c7", display_name="Quality Growth + ETF Mix")
        research.map_instruments(
            theme_key="theme_c7",
            instruments=[
                {
                    "ticker": "VTI",
                    "type": "etf",
                    "instrument_role": "broad_market_etf",
                    "status": "approved",
                    "display_name": "Vanguard Total Stock Market ETF",
                    "conviction": 5,
                    "conviction_note": "Total market at lowest cost — essential DCA backbone",
                },
                {
                    "ticker": "AAPL",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "status": "approved",
                    "display_name": "Apple Inc",
                    "conviction": 4,
                    "conviction_note": "Quality franchise with durable margins",
                    "rationale": "Approved core single-stock holding",
                },
            ],
        )

        # 2. AAPL thesis note (required for single_stock DCA eligibility)
        (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)
        research.set_research_note(
            scope="instrument",
            key="AAPL",
            body=(
                "# AAPL — Investment Thesis\n\n"
                "Apple's ecosystem moat and services revenue diversification "
                "support above-average margins. Conviction: 4/5.\n"
            ),
        )

        # 3. Source links for AAPL (citations required for single_stock DCA eligibility)
        src1 = research.upsert_source(
            url="https://example.com/aapl-thesis",
            title="AAPL Thesis Note",
            source_type="analysis",
        )
        src2 = research.upsert_source(
            url="https://example.com/aapl-10k",
            title="AAPL 10-K 2025",
            source_type="filing",
        )
        research.link_source(source_id=src1["id"], scope="instrument", key="AAPL")
        research.link_source(source_id=src2["id"], scope="instrument", key="AAPL")

        # 4. NO fundamentals seeded — this is the key invariant for C7.
        #    fin_fundamentals remains 0 rows after fixture build.

        # 5. Strategy: promote + activate
        strategy.promote_to_strategy(
            version_id="strat_c7_v1",
            label="Quality Growth + ETF Mix v1",
            confirm=True,
            sleeves=[
                {"sleeve_key": "broad_market", "target_weight_pct": 70},
                {"sleeve_key": "single_stock", "target_weight_pct": 30},
            ],
            instruments=[
                {
                    "ticker": "VTI",
                    "primary_sleeve_key": "broad_market",
                    "source_theme_key": "theme_c7",
                },
                {
                    "ticker": "AAPL",
                    "primary_sleeve_key": "single_stock",
                    "source_theme_key": "theme_c7",
                },
            ],
        )
        strategy.activate_strategy(version_id="strat_c7_v1", confirm=True)

        # 6. Portfolio snapshot + VTI + AAPL positions
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES (?,?,?,?,?)",
                ("snap_c7_fixture", _SNAP_AS_OF, "fidelity_csv", "fixture/c7.csv", _NOW),
            )
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, account_registration, "
                " ticker, name, asset_type, quantity, market_value_micros, "
                " cost_basis_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("snap_c7_fixture", "Individual Brokerage", "brokerage", "cash",
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
                ("snap_c7_fixture", "Individual Brokerage", "brokerage", "cash",
                 "AAPL", "Apple Inc", "stock", "10",
                 1850000000, 1500000000, "USD", 1,
                 _pos_hash("Individual Brokerage", "AAPL", "10", "1850.00", "1500.00")),
            )
            conn.commit()

        # 7. Price bars for VTI + AAPL (required for DCA plan generation)
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

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
        if old_workspace_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_workspace_env
