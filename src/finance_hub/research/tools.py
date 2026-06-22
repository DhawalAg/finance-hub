"""Registered research tools — thin wrappers over pure SQLite persistence.

Every tool returns structured JSON (the shape strategy/render layers
consume); the registry name is dotted (`finance.set_theme`, ...) so the
CLI and MCP surfaces both expose the same entry points.

Theme/instrument/candidate persistence lives here; note + source helpers
live in their own modules and are re-exported through the registry.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from finance_hub import factories
from finance_hub.research import _store
from finance_hub.runtime.registry import tool


_THEME_STATUSES = ("exploring", "watching", "archived")
_INSTRUMENT_TYPES = ("stock", "etf")
_INSTRUMENT_ROLES = ("broad_market_etf", "theme_etf", "single_stock")
_CANDIDATE_STATUSES = ("candidate", "watching", "approved", "rejected")
_SCOPES = ("theme", "instrument")
_NOTE_SUBDIR = {"theme": "themes", "instrument": "instruments"}


def _now() -> str:
    return factories.get_clock().now().isoformat()


def _workspace_root() -> Path:
    """Root of the gitignored ``workspace/`` tree (ADR 0002).

    Overridable via ``FINANCE_HUB_WORKSPACE`` so tests write under
    ``tmp_path`` rather than polluting the repo's workspace.
    """
    return Path(os.environ.get("FINANCE_HUB_WORKSPACE", Path.cwd() / "workspace"))


@tool(
    name="finance.set_theme",
    description="Create or update a research theme.",
)
def set_theme(
    *,
    key: str,
    display_name: str,
    description: Optional[str] = None,
    status: str = "exploring",
    parent_key: Optional[str] = None,
    note_path: Optional[str] = None,
) -> dict:
    if status not in _THEME_STATUSES:
        raise ValueError(
            f"status must be one of {_THEME_STATUSES}, got {status!r}"
        )
    now = _now()
    return _store.upsert_theme(
        key=key,
        display_name=display_name,
        description=description,
        status=status,
        parent_key=parent_key,
        note_path=note_path,
        now=now,
    )


@tool(
    name="finance.list_themes",
    description="List themes filtered by status and/or parent.",
)
def list_themes(
    *,
    status: Optional[str] = None,
    parent_key: Optional[str] = None,
) -> dict:
    if status is not None and status not in _THEME_STATUSES:
        raise ValueError(
            f"status must be one of {_THEME_STATUSES}, got {status!r}"
        )
    rows = _store.list_themes(status=status, parent_key=parent_key)
    return {"themes": rows}


@tool(
    name="finance.get_theme",
    description="Read one theme with its children, candidate instruments, sources, and note path.",
)
def get_theme(*, key: str) -> dict:
    theme = _store.get_theme(key)
    if theme is None:
        raise LookupError(f"no theme with key {key!r}")
    theme["children"] = _store.list_themes(parent_key=key)
    theme["instruments"] = _store.list_theme_instruments(theme_key=key)
    theme["sources"] = _store.list_source_links(scope="theme", key=key)
    return theme


def _require_conviction_note(
    conviction: Optional[int], conviction_note: Optional[str]
) -> None:
    if conviction is None:
        return
    if not (1 <= int(conviction) <= 5):
        raise ValueError(f"conviction must be between 1 and 5, got {conviction!r}")
    if conviction_note is None or not str(conviction_note).strip():
        raise ValueError("conviction requires a non-empty conviction_note")


@tool(
    name="finance.map_instruments",
    description="Attach candidate instruments to a theme.",
)
def map_instruments(
    *,
    theme_key: str,
    instruments: list,
) -> dict:
    if _store.get_theme(theme_key) is None:
        raise LookupError(f"no theme with key {theme_key!r}")
    now = _now()
    out_rows: list[dict] = []
    for item in instruments:
        ticker = item["ticker"]
        type_ = item.get("type", "stock")
        role = item["instrument_role"]
        if type_ not in _INSTRUMENT_TYPES:
            raise ValueError(
                f"instrument.type must be one of {_INSTRUMENT_TYPES}, got {type_!r}"
            )
        if role not in _INSTRUMENT_ROLES:
            raise ValueError(
                f"instrument_role must be one of {_INSTRUMENT_ROLES}, got {role!r}"
            )
        status = item.get("status", "candidate")
        if status not in _CANDIDATE_STATUSES:
            raise ValueError(
                f"status must be one of {_CANDIDATE_STATUSES}, got {status!r}"
            )
        conviction = item.get("conviction")
        conviction_note = item.get("conviction_note")
        _require_conviction_note(conviction, conviction_note)

        _store.upsert_instrument(
            ticker=ticker,
            type_=type_,
            instrument_role=role,
            display_name=item.get("display_name"),
            note_path=item.get("note_path"),
            now=now,
        )
        row = _store.upsert_theme_instrument(
            theme_key=theme_key,
            ticker=ticker,
            status=status,
            role=item.get("role"),
            conviction=conviction,
            conviction_note=conviction_note,
            note=item.get("rationale") or item.get("note"),
            now=now,
        )
        out_rows.append(row)
    return {"theme_key": theme_key, "instruments": out_rows}


@tool(
    name="finance.review_instrument",
    description=(
        "Mark a candidate watching, approved, or rejected with a rationale. "
        "Optional conviction (1-5) requires a conviction note."
    ),
)
def review_instrument(
    *,
    theme_key: str,
    ticker: str,
    status: str,
    rationale: str,
    conviction: Optional[int] = None,
    conviction_note: Optional[str] = None,
    role: Optional[str] = None,
) -> dict:
    if status not in _CANDIDATE_STATUSES:
        raise ValueError(
            f"status must be one of {_CANDIDATE_STATUSES}, got {status!r}"
        )
    existing = _store.get_theme_instrument(theme_key=theme_key, ticker=ticker)
    if existing is None:
        raise LookupError(
            f"no candidate {ticker!r} attached to theme {theme_key!r}"
        )
    _require_conviction_note(conviction, conviction_note)
    # Clearing conviction also clears the note so the CHECK invariant
    # (conviction NULL OR note non-empty) never lingers half-set.
    if conviction is None:
        conviction_note = None
    now = _now()
    return _store.upsert_theme_instrument(
        theme_key=theme_key,
        ticker=ticker,
        status=status,
        role=role if role is not None else existing.get("role"),
        conviction=conviction,
        conviction_note=conviction_note,
        note=rationale,
        now=now,
    )


# ---------------------------------------------------------------------------
# research notes — markdown on disk, path in SQLite (ADR 0002)
# ---------------------------------------------------------------------------


def _note_rel_path(scope: str, key: str) -> str:
    return f"research/{_NOTE_SUBDIR[scope]}/{key}.md"


def _require_target(scope: str, key: str) -> None:
    if scope == "theme":
        if _store.get_theme(key) is None:
            raise LookupError(f"no theme with key {key!r}")
    else:
        if _store.get_instrument(key) is None:
            raise LookupError(f"no instrument with ticker {key!r}")


@tool(
    name="finance.set_research_note",
    description=(
        "Write a thesis/dossier note for a theme or instrument. The markdown "
        "body lives under workspace/research/...; SQLite stores the path."
    ),
)
def set_research_note(*, scope: str, key: str, body: str) -> dict:
    if scope not in _SCOPES:
        raise ValueError(f"scope must be one of {_SCOPES}, got {scope!r}")
    _require_target(scope, key)
    rel = _note_rel_path(scope, key)
    abs_path = _workspace_root() / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(body)
    now = _now()
    if scope == "theme":
        _store.set_theme_note_path(key=key, note_path=rel, now=now)
    else:
        _store.set_instrument_note_path(ticker=key, note_path=rel, now=now)
    return {"scope": scope, "key": key, "path": str(abs_path), "note_path": rel}


@tool(
    name="finance.get_research_note",
    description="Read the thesis/dossier note for a theme or instrument.",
)
def get_research_note(*, scope: str, key: str) -> dict:
    if scope not in _SCOPES:
        raise ValueError(f"scope must be one of {_SCOPES}, got {scope!r}")
    if scope == "theme":
        row = _store.get_theme(key)
        if row is None:
            raise LookupError(f"no theme with key {key!r}")
    else:
        row = _store.get_instrument(key)
        if row is None:
            raise LookupError(f"no instrument with ticker {key!r}")
    rel = row.get("note_path")
    if not rel:
        return {"scope": scope, "key": key, "body": None, "path": None}
    abs_path = _workspace_root() / rel
    body = abs_path.read_text() if abs_path.exists() else None
    return {"scope": scope, "key": key, "body": body, "path": str(abs_path)}


# ---------------------------------------------------------------------------
# sources + citation links — upsert by URL, review_after, supersession
# ---------------------------------------------------------------------------


@tool(
    name="finance.upsert_source",
    description=(
        "Upsert a cited source by URL (idempotent). Returns the stable source "
        "id used for inline citation (e.g. [source:123])."
    ),
)
def upsert_source(
    *,
    url: str,
    title: Optional[str] = None,
    publisher: Optional[str] = None,
    source_type: Optional[str] = None,
    published_on: Optional[str] = None,
    trusted: bool = False,
) -> dict:
    return _store.upsert_source(
        url=url,
        title=title,
        publisher=publisher,
        source_type=source_type,
        published_on=published_on,
        trusted=trusted,
        now=_now(),
    )


@tool(
    name="finance.link_source",
    description=(
        "Link an existing source to a theme or instrument, optionally with a "
        "review_after date. Reusable: the same source can back many links."
    ),
)
def link_source(
    *,
    source_id: int,
    scope: str,
    key: str,
    note: Optional[str] = None,
    review_after: Optional[str] = None,
) -> dict:
    if scope not in _SCOPES:
        raise ValueError(f"scope must be one of {_SCOPES}, got {scope!r}")
    if _store.get_source_by_id(source_id) is None:
        raise LookupError(f"no source with id {source_id!r}")
    _require_target(scope, key)
    return _store.upsert_source_link(
        source_id=source_id,
        scope=scope,
        key=key,
        note=note,
        status="active",
        review_after=review_after,
        now=_now(),
    )


@tool(
    name="finance.supersede_source_link",
    description=(
        "Mark a source link superseded when newer evidence replaces it, "
        "retaining the old row so historical citations stay explainable."
    ),
)
def supersede_source_link(
    *,
    source_id: int,
    scope: str,
    key: str,
    note: Optional[str] = None,
) -> dict:
    if scope not in _SCOPES:
        raise ValueError(f"scope must be one of {_SCOPES}, got {scope!r}")
    link = _store.upsert_source_link(
        source_id=source_id,
        scope=scope,
        key=key,
        note=note,
        status="superseded",
        review_after=None,
        now=_now(),
    )
    return link


@tool(
    name="finance.list_sources",
    description="List cited sources, optionally filtered to a (scope, key).",
)
def list_sources(
    *,
    scope: Optional[str] = None,
    key: Optional[str] = None,
) -> dict:
    return {"sources": _store.list_sources(scope=scope, key=key)}


@tool(
    name="finance.sources_due_for_review",
    description=(
        "List active source links whose review_after date is due, so stale "
        "evidence is surfaced rather than silently trusted."
    ),
)
def sources_due_for_review(*, as_of: Optional[str] = None) -> dict:
    as_of = as_of or _now()
    return {"as_of": as_of, "due": _store.sources_due_for_review(as_of=as_of)}


# ---------------------------------------------------------------------------
# read contract into strategy/planning — candidate_evidence + the gap scan
#
# These are READ-ONLY: research discovery never mutates strategy or alters
# which instruments the planner can fund (PRD stories 12-14). They surface
# stable references + readiness + gaps, never rendered prose only.
# ---------------------------------------------------------------------------

# Gap codes, ordered by deployment-blocking severity (higher == more blocking).
# Promotion gates everything; missing thesis/citations gate the cited-thesis
# bar; staleness and the one-time fundamentals bar are softer.
_GAP_SEVERITY = {
    "PROMOTION_REQUIRED": 100,
    "MISSING_THESIS_NOTE": 80,
    "MISSING_CITATIONS": 70,
    "STALE_SOURCES": 50,
    "MISSING_FUNDAMENTALS": 40,
    # global (non-candidate) deployment-blocking gaps
    "NO_ACTIVE_STRATEGY": 95,
    "NO_PORTFOLIO_SNAPSHOT": 60,
    "NO_PRICE_DATA": 45,
    "NO_RECENT_PLANS": 20,
}

# Broad-market ETFs may use a compact ETF evidence pack instead of a full
# cited thesis (research spec §2 evidence gates).
_THESIS_REQUIRED_ROLES = ("single_stock", "theme_etf")


def _strategy_has_eligible(ticker: str) -> bool:
    """Whether ``ticker`` is eligible in an active strategy version.

    The strategy slice (promotion + versioned strategy) is not built yet, so
    the table is absent and this is always False — every candidate honestly
    reports ``promotion_required``. Forward-compatible once the table lands.
    """
    return _store.has_rows(
        "fin_strategy_eligible_instruments",
        where="ticker = ?",
        params=(ticker,),
    )


def _candidate_gaps(
    *,
    instrument_role: str,
    has_thesis: bool,
    has_citations: bool,
    has_stale: bool,
    promotion_required: bool,
    has_fundamentals: bool,
) -> dict:
    """Evidence gaps blocking DCA vs one-time eligibility for one candidate."""
    dca: list[str] = []
    if instrument_role in _THESIS_REQUIRED_ROLES:
        if not has_thesis:
            dca.append("MISSING_THESIS_NOTE")
        if not has_citations:
            dca.append("MISSING_CITATIONS")
    if has_stale:
        dca.append("STALE_SOURCES")
    if promotion_required:
        dca.append("PROMOTION_REQUIRED")
    # One-time buys clear a higher bar: every DCA gap plus compact
    # valuation/fundamental context (research spec §2).
    one_time = list(dca)
    if not has_fundamentals:
        one_time.append("MISSING_FUNDAMENTALS")
    return {"dca": dca, "one_time": one_time}


_STATUS_RANK = {"approved": 3, "watching": 2, "candidate": 1, "rejected": 0}


@tool(
    name="finance.candidate_evidence",
    description=(
        "Read one candidate's research evidence as stable references + "
        "readiness + gaps: theme/sleeve mapping, status, thesis note location, "
        "supporting source IDs, stale-source flags, promotion-required state, "
        "and the gaps blocking DCA vs one-time eligibility. Read-only."
    ),
)
def candidate_evidence(*, ticker: str, theme_key: Optional[str] = None) -> dict:
    instrument = _store.get_instrument(ticker)
    if instrument is None:
        raise LookupError(f"no instrument with ticker {ticker!r}")

    themes = _store.list_themes_for_ticker(ticker)
    if theme_key is not None:
        themes = [t for t in themes if t["theme_key"] == theme_key]

    # Supporting sources: instrument-scoped links plus theme-scoped links for
    # every theme this candidate expresses. Only active (non-superseded) links
    # count as supporting evidence.
    due = {
        (d["scope"], d["key"], d["source_id"])
        for d in _store.sources_due_for_review(as_of=_now())
    }
    supporting: set[int] = set()
    stale: set[int] = set()
    scopes = [("instrument", ticker)] + [("theme", t["theme_key"]) for t in themes]
    for scope, key in scopes:
        for link in _store.list_source_links(scope=scope, key=key):
            if link["status"] != "active":
                continue
            sid = link["source_id"]
            supporting.add(sid)
            if (scope, key, sid) in due:
                stale.add(sid)

    # Thesis note: the instrument's own note is the dossier; fall back to a
    # theme note (broad-market ETFs lean on the theme/sleeve thesis).
    thesis_note_path = instrument.get("note_path")
    if not thesis_note_path:
        for t in themes:
            if t.get("theme_note_path"):
                thesis_note_path = t["theme_note_path"]
                break

    promotion_required = not _strategy_has_eligible(ticker)
    has_fundamentals = _store.has_rows(
        "fin_fundamentals", where="ticker = ?", params=(ticker,)
    )

    gaps = _candidate_gaps(
        instrument_role=instrument["instrument_role"],
        has_thesis=bool(thesis_note_path),
        has_citations=bool(supporting),
        has_stale=bool(stale),
        promotion_required=promotion_required,
        has_fundamentals=has_fundamentals,
    )

    research_status = None
    if themes:
        research_status = max(
            (t["status"] for t in themes),
            key=lambda s: _STATUS_RANK.get(s, -1),
        )

    return {
        "ticker": ticker,
        "instrument": {
            "ticker": instrument["ticker"],
            "type": instrument["type"],
            "instrument_role": instrument["instrument_role"],
            "display_name": instrument.get("display_name"),
            "note_path": instrument.get("note_path"),
        },
        "themes": [
            {
                "theme_key": t["theme_key"],
                "status": t["status"],
                "role": t.get("role"),
                "conviction": t.get("conviction"),
                "theme_note_path": t.get("theme_note_path"),
            }
            for t in themes
        ],
        "research_status": research_status,
        "thesis_note_path": thesis_note_path,
        "supporting_source_ids": sorted(supporting),
        "stale_source_ids": sorted(stale),
        "promotion_required": promotion_required,
        "readiness": {
            "dca": not gaps["dca"],
            "one_time": not gaps["one_time"],
        },
        "gaps": gaps,
    }


def _priority(gap: str, **extra) -> dict:
    return {"gap": gap, "severity": _GAP_SEVERITY.get(gap, 0), **extra}


@tool(
    name="finance.research_priorities",
    description=(
        "Gap scan over current stored facts (strategy, candidates, notes/"
        "sources, market data, fundamentals, snapshot, recent plans), ranked "
        "by deployment-blocking impact. Degrades gracefully when downstream "
        "tables are still empty. Read-only."
    ),
)
def research_priorities() -> dict:
    as_of = _now()
    priorities: list[dict] = []

    # Global deployment-blocking gaps — reported (not raised) when the
    # downstream tables are absent or empty.
    if not _store.has_rows("fin_strategy_eligible_instruments"):
        priorities.append(
            _priority(
                "NO_ACTIVE_STRATEGY",
                detail="no active strategy version; candidates cannot be funded "
                "until promoted",
            )
        )
    if not _store.has_rows("fin_portfolio_snapshots"):
        priorities.append(
            _priority(
                "NO_PORTFOLIO_SNAPSHOT",
                detail="no imported portfolio snapshot; weight impact unknown",
            )
        )
    if not _store.has_rows("fin_deployment_plans"):
        priorities.append(
            _priority("NO_RECENT_PLANS", detail="no deployment plans yet")
        )

    # Per-candidate evidence gaps (rejected candidates are out of scope).
    for cand in _store.list_candidates(include_rejected=False):
        ev = candidate_evidence(ticker=cand["ticker"], theme_key=cand["theme_key"])
        if not _store.has_rows(
            "fin_price_bars", where="ticker = ?", params=(cand["ticker"],)
        ):
            priorities.append(
                _priority(
                    "NO_PRICE_DATA",
                    ticker=cand["ticker"],
                    theme_key=cand["theme_key"],
                    detail="no stored price bars",
                )
            )
        for gap in ev["gaps"]["one_time"]:
            blocks = ["one_time"]
            if gap in ev["gaps"]["dca"]:
                blocks.append("dca")
            priorities.append(
                _priority(
                    gap,
                    ticker=cand["ticker"],
                    theme_key=cand["theme_key"],
                    blocks=blocks,
                )
            )

    priorities.sort(
        key=lambda p: (-p["severity"], p.get("ticker") or "", p["gap"])
    )
    return {"as_of": as_of, "priorities": priorities}
