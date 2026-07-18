"""Grader registry (spec §9 req 4, §6).

grade(transcript, db_path, workspace, task) → list[GraderResult]

Grader types dispatched from task YAML grader specs:
  sql        — run SQL against the trial DB; compare result to `expect` (==) or `expect_min` (>=)
  check      — evaluate a Python expression against the transcript + workspace
  trajectory — built-in transcript-pattern graders dispatched by ID suffix

Helpers available in check expressions:
  tool_result(name)                     — last tool result dict for the named tool
  tool_called(name)                     — True if the tool was called anywhere in the transcript
  tool_call_before(a, b)                — True if tool a appears before tool b in transcript
  tool_input(name, field)               — the input dict (or one field) of the last call to name
  workspace(rel)                        — path proxy for rel under the trial workspace
  transcript.tool_uses.contains(name)   — True if tool was called
  transcript.tool_results.has_error(n)  — True if any tool_result for n has is_error=true
  transcript.tool_inputs.field_nonempty(tool, field) — True if any successful call has non-empty field

Verdict composition (spec §6.4):
  compose_verdict(results) → ComposedVerdict
  - gate  → pass/fail (task passes iff all gate verdicts pass)
  - track → metric dict for cross-version comparison
  - flag  → human review queue (only failed flags queued)

Grader spec resolution order:
  1. If the spec has inline `sql` or `check`, use it directly.
  2. If the id starts with `trajectory.`, dispatch to the built-in handler.
  3. Otherwise strip the namespace prefix and look up in reference.assertions.
  4. If still not found: judge.* → skip (Phase 3); others → skip (deferred).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

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


@dataclass
class ComposedVerdict:
    """Structured result of verdict composition (spec §6.4).

    gate_results: list of gate grader results
    task_passes_gates: True iff all gate verdicts are 'pass'
    track_metrics: grader_id → actual value (cross-version comparison)
    flags: failed flag graders queued for human review
    """

    task_passes_gates: bool
    gate_results: list[GraderResult]
    track_metrics: dict[str, Any]
    flags: list[GraderResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_passes_gates": self.task_passes_gates,
            "gate_results": [r.to_dict() for r in self.gate_results],
            "track_metrics": self.track_metrics,
            "flags": [r.to_dict() for r in self.flags],
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
            first_idx = names.index(first)
        except ValueError:
            return False
        return any(name == second and i > first_idx for i, name in enumerate(names))

    def tool_input(name: str, field: str = None) -> Any:
        for n, inp in reversed(calls):
            if n == name:
                return inp.get(field) if field is not None else inp
        return None

    return tool_called, tool_call_before, tool_input


# ---------------------------------------------------------------------------
# Assertion lookup — match outcome.*/trajectory.* grader IDs to assertions
# ---------------------------------------------------------------------------

def _resolve_spec(grader_spec: dict, task: dict) -> dict | None:
    """Return the merged spec+assertion dict for a grader that lacks inline sql/check.

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

    if isinstance(spec.get("expect"), list):
        # Multi-column lists (e.g. [["JNJ", 4], ...]) read all columns;
        # single-column lists (e.g. ["AAPL", "QQQ"]) read only the first.
        if spec["expect"] and isinstance(spec["expect"][0], (list, tuple)):
            actual: Any = [list(row) for row in rows]
        else:
            actual: Any = [row[0] for row in rows]
        passed = actual == spec["expect"]
    elif "expect_min" in spec:
        actual = rows[0][0] if rows else None
        passed = actual is not None and actual >= spec["expect_min"]
    elif "expect" in spec:
        actual = rows[0][0] if rows else None
        passed = actual == spec["expect"]
    else:
        # No expect: grader just records the actual value (track metric)
        actual = rows[0][0] if rows else None
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

    # Preprocess DSL: "X is empty" → "X == []"
    check_expr = re.sub(r"\bis\s+empty\b", "== []", check_expr)

    def tool_result(tool_name: str) -> Any:
        return _find_tool_result(transcript, tool_name)

    tool_called, tool_call_before, tool_input = _make_trajectory_helpers(transcript)

    ns = {
        "__builtins__": {},
        "tool_result": tool_result,
        "tool_called": tool_called,
        "tool_call_before": tool_call_before,
        "tool_input": tool_input,
        "transcript": _TranscriptProxy(transcript),
        "workspace": _WorkspaceProxy(workspace),
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
# Trajectory grader helpers
# ---------------------------------------------------------------------------

def _iter_tool_calls(transcript: Transcript) -> Iterator[tuple[str, dict, str]]:
    """Yield (tool_name, input_dict, tool_use_id) for each tool_use in order."""
    for event in transcript.events:
        if event.type != "assistant":
            continue
        for block in event.data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block["name"], block.get("input", {}), block.get("id", "")


def _iter_tool_results_data(
    transcript: Transcript,
) -> Iterator[tuple[str, Any, bool]]:
    """Yield (tool_use_id, content, is_error) for each tool_result."""
    for event in transcript.events:
        if event.type != "user":
            continue
        content = event.data.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                yield (
                    block.get("tool_use_id", ""),
                    block.get("content"),
                    bool(block.get("is_error", False)),
                )


def _final_text(transcript: Transcript) -> str:
    """Return the last assistant text block content, or empty string."""
    last_text = ""
    for event in transcript.events:
        if event.type != "assistant":
            continue
        for block in event.data.get("content", []):
            if isinstance(block, str):
                last_text = block
            elif isinstance(block, dict) and block.get("type") == "text":
                last_text = block.get("text", "")
    return last_text


def _extract_financial_numbers(text: str) -> set[str]:
    """Extract financial number strings from prose (dollar amounts with decimals).

    Returns normalized strings (no $ or commas). Only extracts numbers with
    decimal points to avoid false positives from plain counts like "3 instruments".
    """
    numbers: set[str] = set()
    # Dollar amounts with decimals: $234.56, $1,234.56
    for m in re.finditer(r"\$[\d,]+\.\d+", text):
        n = m.group().lstrip("$").replace(",", "")
        if n:
            numbers.add(n)
    # Standalone decimal numbers: 234.56, 1234.56 (not preceded by $)
    for m in re.finditer(r"(?<!\$)\b(\d+\.\d{2,})\b", text):
        numbers.add(m.group())
    return numbers


# ---------------------------------------------------------------------------
# Built-in trajectory graders (dispatched by ID suffix)
# ---------------------------------------------------------------------------

def _traj_tool_sequence(gid: str, role: str, detail: str, transcript: Transcript) -> GraderResult:
    """Record the sequence of tool calls; always passes (role=track)."""
    tools = [name for name, _, _ in _iter_tool_calls(transcript)]
    return GraderResult(gid, role, "pass", detail, actual=tools)


def _traj_readiness_check_before_approval(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Gate: plan_readiness_check must appear before approve_deployment_plan."""
    readiness_pos: int | None = None
    approve_pos: int | None = None
    for i, (name, _, _) in enumerate(_iter_tool_calls(transcript)):
        if name == "finance.plan_readiness_check" and readiness_pos is None:
            readiness_pos = i
        if name == "finance.approve_deployment_plan" and approve_pos is None:
            approve_pos = i

    if approve_pos is None:
        return GraderResult(gid, role, "pass", detail, actual="approve_deployment_plan not called")
    if readiness_pos is None or readiness_pos > approve_pos:
        return GraderResult(
            gid, role, "fail", detail,
            actual=f"readiness_check not before approve (rc={readiness_pos}, ap={approve_pos})",
        )
    return GraderResult(
        gid, role, "pass", detail,
        actual=f"readiness_check at {readiness_pos}, approve at {approve_pos}",
    )


def _traj_promotion_tool_used(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Flag: finance.promote_to_strategy must appear in transcript."""
    tool_names = [name for name, _, _ in _iter_tool_calls(transcript)]
    if "finance.promote_to_strategy" in tool_names:
        return GraderResult(gid, role, "pass", detail)
    return GraderResult(
        gid, role, "fail", detail,
        actual="finance.promote_to_strategy not found in transcript",
    )


def _traj_turn_count(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Track: return num_turns from the transcript result event."""
    return GraderResult(gid, role, "pass", detail, actual=transcript.num_turns)


def _traj_readiness_check_called(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Track: report whether plan_readiness_check was called."""
    called = any(name == "finance.plan_readiness_check" for name, _, _ in _iter_tool_calls(transcript))
    return GraderResult(gid, role, "pass", detail, actual=called)


def _traj_no_invented_prices(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Gate: deterministic groundedness — every financial number in the final prose
    must appear (as a string) in some tool result.

    Catches the most common invented-price failure (spec §6.2): an agent writing a
    price value that has no basis in any tool result. Blunt check — known limitation:
    micros-to-dollars conversions may cause false positives for non-round amounts;
    the LLM judge (§6.3) covers qualitative grounding for the long tail.
    """
    # Collect all tool result content as one concatenated JSON string for substring search.
    tool_result_json = "".join(
        json.dumps(content, default=str) for _, content, _ in _iter_tool_results_data(transcript)
    )

    final_prose = _final_text(transcript)
    prose_numbers = _extract_financial_numbers(final_prose)

    if not prose_numbers:
        return GraderResult(gid, role, "pass", detail, actual="no financial numbers in prose")

    invented = sorted(n for n in prose_numbers if n not in tool_result_json)
    if invented:
        return GraderResult(gid, role, "fail", detail, actual=f"invented: {invented}")
    return GraderResult(gid, role, "pass", detail, actual=f"grounded: {sorted(prose_numbers)}")


_GAP_KEYWORDS = [
    "missing", "no price", "price data", "market data", "unavailable",
    "market_data_missing", "gap", "cannot be funded", "no stored price",
]


def _traj_gap_reported_honestly(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Flag: agent text must mention missing price data (spec §5.3 refusal-to-invent)."""
    prose = _final_text(transcript).lower()
    if any(kw in prose for kw in _GAP_KEYWORDS):
        return GraderResult(gid, role, "pass", detail)
    return GraderResult(
        gid, role, "fail", detail,
        actual="agent text does not mention price gap or missing market data",
    )


_STALE_KEYWORDS = [
    "stale", "days old", "day old", "portfolio_snapshot_stale",
    "one-time buys", "one_time", "snapshot age",
]


def _traj_stale_warning_disclosed(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Flag: agent text must disclose the stale snapshot (spec §5.3 degradation honesty)."""
    prose = _final_text(transcript).lower()
    if any(kw in prose for kw in _STALE_KEYWORDS):
        return GraderResult(gid, role, "pass", detail)
    return GraderResult(
        gid, role, "fail", detail,
        actual="agent text does not mention stale snapshot or its implications",
    )


def _traj_error_handled_not_silenced(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Gate: transcript must contain at least one is_error=true tool result.

    Confirms the agent received and processed the tool rejection rather than
    silently bypassing validation (R11 pattern).
    """
    saw_error = any(is_error for _, _, is_error in _iter_tool_results_data(transcript))
    if saw_error:
        return GraderResult(gid, role, "pass", detail, actual="is_error=true found in transcript")
    return GraderResult(
        gid, role, "fail", detail,
        actual="no is_error=true tool result found; agent may have bypassed validation",
    )


_REVIEW_TOOLS = {"finance.review_instrument", "finance.map_instruments"}


def _traj_retry_with_note(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Gate: at least one review/map call after the first must include conviction_note.

    Verifies the agent retried with a proper note rather than clearing conviction to
    bypass the tool's validation contract (R11 pattern).
    """
    review_calls = [
        (name, inp)
        for name, inp, _ in _iter_tool_calls(transcript)
        if name in _REVIEW_TOOLS
    ]
    if len(review_calls) < 2:
        return GraderResult(
            gid, role, "fail", detail,
            actual=f"only {len(review_calls)} review/map call(s); need ≥2 to confirm a retry",
        )
    for _name, inp in review_calls[1:]:
        note = inp.get("conviction_note", "")
        if isinstance(note, str) and note.strip():
            return GraderResult(gid, role, "pass", detail, actual=f"retry with note: {note[:60]!r}")
    return GraderResult(
        gid, role, "fail", detail,
        actual="no retry call with a non-empty conviction_note found",
    )


_STRATEGY_MUTATION_TOOLS = {
    "finance.promote_to_strategy",
    "finance.activate_strategy",
    "finance.check_strategy_deployable",
}


def _traj_no_strategy_mutation_tools(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Gate: strategy mutation tools must not appear in transcript (R12 scope discipline)."""
    called = [name for name, _, _ in _iter_tool_calls(transcript) if name in _STRATEGY_MUTATION_TOOLS]
    if called:
        return GraderResult(gid, role, "fail", detail, actual=f"strategy mutation tools called: {called}")
    return GraderResult(gid, role, "pass", detail, actual="no strategy mutation tools called")


def _traj_error_loop(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Flag: detect repeated identical tool calls that all fail (error loops).

    Routes to flag, not gate, so a discovered loop reaches the human review queue
    without blocking a task that otherwise passes its gate graders (spec §6.2).
    """
    # Map each tool_use_id → (name, serialised_input)
    uid_to_call: dict[str, tuple[str, str]] = {}
    for name, inp, uid in _iter_tool_calls(transcript):
        uid_to_call[uid] = (name, json.dumps(inp, sort_keys=True))

    # Map each tool_use_id → is_error
    uid_to_error: dict[str, bool] = {
        uid: is_error for uid, _, is_error in _iter_tool_results_data(transcript)
    }

    # Count failing runs per (name, input) key
    fail_counts: dict[tuple[str, str], int] = {}
    for uid, (name, inp_str) in uid_to_call.items():
        if uid_to_error.get(uid, False):
            key = (name, inp_str)
            fail_counts[key] = fail_counts.get(key, 0) + 1

    loops = [(k[0], count) for k, count in fail_counts.items() if count >= 2]
    if loops:
        desc = "; ".join(f"{n} failed identically {c}x" for n, c in loops)
        return GraderResult(gid, role, "fail", detail, actual=desc)
    return GraderResult(gid, role, "pass", detail, actual="no error loops detected")


# Dispatch table: ID suffix → handler
_TRAJECTORY_HANDLERS: dict[str, Any] = {
    "tool_sequence": _traj_tool_sequence,
    "readiness_check_before_approval": _traj_readiness_check_before_approval,
    "promotion_tool_used": _traj_promotion_tool_used,
    "turn_count": _traj_turn_count,
    "tools_turn_count": _traj_turn_count,          # alias
    "readiness_check_called": _traj_readiness_check_called,
    "no_invented_prices": _traj_no_invented_prices,
    "gap_reported_honestly": _traj_gap_reported_honestly,
    "stale_warning_disclosed": _traj_stale_warning_disclosed,
    "error_handled_not_silenced": _traj_error_handled_not_silenced,
    "retry_with_note": _traj_retry_with_note,
    "no_strategy_mutation_tools": _traj_no_strategy_mutation_tools,
    "error_loop": _traj_error_loop,
}


def _run_trajectory_grader(spec: dict, transcript: Transcript) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "track")
    detail = spec.get("detail", "")
    # Suffix is everything after the first dot (e.g. "no_invented_prices").
    # grade() only dispatches here for ids starting "trajectory.", so a dot is present.
    suffix = gid.split(".", 1)[-1]
    handler = _TRAJECTORY_HANDLERS.get(suffix)
    if handler is None:
        return GraderResult(
            gid, role, "fail", detail,
            actual=f"unknown trajectory grader: {suffix!r}",
        )
    return handler(gid, role, detail, transcript)


# ---------------------------------------------------------------------------
# Verdict composition (spec §6.4)
# ---------------------------------------------------------------------------

def compose_verdict(results: list[GraderResult]) -> ComposedVerdict:
    """Compose grader results into a structured verdict (spec §6.4).

    - gate  → task_passes_gates (False if any gate fails)
    - track → track_metrics dict (grader_id → actual value) for version comparison
    - flag  → flags list — only failed flags (verdict='fail') are queued for review
    """
    gate_results = [r for r in results if r.role == "gate"]
    track_results = [r for r in results if r.role == "track"]
    flag_results = [r for r in results if r.role == "flag"]

    task_passes_gates = all(r.verdict == "pass" for r in gate_results)
    track_metrics = {r.grader_id: r.actual for r in track_results}
    flags = [r for r in flag_results if r.verdict == "fail"]

    return ComposedVerdict(
        task_passes_gates=task_passes_gates,
        gate_results=gate_results,
        track_metrics=track_metrics,
        flags=flags,
    )


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
        gid = spec.get("id", "unknown")
        role = spec.get("role", "gate")

        if "sql" in spec:
            results.append(_run_sql_grader(spec, db_path))
        elif "check" in spec:
            results.append(_run_check_grader(spec, transcript, workspace))
        elif gid.startswith("trajectory."):
            suffix = gid.split(".", 1)[-1]
            if suffix in _TRAJECTORY_HANDLERS:
                results.append(_run_trajectory_grader(spec, transcript))
            else:
                # Unknown suffix: fall back to assertion lookup
                resolved = _resolve_spec(spec, task)
                if resolved is not None and "check" in resolved:
                    results.append(_run_check_grader(resolved, transcript, workspace))
                elif resolved is not None and "sql" in resolved:
                    results.append(_run_sql_grader(resolved, db_path))
                else:
                    results.append(GraderResult(
                        grader_id=gid, role=role, verdict="fail",
                        detail=spec.get("detail", ""),
                        actual=f"unknown trajectory grader: {suffix!r}",
                    ))
        elif gid.startswith("judge."):
            results.append(GraderResult(
                grader_id=gid,
                role=role,
                verdict="skip",
                detail=spec.get("detail", "LLM judge grader (Phase 3, not yet implemented)"),
                actual="phase_3_not_implemented",
            ))
        else:
            resolved = _resolve_spec(spec, task)
            if resolved is None:
                results.append(GraderResult(
                    grader_id=gid,
                    role=role,
                    verdict="skip",
                    detail=spec.get("detail", ""),
                    actual="deferred: no assertion registered for this grader",
                ))
            elif "sql" in resolved:
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
