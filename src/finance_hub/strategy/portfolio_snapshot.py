"""Canonical portfolio snapshot intake (ADR 0004).

``FidelityPortfolioCsvAdapter`` reads a Fidelity positions CSV and writes
immutable rows into ``fin_portfolio_snapshots`` / ``fin_portfolio_positions``.

Why an "adapter" boundary: the planner reads canonical snapshot rows, not
Fidelity-specific CSV shape. Future SnapTrade / brokerage-sync adapters
write the same canonical tables; nothing downstream changes.

Each call to ``import_csv`` produces a *new* snapshot row. Re-importing
the same file yields a distinct ``snapshot_id`` — prior snapshots are
never mutated (ADR 0004 immutability). Inside a single import,
``source_row_hash`` collapses duplicate lines.
"""
from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from finance_hub.money import to_micro_dollars
from finance_hub.store import connection

SOURCE_ADAPTER = "fidelity_csv"

# Fidelity "Type" column → canonical asset_type. Anything outside this map
# is preserved verbatim (lowercased) and treated as unsupported.
_SUPPORTED_ASSET_TYPES = {"stock", "etf"}
_FIDELITY_TYPE_MAP = {
    "etf": "etf",
    "stock": "stock",
    "stk": "stock",
    "common stock": "stock",
    "preferred stock": "preferred_stock",
    "mutual fund": "mutual_fund",
    "bond": "bond",
    "fixed income": "bond",
    "option": "option",
    "cash": "cash",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
}


@dataclass(frozen=True)
class _ParsedPosition:
    account_name: str
    account_type: str
    ticker: Optional[str]
    name: Optional[str]
    asset_type: str
    quantity: Optional[str]
    market_value_micros: Optional[int]
    cost_basis_micros: Optional[int]
    cash_value_micros: Optional[int]
    currency: str
    is_supported: bool
    source_row_hash: str


def _normalize_account_type(account_name: str) -> str:
    """Map a Fidelity account display name to a canonical account_type.

    Recommendations stay allocation-level (the planner never says which
    account receives a buy), but the spec still wants Roth/IRA/brokerage
    distinctions stored.
    """
    n = account_name.lower()
    if "roth" in n:
        return "roth_ira"
    if "ira" in n:
        return "ira"
    if "401" in n:
        return "401k"
    if "hsa" in n:
        return "hsa"
    if "529" in n:
        return "529"
    return "brokerage"


def _normalize_asset_type(raw: str) -> str:
    raw = (raw or "").strip().lower()
    return _FIDELITY_TYPE_MAP.get(raw, raw or "unknown")


def _clean_money(raw: str) -> Optional[str]:
    """Strip Fidelity's ``$`` and thousands separators; empty → None."""
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace(",", "")
    if s == "" or s in {"--", "n/a", "N/A"}:
        return None
    return s


def _money_to_micros(raw: str) -> Optional[int]:
    cleaned = _clean_money(raw)
    if cleaned is None:
        return None
    return to_micro_dollars(cleaned)


def _row_hash(account_name: str, ticker: str, quantity: str, market_value: str, cost_basis: str) -> str:
    """Stable hash of the row fields that identify a position within an import.

    We hash account+ticker+quantity+market_value+cost_basis so two truly
    identical lines collapse, but the same ticker held in two accounts
    (or at two different cost bases after a reinvestment) does not.
    """
    payload = "|".join((account_name, ticker, quantity, market_value, cost_basis))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_row(row: dict[str, str]) -> Optional[_ParsedPosition]:
    """Translate one Fidelity CSV row into a canonical position.

    Returns ``None`` for rows that don't represent a position (blank
    separator lines, footer totals).
    """
    account_name = (row.get("Account Name") or "").strip()
    ticker_raw = (row.get("Symbol") or "").strip()
    if not account_name and not ticker_raw:
        return None  # blank separator / footer line

    name = (row.get("Description") or "").strip() or None
    asset_type = _normalize_asset_type(row.get("Type") or "")
    quantity_raw = (row.get("Quantity") or "").strip()
    quantity = quantity_raw or None
    market_value_micros = _money_to_micros(row.get("Current Value") or "")
    cost_basis_micros = _money_to_micros(row.get("Cost Basis Total") or "")

    is_cash = asset_type == "cash"
    cash_value_micros = market_value_micros if is_cash else None
    if is_cash:
        # Cash rows carry value in ``cash_value`` and are intentionally
        # excluded from ``market_value`` weight math.
        market_value_micros = None

    is_supported = (
        asset_type in _SUPPORTED_ASSET_TYPES
        and bool(ticker_raw)
        and "." not in ticker_raw  # crude proxy for non-USD listings like .L / .TO
    )

    ticker = ticker_raw or None
    source_row_hash = _row_hash(
        account_name,
        ticker_raw,
        quantity_raw,
        row.get("Current Value") or "",
        row.get("Cost Basis Total") or "",
    )
    return _ParsedPosition(
        account_name=account_name,
        account_type=_normalize_account_type(account_name),
        ticker=ticker,
        name=name,
        asset_type=asset_type,
        quantity=quantity,
        market_value_micros=market_value_micros,
        cost_basis_micros=cost_basis_micros,
        cash_value_micros=cash_value_micros,
        currency="USD",
        is_supported=is_supported,
        source_row_hash=source_row_hash,
    )


class FidelityPortfolioCsvAdapter:
    """Read a Fidelity positions CSV and write a canonical snapshot."""

    source_adapter: str = SOURCE_ADAPTER

    def import_csv(self, csv_path: str | Path, *, as_of: str) -> str:
        """Import ``csv_path`` and return the new ``snapshot_id``.

        ``as_of`` is the user-supplied portfolio time the planner uses
        for freshness checks. The file path is recorded verbatim so the
        snapshot can be re-explained later.
        """
        path = Path(csv_path)
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            rows = [_parse_row(r) for r in reader]

        positions = [p for p in rows if p is not None]
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_portfolio_snapshots"
                " (snapshot_id, as_of, source_adapter, source_file, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (snapshot_id, as_of, self.source_adapter, str(path), created_at),
            )
            seen_hashes: set[str] = set()
            for p in positions:
                if p.source_row_hash in seen_hashes:
                    continue
                seen_hashes.add(p.source_row_hash)
                conn.execute(
                    """
                    INSERT INTO fin_portfolio_positions (
                        snapshot_id, account_name, account_type, ticker, name,
                        asset_type, quantity, market_value_micros,
                        cost_basis_micros, cash_value_micros, currency,
                        is_supported, source_row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        p.account_name,
                        p.account_type,
                        p.ticker,
                        p.name,
                        p.asset_type,
                        p.quantity,
                        p.market_value_micros,
                        p.cost_basis_micros,
                        p.cash_value_micros,
                        p.currency,
                        1 if p.is_supported else 0,
                        p.source_row_hash,
                    ),
                )
            conn.commit()
        return snapshot_id
