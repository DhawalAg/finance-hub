# Finance Market Data — Subsystem Overview

**Status:** Split into two sub-specs; acquisition and near-term analytics are being sharpened for the
deployment-recommendation workflow
**Updated:** 2026-06-21
**Home package:** `src/finance_hub/`

This is the index for the market-data subsystem. It does two distinct jobs, now specced separately so
the active contract stays lean while the deferred half evolves on its own:

- **[Acquisition](./acquisition.md)** — turn provider responses into grounded, provenance-stamped,
  daily OHLCV observations (L0–L1). **The active build.** Owns the `PriceProvider.fetch_daily_bars`
  seam, `finance.prices(...)` price-envelope reads, `fin_price_bars`, caching, retries, secrets, and
  operational logging — and is **where the build-now line is drawn** (lead decision, now drawn: line
  at B, reviewed at A).
- **[Analytics](./analytics.md)** — turn those stored facts into derived metrics, portfolio/theme
  aggregates, cross-sectional screens, event-response measures, and simulation (L2–L6). **The v1
  deployment evidence subset is active; deeper analytics remain gated.** Owns `fin_metrics`, the
  metric taxonomy, and the scripts / notebooks / dashboards surfaces.

Decision history and the provider comparison remain in:

- [`data-pipeline-spec.md`](../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md)
- [`data-pipeline-answers.md`](../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
- [`data-source-comparison.md`](../../../notes/finance-corpus/00-inbox/data-source-comparison.md)
- [`provider-comparison.md`](./provider-comparison.md)

---

## North star

*Every number traces to imported data or a deterministic tool result, never model freehand.*
Acquisition produces the imported data; analytics produces the tool results. The agent narrates and
explores; it never invents a price, metric, or fundamental. Market data is a **shared evidence
subsystem, not a user workflow** — the planner and research read narrow seams; the agent is the only
frontend.

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
 L2  Derived metrics              v1 evidence pack now; broader taxonomy later      ── active/v1   ┘
 ── seam: fin_price_bars ──────────────────────────────────────────────────────────────────────────
 L1  Stored observations          bars + compact fundamentals screening cache       ── active/v1   ┐ ACQUISITION
 L0  Providers (acquisition)      PriceProvider + selected FundamentalsProvider     ── active/v1   ┘ (acquisition.md)
        ▲ external world (Yahoo, FMP, SEC EDGAR, …)
```

| L | Layer | Owns | Reads | Spec | Status |
|---|---|---|---|---|---|
| **L0** | Providers | adapters, config, secrets, cache, retry, fetch log, provenance | external APIs | acquisition | **active** |
| **L1** | Stored observations | `fin_price_bars` daily OHLCV plus compact `fin_fundamentals` screening cache; later corp-actions cache | L0 | acquisition | **active/v1** |
| **L2** | Derived metrics | `fin_metrics` per-instrument: v1 return/risk/drawdown/52-week/benchmark evidence now; broader taxonomy later | L1 | analytics | **active/v1 subset** |
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

- **Different lifecycles.** Acquisition and the small v1 metric pack are being built now for deployment
  recommendations; broader analytics remain behind triggers. Mixing the live evidence contract with
  the deferred catalogue blurs what is actually being built.
- **Different concerns.** Acquisition is ops-flavored (adapters, secrets, retries, rate limits,
  operational logging). Analytics is compute-flavored (metric math, surfaces, dependency stack).
- **Different dependency footprint.** Acquisition runs light; analytics pulls the heavy
  `pandas`/`numpy`/`jupyter` extra. The split mirrors a real packaging boundary.

The cost of the split — two docs sharing one contract — is paid down by keeping the shared stack and
the `close`/`adj_close` decision in exactly one place each (here and in acquisition, respectively).

## The build line (drawn)

Drawn 2026-05-31 in **[acquisition §5](./acquisition.md)** and narrowed for the 2026-06-21 deployment
recommendation workflow: the first-push acquisition line sits at **B** (the `finance.snapshot()` loop),
reviewed at **A** (on-demand closing price). The v1 planner also pulls forward a small L2 evidence
pack from [analytics](./analytics.md): 1m/3m/6m/1y returns, volatility, max drawdown, current drawdown,
52-week-position context, and benchmark context defaulting to `SPY`, computed from the stored
`fin_price_bars` series and stored in `fin_metrics`. Broader **Analyze** work, scheduling, screens,
event-response analytics, simulation, and allocation drift beyond planner-owned weight impact remain
behind their own triggers.
