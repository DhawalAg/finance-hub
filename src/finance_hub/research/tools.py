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
_NOTE_SCOPES = ("theme", "instrument")
_NOTE_SUBDIR = {"theme": "themes", "instrument": "instruments"}
_LINK_SCOPES = ("theme", "instrument")
_LINK_STATUSES = ("active", "superseded", "archived")


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


def _require_note_target(scope: str, key: str) -> None:
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
    if scope not in _NOTE_SCOPES:
        raise ValueError(f"scope must be one of {_NOTE_SCOPES}, got {scope!r}")
    _require_note_target(scope, key)
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
    if scope not in _NOTE_SCOPES:
        raise ValueError(f"scope must be one of {_NOTE_SCOPES}, got {scope!r}")
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


def _require_link_target(scope: str, key: str) -> None:
    if scope == "theme":
        if _store.get_theme(key) is None:
            raise LookupError(f"no theme with key {key!r}")
    else:
        if _store.get_instrument(key) is None:
            raise LookupError(f"no instrument with ticker {key!r}")


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
    if scope not in _LINK_SCOPES:
        raise ValueError(f"scope must be one of {_LINK_SCOPES}, got {scope!r}")
    if _store.get_source_by_id(source_id) is None:
        raise LookupError(f"no source with id {source_id!r}")
    _require_link_target(scope, key)
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
    if scope not in _LINK_SCOPES:
        raise ValueError(f"scope must be one of {_LINK_SCOPES}, got {scope!r}")
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
