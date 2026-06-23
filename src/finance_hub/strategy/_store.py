"""SQLite persistence for the strategy slice.

Pure persistence: every function takes explicit args (including ``now``)
and returns plain dicts. The registered ``tools`` module owns the clock,
research snapshotting, and validation; this module only reads and writes
the ``fin_strategy_*`` tables.

A strategy version is an immutable snapshot of allocation intent: once
created, later research edits never reach back into these rows (the
promotion path copies the values it needs at creation time).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from finance_hub.store import connection


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def create_strategy_version(
    *,
    version_id: str,
    label: Optional[str],
    status: str,
    notes: Optional[str],
    sleeves: list[dict],
    instruments: list[dict],
    now: str,
) -> dict:
    """Insert a version with its sleeves and eligible instruments atomically.

    ``sleeves`` rows carry ``sleeve_key``/``display_name``/
    ``target_weight_bps``/``hard_cap_bps``; ``instruments`` rows carry
    ``ticker``/``primary_sleeve_key``/``instrument_role``/``conviction``/
    ``source_theme_key``/``hard_cap_bps``/``note``. The whole thing rolls
    back if any row violates a constraint (e.g. a second ``active``
    version or a ticker mapped twice).
    """
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_strategy_versions "
            "(version_id, label, status, notes, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (version_id, label, status, notes, now, now),
        )
        for s in sleeves:
            conn.execute(
                "INSERT INTO fin_strategy_sleeves "
                "(version_id, sleeve_key, display_name, target_weight_bps, "
                " hard_cap_bps, created_at) VALUES (?,?,?,?,?,?)",
                (
                    version_id,
                    s["sleeve_key"],
                    s.get("display_name"),
                    s["target_weight_bps"],
                    s.get("hard_cap_bps"),
                    now,
                ),
            )
        for i in instruments:
            conn.execute(
                "INSERT INTO fin_strategy_instruments "
                "(version_id, ticker, primary_sleeve_key, instrument_role, "
                " conviction, source_theme_key, hard_cap_bps, note, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    version_id,
                    i["ticker"],
                    i["primary_sleeve_key"],
                    i.get("instrument_role"),
                    i.get("conviction"),
                    i.get("source_theme_key"),
                    i.get("hard_cap_bps"),
                    i.get("note"),
                    now,
                ),
            )
        conn.commit()
    result = get_strategy_version(version_id)
    assert result is not None  # we just inserted it
    return result


def get_strategy_version(version_id: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_strategy_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        version = _row_to_dict(row)
        version["sleeves"] = [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM fin_strategy_sleeves WHERE version_id = ? "
                "ORDER BY sleeve_key",
                (version_id,),
            ).fetchall()
        ]
        version["instruments"] = [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM fin_strategy_instruments WHERE version_id = ? "
                "ORDER BY ticker",
                (version_id,),
            ).fetchall()
        ]
    return version


def list_strategy_versions(*, status: Optional[str] = None) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connection.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM fin_strategy_versions{where} ORDER BY version_id",
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_version_status(*, version_id: str, status: str, now: str) -> dict:
    with connection.connect() as conn:
        conn.execute(
            "UPDATE fin_strategy_versions SET status = ?, updated_at = ? "
            "WHERE version_id = ?",
            (status, now, version_id),
        )
        conn.commit()
    result = get_strategy_version(version_id)
    assert result is not None
    return result
