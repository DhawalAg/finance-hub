# Finance Market Data — Acquisition Spec

**Status:** Active build (L0–L1); build line drawn (§5) — Slice 1 = A, Slice 2 = B
**Updated:** 2026-06-21
**Home package:** `src/finance_hub/`

The acquisition half of the [market-data subsystem](./spec.md): turn external provider responses into
grounded, provenance-stamped daily market observations, then expose consumer-sized price envelopes.
The planner sees `finance.prices(...)` plus the `price_overrides` escape hatch, not vendor APIs or raw
bar payloads. The shared layer stack and the seam to [analytics](./analytics.md) live in the
[overview](./spec.md); this spec details **L0 (providers)** and **L1 (stored observations)**.

---

## 1. Responsibility

This spec owns:

- the `PriceProvider.fetch_daily_bars(...)` seam that normalizes provider bars, plus the
  `finance.prices(...)` seam and `price_overrides` escape hatch that supply grounded current prices to
  deployment recommendations;
- `fin_price_bars` — daily OHLCV history with `close` as the planner anchor and `adj_close` as the
  return-math convenience field, so analytics has a local series and deployment recommendations can
  persist the exact price they used separately;
- the provider adapters, configuration, secrets, caching, retries, and operational logging — so vendor
  choices stay reversible and the planner/research layers never see a vendor-specific API;
- the canonical daily OHLCV plus **`close` / `adj_close`** decision (§3), which analytics consumes but
  does not own.

It does **not** own metrics, aggregates, or any analysis surface (those are [analytics](./analytics.md));
strategy/holdings/plan arithmetic ([strategy](../strategy/spec.md)); or discovery/theses
([research](../research/spec.md)).

---

## 2. Provider seams & activation ownership

Consumer specs declare the grounded data they need; **this layer owns provider adapters,
configuration, secrets, caching, retries, and operational logging.** Planner and research read stable
seams, not vendor APIs.

```text
Provider adapter seam (L0 → L1):
PriceProvider.fetch_daily_bars(tickers: list[str], *,
                               start: date | None = None,
                               end: date | None = None) -> list[DailyBarEnvelope]

Consumer read seam (L1 → planner / research):
finance.prices(tickers: list[str], *,
               as_of: date | None = None,
               price_field: "close" | "adj_close" = "close",
               max_age_minutes: int = 1440,
               price_overrides: dict | None = None) -> dict[ticker, PriceEnvelope]
```

- Free **yfinance** implementation first. Use daily bars (`interval="1d"`, `auto_adjust=False`) so the
  adapter can normalize raw OHLCV plus adjusted close. Swap to Polygon / Massive or another paid price
  implementation later by registering a new implementation and selecting by config/param — **no
  planner change.**
- Free **EODHD** implementation first for the compact v1 `FundamentalsProvider`. It supplies
  screening-grade stock fundamentals and ETF fundamentals while the product loop is still being
  ironed out. Use **Alpha Vantage** as the fallback when EODHD's 20-request/day free tier is
  exhausted. Swap to FMP or a paid provider only when the free-tier pair becomes the bottleneck.
- Provider adapters write normalized bars to `fin_price_bars`; consumers read price envelopes derived
  from those bars. The planner never receives a raw vendor payload or a bare scalar.
- Callers accept cache within `max_age_minutes` (default `1440` = 1 day). Once the snapshot loop is
  active, the active universe refreshes at least daily after market close; market-calendar smarts can
  later distinguish "stale" from "market was closed."
- On miss/failure: **interactive callers fail loud**, naming the missing tickers so the agent retries
  with `price_overrides`; **scheduled runs log-and-continue** to `fin_fetch_log` so one bad ticker
  can't abort a snapshot. That log is also the reliability trip-wire counter.
- Intraday / `last` is outside v1. The system runs on completed daily sessions; add an intraday seam
  only if a workflow proves that stale close prices are not enough.

`DailyBarEnvelope` carries the stored bar fields (`ticker`, `session_date`, `open_micros`,
`high_micros`, `low_micros`, `close_micros`, `adj_close_micros`, `volume`, `currency`, `source`,
`first_fetched_at`, `last_refreshed_at`). `PriceEnvelope` is the consumer-sized projection:

```json
{
  "ticker": "ANET",
  "value_micros": 123450000,
  "currency": "USD",
  "price_field": "close",
  "session_date": "2026-06-03",
  "source": "yfinance",
  "grade": "screening",
  "last_refreshed_at": "2026-06-04T12:00:00Z",
  "is_override": false,
  "stale": false
}
```

### The provider landscape (what each seam buys, and its grade)

| Provider (seam) | Vendor | Gives | Grade |
|---|---|---|---|
| `PriceProvider` | yfinance → Polygon / Massive | daily OHLCV bars; consumer price envelopes expose `close` or `adj_close` | prices are reliable |
| `FundamentalsProvider` | EODHD → Alpha Vantage → FMP | compact stock fundamentals, ETF fundamentals / holdings / allocation, statements, ratios, analyst **estimates** where available | **screening only unless filing-grounded** |
| `FilingsProvider` | edgartools (SEC EDGAR) | 10-K/10-Q/8-K/Form 4, XBRL statements | **primary source — ground truth** |
| `EarningsProvider` | FMP | earnings calendar / dates | reliable (replaces flaky free dates) |
| `CorporateActionsProvider` | (later) | splits, dividends | folded into `adj_close` until we track cost basis |

Two standing rules from [`data-source-comparison.md`](../../../notes/finance-corpus/00-inbox/data-source-comparison.md):
aggregator **statements** (EODHD, Alpha Vantage, FMP, etc.) are directional/screening only — ground
any thesis-critical financial number in **edgartools** primary source; and **never mix two vendors in
one time series** (adjustment methodology differs), which is why `source` is part of the
`fin_price_bars` key.

### The graded-provenance envelope (the read contract)

Grade is not only a property of a *provider* — it must **ride with every quantitative value** the
subsystem hands a consumer, all the way to the dossier cell. So the read contract is an *envelope*, not
a bare number:

```json
{ "value": 28.5, "source": "fmp", "grade": "screening", "as_of": "2026-05-30" }
```

- **grade** ∈ `decision` (primary source — edgartools/EDGAR filings) | `screening` (aggregator —
  EODHD/Alpha Vantage/FMP, or agent-read web). Price-derived values are `screening` (reliable, but not
  primary-source ground truth); only filing-sourced figures are `decision`.
- **source** + **as_of** are the provenance; for stored bars, `session_date` is the as-of date and
  `last_refreshed_at` records the latest adjustment refresh.
- A **composite's grade = the lowest grade of its inputs** (a Value/Growth score built on EODHD,
  Alpha Vantage, or FMP numbers is `screening`).

This is the literal mechanism of the north star — a number cannot cross a seam without its source and
grade attached — and it is what makes multi-source composition (the analytics "pie", see
[analytics §2.3](./analytics.md)) safe: each cell self-identifies, so a decision-grade 10-K figure sits
honestly next to a screening-grade EODHD, Alpha Vantage, or FMP ratio. `fin_metrics` and the compact v1
fundamentals cache carry these fields; **bare numbers never cross a seam.**

### Activation policy

Start free for price bars and compact fundamentals: **yfinance** for `PriceProvider`, **EODHD** for
`FundamentalsProvider`, **Alpha Vantage** as the fallback runner, and **SEC / edgartools** for
`FilingsProvider` verification.
Revisit the price implementation when daily-bar fetches fail often, adjusted/unadjusted semantics
become hard to trust, analytics/backfill needs exceed yfinance reliability, or a workflow needs
intraday / production-grade market data. Polygon / Massive is the first named paid price-data upgrade
candidate.

Fundamentals are now part of the v1 deployment-recommendation workflow because one-time-buy
eligibility needs compact valuation/fundamental context. Preserve CSV/manual fundamentals as an
override and bootstrap path, but start with EODHD so the product can be used before paying for a
broader feed. Switch to Alpha Vantage once EODHD's free tier of 20 requests/day is exhausted. Move
from the free-tier pair to FMP, a paid provider, or another fundamentals provider only when the free
rate limits block normal usage, ETF fields are still missing, stock fundamentals miss too many
valuation fields, or manual gaps become common enough to slow product iteration. FMP is the broader
paid bundle candidate; EODHD remains the cleaner stock + ETF fundamentals candidate. Add other
providers only when a named research or market-data workflow needs repeatable filing-grounded
extraction, earnings-calendar automation, analyst estimates, intraday backtesting, real-time
news/sentiment, or filing surveillance at scale. The
[instrument deep-dive dossier](../../../notes/finance-corpus/00-inbox/ticker-deep-dive-target-experience.md)
is **one such concrete trigger** (among several): its L3/L4 lenses are the first named, worked workflow
that justifies turning on `FilingsProvider` (edgartools, decision-grade) then `FundamentalsProvider`
(screening unless filing-grounded). **Before activating any adapter, run a sharpening pass** — confirm
the current API shape and commercial terms, then specify the schema enrichment, migrations,
configuration, secrets, cache policy, retry policy, and failure reporting it requires.

---

## 3. Storage model — daily OHLCV, `close` / `adj_close`, and what we keep locally

The single most important modelling decision in the subsystem. Stored here; consumed by analytics.

- **OHLCV** — store the provider's daily open, high, low, close, and volume when supplied. Slice 1
  still returns the planner's closing-price view; storing the full daily bar is nearly free and avoids
  a later migration when charts, daily ranges, or event windows need it.
- **`close`** — raw, unadjusted regular-session close. The **immutable fact**. Reconcilable against a
  brokerage statement, reproducible intraday, what you'd actually pay. **The planner/valuation uses
  `close`.**
- **`adj_close`** — vendor back-adjusted for splits/dividends; **retroactively re-adjusted** over time,
  so it is allowed to refresh and is stamped with `last_refreshed_at`. The industry standard for
  *return* math. **The metrics layer (analytics) uses `adj_close`.**

Persist prices as integer micro-dollars (`PRICE_SCALE = 1_000_000`) after parsing provider values
through `Decimal`. Do not persist provider floats. Volumes are integer shares.

### Why store our own at all (vs. re-querying the API), strongest first

1. **Point-in-time decision audit.** Deployment history must reconcile against the prices actually used,
   so deployment recommendations persist their exact price inputs separately. `fin_price_bars` is the
   normalized analytical cache those decisions usually read from.
2. **Our own consistent metrics.** A gap-free series computed our way, immune to a vendor changing
   methodology or coverage.
3. **Provider independence.** If yfinance breaks or we switch to Polygon / Massive, accumulated
   history survives.
4. **Cost / rate-limit efficiency.** Local reads are instant and free.
5. **Captures the un-backfillable.** Observed snapshots and decision-time metrics can't be
   reconstructed after the fact.

But **don't over-hoard**: deep history for a rare backtest is *lazily fetched on demand and cached*
(`finance.backfill(...)`, far future), not eagerly dumped. Two roles, one table.

### Local storage policy (by data type)

"Store the entire financial dataset of a ticker" is the wrong default. There is **no bulk
fetch-everything tool** — each provider seam (§2) lazily fetches-and-caches its own slice, and
research's `instrument_brief` composes a *read* view over whatever is grounded. What we keep locally is
governed by one rule, generalizing the price reasoning above:

> **Store locally when the data is (a) immutable point-in-time *and* decision-grade, (b) needed
> point-in-time for audit/metrics — with refresh metadata or revision history where appropriate, or
> (c) hot *and* rate-limited. Lazily cache on first real use otherwise. Never eagerly bulk-hoard a
> whole ticker, and never treat restated aggregator data as durable truth.**

| Data | Mutates? | Store locally? | Where / status |
|---|---|---|---|
| Daily OHLCV / `close` | no once final for the session | **Yes** | `fin_price_bars` (active) |
| `adj_close` | yes (retroactive re-adjust) | **Yes, refreshable with timestamp** | `fin_price_bars` (active) |
| Deep price history | no | **Lazy** cache on first need | `finance.backfill()` (far future) |
| Corporate actions | no | Yes, when cost-basis matters | deferred table |
| **Filings (edgartools, as-filed)** | no | **Yes — cache** (primary source + SEC rate-limit hygiene) | `FilingsProvider` cache (research-era) |
| Statements / ratios (aggregator) | yes (restated) | **Cache for convenience, not as truth** — stamp source + vintage | `fin_fundamentals` cache (v1 for compact screening pack; EODHD first) |
| Analyst estimates (FMP) | yes (revised) | Point-in-time snapshot **only if** tracking revisions; else on-demand | deferred |
| Earnings / ex-div dates | yes (tentative→confirmed) | Yes — as occurrences | research `fin_events` (manual now) |
| Company profile / metadata | slow | Minimal only | `fin_instruments` (shared) |
| News | — | No — cite as a source if used | research `fin_research_sources` |

Two consequences worth stating:

- **Filings are the strongest store-candidate after prices** — immutable primary source, decision-grade,
  and caching doubles as SEC rate-limit hygiene. Structured facts → SQLite; document *bodies* (the 10-K
  itself) → a local file cache, deferred until URL durability or auditability becomes a real problem.
- **Aggregator fundamentals are the trap.** Cache EODHD / Alpha Vantage / FMP statements for
  convenience, but never let the stored copy become the durable truth — stamp `source` + vintage and
  keep any decision-grade claim pointed at the filing.

This is **policy plus a narrow v1 build**: `fin_price_bars` and the compact `fin_fundamentals`
screening cache are active for the deployment-recommendation workflow. Broader provider caches are
shaped only when their seam activates (§2 activation policy).

---

## 4. Data model

`fin_price_bars` is built in the price slice; `fin_fetch_log` is built with the snapshot slice.
`fin_metrics` is **owned by [analytics](./analytics.md)** and shown there. The compact
`fin_fundamentals` screening cache is active for one-time-buy eligibility, with EODHD as the default
free runner, Alpha Vantage as the fallback runner, and [provider-comparison](./provider-comparison.md)
owning the replacement bakeoff if either becomes a bottleneck. Finance owns these via the
finance-owned migration table
(`fin_schema_migrations`, per ingestion M1 — **not** global
`PRAGMA user_version`, since `hub.db` is shared), with FK + `CHECK` + indexes and
`PRAGMA foreign_keys = ON` per connection.

```sql
-- L1 — built in the price slice. One canonical bars table; snapshots and lazy backfill both write here.
CREATE TABLE fin_price_bars (
  ticker            TEXT NOT NULL,
  session_date      TEXT NOT NULL,      -- trading day this price belongs to (YYYY-MM-DD)
  open_micros       INTEGER,
  high_micros       INTEGER,
  low_micros        INTEGER,
  close_micros      INTEGER NOT NULL,   -- raw, unadjusted close; planner/valuation anchor
  adj_close_micros  INTEGER,            -- vendor-adjusted; refreshable for return math
  volume            INTEGER,
  currency          TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  source            TEXT NOT NULL,      -- 'yfinance' | 'fmp' | ...  — NEVER mix sources in one series
  first_fetched_at  TEXT NOT NULL,
  last_refreshed_at TEXT NOT NULL,
  PRIMARY KEY (ticker, session_date, source)
);
-- fin_prices (latest-only cache the planner's first slice referenced) is just a view/query over the
-- newest session_date per ticker in fin_price_bars — no separate table needed.

-- Operational log — built with the snapshot slice. Drives the >10% reliability trip-wire.
CREATE TABLE fin_fetch_log (
  id           INTEGER PRIMARY KEY,
  ticker       TEXT,
  attempted_at TEXT NOT NULL,
  source       TEXT,
  ok           INTEGER NOT NULL,   -- 1 success / 0 failure
  error        TEXT
);

-- Compact v1 fundamentals screening cache — EODHD first; Alpha Vantage fallback; replace only
-- through the provider bakeoff. Values are envelopes: source/as_of/grade are required, and gaps are
-- explicit.
CREATE TABLE fin_fundamentals (
  ticker       TEXT NOT NULL,
  field        TEXT NOT NULL,      -- revenue_growth, profitability, ps, forward_ps, ev_ebitda, ...
  as_of        TEXT NOT NULL,
  value        TEXT,               -- store as text to preserve Decimal/string-valued provider fields
  unit         TEXT,
  source       TEXT NOT NULL,
  grade        TEXT NOT NULL CHECK (grade IN ('decision', 'screening')),
  fetched_at   TEXT NOT NULL,
  source_ref   TEXT,               -- filing URL/accession/provider object id when available
  PRIMARY KEY (ticker, field, as_of, source)
);
-- Deferred, shape-on-activation: corporate-actions table and broader fundamentals/filings caches.
```

Notes:
- **`source` in the key** prevents silently mixing vendors in one series.
- **Manual `price_overrides` never write into this provider series.** They are recorded with the
  deployment recommendation that used them.
- **Decision-time audit is separate from the analytical series.** The planner's `fin_deployments`
  stores the exact prices used for a plan (the decision ledger); `fin_price_bars` is the analytical
  series. No "snapshot vs history" duplicate table.
- **This is not a vendor-revision journal.** If a completed-session raw OHLC value changes on refresh,
  log a mismatch for review. `adj_close_micros` may update because vendors recalculate historical
  adjustments after splits or dividends. Add `fin_price_bar_revisions` later only if historical
  vendor-vintage analysis becomes a demonstrated need.
- **`fin_instruments` stays a small shared reference contract** (research annotates, market data prices,
  strategy snapshots). Market data adds its own tables rather than widening it.

---

## 5. Lead decision (drawn) — where the build line sits

**Status: DRAWN 2026-05-31.** We re-examined four candidate stopping points *and* the framing itself.

**The candidates (A = narrowest → D):**

- **A** — on-demand daily-bar fetch plus price-envelope reads: `PriceProvider.fetch_daily_bars` +
  `fin_price_bars` daily OHLCV + `finance.prices(...)` / cache / `price_overrides`.
- **B** — A + `finance.snapshot()` (manual-trigger universe loop → append bars → `fin_fetch_log`).
- **C** — B + scheduling (launchd twice-weekly, DST, market calendar, missed-run backfill, monitoring).
- **D** — B + the L2 metrics step (returns/vol/drawdown/drift).

**The reframe (the axes weren't linear):**

- **A→B is a near-term spine, not a fork.** Per the corpus pacing rule, **A is the review checkpoint and
  B is the immediately-following slice.** A alone doesn't deliver "see what shifts" — it only writes a
  bar when you happen to fetch, so its series is incidental. B does, and is cheap on top of A.
- **After B the path forks into independently-triggered gates** — not a 3rd and 4th point on one line:
  - **Automate** (was C) — owned here; trigger: *manual snapshot cadence becomes a chore.*
  - **V1 metrics** — owned by [analytics](./analytics.md); trigger: *deployment candidate evidence
    needs return/risk/drawdown/52-week context.*
  - **Broader Analyze** (was D) — owned by [analytics](./analytics.md); trigger: *a named workflow needs
    metrics beyond the v1 evidence pack.*
- **The headline "what shifted" metric — allocation drift — is gated outside this subsystem.** Drift is
  an L3 aggregate needing holdings + strategy weights (later slices), and per-instrument metrics need a
  series of length ≥ 2. So "metrics in the first push" couldn't show drift on day one anyway.

**Decision:** draw the first-push line at **B**, reviewed at **A**.

- **Slice 1 = A** — the review checkpoint (planner unblocked; one end-to-end on-demand price path).
- **Slice 2 = B** — the snapshot loop, on the same write path; this is where "see what shifts" begins.
- **Automate** and broader **Analyze** stay parallel later gates behind their own triggers (§6); the
  narrow v1 metric pack is pulled forward by the deployment-recommendation contract.

Rationale: B delivers the "see what shifts" goal as early as honestly possible and is cheap on top of A;
**C** front-loads an operational tail the corpus explicitly parked; the old broad **D** would build
more compute than the first planner needs. The 2026-06-21 v1 adjustment keeps only the evidence metrics
required by candidate eligibility. Recorded in the ledger (§9).

---

## 6. Slices & build order

Drawn per §5: a near-term spine (Slice 1 → 2) plus two parallel later gates.

| Slice | Layer | Builds | Gate |
|---|---|---|---|
| **1 (A)** | L0 + L1 | `PriceProvider.fetch_daily_bars` (yfinance), `fin_price_bars` daily OHLCV, `finance.prices(...)` consumer envelopes, on-demand daily-bar fetch + close envelope + persist/cache + `price_overrides`; interactive fail-loud. For deployment recommendations, fetch/store **1 year of daily bars when available**, with an explicit waiver for newer tickers/IPOs/ETFs. **Review checkpoint.** | now (planner needs it) |
| **2 (B)** | L0 + L1 | `finance.snapshot()` headless tool (manual trigger): universe → append bars → `fin_fetch_log`, log-and-continue. **"See what shifts" begins.** | right after Slice 1 |
| **Automate** | scheduling | `launchd` silent driver → `/schedule` narrative driver → reliability host (DST, market calendar, missed-run backfill, monitoring) | manual snapshot cadence becomes a chore |
| **V1 metrics** | L2 | required deployment evidence pack in `fin_metrics`: 1m/3m/6m/1y returns, volatility, max drawdown, current drawdown, 52-week-position context, and `SPY`-default benchmark context | v1 planner needs candidate eligibility evidence |
| **Analyze** | L2+ | broader metrics, aggregates, screens, event-response — see [analytics](./analytics.md) | after the v1 metric pack, when broader analysis has a named consumer (drift also needs holdings/strategy) |

Pure helpers (normalization, cache-age logic) are TDD'd outside the `@tool` wrappers; wrappers stay
thin (load → call pure fn → persist → return), mirroring the ingestion slice. **Stop after Slice 1 (A)
+ one end-to-end on-demand price path for review** before building the snapshot tool (corpus pacing
rule).

---

## 7. Correctness & edge cases

- **Price field:** consumer reads parameterize `price_field ∈ {close, adj_close}`; planner default
  `close`, metrics default `adj_close`. Do not expose `last` in v1 — intraday quotes break the
  completed-session model and are unnecessary for the current cadence.
- **Corporate actions (splits/dividends):** defer a corporate-actions engine. Safe because holdings are
  broker-sourced (post-split counts come in correct) and return math uses vendor `adj_close` (splits +
  dividends already folded in). Residual gap — raw `close` shows split discontinuities — handled by
  always preferring `adj_close` for return math. Reopen when we track cost basis / tax lots.
- **Currency / FX:** USD-only v1. Detect non-USD listings (suffixes `.L`, `.TO`, `.HK`) and reject at
  strategy-set time with a clear message.
- **Unresolved tickers:** interactive → fail loud, naming the offenders; scheduled → log-and-continue
  to `fin_fetch_log` + per-run summary.
- **Idempotency:** the `(ticker, session_date, source)` key makes a same-day re-run a no-op via upsert;
  running the snapshot twice must not double-write.
- **Point-in-time integrity:** raw OHLC for a completed session should not silently change; log a
  mismatch for review. `adj_close_micros` may refresh and `last_refreshed_at` records when.

---

## 8. Boundaries

**Always:**
- Every price a consumer shows traces to `fin_price_bars` / a `PriceEnvelope` / an explicit
  `price_overrides` — never model freehand.
- Stamp `source`, `first_fetched_at`, and `last_refreshed_at` on every stored bar; never mix vendors in
  one series.
- Only the L0 adapter touches a provider; everything downstream reads `fin_price_bars` directly or
  through `finance.prices(...)`.

**Ask first:**
- Activating a paid provider (FMP, EODHD, Polygon / Massive, etc.) or adding a heavier dependency
  (edgartools, provider SDKs) — confirm + sharpening pass. EODHD is the approved first free compact
  fundamentals adapter; Alpha Vantage is the fallback runner.
- Changing the `fin_price_bars` shape after the first bars are stored.

**Never:**
- Invent a price the tools can't source.
- Treat EODHD, Alpha Vantage, FMP, or any aggregator statement data as decision-grade (screening only
  — ground decisions in edgartools).
- Execute trades or place orders (inherited, absolute).
- Commit provider API keys, an EDGAR identity, or local SQLite contents.

---

## 9. Sharpening agenda & decision ledger

Work these like the research spec's block-by-block pass. The build line (§5) is the lead item;
everything else flows from it.

| # | Question | Lean | Status |
|---|---|---|---|
| **A1** | What daily market data do we store, and with what precision / revision semantics? | Daily OHLCV in integer micro-dollars; `close` is planner anchor; `adj_close` is refreshable; no override rows in provider series | **APPROVED** |
| **A2** | What is the provider seam shape now that we store more than price? | Provider adapters fetch daily bars; consumers read `PriceEnvelope`s via `finance.prices(...)`; no intraday/`last` in v1 | **APPROVED** |
| **D1** | Where is the build line — snapshot/metrics/scheduling in or out of the first push? (§5) | Line at **B**, reviewed at **A**; Automate/Analyze are parallel later gates | **DRAWN** |
| **D2** | `max_age_minutes` default + when to add market-calendar awareness | Daily refresh minimum; `max_age_minutes = 1440`; calendar logic later | **APPROVED** |
| **D3** | Provider defaults + exact trip-wires for paid upgrades | Start with yfinance for price bars, EODHD for compact fundamentals, Alpha Vantage as the spillover runner, and SEC/edgartools for filing-grounded verification. Move price data to Polygon / Massive only if daily bars fail often, adjusted/unadjusted semantics become hard to trust, analytics/backfill needs exceed yfinance reliability, or intraday / production-grade market data becomes necessary. Move fundamentals to FMP if the free-tier pair runs out, ETF gaps remain, stock valuation gaps remain, or manual gap-filling slows normal use. | **APPROVED** |
| **D4** | Snapshot universe definition (sleeve instruments ∪ holdings? research watchlist too?) | First snapshot universe is `approved strategy sleeve instruments ∪ current holdings`; research watchlist pricing stays on-demand unless a workflow needs routine quantitative readouts. | **APPROVED** |

### Decision ledger

| Date | Topic | Decision | Consequence |
|---|---|---|---|
| 2026-06-04 | D2 — daily refresh and cache freshness | Refresh the active market-data universe at least daily once the snapshot loop exists; set `max_age_minutes = 1440` for consumer cache reads; defer market-calendar-specific freshness rules. | Keeps the system current enough for planning without adding calendar/scheduler complexity before Slice B/Automate. |
| 2026-06-21 | D3 / D4 — provider escalation and snapshot universe | Keep yfinance as the v1 price provider; use EODHD as the first compact fundamentals provider, Alpha Vantage as the fallback runner, and SEC/edgartools as the decision-grade verification path; define the first snapshot universe as approved strategy sleeve instruments plus current holdings. | Closes the release-gate ambiguity: v1 can build the deployment evidence path without selecting a paid provider or refreshing the whole research watchlist. |
| 2026-06-04 | A2 — provider seam shape | Split the seam into provider ingestion (`PriceProvider.fetch_daily_bars`) and consumer reads (`finance.prices(...) -> PriceEnvelope`). Keep `last` / intraday outside v1. | Lets acquisition capture richer daily bars while planner/research consume a small stable envelope; avoids scalar-price coupling and premature intraday complexity. |
| 2026-06-04 | A1 — daily bars, precision, and revision semantics | Store daily OHLCV in integer micro-dollars; use raw `close` as the planner anchor; allow `adj_close` to refresh with `last_refreshed_at`; keep manual overrides out of the provider series; defer a vendor-revision journal. | Keeps Slice A broader than price-only without adding provider truthiness, float storage, or revision-history complexity. |
| 2026-05-31 | Split | Acquisition (L0–L1) split from analytics (L2–L6) into sibling sub-specs under `market-data/`. | Active price contract stays lean; analytics evolves separately. See [overview](./spec.md). |
| 2026-05-31 | `close` vs `adj_close` | Superseded by A1: `close` remains the planner anchor; `adj_close` remains the return-math field. | A1 extends this into full daily OHLCV and replaces `ingested_at` with `first_fetched_at` / `last_refreshed_at`. |
| 2026-05-31 | Store vs re-query | Accumulate our own `fin_price_bars` but lazily backfill deep history on demand rather than eagerly hoarding. | Decisions reconcile against prices actually used; quota stays cheap. |
| 2026-05-31 | Provider ownership | Adapters, secrets, cache, retry, and operational logging live here; consumers read stable seams. Free first; activate paid/new providers only on a named trigger after a sharpening pass. | Vendor choices stay reversible; planner/research never see a vendor API. |
| 2026-05-31 | Build line (D1) | First-push line drawn at **B** (snapshot loop), reviewed at **A** (on-demand price). Reframed the axes: A→B is the near-term spine; Automate (was C) and Analyze (was D) are parallel, independently-triggered later gates; drift is gated on holdings outside market-data. | Slice 1 = A (review gate), Slice 2 = B. Scheduling and metrics stay trigger-gated; §6 tightened. |
| 2026-06-21 | V1 metric exception to D1 | Deployment recommendations pull forward the narrow candidate evidence metric pack, while broader Analyze remains gated. | Candidate eligibility can cite stored metrics without turning v1 into a general analytics product. |
| 2026-05-31 | Local storage policy | Store by data type via one rule (immutable+decision-grade, or point-in-time-for-audit with refresh/revision metadata, or hot+rate-limited → store; else lazy-cache; never bulk-hoard or enshrine restated aggregator data). No bulk fetch-everything tool. | Filings are the strongest store-candidate after prices; aggregator statements are cache-only, never durable truth. See §3. |
