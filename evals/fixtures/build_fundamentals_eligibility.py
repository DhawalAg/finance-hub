"""Fixture builder for 'fundamentals_eligibility' (used by C2, spec §5.2).

Builds a DB with AAPL:
- Approved single_stock candidate in theme_c2 (conviction + note)
- Thesis note in workspace/research/instruments/AAPL.md
- Two source links (DCA eligibility)
- 8 fundamentals rows pre-seeded from EODHD fixture (one-time eligibility)
- Active strategy strat_c2_v1 with AAPL in the single_stock sleeve
- Portfolio snapshot snap_c2_fixture with AAPL position
- One price bar for AAPL (2026-06-22, $185.00)

No live fundamentals provider needed — fundamentals are pre-seeded.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_EODHD_AAPL = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_aapl.json"
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
    """Materialise the fundamentals_eligibility fixture into trial_dir.

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
    from finance_hub.market_data.fundamentals import normalize_eodhd, store_fundamentals
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

        # 1. Research: theme + approved candidate
        research.set_theme(key="theme_c2", display_name="Quality Growth")
        research.map_instruments(
            theme_key="theme_c2",
            instruments=[{
                "ticker": "AAPL",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "display_name": "Apple Inc",
                "conviction": 4,
                "conviction_note": "Quality franchise with durable margins",
                "rationale": "Approved core single-stock holding",
            }],
        )

        # 2. Thesis note (required for single_stock DCA eligibility)
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

        # 3. Sources (citations required for single_stock DCA eligibility)
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
        research.link_source(
            source_id=src1["id"], scope="instrument", key="AAPL"
        )
        research.link_source(
            source_id=src2["id"], scope="instrument", key="AAPL"
        )

        # 4. Pre-seed fundamentals from EODHD fixture
        raw_aapl = json.loads(_EODHD_AAPL.read_text())
        aapl_records = normalize_eodhd(raw_aapl)
        with connection.connect() as conn:
            store_fundamentals(conn, "AAPL", aapl_records, fetched_at=_NOW)

        # 5. Strategy: promote + activate
        strategy.promote_to_strategy(
            version_id="strat_c2_v1",
            label="Quality Growth v1",
            confirm=True,
            sleeves=[{"sleeve_key": "single_stock", "target_weight_pct": 100}],
            instruments=[{
                "ticker": "AAPL",
                "primary_sleeve_key": "single_stock",
                "source_theme_key": "theme_c2",
            }],
        )
        strategy.activate_strategy(version_id="strat_c2_v1", confirm=True)

        # 6. Portfolio snapshot + AAPL position
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots "
                "(snapshot_id, as_of, source_adapter, source_file, created_at) "
                "VALUES (?,?,?,?,?)",
                ("snap_c2_fixture", _SNAP_AS_OF, "fidelity_csv", "fixture/c2.csv", _NOW),
            )
            conn.execute(
                "INSERT INTO fin_portfolio_positions "
                "(snapshot_id, account_name, account_type, account_registration, "
                " ticker, name, asset_type, quantity, market_value_micros, "
                " cost_basis_micros, currency, is_supported, source_row_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("snap_c2_fixture", "Individual Brokerage", "brokerage", "cash",
                 "AAPL", "Apple Inc", "stock", "10",
                 1850000000, 1500000000, "USD", 1,
                 _pos_hash("Individual Brokerage", "AAPL", "10", "1850.00", "1500.00")),
            )
            conn.commit()

        # 7. Price bar for AAPL
        with connection.connect() as conn:
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
