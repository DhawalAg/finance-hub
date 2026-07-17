# Finance Hub — Agent Evals — Working Spec

**Status:** Ratified — every §13 open question resolved via the grilling tickets (#25–#30);
this revision folds the resolutions in (#31)
**Updated:** 2026-07-17
**Sources:** Anthropic webinar notes (`my-obsidian: 100-agentic/anthropic-webinars/ai-evals`),
[Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
(esp. the *Evaluating Research Agents* section)

This spec defines **what the finance-hub eval system must measure and how**, so a later
implementation pass can build the harness without re-deriving the design. It deliberately specifies
contracts (task model, grader tiers, suite policy, harness requirements); the implementation
choices originally left open are now resolved and folded in (§13 records each resolution).

## 1. Why This Exists

The pytest suite already covers the **deterministic layer** thoroughly: adapters, migrations, money
math, plan generation, output-mode degradation. That is regression testing of tools — it is *not* an
agent eval, and this spec does not duplicate it.

What nothing verifies today is the layer the repo actually exists for: **an agent orchestrating
registered tools into a grounded, durable, citable outcome.** The core invariant (CONTEXT.md: the
agent "must not invent prices, metrics, budget facts, or allocation math") is currently enforced by
tool design and hope, and checked only by manual use. Three pressures make that untenable:

1. **ADR 0005 makes skills the orchestration layer.** Each finance skill is a playbook over tools.
   A skill that silently does freehand math, skips the readiness check, or writes uncited prose
   defeats the repo's differentiator — and today there is no way to detect that except by reading
   sessions by hand.
2. **The SUT keeps changing.** Model swaps, prompt/CLAUDE.md edits, new skills, and tool-contract
   changes each move behavior. Evals are a *hill to climb, not a gate you pass once*: every change
   to any layer of the stack should be measurable against the same task set.
3. **The frontier is live.** The fundamentals HTTP client just landed (PR #20), unlocking the
   one-time-buy flow. Writing capability evals for that flow *now* — before the orchestration
   hardens — is eval-driven development: the evals define what "the one-time-buy workflow works"
   means before we claim it does.

## 2. System Under Test

The SUT is the **whole agent stack**, not the tools alone:

```text
model + runtime CLAUDE.md + skills (ADR 0005) + tool registry + MCP server + SQLite store
```

A trial exercises this stack end-to-end: a task prompt goes in, the agent runs until done, and the
graders inspect what durably happened. Changing any layer (model, prompt, skill, tool schema) is a
new SUT version; whether it triggers a suite run is decided by the §8.1 hash rule (adoption
boundaries, not every edit).

**The prompt surface is the runtime surface only** (resolved, #30). The repo holds two distinct
prompt surfaces: the **runtime surface** — the deployed finance-hub's skills, MCP config, and a
runtime-only CLAUDE.md — and **dev scaffolding** — the root CLAUDE.md, `docs/agents/**`,
triage/process docs: the factory, not the product. Only the runtime surface is part of the SUT.
The harness materializes exactly that surface into each trial dir from a checked-in
**materialization list** under `evals/` (§9); the §8.3 prompt hash is computed over exactly what
gets materialized. The list cannot drift from reality because it *is* the mechanism by which
trials load anything — a file not on the list is not in the trial's context. This also closes a
latent contamination bug: running trials with `setting_sources=["project"]` against the live repo
would have injected triage/process instructions into SUT trials. Scaffolding edits never change
the hash and never trigger runs.

**Two CLAUDE.md sets.** The runtime-only CLAUDE.md copied into every trial dir is a real
versioned artifact — the first draft of what a deployed finance-hub ships with, not just eval
plumbing — distinct from the root dev CLAUDE.md. Its home is decided at Phase 1 (e.g. `evals/sut/`
or `runtime/`); the line-by-line audit splitting today's CLAUDE.md happens once, at Phase 0/1
task-writing (§11). New runtime files enter via the ADR-0006 skill DoD: shipping a skill includes
adding it to the materialization list (§7).

Three evaluation layers, only two of which are this spec's scope:

| Layer | Question | Mechanism | Status |
|---|---|---|---|
| L0 — deterministic | Do the tools compute correctly? | pytest | Exists; out of scope |
| L1 — agentic outcome | Did the agent drive the tools to the correct durable state? | outcome + trajectory graders | This spec |
| L2 — research quality | Is the prose grounded, complete, well-sourced? | LLM-judge rubrics + human calibration | This spec |

## 3. Vocabulary

These terms extend the CONTEXT.md Language section and should migrate there once the spec is
accepted.

**Task**: One test case — a fixture, a prompt, a reference solution, and a set of graders. Written
so two competent reviewers would agree on what success means.

**Trial**: One agent attempt at a task. Tasks run as multiple trials because the SUT is
non-deterministic.

**Transcript**: The complete record of a trial — every tool call, its arguments, its result, and
all agent text. Persisted durably so graders can be re-run without re-running trials.

**Outcome**: The durable state after a trial — rows in the SQLite store and artifacts in the
workspace. *Never* the agent's claim that something happened. A plan is approved when
`fin_deployment_plans.status` says so, not when the transcript says "I approved the plan."

**Grader**: A function scoring one aspect of a trial. Tasks compose multiple graders; each grader
produces one verdict plus detail.

**Suite**: A named collection of tasks. Two kinds — **regression** (should pass ~100%; a drop is a
defect) and **capability** (expected to start low; measures the frontier).

**Gate / Track / Flag**: The three verdict roles. *Gate* fails the trial (outcome wrong). *Track*
records a metric for cross-version comparison without failing (turns, tokens, trajectory quality).
*Flag* routes the transcript to human review instead of failing (subjective quality below
threshold, suspicious trace patterns).

**pass@k / pass^k**: pass@k = at least one of k trials succeeded (fine for research exploration).
pass^k = all k trials succeeded (the bar for money-adjacent flows, where consistency is the
product).

**Runtime surface / dev scaffolding**: The repo's two prompt surfaces (§2). The runtime surface
(runtime CLAUDE.md, skills, MCP config) is part of the SUT and is all a trial ever loads; dev
scaffolding (root CLAUDE.md, `docs/agents/**`, process docs) never enters a trial.

**Materialization list**: The checked-in manifest under `evals/` naming every runtime-surface
file the harness copies into a trial dir; also the exact input to the §8.3 prompt hash.

**Adoption boundary**: The moment before a change to a versioned SUT component (model pin, skill
set, prompt surface) is adopted. The regression suite runs at adoption boundaries, not on every
edit (§8.1).

## 4. The Outcome Is The Database

The webinar's central point maps one-to-one onto finance-hub: the durable proof of "X was done" is
a row, not a sentence. Concretely, per workflow:

| Workflow | Durable outcome surface |
|---|---|
| Research | theme rows and statuses, instrument mappings, review rows (status, conviction, conviction note), research notes (markdown), source links and supersessions |
| Market data | price/envelope/metric/fundamentals rows with provenance |
| Strategy | promotion snapshots, versioned strategy rows, active-version status |
| Planning | deployment plan rows (status, lines, buckets), evidence references that resolve, readiness-check results, memo artifacts in the workspace |

Every L1 grader reads these surfaces (plus the transcript). No grader ever trusts prose about
state.

## 5. Task Model

### 5.1 Task definition

Tasks live as one file each under `evals/tasks/` (format decided at implementation; YAML assumed).
Required fields:

- `id`, `title` — stable identity; results reference tasks by id + version.
- `suite` — `regression` | `capability`.
- `workflow` — `research` | `market-data` | `strategy` | `planning` | `chain` (multi-workflow).
- `fixture` — named fixture the harness materializes before the trial (§5.2).
- `now` — the frozen timestamp for the trial (§5.2). Required for every frozen-fixture task; the
  harness refuses to run a frozen-fixture task without one. Absent for live-replay tasks, where
  the harness must not freeze the clock.
- `prompt` — the user message given to the agent. Unambiguous: two experts must agree on success.
- `reference` — a reference solution: the expected outcome described concretely (expected rows /
  artifact properties), plus optionally a golden transcript from a manual run.
- `graders` — ordered list of grader ids with per-task parameters (e.g. coverage key-facts list).
- `provenance` — where the task came from (real session, bug, spec section). Tasks are collected
  from real usage first, invented second.
- `version` — bumped on any change to prompt, fixture, or graders; results are comparable only
  within a task version.

### 5.2 Fixtures: freeze by default

A fixture is a fully materialized environment: a seeded SQLite DB, a seeded workspace, and frozen
provider data. Freezing beats replaying for nearly everything we do — deterministic, reproducible,
cheap:

- **DB fixtures** are built by scripts that run the real migrations and real tools against a temp
  DB (reuse the `tests/fixtures` machinery). Never hand-crafted SQL — fixtures must stay valid as
  the schema evolves.
- **Provider data is frozen.** The recorded-fixture adapters that already exist for fundamentals
  are the pattern; price data gets the same treatment. Live-provider (replay) trials are a separate
  small capability set, not the default.
- **The clock is frozen via `FINANCE_HUB_NOW`** (resolved, #26). Freshness bands and output-mode
  degradation depend on "now", so staleness-dependent tasks would rot as real time passes.
  Mechanism: when the env var is set, `factories.py` installs a fixed clock through the *existing*
  `Clock` seam (`set_clock`) — an env-var front door on the seam the tool layer already routes all
  time through (`factories.get_clock().now()`); precedent: `FINANCE_HUB_DB` in
  `store/connection.py`. Semantics: a **frozen instant** — every `now()` call in a trial returns
  exactly the pinned timestamp. Known, accepted caveat: timestamp ties at the three
  `ORDER BY`-on-timestamp sites; revisit only if a grader ever trips on a tie. Validation:
  ISO-8601; bare date → midnight UTC; naive datetime → assumed UTC; set-but-unparseable **fails
  fast at factory init** — never a silent fallback to the real clock. On activation the factory
  emits one loud log line (`clock frozen at <ts> via FINANCE_HUB_NOW`) so a frozen clock can never
  leak into normal use silently.
- **Fixtures document their data epoch; variants share fixtures.** Every frozen-fixture task
  declares its `now` at task level (§5.1). Fresh/stale variants of a scenario share one fixture
  with different `now`s — degradation honesty (§5.3) becomes a one-line variant of the happy-path
  task, not a second fixture.
- **Live-replay tasks are the explicit exception**: the harness must NOT set `FINANCE_HUB_NOW`
  for them — a frozen clock would contradict live provider data.
- **Isolation is absolute.** Every trial gets its own copy of the fixture DB and workspace via
  `FINANCE_HUB_DB` / `FINANCE_HUB_WORKSPACE`. Shared state between trials is the canonical harness
  anti-pattern (correlated failures, order-dependent results).

### 5.3 Balanced tasks: negatives are half the point

One-sided evals produce one-sided optimization. For finance-hub the negative cases *are* the core
invariant, so the task set must include, from day one:

- **Refusal-to-invent**: price provider unavailable in fixture → correct behavior is a reported
  gap, not a number. Any numeric answer fails.
- **Degradation honesty**: stale fixture data → plan must come out in the degraded output mode with
  the right warnings, and the agent must present it as degraded.
- **Gate respect**: readiness check fails → agent must not push to approval; a plan approved
  anyway fails the task.
- **Validation handling**: conviction score without a note is rejected by the tool → agent must
  handle the rejection correctly (supply a note or surface the requirement), not silently drop the
  review.
- **Scope discipline**: research actions must not mutate strategy state (Boundary Decision 1);
  promotion only via the explicit tool.

## 6. Graders

Ordering principle (webinar): put the most coverage in the **cheapest grader type that exposes the
failures you care about**. For finance-hub that ordering is unusually favorable — the grounding
architecture means most of what matters is checkable deterministically.

### 6.1 Outcome graders (code-based, primary)

SQL and filesystem assertions against the post-trial environment. One assertion per reasoning step,
not one per task — when a task fails, the report should show the exact breaking point ("plan
generated, buy-only ✓, but allocations exceeded deployable cash"), not "wrong answer".

Illustrative assertions for the DCA chain task:

- portfolio snapshot imported with expected position count and `as_of`
- theme exists with expected status; instruments mapped with expected roles
- reviews present with status/conviction, and every conviction has a non-empty note
- strategy version created by explicit promotion; active
- plan row exists; buy-only; every line's instrument is in the active strategy version;
  `sum(lines) ≤ deployable_cash`
- every evidence reference resolves to a real store row (the *citations are real* check)
- output mode matches what the fixture's data freshness dictates
- memo artifact exists in the workspace and carries the generated-do-not-edit warning
- plan status is exactly what the task called for (`draft` vs `approved` — an over-eager approval
  fails a draft-only task)

### 6.2 Trajectory graders (transcript-based, secondary)

For finance flows the path genuinely matters, so grade it — but as **track/flag, not gate**, unless
the task says otherwise (rigid step-sequence gates penalize valid creative solutions):

- **right tools**: readiness check called before generation/approval; promotion tool used rather
  than any other mutation path
- **right args**: correct `theme_key`/ticker; queried the category asked about
- **no waste**: no duplicate identical calls, no error loops (error loop → flag for human review)
- **grounded numbers (deterministic groundedness)**: every number in the agent's final prose
  appears in some tool result within the transcript. This is a cheap, code-based check that catches
  most invented-number failures *before* any LLM judge is involved — it should be one of the first
  graders built.

### 6.3 LLM-judge graders (L2, research prose only)

The research layer is a research agent in the blog's sense, and inherits its recommended grader mix.
Judges score against **versioned rubrics**, not golden answers:

- **Groundedness**: every material claim in a thesis/note is supported by a linked source or
  evidence reference in the store. (The deterministic 6.2 check covers numbers; the judge covers
  qualitative claims.)
- **Coverage**: the task defines key facts a competent thesis must address (e.g. for a defensive
  anchor: valuation, cyclicality, dividend history); the judge checks presence, not phrasing.
- **Source quality**: sources consulted are authoritative for the claim type, not merely
  first-retrieved.

Judge discipline, non-negotiable (resolved, #27): versioned rubric + judge version recorded in
every result, and —

- **Pinned judge: Sonnet 5**, invoked via the Agent SDK on the Claude Max subscription (no API
  spend anywhere in the judge path, per #25). Rubric-checking is within Sonnet-tier capability;
  it is light on the shared quota the SUT trials also consume; and a tier below the likely SUT
  partially mitigates self-preference bias — further blunted by verdicts flagging rather than
  gating.
- **Pinning policy**: the pin moves only when **forced** (Sonnet 5 retired/unavailable via the
  SDK) or on **calibration failure** (persistent disagreement with SME verdicts). Every move,
  either kind, pays the same price: recalibration on sampled transcripts, judge-version bump in
  result rows, and pre/post-move judge scores treated as non-comparable (trend lines reset). No
  elective upgrades — a calibrated judge is an asset paid for with SME time.
- **Call shape**: one judge call per judged trial, returning a structured verdict with separate
  score + justification per rubric dimension (groundedness, coverage, source quality). The
  results store holds **per-dimension verdict rows regardless of call structure**, so a later
  split into per-dimension calls is a judge-version bump, not a redesign. Split trigger:
  calibration shows judge dimension scores moving in lockstep where the SME's don't, uncured by
  rubric rewording.
- **Which trials get judged**: every trial that passes its deterministic outcome gates.
  Gate-failed trials skip the judge — their prose quality cannot change any result. Judge volume
  thus scales naturally with k.
- **Calibration, three-part**: (a) bootstrap pass at Phase 3, tuning the rubric until SME
  (Dhawal) and judge mostly agree; (b) recalibration sample on any judge- or rubric-version bump;
  (c) steady-state spot-checks of **passing** verdicts (~3 per 10 judged runs, rate tunable) so a
  too-lenient judge cannot fail silently. Flagged verdicts continue to reach the SME
  automatically.
- **Budget: structural policy only, no hard numeric cap.** The principle: judge cost must stay
  small relative to trial cost. Today's math: 3 judge-graded tasks (R3, C4, C5) × ≤3 gate-passing
  trials = **≤9 Sonnet 5 calls per full run** plus calibration samples — minor next to the agent
  trials. If judged tasks ever multiply, that is an explicit amendment moment.

Judge verdicts below threshold **flag**, they do not gate; research quality is subjective enough
that a human sees the transcript before it counts as a failure.

### 6.4 Verdict composition

Each task's result is: gate verdicts (outcome graders) → pass/fail; track metrics (trajectory
quality + proxies: tool calls, turns, tokens, latency, cost per task) → compared across SUT
versions; flags → human review queue. A task can pass its gate and still flag ("right plan, ugly
path").

## 7. Suites: Regression vs Capability

**Regression suite** — the DCA loop, which works end-to-end today:

- each stage as an isolated task (import; theme+review; promotion; plan generation; approval),
  plus the full chain task
- the negative/invariant tasks from §5.3 — these are regression from day one, because the
  grounding invariant already holds and must never regress
- expectation ~100% pass^k; any drop blocks adopting the change (model/prompt/skill) that caused it

**Capability suite** — the frontier:

- the one-time-buy flow (fundamentals screening → eligibility → one-time recommendation lines),
  written *now*, expected to start low
- multi-source research synthesis tasks (theme brief with cited evidence across several
  instruments)
- each new skill adopted under ADR 0005 ships with its capability tasks — ratified as
  [ADR 0006](../../adr/0006-skills-ship-with-capability-eval-tasks.md) (#28). Adopting a skill is
  a capability claim: the adopting change adds ≥1 capability task per workflow the skill
  orchestrates. Tasks grade **workflows, not skills** — they never invoke the skill directly and
  they outlive it; the skill's value (or harm) shows as pass-rate deltas on its workflow's tasks.
  Tasks must exist and run; passing is not required — the frontier starts low by design. Per-task
  bar: definition (unambiguous prompt, fixture, outcome graders) **plus one witnessed run**
  against the current stack with the skill loaded (graders execute, transcript saved, pass
  irrelevant); golden transcripts are deferred to the task's migration-to-regression moment.
  Bounded carve-out: a skill is exempt only if it invokes no mutating tools and produces no
  durable artifacts, and the exemption is **explicitly declared** in the adoption record (silence
  is not an option); one mutation step anywhere voids it — exempt skills stay indirectly measured
  via the workflow tasks they operate inside. Authoring constraint (from #25): the Agent SDK
  ignores SKILL.md `allowed-tools` frontmatter — tool restriction belongs in the runner's
  `allowed_tools` config. Shipping a skill also adds its runtime files to the materialization
  list (§2).

**Migration and saturation policy**: a capability task passing ~100% across k trials and two SUT
versions moves to regression. A regression suite passing 100% for a long stretch is not "done" —
it is saturated as a signal for improvement, and the capability suite needs new tasks. Version
everything so movement is auditable: task set, fixtures, rubrics, judge model, harness — every
result row records all five versions.

## 8. Metrics & Reporting

### 8.1 pass^k policy and run triggers (resolved, #30)

- **k=3 on every triggered run — no k=1 smoke tier in the gate.** Economics are controlled by
  cutting *frequency* (adoption boundaries only), not *statistical power* (k). k=1 cannot see the
  failure mode the suite exists to catch: a change degrading a money-adjacent task from 100% to
  70% reliability still passes a k=1 smoke 70% of the time — k=1 only catches hard breaks, the
  cheap kind.
- **Trigger: adoption boundaries, hash-detected.** The regression suite runs before adopting a
  change to any versioned SUT component (model pin, skill set, prompt surface); intermediate
  edits during iteration never trigger it. A change is SUT-changing **iff it changes the §8.3
  prompt hash or the model pin** — no per-edit relevance judgments ("does this touch an evaluated
  flow?"), which rot into silent regressions. Hash unchanged → no run, regardless of diff size.
  Tool-layer Python stays out: pytest owns L0 determinism (§12), and tool changes that matter
  surface as fixture/harness version bumps, which re-baseline results anyway.
- **Why per-boundary, not release-only**: the suite's contract is blocking *the change that
  caused* a drop (§7). Release-only k=3 surfaces drops after several stacked changes, forcing a
  quota-burning bisect that costs more than the skipped runs. Capacity (per #25): a full pass^3
  run ≈ one moderate interactive coding session on the 5-hour window; a few adoption
  boundaries/week ≈ 2–4 sessions of quota — affordable on Max 5x.
- **Carve-outs**: (a) hand-run single-task k=1 trials during development are debugging, not
  gates, and are never recorded as verdicts; (b) capability tasks stay **pass@k** — one good
  synthesis demonstrates the capability exists — so k=3 cost lands only on the regression suite,
  the small stable set.
- **Escape hatch**: if quota pressure materializes in practice, amend k or the trigger as an
  explicit, data-backed decision (same pattern as the #27 budget policy). No pre-emptive k=1
  tier for a problem that doesn't yet bite.

### 8.2 Per-run report

One row per task — gate verdict per trial, track-metric deltas vs the previous SUT version, flags
with links to transcripts. Aggregates per suite. The v1 report reads run dirs directly — trivial
at ~20 tasks × 3 trials.

### 8.3 Results: files are the source of truth (resolved, #29)

Tasks and results live in `evals/` **in this repo**: one commit pins task-set + SUT versions
together, fixture scripts import the `tests/fixtures` machinery directly, and ADR-0006 skill
adoptions ship their tasks in the same PR as the skill.

- **Run artifacts**: `evals/results/runs/{run_id}/` per run — `meta.json` (SUT description:
  model, prompt hash, skill set; plus task/fixture/harness/rubric+judge versions and
  timing/cost), one transcript JSONL per trial (§9), and `verdicts.jsonl` appended by
  grade/re-grade passes. Immutable once written; each run dir is a self-contained, portable
  artifact. Because re-grading (§9, requirement 5) makes verdicts *derived* data, any database
  over them is logically a cache.
- **The prompt hash** is computed over exactly the materialized runtime surface (§2): the files
  the materialization list names, as copied into trial dirs.
- **Query layer: lazy, derived SQLite.** `evals/results/results.db` is added only when cross-run
  queries hurt; rebuilt from run dirs by one command; never written directly, never
  authoritative — no migration discipline, deletable anytime.
- **Commit boundary**: committed — `evals/harness/`, `evals/tasks/` (incl. per-task `golden/`
  witnessed-run and golden transcripts: task-definition material per ADR 0006), `evals/fixtures/`
  (scripts only, §5.2 — materialized DBs are build artifacts). Gitignored — `evals/results/`
  wholesale. Run history is local-only; what git preserves is reproducibility, not results.

## 9. Harness Requirements

Contract only; the webinar's "even a Python script" is the right ambition. The harness must:

1. **Materialize isolated trials**: per-trial ephemeral temp dir; fixture DB and workspace copied
   in; the runtime surface (runtime CLAUDE.md, skills, MCP config) copied in per the
   materialization list (§2); `FINANCE_HUB_DB`/`FINANCE_HUB_WORKSPACE` pointed at it;
   `FINANCE_HUB_NOW` set to the task's `now` for frozen-fixture tasks and left unset for
   live-replay tasks (§5.2). Only transcripts and verdicts persist into the run dir (§8.3); the
   trial dir itself is disposable.
2. **Run the SUT headless behind a runner seam** (resolved, #25 — full analysis in
   [runner-choice.md](runner-choice.md)): the primary runner is the **Claude Agent SDK (Python)**
   — in-process, typed message objects for every turn/tool_use/tool_result, per-trial control of
   `cwd`, `env`, `mcp_servers`, `setting_sources`, `model`, `max_turns` — funded by the Claude
   Max subscription (no API spend). A thin CLI-headless runner is kept behind the same seam as a
   comparison/debug variant. Trials must not load settings from the live repo —
   `setting_sources` is restricted to the trial dir, which is the contamination the
   materialization list exists to prevent (§2). Capture the complete transcript as JSONL.
3. **Run trials concurrently** without violating isolation.
4. **Apply graders via a registry**: `grade(transcript, db_path, workspace, task) → {grader_id,
   role: gate|track|flag, verdict, detail}` — plain Python functions registered once, mirroring the
   tool-registry pattern the repo already uses.
5. **Persist transcripts and support re-grading**: graders re-run against stored transcripts
   without re-running trials, so grader iteration is cheap and grader bugs are fixable
   retroactively.
6. **Emit the §8 report** and append to durable results.

Explicitly *not* harness v1: CI wiring, dashboards, A/B infrastructure, production telemetry.

## 10. Seed Task List (v0 target: ~20 tasks)

Regression:

| id | workflow | sketch |
|---|---|---|
| R1 | planning | Import real-shape Fidelity CSV fixture; verify snapshot rows + as_of extraction |
| R2 | research | Create theme, map 3 instruments, review each with conviction+note |
| R3 | research | Write instrument thesis note; verify note stored and linked |
| R4 | strategy | Promote approved candidates; verify explicit versioned snapshot |
| R5 | planning | Generate DCA plan from ready fixture; full §6.1 assertion set |
| R6 | planning | Approve a valid draft; verify status transition + memo artifact |
| R7 | chain | Full CSV→approved-plan chain from the README quickstart |
| R8 | negative | Provider unavailable → no invented prices; gap reported |
| R9 | negative | Stale data fixture → degraded output mode, honestly presented |
| R10 | negative | Failing readiness → no approval attempted |
| R11 | negative | Conviction-without-note rejection handled correctly |
| R12 | negative | Research task does not mutate strategy state |

Capability:

| id | workflow | sketch |
|---|---|---|
| C1 | market-data | Fetch fundamentals for candidate; verify stored rows + provenance |
| C2 | planning | One-time-buy eligibility screen over fundamentals fixture |
| C3 | planning | Mixed DCA + one-time plan; bucket math and evidence refs |
| C4 | research | Multi-instrument theme brief with cited evidence (judge-graded) |
| C5 | research | Source supersession workflow: replace stale source, note updated |
| C6 | chain | Research→promotion→plan for a *new* theme from scratch |
| C7 | negative | One-time buy requested with missing fundamentals → refused with gap |
| C8 | skill | First adopted ADR-0005 skill exercised end-to-end (placeholder) |

Each of these must be sharpened into an unambiguous prompt + reference solution during Phase 0 —
this table is a coverage map, not final task text.

## 11. Rollout Plan

- **Phase 0 — task collection (no code).** Grilling: done (#25–#30). Write 10–20 tasks from §10
  with real prompts and reference solutions: run each manually against the current stack, save
  the transcript as the golden reference (under the task's `golden/`, §8.3), and note where
  success criteria were ambiguous (fix the task, not the grader). This phase alone produces
  value: it is a structured audit of what the system actually does. It also starts the
  line-by-line audit splitting today's root CLAUDE.md into runtime surface vs dev scaffolding
  (§2).
- **Phase 1 — harness MVP.** One regression task end-to-end: fixture materialization, Agent SDK
  runner, transcript capture, outcome graders only, minimal report. Proves the seams. Lands the
  `FINANCE_HUB_NOW` front door (§5.2), the materialization list, and the runtime CLAUDE.md in its
  decided home (§2).
- **Phase 2 — trajectory + breadth.** Trajectory graders (incl. deterministic groundedness),
  re-grading from stored transcripts, the full regression suite, pass^3.
- **Phase 3 — judge + calibration.** Research-prose rubrics, pinned judge, first calibration pass
  against SME judgment.
- **Phase 4 — capability frontier.** One-time-buy tasks live; saturation/migration policy in
  effect; skills ship with eval tasks.

Standing habit from Phase 1 onward: **read transcripts every run.** Graders are verified by
reading, failures must feel fair, and grader bugs (rigid matching, bypassable checks) are found by
eyes, not by more graders.

## 12. Out of Scope

- Building the harness (this document is its spec).
- Public model benchmarking (MMLU/SWE-bench-style comparisons) — we evaluate *our* stack, not
  models in the abstract.
- Production monitoring, A/B testing, user-feedback pipelines — single-user system, no prod fleet.
- Re-testing L0 determinism that pytest owns.
- Ingestion-workflow evals (parked with the ingestion slice itself).

## 13. Resolved Questions (grilling outcomes)

Every question the original draft left open was resolved through the grilling tickets (map #24);
each ticket's `## Resolution (user-ratified …)` comment is the authoritative record. Summary and
where each landed in this spec:

1. **Runner** — resolved
   ([#25](https://github.com/DhawalAg/finance-hub/issues/25)): Claude Agent SDK (Python) as
   primary runner, thin CLI-headless comparison variant behind the same seam; funded by the
   Claude Max subscription. Full analysis: [runner-choice.md](runner-choice.md). Folded into §9.
2. **Clock seam** — resolved
   ([#26](https://github.com/DhawalAg/finance-hub/issues/26)): `FINANCE_HUB_NOW` env override
   installing a fixed clock through the existing `Clock` seam; frozen-instant semantics;
   fail-fast validation; task-level `now` declarations; live-replay exception; loud activation
   log. Folded into §5.1–§5.2.
3. **Judge model + budget** — resolved
   ([#27](https://github.com/DhawalAg/finance-hub/issues/27)): pinned Sonnet 5 via the Agent SDK;
   move-only-when-forced pinning; one call per judged trial with per-dimension verdict rows;
   gate-passing trials only; three-part calibration; structural budget, no hard cap. Folded into
   §6.3.
4. **Skill DoD policy** — resolved
   ([#28](https://github.com/DhawalAg/finance-hub/issues/28)): confirmed and recorded as
   [ADR 0006](../../adr/0006-skills-ship-with-capability-eval-tasks.md) — skills ship with
   capability eval tasks graded on workflows; definition + witnessed-run bar; bounded,
   explicitly-declared no-mutation carve-out. Folded into §7.
5. **Task/results home** — resolved
   ([#29](https://github.com/DhawalAg/finance-hub/issues/29)): `evals/` in this repo; files-first
   results (`evals/results/runs/{run_id}/`, immutable) with a derived, rebuildable SQLite index;
   `evals/results/` gitignored wholesale. Folded into §8.3.
6. **pass^k economics** — resolved
   ([#30](https://github.com/DhawalAg/finance-hub/issues/30)): k=3 on every triggered run, no
   k=1 smoke tier; triggers are adoption boundaries detected by prompt-hash/model-pin change;
   runtime surface vs dev scaffolding separated via a checked-in materialization list; two
   CLAUDE.md sets. Folded into §2, §3, §8.1, §8.3, §9.
