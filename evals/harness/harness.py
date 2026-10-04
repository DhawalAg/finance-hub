"""Harness — k-trial orchestrator with re-grading and per-run report (spec §8, §9).

Orchestrates: task validation → fixture materialisation (sequential, k copies) →
runtime surface materialisation → prompt-hash computation → k concurrent trial runs →
grading → run-dir layout (meta.json, trial_N/transcript.jsonl, trial_N/verdicts.jsonl)
→ per-run report.

Re-grading (spec §9 req 5): regrade() re-runs graders against stored transcripts
and the persisted trial_N/workspace/ snapshot without re-running trials; appends new
rows to trial_N/verdicts.jsonl.

Failure isolation: each trial persists its transcript and workspace before grading,
and trials are gathered with return_exceptions=True — a trial that raises (runner or
grader) is recorded in meta.json as {"error": ...} with gate_pass=False, and never
cancels its siblings or prevents meta.json from being written.
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

from evals.harness.graders import GraderResult, gates_pass, grade
from evals.harness.runner import Runner, Transcript, TrialEnv

_REPO_ROOT = Path(__file__).parent.parent.parent
_MATERIALIZATION_LIST = _REPO_ROOT / "evals" / "materialization_list.txt"
_DEFAULT_RESULTS_ROOT = _REPO_ROOT / "evals" / "results" / "runs"

# Version recorded in every meta.json so runs are self-describing across harness changes.
_HARNESS_VERSION = "2"

# Number of consecutive 100% pass^k regression runs that signals saturation (spec §7).
_SATURATION_THRESHOLD = 5

_FIXTURE_BUILDERS: dict[str, str] = {
    "fidelity_sample_csv":                        "evals.fixtures.build_fidelity_sample_csv",
    "dividend_growth_empty":                       "evals.fixtures.build_dividend_growth_empty",
    "instrument_candidate_aapl":                   "evals.fixtures.build_instrument_candidate_aapl",
    "approved_candidates_ready_for_promotion":     "evals.fixtures.build_approved_candidates_ready_for_promotion",
    "dca_ready_deployment":                        "evals.fixtures.build_dca_ready_deployment",
    "proposed_plan_ready_for_approval":            "evals.fixtures.build_proposed_plan_ready_for_approval",
    "chain_quickstart":                            "evals.fixtures.build_chain_quickstart",
    # R8 — refusal-to-invent: active strategy + snapshot but no price bars
    "plan_ready_no_price_data":                    "evals.fixtures.build_plan_ready_no_price_data",
    # R9 — degradation honesty: active strategy + stale snapshot + current prices
    "stale_portfolio_snapshot":                    "evals.fixtures.build_stale_portfolio_snapshot",
    # R10 — gate respect: pre-generated plan with UNKNOWN_SLEEVE_EXPOSURE block
    "plan_with_block_warning":                     "evals.fixtures.build_plan_with_block_warning",
    # R11 — validation handling: MSFT candidate pending review (no conviction note yet)
    "theme_with_candidate_msft":                   "evals.fixtures.build_theme_with_candidate_msft",
    # R12 — scope discipline: active strategy; research must not mutate strategy state
    "active_strategy_with_research_candidates":    "evals.fixtures.build_active_strategy_with_research_candidates",
    # C1/C2/C3/C7 — capability one-time-buy + market-data tasks
    "fetch_fundamentals_fixture":                  "evals.fixtures.build_fetch_fundamentals_fixture",
    "fundamentals_eligibility":                    "evals.fixtures.build_fundamentals_eligibility",
    "one_time_ready_deployment":                   "evals.fixtures.build_one_time_ready_deployment",
    "dca_ready_no_fundamentals":                   "evals.fixtures.build_dca_ready_no_fundamentals",
    # C4/C5/C6/C8 — capability research/chain/skill tasks
    "multi_instrument_theme_brief":                "evals.fixtures.build_multi_instrument_theme_brief",
    "stale_source_workflow":                       "evals.fixtures.build_stale_source_workflow",
    "new_theme_chain":                             "evals.fixtures.build_new_theme_chain",
    "skill_workflow_stub":                         "evals.fixtures.build_skill_workflow_stub",
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


def _get_fixture_version(fixture_name: str) -> str:
    """Return the VERSION constant from the fixture builder module (defaults to '1')."""
    if fixture_name not in _FIXTURE_BUILDERS:
        return "1"
    mod = importlib.import_module(_FIXTURE_BUILDERS[fixture_name])
    return str(getattr(mod, "VERSION", "1"))


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


def _trial_gate_pass(verdicts: list[GraderResult]) -> bool:
    """True iff this trial passes its gates — delegates to graders.gates_pass."""
    return gates_pass(verdicts)


def _compute_pass_k(all_trial_verdicts: list[list[GraderResult]]) -> bool:
    """pass^k: every trial passes all its gate graders (spec §8.1)."""
    return all(_trial_gate_pass(vs) for vs in all_trial_verdicts)


def _compute_pass_at_k(all_trial_verdicts: list[list[GraderResult]]) -> bool:
    """pass@k: at least one trial passes all its gate graders (spec §8.1)."""
    return any(_trial_gate_pass(vs) for vs in all_trial_verdicts)


def _write_verdicts_jsonl(path: Path, verdicts: list[GraderResult]) -> None:
    path.write_text(
        "\n".join(json.dumps(v.to_dict()) for v in verdicts) + "\n"
        if verdicts
        else ""
    )


def _append_verdicts_jsonl(path: Path, verdicts: list[GraderResult]) -> None:
    """Append new verdict rows to an existing verdicts.jsonl (re-grade pass)."""
    if not verdicts:
        return
    with open(path, "a") as f:
        for v in verdicts:
            f.write(json.dumps(v.to_dict()) + "\n")


def _find_prior_run(run_dir: Path, task_id: str) -> Path | None:
    """Return the most recent prior run dir for task_id in the same results dir."""
    results_dir = run_dir.parent
    if not results_dir.exists():
        return None
    candidates = sorted(
        [
            d for d in results_dir.iterdir()
            if d.is_dir()
            and d.name.startswith(f"{task_id}_")
            and d.name != run_dir.name
            and (d / "meta.json").exists()
        ],
        key=lambda d: d.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_track_metrics(run_dir: Path, k: int) -> dict[str, list[Any]]:
    """Collect track-role verdict actuals across all trials in a run dir."""
    result: dict[str, list[Any]] = {}
    for i in range(k):
        verdicts_path = run_dir / f"trial_{i}" / "verdicts.jsonl"
        if not verdicts_path.exists():
            continue
        for line in verdicts_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("role") == "track" and d.get("actual") is not None:
                result.setdefault(d["grader_id"], []).append(d["actual"])
    return result


def _emit_report(
    meta: dict,
    all_trial_verdicts: list[list[GraderResult]],
    run_dir: Path,
) -> None:
    """Emit the per-run console report (spec §8.2)."""
    k = meta.get("k", 1)
    suite = meta.get("suite", "regression")
    pass_k = meta.get("pass_k", False)
    pass_at_k = meta.get("pass_at_k", False)

    prior_dir = _find_prior_run(run_dir, meta["task_id"])
    prior_track: dict[str, list[Any]] = {}
    if prior_dir:
        prior_meta = json.loads((prior_dir / "meta.json").read_text())
        prior_track = _read_track_metrics(prior_dir, prior_meta.get("k", 1))

    print(f"\n{'='*64}")
    print(f"Run:   {meta['run_id']}  Suite: {suite}")
    print(f"Task:  {meta['task_id']} v{meta['task_version']}")
    print(f"Model: {meta['model']}  hash: {meta['prompt_hash'][:12]}…")
    print(f"{'='*64}")

    trial_meta = meta.get("trials", [])
    for i, verdicts in enumerate(all_trial_verdicts):
        transcript_link = str(run_dir / f"trial_{i}" / "transcript.jsonl")
        print(f"\nTrial {i}  [{transcript_link}]")
        error = trial_meta[i].get("error") if i < len(trial_meta) else None
        if error:
            print(f"  ✗ ERROR  {error}")
        for v in verdicts:
            mark = "✓" if v.verdict == "pass" else ("~" if v.verdict == "skip" else "✗")
            print(f"  {mark} [{v.role:5s}] {v.grader_id:<42} {v.verdict.upper()}")
            if v.verdict == "fail" and v.actual is not None:
                print(f"         actual={v.actual!r}")
            if v.role == "track" and v.actual is not None:
                prior_vals = prior_track.get(v.grader_id, [])
                if prior_vals and isinstance(v.actual, (int, float)):
                    prior_avg = sum(prior_vals) / len(prior_vals)
                    delta = v.actual - prior_avg
                    sign = "+" if delta >= 0 else ""
                    print(f"         track={v.actual}  Δ={sign}{delta:.2f} vs prior")
                else:
                    print(f"         track={v.actual}  (no prior)")

    print(f"\n{'='*64}")
    policy_label = "pass^k" if suite == "regression" else "pass@k"
    overall = pass_k if suite == "regression" else pass_at_k
    overall_str = "PASS" if overall else "FAIL"
    gate_passing = sum(1 for vs in all_trial_verdicts if _trial_gate_pass(vs))
    print(f"pass^{k}: {'PASS' if pass_k else 'FAIL'}  |  pass@{k}: {'PASS' if pass_at_k else 'FAIL'}")
    print(f"Gate:  {gate_passing}/{k} trials passing  |  Policy: {policy_label} → {overall_str}")
    if prior_dir:
        print(f"Prior: {prior_dir.name}")
    print(f"{'='*64}\n")


# ---------------------------------------------------------------------------
# Async trial execution
# ---------------------------------------------------------------------------

async def _run_one_trial_async(
    trial_idx: int,
    task: dict,
    trial_dir: Path,
    fixture_env: dict[str, str],
    runner: Runner,
    model: str,
    max_turns: int,
    run_dir: Path,
    graded_at: str,
) -> tuple[Transcript, list[GraderResult]]:
    """Run one trial: make env → run → persist transcript + workspace → grade → persist verdicts.

    The transcript and a copy of the workspace land in trial_N/ BEFORE grading, so a
    grading exception never loses the (expensive) agent run, and regrade() can later
    evaluate workspace checks against trial_N/workspace/ (the live workspace is a
    tmpdir deleted at the end of run()). Workspaces hold only small text artefacts
    (notes, memos), so the copy is cheap.

    grade() is blocking (sqlite, file IO, and the LLM judge's round-trip), so it runs
    in a worker thread to keep sibling trials' runner coroutines progressing.
    """
    trial_env = _make_trial_env(task, trial_dir, fixture_env, model, max_turns, trial_dir)
    transcript = await runner.run(task["prompt"], trial_env)

    db_path_str = fixture_env.get("FINANCE_HUB_DB", "")
    db_path = Path(db_path_str) if db_path_str else None
    workspace_str = fixture_env.get("FINANCE_HUB_WORKSPACE", str(trial_dir / "workspace"))
    workspace = Path(workspace_str)

    out_dir = run_dir / f"trial_{trial_idx}"
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript.write_jsonl(out_dir / "transcript.jsonl")
    if workspace.is_dir():
        shutil.copytree(workspace, out_dir / "workspace", dirs_exist_ok=True)

    verdicts = await asyncio.to_thread(grade, transcript, db_path, workspace, task)
    for v in verdicts:
        v.graded_at = graded_at

    _write_verdicts_jsonl(out_dir / "verdicts.jsonl", verdicts)

    return transcript, verdicts


async def _gather_trials(
    task: dict,
    trial_dirs: list[Path],
    fixture_envs: list[dict[str, str]],
    runner: Runner,
    model: str,
    max_turns: int,
    run_dir: Path,
    graded_at: str,
) -> list[tuple[Transcript, list[GraderResult]] | BaseException]:
    """Run all trials concurrently; a failed trial yields its exception in place."""
    coros = [
        _run_one_trial_async(
            i, task, trial_dir, fixture_env,
            runner, model, max_turns, run_dir, graded_at,
        )
        for i, (trial_dir, fixture_env) in enumerate(zip(trial_dirs, fixture_envs))
    ]
    return list(await asyncio.gather(*coros, return_exceptions=True))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    task_path: Path,
    runner: Runner,
    *,
    k: int = 3,
    model: str = "claude-sonnet-5",
    max_turns: int = 20,
    results_root: Path | None = None,
) -> Path:
    """Run k concurrent trials for a task and return the run dir path (spec §9 req 3).

    Steps:
      1. Parse + validate task YAML.
      2. Build k fixture copies sequentially (fixture builder has global state).
      3. Materialise runtime surface into each trial dir.
      4. Compute prompt hash from first trial dir (same for all).
      5. Run k trials concurrently via the runner seam.
      6. Grade each trial while its fixture DB is still live.
      7. Persist run dir: meta.json, trial_N/transcript.jsonl, trial_N/verdicts.jsonl.
      8. Emit per-run report.
      9. Clean up all trial dirs.
    """
    task = yaml.safe_load(task_path.read_text())
    _validate_task(task)

    task_id: str = task["id"]
    task_version: str = str(task.get("version", "1"))
    suite: str = task.get("suite", "regression")
    now_ts = datetime.now(timezone.utc)
    run_id = f"{task_id}_{now_ts.strftime('%Y%m%d_%H%M%S')}"

    out_root = results_root or _DEFAULT_RESULTS_ROOT
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at = now_ts.isoformat()

    # Build k fixtures sequentially — fixture builder modifies connection.DB_PATH globally.
    trial_tmpdirs: list[tempfile.TemporaryDirectory] = []
    trial_dirs: list[Path] = []
    trial_fixture_envs: list[dict[str, str]] = []

    try:
        for i in range(k):
            tmpdir = tempfile.TemporaryDirectory(prefix=f"trial_{task_id}_{i}_")
            trial_tmpdirs.append(tmpdir)
            td = Path(tmpdir.name)
            trial_dirs.append(td)

            if task.get("fixture"):
                fixture_env = _build_fixture(task["fixture"], td)
            else:
                (td / "workspace").mkdir(exist_ok=True)
                fixture_env = {}
            trial_fixture_envs.append(fixture_env)

            _materialize_runtime_surface(td)

        # Prompt hash is the same for all trials (identical runtime surface).
        prompt_hash = compute_prompt_hash(trial_dirs[0])
        graded_at = datetime.now(timezone.utc).isoformat()

        # Run k trials concurrently (spec §9 req 3).
        trial_outcomes = asyncio.run(
            _gather_trials(
                task, trial_dirs, trial_fixture_envs,
                runner, model, max_turns, run_dir, graded_at,
            )
        )
    finally:
        for tmpdir in trial_tmpdirs:
            tmpdir.cleanup()

    finished_at = datetime.now(timezone.utc).isoformat()

    # A trial that raised has no verdicts (→ gate_pass False) and an error entry in meta.
    trial_entries: list[dict[str, Any]] = []
    all_trial_verdicts: list[list[GraderResult]] = []
    for i, outcome in enumerate(trial_outcomes):
        if isinstance(outcome, BaseException):
            verdicts: list[GraderResult] = []
            entry: dict[str, Any] = {
                "trial_idx": i,
                "num_turns": None,
                "total_cost_usd": None,
                "gate_pass": False,
                "error": f"{type(outcome).__name__}: {outcome}",
            }
        else:
            transcript, verdicts = outcome
            entry = {
                "trial_idx": i,
                "num_turns": transcript.num_turns,
                "total_cost_usd": transcript.total_cost_usd,
                "gate_pass": _trial_gate_pass(verdicts),
            }
        all_trial_verdicts.append(verdicts)
        trial_entries.append(entry)
    pass_k_result = _compute_pass_k(all_trial_verdicts)
    pass_at_k_result = _compute_pass_at_k(all_trial_verdicts)

    fixture_name = task.get("fixture", "")
    meta = {
        "run_id": run_id,
        "task_id": task_id,
        "task_version": task_version,
        "suite": suite,
        "model": model,
        "prompt_hash": prompt_hash,
        "fixture": fixture_name,
        "fixture_version": _get_fixture_version(fixture_name) if fixture_name else "n/a",
        "harness_version": _HARNESS_VERSION,
        "now": task.get("now"),
        "k": k,
        "started_at": started_at,
        "finished_at": finished_at,
        "pass_k": pass_k_result,
        "pass_at_k": pass_at_k_result,
        "trials": trial_entries,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    _emit_report(meta, all_trial_verdicts, run_dir)
    return run_dir


def regrade(
    run_dir: Path,
    task_path: Path,
    db_paths: list[Path] | None = None,
) -> list[list[GraderResult]]:
    """Re-run graders against stored transcripts; append new rows to verdicts.jsonl.

    check graders: always re-run from stored transcript; workspace checks read the
      trial_N/workspace/ snapshot persisted by run().
    sql graders: re-run only if db_paths[i] provided; verdict is 'skip' otherwise.

    Satisfies spec §9 req 5: grader iteration without re-running the trial (no API call).
    """
    task = yaml.safe_load(task_path.read_text())
    meta = json.loads((run_dir / "meta.json").read_text())
    k = meta.get("k", 1)
    graded_at = datetime.now(timezone.utc).isoformat()

    all_results: list[list[GraderResult]] = []
    for i in range(k):
        trial_dir = run_dir / f"trial_{i}"
        transcript_path = trial_dir / "transcript.jsonl"
        if not transcript_path.exists():
            # Trial errored before producing a transcript (see meta.json trials[i].error).
            all_results.append([])
            continue
        transcript = Transcript.read_jsonl(transcript_path)

        db_path = db_paths[i] if db_paths and i < len(db_paths) else None
        workspace = trial_dir / "workspace"

        verdicts = grade(transcript, db_path, workspace, task)
        for v in verdicts:
            v.graded_at = graded_at

        _append_verdicts_jsonl(trial_dir / "verdicts.jsonl", verdicts)
        all_results.append(verdicts)

    return all_results


def _count_consecutive_passing_runs(results_root: Path, task_id: str) -> int:
    """Count how many of the most-recent runs for task_id all have pass_k=True.

    Walks run dirs newest-first; stops at the first non-passing run.
    """
    if not results_root.exists():
        return 0
    candidates = sorted(
        [
            d for d in results_root.iterdir()
            if d.is_dir()
            and d.name.startswith(f"{task_id}_")
            and (d / "meta.json").exists()
        ],
        key=lambda d: d.name,
        reverse=True,
    )
    consecutive = 0
    for run_dir in candidates:
        meta = json.loads((run_dir / "meta.json").read_text())
        if meta.get("pass_k"):
            consecutive += 1
        else:
            break
    return consecutive


def emit_suite_report(results_root: Path) -> None:
    """Print a per-task summary across all runs in results_root (spec §8.2).

    Reads run dirs directly; picks the latest run per task_id. Shows pass^k /
    pass@k per task and per-suite aggregates (regression pass^k rate, capability
    pass@k rate).

    Saturation signal (spec §7): a regression task that has passed 100% (pass^k)
    for _SATURATION_THRESHOLD or more consecutive runs is flagged — the regression
    suite is saturated as a signal that the capability suite needs new tasks.
    """
    if not results_root.exists():
        print("No results found.")
        return

    latest: dict[str, dict] = {}
    for d in sorted(results_root.iterdir()):
        if not d.is_dir() or not (d / "meta.json").exists():
            continue
        meta = json.loads((d / "meta.json").read_text())
        task_id = meta["task_id"]
        if task_id not in latest or d.name > latest[task_id]["_dir_name"]:
            meta["_dir_name"] = d.name
            latest[task_id] = meta

    if not latest:
        print("No completed runs found.")
        return

    regression = [m for m in latest.values() if m.get("suite") == "regression"]
    capability = [m for m in latest.values() if m.get("suite") == "capability"]

    print(f"\n{'='*64}")
    print("Suite Report")
    print(f"{'='*64}")

    for group_label, group in [("Regression", regression), ("Capability", capability)]:
        if not group:
            continue
        is_regression = group_label == "Regression"
        metric_key = "pass_k" if is_regression else "pass_at_k"
        policy = "pass^k" if is_regression else "pass@k"

        print(f"\n{group_label}:")
        print(f"  {'Task':<10} {'pass^k':<10} {'pass@k':<10} {'Run'}")
        print(f"  {'-'*60}")
        for m in sorted(group, key=lambda x: x["task_id"]):
            pk = "PASS" if m.get("pass_k") else "FAIL"
            pak = "PASS" if m.get("pass_at_k") else "FAIL"
            print(f"  {m['task_id']:<10} {pk:<10} {pak:<10} {m['run_id']}")
        passing = sum(1 for m in group if m.get(metric_key))
        print(f"  {'-'*60}")
        print(f"  {policy} aggregate: {passing}/{len(group)} tasks passing")

    # Saturation signal (spec §7)
    if regression:
        saturated = []
        for m in regression:
            streak = _count_consecutive_passing_runs(results_root, m["task_id"])
            if streak >= _SATURATION_THRESHOLD:
                saturated.append((m["task_id"], streak))
        if saturated:
            print(f"\n⚠  SATURATION SIGNAL: {len(saturated)} regression task(s) passed 100% "
                  f"for ≥{_SATURATION_THRESHOLD} consecutive runs — the capability suite "
                  "needs new tasks (spec §7).")
            for tid, streak in sorted(saturated):
                print(f"   {tid}: {streak} consecutive pass^k runs")

    print(f"\n{'='*64}\n")
