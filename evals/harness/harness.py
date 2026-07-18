"""Harness MVP — R1 end-to-end (spec §9, Phase 1).

Orchestrates: task validation → fixture materialisation → runtime surface
materialisation → prompt-hash computation → trial run → transcript
persistence → grading → run-dir layout (meta.json, transcript.jsonl,
verdicts.jsonl) → minimal report.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from evals.harness.graders import GraderResult, grade
from evals.harness.runner import Runner, Transcript, TrialEnv

_REPO_ROOT = Path(__file__).parent.parent.parent
_MATERIALIZATION_LIST = _REPO_ROOT / "evals" / "materialization_list.txt"
_DEFAULT_RESULTS_ROOT = _REPO_ROOT / "evals" / "results" / "runs"

_FIXTURE_BUILDERS: dict[str, str] = {
    "fidelity_sample_csv":                      "evals.fixtures.build_fidelity_sample_csv",
    "dividend_growth_empty":                     "evals.fixtures.build_dividend_growth_empty",
    "instrument_candidate_aapl":                 "evals.fixtures.build_instrument_candidate_aapl",
    "approved_candidates_ready_for_promotion":   "evals.fixtures.build_approved_candidates_ready_for_promotion",
    "dca_ready_deployment":                      "evals.fixtures.build_dca_ready_deployment",
    "proposed_plan_ready_for_approval":          "evals.fixtures.build_proposed_plan_ready_for_approval",
    "chain_quickstart":                          "evals.fixtures.build_chain_quickstart",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_materialization_list() -> list[str]:
    lines = []
    for raw in _MATERIALIZATION_LIST.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _materialize_runtime_surface(trial_dir: Path) -> None:
    """Copy runtime surface files into trial_dir per the materialization list."""
    for rel in _parse_materialization_list():
        src = _REPO_ROOT / rel
        dst = trial_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def compute_prompt_hash(trial_dir: Path) -> str:
    """SHA-256 over materialised runtime surface files (spec §8.3).

    Computed over exactly the files the materialisation list names, in order.
    Scaffolding edits (root CLAUDE.md, docs/) never change this hash.
    """
    entries = _parse_materialization_list()
    h = hashlib.sha256()
    for rel in entries:
        target = trial_dir / rel
        if target.exists():
            h.update(rel.encode())
            h.update(b"\n")
            h.update(target.read_bytes())
            h.update(b"\n")
    return h.hexdigest()


def _validate_task(task: dict) -> None:
    """Raise ValueError if the task spec is missing required fields."""
    fixture = task.get("fixture")
    now = task.get("now")
    if fixture and not now:
        raise ValueError(
            f"Task {task.get('id', '?')!r} has fixture={fixture!r} but no 'now'. "
            "Frozen-fixture tasks must declare a 'now' timestamp (spec §5.1)."
        )


def _build_fixture(fixture_name: str, trial_dir: Path) -> dict[str, str]:
    if fixture_name not in _FIXTURE_BUILDERS:
        raise ValueError(f"unknown fixture: {fixture_name!r}")
    mod = importlib.import_module(_FIXTURE_BUILDERS[fixture_name])
    return mod.build(trial_dir)


def _make_trial_env(
    task: dict,
    trial_dir: Path,
    fixture_env: dict[str, str],
    model: str,
    max_turns: int,
    mcp_config_dir: Path,
) -> TrialEnv:
    """Build the TrialEnv for one trial run."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env.update(fixture_env)

    now_str: str | None = task.get("now")
    if now_str:
        env["FINANCE_HUB_NOW"] = now_str
    else:
        env.pop("FINANCE_HUB_NOW", None)

    mcp_config_path = mcp_config_dir / "runtime" / "mcp.json"
    with open(mcp_config_path) as f:
        mcp_raw = json.load(f)

    # Inject fixture env (+ frozen clock) into each MCP server's env so the
    # finance-mcp subprocess points at the trial DB, not the live repo DB.
    mcp_servers: dict[str, Any] = {}
    for srv_name, srv_cfg in mcp_raw.get("mcpServers", {}).items():
        srv = dict(srv_cfg)
        srv_env = dict(srv.get("env", {}))
        srv_env.update(fixture_env)
        if now_str:
            srv_env["FINANCE_HUB_NOW"] = now_str
        srv["env"] = srv_env
        mcp_servers[srv_name] = srv

    return TrialEnv(
        cwd=trial_dir,
        env=env,
        mcp_servers=mcp_servers,
        model=model,
        max_turns=max_turns,
        setting_sources=["project"],
    )


def _write_verdicts_jsonl(path: Path, verdicts: list[GraderResult]) -> None:
    path.write_text(
        "\n".join(json.dumps(v.to_dict()) for v in verdicts) + "\n"
        if verdicts
        else ""
    )


def _emit_report(meta: dict, verdicts: list[GraderResult]) -> None:
    gate_verdicts = [v for v in verdicts if v.role == "gate"]
    passed = sum(1 for v in gate_verdicts if v.verdict == "pass")
    total = len(gate_verdicts)
    overall = "PASS" if passed == total else "FAIL"

    print(f"\n{'='*60}")
    print(f"Run: {meta['run_id']}")
    print(f"Task: {meta['task_id']} v{meta['task_version']}")
    print(f"Model: {meta['model']}  prompt_hash: {meta['prompt_hash'][:12]}…")
    print(f"{'='*60}")
    for v in verdicts:
        mark = "✓" if v.verdict == "pass" else "✗"
        print(f"  {mark} [{v.role:5s}] {v.grader_id:<38} {v.verdict.upper()}")
        if v.verdict == "fail" and v.actual is not None:
            print(f"         actual={v.actual!r}")
    print(f"{'='*60}")
    print(f"Overall: {overall} ({passed}/{total} gate verdicts passed)")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    task_path: Path,
    runner: Runner,
    *,
    model: str = "claude-sonnet-5",
    max_turns: int = 20,
    results_root: Path | None = None,
) -> Path:
    """Run one task end-to-end and return the run dir path.

    Steps:
      1. Parse + validate task YAML.
      2. Create ephemeral trial dir; materialise fixture + runtime surface.
      3. Compute prompt hash.
      4. Run the trial via the runner seam.
      5. Grade the transcript against the trial DB.
      6. Write run dir: meta.json, transcript.jsonl, verdicts.jsonl.
      7. Emit minimal report.
      8. Clean up trial dir.
    """
    task = yaml.safe_load(task_path.read_text())
    _validate_task(task)

    task_id: str = task["id"]
    task_version: str = str(task.get("version", "1"))
    now_ts = datetime.now(timezone.utc)
    run_id = f"{task_id}_{now_ts.strftime('%Y%m%d_%H%M%S')}"

    out_root = results_root or _DEFAULT_RESULTS_ROOT
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at = now_ts.isoformat()

    with tempfile.TemporaryDirectory(prefix=f"trial_{task_id}_") as _tmp:
        trial_dir = Path(_tmp)

        fixture_env = _build_fixture(task["fixture"], trial_dir)
        _materialize_runtime_surface(trial_dir)
        prompt_hash = compute_prompt_hash(trial_dir)

        trial_env = _make_trial_env(
            task, trial_dir, fixture_env, model, max_turns, trial_dir
        )
        transcript: Transcript = asyncio.run(runner.run(task["prompt"], trial_env))
        finished_at = datetime.now(timezone.utc).isoformat()

        transcript.write_jsonl(run_dir / "transcript.jsonl")

        db_path = Path(fixture_env["FINANCE_HUB_DB"])
        workspace = Path(fixture_env["FINANCE_HUB_WORKSPACE"])
        verdicts = grade(transcript, db_path, workspace, task)
        _write_verdicts_jsonl(run_dir / "verdicts.jsonl", verdicts)

    meta = {
        "run_id": run_id,
        "task_id": task_id,
        "task_version": task_version,
        "model": model,
        "prompt_hash": prompt_hash,
        "fixture": task.get("fixture", ""),
        "now": task.get("now"),
        "started_at": started_at,
        "finished_at": finished_at,
        "num_turns": transcript.num_turns,
        "total_cost_usd": transcript.total_cost_usd,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    _emit_report(meta, verdicts)
    return run_dir
