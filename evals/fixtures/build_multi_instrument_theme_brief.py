"""Fixture builder for 'multi_instrument_theme_brief' (used by C4, spec §5.2).

Builds a DB with VTI + AAPL both approved in theme_c4:
- fin_themes: theme_c4 (status=watching, display_name="Quality Compounders")
- fin_instruments: VTI (etf/broad_market_etf, approved, conviction=5)
                   AAPL (stock/single_stock, approved, conviction=4)
- fin_research_sources + fin_research_source_links: 2 active links per instrument
- fin_fundamentals: 8 AAPL rows + ≥1 VTI rows (both pre-seeded from EODHD fixture)
- workspace/research/instruments/AAPL.md: thesis note for AAPL
- workspace/research/instruments/VTI.md: brief rationale for VTI
- workspace/research/themes/theme_c4.md: theme brief stub

Agent task (C4): synthesize a multi-instrument research brief for theme_c4,
citing evidence from source links for each instrument. Judge-graded.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

VERSION = "1"

_REPO_ROOT = Path(__file__).parent.parent.parent
_EODHD_AAPL = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_aapl.json"
_EODHD_SPY = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_spy.json"
_NOW = "2026-06-23T12:00:00+00:00"


class _FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the multi_instrument_theme_brief fixture into trial_dir."""
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

        # 1. Theme + approved instruments
        research.set_theme(key="theme_c4", display_name="Quality Compounders")
        research.map_instruments(
            theme_key="theme_c4",
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
                    "conviction_note": "Quality franchise with durable margins and ecosystem lock-in",
                    "rationale": "Core single-stock holding; differentiated by services growth",
                },
            ],
        )

        # 2. AAPL thesis note
        instruments_dir = workspace / "research" / "instruments"
        instruments_dir.mkdir(parents=True, exist_ok=True)
        research.set_research_note(
            scope="instrument",
            key="AAPL",
            body=(
                "# AAPL — Investment Thesis\n\n"
                "Apple's ecosystem moat and services revenue diversification support "
                "above-average margins. The installed base of 2B+ devices creates switching "
                "costs that sustain pricing power. Services segment growing at 12% YoY.\n\n"
                "Conviction: 4/5. Key risk: regulatory pressure on App Store economics.\n"
            ),
        )

        # 3. VTI research note
        research.set_research_note(
            scope="instrument",
            key="VTI",
            body=(
                "# VTI — ETF Rationale\n\n"
                "Vanguard Total Stock Market ETF provides broad U.S. equity exposure at 0.03% "
                "expense ratio. Market-cap weighted; auto-rebalances as the market evolves. "
                "Conviction: 5/5. No single-stock risk; lowest-cost implementation.\n"
            ),
        )

        # 4. Source links for AAPL (2 active)
        aapl_src1 = research.upsert_source(
            url="https://example.com/aapl-10k-2025",
            title="AAPL 10-K FY2025",
            source_type="filing",
        )
        aapl_src2 = research.upsert_source(
            url="https://example.com/aapl-services-analysis",
            title="Apple Services Revenue Analysis",
            source_type="analysis",
        )
        research.link_source(source_id=aapl_src1["id"], scope="instrument", key="AAPL")
        research.link_source(source_id=aapl_src2["id"], scope="instrument", key="AAPL")

        # 5. Source links for VTI (2 active)
        vti_src1 = research.upsert_source(
            url="https://example.com/vti-factsheet",
            title="VTI Fund Fact Sheet",
            source_type="prospectus",
        )
        vti_src2 = research.upsert_source(
            url="https://example.com/total-market-study",
            title="Total Market Index Performance Study",
            source_type="analysis",
        )
        research.link_source(source_id=vti_src1["id"], scope="instrument", key="VTI")
        research.link_source(source_id=vti_src2["id"], scope="instrument", key="VTI")

        # 6. Pre-seed fundamentals: AAPL (8 rows) + VTI (ETF fixture rows)
        raw_aapl = json.loads(_EODHD_AAPL.read_text())
        aapl_records = normalize_eodhd(raw_aapl)
        raw_vti = json.loads(_EODHD_SPY.read_text())
        vti_records = normalize_eodhd(raw_vti)
        with connection.connect() as conn:
            store_fundamentals(conn, "AAPL", aapl_records, fetched_at=_NOW)
            store_fundamentals(conn, "VTI", vti_records, fetched_at=_NOW)

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
        if old_workspace_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_workspace_env
