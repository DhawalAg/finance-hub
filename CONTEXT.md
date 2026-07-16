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

## Source Of Truth

Finance behavior belongs under `src/finance_hub/`. Durable specs live under
`docs/requests/`, with `docs/requests/README.md` as the canonical spec map. ADRs live
under `docs/adr/`.

Source notes under `docs/notes/finance-corpus/00-inbox/` are retained for provenance and decision
history. They are not implementation contracts. When a note conflicts with a durable spec, the durable
spec wins unless an ADR says otherwise.

GitHub Issues are the implementation tracker. Keep this file as the shared language and context map;
put slice-level status in issues and detailed behavioral contracts in request specs.
