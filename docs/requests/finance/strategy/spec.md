# Finance Strategy & Deployment Planner — Working Spec

**Status:** Scaffold — extraction and sharpening pending
**Updated:** 2026-06-04

This is the durable destination for the strategy and deployment-planner contract. Detailed working
material currently lives in
[`requirements-dump.md`](../../../../notes/finance-corpus/00-inbox/requirements-dump.md).

## Responsibility

This spec will define:

- explicit promotion of approved [research](../research/spec.md) candidates;
- minimally versioned strategies, sleeves, target weights, and eligible instruments;
- the boundary around later `deployable_capital` composition;
- holdings as a planner input, with acquisition sharpened when that slice is activated;
- deterministic deployment-plan arithmetic over strategy, capital, holdings, and
  [market-data price envelopes](../market-data/acquisition.md);
- provenance, persisted plans, and planner-specific edge cases.

Research discovery does not mutate strategy state. Strategy authoring does not execute trades.

## Current Boundary Decision

A user-confirmed `finance.promote_to_strategy(...)` snapshots selected themes, target weights, and
approved instruments into a new immutable strategy version. The detailed table and tool contracts
will be sharpened in this spec rather than the research spec.
