"""Repro tests for docs/requests/evals/review-2026-07-19-issue-34-implementation.md.

Each test asserts the INTENDED behavior. Open findings are marked strict xfail;
the fix for a finding must remove its marker.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

from evals.harness import graders, harness
from evals.harness.cli_runner import CLIRunner
from evals.harness.graders import (
    _make_trajectory_helpers,
    _run_check_grader,
    _run_sql_grader,
    _traj_no_invented_prices,
    _traj_no_strategy_mutation_tools,
    compose_verdict,
    grade,
)
from evals.harness.runner import Runner, Transcript, TranscriptEvent, TrialEnv

REPO = Path(harness._REPO_ROOT)


def open_finding(n):
    return pytest.mark.xfail(strict=True, reason=f"review finding {n} not fixed yet")
RUBRIC = "rubrics/thesis_quality_v1.yaml"
RUBRIC_DIMS = list(yaml.safe_load((REPO / "evals" / RUBRIC).read_text())["dimensions"])


def _tx(*calls):
    """calls: (tool_use_id, name, input, result_content, is_error)."""
    ev = []
    for tid, name, inp, res, err in calls:
        ev.append(TranscriptEvent("assistant", {"content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}))
        ev.append(TranscriptEvent("user", {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": res, "is_error": err}]}))
    return Transcript(events=ev)


def _with_final_text(t: Transcript, text: str) -> Transcript:
    t.events.append(TranscriptEvent("assistant", {"content": [{"type": "text", "text": text}]}))
    return t


# How Claude Code actually names an MCP tool: server "finance-hub", tool "finance.promote_to_strategy"
# -> "mcp__finance-hub__finance_promote_to_strategy" (dots sanitised to underscores).
REAL_PROMOTE = "mcp__finance-hub__finance_promote_to_strategy"


# ---------------------------------------------------------------- F1
def test_f1_tool_called_matches_real_mcp_name():
    t = _tx(("t1", REAL_PROMOTE, {}, "{}", False))
    tool_called, _, _ = _make_trajectory_helpers(t)
    assert tool_called("finance.promote_to_strategy")


def test_f1_no_strategy_mutation_gate_catches_real_mcp_name():
    t = _tx(("t1", REAL_PROMOTE, {}, "{}", False))
    r = _traj_no_strategy_mutation_tools("trajectory.no_strategy_mutation_tools", "gate", "", t)
    assert r.verdict == "fail", "safety gate passed vacuously on a real forbidden call"


# ---------------------------------------------------------------- F2
def test_f2_tool_result_attr_on_sdk_text_block_content():
    content = [{"type": "text", "text": json.dumps({"stored": 8})}]
    t = _tx(("t1", "finance.fetch_fundamentals", {}, content, False))
    spec = {"id": "c1", "role": "gate",
            "check": "tool_result('finance.fetch_fundamentals').stored == 8"}
    r = _run_check_grader(spec, t)
    assert r.verdict == "pass", r.actual


# ---------------------------------------------------------------- helpers for harness tests
class FakeRunner(Runner):
    def __init__(self, behaviours):
        self.behaviours = behaviours  # list of async callables(env) -> None
        self.n = 0

    async def run(self, prompt, env):
        i = self.n
        self.n += 1
        await self.behaviours[i](env)
        return Transcript(events=[TranscriptEvent("result", {"num_turns": 1})])


async def _noop(env):
    return None


def _write_task(tmp_path, graders_list):
    p = tmp_path / "T.yaml"
    p.write_text(yaml.safe_dump({"id": "TREV", "version": 1, "suite": "regression",
                                 "prompt": "x", "graders": graders_list}))
    return p


JUDGE_SPEC = {"id": "judge.thesis_quality", "rubric": RUBRIC, "dimensions": RUBRIC_DIMS}
OK_JUDGE = json.dumps({d: {"score": 5, "justification": "ok"} for d in RUBRIC_DIMS})


# ---------------------------------------------------------------- F3
def test_f3_judge_error_does_not_lose_transcripts(tmp_path, monkeypatch):
    calls = {"n": 0}

    def judge(prompt, model):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("CLIConnectionError (simulated)")
        return OK_JUDGE

    monkeypatch.setattr(graders, "_invoke_judge", judge)
    task = _write_task(tmp_path, [{"id": "g", "role": "gate", "check": "True"}, JUDGE_SPEC])
    results = tmp_path / "runs"
    try:
        harness.run(task, FakeRunner([_noop] * 3), k=3, results_root=results)
    except Exception:
        pass
    run_dirs = list(results.iterdir())
    assert run_dirs
    missing = [i for i in range(3) if not (run_dirs[0] / f"trial_{i}" / "transcript.jsonl").exists()]
    assert not missing, f"transcripts lost for trials {missing}"
    assert (run_dirs[0] / "meta.json").exists(), "meta.json never written"


# ---------------------------------------------------------------- F4
def test_f4_no_invented_prices_accepts_micros_grounded_amount():
    t = _tx(("t1", "finance.get_deployment_plan", {},
             {"amount_micros": 12_345_670_000, "budget": "1000"}, False))
    _with_final_text(t, "Plan buys $12,345.67 of VTI; budget $1,000.00.")
    r = _traj_no_invented_prices("trajectory.no_invented_prices", "gate", "", t)
    assert r.verdict == "pass", r.actual


# ---------------------------------------------------------------- F5
def test_f5_regrade_preserves_workspace_verdict(tmp_path):
    async def write_memo(env):
        d = Path(env.cwd) / "workspace" / "approved"
        d.mkdir(parents=True, exist_ok=True)
        (d / "memo_plan_r6_fixture.md").write_text("memo")

    task = _write_task(tmp_path, [{"id": "outcome.memo", "role": "gate",
                                   "check": "bool(workspace('approved/').glob('*plan_r6_fixture*'))"}])
    run_dir = harness.run(task, FakeRunner([write_memo]), k=1, results_root=tmp_path / "runs")
    first = json.loads((run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines()[0])
    assert first["verdict"] == "pass"
    re = harness.regrade(run_dir, task)
    assert re[0][0].verdict in ("pass", "skip"), "regrade flipped a passing workspace gate to FAIL"


# ---------------------------------------------------------------- F6
def _fake_cli(tmp_path):
    argv_file = tmp_path / "argv.json"
    script = tmp_path / "claude"
    lines = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "finance.promote_to_strategy", "input": {}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "{}", "is_error": False}]}},
        {"type": "result", "num_turns": 1},
    ]
    script.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, sys
        json.dump(sys.argv, open({str(argv_file)!r}, "w"))
        for l in json.loads({json.dumps(lines)!r}):
            print(json.dumps(l))
        """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, argv_file


def _cli_env(tmp_path):
    return TrialEnv(cwd=tmp_path, env={}, mcp_servers={}, model="m")


def test_f6_cli_transcript_readable_by_graders(tmp_path):
    script, _ = _fake_cli(tmp_path)
    t = asyncio.run(CLIRunner(str(script)).run("p", _cli_env(tmp_path)))
    tool_called, _, _ = _make_trajectory_helpers(t)
    assert tool_called("finance.promote_to_strategy"), "graders see empty transcript from CLIRunner"


def test_f6_cli_respects_setting_sources(tmp_path):
    script, argv_file = _fake_cli(tmp_path)
    asyncio.run(CLIRunner(str(script)).run("p", _cli_env(tmp_path)))
    argv = json.loads(argv_file.read_text())
    assert "--setting-sources" in argv, "CLI trial loads developer ~/.claude config"


# ---------------------------------------------------------------- F7
def test_f7_tool_result_returns_last_call():
    t = _tx(("t1", "finance.candidate_evidence", {}, "ERROR: transient", True),
            ("t2", "finance.candidate_evidence", {}, {"readiness": {"one_time": True}}, False))
    spec = {"id": "c", "role": "gate",
            "check": "tool_result('finance.candidate_evidence').readiness['one_time'] == True"}
    r = _run_check_grader(spec, t)
    assert r.verdict == "pass", r.actual


# ---------------------------------------------------------------- F8
def test_f8_judge_does_not_block_event_loop(tmp_path, monkeypatch):
    def slow_judge(prompt, model):
        time.sleep(1.0)
        return OK_JUDGE

    monkeypatch.setattr(graders, "_invoke_judge", slow_judge)
    lag = {"max": 0.0}

    async def heartbeat(env):
        for _ in range(30):
            t0 = time.monotonic()
            await asyncio.sleep(0.05)
            lag["max"] = max(lag["max"], time.monotonic() - t0 - 0.05)

    async def short(env):
        await asyncio.sleep(0.2)  # let heartbeat start, then this trial gets judged

    task = _write_task(tmp_path, [{"id": "g", "role": "gate", "check": "True"}, JUDGE_SPEC])
    harness.run(task, FakeRunner([short, heartbeat]), k=2, results_root=tmp_path / "runs")
    assert lag["max"] < 0.3, f"event loop stalled {lag['max']:.2f}s while another trial was judged"


# ---------------------------------------------------------------- F9
def test_f9_sql_gate_with_typoed_expect_key_does_not_pass(tmp_path):
    db = tmp_path / "t.db"
    sqlite3.connect(db).close()
    r = _run_sql_grader({"id": "outcome.x", "role": "gate", "sql": "SELECT 0", "expects": 99}, db)
    assert r.verdict != "pass", "typo'd gate passed vacuously"


# ---------------------------------------------------------------- F10
def test_f10_no_worktree_snapshot_or_nvim_log_tracked():
    out = subprocess.run(["git", "ls-files", ".claude/worktrees", "nvim.log"],
                         cwd=REPO, capture_output=True, text=True).stdout.split()
    assert not out, f"{len(out)} stray tracked files, e.g. {out[:3]}"


# ================================================================ cut-by-cap findings
def test_cut1_zero_gate_semantics_consistent():
    assert harness._trial_gate_pass([]) == compose_verdict([]).task_passes_gates


def test_cut2_mcp_json_uses_py3env_interpreter():
    cmd = json.loads((REPO / "runtime" / "mcp.json").read_text())["mcpServers"]["finance-hub"]["command"]
    assert "py3env" in cmd, f"command {cmd!r} resolves via PATH (not py3env)"


def test_cut3_judge_skip_rows_fall_back_to_rubric_dims():
    task = {"graders": [{"id": "g", "role": "gate", "check": "False"},
                        {"id": "judge.thesis_quality", "rubric": RUBRIC}]}
    rows = [r for r in grade(Transcript(), None, Path("/nonexistent"), task)
            if r.grader_id.startswith("judge.")]
    assert len(rows) == len(RUBRIC_DIMS), f"got {len(rows)} judge skip rows"


@pytest.mark.parametrize("golden", sorted((REPO / "evals" / "tasks").glob("*/golden/transcript.jsonl")),
                         ids=lambda p: p.parts[-3])
def test_cut4_golden_transcript_parses(golden):
    Transcript.read_jsonl(golden)


@pytest.mark.parametrize("rel,pat", [
    ("src/finance_hub/strategy/portfolio_snapshot.py", "datetime.now("),
    ("src/finance_hub/market_data/fundamentals.py", "date.today()"),
])
def test_cut5_clock_front_door(rel, pat):
    hits = [i for i, l in enumerate((REPO / rel).read_text().splitlines(), 1) if pat in l]
    assert not hits, f"{rel} bypasses factories.get_clock() at lines {hits}"
