# Finance Hub — Spec Map

**Status:** Working architecture map
**Updated:** 2026-06-21

This is the durable map for the finance-hub specification set. The current v1 product target is the
deployment recommendation workflow: CSV-supplied portfolio state, explicit deployable cash, research
candidates, and market-data evidence feed a reviewable buy-only plan.

The executable code now lives in the installable `src/finance_hub/` package. Specs, plans, TODOs,
and design docs stay request-scoped under `docs/requests/finance/`.

## Product Flow

```text
PORTFOLIO CSV + EXPLICIT DEPLOYABLE_CASH ─────────────────────────────┐
RESEARCH ───▶ candidates + cited evidence ─────▶ strategy promotion ──┤
MARKET DATA ▶ history + price envelopes + metrics + fundamentals ─────┤
STRATEGY ───▶ active version + DCA/one-time buckets ──────────────────┴──▶ deployment recommendation

INGESTION ──▶ historical-surplus evidence ──▶ capital composition ──▶ later replacement/enrichment
```

The four specs separate user commitments and engineering ownership:

| Spec | Owns | Produces | Status |
|---|---|---|---|
| [Finance ingestion](./ingestion/spec.md) | Statement import, canonical budget facts, reconciliation, historical-surplus evidence | Reconciled budget evidence for later capital composition | Finalized Slice 1 contract; parked as future capital-policy support |
| [Finance research](./research/spec.md) | Theme discovery, instrument research, cited evidence, candidate review | Candidates, theses, and cited evidence for planning | V1 support contract sharpened |
| [Finance strategy](./strategy/spec.md) | Portfolio/deployable-cash inputs, explicit promotion, versioned strategy, deterministic deployment recommendation | Reviewable deployment recommendation across DCA and one-time buys | Sharpened v1 contract |
| [Finance market data](./market-data/spec.md) | Shared market-data subsystem, split into [acquisition](./market-data/acquisition.md) (daily-bar provider seam, persistence, price-envelope reads, provider ownership) + [analytics](./market-data/analytics.md) (metrics, aggregates, analysis surfaces) | Grounded price history, price envelopes, metrics, compact fundamentals, and quantitative research inputs | Support contract for v1; next cleanup focus for evidence readiness |

## Agent-Ready Read Order

For future `/grill-with-docs`, `/to-prd`, and `/to-issues` work, read in this order:

1. [`CONTEXT.md`](../../../CONTEXT.md) and [`docs/adr/`](../../adr/) for vocabulary and durable architecture decisions.
2. This spec map for product flow, boundaries, and current status.
3. [`strategy/spec.md`](./strategy/spec.md) for the current v1 deployment recommendation contract.
4. Support specs only as needed for the evidence surfaces feeding that contract:
   [`market-data/spec.md`](./market-data/spec.md) for price, metric, and fundamentals evidence;
   [`research/spec.md`](./research/spec.md) for candidates, theses, citations, and promotion inputs.
5. Source notes under [`docs/notes/finance-corpus/00-inbox`](../../notes/finance-corpus/00-inbox/)
   only when provenance or unresolved decision history is needed.

## Boundary Decisions

1. **Research and strategy are separate.** Discovery changes research state only. It never silently
   changes the planner-eligible universe.
2. **Promotion is explicit.** A user-confirmed action snapshots approved research candidates into a
   versioned strategy.
3. **Ingestion does not over-claim deployable cash.** Slice 1 produces reconciled
   `historical_surplus` evidence. A later capital-composition step combines evidence with liquidity,
   reserves, obligations, and explicit overrides.
4. **Market data is a shared subsystem, not a separate user workflow.** Research and planning consume
   grounded history, price envelopes, fundamentals, and metrics through narrow market-data seams.
5. **The agent owns judgment; tools own durable facts and deterministic arithmetic.** No tool should
   turn prose or agent confidence into an allocation implicitly.
6. **Research readouts have one source of truth.** Markdown is the canonical portable artifact.
   Static HTML is generated from the same grounded brief model and is not edited independently.
   Generated readouts must carry visible **generated — do not edit** warnings.

## Modular Evolution Policy

Keep each layer independently evolvable without building a generalized platform up front:

- For the research knowledge base, preserve the canonical ownership rule:

  ```text
  Markdown owns research thinking.
  SQLite owns structured facts and relationships.
  Generated readouts combine both.
  ```

- Each spec owns its domain tables and behavior. Cross-layer writes happen only through explicit
  handoff tools such as `finance.promote_to_strategy(...)`.
- Shared concepts stay deliberately small. For example, `fin_instruments` is a shared reference
  contract; research annotates tickers, market data stores daily bars / price envelopes for them, and
  strategy snapshots approved selections.
- Layer boundaries use narrow, versionable inputs and outputs: reconciled budget evidence, approved
  candidates, grounded price envelopes / metrics, explicit deployable cash, and immutable strategy
  versions.
- Add fields and tables when a demonstrated workflow needs them. Avoid speculative abstractions,
  vendor-shaped core models, and duplicated state.
- Put provider-specific logic behind adapters. Persist provenance so a later implementation can
  replace a provider or enrich a model without rewriting downstream behavior.
- Prefer additive migrations and immutable snapshots where historical interpretation matters.

## Supporting Material

The files under [`docs/notes/finance-corpus/00-inbox`](../../notes/finance-corpus/00-inbox/) remain
working notes, decision history, and source material. They are not the final implementation
contracts. As each spec is sharpened, durable decisions move into the corresponding document under
`docs/requests/finance/`.

Generated HTML explainers and completed one-off conversion TODOs are intentionally not kept in the
active spec tree. Regenerate readouts from durable markdown when needed.
