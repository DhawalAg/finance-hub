# 0004 Use Canonical Portfolio Snapshots For Account State

Date: 2026-06-20

## Status

Accepted

## Context

The deployment recommendation workflow needs current portfolio state, but secure, free, real-time
Fidelity account access is not available for retail users. Fidelity CSV export is secure and free but
manual. Sanctioned OAuth-style account aggregation can be added later through paid providers. Browser
automation would require fragile login scraping and credential handling.

## Decision

Use immutable canonical portfolio snapshots as the planner input. V1 imports Fidelity positions CSV
through a `FidelityPortfolioCsvAdapter` into `fin_portfolio_snapshots` and
`fin_portfolio_positions`. Each deployment recommendation references one `portfolio_snapshot_id`.

Future live integrations must write the same canonical snapshot tables. Browser automation against
Fidelity is out of scope.

## Consequences

The first workflow is secure and free, but not real-time. Recommendations must carry `as_of` metadata
and stale-snapshot warnings. The planner is insulated from Fidelity CSV shape and from future account
sync providers.
