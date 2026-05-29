# Finance Hub — Data Pipeline Spec (sister to requirements-dump.md)

Last updated: 2026-05-28
Status: scaffold — most of this is open questions to sharpen as we build

This is the **data-fetching subsystem** the finance hub sits on. It is specced apart from
[requirements-dump.md](./requirements-dump.md) so the planner spec stays about *join logic*
and this stays about *getting clean, grounded numbers in*. The planner depends on it through
exactly one seam (**PriceProvider**) and one escape hatch (`price_overrides`).

## North star (inherited)

Every number the agent uses must trace back to imported data or a tool result, not model
freehand. This pipeline is the "imported data" side of that contract. **Tools fetch and
persist; the agent never invents a price.**

## What the lenses actually need (drives everything)

The pipeline should be built to the *narrowest* real need first and widened only when a lens
that needs more becomes active.

| Lens | Needs | When |
|---|---|---|
| **Deployment planner** (now) | current price per ticker (delayed OK) | first slice |
| Reporting (deferred) | earnings dates, day/period movers, dividends | after planner |
| Research (deferred) | fundamentals, filings, analyst/consensus | later |
| Simulation (far future) | historical price series, corporate actions | far later |

**Implication:** the first slice needs only `fetch(tickers) -> {ticker: last_price}`.
Everything below is scaffolding so the architecture doesn't block the wider needs.

## The PriceProvider seam (the one contract the planner sees)

```
fetch(tickers: list[str], *, as_of: date | None = None) -> dict[ticker, price]
```

- Free **yfinance-class** implementation now.
- Swap to a paid provider later by registering a new implementation and selecting it by
  config/param — *no planner change*.
- Results cached in `fin_prices`; callers can accept cache within `max_price_age_minutes`.
- On miss/failure, raise a clean error naming the missing tickers so the agent can retry
  with `price_overrides`.

## Open questions to sharpen (the real agenda)

These are the decisions we'll work through as we build. Nothing here is decided yet.

### A. Scope of fetched data
- A1. First slice = last price only? (assumed yes)
- A2. Which price field: last trade vs previous close vs adjusted close? (DCA → previous
  close or last is fine; adjusted matters for historical/backtest only)
- A3. Instrument types in scope: stocks + ETFs only for v1? (matches the strategy model)

### B. Source / provider
- B1. Confirm yfinance for the first slice, accepting it's unofficial + occasionally flaky.
- B2. The upgrade trigger: *what specifically* would make us pay — earnings-calendar
  reliability? fundamentals breadth? rate limits? Define the trip-wire now so the decision
  isn't vibes later.
- B3. Candidate paid tiers if/when triggered: Tiingo (~$10/mo EOD), FMP (~$22/mo
  fundamentals+earnings). Pick the *first* paid provider we'd reach for.
- B4. Python 3.14 reality check: yfinance/pandas wheels on 3.14 — if not ready, the
  `price_overrides` path keeps the planner working while we resolve the runtime.

### C. Cadence & freshness
- C1. On-demand at plan time only, or a scheduled refresh that pre-warms the cache?
- C2. `max_price_age_minutes` default — how stale is acceptable for a weekly/monthly
  cadence? (a day? an hour?)
- C3. If we add scheduled refresh: harness cron / `/schedule` vs an in-hub job. (Reporting's
  scheduled delivery would share this.)

### D. Storage & history
- D1. Keep only the latest price per ticker (cache), or accumulate a price *time series*?
  (Time series is the precondition for simulation/backtest; cheap to start hoarding now,
  costly to backfill later.)
- D2. Where: `fin_prices` (latest, decided) — add a `fin_price_history` table now or defer?

### E. Correctness edge cases
- E1. Corporate actions (splits, dividends): do they affect share counts / cost basis in
  `fin_holdings`? (Matters once holdings are real, not hypothetical.)
- E2. Currency / FX: USD-only for v1? Any non-US listings change this.
- E3. Tickers that don't resolve (delisted, typo, wrong exchange): fail loud vs skip.

### F. Reporting-era extensions (parked until reporting is active)
- F1. Earnings calendar source + "important dates in the coming week/day".
- F2. Movers / gainers / losers — needs at least previous-close vs last, possibly intraday.
- F3. Dividend calendar.

## Build note

Do **not** build B–F now. The first slice ships with the PriceProvider seam + yfinance +
`fin_prices` cache + the `price_overrides` escape hatch. This spec exists so each later need
slots into the seam instead of forcing a rewrite.
