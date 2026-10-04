# Code review — issue #34 implementation (agent-evals system)

- **Date:** 2026-07-19
- **Target:** umbrella issue #34 and the implementation of its sub-issues #35–#50
  (#48 judge-calibration still open at review time)
- **Scope:** `git diff a8dc779~1...HEAD -- ':!.claude' ':!nvim.log'` — ~23k lines across
  `evals/`, `runtime/`, `src/finance_hub/{bootstrap,factories}.py`, and tests
- **Method:** /code-review at high effort — 8 independent finder angles (3 correctness,
  3 cleanup, altitude, conventions), 44 raw candidates, deduped to 16, one verifier per
  candidate (recall-biased). 12 CONFIRMED, 2 PLAUSIBLE, 2 REFUTED.
- **Test ground truth:** all 308 eval tests pass locally after installing the
  declared-but-missing `claude-agent-sdk` and `pyyaml` into `py3env` (environment drift,
  not a code finding).

## Headline theme

The harness, graders, and tasks were built and tested almost entirely against
hand-written golden transcripts and synthetic fixtures — and several core contracts are
wrong for **real** runner transcripts. Findings 1, 2, and 6 mean the first real SDK/CLI
run will mis-grade essentially every tool-based gate: positive gates false-fail, and
safety gates (no-mutation, approve-not-called) pass vacuously even when violated.

## Findings (ranked most-severe first)

### 1. MCP tool-name prefix never matched — all tool-name gates wrong on real runs — CONFIRMED

`evals/harness/graders.py:664` (and every exact-string matcher at :122, :249, :286)

All tool-name matching uses bare registry names (`finance.promote_to_strategy`), but
real SDK/CLI transcripts record MCP tools as `mcp__finance-hub__finance.*`
(`sdk_runner.py:31` records `block.name` verbatim; server name from `runtime/mcp.json`).
`grep -rn 'mcp__' evals/` has zero hits — no normalization exists.

**Failure:** positive gates (`tool_called`, readiness-before-approval) always FAIL on
real trials; negative gates (R12 no-strategy-mutation, R10 approve-not-called) pass
VACUOUSLY even when the agent calls the forbidden tool. Only hand-written golden
transcripts grade correctly.

### 2. `tool_result(...)` attribute checks fail on real SDK transcripts — CONFIRMED

`evals/harness/graders.py:264`

`_find_tool_result` wraps content in `_DictNamespace` only when it is a dict, but the
SDK's `ToolResultBlock.content` is `str | list[dict] | None` and `sdk_runner.py:54`
persists it raw — real MCP results arrive as a list of text blocks, never a dict.

**Failure (verified by execution):** content `[{'type':'text','text':'{"stored": 8}'}]`
makes C1's gate `tool_result('finance.fetch_fundamentals').stored == 8` raise
`'list' object has no attribute 'stored'`, caught at graders.py:404-406 and recorded as
FAIL regardless of agent behavior. Affects C1/C2/C7/R1 gates; nothing json-parses text
blocks before attribute access.

### 3. Grading exception discards the trial transcript and cancels siblings — CONFIRMED

`evals/harness/harness.py:326`

`grade()` runs before `transcript.write_jsonl` (line 332), and the judge invocation
(`graders.py:955`, blocking `future.result()` at :764) has no try/except.

**Failure:** k=3 run — trial 1 completes its expensive agent run, its judge grader
raises `CLIConnectionError`; the exception escapes `grade()` before the transcript is
persisted, `asyncio.gather` (harness.py:355, `return_exceptions` unset) cancels trials
0 and 2, `run()`'s finally (lines 431-433) deletes the tmpdirs, and `meta.json`
(line 468) is never written — full API spend, zero persisted output.

### 4. `no_invented_prices` false-fails grounded dollar amounts (micros mismatch) — CONFIRMED

`evals/harness/graders.py:561`

The grader declares any dollar figure "invented" unless its decimal string appears
verbatim in the JSON-dumped tool results, but tool envelopes carry amounts as integer
micros.

**Failure (verified by running the real grader):** a grounded report of a micros-only
`finance.get_deployment_plan` envelope (`SELECT *` over `amount_micros` columns,
`_plan_store.py:126-160`) fails with `invented: ['12345.67', '433.71']`; even
`"$1,000.00"` fails against the paired string `"1000"` emitted by `_micros_to_str`
(`strategy/tools.py:308-310`). `R8.yaml:110` wires this as a hard gate, so grounded
refusal trials false-FAIL for any non-round amount. The docstring at graders.py:546-548
admits the risk; tests only exercise dollar-string tool results.

### 5. `regrade()` grades against a directory that never held workspace files — CONFIRMED

`evals/harness/harness.py:497`

`regrade()` passes `workspace=run_dir/trial_i`, which only ever contains
`transcript.jsonl` and `verdicts.jsonl` — the real fixture workspace was a tmpdir
deleted in `run()`'s finally (lines 431-433).

**Failure:** regrade a passing R6 run — the gate
`bool(workspace('approved/').glob('*plan_r6_fixture*'))` (`R6.yaml:82`) globs a
nonexistent dir and silently returns `[]` (sql graders get skip semantics on a missing
DB at graders.py:338-339; workspace checks get none, graders.py:217-220), appending a
contradictory FAIL row to `verdicts.jsonl`; judge context reads "(no note files
found)". Regrade tests (`test_eval_harness.py:2147-2226`) only cover R1's
sql/transcript graders, so the path is untested.

### 6. CLIRunner produces transcripts graders can't read, and leaks user config — CONFIRMED

`evals/harness/cli_runner.py:62`

CLIRunner stores raw stream-json objects as event data, but the CLI nests the API
message under `"message"`, so every grader helper's `e.data.get('content', [])` returns
`[]` for all events. It also never reads `TrialEnv.setting_sources` (no
`--setting-sources` flag at cli_runner.py:26-37), so the subprocess loads the
developer's `~/.claude` config, breaking the isolation SDKRunner establishes with
`setting_sources=['project']` (`runner.py:73-92`).

**Failure:** any CLIRunner trial (the advertised debug/parity path,
`EVALS-TRIGGER.md:53`) — tool gates fail, `not_contains` gates pass vacuously; an
SDK/CLI parity comparison silently grades an empty transcript. (CLIRunner is not wired
into the harness today, but it is exported and documented.)

### 7. `_find_tool_result` returns FIRST result; contract everywhere else is LAST — CONFIRMED

`evals/harness/graders.py:245`

Its own docstring (line 244), the module DSL doc (line 12), and the sibling
`tool_input` (which iterates `reversed(calls)`) all promise the LAST call; the
implementation iterates forward and returns on the first match.

**Failure:** agent's first call errors, retry succeeds (a path the suite itself
anticipates — `_traj_retry_with_note` exists for exactly this);
`tool_result(...).readiness['one_time']` evaluates the stale failed (string-content)
result, attribute access raises, and the check converts to a wrong-verdict FAIL for a
successful trial.

### 8. Synchronous grading (incl. LLM judge) blocks the shared event loop — CONFIRMED

`evals/harness/harness.py:326` + `graders.py:762-764`

Issue #46's k concurrent trials run as coroutines on one loop (harness.py:355,
425-430); `grade()` is called synchronously inside the coroutine, and `_invoke_judge`
blocks the loop thread on `future.result()` (its docstring confirms the design).

**Failure:** while one trial's judge grade runs (tens of seconds of LLM round-trip),
every other trial's `runner.run` coroutine stops consuming SDK output — k-concurrency
degrades toward sequential. Fix: `await asyncio.to_thread(grade, ...)` or make the
judge path natively async.

### 9. sql grader without expect/expect_min silently passes as a gate — CONFIRMED (latent)

`evals/harness/graders.py:365`

The explicit fail guard from commit `514e5b3` ("no 'expect' or 'expect_min' in spec" →
FAIL) was dropped in the `efc83f4` merge resolution in favor of mainline `12b6e3e`'s
track-metric else-branch, which is role-unconditional and undocumented.

**Failure (verified by execution):** a gate-role sql spec with a typo'd key
(`expects: 99`) returns verdict `pass` with actual=0. `_validate_task`
(harness.py:110-118) validates nothing about grader keys, so a typo turns a gate
vacuous and pass^k masks real regressions. No current YAML hits it.

### 10. Entire worktree snapshot + nvim.log committed to main — CONFIRMED

`.claude/worktrees/glowing-conjuring-ritchie/` (117 files), `nvim.log` — via merge
`efc83f4` (issue #44)

A second complete copy of the codebase (src/, tests/, docs/, `.sandcastle/`, and
`.claude/settings.local.json` — a local-permissions file that should never be shared)
is tracked in the repo and diverges from the real tree as main moves; greps and
refactors now hit stale duplicates.

**Fix:** `git rm -r .claude/worktrees nvim.log` and add both to `.gitignore`.

## Verified but cut by the 10-finding cap

- **Gate-pass policy in triplicate with diverging zero-gate semantics** — CONFIRMED
  (latent). `_trial_gate_pass` (harness.py:183, `bool(gate) and all(...)`) fails an
  all-track/flag task while `grade()`'s inline gating (graders.py:1069) and the
  exported-but-never-called `compose_verdict` (graders.py:974 — spec §6.4's mechanism,
  dead in the run path, test-only callers) treat empty gates as pass. All 20 shipped
  tasks have explicit gates, so latent; but any rule change must be made in three
  places.
- **`runtime/mcp.json` launches bare `finance-mcp` via PATH** — PLAUSIBLE. Resolves to
  the global framework Python instead of `py3env/bin/finance-mcp`, violating the repo
  CLAUDE.md py3env rule; `_make_trial_env` (harness.py:160-166) passes the command
  through verbatim. Mitigating: the global install turned out to be editable against
  this same repo, so the risk is interpreter/dependency skew rather than stale code.
- **Judge skip rows have no rubric-dimension fallback** — CONFIRMED (latent).
  graders.py:1075 uses `spec.get('dimensions', [])` while the run path (:866) falls
  back to the rubric's dimensions — a rubric-only judge task emits zero judge rows when
  gates fail, violating the docstring's promise at :1054. Both shipped judge tasks
  declare inline dimensions.
- **Golden transcripts use a flat schema `Transcript.read_jsonl` can't parse** —
  PLAUSIBLE (latent). `{"type": "metadata", ...}` lines raise `KeyError: 'data'` at
  `runner.py:24` (reproduced), and flat `tool_use`/`tool_result` types don't match the
  assistant/user iteration graders use. Inert today — nothing loads goldens — but will
  break golden replay when wired up.
- **Clock front door incomplete** — CONFIRMED (latent).
  `portfolio_snapshot.py:257` uses `datetime.now(timezone.utc)` and
  `fundamentals.py:268/320/330` fall back to `date.today()`, violating spec §5.2's
  claim that the tool layer routes all time through `factories.get_clock()`. Verified
  by execution with `FINANCE_HUB_NOW` set. No current grader reads the affected fields.

## Refuted candidates (for the record)

- **`factories.reset()` re-applying the env clock** — REFUTED. Honoring
  `FINANCE_HUB_NOW` across `reset()` is issue #35's explicit acceptance criterion
  ("every now() call in the process returns exactly the pinned timestamp"); fixture
  subprocesses depend on it, live CLI paths don't call `reset()`, and the loud warning
  is the designed signal.
- **Fixture builders leaking process globals between trials** — REFUTED as a
  correctness bug. Every global the hand-rolled builders set is restored in a finally;
  the finding reduces to duplication of `seed_context` (`_common.py:78-127`) — latent
  fragility, no current leak.

## Cleanup backlog (real, outranked — candidates for a /simplify pass)

- `_FixedClock` re-declared in 8 fixture builders (plus `_common.py`, `tests/helpers.py`,
  `factories.py`) — import the shared one.
- ~10 C-task builders hand-roll the save/restore that `_common.seed_context` provides.
- `_pos_hash` byte-for-byte copy of `portfolio_snapshot._row_hash` in 4 builders —
  hash drift would silently break dedup assumptions under test.
- `_helpers.seed_price_bars` duplicates `_common._FixedProvider`/`_make_bar`/`daily_bars`;
  its `calls` recording field is dead.
- `seed_context` inlines the body of `_helpers.use_db` instead of composing it.
- `_FIXTURE_BUILDERS` (harness.py:39) is a 20-entry hand-maintained dict fully
  derivable as `importlib.import_module(f'evals.fixtures.build_{name}')`.
- `_count_consecutive_passing_runs` duplicates `_find_prior_run`'s run-dir scan, and
  `emit_suite_report` re-reads every `meta.json` it already loaded (O(tasks × runs)).
- `ANTHROPIC_API_KEY` stripped in three places (harness.py:145, runner.py:95,
  cli_runner.py:40) — keep the `TrialEnv.__post_init__` invariant only.
- Five independent transcript walkers in graders.py (`_iter_tool_calls`,
  `_tool_calls_ordered`, the three proxies, `_find_tool_result`) — one shared index
  would also fix the O(n²) rescans and finding 7's first-vs-last bug at the root.
- `evals/README.md` phase table drift: Phase 3 "Trajectory + breadth — Not started"
  though #45 merged; Phase 4 "Judge + calibration — Complete" though calibration (#48)
  is still open.

## Suggested fix order

1. Findings 1+2+7 together — they share a root cause: define the canonical transcript
   event schema + one tool-call/result index at the runner seam, normalize MCP names
   there, and make all graders consume it (also fixes finding 6's shape half).
2. Finding 3 (persist transcript before grading; wrap judge invocation) — protects all
   future spend.
3. Finding 4 (micros-aware groundedness matching) and finding 5 (persist or re-point
   the workspace for regrade).
4. Finding 9 (restore the missing-expect guard, or role-condition it) + task-schema
   validation.
5. Finding 10 (`git rm` the worktree snapshot + nvim.log) — one-commit hygiene fix.
