"""Fixture builder for 'dca_ready_deployment' (used by R5, spec §5.2).

Seeds a fully-ready DCA deployment fixture:
  - fin_themes: theme_r5 with VTI, QQQ, AAPL approved (with citations + thesis)
  - fin_strategy_versions: strat_r5_v1 (active)
  - fin_strategy_instruments: VTI→broad_market (70%), QQQ→broad_market, AAPL→single_stock (30%)
  - fin_portfolio_snapshots: snap_r5_fixture (as_of 2026-06-20T16:00:00+00:00)
  - fin_price_bars: 60 days for VTI, AAPL, QQQ, SPY (source=yfinance, up to 2026-06-20)
  - workspace/research/instruments/AAPL.md: stub thesis note
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from evals.fixtures._common import (
    _CSV_SOURCE,
    _FixedProvider,
    daily_bars,
    seed_context,
)

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
_NOW_STR = "2026-06-23T12:00:00+00:00"
_PRICE_AS_OF = date(2026, 6, 20)
_SNAP_AS_OF = "2026-06-20T16:00:00+00:00"

_AAPL_THESIS = """\
# AAPL Investment Thesis

Apple Inc (AAPL) represents a high-quality compounding business with exceptional capital returns.

Revenue growth: Services CAGR ~17% (5-year); hardware mature but sticky.
Services margin profile: ~71% gross margin vs ~36% hardware — accelerating mix shift.
Competitive moat: 2 billion active devices, tight ecosystem, high switching costs.
Capital return program: $110B+ annual buybacks; 12 consecutive years of dividend growth.
Key risks: China concentration (~17% of revenue), antitrust scrutiny, device saturation.

Sources: see linked citations in fin_research_source_links for scope=instrument, key=AAPL.
"""


def _make_provider() -> _FixedProvider:
    return _FixedProvider(bars_by_ticker={
        "VTI":  daily_bars("VTI",  242_100_000, _NOW_STR, _PRICE_AS_OF),
        "AAPL": daily_bars("AAPL", 190_500_000, _NOW_STR, _PRICE_AS_OF),
        "QQQ":  daily_bars("QQQ",  480_200_000, _NOW_STR, _PRICE_AS_OF),
        "SPY":  daily_bars("SPY",  540_000_000, _NOW_STR, _PRICE_AS_OF),
    })


def _seed_research(research, theme_key: str = "theme_r5") -> None:
    research.set_theme(key=theme_key, display_name="DCA Ready", status="watching")
    research.map_instruments(
        theme_key=theme_key,
        instruments=[
            {"ticker": "VTI", "type": "etf", "instrument_role": "broad_market_etf",
             "display_name": "Vanguard Total Stock Market ETF"},
            {"ticker": "QQQ", "type": "etf", "instrument_role": "broad_market_etf",
             "display_name": "Invesco QQQ Trust ETF"},
            {"ticker": "AAPL", "type": "stock", "instrument_role": "single_stock",
             "display_name": "Apple Inc"},
        ],
    )
    for ticker, conviction, note in [
        ("VTI",  5, "Total market core — essential DCA backbone"),
        ("QQQ",  3, "Tech-weighted complement to VTI"),
        ("AAPL", 3, "Quality single-stock allocation"),
    ]:
        research.review_instrument(
            theme_key=theme_key, ticker=ticker, status="approved",
            rationale=f"{ticker} research basis",
            conviction=conviction,
            conviction_note=note,
        )
    for ticker in ("VTI", "QQQ", "AAPL"):
        s1 = research.upsert_source(
            url=f"https://example.com/{ticker.lower()}-1", title=f"{ticker} source 1"
        )
        research.link_source(source_id=s1["id"], scope="instrument", key=ticker)
        s2 = research.upsert_source(
            url=f"https://example.com/{ticker.lower()}-2", title=f"{ticker} source 2"
        )
        research.link_source(source_id=s2["id"], scope="instrument", key=ticker)
    research.set_research_note(scope="instrument", key="AAPL", body=_AAPL_THESIS)


def _seed_strategy(strategy, version_id: str = "strat_r5_v1", theme_key: str = "theme_r5") -> None:
    strategy.promote_to_strategy(
        version_id=version_id,
        label=f"DCA Ready {version_id}",
        status="active",
        confirm=True,
        sleeves=[
            {"sleeve_key": "broad_market", "target_weight_pct": 70},
            {"sleeve_key": "single_stock", "target_weight_pct": 30},
        ],
        instruments=[
            {"ticker": "VTI",  "primary_sleeve_key": "broad_market", "source_theme_key": theme_key},
            {"ticker": "QQQ",  "primary_sleeve_key": "broad_market", "source_theme_key": theme_key},
            {"ticker": "AAPL", "primary_sleeve_key": "single_stock", "source_theme_key": theme_key},
        ],
    )


def import_snapshot_with_id(snap_suffix: str) -> str:
    """Import CSV with uuid patched so snapshot_id = f'snap_{snap_suffix}'."""
    from finance_hub.strategy.portfolio_snapshot import FidelityPortfolioCsvAdapter

    mock_uuid = MagicMock()
    mock_uuid.hex = snap_suffix  # hex[:12] returns suffix as-is when len < 12
    target = "finance_hub.strategy.portfolio_snapshot.uuid.uuid4"
    with patch(target, return_value=mock_uuid):
        return FidelityPortfolioCsvAdapter().import_csv(_CSV_SOURCE, as_of=_SNAP_AS_OF)


def build(trial_dir: Path) -> dict[str, str]:
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    (workspace / "research" / "instruments").mkdir(parents=True, exist_ok=True)

    db_path = trial_dir / "db.sqlite"

    with seed_context(db_path, workspace, _NOW, _make_provider()):
        from finance_hub.store import migrations
        from finance_hub.research import tools as research
        from finance_hub.strategy import tools as strategy
        from finance_hub.market_data.tools import snapshot

        migrations.run()
        _seed_research(research)
        _seed_strategy(strategy)
        import_snapshot_with_id("r5_fixture")
        snapshot(["VTI", "AAPL", "QQQ", "SPY"], as_of=_PRICE_AS_OF)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
