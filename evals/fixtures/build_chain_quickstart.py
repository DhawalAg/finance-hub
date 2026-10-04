"""Fixture builder for 'chain_quickstart' (used by R7, spec §5.2).

Seeds the minimum state for the full CSV→approved-plan chain:
  - fin_themes: theme_chain (status=exploring)
  - fin_theme_instruments: VTI, AAPL, QQQ as candidates (not yet approved)
  - fin_research_sources + links: ≥2 active source links per instrument (pre-seeded)
  - fin_instruments.note_path set for AAPL
  - workspace/research/instruments/AAPL.md: stub thesis note
  - fin_price_bars: 60 days for VTI, AAPL, QQQ, SPY (up to 2026-06-20)
  - fixture/fidelity_sample.csv: CSV for the agent to import

NOT pre-seeded: portfolio snapshot, strategy version, deployment plan.
"""
from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from evals.fixtures._common import _CSV_SOURCE, seed_context
from evals.fixtures.build_dca_ready_deployment import _AAPL_THESIS, _make_provider

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
_PRICE_AS_OF = date(2026, 6, 20)


def build(trial_dir: Path) -> dict[str, str]:
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

    fixture_dir = trial_dir / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    shutil.copy2(_CSV_SOURCE, fixture_dir / "fidelity_sample.csv")

    db_path = trial_dir / "db.sqlite"

    with seed_context(db_path, workspace, _NOW, _make_provider()):
        from finance_hub.store import migrations
        from finance_hub.research import tools as research
        from finance_hub.market_data.tools import snapshot

        migrations.run()

        research.set_theme(
            key="theme_chain", display_name="Chain Quickstart", status="exploring"
        )
        research.map_instruments(
            theme_key="theme_chain",
            instruments=[
                {"ticker": "VTI", "type": "etf", "instrument_role": "broad_market_etf",
                 "display_name": "Vanguard Total Stock Market ETF"},
                {"ticker": "QQQ", "type": "etf", "instrument_role": "broad_market_etf",
                 "display_name": "Invesco QQQ Trust ETF"},
                {"ticker": "AAPL", "type": "stock", "instrument_role": "single_stock",
                 "display_name": "Apple Inc"},
            ],
        )
        # Pre-seed citations for all three (required for AAPL DCA eligibility later)
        for ticker in ("VTI", "QQQ", "AAPL"):
            s1 = research.upsert_source(
                url=f"https://example.com/{ticker.lower()}-chain-1",
                title=f"{ticker} chain source 1",
            )
            research.link_source(source_id=s1["id"], scope="instrument", key=ticker)
            s2 = research.upsert_source(
                url=f"https://example.com/{ticker.lower()}-chain-2",
                title=f"{ticker} chain source 2",
            )
            research.link_source(source_id=s2["id"], scope="instrument", key=ticker)
        # Pre-seed AAPL thesis (required for DCA eligibility at plan-generation time)
        research.set_research_note(scope="instrument", key="AAPL", body=_AAPL_THESIS)

        snapshot(["VTI", "AAPL", "QQQ", "SPY"], as_of=_PRICE_AS_OF)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
