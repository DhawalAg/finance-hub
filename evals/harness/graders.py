"""Grader registry (spec §9 req 4, §6).

grade(transcript, db_path, workspace, task) → list[GraderResult]

Grader types dispatched from task YAML grader specs:
  sql   — run SQL against the trial DB; compare result to `expect` / `expect_min`
  check — evaluate a Python expression against the transcript + workspace

Grader specs may be inline (have 'sql' or 'check' fields directly) or may
reference an assertion from reference.assertions by ID (the grader id with its
'outcome.' or 'trajectory.' prefix stripped is matched against assertion ids).
Trajectory graders with no matching assertion return verdict='skip'.
"""
from __future__ import annotations

import re
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "grader_id": self.grader_id,
            "role": self.role,
            "verdict": self.verdict,
            "detail": self.detail,
            "actual": self.actual,
        }


# ---------------------------------------------------------------------------
# Transcript DSL helpers — used in check expressions
# ---------------------------------------------------------------------------

class _DictNamespace:
    """Wrap a dict so attribute-style access works in check expressions."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)

    def __repr__(self) -> str:
        return f"_DictNamespace({self.__dict__!r})"


class _ToolUsesProxy:
    """transcript.tool_uses — check tool presence in assistant turns."""

    def __init__(self, transcript: Transcript) -> None:
        self._names = [
            b.get("name")
            for e in transcript.events if e.type == "assistant"
            for b in e.data.get("content", [])
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]

    def contains(self, name: str) -> bool:
        return name in self._names

    def not_contains(self, name: str) -> bool:
        return name not in self._names


class _ToolResultsProxy:
    """transcript.tool_results — check error/success patterns in tool results."""

    def __init__(self, transcript: Transcript) -> None:
        id_to_name: dict[str, str] = {}
        for e in transcript.events:
            if e.type != "assistant":
                continue
            for b in e.data.get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    id_to_name[b.get("id", "")] = b.get("name", "")

        self._results: list[tuple[str, bool]] = []
        for e in transcript.events:
            if e.type != "user":
                continue
            content = e.data.get("content", [])
            if isinstance(content, str):
                continue
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tuid = b.get("tool_use_id", "")
                    name = id_to_name.get(tuid, "")
                    self._results.append((name, bool(b.get("is_error"))))

    def has_error(self, tool_name: str) -> bool:
        """True if any tool_result for this tool has is_error=true."""
        return any(n == tool_name and err for n, err in self._results)


class _ToolInputsProxy:
    """transcript.tool_inputs — inspect input fields of tool calls."""

    def __init__(self, transcript: Transcript) -> None:
        self._id_to_call: dict[str, tuple[str, dict]] = {}
        for e in transcript.events:
            if e.type != "assistant":
                continue
            for b in e.data.get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    self._id_to_call[b.get("id", "")] = (
                        b.get("name", ""),
                        b.get("input", {}),
                    )

        self._id_is_error: dict[str, bool] = {}
        for e in transcript.events:
            if e.type != "user":
                continue
            content = e.data.get("content", [])
            if isinstance(content, str):
                continue
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    self._id_is_error[b.get("tool_use_id", "")] = bool(b.get("is_error"))

    def field_nonempty(self, tool_name: str, field_name: str) -> bool:
        """True if any SUCCESSFUL call to tool_name has a non-empty value for field."""
        for tuid, (name, inp) in self._id_to_call.items():
            if name != tool_name:
                continue
            if self._id_is_error.get(tuid):
                continue
            val = inp.get(field_name)
            if val and str(val).strip():
                return True
        return False


class _TranscriptProxy:
    """transcript DSL object exposed in check expressions."""

    def __init__(self, transcript: Transcript) -> None:
        self.tool_uses = _ToolUsesProxy(transcript)
        self.tool_results = _ToolResultsProxy(transcript)
        self.tool_inputs = _ToolInputsProxy(transcript)


# ---------------------------------------------------------------------------
# Workspace DSL helpers — used in check expressions
# ---------------------------------------------------------------------------

class _SubpathProxy:
    """Result of workspace('subpath') — supports .glob() and .size."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def glob(self, pattern: str) -> list[Path]:
        if not self._path.exists():
            return []
        return list(self._path.glob(pattern))

    @property
    def size(self) -> int:
        if not self._path.exists():
            return 0
        return self._path.stat().st_size


class _WorkspaceProxy:
    """workspace(subpath) callable — returns _SubpathProxy."""

    def __init__(self, workspace: Path | None) -> None:
        self._root = workspace or Path("workspace")

    def __call__(self, subpath: str) -> _SubpathProxy:
        return _SubpathProxy(self._root / subpath)


# ---------------------------------------------------------------------------
# Internal: find tool result in transcript
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Assertion lookup — match outcome.*/trajectory.* grader IDs to assertions
# ---------------------------------------------------------------------------

def _resolve_spec(grader_spec: dict, task: dict) -> dict | None:
    """Return the assertion dict for a grader that lacks inline sql/check.

    Strips the 'outcome.' or 'trajectory.' prefix and looks up by id in
    reference.assertions. Returns None when no assertion is found.
    """
    gid = grader_spec.get("id", "")
    assertion_id = gid
    for prefix in ("outcome.", "trajectory.", "judge."):
        if gid.startswith(prefix):
            assertion_id = gid[len(prefix):]
            break

    for a in task.get("reference", {}).get("assertions", []):
        if a.get("id") == assertion_id:
            merged = {**grader_spec, **a, "id": gid}
            return merged
    return None


# ---------------------------------------------------------------------------
# Grader runners
# ---------------------------------------------------------------------------

def _run_sql_grader(spec: dict, db_path: Path) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "gate")
    detail = spec.get("detail", "")
    sql = spec["sql"]

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
    except Exception as exc:
        return GraderResult(gid, role, "fail", detail, actual=f"SQL error: {exc}")

    if "expect" in spec:
        expected = spec["expect"]
        if isinstance(expected, list):
            actual: Any = [row[0] for row in rows]
        else:
            actual = rows[0][0] if rows else None
        passed = actual == expected
    elif "expect_min" in spec:
        expected_min = spec["expect_min"]
        actual = rows[0][0] if rows else None
        passed = actual is not None and actual >= expected_min
    else:
        return GraderResult(gid, role, "fail", detail, actual="no 'expect' or 'expect_min' in spec")

    return GraderResult(gid, role, "pass" if passed else "fail", detail, actual=actual)


def _run_check_grader(
    spec: dict,
    transcript: Transcript,
    workspace: Path | None = None,
) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "gate")
    detail = spec.get("detail", "")
    check_expr = spec["check"]

    # Preprocess DSL: "X is empty" → "X == []"
    check_expr = re.sub(r"\bis\s+empty\b", "== []", check_expr)

    def tool_result(tool_name: str) -> Any:
        return _find_tool_result(transcript, tool_name)

    ns = {
        "__builtins__": {},
        "tool_result": tool_result,
        "transcript": _TranscriptProxy(transcript),
        "workspace": _WorkspaceProxy(workspace),
    }

    try:
        passed = bool(eval(check_expr, ns))
    except Exception as exc:
        return GraderResult(gid, role, "fail", detail, actual=f"eval error: {exc}")

    return GraderResult(gid, role, "pass" if passed else "fail", detail)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grade(
    transcript: Transcript,
    db_path: Path,
    workspace: Path,
    task: dict,
) -> list[GraderResult]:
    """Apply all graders for a task and return verdicts (spec §9 req 4)."""
    results = []
    for spec in task.get("graders", []):
        resolved = spec

        # If the spec has no sql/check, look up the assertion by ID
        if "sql" not in spec and "check" not in spec:
            resolved = _resolve_spec(spec, task)
            if resolved is None:
                results.append(GraderResult(
                    grader_id=spec.get("id", "unknown"),
                    role=spec.get("role", "gate"),
                    verdict="skip",
                    detail=spec.get("detail", ""),
                    actual="deferred: no assertion registered for this grader",
                ))
                continue

        if "sql" in resolved:
            results.append(_run_sql_grader(resolved, db_path))
        elif "check" in resolved:
            results.append(_run_check_grader(resolved, transcript, workspace))
        else:
            results.append(GraderResult(
                grader_id=resolved.get("id", "unknown"),
                role=resolved.get("role", "gate"),
                verdict="fail",
                detail=resolved.get("detail", ""),
                actual="unknown grader type: no 'sql' or 'check' field",
            ))
    return results
