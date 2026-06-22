# Finance Hub Context

Finance Hub is a finance-only agent tool repo. The runtime is intentionally small: plain Python
functions register once, then become callable through both the `finance` CLI and the MCP server.
Finance behavior belongs under `src/finance_hub/`; durable specs live under
`docs/requests/finance/`; raw source notes live under `docs/notes/finance-corpus/`.

## Current Build State

The codebase is still a skeleton. It has the CLI/MCP/tool-registry spine, a SQLite connection helper,
and placeholder package boundaries for ingestion, market data, research, and strategy. Domain tools
and finance-owned migrations have not landed yet.

The first product workflow being sharpened is a grounded deployment recommendation loop: CSV-supplied
portfolio state, explicit deployable cash, research candidates, and market-data evidence feed a
reviewable plan for DCA and one-time buys. Live account integrations come later.

## Domain Vocabulary

- **Agent**: the reasoning layer. It explores, asks questions, writes prose, and chooses when to call
  tools. It must not invent prices, metrics, budget facts, or allocation math.
- **Tool**: deterministic Python behavior exposed through the registry, CLI, and MCP.
- **SQLite store**: the durable owner of structured finance facts, relationships, snapshots, and
  deterministic tool results.
- **Markdown note**: the durable owner of research prose, theses, briefs, and explanatory material.
- **Ingestion**: statement import and normalization into budget evidence.
- **Historical-surplus evidence**: reconciled budget evidence from ingestion. It is an input to later
  deployable-cash policy decisions, not deployable cash by itself.
- **Research**: theme discovery, instrument research, cited evidence, and candidate review.
- **Candidate**: an instrument or theme that research has evaluated but strategy has not yet adopted.
- **Strategy**: user-approved, versioned allocation intent.
- **Promotion**: an explicit user-confirmed handoff that snapshots approved research candidates into
  strategy state.
- **Sleeve**: a strategy allocation bucket with target weight and eligible instruments.
- **Holdings**: current positions. They are planner inputs, not research state.
- **Portfolio state**: the current holdings/cash/account snapshot supplied to the planner. It may come
  from CSV in v1 and from live account integrations later.
- **Portfolio snapshot**: an immutable portfolio-state import with an `as_of` time, source adapter, and
  source file/provenance. Deployment recommendations reference one snapshot, never a mutable account
  view.
- **Deployable cash**: the explicit user-approved dollar amount available for a plan in v1, regardless
  of where the cash currently sits. Historical-surplus evidence, brokerage cash, savings cash, reserves,
  and obligations are future inputs to a capital-policy layer, not automatically deployable.
- **Market data acquisition**: provider adapters, daily OHLCV bars, price envelopes, cache/freshness,
  and provenance.
- **Market data analytics**: derived metrics, aggregates, screens, event-response analytics, and
  simulations built on stored market-data facts.
- **Price envelope**: the narrow consumer-facing projection of a stored market-data observation:
  value, currency, field, date, source, grade, and freshness.
- **Deployment recommendation**: a reviewable plan for allocating deployable cash across DCA and
  one-time buys, grounded in portfolio state, research evidence, market-data evidence, and strategy.
  It does not execute trades.
- **Advisory-only plan**: a generated plan result that can produce research/review outputs but cannot
  produce dollar-denominated deployment drafts or approval-ready deployment output until account-state
  blockers are resolved.
- **Evidence reference**: a lightweight pointer from a generated plan or memo to the stored evidence it
  used. It cites existing price, metric, fundamental, research-note, or source records; it does not
  duplicate the evidence payload.

## Source Of Truth

The canonical durable spec map is `docs/requests/finance/README.md`.

Source notes under `docs/notes/finance-corpus/00-inbox/` are retained for provenance and decision
history. They are not implementation contracts. When a note conflicts with a durable spec, the durable
spec wins unless an ADR says otherwise.
