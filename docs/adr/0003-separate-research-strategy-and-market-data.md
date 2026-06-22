# ADR 0003: Separate Research, Strategy, And Market Data

## Status

Accepted

## Context

The early finance notes mix discovery, strategy authoring, holdings, prices, metrics, and deployment
planning. That makes it too easy for agent judgment to silently mutate investment state.

## Decision

Keep these boundaries explicit:

- Research produces candidates and cited evidence.
- Strategy is a user-approved, versioned allocation contract.
- Promotion from research to strategy is explicit and user-confirmed.
- Market data is a shared subsystem that exposes grounded price envelopes and later metrics.
- Deployment planning is deterministic arithmetic over strategy, deployable capital, holdings, and
  market-data reads.

## Consequences

Discovery can evolve without changing planner-eligible instruments. Provider changes and analytic
metrics stay behind market-data seams. Allocation changes require an explicit strategy handoff.
