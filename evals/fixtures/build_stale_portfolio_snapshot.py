"""Fixture builder for 'stale_portfolio_snapshot' (used by R9).

Seeds a fully-equipped strategy (strat_r9_v1) with a portfolio snapshot that is
20 days old relative to FINANCE_HUB_NOW=2026-07-10. Price bars and metrics are
current. generate_deployment_plan will produce a PORTFOLIO_SNAPSHOT_STALE warning
(status=proposed_with_warnings) and block one-time buys.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the stale_portfolio_snapshot fixture.

    Seed steps (as_of date is 2026-06-20, now=2026-07-10 → 20 days old → stale):
      1. migrations.run() on a fresh DB
      2. set_theme(key='theme_r9', ...) + map VTI, QQQ, AAPL
      3. review_instrument: approve all with conviction + note; AAPL gets thesis + sources
      4. promote_to_strategy(strat_r9_v1: broad_market 70% [VTI+QQQ], single_stock 30% [AAPL])
      5. activate_strategy(strat_r9_v1)
      6. import snapshot at as_of='2026-06-20T16:00:00+00:00' → rename to 'snap_r9_fixture'
      7. seed 60 days of price bars for VTI, AAPL, QQQ, SPY up to 2026-07-10
      8. compute and store metrics for VTI, AAPL, QQQ

    Returns env overrides: FINANCE_HUB_DB, FINANCE_HUB_WORKSPACE.
    """
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.strategy import tools as strategy
    from finance_hub.store import connection, migrations
    from evals.fixtures._helpers import (
        copy_fidelity_csv,
        import_snapshot_as,
        run_migrations,
        seed_metrics,
        seed_price_bars,
    )

    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    old_db = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    factories.reset()

    try:
        migrations.run()

        research.set_theme(key="theme_r9", display_name="Core Balanced", status="watching")
        research.map_instruments(
            theme_key="theme_r9",
            instruments=[
                {
                    "ticker": "VTI",
                    "type": "etf",
                    "instrument_role": "broad_market_etf",
                    "display_name": "Vanguard Total Stock Market ETF",
                },
                {
                    "ticker": "QQQ",
                    "type": "etf",
                    "instrument_role": "broad_market_etf",
                    "display_name": "Invesco QQQ Trust ETF",
                },
                {
                    "ticker": "AAPL",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "display_name": "Apple Inc",
                },
            ],
        )
        research.review_instrument(
            theme_key="theme_r9",
            ticker="VTI",
            status="approved",
            rationale="Total market core holding",
            conviction=5,
            conviction_note="Total market ETF — lowest cost broad market exposure",
        )
        research.review_instrument(
            theme_key="theme_r9",
            ticker="QQQ",
            status="approved",
            rationale="Tech-tilted ETF for growth sleeve",
            conviction=3,
            conviction_note="Acceptable tech concentration; diversified within growth sleeve",
        )
        research.review_instrument(
            theme_key="theme_r9",
            ticker="AAPL",
            status="approved",
            rationale="Services growth offsets hardware saturation; strong FCF",
            conviction=4,
            conviction_note="Services flywheel + premium hardware position; recurring revenue moat",
        )
        research.set_research_note(
            scope="instrument",
            key="AAPL",
            body="# AAPL Thesis\nServices segment generating recurring revenue. "
                "Premium hardware ecosystem with high switching costs.",
        )
        src1 = research.upsert_source(
            url="https://example.com/aapl-services-r9",
            title="AAPL Services Growth Thesis",
        )
        research.link_source(source_id=src1["id"], scope="instrument", key="AAPL")
        src2 = research.upsert_source(
            url="https://example.com/aapl-earnings-r9",
            title="AAPL Q2 2026 Earnings",
        )
        research.link_source(source_id=src2["id"], scope="instrument", key="AAPL")

        strategy.promote_to_strategy(
            version_id="strat_r9_v1",
            label="Core Balanced",
            sleeves=[
                {"sleeve_key": "broad_market", "target_weight_pct": 70},
                {"sleeve_key": "single_stock", "target_weight_pct": 30},
            ],
            instruments=[
                {"ticker": "VTI", "primary_sleeve_key": "broad_market", "source_theme_key": "theme_r9"},
                {"ticker": "QQQ", "primary_sleeve_key": "broad_market", "source_theme_key": "theme_r9"},
                {"ticker": "AAPL", "primary_sleeve_key": "single_stock", "source_theme_key": "theme_r9"},
            ],
            confirm=True,
        )
        strategy.activate_strategy(version_id="strat_r9_v1", confirm=True)

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories.reset()

    # Import snapshot (20 days before now=2026-07-10 → stale band 15-30 days)
    csv_path = copy_fidelity_csv(trial_dir)
    import_snapshot_as(
        db_path=db_path,
        csv_path=csv_path,
        as_of="2026-06-20T16:00:00+00:00",
        target_snapshot_id="snap_r9_fixture",
    )

    # Seed 60 days of price bars up to 2026-07-10 (now date for this task)
    as_of_date = date(2026, 7, 10)
    seed_price_bars(
        db_path=db_path,
        tickers=["VTI", "AAPL", "QQQ", "SPY"],
        as_of_date=as_of_date,
        prices={
            "VTI": 242_100_000,   # $242.10
            "AAPL": 190_500_000,  # $190.50
            "QQQ": 480_200_000,   # $480.20
            "SPY": 540_000_000,   # $540.00
        },
    )

    seed_metrics(
        db_path=db_path,
        tickers=["VTI", "AAPL", "QQQ"],
        benchmark_ticker="SPY",
        as_of_date=as_of_date,
    )

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }
