"""Grader registry (spec §9 req 4, §6).

grade(transcript, db_path, workspace, task) → list[GraderResult]

Grader types dispatched from task YAML grader specs:
  sql   — run SQL against the trial DB; compare result to `expect`
  check — evaluate a Python expression against the transcript
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.harness.runner import Transcript


@dataclass
class GraderResult:
    grader_id: str
    role: str           # gate | track | flag
    verdict: str        # pass | fail | skip
    detail: str
    actual: Any = field(default=None)
    graded_at: str | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "grader_id": self.grader_id,
            "role": self.role,
            "verdict": self.verdict,
            "detail": self.detail,
            "actual": self.actual,
            "graded_at": self.graded_at,
        }


class _DictNamespace:
    """Wrap a dict so attribute-style access works in check expressions."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)

    def __repr__(self) -> str:
        return f"_DictNamespace({self.__dict__!r})"


def _find_tool_result(transcript: Transcript, tool_name: str) -> Any:
    """Return the content of the last tool result for tool_name in transcript."""
    for event in transcript.events:
        if event.type != "assistant":
            continue
        for block in event.data.get("content", []):
            if block.get("type") != "tool_use" or block.get("name") != tool_name:
                continue
            tool_use_id = block.get("id")
            for ue in transcript.events:
                if ue.type != "user":
                    continue
                content = ue.data.get("content", [])
                if isinstance(content, str):
                    continue
                for ub in content:
                    if (
                        ub.get("type") == "tool_result"
                        and ub.get("tool_use_id") == tool_use_id
                    ):
                        raw = ub.get("content")
                        return _DictNamespace(raw) if isinstance(raw, dict) else raw
    return None


def _run_sql_grader(spec: dict, db_path: Path | None) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "gate")
    detail = spec.get("detail", "")
    sql = spec["sql"]
    expected = spec["expect"]

    if db_path is None:
        return GraderResult(gid, role, "skip", detail, actual="sql grader skipped: no db_path")

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
    except Exception as exc:
        return GraderResult(gid, role, "fail", detail, actual=f"SQL error: {exc}")

    if isinstance(expected, list):
        actual: Any = [row[0] for row in rows]
    else:
        actual = rows[0][0] if rows else None
    passed = actual == expected

    return GraderResult(gid, role, "pass" if passed else "fail", detail, actual=actual)


def _run_check_grader(spec: dict, transcript: Transcript) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "gate")
    detail = spec.get("detail", "")
    check_expr = spec["check"]

    def tool_result(tool_name: str) -> Any:
        return _find_tool_result(transcript, tool_name)

    try:
        passed = bool(eval(check_expr, {"__builtins__": {}, "tool_result": tool_result}))
    except Exception as exc:
        return GraderResult(gid, role, "fail", detail, actual=f"eval error: {exc}")

    return GraderResult(gid, role, "pass" if passed else "fail", detail)


def grade(
    transcript: Transcript,
    db_path: Path | None,
    workspace: Path,
    task: dict,
) -> list[GraderResult]:
    """Apply all graders for a task and return verdicts (spec §9 req 4)."""
    results = []
    for spec in task.get("graders", []):
        if "sql" in spec:
            results.append(_run_sql_grader(spec, db_path))
        elif "check" in spec:
            results.append(_run_check_grader(spec, transcript))
        else:
            results.append(GraderResult(
                grader_id=spec.get("id", "unknown"),
                role=spec.get("role", "gate"),
                verdict="fail",
                detail=spec.get("detail", ""),
                actual="unknown grader type: no 'sql' or 'check' field",
            ))
    return results
