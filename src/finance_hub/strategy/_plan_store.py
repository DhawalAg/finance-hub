"""SQLite persistence for deployment plans.

Pure persistence: explicit args in, plain dicts out. The registered
``generate_deployment_plan`` wrapper owns the clock, state loading, and
the pure arithmetic; this module only writes/reads the
``fin_deployment_plan*`` tables. ``generate_deployment_plan`` is the sole
writer of recommendation-line rows, so there is intentionally no public
"insert a line" entry point beyond ``persist_plan``.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from finance_hub.store import connection


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def persist_plan(
    *,
    header: dict,
    lines: list[dict],
    warnings: list[dict],
    evidence: list[dict],
    now: str,
) -> None:
    """Write a plan header plus its lines, warning/block rows, evidence refs.

    All in one transaction so a half-written plan never lands. ``header``
    carries ``effective_policy`` as a dict; it is serialized to JSON here.
    ``lines`` carry ``ranked_factors`` as a list; same treatment.
    ``header`` may include Slice-10 freshness and mode fields.
    """
    blocked = header.get("blocked_output_modes")
    with connection.connect() as conn:
        conn.execute(
            "INSERT INTO fin_deployment_plans ("
            " plan_id, output_mode, status, portfolio_snapshot_id,"
            " strategy_version_id, benchmark_ticker, risk_mode, dca_cadence,"
            " deployable_cash_micros, dca_budget_micros, one_time_buy_budget_micros,"
            " dca_unallocated_micros, one_time_unallocated_micros,"
            " total_unallocated_micros, effective_policy, supersedes_plan_id,"
            " created_at,"
            " snapshot_freshness_band, snapshot_days_old,"
            " portfolio_changed_after_snapshot, blocked_output_modes"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                header["plan_id"],
                header["output_mode"],
                header["status"],
                header.get("portfolio_snapshot_id"),
                header.get("strategy_version_id"),
                header["benchmark_ticker"],
                header["risk_mode"],
                header.get("dca_cadence"),
                header["deployable_cash_micros"],
                header["dca_budget_micros"],
                header["one_time_buy_budget_micros"],
                header["dca_unallocated_micros"],
                header["one_time_unallocated_micros"],
                header["total_unallocated_micros"],
                json.dumps(header["effective_policy"]),
                header.get("supersedes_plan_id"),
                now,
                header.get("snapshot_freshness_band"),
                header.get("snapshot_days_old"),
                1 if header.get("portfolio_changed_after_snapshot") else 0,
                json.dumps(blocked) if blocked is not None else None,
            ),
        )
        for line in lines:
            conn.execute(
                "INSERT INTO fin_deployment_plan_lines ("
                " line_id, plan_id, bucket, ticker, sleeve_key, amount_micros,"
                " rank, ranked_factors, rationale, created_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    line["line_id"],
                    header["plan_id"],
                    line["bucket"],
                    line["ticker"],
                    line.get("sleeve_key"),
                    line["amount_micros"],
                    line["rank"],
                    json.dumps(line["ranked_factors"]),
                    line.get("rationale"),
                    now,
                ),
            )
        for w in warnings:
            conn.execute(
                "INSERT INTO fin_deployment_plan_warnings ("
                " plan_id, code, severity, ticker, message"
                ") VALUES (?,?,?,?,?)",
                (
                    header["plan_id"],
                    w["code"],
                    w["severity"],
                    w.get("ticker"),
                    w["message"],
                ),
            )
        for e in evidence:
            conn.execute(
                "INSERT INTO fin_deployment_plan_evidence ("
                " plan_id, line_id, evidence_type, ref_table, ref_key, summary"
                ") VALUES (?,?,?,?,?,?)",
                (
                    header["plan_id"],
                    e.get("line_id"),
                    e["evidence_type"],
                    e["ref_table"],
                    e["ref_key"],
                    e.get("summary"),
                ),
            )
        conn.commit()


def get_plan(plan_id: str) -> Optional[dict]:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_deployment_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        plan = _row_to_dict(row)
        plan["effective_policy"] = json.loads(plan["effective_policy"])
        plan["lines"] = []
        for r in conn.execute(
            "SELECT * FROM fin_deployment_plan_lines WHERE plan_id = ? "
            "ORDER BY bucket, rank",
            (plan_id,),
        ):
            line = _row_to_dict(r)
            line["ranked_factors"] = json.loads(line["ranked_factors"])
            plan["lines"].append(line)
        plan["warnings"] = [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM fin_deployment_plan_warnings WHERE plan_id = ? "
                "ORDER BY id",
                (plan_id,),
            )
        ]
        plan["evidence"] = [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM fin_deployment_plan_evidence WHERE plan_id = ? "
                "ORDER BY id",
                (plan_id,),
            )
        ]
    return plan


def load_snapshot_header(snapshot_id: str) -> Optional[dict]:
    """Return the header row for a snapshot (snapshot_id, as_of, ...), or None."""
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT * FROM fin_portfolio_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None


def load_snapshot_positions(snapshot_id: str) -> Optional[list[dict]]:
    """Return canonical positions for a snapshot, or None if it doesn't exist."""
    with connection.connect() as conn:
        snap = conn.execute(
            "SELECT 1 FROM fin_portfolio_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if snap is None:
            return None
        return [
            _row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM fin_portfolio_positions WHERE snapshot_id = ?",
                (snapshot_id,),
            )
        ]


def latest_price_ref(ticker: str) -> Optional[dict]:
    """Latest stored daily bar for ``ticker`` (most recent session), or None."""
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT ticker, session_date, close_micros, source "
            "FROM fin_price_bars WHERE ticker = ? "
            "ORDER BY session_date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None


def has_metrics(ticker: str) -> bool:
    with connection.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM fin_metrics WHERE scope = 'ticker' AND key = ? LIMIT 1",
            (ticker,),
        ).fetchone()
        return row is not None
