# Finance Hub — Data Pipeline: Answers & Decisions

Last updated: 2026-05-30
Status: living back-and-forth — companion to [data-pipeline-spec.md](./data-pipeline-spec.md)

> **⏸ PARKED (per the 2026-05-30 finance-ingestion design review, #7).** The operational/monitoring
> detail in this doc — scheduling mechanism (C3), the launchd/cron progression, DST handling, market-calendar
> checks, missed-run backfill, observability/alerting, retention — is **Slice-2+ (price snapshots)** and is
> **not to be built until the price-snapshot slice is active.** It informs the seam (so the architecture
> doesn't block it); it is *not* a build checklist. The active ingestion work is the budget slice, specced in
> [`docs/requests/finance-ingestion/spec.md`](../../../docs/requests/finance-ingestion/spec.md).

Working doc where we resolve the A–F open questions one at a time. Each item records:
**your call**, **my recommendation + why**, and the **resulting decision / todo**. Decisions
here feed back into the spec once settled.

Legend: ✅ decided · 🔄 needs one more input from you · 🅿️ parked

---

## A. Scope of fetched data

### A1 — first slice = last price only ✅
**Your call:** good for now.
**Decision:** first slice fetches one number per ticker. Everything else is scaffolding.

### A2 — which price field (parameterize, default to industry-prevalent) ✅
**Your call:** parameterize; default to the most prevalent, with reasoning.
**Recommendation:** parameter `price_field` ∈ `{close, last, adj_close}`, with **two
context-specific defaults** because the "prevalent" choice differs by use:

- **Planner / valuation → default `close`** (the official daily *regular-session close*,
  unadjusted). Why this over the alternatives:
  - `last` (live intraday trade) drifts every second the market is open → the same plan run
    twice in a day gives different share counts. Noise for a DCA/weekly horizon, and it
    breaks reproducibility (you want to *see what shifts* between runs, not chase ticks).
  - `adj_close` (back-adjusted for splits/dividends) is **not what you'd pay** and gets
    *retroactively re-adjusted* every time a new dividend/split lands — so a stored
    adj_close for a past day silently changes. Bad as a transactable reference and bad as a
    durable fact.
  - `close` is the actual closing price that day: immutable once the session ends,
    reconcilable against a brokerage statement, reproducible intra-day, and what virtually
    every EOD-oriented retail/long-horizon tool treats as *the* daily price. It's the
    honest "what it costs" number for a buy decision.
- **Analytics / returns layer → default `adj_close`.** This is the genuine industry standard
  for *return* and performance math (splits/dividends folded in → a continuous series).
  Used for the metrics layer in §D, never for "how many shares do I buy."

**Decision:** store **raw `close` as the immutable fact**; carry `adj_close` (vintage-stamped
with its ingest time) alongside for the analytics layer. Planner defaults to `close`; metrics
default to `adj_close`. This single split also cleanly resolves the §D adjustment headache.

### A3 — instrument types ✅
**Your call:** yes — stocks + ETFs.
**Decision:** v1 universe = stocks + ETFs (US). `instrument.type ∈ {stock, etf}`. Reject /
flag anything else for now (ties to E2/E3).

---

## B. Source / provider

### B1 — yfinance for the first slice ✅
**Your call:** OK.
**Decision:** yfinance is the first-slice `PriceProvider`. Verified installable on this
runtime (see B4).

> **Deeper dive:** a full FMP/Finnhub/Polygon/edgartools/sec-api comparison + cost-benefit +
> recommendation now lives in **[data-source-comparison.md](./data-source-comparison.md)**.
> Net of it: **FMP (~$22–50) as the workhorse + edgartools (free) as primary-source ground
> truth**; skip Polygon/Finnhub/sec-api until a specific trigger. The summary below stands.

### B2 / B3 — the provider landscape (you asked: what are my options, what to be wary of, who uses what)

Here's the map. Think of it as four tiers; users self-sort by *horizon* and *whether they
need fundamentals/real-time*.

**Tier 0 — Free / unofficial** (where we are)
- **yfinance** (Yahoo scraper): free; enormous coverage (stocks, ETFs, FX, indices, crypto);
  gives EOD + intraday + earnings dates + corporate actions + basic fundamentals.
  *Wary of:* unofficial (ToS gray area, no commercial use), no SLA, breaks when Yahoo changes
  its endpoints, IP rate-limiting, occasional missing/garbled fields, earnings dates often
  wrong. *Who uses it:* hobbyists, students, prototypes, personal dashboards — **us, now.**
- Also free-ish: stooq, Alpha Vantage free (25 calls/day — too tight), Twelve Data free tier.

**Tier 1 — Cheap paid, "serious individual"** (our likely upgrade)
- **Financial Modeling Prep / FMP (~$22/mo):** one vendor for prices + historical prices +
  **earnings calendar** + financial statements + ratios + analyst estimates. *Who:* solo
  builders / research-and-screener tools who don't want to stitch sources. **Best overall
  value for us** — covers the planner *and* the deferred reporting/research lenses from a
  single key.
- **Tiingo (~$30/mo individual):** clean, well-adjusted EOD price history + news + IEX
  intraday; **prices-first** (fundamentals are a third-party add-on). *Who:* quant/backtest
  builders who care more about pristine price history than fundamentals. Pricier than FMP and
  narrower for our needs, so it's the second choice, not the first.
- EODHD (~$20–60/mo), Twelve Data: similar, stronger *global* coverage.

**Tier 2 — Real-time / developer-grade**
- **Polygon.io** (~$30 starter → real money for full), **Finnhub** (free tier + ~$50/mo):
  real-time/intraday, websockets, news, alt-data. *Who:* algo traders, alerting tools,
  fintech startups. **Overkill for a weekly DCA plan.**

**Tier 3 — Broker-provided** (worth knowing, since you hold real positions)
- **Alpaca** (free IEX data with an account), **Interactive Brokers / Schwab APIs**: free,
  *official*, reconcilable data — and the same API can later *place and track orders*.
  *Who:* anyone who already has that brokerage. **Strategic note:** this is the one path that
  is free, official, AND could eventually close the loop from "plan" → "execute." If your
  brokerage has a decent API, it may leapfrog the paid data question entirely.

**Tier 4 — Institutional** (Bloomberg/Refinitiv/FactSet, $$$$): not relevant.

**What to be wary of across all of them:**
- ToS / commercial-use & redistribution limits (not an issue for single-user personal use,
  but real if this ever ships to others).
- Rate limits & quotas (free tiers throttle hard; matters once we run scheduled snapshots).
- **Adjustment methodology differs by vendor** — never mix sources within one time series, or
  your returns lie. (We stamp `source` on every stored bar for exactly this reason.)
- Survivorship/delisting coverage — matters only for honest backtests (far future).

**B2 — the trip-wire (define now so the upgrade isn't a vibe).** Move off free when **any**
of these fires:
1. **Reliability:** yfinance returns errors/empties on more than ~10% of scheduled snapshot
   runs over a rolling 2-week window. *(We'll know because the fetch log in E3 counts this.)*
2. **Reporting lens activates** and we need a *trustworthy earnings calendar* — yfinance's is
   notoriously unreliable.
3. **Analytics layer wants clean history** we don't have to babysit (consistent adjustment,
   no gaps).

**B3 — first paid provider to reach for: FMP (~$22/mo)** ✅. Updated after research
(2026-05-30): FMP is both cheaper than Tiingo (~$22 vs ~$30) *and* broader (prices + earnings
+ fundamentals + analyst estimates from one vendor), so a single key satisfies all three
trip-wire triggers with no source-stitching. Tiingo is the fallback only if we later want
pristine quant-grade adjusted price history above all else.

**Fidelity (you asked how to check): not viable as a data/execution API** ✅. Fidelity's APIs
target workplace / institutional / wealth-management partners — there is **no public retail
REST API** for a normal brokerage account comparable to the Schwab Developer Portal, Alpaca,
or IBKR. The only ways to touch a Fidelity account programmatically are screen-scraping,
browser automation, or third-party account aggregation (Plaid / Akoya / Yodlee, read-only) —
all less reliable than a dedicated data vendor, and none provide clean market data. **So the
Tier-3 "broker API leapfrogs the data question" path is closed for Fidelity.** (Account
aggregation could still be useful *later* for read-only import of holdings/balances into the
budget lens — but that's not market data and not now.) The brokers that *do* have real
developer APIs are Schwab, Alpaca, IBKR, Tradier; revisit Tier 3 only if you ever open one for
actual execution.

### B4 — Python 3.14 reality check ✅
**Result:** clean. A binary-only resolve pulled prebuilt cp314 wheels for the whole stack
(`numpy 2.4.6`, `pandas 3.0.3`, `yfinance 1.4.1`) — **no source builds needed.** yfinance is
viable on this runtime; the `price_overrides` fallback remains as belt-and-suspenders.

---

## C. Cadence & freshness

### C1 — on-demand vs scheduled refresh ✅
**Your goal:** run regularly (e.g., twice a week) to *see what shifts*.
**Recommendation:** that goal implies a **scheduled snapshot**, not just plan-time fetches.
Build a headless `finance.snapshot()` capability that, per run: fetches the universe → appends
a price-history row per ticker → recomputes drift vs. the strategy → logs a metrics row. The
"see what shifts" engine *is* this snapshot series over time. On-demand fetch stays available
(plan time can force-refresh).
**Decision:** starting goal = **a twice-weekly snapshot** (proposed: Tue & Fri after US
close, ~4:30pm ET). Each run is append-only; the diff between runs is the "what shifted."

### C2 — staleness tolerance (`max_price_age_minutes`) ✅
**Plain-English version (you asked what this means):** a "staleness window" is just *how old
a saved price is allowed to be before we bother fetching a fresh one*. We price off the
**daily closing price**. The market is shut nights/weekends, so the close doesn't change until
the next trading day — **Friday's close is still the correct, current price all weekend.** A
naïve "24-hour" rule would wrongly decide Friday's price is "too old" by Sunday and refetch
for nothing. A "market-calendar check" simply means the code knows which days the market is
actually open (skips weekends + holidays), so the question becomes the right one: *"is this
price from the last day the market was open?"*

**Decision:** start with the simple rule — `max_price_age_minutes = 4320` (3 days), which
covers weekends — and add the market-calendar smarts later. **Implication:** because we price
on closes, **plans are reproducible within a session and only move between sessions** — which
is exactly what makes "see what shifts" meaningful (the move is a real daily change, not
intraday jitter).

### C3 — scheduling mechanism (let's explore) 🔄
Three shapes, and I think the answer is the hybrid — consistent with hub-hub's "one
capability, many drivers" design:

- **(a) Harness `/schedule` routine** (remote agent on a cron). *Pro:* agent-native — one
  routine can fetch → snapshot → narrate → email you; no separate infra; fits agent-as-
  frontend. *Con:* it's a billed *agent* run, depends on the remote runner, heavier than the
  job needs for pure data capture.
- **(b) In-hub job via macOS `launchd`/cron** calling `hub run finance.snapshot`. *Pro:*
  deterministic, free, runs even when you're nowhere near a session; no LLM in the loop.
  *Con:* separate OS-level setup; does only the deterministic part (no commentary/delivery).
- **(c) Hybrid (recommended):** make `finance.snapshot()` a **plain headless tool** (the
  deterministic fetch+store+drift). Then the *trigger* is a free choice of driver: `launchd`
  for silent data capture, **or** a `/schedule` routine that calls the same tool *and* adds
  agent commentary + delivery. Same engine, swappable mouth — mirrors CLI/MCP/vault.

**Decision ✅:** build `finance.snapshot()` driver-agnostic; **start silent-data-only**, add
narrative later. Concrete progression:

- **Phase 1 — silent accumulation (`launchd`).** A macOS `launchd` job runs
  `hub run finance.snapshot` twice weekly. Pure data: fetch → append bars → recompute drift →
  log metrics. No LLM, no delivery. Goal is clean accumulation so the metrics series has
  something to chew on.
- **Phase 2 — narrative layer (`/schedule` routine).** Once the metrics are worth reading, a
  harness `/schedule` routine calls the *same* `finance.snapshot()` tool, then has the agent
  summarize "what shifted" and deliver it (email / Drive). Same engine, second mouth.
- **Phase 3 — reliability move (optional).** If the laptop being asleep costs too many runs,
  move the trigger to an always-on host (cheap VPS cron, or a cloud routine). The tool
  doesn't change — only what pulls the trigger.

**What else to think about here (scheduling/automation considerations, parked as a checklist
for build time):**

1. **Machine availability.** A laptop sleeps/closes — `launchd` can miss runs. Use
   `launchd`'s run-at-next-wake behavior, and add **missed-run backfill** (on each run, fill
   any sessions absent from `fin_price_bars`). This is the main reason Phase 3 exists.
2. **Timezone & DST.** "After US close" = 4pm *ET*, which drifts vs. local/UTC across DST.
   Schedule against a fixed ET offset or compute it; don't hardcode a local wall-clock.
3. **Market holidays.** Don't snapshot on closed days (or let dedup make it a no-op). A
   calendar check (same one C2 wants) avoids logging junk rows.
4. **Idempotency / dedup.** Running twice on the same day must not double-write — the
   `(ticker, session_date, source)` primary key already enforces this; use upsert semantics.
5. **Secrets for headless runs.** A `launchd` job has no shell profile — `ANTHROPIC_API_KEY`
   and any future provider key must be made available to it explicitly (env file / plist),
   and **never committed**. (Already gitignored: `.env`.)
6. **Observability & failure alerting.** Silent is good until it fails silently. The
   `fin_fetch_log` (E3) records per-run success/failure; add a lightweight "last run / last
   error" surface so a dead job is visible. This log is also the B2 trip-wire counter.
7. **Data growth / retention.** Tiny for one user (universe × 2/week), but note a retention
   policy exists as a knob if it ever matters.

---

## D. Storage & history (+ your "why store our own vs. just call the API?" question)

**Your call:** accumulate a series; build a daily/weekly/biweekly analysis/metrics layer on
top; structure the tables right.

### Your sharp question: can't we just fetch history from the API on demand — is storing our own worth it?
Yes, every provider serves historical daily bars on demand. Storing your own still earns its
keep, for five reasons — strongest first:

1. **Point-in-time truth / auditability.** Your north star is "numbers trace to a tool
   result." A stored observation records *what you saw when you decided*. Re-querying later
   can return *different* numbers — `adj_close` is retroactively re-adjusted on every
   dividend/split, and vendors silently revise data. Your deployment history must reconcile
   against the prices you actually used.
2. **Your own consistent metrics.** A daily/weekly/biweekly analytics layer needs a gap-free
   series computed *your* way, not subject to a vendor changing methodology or coverage.
3. **Provider independence & resilience.** If yfinance breaks or you switch to Tiingo, your
   accumulated history survives — you don't re-fetch (and re-pay / re-rate-limit) on every
   analysis.
4. **Cost / rate-limit efficiency.** Recomputing metrics over a long window by hammering the
   API burns quota; a local read is instant and free.
5. **Captures the un-backfillable.** Your *observed* snapshots and portfolio-level metrics at
   decision time can't be reconstructed after the fact.

**But don't over-hoard:** you do **not** need to eagerly download decades of bars. Deep
history for a rare backtest can be **lazily fetched on demand and cached**. So two distinct
roles, not one giant dump.

### D1/D2 — recommended table design ✅ (structure to confirm)

```sql
-- One canonical bars table. Snapshots and lazy backfill both write here.
CREATE TABLE fin_price_bars (
  ticker       TEXT NOT NULL,
  session_date TEXT NOT NULL,      -- the trading day this price belongs to (YYYY-MM-DD)
  close        REAL NOT NULL,      -- raw, unadjusted: the IMMUTABLE fact
  adj_close    REAL,              -- vendor-adjusted; vintage-stamped by ingested_at
  volume       REAL,
  source       TEXT NOT NULL,      -- 'yfinance' | 'tiingo' | ... (never mix in one series)
  ingested_at  TEXT NOT NULL,      -- when WE recorded it (adj_close vintage)
  PRIMARY KEY (ticker, session_date, source)
);

-- Layered analytics, recomputed/appended over time so we can analyze the analysis.
CREATE TABLE fin_metrics (
  scope   TEXT NOT NULL,           -- 'ticker' | 'sleeve' | 'portfolio'
  key     TEXT NOT NULL,           -- ticker / sleeve name / 'TOTAL'
  metric  TEXT NOT NULL,           -- 'ret','vol','drift_pct','drawdown','momentum',...
  window  TEXT NOT NULL,           -- '1d' | '1w' | '2w' | '1m' | ...
  as_of   TEXT NOT NULL,           -- trading day the metric is computed for
  value   REAL,
  PRIMARY KEY (scope, key, metric, window, as_of)
);
```

Notes on the design:
- **`close` is the immutable anchor**; `adj_close` is a stamped convenience for return math.
  Returns/vol/drawdown in `fin_metrics` compute from `adj_close`; share-count/valuation in the
  planner uses `close`. (This is the A2 split paying off.)
- **`source` in the key** prevents silently mixing yfinance and Tiingo bars in one series.
- **Point-in-time decision audit is already covered** by `fin_deployments.plan.prices` (the
  planner stores the exact prices used) — so we *don't* need a separate "snapshot vs history"
  table. `fin_price_bars` is the analytical series; the deployment record is the decision
  ledger. Clean separation.
- `fin_metrics` is **append-by-as_of**, so the metrics themselves form time-series you can run
  a second-order analysis over (e.g., "compute drift has widened 3 snapshots running").
- `fin_prices` (latest-only cache, from the first-slice spec) becomes a trivial view/query
  over the newest `session_date` in `fin_price_bars` — no separate table needed.

**Decision:** adopt `fin_price_bars` (snapshots + lazy backfill) + `fin_metrics` (layered).
Build the bars table with the snapshot tool (§C); add the metrics layer as a thin computed
step right after, since logging metrics over time is a stated goal. Deep historical backfill
= a lazy, cached `finance.backfill(ticker, from, to)` we add when an analysis first needs it.

---

## E. Correctness edge cases

### E1 — corporate actions (splits/dividends): defer? ✅ (defer, safely)
**Your call:** defer if it's extra work.
**Recommendation: defer building a corporate-actions engine** — and it's *safe* to defer
because of three mitigations already in the design:
1. **Holdings are user/broker-sourced**, so post-split share counts come in correct (your
   broker already turned 10 shares into 40 after a 4:1 split; you just re-enter from the
   statement).
2. **Return metrics use the vendor's `adj_close`**, which already folds in splits *and*
   dividends — so we get correct returns *without* our own adjustment engine.
3. The only residual gap: a raw-`close` series shows split *discontinuities*. We handle that
   by **always preferring `adj_close` for any return math** (which we do).
**Decision:** parked 🅿️ until we track cost-basis / tax-lots or want to compute our own
adjustments from raw. Note the gap in the spec so future-us isn't surprised.

### E2 — currency / FX ✅
**Your call:** USD only.
**Decision:** v1 is USD-only. Detect non-USD listings (suffixes like `.L`, `.TO`, `.HK`) and
**reject them at strategy-set time** with a clear message (ties to E3).

### E3 — unresolved tickers: fail loud ✅
**Your call:** fail loud, or at minimum log.
**Recommendation — split by context:**
- **Interactive (plan time):** *fail loud* — raise a clean error naming the offending tickers
  so the agent fixes the strategy or supplies `price_overrides`. (The planner already does
  this via `PriceError`.)
- **Scheduled (snapshot job, no human in loop):** *log-and-continue* — one bad ticker must not
  abort the whole snapshot. Record failures to a **`fin_fetch_log`** (ticker, attempted_at,
  source, error) and surface a per-run summary. Bonus: this log is exactly the counter that
  drives the **B2 reliability trip-wire** (>10% failure rate over 2 weeks).
**Decision:** raise interactively; log-and-continue + summary on scheduled runs; add
`fin_fetch_log`.

```sql
CREATE TABLE fin_fetch_log (
  id           INTEGER PRIMARY KEY,
  ticker       TEXT,
  attempted_at TEXT NOT NULL,
  source       TEXT,
  ok           INTEGER NOT NULL,   -- 1 success / 0 failure
  error        TEXT
);
```

---

## F. Reporting-era extensions

🅿️ **Parked** per your call — revisit F1 (earnings calendar) / F2 (movers) / F3 (dividends)
only after A–E are built. Noting that the B2 trip-wire #2 (earnings reliability) is the event
that will reopen F1, and likely the moment FMP enters.

---

## Status

All of A–E are now decided; F is parked. The whole section is resolved enough to build the
first slice.

One remaining **judgment call** (not a blocker): when the paid trip-wire fires, do we
**switch to FMP** or stay on free yfinance and live with the gaps? Given FMP is ~$22/mo and
consolidates prices + earnings + fundamentals for the deferred reporting/research lenses too,
the lean is "switch when triggered." First slice still ships **free on yfinance** behind the
provider seam regardless — FMP is a one-file swap when/if a trigger fires.
