# Finance Hub — Spec Map

**Status:** Working architecture map
**Updated:** 2026-05-31

This is the durable map for the finance-hub specification set. The final deliverable is this
overview plus four implementation specs under `docs/requests/`.

## Product Flow

```text
INGESTION ──▶ historical-surplus evidence ──▶ capital composition ┐
RESEARCH ───▶ approved candidates ──────────▶ versioned strategy ├──▶ deployment plan
MARKET DATA ▶ prices + metrics ───────────────────────────────────┘
```

The four specs separate user commitments and engineering ownership:

| Spec | Owns | Produces | Status |
|---|---|---|---|
| [Finance ingestion](../finance-ingestion/spec.md) | Statement import, canonical budget facts, reconciliation, historical-surplus evidence | Reconciled budget evidence | Finalized Slice 1 contract on `finance-ingestion-spec` (`55b58a9`); merge/rebase pending in this worktree |
| [Finance research](../finance-research/spec.md) | Theme discovery, instrument research, cited evidence, candidate review | Approved research candidates + cited markdown / static-HTML readouts | Active sharpening pass |
| [Finance strategy](../finance-strategy/spec.md) | Explicit promotion, versioned strategy, holdings input, capital composition boundary, deterministic deployment planning | Reviewable deployment plan | Extraction + sharpening pending |
| [Finance market data](../finance-market-data/spec.md) | Price-provider seam, price persistence, metrics, deferred provider activation | Grounded prices and quantitative inputs | Scaffold migration + sharpening pending |

## Boundary Decisions

1. **Research and strategy are separate.** Discovery changes research state only. It never silently
   changes the planner-eligible universe.
2. **Promotion is explicit.** A user-confirmed action snapshots approved research candidates into a
   versioned strategy.
3. **Ingestion does not over-claim deployable capital.** Slice 1 produces reconciled
   `historical_surplus` evidence. A later capital-composition step combines evidence with liquidity,
   reserves, obligations, and explicit overrides.
4. **Market data is a shared subsystem, not a separate user workflow.** Research and planning consume
   grounded prices / metrics through narrow provider seams.
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
  contract; research annotates tickers, market data prices them, and strategy snapshots approved
  selections.
- Layer boundaries use narrow, versionable inputs and outputs: reconciled budget evidence, approved
  candidates, grounded prices / metrics, and immutable strategy versions.
- Add fields and tables when a demonstrated workflow needs them. Avoid speculative abstractions,
  vendor-shaped core models, and duplicated state.
- Put provider-specific logic behind adapters. Persist provenance so a later implementation can
  replace a provider or enrich a model without rewriting downstream behavior.
- Prefer additive migrations and immutable snapshots where historical interpretation matters.

## Supporting Material

The files under [`notes/finance-corpus/00-inbox`](../../../notes/finance-corpus/00-inbox/) remain
working notes, decision history, and source material. They are not the final implementation
contracts. As each spec is sharpened, durable decisions move into the corresponding
`docs/requests/finance-*` document.
