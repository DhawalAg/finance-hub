# Finance Market Data — Analytics Spec

**Status:** Design-ahead; fully build-gated behind the acquisition build line
**Updated:** 2026-05-31
**Home hub:** `hubs/finance/`

The analytics half of the [market-data subsystem](./spec.md): turn the stored price facts into derived
metrics, portfolio/theme aggregates, cross-sectional screens, event-response measures, and simulation
(L2–L6). This spec is a **map, not a build list** — every layer here is deferred until a real workflow
triggers it, and the first one cannot start until the [acquisition](./acquisition.md) build line (its
§5) puts a bar series on the ground. It reads `fin_price_bars`; it never reaches back to a provider.

> **What "design-ahead" buys.** Each layer below slots into a slot that already exists in its consumer:
> the research `instrument_brief` / `theme_brief` carry optional `metrics` / `fundamentals` slots with
> availability metadata ([research §9](../research/spec.md)); the planner reads a `prices` seam. When a
> layer activates, it *fills a slot* — it does not reshape its consumer. That is the whole point of
> writing this before building it.

---

## 1. Responsibility

This spec owns:

- `fin_metrics` — derived quantitative facts computed **our way** from `fin_price_bars`, stored
  point-in-time so the metrics themselves form an analyzable series;
- the metric / aggregate / screen / event-response **taxonomy** (§2) and which layer each belongs to;
- the **analysis surfaces** (§3): headless scripts/tools, Jupyter notebooks, and (later) dashboards,
  and the rules that keep them composable;
- the **runtime & dependency boundary** (§4) — the heavy scientific stack as an optional extra.

It does **not** own price acquisition, the `close`/`adj_close` decision, or provider adapters (those
are [acquisition](./acquisition.md)); strategy/holdings ([strategy](../strategy/spec.md)); or event
*occurrences* — those are stored by [research](../research/spec.md)'s `fin_events`; this spec only
*joins* them to bars (L5).

---

## 2. The data taxonomy (L2–L6)

The catalogue of what can be computed, by layer. **A map of what's possible, gated on real need.**

### 2.1 Derived metrics (L2) — computed our way, per instrument

Recomputable from `fin_price_bars`, stored in `fin_metrics` **append-by-`as_of`** so the metrics form a
time series you can run second-order analysis over ("compute-theme drift has widened three snapshots
running"). All need **only prices** — no paid provider — and are exactly what the research
`instrument_brief.metrics` slot reads.

| Family | Metrics | Inputs | Notes |
|---|---|---|---|
| **Return / performance** | simple return over window (1d/1w/2w/1m/3m/6m/YTD/1y/since-inception), CAGR, cumulative series | `adj_close` | the base everything else builds on |
| **Risk** | realized volatility (annualized), downside deviation, max drawdown, current drawdown, drawdown duration | `adj_close` | windowed |
| **Trend / momentum** | momentum (12-1m, 3m), % off 52-week high/low, moving averages (20/50/200d) + crossovers | `adj_close` | |
| **Relative** | return / momentum **vs a benchmark** (SPY/QQQ), beta, relative strength | `adj_close` + benchmark bars | needs a benchmark ticker in the universe |
| **Risk-adjusted** | Sharpe-like (return/vol), Sortino | metrics above + risk-free rate | risk-free rate is a deferred input; note the assumption |

### 2.2 Aggregated metrics (L3) — rollups across instruments ("aggregated data")

Join L1/L2 with **holdings and strategy weights** (a narrow, explicit cross-layer read — never a silent
mutation). `fin_metrics` already carries `scope ∈ {ticker, sleeve, portfolio}` for exactly this.

| Scope | Metrics |
|---|---|
| **Sleeve / theme** | sleeve return, **allocation drift (current weight − target weight)** ← the planner's core "what shifted", sleeve volatility, theme-relative performance |
| **Portfolio** | total return & volatility, concentration (top-N weight, HHI), contribution-to-return, contribution-to-risk, pairwise correlations / correlation matrix, tracking error vs target |

Drift is the highest-value aggregate — it is the "see what shifts" signal the twice-weekly snapshot
exists to feed.

### 2.3 Cross-sectional analytics (L4) — compare players *within* a theme/universe

Two flavors: **price-derived screens** (momentum rank, drawdown rank, vol rank, relative strength vs
theme median) and — the user's most-wanted artifact — a **fundamentals valuation table**: peers compared
on P/S (TTM + forward), EV/EBITDA, gross margin, YoY revenue growth, plus a computed **Value/Growth
score**. This is the L4 lens of the
[instrument deep-dive dossier](../../../../notes/finance-corpus/00-inbox/ticker-deep-dive-target-experience.md)
(its DD-2/DD-3), and the "financial analysis of a theme's players" the research lens wants to **read**
but never compute itself (research §8: cross-player screens are a fast-follow once metrics exist).

**The surface is one tool:** `finance.compare(tickers, metrics)` — hand it an explicit peer list and a
metric set, get back a deterministic table. Peer selection is a *caller* input (theme co-members from
`fin_theme_instruments`, or user-supplied); analytics computes over the list it is handed, it does not
pick peers.

Three rules keep the table honest:

1. **A derived score is a tool computation, never agent freehand.** `Value/Growth = P/S ÷ rev-growth`
   is arithmetic over two numbers, so — like the planner's `compute_plan` — it must be computed by the
   tool from cited, graded inputs. The agent never eyeballs a ratio into the prose.
2. **Multi-source by design (the "pie"), graded per cell.** One table may draw each column from a
   different source — P/S from FMP (`screening`), segment revenue from a 10-K (`decision`), momentum
   from `fin_price_bars` — and **every cell carries its graded-provenance envelope**
   ([acquisition §2](./acquisition.md)). A composite's grade = the lowest grade of its inputs.
3. **Compose, don't blend.** Different *metrics* may come from different sources, but never average two
   sources into one "consensus" number, and never build a single price/return series from mixed vendors.
   Disagreement is shown with the decision-grade figure preferred — not mushed.

Output is a deterministic table surfaced into `theme_brief` / the instrument dossier, or rendered by a
script.

### 2.4 Event-response analytics (L5) — `fin_events` × `fin_price_bars`

Join research's event occurrences to our bars with **trading-session-aware** logic: next-session
return, `[-5,+5]`-session cumulative return, realized vol in the earnings window vs baseline, post-event
drift, peer reactions, theme-relative response. Use `adj_close` for returns; interpret the window using
the event's `timing` (before/after market). When sharpened, account for trading vs calendar days,
corporate actions, tentative vs revised dates, provider gaps, look-ahead bias, and survivorship bias.
**Do not persist simulation/analysis results as hand-authored markdown.**

### 2.5 Simulation / backtest (L6) — far future

What-if a strategy over deep (lazily backfilled) history: DCA backtest, strategy comparison, glidepath
simulation. Needs survivorship-aware history and the full corporate-actions story. Listed so the bars
table is shaped to support it (it already is — append-only, source-stamped).

---

## 3. The analysis surfaces — scripts, notebooks, dashboards

The layers above are *where computation lives*; the surfaces are *how a human/agent drives it* —
mirroring the hub's "one capability, many drivers" design. Three surfaces, each with a distinct,
non-overlapping job:

| Surface | Job | Character | Examples |
|---|---|---|---|
| **Headless scripts / tools** | repeatable, deterministic computation | reproducible, no LLM, venv-runnable via bash | `hub run finance.snapshot`, `finance.metrics(ticker, window)`, a `scripts/finance/theme_screen.py` |
| **Jupyter notebooks** | exploration, charting, hypothesis-forming | interactive, throwaway, read-only on stored data | "is compute drift widening?", correlation heatmaps, eyeballing a new metric before it's a tool |
| **Dashboards** (later) | at-a-glance composed views | generated, replaceable, no hand-editing | a static HTML portfolio/theme readout |

Three principles make these compose instead of collide:

1. **The database is the contract between surfaces.** Scripts/tools **write** `fin_price_bars` /
   `fin_metrics`; notebooks and dashboards **read** them. No surface fetches from a provider directly
   except through the acquisition L0 seam. This is what stops provider data (and vendor-specific quirks)
   from leaking into every notebook, and it's why a vendor swap touches one adapter, not fifty cells.
2. **There is a promotion path, exactly like research sources.** A notebook is ephemeral by default.
   When an exploration proves out a repeatable insight, **harden it into a script/tool/metric** (the
   same move as promoting an ad-hoc web result into a `fin_research_source`). Notebooks are where
   metrics are *born*; `fin_metrics` + a script is where they *live* once they earn it.
3. **Scripts are the production path; notebooks are the lab.** Anything that must be reproducible,
   scheduled, or relied on for a decision is a script/tool with tests. Notebooks stay out of the
   decision-grade path — their output is a hypothesis or a chart, not a persisted fact.

Dashboards come *after* there's something worth showing, and follow the research-lens rendering
convention: generated from the same grounded tool output, carry a visible **generated — do not edit**
warning, static (no JavaScript) to start. No dashboard work until at least L2 metrics exist.

---

## 4. Runtime & dependency boundary

The analytics stack pulls in heavy scientific dependencies (`pandas`, `numpy`, later
`matplotlib`/`jupyter`; `yfinance` is shared with acquisition). The core hub is intentionally light
(`anthropic`, `typer`, `mcp`). Keep them separate:

- **The analysis stack is an optional dependency group / extra** (e.g. `finance-analysis`), not a core
  runtime dep. The CLI, MCP server, and the budget-ingestion slice install and run without it. Tools
  that need it import lazily and fail with a clear "install the finance-analysis extra" message when
  it's absent — never a bare `ImportError`.
- **Scripts and notebooks share one venv** (managed with `uv`, matching the ingestion spec's
  `uv add --dev` / `uv run` convention). A metric eyeballed in a notebook and the same metric computed
  by a script resolve the same `fin_price_bars` and agree by construction.
- **Headless runs carry no shell profile.** A scheduled/`launchd` driver must be given any secrets
  explicitly via env file / plist, never committed.

---

## 5. Data model

`fin_metrics` is **owned here** but **built when the metrics slice (L2) activates** — the same
discipline research uses for `promote_to_strategy` (design the seam, defer the build). It reads
`fin_price_bars` (owned by [acquisition](./acquisition.md)). Finance-owned migration table,
FK/`CHECK`/indexes, `PRAGMA foreign_keys = ON` per connection — same conventions as acquisition.

```sql
-- L2 — designed now, built when the metrics slice activates. Append-by-as_of so metrics form a series.
CREATE TABLE fin_metrics (
  scope   TEXT NOT NULL,           -- 'ticker' | 'sleeve' | 'portfolio'
  key     TEXT NOT NULL,           -- ticker / sleeve name / 'TOTAL'
  metric  TEXT NOT NULL,           -- 'ret' | 'vol' | 'drift_pct' | 'drawdown' | 'momentum' | ...
  window  TEXT NOT NULL,           -- '1d' | '1w' | '2w' | '1m' | '3m' | ...
  as_of   TEXT NOT NULL,           -- trading day the metric is computed for
  value   REAL,
  source  TEXT,                    -- provenance: which bars / provider this was computed from
  grade   TEXT,                    -- 'decision' | 'screening' (price-derived = screening) — the envelope
  PRIMARY KEY (scope, key, metric, window, as_of)
);
```

Every row carries the **graded-provenance envelope** (`source`, `grade`, `as_of`; see
[acquisition §2](./acquisition.md)) so a metric never crosses a seam as a bare number. A composite's
`grade` is the lowest grade of its inputs.

**Stored vs. computed-on-read.** Frequently-read, point-in-time-meaningful metrics are *stored* in
`fin_metrics` (so they form their own analyzable series). Heavy, exploratory, or one-off metrics are
*computed on the fly* in scripts/notebooks from `fin_price_bars` and **not** persisted until they earn
it (the promotion path, §3). This keeps the table from accreting every experiment.

---

## 6. Build gating & proposed slices

This whole spec is the **Analyze gate** downstream of the acquisition build line
([acquisition §5](./acquisition.md), drawn 2026-05-31): the first push stops at the snapshot loop (B),
so **metrics are explicitly *not* in the initial slice** — they activate once a `fin_price_bars` series
has depth. Note allocation drift (the headline "what shifted" aggregate) additionally needs
holdings/strategy from later slices, so it lands in Slice B here, not Slice A.

The [instrument deep-dive dossier](../../../../notes/finance-corpus/00-inbox/ticker-deep-dive-target-experience.md)
is the first named consumer pulling these forward: its price/momentum context wants Slice A (L2
metrics), and its valuation-table lens wants the `finance.compare` table (Slice C, L4) on top of graded
fundamentals from acquisition.

| Slice | Layer | Builds | Gate |
|---|---|---|---|
| **A** | L2 | `fin_metrics` compute step (returns/vol/drawdown/momentum from `adj_close`); fills research `metrics` slot | the Analyze gate fires — a `fin_price_bars` series has depth |
| **B** | L3 | sleeve/portfolio aggregates (drift, concentration, contribution) | holdings + strategy slices are live |
| **C** | L4 | cross-sectional theme screens/rankings | metrics exist and a theme comparison is wanted |
| **D** | L5 / L6 | event-response analytics; simulation/backtest | `fin_events` active; deep history justified |

Pure metric math is TDD'd outside any `@tool` wrapper; wrappers stay thin (load bars → call pure fn →
persist/return), mirroring the ingestion slice.

---

## 7. Boundaries

**Always:**
- Every metric a consumer shows traces to `fin_price_bars` / `fin_metrics` / a provider response —
  never model freehand.
- Analysis surfaces read the stored tables; only the acquisition L0 adapter touches a provider.
- Returns use `adj_close`; valuation/share-count uses `close`.

**Ask first:**
- Adding the heavy analysis dependency group, or changing the venv/runtime boundary.
- Persisting a new metric family into `fin_metrics` (vs. leaving it computed-on-read).

**Never:**
- Invent a metric the tools can't compute from stored bars.
- Persist notebook/simulation output as hand-authored markdown decision facts.
- Hand-edit generated dashboards/readouts; regenerate them.

---

## 8. Sharpening agenda & decision ledger

These open only once the Analyze gate fires and L2 is on the build path ([acquisition §5](./acquisition.md)).
Recorded now so the design is ready.

| # | Question | Lean | Status |
|---|---|---|---|
| **N1** | Exact metric set + window definitions for the first `fin_metrics` slice | return + vol + drawdown + momentum over 1w/1m/3m | open |
| N2 | Benchmark ticker(s) for relative metrics, and how they enter the universe | SPY (+ QQQ for compute-heavy themes) | open |
| N3 | Risk-free rate source for risk-adjusted metrics | defer Sharpe/Sortino until a real need; note the assumption | open |
| N4 | Which metrics are stored vs. computed-on-read | store the cheap point-in-time set; compute heavy/exploratory on the fly | leaning (§5) |
| N5 | Vault/repo location + structure for `scripts/finance/` and notebooks | settle alongside the first real script | open |

### Decision ledger

| Date | Topic | Decision | Consequence |
|---|---|---|---|
| 2026-05-31 | Split | Analytics (L2–L6) split from acquisition (L0–L1) into sibling sub-specs under `market-data/`. | This spec evolves on its own; acquisition stays the lean active contract. See [overview](./spec.md). |
| 2026-05-31 | Surfaces | Three surfaces — scripts/tools (production, reproducible), notebooks (exploration, throwaway), dashboards (later, generated). The database is the contract between them; notebook insights are *promoted* into scripts/metrics. | Exploration and production stay separated; provider quirks don't leak into notebooks. |
| 2026-05-31 | Dependency boundary | Analysis stack (`pandas`/`numpy`/`jupyter`/…) is an optional extra, not a core dep; scripts + notebooks share one `uv` venv; lazy import with a clear "install the extra" error. | Core hub + CLI + budget slice stay light and installable without the scientific stack. |
| 2026-05-31 | Metric storage | Cheap point-in-time metrics → stored in `fin_metrics` (append-by-`as_of`); heavy/exploratory/one-off → computed on the fly until they earn persistence. | Metrics form their own analyzable series without persisting every experiment. |
| 2026-05-31 | L4 / `finance.compare` | L4 includes a fundamentals **valuation table** via `finance.compare(tickers, metrics)`. Derived scores (e.g. Value/Growth) are deterministic tool computations over cited, graded inputs; tables are **multi-source per-cell** (the "pie") with composite grade = min(inputs); **compose, don't blend**; never a mixed-vendor series. Peer set is a caller input. | Absorbs the dossier's DD-2/DD-3 and DDQ-1/DDQ-4 (§2.3). |
| 2026-05-31 | Graded-provenance envelope | Every quantitative value crossing a seam carries `{value, source, grade, as_of}`; `fin_metrics` gains `source`/`grade` columns; the deferred fundamentals cache carries them too. | Makes the north star structural and the multi-source pie safe. Canonical statement in [acquisition §2](./acquisition.md). |
