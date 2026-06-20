# Finance Hub — Spec Map

**Status:** Working architecture map
**Updated:** 2026-06-04

This is the durable map for the finance-hub specification set. The final deliverable is this
overview plus four implementation specs under `docs/requests/`.

The executable code now lives in the installable `src/finance_hub/` package. Specs, plans, TODOs,
and design docs stay request-scoped under `docs/requests/finance/`.

## Product Flow

```text
INGESTION ──▶ historical-surplus evidence ──▶ capital composition ┐
RESEARCH ───▶ approved candidates ──────────▶ versioned strategy ├──▶ deployment plan
MARKET DATA ▶ daily bars + price envelopes + metrics ─────────────┘
```

The four specs separate user commitments and engineering ownership:

| Spec | Owns | Produces | Status |
|---|---|---|---|
| [Finance ingestion](./ingestion/spec.md) | Statement import, canonical budget facts, reconciliation, historical-surplus evidence | Reconciled budget evidence | Finalized Slice 1 contract |
| [Finance research](./research/spec.md) | Theme discovery, instrument research, cited evidence, candidate review | Approved research candidates + cited markdown / static-HTML readouts | Sharpening decisions recorded |
| [Finance strategy](./strategy/spec.md) | Explicit promotion, versioned strategy, holdings input, capital composition boundary, deterministic deployment planning | Reviewable deployment plan | Extraction + sharpening pending |
| [Finance market data](./market-data/spec.md) | Shared market-data subsystem, split into [acquisition](./market-data/acquisition.md) (daily-bar provider seam, persistence, price-envelope reads, provider ownership) + [analytics](./market-data/analytics.md) (metrics, aggregates, analysis surfaces) | Grounded daily bars, price envelopes, and quantitative inputs | Acquisition active (build line drawn); analytics design-ahead |

## Boundary Decisions

1. **Research and strategy are separate.** Discovery changes research state only. It never silently
   changes the planner-eligible universe.
2. **Promotion is explicit.** A user-confirmed action snapshots approved research candidates into a
   versioned strategy.
3. **Ingestion does not over-claim deployable capital.** Slice 1 produces reconciled
   `historical_surplus` evidence. A later capital-composition step combines evidence with liquidity,
   reserves, obligations, and explicit overrides.
4. **Market data is a shared subsystem, not a separate user workflow.** Research and planning consume
   grounded price envelopes / metrics through narrow market-data seams.
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
  candidates, grounded price envelopes / metrics, and immutable strategy versions.
- Add fields and tables when a demonstrated workflow needs them. Avoid speculative abstractions,
  vendor-shaped core models, and duplicated state.
- Put provider-specific logic behind adapters. Persist provenance so a later implementation can
  replace a provider or enrich a model without rewriting downstream behavior.
- Prefer additive migrations and immutable snapshots where historical interpretation matters.

## Supporting Material

The files under [`notes/finance-corpus/00-inbox`](../../../notes/finance-corpus/00-inbox/) remain
working notes, decision history, and source material. They are not the final implementation
contracts. As each spec is sharpened, durable decisions move into the corresponding document under
`docs/requests/finance/`.
