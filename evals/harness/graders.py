"""Grader registry (spec §9 req 4, §6).

grade(transcript, db_path, workspace, task) → list[GraderResult]

Grader types dispatched from task YAML grader specs:
  sql        — run SQL against the trial DB; compare result to `expect` (==) or `expect_min` (>=)
  check      — evaluate a Python expression against the transcript + workspace
  trajectory — built-in transcript-pattern graders dispatched by ID suffix
  judge.*    — LLM-judge grader; runs only on gate-passing trials; returns per-dimension rows

Helpers available in check expressions:
  tool_result(name)                     — last tool result dict for the named tool
  tool_called(name)                     — True if the tool was called anywhere in the transcript
  tool_call_before(a, b)                — True if tool a appears before tool b in transcript
  tool_input(name, field)               — the input dict (or one field) of the last call to name
  workspace(rel)                        — path proxy for rel under the trial workspace
  transcript.tool_uses.contains(name)   — True if tool was called
  transcript.tool_results.has_error(n)  — True if any tool_result for n has is_error=true
  transcript.tool_inputs.field_nonempty(tool, field) — True if any successful call has non-empty field

Tool names are canonicalised to the registry form ("finance.<tool>"): real runner
transcripts record MCP tools as "mcp__finance-hub__finance_<tool>" (see
_canonical_tool_name). Tool-result content is decoded (SDK text blocks → joined
text → JSON when parseable) before helpers/graders see it (see _decode_tool_content).

Verdict composition (spec §6.4):
  compose_verdict(results) → ComposedVerdict
  - gate  → pass/fail (task passes iff all gate verdicts pass)
  - track → metric dict for cross-version comparison
  - flag  → human review queue (only failed flags queued)

Grader spec resolution order:
  1. If the spec has inline `sql` or `check`, use it directly.
  2. If the id starts with `trajectory.`, dispatch to the built-in handler.
  3. If the id starts with `judge.`, dispatch to the LLM-judge handler (§6.3).
  4. Otherwise strip the namespace prefix and look up in reference.assertions.
  5. If still not found: others → skip (deferred); unknown trajectory.* gates → fail,
     unknown trajectory.* track/flag → skip.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import sqlite3
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

import yaml

from evals.harness.runner import Transcript

_REPO_ROOT = Path(__file__).parent.parent.parent
_EVALS_ROOT = _REPO_ROOT / "evals"


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
# Transcript tool index — the one walker every helper/proxy/grader reads
# ---------------------------------------------------------------------------

def _canonical_tool_name(name: str) -> str:
    """Map a transcript tool name to its registry form ("finance.<tool>").

    Claude Code exposes an MCP tool as "mcp__<server>__<tool>" with the dots in the
    registry name sanitised to underscores, so the real runner records
    "mcp__finance-hub__finance_promote_to_strategy" for "finance.promote_to_strategy".
    Rule: strip "mcp__<server>__"; then, because every finance registry name is
    "finance.<snake_case>", turn only the FIRST "finance_" back into "finance."
    (later underscores belong to the tool name). Already-dotted names (hand-written
    goldens/tests) and non-MCP tools (ToolSearch, Read, ...) pass through unchanged.
    """
    if not name.startswith("mcp__"):
        return name
    _server, sep, tool = name[len("mcp__"):].partition("__")
    if not sep:
        return name
    if tool.startswith("finance_"):
        return "finance." + tool[len("finance_"):]
    return tool


def _decode_tool_content(raw: Any) -> Any:
    """Decode a tool_result's content into the value the tool returned.

    The SDK records MCP results as a list of content blocks; finance tools return
    one text block holding JSON. Text blocks are joined and json-parsed; a plain
    string is json-parsed when possible (MCP error text stays a string). Lists with
    no text blocks (e.g. ToolSearch tool_reference blocks) and dicts (hand-written
    transcripts) are returned unchanged.
    """
    if isinstance(raw, list):
        texts = [
            b.get("text", "") for b in raw
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        if not texts:
            return raw
        raw = "".join(texts)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


@dataclass
class _ToolCall:
    """One tool_use with its matched tool_result (if any)."""

    id: str
    name: str                  # canonical (registry) name
    input: dict
    content: Any = None        # decoded result content
    is_error: bool = False     # null/missing is_error → False
    has_result: bool = False


class _ToolIndex:
    """Single pass over a transcript: tool calls in order, each matched to its result.

    results keeps every tool_result in transcript order (including orphans with no
    matching tool_use) as (tool_use_id, decoded content, is_error).
    """

    def __init__(self, transcript: Transcript) -> None:
        self.calls: list[_ToolCall] = []
        self.results: list[tuple[str, Any, bool]] = []
        for event in transcript.events:
            content = event.data.get("content", [])
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if event.type == "assistant" and b.get("type") == "tool_use":
                    self.calls.append(_ToolCall(
                        id=b.get("id", ""),
                        name=_canonical_tool_name(b.get("name", "")),
                        input=b.get("input") or {},
                    ))
                elif event.type == "user" and b.get("type") == "tool_result":
                    self.results.append((
                        b.get("tool_use_id", ""),
                        _decode_tool_content(b.get("content")),
                        bool(b.get("is_error")),
                    ))
        by_id = {c.id: c for c in self.calls}
        for tuid, content, is_error in self.results:
            call = by_id.get(tuid)
            if call is not None:
                call.content, call.is_error, call.has_result = content, is_error, True

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.calls]

    def calls_to(self, name: str) -> list[_ToolCall]:
        name = _canonical_tool_name(name)
        return [c for c in self.calls if c.name == name]


# ---------------------------------------------------------------------------
# Transcript DSL helpers — used in check expressions
# ---------------------------------------------------------------------------

class _DictNamespace:
    """Wrap a dict so attribute-style access works in check expressions.

    Only the top level is wrapped; nested dicts stay plain so subscripting
    (`tool_result(x).readiness['one_time']`) keeps working.
    """

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)

    def __repr__(self) -> str:
        return f"_DictNamespace({self.__dict__!r})"


class _ToolUsesProxy:
    """transcript.tool_uses — check tool presence in assistant turns."""

    def __init__(self, index: _ToolIndex) -> None:
        self._index = index

    def contains(self, name: str) -> bool:
        return bool(self._index.calls_to(name))

    def not_contains(self, name: str) -> bool:
        return not self.contains(name)


class _ToolResultsProxy:
    """transcript.tool_results — check error/success patterns in tool results."""

    def __init__(self, index: _ToolIndex) -> None:
        self._index = index

    def has_error(self, tool_name: str) -> bool:
        """True if any tool_result for this tool has is_error=true."""
        return any(c.has_result and c.is_error for c in self._index.calls_to(tool_name))


class _ToolInputsProxy:
    """transcript.tool_inputs — inspect input fields of tool calls."""

    def __init__(self, index: _ToolIndex) -> None:
        self._index = index

    def field_nonempty(self, tool_name: str, field_name: str) -> bool:
        """True if any SUCCESSFUL call to tool_name has a non-empty value for field."""
        for call in self._index.calls_to(tool_name):
            if call.is_error:
                continue
            val = call.input.get(field_name)
            if val and str(val).strip():
                return True
        return False


class _TranscriptProxy:
    """transcript DSL object exposed in check expressions."""

    def __init__(self, index: _ToolIndex) -> None:
        self.tool_uses = _ToolUsesProxy(index)
        self.tool_results = _ToolResultsProxy(index)
        self.tool_inputs = _ToolInputsProxy(index)


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

def _find_tool_result(transcript: Transcript | _ToolIndex, tool_name: str) -> Any:
    """Return the decoded content of the LAST call to tool_name that has a result.

    A dict result is wrapped in _DictNamespace for attribute access. Returns None
    when the tool was never called (or no call has a recorded result).
    """
    index = transcript if isinstance(transcript, _ToolIndex) else _ToolIndex(transcript)
    for call in reversed(index.calls_to(tool_name)):
        if call.has_result:
            c = call.content
            return _DictNamespace(c) if isinstance(c, dict) else c
    return None


def _make_trajectory_helpers(transcript: Transcript | _ToolIndex):
    """Build the tool_called / tool_call_before / tool_input helpers."""
    index = transcript if isinstance(transcript, _ToolIndex) else _ToolIndex(transcript)
    names = index.names

    def tool_called(name: str) -> bool:
        return _canonical_tool_name(name) in names

    def tool_call_before(first: str, second: str) -> bool:
        first, second = _canonical_tool_name(first), _canonical_tool_name(second)
        try:
            first_idx = names.index(first)
        except ValueError:
            return False
        return any(name == second and i > first_idx for i, name in enumerate(names))

    def tool_input(name: str, field: str = None) -> Any:
        calls = index.calls_to(name)
        if not calls:
            return None
        inp = calls[-1].input
        return inp.get(field) if field is not None else inp

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

def _run_sql_grader(spec: dict, db_path: Path | None) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "gate")
    detail = spec.get("detail", "")
    sql = spec["sql"]

    if db_path is None:
        return GraderResult(gid, role, "skip", detail, actual="sql grader skipped: no db_path")

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
        # No expect: track/flag graders just record the actual value. A gate with no
        # expectation (e.g. a typo'd key) must not pass vacuously.
        actual = rows[0][0] if rows else None
        if role == "gate":
            return GraderResult(
                gid, role, "fail", detail,
                actual=f"gate sql grader has no 'expect' or 'expect_min' (actual={actual!r})",
            )
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

    index = _ToolIndex(transcript)

    def tool_result(tool_name: str) -> Any:
        return _find_tool_result(index, tool_name)

    tool_called, tool_call_before, tool_input = _make_trajectory_helpers(index)

    ns = {
        "__builtins__": {},
        "tool_result": tool_result,
        "tool_called": tool_called,
        "tool_call_before": tool_call_before,
        "tool_input": tool_input,
        "transcript": _TranscriptProxy(index),
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
    """Yield (canonical tool_name, input_dict, tool_use_id) for each tool_use in order."""
    for call in _ToolIndex(transcript).calls:
        yield call.name, call.input, call.id


def _iter_tool_results_data(
    transcript: Transcript,
) -> Iterator[tuple[str, Any, bool]]:
    """Yield (tool_use_id, decoded content, is_error) for each tool_result."""
    yield from _ToolIndex(transcript).results


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
    # Standalone decimal numbers: 234.56, 1234.56, 1,234.56 (not preceded by $). The
    # lookbehind also rejects a digit/comma/dot so "$12,345.67" never yields "345.67".
    for m in re.finditer(r"(?<![$\d,.])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2,}(?![\d.])", text):
        numbers.add(m.group().replace(",", ""))
    return numbers


_NUMERIC_STR_RE = re.compile(r"-?\d+(?:\.\d+)?")
_DECIMAL_TOKEN_RE = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")
_MICROS = Decimal(1_000_000)


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _is_grounded(value: Decimal | None, grounded: set[Decimal]) -> bool:
    """True if value equals a grounded amount, or one rounded to value's precision."""
    if value is None:
        return False
    if value in grounded:
        return True
    step = Decimal(1).scaleb(value.as_tuple().exponent)
    for g in grounded:
        try:
            if g.quantize(step, rounding=ROUND_HALF_UP) == value:
                return True
        except InvalidOperation:
            continue
    return False


def _grounded_amounts(content: Any, out: set[Decimal], key: str = "") -> None:
    """Collect the money/price amounts a decoded tool result grounds, into `out`.

    Conservative by design — plain JSON integers (counts, bps, ids) are NOT amounts:
      - integer (or numeric-string) value under a key ending "_micros" → value ÷ 1e6
      - string that is wholly numeric ("700", "190.5") → its value
      - decimal tokens embedded in a string ("close 185.20 on …") → their values
      - JSON float → its value
    """
    if isinstance(content, dict):
        for k, v in content.items():
            _grounded_amounts(v, out, str(k))
    elif isinstance(content, list):
        for v in content:
            _grounded_amounts(v, out, key)
    elif isinstance(content, bool) or content is None:
        return
    elif key.endswith("_micros") and isinstance(content, (int, str)):
        d = _to_decimal(content)
        if d is not None and d == d.to_integral_value():
            out.add(d / _MICROS)
    elif isinstance(content, float):
        d = _to_decimal(content)
        if d is not None:
            out.add(d)
    elif isinstance(content, str):
        if _NUMERIC_STR_RE.fullmatch(content.strip()):
            out.add(Decimal(content.strip()))
        for m in _DECIMAL_TOKEN_RE.finditer(content):
            out.add(Decimal(m.group()))


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
    must numerically equal some amount in a tool result.

    Catches the most common invented-price failure (spec §6.2): an agent writing a
    price value that has no basis in any tool result. Comparison is by Decimal value
    (so "$1,000.00" matches "1000" and "190.50" matches "190.5"); a source amount
    rounded half-up to the prose's precision also counts, so 176470588 micros grounds
    "$176.47" (see _is_grounded). Grounded amounts are
    collected conservatively (see _grounded_amounts): integer *_micros fields ÷ 1e6,
    whole-string numerics ("700", "190.5"), decimal tokens inside strings, and JSON
    floats — never arbitrary JSON integers (counts, bps, ids). The LLM judge (§6.3)
    covers qualitative grounding for the long tail.
    """
    grounded: set[Decimal] = set()
    for _, content, _ in _iter_tool_results_data(transcript):
        _grounded_amounts(content, grounded)

    final_prose = _final_text(transcript)
    prose_numbers = _extract_financial_numbers(final_prose)

    if not prose_numbers:
        return GraderResult(gid, role, "pass", detail, actual="no financial numbers in prose")

    invented = sorted(n for n in prose_numbers if not _is_grounded(_to_decimal(n), grounded))
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
    # Count failing calls per (name, serialised input) key
    fail_counts: dict[tuple[str, str], int] = {}
    for call in _ToolIndex(transcript).calls:
        if call.is_error:
            key = (call.name, json.dumps(call.input, sort_keys=True))
            fail_counts[key] = fail_counts.get(key, 0) + 1

    loops = [(k[0], count) for k, count in fail_counts.items() if count >= 2]
    if loops:
        desc = "; ".join(f"{n} failed identically {c}x" for n, c in loops)
        return GraderResult(gid, role, "fail", detail, actual=desc)
    return GraderResult(gid, role, "pass", detail, actual="no error loops detected")


def _traj_fetch_fundamentals_called_for_aapl(
    gid: str, role: str, detail: str, transcript: Transcript
) -> GraderResult:
    """Track (C1): report whether finance.fetch_fundamentals was called with ticker AAPL."""
    called = any(
        str(c.input.get("ticker", "")).upper() == "AAPL"
        for c in _ToolIndex(transcript).calls_to("finance.fetch_fundamentals")
    )
    return GraderResult(gid, role, "pass", detail, actual=called)


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
    "fetch_fundamentals_called_for_aapl": _traj_fetch_fundamentals_called_for_aapl,
}


def _unknown_trajectory_result(gid: str, role: str, detail: str, suffix: str) -> GraderResult:
    """No handler and no reference assertion for a trajectory grader.

    A gate must not pass vacuously → fail. A track/flag has nothing to measure yet
    (several capability tasks declare deferred track metrics) → skip, so it neither
    records a bogus metric nor floods the human-review flag queue.
    """
    if role == "gate":
        return GraderResult(gid, role, "fail", detail, actual=f"unknown trajectory grader: {suffix!r}")
    return GraderResult(
        gid, role, "skip", detail,
        actual=f"deferred: unknown trajectory grader {suffix!r} (no built-in handler or reference assertion)",
    )


def _run_trajectory_grader(spec: dict, transcript: Transcript) -> GraderResult:
    gid = spec["id"]
    role = spec.get("role", "track")
    detail = spec.get("detail", "")
    # Suffix is everything after the first dot (e.g. "no_invented_prices").
    # grade() only dispatches here for ids starting "trajectory.", so a dot is present.
    suffix = gid.split(".", 1)[-1]
    handler = _TRAJECTORY_HANDLERS.get(suffix)
    if handler is None:
        return _unknown_trajectory_result(gid, role, detail, suffix)
    return handler(gid, role, detail, transcript)


# ---------------------------------------------------------------------------
# LLM-judge grader (spec §6.3)
# ---------------------------------------------------------------------------

def _invoke_judge(prompt: str, judge_model: str) -> str:
    """Call the LLM judge via Agent SDK; returns the raw response text.

    Blocking. Runs the async SDK call in a fresh thread with its own event loop so
    grade() stays synchronous even when called with an event loop running in the
    current thread. harness.run calls grade() via asyncio.to_thread, so this never
    blocks the shared trial loop.
    """
    async def _call() -> str:
        from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
        options = ClaudeAgentOptions(
            model=judge_model,
            max_turns=1,
            setting_sources=[],
        )
        text_parts: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
        return "".join(text_parts)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _call())
        return future.result()


def _load_rubric(rubric_relpath: str) -> dict:
    """Load a versioned rubric YAML; path is relative to evals/."""
    rubric_path = _EVALS_ROOT / rubric_relpath
    return yaml.safe_load(rubric_path.read_text())


def _collect_judge_context(workspace: Path | None, db_path: Path | None) -> dict:
    """Collect note text and source data from workspace + DB for the judge prompt."""
    notes: dict[str, str] = {}
    if workspace:
        research_dir = workspace / "research"
        if research_dir.exists():
            for md_file in research_dir.rglob("*.md"):
                rel = md_file.relative_to(workspace)
                notes[str(rel)] = md_file.read_text()

    sources: list[dict] = []
    if db_path and db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT rs.id, rs.url, rs.title FROM fin_research_sources rs "
                    "JOIN fin_research_source_links rl ON rs.id = rl.source_id "
                    "WHERE rl.status = 'active'"
                ).fetchall()
                sources = [{"id": r[0], "url": r[1], "title": r[2]} for r in rows]
        except Exception:
            pass

    return {"notes": notes, "sources": sources}


def _build_judge_prompt(rubric: dict, context: dict, spec: dict) -> str:
    """Build the judge prompt from rubric, workspace context, and grader spec."""
    lines: list[str] = []

    instructions = rubric.get("judge_instructions", "").strip()
    if instructions:
        lines.append(instructions)
        lines.append("")

    lines.append("## Thesis Note(s)")
    if context["notes"]:
        for path, text in context["notes"].items():
            lines.append(f"\n### {path}")
            lines.append(text)
    else:
        lines.append("(no note files found in workspace/research/)")

    lines.append("\n## Registered Sources")
    if context["sources"]:
        for src in context["sources"]:
            url_str = f" — {src['url']}" if src.get("url") else ""
            title_str = src.get("title") or "(no title)"
            lines.append(f"- ID {src['id']}: {title_str}{url_str}")
    else:
        lines.append("(no sources registered)")

    coverage_key_facts = spec.get("coverage_key_facts", [])
    if coverage_key_facts:
        lines.append("\n## Coverage Key Facts Required")
        for i, fact in enumerate(coverage_key_facts, 1):
            lines.append(f"{i}. {fact}")

    dimensions = spec.get("dimensions", list(rubric.get("dimensions", {}).keys()))
    lines.append("\n## Scoring Instructions")
    for dim in dimensions:
        dim_rubric = rubric.get("dimensions", {}).get(dim, {})
        desc = dim_rubric.get("description", "").strip()
        flag_below = dim_rubric.get("flag_below", 3)
        lines.append(f"\n**{dim}** (score 1–5; flag_below={flag_below}): {desc}")
        scoring = dim_rubric.get("scoring", {})
        for score_val in sorted(scoring.keys(), reverse=True):
            lines.append(f"  {score_val}: {scoring[score_val]}")

    dim_list = json.dumps({d: {"score": "1-5", "justification": "..."} for d in dimensions}, indent=2)
    lines.append(f"""
## Required Output Format

Respond with ONLY a JSON object (no prose, no code fences):
{dim_list}
""")
    return "\n".join(lines)


def _parse_judge_response(
    response: str,
    rubric: dict,
    spec: dict,
) -> list[GraderResult]:
    """Parse the judge's JSON response into per-dimension GraderResult rows.

    Always returns one row per dimension. On parse error, returns fail rows with
    an error detail so the human reviewer can investigate.
    """
    base_id = spec["id"]
    judge_version = spec.get("judge_model", rubric.get("judge_model", "unknown"))
    rubric_id = rubric.get("id", "unknown")
    rubric_version = str(spec.get("rubric_version", rubric.get("version", "unknown")))
    dimensions = spec.get("dimensions", list(rubric.get("dimensions", {}).keys()))

    def _meta(dim: str, **extra: Any) -> dict:
        return {
            "dimension": dim,
            "rubric_id": rubric_id,
            "rubric_version": rubric_version,
            "judge_version": judge_version,
            **extra,
        }

    try:
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.MULTILINE)
        parsed = json.loads(cleaned)
    except Exception as exc:
        # Return fail rows for all dimensions on parse error
        return [
            GraderResult(
                grader_id=f"{base_id}.{dim}",
                role="flag",
                verdict="fail",
                detail=f"judge response parse error: {exc}",
                actual=_meta(dim, parse_error=str(exc)),
            )
            for dim in dimensions
        ]

    results = []
    for dim in dimensions:
        dim_rubric = rubric.get("dimensions", {}).get(dim, {})
        flag_below = dim_rubric.get("flag_below", 3)
        dim_data = parsed.get(dim, {})

        score = dim_data.get("score")
        justification = dim_data.get("justification", "")

        if score is None:
            verdict = "fail"
            detail = f"dimension '{dim}' missing from judge response"
        else:
            try:
                score = int(score)
                verdict = "pass" if score >= flag_below else "fail"
                detail = str(justification)
            except (TypeError, ValueError):
                verdict = "fail"
                detail = f"invalid score {score!r} for dimension '{dim}'"
                score = None

        results.append(GraderResult(
            grader_id=f"{base_id}.{dim}",
            role="flag",
            verdict=verdict,
            detail=detail,
            actual=_meta(dim, score=score),
        ))

    return results


def _run_judge_grader(
    spec: dict,
    transcript: Transcript,
    workspace: Path | None,
    db_path: Path | None,
) -> list[GraderResult]:
    """Run the LLM-judge grader; return per-dimension GraderResult rows (spec §6.3)."""
    rubric_relpath = spec.get("rubric", "")
    dimensions = spec.get("dimensions", [])

    try:
        rubric = _load_rubric(rubric_relpath)
    except Exception as exc:
        return [
            GraderResult(
                grader_id=f"{spec['id']}.{dim}",
                role="flag",
                verdict="fail",
                detail=f"rubric load error: {exc}",
                actual={"dimension": dim, "rubric_load_error": str(exc)},
            )
            for dim in dimensions
        ]

    context = _collect_judge_context(workspace, db_path)
    prompt = _build_judge_prompt(rubric, context, spec)
    judge_model = spec.get("judge_model", rubric.get("judge_model", "claude-sonnet-5"))

    try:
        response = _invoke_judge(prompt, judge_model)
    except Exception as exc:
        # A judge failure (e.g. CLIConnectionError) must not escape grade() and
        # take the trial's deterministic verdicts down with it. Same shape as the
        # parse-error rows: one failed flag per dimension for human review.
        rubric_dims = list(rubric.get("dimensions", {}).keys())
        return [
            GraderResult(
                grader_id=f"{spec['id']}.{dim}",
                role="flag",
                verdict="fail",
                detail=f"judge invocation error: {type(exc).__name__}: {exc}",
                actual={
                    "dimension": dim,
                    "rubric_id": rubric.get("id", "unknown"),
                    "judge_version": judge_model,
                    "judge_error": f"{type(exc).__name__}: {exc}",
                },
            )
            for dim in spec.get("dimensions", rubric_dims)
        ]
    return _parse_judge_response(response, rubric, spec)


# ---------------------------------------------------------------------------
# Verdict composition (spec §6.4)
# ---------------------------------------------------------------------------

def gates_pass(results: list[GraderResult]) -> bool:
    """Single source of truth for "this trial passes its gates" (spec §6.4).

    True iff at least one gate verdict exists and every gate verdict is 'pass'.
    A trial with no gate rows does NOT pass: an all-track/flag task has no outcome
    to pass on, and pass^k must not be vacuously true. Used by grade() (judge
    gating), compose_verdict(), and harness pass^k / pass@k.
    """
    gate = [r for r in results if r.role == "gate"]
    return bool(gate) and all(r.verdict == "pass" for r in gate)


def compose_verdict(results: list[GraderResult]) -> ComposedVerdict:
    """Compose grader results into a structured verdict (spec §6.4).

    - gate  → task_passes_gates via gates_pass() (False if any gate fails or none exist)
    - track → track_metrics dict (grader_id → actual value) for version comparison
    - flag  → flags list — only failed flags (verdict='fail') are queued for review
    """
    gate_results = [r for r in results if r.role == "gate"]
    track_results = [r for r in results if r.role == "track"]
    flag_results = [r for r in results if r.role == "flag"]

    task_passes_gates = gates_pass(results)
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

def _run_one_grader(
    spec: dict,
    transcript: Transcript,
    db_path: Path | None,
    workspace: Path | None,
    task: dict,
) -> GraderResult:
    """Dispatch a single non-judge grader spec and return one GraderResult."""
    gid = spec.get("id", "unknown")
    role = spec.get("role", "gate")

    if "sql" in spec:
        return _run_sql_grader(spec, db_path)
    if "check" in spec:
        return _run_check_grader(spec, transcript, workspace)
    if gid.startswith("trajectory."):
        suffix = gid.split(".", 1)[-1]
        if suffix in _TRAJECTORY_HANDLERS:
            return _run_trajectory_grader(spec, transcript)
        resolved = _resolve_spec(spec, task)
        if resolved is not None and "check" in resolved:
            return _run_check_grader(resolved, transcript, workspace)
        if resolved is not None and "sql" in resolved:
            return _run_sql_grader(resolved, db_path)
        return _unknown_trajectory_result(gid, role, spec.get("detail", ""), suffix)

    resolved = _resolve_spec(spec, task)
    if resolved is None:
        return GraderResult(
            grader_id=gid,
            role=role,
            verdict="skip",
            detail=spec.get("detail", ""),
            actual="deferred: no assertion registered for this grader",
        )
    if "sql" in resolved:
        return _run_sql_grader(resolved, db_path)
    if "check" in resolved:
        return _run_check_grader(resolved, transcript, workspace)
    return GraderResult(
        grader_id=resolved.get("id", "unknown"),
        role=resolved.get("role", "gate"),
        verdict="fail",
        detail=resolved.get("detail", ""),
        actual="unknown grader type: no 'sql' or 'check' field",
    )


def _judge_skip_dimensions(spec: dict) -> list[str]:
    """Dimensions for a judge spec's skip rows: the spec's own, else the rubric's.

    Mirrors the run path's fallback so a rubric-only judge task still emits one skip
    row per dimension when gates fail. A rubric that cannot be loaded yields none.
    """
    if "dimensions" in spec:
        return list(spec["dimensions"])
    try:
        return list(_load_rubric(spec.get("rubric", "")).get("dimensions", {}).keys())
    except Exception:
        return []


def grade(
    transcript: Transcript,
    db_path: Path | None,
    workspace: Path,
    task: dict,
) -> list[GraderResult]:
    """Apply all graders for a task and return verdicts (spec §9 req 4).

    Processing order (spec §6.3):
      1. Run all non-judge graders first (deterministic gates, trajectories, etc.).
      2. Check gates_pass() (≥1 gate row, all 'pass').
      3. If gates pass: run each judge.* grader, extending results with per-dimension rows.
         If gates fail: emit skip rows for each judge.* grader's declared dimensions.
    """
    results: list[GraderResult] = []
    judge_specs: list[dict] = []

    for spec in task.get("graders", []):
        gid = spec.get("id", "unknown")
        if gid.startswith("judge."):
            judge_specs.append(spec)
        else:
            results.append(_run_one_grader(spec, transcript, db_path, workspace, task))

    if not judge_specs:
        return results

    trial_passes_gates = gates_pass(results)

    for spec in judge_specs:
        if trial_passes_gates:
            results.extend(_run_judge_grader(spec, transcript, workspace, db_path))
        else:
            for dim in _judge_skip_dimensions(spec):
                results.append(GraderResult(
                    grader_id=f"{spec['id']}.{dim}",
                    role="flag",
                    verdict="skip",
                    detail=spec.get("detail", ""),
                    actual="skipped: gate graders did not all pass",
                ))

    return results
