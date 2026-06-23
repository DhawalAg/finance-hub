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
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Optional

from finance_hub import factories
from finance_hub.money import to_micro_dollars
from finance_hub.research import _store as research_store
from finance_hub.research import tools as research_tools
from finance_hub.runtime.registry import tool
from finance_hub.strategy import _plan_store, _store, deployment

_STRATEGY_STATUSES = ("draft", "active", "archived")
_FULL_ALLOCATION_BPS = 10_000  # 100%
_RISK_MODES = ("conservative", "balanced", "aggressive")


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


# ---------------------------------------------------------------------------
# generate_deployment_plan — the deterministic draft engine (PRD story 79)
#
# The SOLE writer of recommendation rows. Pipeline: load -> validate candidate
# evidence -> validate bucket eligibility -> compute lines -> persist -> JSON.
# Freshness banding and output-mode downgrades land in the next slice; this
# slice is the in-band case (a deployable strategy + a snapshot in hand).
# ---------------------------------------------------------------------------


def _micros_to_str(micros: int) -> str:
    return str(Decimal(micros) / 1_000_000)


def _eligibility_from_evidence(ev: dict) -> tuple[bool, bool, tuple, tuple]:
    """DCA/one-time eligibility from candidate_evidence, minus promotion.

    The planner already restricts the universe to strategy-eligible
    instruments, so ``PROMOTION_REQUIRED`` (which candidate_evidence raises
    for everything until the research-side lookup is wired) is not a gate
    here — being in the active strategy *is* the promotion.
    """
    dca_gaps = tuple(g for g in ev["gaps"]["dca"] if g != "PROMOTION_REQUIRED")
    one_time_gaps = tuple(
        g for g in ev["gaps"]["one_time"] if g != "PROMOTION_REQUIRED"
    )
    return (not dca_gaps), (not one_time_gaps), dca_gaps, one_time_gaps


def _load_portfolio(positions: list[dict], sleeve_of: dict[str, str]):
    """Aggregate snapshot positions into the weight inputs the engine needs."""
    portfolio_total = 0
    sleeve_current: dict[str, int] = defaultdict(int)
    unknown_sleeve = 0
    mv_by_ticker: dict[str, int] = defaultdict(int)
    for p in positions:
        mv = p["market_value_micros"]
        if mv is None:
            continue
        portfolio_total += mv
        ticker = p["ticker"]
        if ticker:
            mv_by_ticker[ticker] += mv
        sleeve = sleeve_of.get(ticker) if ticker else None
        if sleeve is not None:
            sleeve_current[sleeve] += mv
        else:
            unknown_sleeve += mv
    return portfolio_total, dict(sleeve_current), unknown_sleeve, dict(mv_by_ticker)


def _line_evidence(line, ev: dict) -> list[dict]:
    """Lightweight references answering "why did we recommend this ticker?"."""
    refs: list[dict] = []
    price = _plan_store.latest_price_ref(line.ticker)
    if price is not None:
        refs.append(
            {
                "line_id": line.line_id,
                "evidence_type": "price",
                "ref_table": "fin_price_bars",
                "ref_key": line.ticker,
                "summary": f"close {_micros_to_str(price['close_micros'])} "
                f"on {price['session_date']}",
            }
        )
    if _plan_store.has_metrics(line.ticker):
        refs.append(
            {
                "line_id": line.line_id,
                "evidence_type": "metric",
                "ref_table": "fin_metrics",
                "ref_key": line.ticker,
                "summary": "stored metrics pack",
            }
        )
    if ev.get("thesis_note_path"):
        refs.append(
            {
                "line_id": line.line_id,
                "evidence_type": "research_note",
                "ref_table": "fin_instruments",
                "ref_key": line.ticker,
                "summary": ev["thesis_note_path"],
            }
        )
    for sid in ev.get("supporting_source_ids", []):
        refs.append(
            {
                "line_id": line.line_id,
                "evidence_type": "research_source",
                "ref_table": "fin_research_sources",
                "ref_key": str(sid),
                "summary": None,
            }
        )
    return refs


def _bucket_json(res) -> dict:
    return {
        "bucket": res.bucket,
        "budget": _micros_to_str(res.budget_micros),
        "budget_micros": res.budget_micros,
        "allocated": _micros_to_str(res.allocated_micros),
        "allocated_micros": res.allocated_micros,
        "unallocated": _micros_to_str(res.unallocated_micros),
        "unallocated_micros": res.unallocated_micros,
        "unallocated_reasons": [
            {
                "ticker": r.ticker,
                "reason": r.reason,
                "amount_micros": r.amount_micros,
            }
            for r in res.unallocated_reasons
        ],
    }


@tool(
    name="finance.generate_deployment_plan",
    description=(
        "The sole writer of recommendation rows: validate inputs and candidate "
        "evidence, compute DCA + one-time buy lines against directly-loaded "
        "snapshot/strategy/evidence state, persist the plan with warning/block "
        "rows and evidence references, and return the structured deployment_draft."
    ),
)
def generate_deployment_plan(
    *,
    portfolio_snapshot_id: str,
    strategy_version_id: str,
    deployable_cash: str,
    dca_budget: str = "0",
    one_time_buy_budget: str = "0",
    dca_cadence: Optional[str] = None,
    benchmark_ticker: str = "SPY",
    risk_mode: str = "balanced",
    candidate_tickers: Optional[list] = None,
    exclude_tickers: Optional[list] = None,
) -> dict:
    if risk_mode not in _RISK_MODES:
        raise ValueError(f"risk_mode must be one of {_RISK_MODES}, got {risk_mode!r}")

    deployable_micros = to_micro_dollars(deployable_cash)
    dca_micros = to_micro_dollars(dca_budget)
    one_time_micros = to_micro_dollars(one_time_buy_budget)
    if dca_micros < 0 or one_time_micros < 0 or deployable_micros < 0:
        raise ValueError("budgets must be non-negative")
    if dca_micros + one_time_micros > deployable_micros:
        raise ValueError(
            "dca_budget + one_time_buy_budget exceeds deployable_cash; a plan "
            "never proposes more than the approved total"
        )

    version = _store.get_strategy_version(strategy_version_id)
    if version is None:
        raise LookupError(f"no strategy version {strategy_version_id!r}")
    check = check_strategy_deployable(version_id=strategy_version_id)
    if not check["deployable"]:
        raise ValueError(
            "strategy version is not deployable: " + "; ".join(check["reasons"])
        )

    positions = _plan_store.load_snapshot_positions(portfolio_snapshot_id)
    if positions is None:
        raise LookupError(f"no portfolio snapshot {portfolio_snapshot_id!r}")

    sleeve_target = {s["sleeve_key"]: s["target_weight_bps"] for s in version["sleeves"]}
    instruments = {i["ticker"]: i for i in version["instruments"]}
    sleeve_of = {t: i["primary_sleeve_key"] for t, i in instruments.items()}

    universe = list(instruments)
    if candidate_tickers is not None:
        unknown = [t for t in candidate_tickers if t not in instruments]
        if unknown:
            raise ValueError(
                "candidate_tickers may only narrow to already-eligible strategy "
                f"instruments; not eligible: {unknown}"
            )
        universe = [t for t in universe if t in set(candidate_tickers)]
    excluded = set(exclude_tickers or [])

    (
        portfolio_total,
        sleeve_current,
        unknown_sleeve,
        mv_by_ticker,
    ) = _load_portfolio(positions, sleeve_of)

    candidates: list[deployment.CandidateInput] = []
    evidence_by_ticker: dict[str, dict] = {}
    for ticker in universe:
        instr = instruments[ticker]
        ev = research_tools.candidate_evidence(ticker=ticker)
        evidence_by_ticker[ticker] = ev
        dca_ok, one_time_ok, dca_gaps, one_time_gaps = _eligibility_from_evidence(ev)
        candidates.append(
            deployment.CandidateInput(
                ticker=ticker,
                sleeve_key=instr["primary_sleeve_key"],
                sleeve_target_bps=sleeve_target.get(instr["primary_sleeve_key"], 0),
                instrument_role=instr.get("instrument_role"),
                conviction=instr.get("conviction"),
                hard_cap_bps=instr.get("hard_cap_bps"),
                dca_eligible=dca_ok,
                one_time_eligible=one_time_ok,
                has_price=_plan_store.latest_price_ref(ticker) is not None,
                current_mv_micros=mv_by_ticker.get(ticker, 0),
                dca_gaps=dca_gaps,
                one_time_gaps=one_time_gaps,
                excluded=ticker in excluded,
            )
        )

    policy = deployment.PlanPolicy()
    computation = deployment.compute_recommendation_lines(
        candidates=candidates,
        dca_budget_micros=dca_micros,
        one_time_budget_micros=one_time_micros,
        portfolio_total_micros=portfolio_total,
        sleeve_current_micros=sleeve_current,
        unknown_sleeve_micros=unknown_sleeve,
        policy=policy,
    )

    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    lines: list = []
    line_dicts: list[dict] = []
    evidence_refs: list[dict] = []
    for bucket in ("dca", "one_time"):
        for line in computation.buckets[bucket].lines:
            line.line_id = f"{plan_id}_{bucket}_{line.ticker}"
            lines.append(line)
            line_dicts.append(
                {
                    "line_id": line.line_id,
                    "bucket": line.bucket,
                    "ticker": line.ticker,
                    "sleeve_key": line.sleeve_key,
                    "amount_micros": line.amount_micros,
                    "rank": line.rank,
                    "ranked_factors": line.ranked_factors,
                    "rationale": line.rationale,
                }
            )
            evidence_refs.extend(_line_evidence(line, evidence_by_ticker[line.ticker]))

    has_block = any(w.severity == "block" for w in computation.warnings)
    status = "proposed_with_warnings" if computation.warnings else "proposed"
    dca_unalloc = computation.buckets["dca"].unallocated_micros
    one_time_unalloc = computation.buckets["one_time"].unallocated_micros

    header = {
        "plan_id": plan_id,
        "output_mode": "deployment_draft",
        "status": status,
        "portfolio_snapshot_id": portfolio_snapshot_id,
        "strategy_version_id": strategy_version_id,
        "benchmark_ticker": benchmark_ticker,
        "risk_mode": risk_mode,
        "dca_cadence": dca_cadence,
        "deployable_cash_micros": deployable_micros,
        "dca_budget_micros": dca_micros,
        "one_time_buy_budget_micros": one_time_micros,
        "dca_unallocated_micros": dca_unalloc,
        "one_time_unallocated_micros": one_time_unalloc,
        "total_unallocated_micros": dca_unalloc + one_time_unalloc,
        "effective_policy": policy.as_dict(),
        "supersedes_plan_id": None,
    }
    warning_dicts = [
        {
            "code": w.code,
            "severity": w.severity,
            "ticker": w.ticker,
            "message": w.message,
        }
        for w in computation.warnings
    ]

    _plan_store.persist_plan(
        header=header,
        lines=line_dicts,
        warnings=warning_dicts,
        evidence=evidence_refs,
        now=_now(),
    )

    return {
        "plan_id": plan_id,
        "output_mode": "deployment_draft",
        "status": status,
        "has_block": has_block,
        "inputs": {
            "portfolio_snapshot_id": portfolio_snapshot_id,
            "strategy_version_id": strategy_version_id,
            "deployable_cash": _micros_to_str(deployable_micros),
            "dca_budget": _micros_to_str(dca_micros),
            "one_time_buy_budget": _micros_to_str(one_time_micros),
            "dca_cadence": dca_cadence,
            "benchmark_ticker": benchmark_ticker,
            "risk_mode": risk_mode,
            "candidate_tickers": candidate_tickers,
            "exclude_tickers": sorted(excluded),
        },
        "lines": [
            {
                **ld,
                "amount": _micros_to_str(ld["amount_micros"]),
            }
            for ld in line_dicts
        ],
        "buckets": {b: _bucket_json(computation.buckets[b]) for b in ("dca", "one_time")},
        "unallocated": {
            "dca_micros": dca_unalloc,
            "one_time_micros": one_time_unalloc,
            "total_micros": dca_unalloc + one_time_unalloc,
            "total": _micros_to_str(dca_unalloc + one_time_unalloc),
        },
        "warnings": warning_dicts,
        "watchlist": [
            {"ticker": w.ticker, "reason": w.reason, "detail": w.detail}
            for w in computation.watchlist
        ],
        "evidence": evidence_refs,
        "effective_policy": policy.as_dict(),
    }


@tool(
    name="finance.get_deployment_plan",
    description="Read a persisted deployment plan with its lines, warnings, and evidence refs.",
)
def get_deployment_plan(*, plan_id: str) -> dict:
    plan = _plan_store.get_plan(plan_id)
    if plan is None:
        raise LookupError(f"no deployment plan {plan_id!r}")
    return plan
