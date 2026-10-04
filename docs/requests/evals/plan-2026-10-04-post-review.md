# Plan: evals post-review follow-through

- **Date:** 2026-10-04
- **For:** a fresh lead-agent session that orchestrates subagents
- **Parent:** umbrella issue #34, spec `docs/requests/evals/spec.md`
- **Predecessor work:** the review `review-2026-07-19-issue-34-implementation.md` (this folder) was
  verified finding-by-finding and fully fixed on branch `eval-review-fixes` (see "Starting state").

## How to use this document (lead agent)

You are the **lead**. You plan, delegate, review diffs, run the suite, and commit. Subagents do the
focused work. Work the workstreams **in order**; each ends at a commit (a revert point) and, where
marked **USER CHECKPOINT**, a stop for the user's decision. Do not skip checkpoints — several
spend subscription quota or need a product decision only the user can make.

Read first, in this order:
1. Repo `CLAUDE.md` (py3env + `bin/finance` rules) and `~/.claude/CLAUDE.md` (be concise).
2. This plan, end to end.
3. `docs/requests/evals/spec.md` §6 (graders), §7 (suites), §8 (results), §11 (rollout).
4. `evals/README.md`, `evals/harness/runner.py` (top-of-file lockdown comment).

## Starting state (verified 2026-10-04)

- Branch **`eval-review-fixes`**, 5 commits on top of `main`. `main` is untouched.
- Revert point: tag **`pre-eval-review-fixes`** (= `main` @ `b308c69`).
  `git reset --hard pre-eval-review-fixes` on the branch, or just `git switch main`.
- Commits:
  | Commit | Content |
  |---|---|
  | `644e936` | 29 repro tests for every review finding (`tests/test_eval_review_findings.py`) |
  | `bd45cbd` | untrack `.claude/worktrees/` + `nvim.log` (F10) |
  | `a81021f` | graders + harness: F1–F5, F7, F8, cut1, cut3 (shared tool-call index, MCP name canonicalisation, text-block decoding, micros-aware groundedness, transcript persisted before grading, grade off-loop, single `gates_pass`) |
  | `fad5535` | **trial lockdown** + F6, cut2, cut4, runtime/CLAUDE.md bridge |
  | `3be59e0` | F9 (gate sql without expect fails), cut5 (clock front door) |
- Suite: `py3env/bin/pytest tests/ -q -p no:cacheprovider` → **839 passed, 0 xfailed**.
- Not committed and must stay that way: `.claude/settings.local.json` (user-local edits).

### Facts established by real runs (don't re-derive)

- Real trial tool names are `mcp__finance-hub__finance_<tool>`; graders canonicalise to
  `finance.<tool>`. Agents call `ToolSearch` first (MCP tools are deferred).
- MCP results = one text block of JSON; errors = plain text with `is_error: true`; success
  `is_error` is null from the SDK (runner coerces to bool).
- Money in tool results: `*_micros` ints and `$`-less decimal strings without trailing zeros.
- Trial isolation (fixture DB, frozen clock) works; live `finance-hub.db` untouched.
- **Lockdown** (`evals/harness/runner.py`): `--tools ToolSearch`, strict MCP config,
  `ENABLE_CLAUDEAI_MCP_SERVERS=false` (the load-bearing connector switch — strict-mcp alone does
  NOT block claude.ai Gmail/Drive/etc.), `dontAsk` + allow-list, `ANTHROPIC_API_KEY` blanked.
  Before the fix, trials had Bash/Write/WebFetch and the user's Gmail/Drive connectors under
  `bypassPermissions`.
- Cost: ~$0.35–0.50 per trial (`claude-sonnet-5`, 3–9 turns). Each trial also writes a session file
  under `~/.claude/projects/-private-var-folders-…-trial-*` (harmless; user may want them cleaned).
- Real transcripts as test fixtures: `tests/fixtures/eval_transcripts/` (R12, C1 + MCP envelopes).
- Probe scripts (portable, in `docs/requests/evals/probes-2026-10-04/`):
  - `verify_lockdown.py new <out.json>` — **no-LLM** check (fake local API) that the trial gets
    only `ToolSearch` + `finance-hub`, `dontAsk`, `apiKeySource: none`. Run before any real spend.
  - `verify_permissions*.py`, `verify_cli_runner.py`, `verify_apikey.py` — deeper no-LLM probes.
  - `capture_mcp.py` (env `OUT=<dir>`) — call MCP tools directly against fixtures, no LLM.
  - `run_trial.py <TASK> <OUT> [model]` — one real trial (k=1) that saves the raw SDK stream and
    the trial dir. **Spends quota.**

## Ground rules

1. **Python** only via `py3env/bin/python` / `py3env/bin/pytest`. `finance` only via `bin/finance`.
2. **Quota**: any real agent trial (harness `run()` with `SDKRunner`, `run_trial.py`) needs explicit
   user approval of the count. Always run `verify_lockdown.py` first; abort if `tools` ≠
   `['ToolSearch']` or any `claude.ai *` server appears.
3. **Revert points**: one commit per workstream phase on the working branch; tag the start of each
   workstream (`ws1-start`, …). Never force-push, never rewrite `main`.
4. **Repro-first**: for each bug, first add a test asserting intended behaviour, marked strict
   `xfail`; the fix removes the marker (pattern: `open_finding` in
   `tests/test_eval_review_findings.py`).
5. **Subagent file ownership**: when subagents run in parallel, give each a disjoint file list and
   say "re-read before each edit; don't revert others' changes". Prefer sequential when two tasks
   touch the same file. Subagents never commit and never switch branches; the lead reviews the
   diff, runs the full suite, and commits.
6. **Outward-facing actions** (opening/commenting on GitHub issues, PRs, merging) — confirm with the
   user first; draft the text and show it.
7. Follow the spec's habit (§11): **read transcripts every real run**; find grader gaps by reading,
   not by adding graders speculatively.

## Workstreams

### WS0 — Land the review fixes (USER CHECKPOINT)

Ask the user how to land `eval-review-fixes`: (a) open a PR to `main` (recommended — draft the body
from the commit table above, include the lockdown note prominently), (b) merge locally, or
(c) keep stacking new work on the branch. Do whatever they choose; if stacking, still tag
`ws1-start`.

Surface these judgment calls made on the branch (in the PR body, or to the user directly) so they
are ratified, not silently inherited:
- **Zero gates ⇒ not passing** (`graders.gates_pass`): a task with no gate graders fails pass^k and
  skips its judge. Spec §6.3/§6.4 is silent; all shipped tasks have gates.
- **Groundedness accepts rounding**: a prose amount is grounded if it equals a tool amount rounded
  half-up to the prose's precision (e.g. "$176.47" vs `176470588` micros). Strict equality is a
  one-branch removal in `_is_grounded`.
- **Unknown track/flag trajectory graders now `skip`** (were spurious `fail`); unknown *gate*
  trajectory graders still fail.
- **`runtime/mcp.json` → `py3env/bin/finance-mcp`** — also changes interactive sessions via the
  `.mcp.json` symlink (works when Claude Code is started from the repo root).

## Provenance of the workstreams

Before writing this plan, the 2026-10-04 session proposed: fix eligibility; build all 12 missing
C-task graders; convert C1's handler to YAML; run the regression suite. After checking open issues
and the repo for leftover eval work (only #34 umbrella and #48 calibration are open; the suite had
never run for real), it re-scoped: eligibility → WS1; real baseline → WS2; only the promised C7
groundedness grader + C1 conversion → WS3; the 11 track-only graders → deferred backlog issue
(WS4) until real runs show they're worth tracking (spec §11: find grader gaps by reading
transcripts).

### WS1 — Fix strategy-eligibility bug (USER CHECKPOINT on the rule)

**Bug:** `src/finance_hub/research/tools.py:421` (`_strategy_has_eligible`) and `:584`
(`research_priorities`) query `fin_strategy_eligible_instruments`, a table that never existed.
`_store.has_rows` treats a missing table as "no rows", so every candidate reports
`PROMOTION_REQUIRED` (`readiness.dca/one_time` always False) and `research_priorities` always reports
`NO_ACTIVE_STRATEGY`. The docstring ("strategy slice not built yet") is stale: promotion writes
`fin_strategy_instruments` (`src/finance_hub/strategy/_store.py:66`) under `fin_strategy_versions`
(`status IN draft|active|archived`, at most one active).

**Decide with the user before coding** (present as a short question):
- Eligible = ticker in `fin_strategy_instruments` for the version with `status='active'`
  (recommended), or additionally require its sleeve `target_weight_bps > 0`?
- Draft/archived versions do not count (recommended).
- `research_priorities` `NO_ACTIVE_STRATEGY` = no `fin_strategy_versions` row with `status='active'`.

**Execution:** one subagent (files: `src/finance_hub/research/tools.py`, research tests).
Repro tests first: C2 fixture (`evals/fixtures/build_fundamentals_eligibility.py`) must yield
`readiness.dca=True, one_time=True`, no `PROMOTION_REQUIRED`; a draft-only strategy must still yield
`PROMOTION_REQUIRED`. Prefer reusing strategy-side readers (`strategy/_store.py`) over new SQL if a
suitable function exists. Lead verifies end-to-end with `capture_mcp.py` against the C2 fixture
(no LLM). Grep for other readers of the phantom table. Commit.

### WS2 — First real regression baseline (USER CHECKPOINT: spend)

Purpose: the suite has **never** run for real (`evals/results/` empty). This is spec §11's next
step and a prerequisite for #48 calibration.

1. Pre-flight (no spend): full test suite green; `verify_lockdown.py new` passes.
2. Ask the user to approve: **R1–R12, k=1 → 12 trials, est. $4–6**. Suggest k=1 now; pass^3 later.
   Also ask whether run outputs under `evals/results/runs/` should be committed or gitignored.
3. Run tasks via `harness.run(Path('evals/tasks/R<n>.yaml'), SDKRunner(), k=1)` (from repo root,
   `PYTHONPATH=.`). Run 2–3 at a time at most (rate limits); record each run dir. Then
   `emit_suite_report(Path('evals/results/runs'))`.
4. **Transcript reading — fan out**: one read-only subagent per task (or per 2–3 tasks), each given
   the run dir, the task YAML, and this brief: for every verdict, classify as
   *correct* / *mis-grade (grader bug)* / *agent failure* / *task-spec ambiguity*, citing transcript
   evidence; list anything surprising (isolation, tool errors, prompt issues). No code changes.
5. Lead consolidates into `docs/requests/evals/baseline-2026-10-<dd>.md` (table: task → verdicts →
   classification → evidence → proposed action). Show the user. Fixes found here become their own
   repro-first commits (grader bugs) or issue drafts (product bugs / task-spec changes).

Known expectations: C-tasks are out of scope for this baseline; R11 deliberately exercises a tool
error; R8 expects an honest refusal (no prices); `map_instruments` with a wrong arg name returns a
bare `KeyError` (known, see WS4).

### WS3 — C7 `trajectory.no_invented_fundamentals`

Promised at `evals/tasks/C7.yaml:95-101` ("deterministic groundedness check at Phase 2"); currently
skips (no handler). Build as a Python trajectory handler in `evals/harness/graders.py` reusing the
groundedness helpers from F4 (`_grounded_amounts`, `_is_grounded`, `_extract_financial_numbers`):
every fundamentals-style number in final prose (ratios, percentages, large figures) must be
grounded in a tool result. Role stays `flag`. Tests: synthetic pass/fail + the real C7
`generate_deployment_plan` envelope in `tests/fixtures/eval_transcripts/`. Decide (and document)
how percentages and ratios are extracted — keep it conservative to avoid flagging counts/dates.
One subagent; commit.

Also convert the one Python-only track handler added on 2026-10-04,
`_traj_fetch_fundamentals_called_for_aapl`, into an inline YAML `check:` in `C1.yaml`
(`tool_input('finance.fetch_fundamentals','ticker') == 'AAPL'`), matching the R-task pattern, and
delete the handler.

### WS4 — Housekeeping + issue drafts (USER CHECKPOINT before posting)

- Fix `evals/README.md` phase table (Phase 3 "Trajectory + breadth" is done via #45; "Judge +
  calibration" is not complete — #48 open). Document the lockdown and `probes-2026-10-04/`.
- Draft (show the user, post only on approval):
  - Comment on #34 summarising the review verification + fixes (commit table above) and WS1–WS3.
  - New issues (labels per `docs/agents/triage-labels.md`):
    1. `finance.map_instruments` returns a bare `KeyError('instrument_role')` on a wrong arg name —
       should be a validation error naming the expected field.
    2. Fixture seed rows use the wall clock, not the task's frozen `now` (only tool-written rows are
       frozen).
    3. `graded_at` is set before trials run (equals start time).
    4. Backlog: 11 track graders declared in C2–C8 with no implementation (now `skip`):
       C2 `candidate_evidence_called`; C3 `generate_deployment_plan_called`,
       `one_time_budget_passed`; C4 `list_sources_or_get_theme_called`; C5
       `replacement_source_added`, `workflow_order_correct`; C6 `promote_to_strategy_called`,
       `generate_deployment_plan_called`, `review_instrument_called`; C8 `readiness_reported`,
       `both_candidates_reviewed`. Implement as inline YAML `check:` expressions (R-task pattern;
       C8 needs a small `tool_inputs_all(name, field)` helper) **only once real runs show they are
       worth tracking**.
    5. Trial context still includes the OAuth account email and the real date (low priority).
- Ask the user whether to delete the two `~/.claude/projects/*trial-R12*` / `*trial-C1*` session
  dirs from 2026-10-04.

### Explicitly out of scope

- #48 judge calibration — human/SME work; WS2 output feeds it. Offer to prepare a sampling sheet
  only if asked.
- Golden transcripts for C-tasks (deferred by design to migration-to-regression, spec §7).
- Skills (#51–#59) and C8's skill placeholder.
- pass^3 runs and capability-suite runs — after the baseline is read and fixed.

## Suggested orchestration

```
WS0 (ask) ─► WS1 (ask rule) ─► subagent: fix + tests ─► lead: verify (capture_mcp) ─► commit
          └► WS2 pre-flight (parallel with WS1 coding; no spend)
WS1 done ─► WS2 (ask spend) ─► lead runs trials ─► N parallel read-only transcript readers
          ─► lead consolidates baseline doc ─► show user
WS3 subagent (graders.py) can run in parallel with WS2 reading (no shared files)
WS4 last: drafts ─► user approves ─► post
```

Status updates to the user: one line per workstream transition; full summary at each checkpoint.
