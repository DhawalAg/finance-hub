# Finance Hub — Agent Evals — Working Spec

**Status:** Draft; needs sharpening via `/grill-with-docs` before PRD synthesis
**Updated:** 2026-07-16
**Sources:** Anthropic webinar notes (`my-obsidian: 100-agentic/anthropic-webinars/ai-evals`),
[Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
(esp. the *Evaluating Research Agents* section)

This spec defines **what the finance-hub eval system must measure and how**, so a later
implementation pass can build the harness without re-deriving the design. It deliberately specifies
contracts (task model, grader tiers, suite policy, harness requirements) and defers implementation
choices to named open questions (§13).

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
model + system prompt / CLAUDE.md + skills (ADR 0005) + tool registry + MCP server + SQLite store
```

A trial exercises this stack end-to-end: a task prompt goes in, the agent runs until done, and the
graders inspect what durably happened. Changing any layer (model, prompt, skill, tool schema) is a
new SUT version and warrants a run.

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
- **The clock must be freezable.** Freshness bands and output-mode degradation depend on "now", and
  today the tool layer reads the real clock (`strategy/tools.py::_now`); only the yfinance provider
  accepts an injected clock. The harness needs a seam — e.g. a `FINANCE_HUB_NOW` env override
  honored by `_now()` — otherwise staleness-dependent tasks rot as real time passes. This is a
  small tool-layer change the eval work is allowed to request (§13).
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

Judge discipline, non-negotiable: pinned judge model + versioned rubric recorded in every result;
periodic calibration against the SME (Dhawal) — sample judged transcripts, compare verdicts,
recalibrate the rubric on disagreement. Judge verdicts below threshold **flag**, they do not gate;
research quality is subjective enough that a human sees the transcript before it counts as a
failure.

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
- each new skill adopted under ADR 0005 ships with its capability tasks — the skill's eval tasks
  are part of the skill's definition of done (proposed policy; confirm in grilling, §13)

**Migration and saturation policy**: a capability task passing ~100% across k trials and two SUT
versions moves to regression. A regression suite passing 100% for a long stretch is not "done" —
it is saturated as a signal for improvement, and the capability suite needs new tasks. Version
everything so movement is auditable: task set, fixtures, rubrics, judge model, harness — every
result row records all five versions.

## 8. Metrics & Reporting

- **pass^k (k=3 initially)** for regression, money-adjacent tasks — consistency is the product;
  this is a real portfolio.
- **pass@k** acceptable for capability research tasks, where one good synthesis demonstrates the
  capability exists.
- Per-run report: one row per task — gate verdict per trial, track-metric deltas vs the previous
  SUT version, flags with links to transcripts. Aggregates per suite.
- Results are durable and queryable (a small eval schema in SQLite or JSONL under `evals/results/`;
  decided at implementation). Every row carries: task id+version, fixture version, SUT description
  (model, prompt hash, skill set), harness version, rubric+judge version where applicable.

## 9. Harness Requirements

Contract only; the webinar's "even a Python script" is the right ambition. The harness must:

1. **Materialize isolated trials**: per-trial temp dir; fixture DB and workspace copied in;
   `FINANCE_HUB_DB`/`FINANCE_HUB_WORKSPACE` (and the frozen-clock seam) pointed at it.
2. **Run the SUT headless behind a runner seam**: launch the agent (Claude CLI headless with an MCP
   config pointing at the trial's server, or the Agent SDK — open question §13) with the task
   prompt; capture the complete transcript as JSONL. The runner is pluggable so SUT variants are
   comparable.
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

- **Phase 0 — task collection (no code).** Grill this spec. Then write 10–20 tasks from §10 with
  real prompts and reference solutions: run each manually against the current stack, save the
  transcript as the golden reference, and note where success criteria were ambiguous (fix the task,
  not the grader). This phase alone produces value: it is a structured audit of what the system
  actually does.
- **Phase 1 — harness MVP.** One regression task end-to-end: fixture materialization, headless
  runner, transcript capture, outcome graders only, minimal report. Proves the seams.
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

## 13. Open Questions (grilling agenda)

1. **Runner**: Claude CLI headless + MCP config vs Agent SDK? (Criteria: transcript fidelity,
   skill loading, cost of keeping it working.)
2. **Clock seam**: is a `FINANCE_HUB_NOW` override in `_now()` acceptable as a small tool-layer
   change, or should freshness-dependent tasks pin fixture timestamps relative to real now?
3. **Judge model + budget**: which pinned model, how many judge calls per run are acceptable?
4. **Skill DoD policy**: confirm that ADR-0005 skills must ship with capability tasks (proposed
   §7); if yes, record as an ADR amendment or new ADR.
5. **Task/results home**: `evals/` in this repo (assumed) vs separate repo; results in SQLite vs
   JSONL.
6. **pass^k economics**: k=3 triples cost per run — acceptable for the regression suite on every
   SUT change, or reserved for release decisions?
