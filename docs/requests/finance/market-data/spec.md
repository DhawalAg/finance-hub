# Finance Market Data — Subsystem Overview

**Status:** Split into two sub-specs; acquisition is the active build, analytics is design-ahead
**Updated:** 2026-06-04
**Home hub:** `hubs/finance/`

This is the index for the market-data subsystem. It does two distinct jobs, now specced separately so
the active contract stays lean while the deferred half evolves on its own:

- **[Acquisition](./acquisition.md)** — turn provider responses into grounded, provenance-stamped,
  daily OHLCV observations (L0–L1). **The active build.** Owns the `PriceProvider.fetch_daily_bars`
  seam, `finance.prices(...)` price-envelope reads, `fin_price_bars`, caching, retries, secrets, and
  operational logging — and is **where the build-now line is drawn** (lead decision, now drawn: line
  at B, reviewed at A).
- **[Analytics](./analytics.md)** — turn those stored facts into derived metrics, portfolio/theme
  aggregates, cross-sectional screens, event-response measures, and simulation (L2–L6). **Design-ahead
  and fully build-gated.** Owns `fin_metrics`, the metric taxonomy, and the scripts / notebooks /
  dashboards surfaces.

Decision history and the provider comparison remain in:

- [`data-pipeline-spec.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md)
- [`data-pipeline-answers.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
- [`data-source-comparison.md`](../../../../notes/finance-corpus/00-inbox/data-source-comparison.md)
- [`provider-comparison.md`](./provider-comparison.md)

---

## North star

*Every number traces to imported data or a deterministic tool result, never model freehand.*
Acquisition produces the imported data; analytics produces the tool results. The agent narrates and
explores; it never invents a price or a metric. Market data is a **shared subsystem, not a user
workflow** — the planner and research read narrow seams; the agent is the only frontend.

---

## Two jobs, one stack

Both jobs are layers of one stack. **Each layer reads only from the layers below it, writes its own
tables, and is reachable through a stable seam** — which is what makes a new metric, aggregate, or
provider an *additive* change rather than a rewrite. This diagram is the shared mental model; the
sub-specs detail their own layers and do not redraw it.

```text
 L6  Simulation / backtest        "what if I'd DCA'd this strategy for 2 years?"   ── far future  ┐
 L5  Event-response analytics     earnings reaction, [-5,+5] return, drift          ── deferred    │ ANALYTICS
 L4  Cross-sectional analytics    rank/screen/compare players within a theme        ── deferred    │ (analytics.md)
 L3  Aggregated metrics           sleeve & portfolio rollups, drift, concentration  ── deferred    │
 L2  Derived metrics              returns, vol, drawdown, momentum (per instrument) ── deferred    ┘
 ── seam: fin_price_bars ──────────────────────────────────────────────────────────────────────────
 L1  Stored observations          fin_price_bars (daily OHLCV + refreshed adj)      ── active      ┐ ACQUISITION
 L0  Providers (acquisition)      PriceProvider.fetch_daily_bars → yfinance | FMP   ── active      ┘ (acquisition.md)
        ▲ external world (Yahoo, FMP, SEC EDGAR, …)
```

| L | Layer | Owns | Reads | Spec | Status |
|---|---|---|---|---|---|
| **L0** | Providers | adapters, config, secrets, cache, retry, fetch log, provenance | external APIs | acquisition | **active** |
| **L1** | Stored observations | `fin_price_bars` daily OHLCV (+ later a fundamentals / corp-actions cache) | L0 | acquisition | **active** |
| **L2** | Derived metrics | `fin_metrics` per-instrument: return, vol, drawdown, momentum | L1 | analytics | deferred |
| **L3** | Aggregated metrics | sleeve / theme / portfolio rollups | L1, L2 + holdings/strategy | analytics | deferred |
| **L4** | Cross-sectional | screens, rankings, peer comparisons within a theme | L1, L2 | analytics | deferred |
| **L5** | Event-response | earnings/dividend reaction joined to bars | L1 + `fin_events` (research) | analytics | deferred |
| **L6** | Simulation | strategy what-ifs over deep history | L1 (lazy-backfilled) + strategy | analytics | far future |

---

## The seam between the two specs

`fin_price_bars` is the contract. **Acquisition writes it; analytics reads it.** Reads go strictly
downward — analytics never reaches back into a provider, and acquisition never depends on a metric.
The single most load-bearing modelling decision — store raw **OHLCV** with `close` as the planner
anchor and carry vendor **`adj_close`** for return math — spans both halves; its **canonical
statement lives in the [acquisition spec](./acquisition.md)** (it is stored there) and analytics
consumes it. No decision is duplicated across the two docs.

## Why split

- **Different lifecycles.** Acquisition is being built now (current closing price); every analytics
  layer is deferred behind a trigger. Mixing a live contract with an all-deferred catalogue blurs what
  is actually being built.
- **Different concerns.** Acquisition is ops-flavored (adapters, secrets, retries, rate limits,
  operational logging). Analytics is compute-flavored (metric math, surfaces, dependency stack).
- **Different dependency footprint.** Acquisition runs light; analytics pulls the heavy
  `pandas`/`numpy`/`jupyter` extra. The split mirrors a real packaging boundary.

The cost of the split — two docs sharing one contract — is paid down by keeping the shared stack and
the `close`/`adj_close` decision in exactly one place each (here and in acquisition, respectively).

## The build line (drawn)

Drawn 2026-05-31 in **[acquisition §5](./acquisition.md)**: the first-push line sits at **B** (the
`finance.snapshot()` loop), reviewed at **A** (on-demand closing price). The axes were also reframed —
**A→B is the near-term spine** (A is the review checkpoint; B is the next slice and where "see what
shifts" begins), while **Automate** (scheduling) and **Analyze** (metrics, in
[analytics](./analytics.md)) are **parallel later gates** behind their own triggers. Note the headline
"what shifted" metric — allocation drift — is gated on holdings/strategy *outside* this subsystem, so it
can't appear on day one.
