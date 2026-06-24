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
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from finance_hub.money import to_micro_dollars
from finance_hub.store import connection

SOURCE_ADAPTER = "fidelity_csv"

_SUPPORTED_ASSET_TYPES = {"stock", "etf"}

# Month abbreviations used in Fidelity's "Date downloaded" line.
_MONTH_ABBR: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# The meridiem's trailing period is optional: real Fidelity exports write
# "6:29 p.m ET" while the documented form is "10:30 a.m. ET". Match either,
# case-insensitively, and key the AM/PM decision off the leading letter.
_DATE_DOWNLOADED_RE = re.compile(
    r'Date downloaded\s+([A-Za-z]+)-(\d{1,2})-(\d{4})'
    r'\s+(\d{1,2}):(\d{2})\s+([ap])\.m\.?\s+ET',
    re.IGNORECASE,
)


def parse_date_downloaded(line: str) -> datetime:
    """Parse a Fidelity 'Date downloaded' line into a timezone-aware datetime.

    Accepts the bare or quoted form, with or without the meridiem's trailing
    period (both occur in real exports):
        Date downloaded Jun-22-2026 10:30 a.m. ET
        Date downloaded Jun-23-2026 6:29 p.m ET
        "Date downloaded Jun-22-2026 10:30 a.m. ET"

    The timezone is America/New_York (Fidelity always writes literal 'ET').
    """
    line = line.strip().strip('"')
    m = _DATE_DOWNLOADED_RE.search(line)
    if not m:
        raise ValueError(f"Cannot parse Date downloaded line: {line!r}")
    month_abbr, day, year, hour, minute, meridiem = m.groups()
    month = _MONTH_ABBR.get(month_abbr.lower())
    if not month:
        raise ValueError(f"Unknown month abbreviation: {month_abbr!r}")
    h = int(hour)
    is_pm = meridiem.lower() == "p"
    if is_pm and h != 12:
        h += 12
    elif not is_pm and h == 12:
        h = 0
    return datetime(
        int(year), month, int(day), h, int(minute),
        tzinfo=ZoneInfo("America/New_York"),
    )


@dataclass(frozen=True)
class _ParsedPosition:
    account_name: str
    account_type: str
    account_registration: Optional[str]
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
    """Map a Fidelity account display name to a canonical account_type."""
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


def _infer_asset_type(ticker: str, description: str) -> tuple[str, bool]:
    """Return (asset_type, skip) inferred from ticker and description.

    skip=True means the row should not be persisted (e.g. Pending activity).
    Classification rules (applied in order):
      1. "pending" in the ticker or description → skip
      2. Ticker starts with FCASH or "fcash" in description → cash
      3. "etf" in description → etf
      4. Non-empty ticker → stock
      5. Fallback → unknown

    Real Fidelity exports put "Pending activity" in the Symbol column with an
    empty Description, so the pending check must look at the ticker too.
    """
    desc_lower = (description or "").lower().strip()
    ticker_upper = (ticker or "").upper()
    ticker_lower = ticker_upper.lower()

    if "pending" in desc_lower or "pending" in ticker_lower:
        return "cash", True

    if ticker_upper.startswith("FCASH") or "fcash" in desc_lower:
        return "cash", False

    if "etf" in desc_lower:
        return "etf", False

    if ticker:
        return "stock", False

    return "unknown", False


def _clean_money(raw: Optional[str]) -> Optional[str]:
    """Strip Fidelity's ``$`` and thousands separators; empty → None."""
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace(",", "")
    if s == "" or s in {"--", "n/a", "N/A"}:
        return None
    return s


def _money_to_micros(raw: Optional[str]) -> Optional[int]:
    cleaned = _clean_money(raw)
    if cleaned is None:
        return None
    return to_micro_dollars(cleaned)


def _row_hash(account_name: str, ticker: str, quantity: str, market_value: str, cost_basis: str) -> str:
    payload = "|".join((account_name, ticker, quantity, market_value, cost_basis))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_row(row: dict[str, str]) -> Optional[_ParsedPosition]:
    """Translate one Fidelity CSV row into a canonical position.

    Returns ``None`` for rows that don't represent a position (blank
    separator lines, footer totals, disclaimer text, Pending activity).
    """
    account_name = (row.get("Account Name") or "").strip()
    ticker_raw = (row.get("Symbol") or "").strip()
    if not account_name and not ticker_raw:
        return None  # blank / disclaimer / date-downloaded rows

    description = (row.get("Description") or "").strip()
    asset_type, skip = _infer_asset_type(ticker_raw, description)
    if skip:
        return None

    # The Fidelity "Type" column carries account registration (Cash/Margin),
    # not security type. Store it verbatim (lowercased) for audit purposes.
    account_registration_raw = (row.get("Type") or "").strip()
    account_registration = account_registration_raw.lower() or None

    quantity_raw = (row.get("Quantity") or "").strip()
    quantity = quantity_raw or None
    current_value_raw = row.get("Current Value")
    cost_basis_raw = row.get("Cost Basis Total")
    market_value_micros = _money_to_micros(current_value_raw)
    cost_basis_micros = _money_to_micros(cost_basis_raw)

    is_cash = asset_type == "cash"
    cash_value_micros = market_value_micros if is_cash else None
    if is_cash:
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
        current_value_raw or "",
        cost_basis_raw or "",
    )
    return _ParsedPosition(
        account_name=account_name,
        account_type=_normalize_account_type(account_name),
        account_registration=account_registration,
        ticker=ticker,
        name=description or None,
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

        Trailing disclaimer paragraphs and the 'Date downloaded' line
        present in real Fidelity exports are silently skipped — they have
        no Account Name or Symbol and fall through the blank-row filter.
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
                        snapshot_id, account_name, account_type, account_registration,
                        ticker, name, asset_type, quantity, market_value_micros,
                        cost_basis_micros, cash_value_micros, currency,
                        is_supported, source_row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        p.account_name,
                        p.account_type,
                        p.account_registration,
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
