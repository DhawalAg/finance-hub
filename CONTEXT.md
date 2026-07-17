# Finance Hub Context

Finance Hub is a finance-only agent tool repo. The runtime is intentionally small: plain Python
functions register once, then become callable through both the `finance` CLI and the MCP server.
It exists to keep finance facts, research evidence, strategy intent, and deployment-planning math
grounded in deterministic tools rather than model freehand.

## Current Shape

The v1 product target is a grounded deployment recommendation loop: CSV-supplied portfolio state,
explicit deployable cash, research candidates, market-data evidence, and an active strategy feed a
reviewable buy-only plan for DCA and one-time buys. Live account integrations, capital-policy
automation, trade execution, tax workflows, and account-location optimization come later.

The full DCA deployment recommendation pipeline is in place and usable end-to-end:

- **Runtime and data layer**: tool registry, SQLite store with migrations, research evidence layer,
  market-data evidence layer, portfolio-snapshot intake (Fidelity CSV adapter), and
  strategy-promotion model.
- **Deployment recommendation**: deterministic draft generation, output-mode degradation, readiness
  checks, approval, and memo artifacts.
- **Bootstrapping seam**: `.env` self-loading, lazy yfinance auto-wiring, `finance check` diagnostic,
  `finance.import_portfolio_csv` registered tool, MCP client setup docs, and README quickstart.

The current implementation frontier is the **live fundamentals HTTP client** (EODHD / Alpha Vantage).
It is the immediate next step — it unlocks one-time buys, which require fundamentals screening. DCA
flows run end-to-end without it.

## Language

### Runtime And Evidence Ownership

**Agent**:
The reasoning layer. It explores, asks questions, writes prose, and chooses when to call tools; it
must not invent prices, metrics, budget facts, or allocation math.

**Tool**:
Deterministic Python behavior exposed through the shared registry, CLI, and MCP server.

**SQLite store**:
The durable owner of structured finance facts, relationships, snapshots, and deterministic tool
results.

**Markdown note**:
The durable owner of research prose, theses, briefs, and explanatory material.

**Evidence reference**:
A lightweight pointer from a generated plan or memo to stored evidence. It cites existing price,
metric, fundamental, research-note, or source records; it does not duplicate the evidence payload.

### Research

**Research**:
Theme discovery, instrument research, cited evidence, and candidate review. Research changes research
state only; it never silently changes planner-eligible strategy state.

**Candidate**:
An instrument or theme that research has evaluated but strategy has not yet adopted.

**Research thesis**:
The cited markdown argument for why an instrument or theme belongs in the candidate universe.

### Strategy And Planning

**Strategy**:
User-approved, versioned allocation intent.

**Strategy version**:
An immutable strategy snapshot containing sleeves, target weights, eligible instruments, and explicit
caps for a draft, active, or archived strategy state.

**Promotion**:
An explicit user-confirmed handoff that snapshots approved research candidates into strategy state.

**Sleeve**:
A strategy allocation bucket with a target weight and eligible instruments.

**Deployment recommendation**:
A reviewable plan for allocating deployable cash across DCA and one-time buys, grounded in portfolio
state, research evidence, market-data evidence, and strategy. It does not execute trades.

**Advisory-only plan**:
A generated plan result that can produce research/review outputs but cannot produce dollar-denominated
deployment drafts or approval-ready deployment output until account-state blockers are resolved.

### Portfolio And Capital

**Holdings**:
Current positions. They are planner inputs, not research state.

**Portfolio state**:
The current holdings, cash, and account snapshot supplied to the planner. It may come from CSV in v1
and from live account integrations later.

**Portfolio snapshot**:
An immutable portfolio-state import with an `as_of` time, source adapter, and source file/provenance.
Deployment recommendations reference one snapshot, never a mutable account view.

**Deployable cash**:
The explicit user-approved dollar amount available for a plan in v1, regardless of where the cash
currently sits. Historical-surplus evidence, brokerage cash, savings cash, reserves, and obligations
are future inputs to a capital-policy layer, not automatically deployable.

**Ingestion**:
Statement import and normalization into budget evidence.

**Historical-surplus evidence**:
Reconciled budget evidence from ingestion. It is an input to later deployable-cash policy decisions,
not deployable cash by itself.

### Market Data

**Market data acquisition**:
Provider adapters, daily OHLCV bars, price envelopes, cache/freshness, and provenance.

**Market data analytics**:
Derived metrics, aggregates, screens, event-response analytics, and simulations built on stored
market-data facts.

**Price envelope**:
The narrow consumer-facing projection of a stored market-data observation: value, currency, field,
date, source, grade, and freshness.

**Fundamentals screening pack**:
Provider-backed valuation and business-context facts used as screening-grade evidence for candidate
review and one-time-buy eligibility.

### Evals

Terms for evaluating the agent. Mechanics — the prompt hash, suite triggers, grader tiers — live in
the agent-evals spec (`docs/requests/evals/spec.md`), which also defines the **system under test**
(SUT): the whole agent stack being evaluated — model, runtime surface, tool registry, MCP server,
and SQLite store.

**Task**:
One eval test case: a fixture, a prompt, a reference solution, and a set of graders. Written so two
competent reviewers would agree on what success means.

**Trial**:
One agent attempt at a task. Tasks run as multiple trials because the agent under test is
non-deterministic.

**Transcript**:
The complete record of a trial — every tool call, its arguments, its result, and all agent text —
persisted durably so graders can re-run without re-running the trial.

**Outcome**:
The durable state left behind by a trial: rows in the SQLite store and artifacts in the trial
workspace. Never the agent's claim that something happened — a plan is approved when the plan row's
status says so, not when the transcript says so.

**Grader**:
A function scoring one aspect of a trial; tasks compose multiple graders, each producing one verdict
plus detail. Distinct from candidate review, which is a research judgment about an instrument or
theme, not a score of an agent run.

**Suite**:
A named collection of eval tasks — distinct from the pytest suite, which tests the tools
deterministically. Two kinds: regression (should pass ~100%; a drop is a defect) and capability
(expected to start low; measures the frontier).

**Gate / Track / Flag**:
The three verdict roles a grader can play. Gate fails the trial (outcome wrong); Track records a
metric for cross-version comparison without failing (turns, tokens, trajectory quality); Flag routes
the transcript to human review instead of failing (subjective quality below threshold, suspicious
trace patterns).

**pass@k / pass^k**:
pass@k: at least one of k trials succeeded (fine for research exploration). pass^k: all k trials
succeeded (the bar for money-adjacent flows, where consistency is the product).

**Runtime surface**:
The deployed agent's prompt surface — the runtime CLAUDE.md, shipped skills, and MCP config under
`runtime/` (ADR 0007). It is part of the system under test and all a trial ever loads. Not the
Python tool runtime, which is code versioned by the repo itself.
_Avoid_: runtime (bare, when the prompt surface is meant)

**Dev scaffolding**:
The development-process prompt surface — root CLAUDE.md, `docs/agents/`, triage and process docs.
The factory, not the product; it never enters a trial.

**Materialization list**:
The checked-in manifest under `evals/` naming every runtime-surface file the harness copies into a
trial directory; the exact input to the prompt hash. A file not on the list never enters a trial.

**Adoption boundary**:
The moment before a change to a versioned system-under-test component (model pin, skill set, prompt
surface) is adopted. The regression suite runs at adoption boundaries, not on every edit.

## Source Of Truth

Finance behavior belongs under `src/finance_hub/`. Durable specs live under
`docs/requests/`, with `docs/requests/README.md` as the canonical spec map. ADRs live
under `docs/adr/`.

Source notes under `docs/notes/finance-corpus/00-inbox/` are retained for provenance and decision
history. They are not implementation contracts. When a note conflicts with a durable spec, the durable
spec wins unless an ADR says otherwise.

GitHub Issues are the implementation tracker. Keep this file as the shared language and context map;
put slice-level status in issues and detailed behavioral contracts in request specs.
