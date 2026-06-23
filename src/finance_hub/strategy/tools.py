"""Registered strategy tools — promotion of research into versioned intent.

``promote_to_strategy`` is the explicit, user-confirmed handoff from
research (ADR 0003): it snapshots approved candidates into a new,
immutable strategy version owning sleeves, target weights, eligible
instruments, the primary sleeve per ticker, and explicit hard caps.

Weights are stored in basis points (10000 = 100%) so the "sleeve targets
must sum to 100%" gate is exact integer arithmetic, not float drift —
matching the micro-dollar discipline used elsewhere in the hub.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Optional

from finance_hub import factories
from finance_hub.research import _store as research_store
from finance_hub.runtime.registry import tool
from finance_hub.strategy import _store

_STRATEGY_STATUSES = ("draft", "active", "archived")
_FULL_ALLOCATION_BPS = 10_000  # 100%


def _now() -> str:
    return factories.get_clock().now().isoformat()


def _pct_to_bps(pct, *, field: str) -> int:
    """Parse a percentage into integer basis points, rejecting float drift.

    Accepts ``12.5`` or ``"12.5"`` (-> 1250 bps). Sub-basis-point
    precision is rejected so two strategies never disagree on whether
    sleeve targets sum to exactly 100%.
    """
    if isinstance(pct, bool):
        raise ValueError(f"{field} must be a number, got a bool")
    try:
        d = Decimal(str(pct))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid percentage: {pct!r}") from exc
    bps = d * 100
    if bps != bps.to_integral_value():
        raise ValueError(
            f"{field} {pct!r} has sub-basis-point precision; "
            "use at most two fractional digits"
        )
    if bps < 0:
        raise ValueError(f"{field} must be non-negative, got {pct!r}")
    return int(bps)


def _bps_to_pct_str(bps: int) -> str:
    return str(Decimal(bps) / 100)


def _build_sleeve_rows(sleeves: list) -> tuple[list[dict], set[str]]:
    if not sleeves:
        raise ValueError("at least one sleeve is required")
    rows: list[dict] = []
    keys: set[str] = set()
    for s in sleeves:
        key = s["sleeve_key"]
        if key in keys:
            raise ValueError(f"duplicate sleeve_key {key!r}")
        keys.add(key)
        hard_cap = s.get("hard_cap_pct")
        rows.append(
            {
                "sleeve_key": key,
                "display_name": s.get("display_name"),
                "target_weight_bps": _pct_to_bps(
                    s["target_weight_pct"], field=f"sleeve {key!r} target_weight_pct"
                ),
                "hard_cap_bps": (
                    None
                    if hard_cap is None
                    else _pct_to_bps(hard_cap, field=f"sleeve {key!r} hard_cap_pct")
                ),
            }
        )
    return rows, keys


def _build_instrument_rows(instruments: list, sleeve_keys: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for i in instruments:
        ticker = i["ticker"]
        if ticker in seen:
            raise ValueError(
                f"ticker {ticker!r} promoted twice; each ticker resolves to "
                "exactly one primary sleeve"
            )
        seen.add(ticker)
        sleeve = i["primary_sleeve_key"]
        if sleeve not in sleeve_keys:
            raise ValueError(
                f"primary_sleeve_key {sleeve!r} for {ticker!r} is not one of "
                "this strategy's sleeves"
            )
        # Snapshot the instrument's research metadata so later research edits
        # never mutate this version (strategy spec §4).
        research_instr = research_store.get_instrument(ticker)
        if research_instr is None:
            raise LookupError(
                f"no research instrument {ticker!r}; only approved research "
                "candidates can be promoted"
            )
        source_theme = i.get("source_theme_key")
        conviction: Optional[int] = None
        if source_theme is not None:
            edge = research_store.get_theme_instrument(
                theme_key=source_theme, ticker=ticker
            )
            if edge is None:
                raise LookupError(
                    f"{ticker!r} is not mapped to theme {source_theme!r}"
                )
            if edge.get("status") != "approved":
                raise ValueError(
                    f"{ticker!r} in theme {source_theme!r} is "
                    f"{edge.get('status')!r}, not 'approved'"
                )
            conviction = edge.get("conviction")
        hard_cap = i.get("hard_cap_pct")
        rows.append(
            {
                "ticker": ticker,
                "primary_sleeve_key": sleeve,
                "instrument_role": research_instr.get("instrument_role"),
                "conviction": conviction,
                "source_theme_key": source_theme,
                "hard_cap_bps": (
                    None
                    if hard_cap is None
                    else _pct_to_bps(hard_cap, field=f"{ticker!r} hard_cap_pct")
                ),
                "note": i.get("note"),
            }
        )
    return rows


def _with_completeness(version: dict) -> dict:
    total = sum(s["target_weight_bps"] for s in version["sleeves"])
    version["targets_sum_bps"] = total
    version["targets_sum_pct"] = _bps_to_pct_str(total)
    version["targets_complete"] = total == _FULL_ALLOCATION_BPS
    return version


@tool(
    name="finance.promote_to_strategy",
    description=(
        "Explicit, user-confirmed handoff: snapshot approved research "
        "candidates into a new versioned strategy with sleeves, target "
        "weights, eligible instruments, a primary sleeve per ticker, and "
        "optional hard caps. Requires confirm=True."
    ),
)
def promote_to_strategy(
    *,
    version_id: str,
    sleeves: list,
    instruments: list,
    label: Optional[str] = None,
    notes: Optional[str] = None,
    status: str = "draft",
    confirm: bool = False,
) -> dict:
    if not confirm:
        raise ValueError(
            "promote_to_strategy requires explicit confirmation; pass confirm=True"
        )
    if status not in _STRATEGY_STATUSES:
        raise ValueError(
            f"status must be one of {_STRATEGY_STATUSES}, got {status!r}"
        )
    sleeve_rows, sleeve_keys = _build_sleeve_rows(sleeves)
    instrument_rows = _build_instrument_rows(instruments, sleeve_keys)
    try:
        version = _store.create_strategy_version(
            version_id=version_id,
            label=label,
            status=status,
            notes=notes,
            sleeves=sleeve_rows,
            instruments=instrument_rows,
            now=_now(),
        )
    except sqlite3.IntegrityError as exc:
        # The partial unique index on status='active' reports a collision on
        # fin_strategy_versions.status; a duplicate version_id reports the PK.
        msg = str(exc)
        if "status" in msg:
            raise ValueError(
                "another strategy version is already active; only one active "
                "version is allowed at a time"
            ) from exc
        if "version_id" in msg:
            raise ValueError(
                f"strategy version {version_id!r} already exists"
            ) from exc
        raise
    return _with_completeness(version)


@tool(
    name="finance.get_strategy",
    description="Read a strategy version with its sleeves and eligible instruments.",
)
def get_strategy(*, version_id: str) -> dict:
    version = _store.get_strategy_version(version_id)
    if version is None:
        raise LookupError(f"no strategy version {version_id!r}")
    return _with_completeness(version)


@tool(
    name="finance.list_strategies",
    description="List strategy versions, optionally filtered by status.",
)
def list_strategies(*, status: Optional[str] = None) -> dict:
    if status is not None and status not in _STRATEGY_STATUSES:
        raise ValueError(
            f"status must be one of {_STRATEGY_STATUSES}, got {status!r}"
        )
    return {"strategies": _store.list_strategy_versions(status=status)}


@tool(
    name="finance.activate_strategy",
    description=(
        "Activate a strategy version (draft -> active). At most one version "
        "may be active; activating fails if another is already active. "
        "Requires confirm=True."
    ),
)
def activate_strategy(*, version_id: str, confirm: bool = False) -> dict:
    if not confirm:
        raise ValueError(
            "activating a strategy requires explicit confirmation; pass confirm=True"
        )
    if _store.get_strategy_version(version_id) is None:
        raise LookupError(f"no strategy version {version_id!r}")
    try:
        version = _store.set_version_status(
            version_id=version_id, status="active", now=_now()
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "another strategy version is already active; archive it first"
        ) from exc
    return _with_completeness(version)


@tool(
    name="finance.check_strategy_deployable",
    description=(
        "Report whether a strategy version can drive a dollar-denominated "
        "deployment draft: it must be active and its sleeve targets must sum "
        "to exactly 100%."
    ),
)
def check_strategy_deployable(*, version_id: str) -> dict:
    version = _store.get_strategy_version(version_id)
    if version is None:
        raise LookupError(f"no strategy version {version_id!r}")
    version = _with_completeness(version)
    reasons: list[str] = []
    if version["status"] != "active":
        reasons.append(f"strategy status is {version['status']!r}, not 'active'")
    if not version["targets_complete"]:
        reasons.append(
            f"sleeve targets sum to {version['targets_sum_pct']}%, not 100%"
        )
    return {
        "version_id": version_id,
        "status": version["status"],
        "deployable": not reasons,
        "targets_sum_pct": version["targets_sum_pct"],
        "reasons": reasons,
    }
