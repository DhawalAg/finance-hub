"""Fixture builder for 'approved_candidates_ready_for_promotion' (used by R4).

Seeds:
  - fin_themes: theme_r4 (status=watching, display_name='Core Equities')
  - fin_theme_instruments: VTI, QQQ, AAPL — all approved with conviction+note
  - fin_instruments.note_path set for AAPL
  - workspace/research/instruments/AAPL.md: stub thesis note
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from evals.fixtures._common import seed_context

_CLOCK = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

_AAPL_STUB_THESIS = """\
# AAPL Research Thesis — Stub

Apple Inc is a candidate in theme_r4 (Core Equities).

Revenue growth trajectory: Services CAGR ~17% over 5 years, hardware mature.
Services margin profile: ~71% gross margin vs ~36% hardware — high-quality mix shift.
Competitive moat: ecosystem lock-in; 2 billion active devices; high switching costs.
Capital returns: $110B+ annual buybacks; 12 consecutive years of dividend growth.
Key risks: China revenue concentration (~17%), regulatory antitrust pressure, device saturation.

This stub thesis meets the minimum presence bar for DCA eligibility in later tasks.
"""


def build(trial_dir: Path) -> dict[str, str]:
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

    db_path = trial_dir / "db.sqlite"

    with seed_context(db_path, workspace, _CLOCK):
        from finance_hub.store import migrations
        migrations.run()

        from finance_hub.research import tools as research

        research.set_theme(key="theme_r4", display_name="Core Equities", status="watching")
        research.map_instruments(
            theme_key="theme_r4",
            instruments=[
                {"ticker": "VTI", "type": "etf", "instrument_role": "broad_market_etf",
                 "display_name": "Vanguard Total Stock Market ETF"},
                {"ticker": "QQQ", "type": "etf", "instrument_role": "broad_market_etf",
                 "display_name": "Invesco QQQ Trust ETF"},
                {"ticker": "AAPL", "type": "stock", "instrument_role": "single_stock",
                 "display_name": "Apple Inc"},
            ],
        )
        research.review_instrument(
            theme_key="theme_r4", ticker="VTI", status="approved",
            rationale="Total market core at lowest cost — essential DCA backbone.",
            conviction=5,
            conviction_note="Total market at lowest cost — essential DCA backbone",
        )
        research.review_instrument(
            theme_key="theme_r4", ticker="QQQ", status="approved",
            rationale="Acceptable tech tilt; diversification at 30% of broad sleeve.",
            conviction=3,
            conviction_note="Acceptable tech tilt; diversification at 30% of broad sleeve",
        )
        research.review_instrument(
            theme_key="theme_r4", ticker="AAPL", status="approved",
            rationale="Services growth offsets hardware saturation risk.",
            conviction=3,
            conviction_note="Services growth offsets hardware saturation risk",
        )
        research.set_research_note(
            scope="instrument", key="AAPL", body=_AAPL_STUB_THESIS
        )

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
