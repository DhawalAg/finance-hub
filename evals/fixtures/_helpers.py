"""Shared fixture helpers — snapshot/plan ID renaming, price bar seeding."""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_CSV_SOURCE = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "fidelity_positions_sample.csv"


def run_migrations(db_path: Path) -> None:
    """Run finance-hub migrations on a fresh DB, restoring global DB_PATH after."""
    from finance_hub.store import connection, migrations

    old = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    try:
        migrations.run()
    finally:
        connection.DB_PATH = old
        connection._migrated_paths = set(old_migrated)


def copy_fidelity_csv(trial_dir: Path) -> Path:
    """Copy the Fidelity sample CSV into fixture/ subdirectory."""
    fixture_dir = trial_dir / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    dst = fixture_dir / "fidelity_sample.csv"
    shutil.copy2(_CSV_SOURCE, dst)
    return dst


def import_snapshot_as(
    db_path: Path,
    csv_path: Path,
    as_of: str,
    target_snapshot_id: str,
) -> str:
    """Import CSV into DB, then rename the auto-generated snapshot_id to target.

    Returns the target_snapshot_id.
    Uses raw sqlite3 (FK off) for the rename so the PK update succeeds.
    """
    from finance_hub import factories
    from finance_hub.store import connection
    from finance_hub.ingestion import tools as ingestion

    old = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))

    try:
        result = ingestion.import_portfolio_csv(csv_path=str(csv_path), as_of=as_of)
        old_id = result["snapshot_id"]
    finally:
        connection.DB_PATH = old
        connection._migrated_paths = set(old_migrated)

    if old_id != target_snapshot_id:
        with sqlite3.connect(db_path) as conn:
            # FK is OFF by default in raw sqlite3.connect
            conn.execute(
                "UPDATE fin_portfolio_positions SET snapshot_id = ? WHERE snapshot_id = ?",
                (target_snapshot_id, old_id),
            )
            conn.execute(
                "UPDATE fin_deployment_plans SET portfolio_snapshot_id = ? WHERE portfolio_snapshot_id = ?",
                (target_snapshot_id, old_id),
            )
            conn.execute(
                "UPDATE fin_portfolio_snapshots SET snapshot_id = ? WHERE snapshot_id = ?",
                (target_snapshot_id, old_id),
            )

    return target_snapshot_id


def rename_plan_id(db_path: Path, old_id: str, new_id: str) -> None:
    """Rename a plan_id in all plan-related tables (FK off via raw sqlite3)."""
    with sqlite3.connect(db_path) as conn:
        for table, col in [
            ("fin_deployment_plan_lines", "plan_id"),
            ("fin_deployment_plan_warnings", "plan_id"),
            ("fin_deployment_plan_evidence", "plan_id"),
            ("fin_deployment_plans", "plan_id"),
        ]:
            conn.execute(
                f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                (new_id, old_id),
            )


def seed_price_bars(
    db_path: Path,
    tickers: list[str],
    as_of_date: date,
    prices: dict[str, int],
    days: int = 60,
) -> None:
    """Seed synthetic daily price bars using a FixedProvider.

    prices: {ticker: close_micros}  — constant bar value for all days.
    Seeds `days` consecutive bars ending on as_of_date.
    """
    from finance_hub import factories
    from finance_hub.market_data.tools import DailyBarEnvelope, snapshot
    from finance_hub.store import connection

    now_str = as_of_date.isoformat() + "T12:00:00+00:00"

    @dataclass
    class _FixedProvider:
        bars_by_ticker: dict
        source: str = "yfinance"
        calls: list = field(default_factory=list)

        def fetch_daily_bars(self, tickers, *, start=None, end=None):
            self.calls.append(tuple(tickers))
            out = []
            for t in tickers:
                out.extend(self.bars_by_ticker.get(t, []))
            return out

    def _make_bar(ticker, session_date, close_micros):
        return DailyBarEnvelope(
            ticker=ticker,
            session_date=session_date,
            open_micros=close_micros,
            high_micros=close_micros,
            low_micros=close_micros,
            close_micros=close_micros,
            adj_close_micros=close_micros,
            volume=1_000_000,
            currency="USD",
            source="yfinance",
            first_fetched_at=now_str,
            last_refreshed_at=now_str,
        )

    bars_by_ticker = {}
    for ticker in tickers:
        price = prices.get(ticker, 200_000_000)
        bars_by_ticker[ticker] = [
            _make_bar(
                ticker,
                (as_of_date - timedelta(days=i)).isoformat(),
                price,
            )
            for i in range(days - 1, -1, -1)
        ]

    provider = _FixedProvider(bars_by_ticker=bars_by_ticker)
    factories.set_price_provider(provider)

    old = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    try:
        snapshot(tickers, as_of=as_of_date)
    finally:
        connection.DB_PATH = old
        connection._migrated_paths = set(old_migrated)
        factories.reset()


def seed_metrics(
    db_path: Path,
    tickers: list[str],
    benchmark_ticker: str,
    as_of_date: date,
) -> None:
    """Compute and store metrics from stored bars for given tickers."""
    from finance_hub.market_data import metrics as M
    from finance_hub.store import connection

    old = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    try:
        with connection.connect() as conn:
            spy_series = M.series_from_bars(conn, benchmark_ticker, "yfinance", as_of_date)
            for ticker in tickers:
                series = M.series_from_bars(conn, ticker, "yfinance", as_of_date)
                if not series:
                    continue
                mv = M.compute_ticker_metrics(
                    series,
                    ticker=ticker,
                    as_of=as_of_date,
                    source="yfinance",
                    benchmark_series=spy_series,
                    benchmark_ticker=benchmark_ticker,
                )
                M.store_metrics(conn, mv)
    finally:
        connection.DB_PATH = old
        connection._migrated_paths = set(old_migrated)
