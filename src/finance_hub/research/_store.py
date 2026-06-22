"""SQLite persistence for the research slice.

Pure persistence: every function takes explicit args (including ``now``)
and returns plain dicts. No clock or registry coupling — the registered
``tools`` module owns those.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from finance_hub.store import connection


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# themes
# ---------------------------------------------------------------------------


def upsert_theme(
    *,
    key: str,
    display_name: str,
    description: Optional[str],
    status: str,
    parent_key: Optional[str],
    note_path: Optional[str],
    now: str,
) -> dict:
    with connection.connect() as conn:
        if parent_key is not None:
            parent = conn.execute(
                "SELECT key FROM fin_themes WHERE key = ?", (parent_key,)
            ).fetchone()
            if parent is None:
                raise ValueError(f"parent_key {parent_key!r} does not exist")
        existing = conn.execute(
            "SELECT * FROM fin_themes WHERE key = ?", (key,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO fin_themes "
                "(key, display_name, description, status, parent_key, note_path, "
                " created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    key,
                    display_name,
                    description,
                    status,
                    parent_key,
                    note_path,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                "UPDATE fin_themes SET "
                "display_name = ?, description = ?, status = ?, "
                "parent_key = ?, note_path = COALESCE(?, note_path), "
                "updated_at = ? "
                "WHERE key = ?",
                (
                    display_name,
                    description,
                    status,
                    parent_key,
                    note_path,
                    now,
                    key,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_themes WHERE key = ?", (key,)
        ).fetchone()
    return _row_to_dict(row)


def list_themes(
    *,
    status: Optional[str] = None,
    parent_key: Optional[str] = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    else:
        # archived themes are noise unless explicitly requested.
        clauses.append("status != 'archived'")
    if parent_key is not None:
        clauses.append("parent_key = ?")
        params.append(parent_key)
    where = " AND ".join(clauses)
    sql = f"SELECT * FROM fin_themes WHERE {where} ORDER BY key"
    with connection.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_theme(key: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_themes WHERE key = ?", (key,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# instruments + theme-instrument edges
# ---------------------------------------------------------------------------


def upsert_instrument(
    *,
    ticker: str,
    type_: str,
    instrument_role: str,
    display_name: Optional[str],
    note_path: Optional[str],
    now: str,
) -> dict:
    with connection.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM fin_instruments WHERE ticker = ?", (ticker,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO fin_instruments "
                "(ticker, type, instrument_role, display_name, note_path, "
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    ticker,
                    type_,
                    instrument_role,
                    display_name,
                    note_path,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                "UPDATE fin_instruments SET "
                "type = ?, instrument_role = ?, "
                "display_name = COALESCE(?, display_name), "
                "note_path = COALESCE(?, note_path), "
                "updated_at = ? "
                "WHERE ticker = ?",
                (
                    type_,
                    instrument_role,
                    display_name,
                    note_path,
                    now,
                    ticker,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_instruments WHERE ticker = ?", (ticker,)
        ).fetchone()
    return _row_to_dict(row)


def get_instrument(ticker: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_instruments WHERE ticker = ?", (ticker,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def set_theme_note_path(*, key: str, note_path: str, now: str) -> dict:
    with connection.connect() as conn:
        conn.execute(
            "UPDATE fin_themes SET note_path = ?, updated_at = ? WHERE key = ?",
            (note_path, now, key),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_themes WHERE key = ?", (key,)
        ).fetchone()
    return _row_to_dict(row)


def set_instrument_note_path(*, ticker: str, note_path: str, now: str) -> dict:
    with connection.connect() as conn:
        conn.execute(
            "UPDATE fin_instruments SET note_path = ?, updated_at = ? "
            "WHERE ticker = ?",
            (note_path, now, ticker),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_instruments WHERE ticker = ?", (ticker,)
        ).fetchone()
    return _row_to_dict(row)


def upsert_theme_instrument(
    *,
    theme_key: str,
    ticker: str,
    status: str,
    role: Optional[str],
    conviction: Optional[int],
    conviction_note: Optional[str],
    note: Optional[str],
    now: str,
) -> dict:
    with connection.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM fin_theme_instruments "
            "WHERE theme_key = ? AND ticker = ?",
            (theme_key, ticker),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO fin_theme_instruments "
                "(theme_key, ticker, status, role, conviction, conviction_note, "
                " note, added_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    theme_key,
                    ticker,
                    status,
                    role,
                    conviction,
                    conviction_note,
                    note,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                "UPDATE fin_theme_instruments SET "
                "status = ?, role = ?, conviction = ?, "
                "conviction_note = ?, note = COALESCE(?, note), "
                "updated_at = ? "
                "WHERE theme_key = ? AND ticker = ?",
                (
                    status,
                    role,
                    conviction,
                    conviction_note,
                    note,
                    now,
                    theme_key,
                    ticker,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_theme_instruments "
            "WHERE theme_key = ? AND ticker = ?",
            (theme_key, ticker),
        ).fetchone()
    return _row_to_dict(row)


def list_theme_instruments(*, theme_key: str) -> list[dict]:
    with connection.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM fin_theme_instruments "
            "WHERE theme_key = ? ORDER BY ticker",
            (theme_key,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_theme_instrument(*, theme_key: str, ticker: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_theme_instruments "
            "WHERE theme_key = ? AND ticker = ?",
            (theme_key, ticker),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# sources + source links
# ---------------------------------------------------------------------------


def upsert_source(
    *,
    url: str,
    title: Optional[str],
    publisher: Optional[str],
    source_type: Optional[str],
    published_on: Optional[str],
    trusted: bool,
    now: str,
) -> dict:
    with connection.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM fin_research_sources WHERE url = ?", (url,)
        ).fetchone()
        trusted_int = 1 if trusted else 0
        if existing is None:
            conn.execute(
                "INSERT INTO fin_research_sources "
                "(url, title, publisher, source_type, published_on, trusted, "
                " first_accessed_at, last_accessed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    url,
                    title,
                    publisher,
                    source_type,
                    published_on,
                    trusted_int,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                "UPDATE fin_research_sources SET "
                "title = COALESCE(?, title), "
                "publisher = COALESCE(?, publisher), "
                "source_type = COALESCE(?, source_type), "
                "published_on = COALESCE(?, published_on), "
                "trusted = ?, "
                "last_accessed_at = ? "
                "WHERE url = ?",
                (
                    title,
                    publisher,
                    source_type,
                    published_on,
                    trusted_int,
                    now,
                    url,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_research_sources WHERE url = ?", (url,)
        ).fetchone()
    return _row_to_dict(row)


def upsert_source_link(
    *,
    source_id: int,
    scope: str,
    key: str,
    note: Optional[str],
    status: str,
    review_after: Optional[str],
    now: str,
) -> dict:
    with connection.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM fin_research_source_links "
            "WHERE source_id = ? AND scope = ? AND key = ?",
            (source_id, scope, key),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO fin_research_source_links "
                "(source_id, scope, key, note, status, review_after, linked_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (source_id, scope, key, note, status, review_after, now),
            )
        else:
            conn.execute(
                "UPDATE fin_research_source_links SET "
                "note = COALESCE(?, note), status = ?, "
                "review_after = COALESCE(?, review_after) "
                "WHERE source_id = ? AND scope = ? AND key = ?",
                (note, status, review_after, source_id, scope, key),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_research_source_links "
            "WHERE source_id = ? AND scope = ? AND key = ?",
            (source_id, scope, key),
        ).fetchone()
    return _row_to_dict(row)


def mark_source_link_reviewed(
    *,
    source_id: int,
    scope: str,
    key: str,
    status: str,
    reviewed_at: str,
    review_after: Optional[str],
) -> Optional[dict]:
    with connection.connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM fin_research_source_links "
            "WHERE source_id = ? AND scope = ? AND key = ?",
            (source_id, scope, key),
        ).fetchone()
        if existing is None:
            return None
        conn.execute(
            "UPDATE fin_research_source_links SET "
            "status = ?, reviewed_at = ?, "
            "review_after = COALESCE(?, review_after) "
            "WHERE source_id = ? AND scope = ? AND key = ?",
            (status, reviewed_at, review_after, source_id, scope, key),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fin_research_source_links "
            "WHERE source_id = ? AND scope = ? AND key = ?",
            (source_id, scope, key),
        ).fetchone()
    return _row_to_dict(row)


def list_source_links(*, scope: str, key: str) -> list[dict]:
    with connection.connect() as conn:
        rows = conn.execute(
            "SELECT l.*, s.url, s.title, s.publisher, s.source_type, "
            "       s.published_on, s.trusted "
            "FROM fin_research_source_links AS l "
            "JOIN fin_research_sources AS s ON s.id = l.source_id "
            "WHERE l.scope = ? AND l.key = ? "
            "ORDER BY l.linked_at",
            (scope, key),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_sources(
    *,
    scope: Optional[str] = None,
    key: Optional[str] = None,
) -> list[dict]:
    """List sources, optionally filtered to those linked to a (scope,key)."""
    with connection.connect() as conn:
        if scope is None and key is None:
            rows = conn.execute(
                "SELECT * FROM fin_research_sources ORDER BY id"
            ).fetchall()
            sources = [_row_to_dict(r) for r in rows]
            for s in sources:
                s["links"] = _all_links_for_source(conn, s["id"])
            return sources
        if scope is None or key is None:
            raise ValueError("scope and key must be supplied together")
        rows = conn.execute(
            "SELECT s.* FROM fin_research_sources AS s "
            "JOIN fin_research_source_links AS l ON l.source_id = s.id "
            "WHERE l.scope = ? AND l.key = ? "
            "ORDER BY s.id",
            (scope, key),
        ).fetchall()
        sources = [_row_to_dict(r) for r in rows]
        for s in sources:
            s["links"] = _all_links_for_source(conn, s["id"])
    return sources


def _all_links_for_source(conn, source_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM fin_research_source_links WHERE source_id = ? "
        "ORDER BY linked_at",
        (source_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def sources_due_for_review(*, as_of: str) -> list[dict]:
    """Active source links whose review_after has passed ``as_of``."""
    with connection.connect() as conn:
        rows = conn.execute(
            "SELECT l.*, s.url, s.title, s.publisher "
            "FROM fin_research_source_links AS l "
            "JOIN fin_research_sources AS s ON s.id = l.source_id "
            "WHERE l.status = 'active' "
            "  AND l.review_after IS NOT NULL "
            "  AND l.review_after <= ? "
            "ORDER BY l.review_after",
            (as_of,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_source_by_url(url: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_research_sources WHERE url = ?", (url,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def get_source_by_id(source_id: int) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_research_sources WHERE id = ?", (source_id,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# read-contract helpers (candidate_evidence / research_priorities)
# ---------------------------------------------------------------------------


def list_themes_for_ticker(ticker: str) -> list[dict]:
    """Theme edges a ticker maps to, carrying the theme's own note path."""
    with connection.connect() as conn:
        rows = conn.execute(
            "SELECT ti.theme_key, ti.status, ti.role, ti.conviction, "
            "       ti.conviction_note, ti.note, t.note_path AS theme_note_path "
            "FROM fin_theme_instruments AS ti "
            "JOIN fin_themes AS t ON t.key = ti.theme_key "
            "WHERE ti.ticker = ? "
            "ORDER BY ti.theme_key",
            (ticker,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_candidates(*, include_rejected: bool = False) -> list[dict]:
    """Every theme-instrument candidate edge with its instrument facts."""
    sql = (
        "SELECT ti.theme_key, ti.ticker, ti.status, ti.role, ti.conviction, "
        "       i.type, i.instrument_role, i.display_name, i.note_path "
        "FROM fin_theme_instruments AS ti "
        "JOIN fin_instruments AS i ON i.ticker = ti.ticker "
    )
    if not include_rejected:
        sql += "WHERE ti.status != 'rejected' "
    sql += "ORDER BY ti.ticker, ti.theme_key"
    with connection.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(r) for r in rows]


def table_exists(name: str) -> bool:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    return row is not None


def has_rows(table: str, *, where: str = "", params: tuple = ()) -> bool:
    """True if ``table`` exists and holds at least one matching row.

    Degrades gracefully: an absent downstream table reads as "no rows"
    rather than raising, so the gap scan reports it instead of erroring.
    """
    if not table_exists(table):
        return False
    sql = f"SELECT 1 FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += " LIMIT 1"
    with connection.connect() as conn:
        return conn.execute(sql, params).fetchone() is not None
