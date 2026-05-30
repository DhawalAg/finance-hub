# Finance Hub — Data Source Comparison

Last updated: 2026-05-30
Status: decision doc — companion to [data-pipeline-spec.md](./data-pipeline-spec.md) and
[data-pipeline-answers.md](./data-pipeline-answers.md)

Extensive comparison of **FMP · Finnhub · Polygon · edgartools · sec-api** for the finance
hub, with a cost/benefit read and an experienced-practitioner recommendation.

> Pricing below is approximate (knowledge as of early 2026) and tiers shift often — treat
> exact numbers as "verify at signup," not gospel. The *relative* positioning is stable.

---

## TL;DR — the verdict first

**They aren't five competitors; they're two categories.** Three are market-data/fundamentals
APIs (FMP, Finnhub, Polygon); two are SEC-filings sources (edgartools, sec-api). Comparing
edgartools to Polygon is apples-to-oranges — you'd plausibly use **one from each column.**

**What an experienced person builds for *our* use case (weekly DCA + thematic research, single
user, no intraday/algo):**

> **FMP as the workhorse data API + edgartools (free) as the primary-source ground truth.**
> ~$22–50/mo all-in. Skip Polygon (you'd pay for real-time latency you don't use), skip
> Finnhub (overlaps FMP; only wins for real-time/news/alt-data), skip sec-api (it productizes
> data edgartools gives you free, and only earns its keep at filing-search/streaming scale).

Rationale in one line: **buy one broad aggregator for convenience, pair it with the free
authoritative source you can cross-check against — and don't pay for capabilities (real-time
ticks, productized public filings) your workflow never exercises.**

---

## Framing: what we actually need (from the specs)

| Need | Lens | When | Best-served by |
|---|---|---|---|
| Current price per ticker | Planner | **now** | yfinance (free, decided) → FMP/Polygon |
| Historical price series | Metrics / sim | soon–later | FMP (fine) · Polygon (pristine) · Tiingo |
| Earnings dates | Reporting | deferred | FMP · Finnhub |
| Movers / dividends | Reporting | deferred | FMP · Finnhub |
| Fundamentals (statements, ratios) | Research | deferred | FMP (aggregated) · **edgartools (source)** |
| Filings (10-K/Q, 8-K, Form 4) | Research | deferred | **edgartools** · sec-api |
| Analyst estimates / consensus | Research | deferred | FMP · Finnhub |

Two observations that decide most of this:
1. We never need **intraday / real-time tick data** — a weekly cadence prices off daily
   closes. That removes Polygon's entire reason for existing *for us*.
2. Our north star is "**every number traces to imported data / a tool result.**" That makes a
   free, authoritative **primary source (SEC EDGAR via edgartools)** philosophically and
   practically valuable for the research lens — you ground theses in filings, not an
   aggregator's restated numbers.

---

## The contenders

### Category A — market data + fundamentals APIs

#### FMP (Financial Modeling Prep)
- **What it is:** one broad API for prices (real-time-ish + historical), full financial
  statements, ratios, earnings calendar, analyst estimates, company profiles, ETF holdings,
  and parsed SEC financials.
- **Strengths:** breadth from a single key; cheap; good docs; covers planner + reporting +
  research needs without stitching vendors. The "do-it-all for a solo builder" choice.
- **Weaknesses:** it's an **aggregator** — fundamentals are normalized/restated and
  *occasionally* have errors or gaps; not the source of truth. US-centric (intl is thinner).
  Lower tiers rate-limit and gate some endpoints.
- **Pricing (verified 2026-05-30):** advanced plans **$19–$99/mo**. Free/Basic = EOD sandbox
  (500 MB/30d). **Starter** (~$19–29/mo): real-time US, **300 req/min**, 20 GB/30d. **Premium**:
  + UK/Canada, longer history, intraday, technicals, calendars, 750 req/min, 50 GB. **Ultimate**
  (~$99/mo): + global, earnings-call transcripts, ETF/13F holdings, 1-min intraday, 3000
  req/min, 150 GB. *(Exact Starter monthly vs annual — confirm at checkout.)*
- **Who uses it:** solo builders, indie fintech, research/screener tools, AI-investing apps.

#### Finnhub
- **What it is:** real-time-leaning stock API — quotes, websockets, company news, earnings
  calendar + surprises, basic financials, and **alternative data** (sentiment, insider
  transactions, some ESG).
- **Strengths:** unusually **generous free tier** (~60 calls/min, US) for quotes/news/earnings
  calendar; strong real-time + news + alt-data; good for alerting.
- **Weaknesses:** paid tiers jump in price and many premium endpoints (deep fundamentals,
  global) are gated high; free tier is non-commercial. Overlaps FMP for our needs without
  beating it on the things we care about.
- **Pricing (approx):** Free (generous, personal use); paid personal tiers ~$50/mo+, premium
  data well north of that.
- **Who uses it:** people wanting near-real-time quotes, news feeds, sentiment/alt-data, or
  alerting dashboards.

#### Polygon.io
- **What it is:** developer-grade **market data** — US stocks, options, forex, crypto,
  indices. Real-time + full historical aggregates and tick data. Best-in-class price data.
- **Strengths:** pristine, low-latency price data; deep, clean historical archive; the serious
  choice for backtesting price series and intraday/algo work.
- **Weaknesses:** **not a fundamentals shop** (financials exist but are thin/secondary); you'd
  pay for real-time/intraday capability our weekly cadence never uses. Wrong tool for our job.
- **Pricing (approx):** Free (5 calls/min, EOD, ~2yr); **Stocks Starter ~$29/mo** (unlimited
  calls, 15-min delayed, ~5yr history); Developer ~$79; Advanced ~$199 (real-time). Asset
  classes priced separately at lower tiers.
- **Who uses it:** algo traders, quant backtesters, fintech needing real-time market data.

### Category B — SEC filings sources

#### edgartools (free Python library over SEC EDGAR)
- **What it is:** an open-source Python wrapper over the **SEC's free, public EDGAR system** —
  filings (10-K, 10-Q, 8-K), XBRL-parsed financial statements, insider filings (Form 4),
  ownership, full submission history. A *library*, not a hosted service.
- **Strengths:** **free**, and the data is **authoritative primary source** (straight from
  what companies actually filed). Pythonic access to statements + filings. Perfectly aligned
  with the "trace to source" north star. No vendor lock-in.
- **Weaknesses:** **no market data** (no prices/quotes). You handle SEC's rate limits
  (~10 req/s) and **must set a descriptive User-Agent** (SEC requirement). Data appears when
  *filed* (so it's authoritative but not "real-time market"). You do a bit more parsing/glue.
- **Pricing:** **$0** (SEC data is public; the library is OSS).
- **Operational rule (verified 2026-05-30):** **10 req/s per IP**, and a descriptive
  `User-Agent` ("Name email") is **mandatory** — missing it is the #1 cause of `403`s;
  exceeding the limit blocks the IP for ~10 min. Build requirement: set an EDGAR identity
  (env var), cap ≤8 req/s, cache locally, exponential backoff. (Our caching-first design
  already covers most of this.)
- **Who uses it:** anyone who wants ground-truth fundamentals/filings for free — diligence
  tools, research workflows, people who don't trust aggregator restatements.

#### sec-api.io
- **What it is:** a **commercial** API over EDGAR — full-text filing search, real-time filing
  stream, structured/XBRL-to-JSON extraction, insider-trading API, nicer querying.
- **Strengths:** saves you building EDGAR search + parsing; **real-time filing alerts** and
  full-text search across the corpus are genuinely hard to DIY at scale.
- **Weaknesses:** **you're paying for ultimately-public data**; for a single user reading a
  handful of tickers, edgartools covers ~all of it for free. Only filings, no prices.
- **Pricing (approx):** Free trial (limited); paid ~$49/mo starter → ~$199/mo+ for higher
  volume / full-text search / streaming.
- **Who uses it:** funds/tools needing real-time filing surveillance or full-text search over
  the whole EDGAR corpus — i.e., scale we don't have.

---

## Comparison matrix

| | FMP | Finnhub | Polygon | edgartools | sec-api |
|---|---|---|---|---|---|
| **Category** | Mkt+fundamentals | Mkt+news+alt | Market data | SEC filings (lib) | SEC filings (API) |
| **Prices (EOD)** | ✅ | ✅ | ✅✅ (best) | ❌ | ❌ |
| **Real-time/intraday** | partial (tiered) | ✅ | ✅✅ | ❌ | n/a |
| **Historical price depth** | good | limited (paid) | ✅✅ (best) | ❌ | n/a |
| **Fundamentals** | ✅ (aggregated) | ✅ (basic/paid) | ✗ (thin) | ✅✅ (source) | ✅ (from filings) |
| **Earnings calendar** | ✅ | ✅ | ✗ | ~ (from filings) | ~ |
| **Analyst estimates** | ✅ | ✅ (paid) | ✗ | ❌ | ❌ |
| **Filings / 8-K / Form 4** | partial | insider (paid) | ✗ | ✅✅ | ✅✅ |
| **Full-text filing search** | ✗ | ✗ | ✗ | limited | ✅✅ |
| **Data authority** | second-hand | second-hand | first-hand (prices) | **primary source** | primary source |
| **Free tier** | yes (250/day) | **generous** | yes (5/min EOD) | **fully free** | trial only |
| **Entry paid** | ~$22–29/mo | ~$50/mo | ~$29/mo | $0 | ~$49/mo |
| **Fit for us** | ✅ **workhorse** | optional | overkill | ✅ **ground truth** | premature |

`✅✅` = best-in-class · `✅` = solid · `~` = partial/indirect · `✗` = weak/absent

---

## Cost / benefit analysis

**What our workflow actually exercises:** daily-close prices, earnings dates, dividends,
fundamentals + filings for research. No intraday, no algo, no filing-surveillance-at-scale,
single user.

- **FMP (~$22–50/mo):** highest benefit-per-dollar for us. One key covers planner + reporting
  + research breadth. The ~$22 Starter likely suffices; bump to ~$50 Premium only if rate
  limits or coverage bite. **Pay for this.**
- **edgartools ($0):** pure upside. Free, authoritative, aligned with our north star, no lock-in.
  The cost is a little glue code. **Use this.**
- **Polygon (~$29–199/mo):** benefit is real-time + pristine deep history — **neither of which
  we use** at a weekly cadence. Paying Starter buys mostly latency we'd throw away. **Skip
  until/unless we go intraday or want a serious price-history backtest archive.**
- **Finnhub (free–$50/mo):** the free tier is a nice *backup/cross-check* for quotes + earnings
  calendar at $0. Paid overlaps FMP without beating it for us. **Optional free; don't pay yet.**
- **sec-api (~$49–199/mo):** paying for productized public data that edgartools gives free, for
  a scale (full-text search / real-time streams) we don't have. **Skip until a concrete need
  for filing search/streaming appears.**

**Spend posture (you said you'll pay for well-built infra):** the well-built-infra money is
**FMP**, not Polygon/sec-api. Spending on Polygon would be paying for *power*, not *fit* —
the experienced move is to buy fit. Total recommended spend: **~$22–50/mo (FMP) + $0
(edgartools)**.

---

## Reliability reality check — the FMP fundamentals caveat

Users (incl. a research-business operator on Reddit, 2026) report FMP's data quality "varies
wildly" and specifically flag **financial-statement data as inaccurate** — enough to consider
moving off it for fundamentals. Worth taking seriously, and worth scoping correctly:

- **It's the aggregator restatement problem, and it's inherent.** FMP doesn't *originate*
  fundamentals — it machine-parses + normalizes filings into one schema across thousands of
  companies (idiosyncratic line items, restatements, GAAP/non-GAAP, odd fiscal calendars).
  That mapping produces errors: mislabeled lines, sign flips, missing periods. **Every cheap
  aggregator has this**; the reason FactSet/Bloomberg/Capital IQ cost thousands/yr is
  analyst-curated, hand-checked fundamentals. "Varies wildly" is the expected trade-off at
  FMP's ~$22–50 price point, not an anomaly.
- **It's scoped to statements, not prices.** Complaints cluster on parsed **financial
  statements + derived ratios**. FMP's **prices** (EOD/historical) and **earnings calendar**
  are far more reliable — price data is standardized and easy to get right. (The quoted user
  is moving off FMP *statement* data, not its prices.)
- **It validates our two-source design.** Our plan already says: never rest a decision on
  aggregator fundamentals — ground them in EDGAR primary source. That Reddit operator is
  rediscovering exactly that need. We have it for free.

**Refinement this forces (recommendation updated below):** since FMP statements are shaky and
edgartools does statements free + authoritatively, **promote edgartools from "cross-check" to
the fundamentals source of record**, and shrink FMP's durable value to **prices + earnings
dates + analyst estimates + convenience**. Treat FMP statement data as *screening/directional
only, never decision-grade*. Analyst **estimates** remain the one thing only an aggregator
(FMP/Finnhub) provides — EDGAR is backward-looking. And because the planner needs only prices
(on free yfinance), this lets us **defer paying FMP even longer**: we owe nothing until the
research/reporting lens is live, and even then we pay for convenience + estimates, not
accuracy.

## Recommendation (the practitioner's call)

**Adopt a two-source design, both behind provider seams so swaps stay cheap:**

1. **FMP = prices + earnings calendar + analyst estimates + convenience** (`PriceProvider` +
   future `EarningsProvider` + `EstimatesProvider`). **Tier = Starter** (~$19–29/mo) — its 300
   req/min + 20 GB are far beyond our few-dozen-tickers-twice-weekly load, so Premium/Ultimate
   buy only deep history / intraday / transcripts we don't need. **Deferred:** the planner runs
   free on yfinance; we don't pay FMP until the research/reporting lens is live. **Treat its
   financial-statement data as screening/directional only — never decision-grade** (see
   reliability caveat). Analyst *estimates* are its uniquely valuable, EDGAR-can't-do-it offering.
2. **edgartools = the fundamentals source of record + `FilingsProvider`** (free). Reported
   statements (10-K/10-Q), 8-K/Form-4 events: this is **ground truth for any fundamental
   number a decision rests on**, not just a cross-check. Authoritative, free, aligned with the
   north star. (Promoted to backbone after the FMP statement-quality caveat.)
3. **yfinance stays the free first-slice `PriceProvider`** — FMP is a one-file swap when the
   trip-wire fires (see [answers doc](./data-pipeline-answers.md) B2). No rush to pay before
   the planner is real.

**Trigger-based upgrade path (don't pre-buy):**
- Reporting/research lens goes active, or yfinance flakiness crosses the trip-wire → **turn on
  FMP.**
- A thesis needs ground-truth financials / you want filing events → **add edgartools** (free,
  so really "whenever").
- You start doing **intraday/algo** or want a pro backtest price archive → **then** consider
  **Polygon.**
- You want **real-time news / sentiment / alerting** → **then** consider **Finnhub** (its free
  tier first).
- You need **full-text filing search or real-time filing surveillance at scale** → **then**
  consider **sec-api** (edgartools first).

**Why not "just FMP for everything, including fundamentals"?** Because aggregators restate and
occasionally err, and for a system that promises every number traces to a source, having the
free authoritative cross-check (EDGAR) is cheap insurance and good craft. Two sources, clean
seams, minimal spend, no lock-in.

---

## Architecture impact (seams)

This maps onto the planner's plugin seams (see requirements-dump.md):
- `PriceProvider` — yfinance now → FMP later. *(realized seam)*
- `FundamentalsProvider` / `EarningsProvider` — FMP. *(new, research/reporting era)*
- `FilingsProvider` — edgartools. *(new, research era)*

Each is selected by config; nothing in the planner or reporting logic knows which vendor is
behind the seam. Vendor decisions stay reversible.

## Verified (2026-05-30)

- **FMP:** advanced plans $19–$99/mo; **Starter** (300 req/min, 20 GB/30d, real-time US) is
  the tier for us — confirmed far above our load. Only residual to confirm at checkout is the
  exact Starter monthly-vs-annual figure.
- **EDGAR/edgartools:** 10 req/s per IP, mandatory descriptive `User-Agent`, ~10-min IP block
  on breach. Captured as a build requirement above.

**Decision (2026-05-30):** FMP **Starter** as the eventual paid tier (deferred until the
research/reporting lens; planner stays on free yfinance) + edgartools (free) as the
fundamentals/filings source of record. Skip Polygon/Finnhub/sec-api pending specific triggers.
Sources: [FMP pricing](https://site.financialmodelingprep.com/pricing-plans) ·
[SEC EDGAR rate-limit policy](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)
· [edgartools config](https://edgartools.readthedocs.io/en/stable/configuration/).
