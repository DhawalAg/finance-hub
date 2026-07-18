"""Grader registry (spec §9 req 4, §6).

grade(transcript, db_path, workspace, task) → list[GraderResult]

Grader types dispatched from task YAML grader specs:
  sql   — run SQL against the trial DB; compare result to `expect` (==) or `expect_min` (>=)
  check — evaluate a Python expression against the transcript + workspace

Helpers available in check expressions:
  tool_result(name)       — last tool result dict for the named tool
  tool_called(name)       — True if the tool was called anywhere in the transcript
  tool_call_before(a, b)  — True if tool a appears before tool b in transcript
  tool_input(name, field) — the input dict (or one field) of the last call to name
  workspace(rel)          — _WorkspacePath for rel under the trial workspace

Grader spec resolution order:
  1. If the spec has inline `sql` or `check`, use it directly.
  2. Otherwise strip the namespace prefix (outcome./trajectory.) and look up
     the assertion by id in task.reference.assertions.
  3. If still not found: judge.* → skip (Phase 3); track/flag → skip; gate → fail.
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "grader_id": self.grader_id,
            "role": self.role,
            "verdict": self.verdict,
            "detail": self.detail,
            "actual": self.actual,
        }


# ---------------------------------------------------------------------------
# Workspace helper (for check expressions)
# ---------------------------------------------------------------------------

class _WorkspacePath:
    """Thin wrapper around a workspace-relative Path for check expressions."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def size(self) -> int:
        try:
            return self._path.stat().st_size
        except OSError:
            return 0

    def glob(self, pattern: str) -> list:
        try:
            return sorted(self._path.glob(pattern))
        except OSError:
            return []

    def exists(self) -> bool:
        return self._path.exists()

    def __bool__(self) -> bool:
        return self._path.exists()


def _make_workspace_fn(workspace: Path | None):
    def workspace_fn(rel: str = "") -> _WorkspacePath:
        base = workspace or Path(".")
        return _WorkspacePath(base / rel if rel else base)
    return workspace_fn


# ---------------------------------------------------------------------------
# Transcript helpers
# ---------------------------------------------------------------------------

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


def _tool_calls_ordered(transcript: Transcript) -> list[tuple[str, dict]]:
    """Return (name, input) for every tool_use in transcript order."""
    calls = []
    for event in transcript.events:
        if event.type != "assistant":
            continue
        for block in event.data.get("content", []):
            if block.get("type") == "tool_use":
                calls.append((block.get("name", ""), block.get("input", {})))
    return calls


def _make_trajectory_helpers(transcript: Transcript):
    """Build the tool_called / tool_call_before / tool_input helpers."""
    calls = _tool_calls_ordered(transcript)
    names = [name for name, _ in calls]

    def tool_called(name: str) -> bool:
        return name in names

    def tool_call_before(first: str, second: str) -> bool:
        try:
            fi = names.index(first)
        except ValueError:
            return False
        try:
            # find second occurrence AFTER first
            si = next(i for i, n in enumerate(names) if n == second and i > fi)
            return True
        except StopIteration:
            return False

    def tool_input(name: str, field: str = None) -> Any:
        for n, inp in reversed(calls):
            if n == name:
                return inp.get(field) if field is not None else inp
        return None

    return tool_called, tool_call_before, tool_input


# ---------------------------------------------------------------------------
# Grader spec resolution
# ---------------------------------------------------------------------------

def _resolve_grader_spec(spec: dict, task: dict) -> dict:
    """Merge spec with reference.assertions entry if spec has no sql/check."""
    if "sql" in spec or "check" in spec:
        return spec
    gid = spec.get("id", "")
    # Strip namespace prefix: outcome.foo → foo, trajectory.foo → foo
    short_id = gid.split(".", 1)[-1] if "." in gid else gid
    for assertion in task.get("reference", {}).get("assertions", []):
        if assertion.get("id") == short_id:
            merged = dict(spec)
            for key in ("sql", "check", "expect", "expect_min", "description"):
                if key in assertion and key not in merged:
                    merged[key] = assertion[key]
            return merged
    return spec


# ---------------------------------------------------------------------------
# Individual grader runners
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

    if isinstance(spec.get("expect"), list):
        # Multi-column lists (e.g. [["JNJ", 4], ...]) read all columns;
        # single-column lists (e.g. ["AAPL", "QQQ"]) read only the first.
        if spec["expect"] and isinstance(spec["expect"][0], (list, tuple)):
            actual: Any = [list(row) for row in rows]
        else:
            actual: Any = [row[0] for row in rows]
    else:
        actual = rows[0][0] if rows else None

    expect_min = spec.get("expect_min")
    if expect_min is not None:
        passed = actual is not None and actual >= expect_min
    elif "expect" in spec:
        passed = actual == spec["expect"]
    else:
        # No expect: grader just records the actual value (track metric)
        passed = True

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

    def tool_result(tool_name: str) -> Any:
        return _find_tool_result(transcript, tool_name)

    tool_called, tool_call_before, tool_input = _make_trajectory_helpers(transcript)

    ns = {
        "__builtins__": {},
        "tool_result": tool_result,
        "tool_called": tool_called,
        "tool_call_before": tool_call_before,
        "tool_input": tool_input,
        "workspace": _make_workspace_fn(workspace),
        "bool": bool,
        "len": len,
        "True": True,
        "False": False,
        "None": None,
    }

    try:
        passed = bool(eval(check_expr, ns))
    except Exception as exc:
        return GraderResult(gid, role, "fail", detail, actual=f"eval error: {exc}")

    return GraderResult(gid, role, "pass" if passed else "fail", detail)


# ---------------------------------------------------------------------------
# Public entry point
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
        resolved = _resolve_grader_spec(spec, task)
        gid = resolved.get("id", "unknown")
        role = resolved.get("role", "gate")

        # Phase 3: LLM judge graders are not yet implemented — skip cleanly.
        if gid.startswith("judge."):
            results.append(GraderResult(
                grader_id=gid,
                role=role,
                verdict="skip",
                detail=resolved.get("detail", "LLM judge grader (Phase 3, not yet implemented)"),
                actual="phase_3_not_implemented",
            ))
            continue

        if "sql" in resolved:
            results.append(_run_sql_grader(resolved, db_path))
        elif "check" in resolved:
            results.append(_run_check_grader(resolved, transcript, workspace))
        else:
            # Gate graders that aren't implemented fail; track/flag are skipped.
            results.append(GraderResult(
                grader_id=gid,
                role=role,
                verdict="fail" if role == "gate" else "skip",
                detail=resolved.get("detail", ""),
                actual="grader not yet implemented: no 'sql' or 'check' field",
            ))
    return results
