"""Registered tool: finance.import_portfolio_csv.

Wraps FidelityPortfolioCsvAdapter with auto-as_of extraction from the CSV
download line and returns a rich summary of what landed in the snapshot.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from finance_hub.runtime.registry import tool
from finance_hub.store import connection
from finance_hub.strategy.portfolio_snapshot import (
    FidelityPortfolioCsvAdapter,
    parse_date_downloaded,
)


def _find_date_downloaded(path: Path) -> Optional[datetime]:
    """Scan a Fidelity CSV file for the 'Date downloaded' line and parse it.

    Returns a timezone-aware datetime or None if no such line is found.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip().strip('"')
        if stripped.startswith("Date downloaded"):
            try:
                return parse_date_downloaded(stripped)
            except ValueError:
                continue
    return None


def _count_skipped_pending(path: Path) -> int:
    """Count 'Pending activity' rows the adapter skips.

    Fidelity may carry the marker in either the Symbol or the Description
    column, so check both — matching the adapter's own skip rule.
    """
    count = 0
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            account_name = (row.get("Account Name") or "").strip()
            ticker_raw = (row.get("Symbol") or "").strip()
            if not account_name and not ticker_raw:
                continue  # blank / footer rows
            description = (row.get("Description") or "").strip()
            if "pending" in description.lower() or "pending" in ticker_raw.lower():
                count += 1
    return count


def _sorted_tickers(rows, predicate) -> list[str]:
    """Distinct, sorted, non-empty tickers among ``rows`` matching ``predicate``."""
    return sorted({r["ticker"] for r in rows if r["ticker"] and predicate(r)})


@tool(
    name="finance.import_portfolio_csv",
    description=(
        "Import a Fidelity portfolio CSV into a new immutable snapshot. "
        "Auto-extracts as_of from the 'Date downloaded' line in the CSV; "
        "an explicit as_of argument overrides it. Raises if no timestamp is "
        "available — never silently stamps 'now'. Returns: snapshot_id, "
        "as_of, as_of_source (csv_download_timestamp | explicit_override), "
        "and supported / cash / unsupported / skipped buckets with tickers."
    ),
)
def import_portfolio_csv(
    *, csv_path: str, as_of: Optional[str] = None
) -> dict:
    path = Path(csv_path)

    if as_of is not None:
        effective_as_of = as_of
        as_of_source = "explicit_override"
    else:
        dt = _find_date_downloaded(path)
        if dt is None:
            raise ValueError(
                "no 'Date downloaded' line found in the CSV and no as_of provided; "
                "pass an explicit as_of= to avoid silently stamping 'now'"
            )
        effective_as_of = dt.isoformat()
        as_of_source = "csv_download_timestamp"

    skipped_count = _count_skipped_pending(path)

    adapter = FidelityPortfolioCsvAdapter()
    snapshot_id = adapter.import_csv(path, as_of=effective_as_of)

    with connection.connect() as conn:
        positions = conn.execute(
            "SELECT ticker, asset_type, is_supported"
            " FROM fin_portfolio_positions WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchall()

    supported = _sorted_tickers(positions, lambda r: r["is_supported"])
    cash = _sorted_tickers(positions, lambda r: r["asset_type"] == "cash")
    unsupported = _sorted_tickers(
        positions, lambda r: not r["is_supported"] and r["asset_type"] != "cash"
    )

    return {
        "snapshot_id": snapshot_id,
        "as_of": effective_as_of,
        "as_of_source": as_of_source,
        "buckets": {
            "supported": {"count": len(supported), "tickers": supported},
            "cash": {"count": len(cash), "tickers": cash},
            "unsupported": {"count": len(unsupported), "tickers": unsupported},
            "skipped": {"count": skipped_count, "tickers": []},
        },
    }
