# Finance Market Data Provider Comparison — Working Note

**Status:** D3 / D4 resolved for v1; free fundamentals runner corrected to Alpha Vantage
**Updated:** 2026-07-04
**Owner spec:** [acquisition](./acquisition.md)

This note compares stock-market data providers for two different jobs:

1. **Daily market data:** reliable daily OHLCV bars, raw close, adjusted close / return support,
   historical backfill, corporate actions, and daily refresh.
2. **Fundamentals / research data:** standardized financial statements, ratios, estimates, filings,
   segment data, and source traceability.

Do not collapse these into one provider decision too early. The best price-data provider may not be
the best fundamentals provider.

---

## 2026-07-04 Correction — EODHD Free Tier Excludes Fundamentals

The original decision (2026-06-21) named **EODHD** as the first *free* fundamentals runner. That was
wrong: verified against [EODHD pricing](https://eodhd.com/pricing), the free tier (20 calls/day)
covers EOD prices, splits/dividends, and search — **fundamentals are paid-only** (the "Fundamentals
Data Feed" starts at $59.99/mo). The earlier check passed only because the public `demo` token
returns fundamentals for a few tickers regardless of plan, which masked the gate.

What actually holds on a free tier, verified empirically on 2026-07-04:

- **Alpha Vantage free (25 calls/day, 5/min)** returns the compact stock screening pack. A live
  `OVERVIEW` fetch for NVDA yielded revenue growth, profit margin, P/S, and EV/EBITDA — the four core
  screening fields — all graded `screening`. This is now the **free fundamentals runner**.
  - Caveat: free `OVERVIEW` is thinner than EODHD's paid pack — no forward P/S, no balance-sheet
    debt/cash, no next-earnings-date in that call. Those need extra AV endpoints (more quota) or a
    paid provider. Missing fields surface as explicit gaps, never zero.
  - 25/day is enough for a personal portfolio because fundamentals change quarterly and are cached in
    `fin_fundamentals` with a 120-day staleness window — we do not re-fetch on every plan.
- **FMP free** is a 250-calls/day EOD *sandbox* with restricted fundamentals depth; its value is the
  paid tiers, not a free win. Keep as a paid alternative.
- **yfinance** can scrape fundamentals for free but is explicitly *not a fundamentals source of
  truth* (unofficial, breaks silently) — do not use it for the evidence store.

## Current Working Decision

For build-now:

- Keep **yfinance** as the first free `PriceProvider.fetch_daily_bars(...)` implementation.
- Use **Alpha Vantage** as the free `FundamentalsProvider` runner for the compact v1 stock evidence
  pack (core screening fields). This is the default when only `ALPHA_VANTAGE_API_KEY` is set.
- Use **EODHD** as the *paid* upgrade for a richer stock + ETF pack; when an `EODHD_API_KEY` is
  configured it runs primary and spills to Alpha Vantage on quota exhaustion. It is not a free option.
- Use **SEC / edgartools** as the filing-grounded verification path for thesis-critical stock
  fundamentals.
- Refresh the active universe **at least daily** once the snapshot loop exists.
- Store normalized daily OHLCV in `fin_price_bars`.
- Include a compact fundamentals workflow in v1 because one-time-buy eligibility depends on it.
  CSV/manual intake remains an override and bootstrap path, not the primary planned workflow.

For provider escalation:

- Do **not** treat FMP, EODHD, Polygon / Massive, or any other provider as the automatic paid default.
- Start with Alpha Vantage so the product can be used and sharpened on the free tier before paying for
  a broader feed.
- Run a small provider bakeoff before replacing Alpha Vantage with EODHD (paid) or another paid
  fundamentals integration.
- Evaluate price-data providers and fundamentals providers separately.
- Use SEC / edgartools or another filing-grounded source for decision-grade fundamentals; treat
  aggregator fundamentals as screening unless validated against filings.

---

## Why Fundamentals Are Hard

Fundamental data quality is mostly an XBRL normalization problem.

SEC filings are primary source, but filers can use company-specific concepts, dimensions, custom
labels, and changing presentation structures. The SEC's XBRL guide explicitly discusses custom
taxonomies and tells filers to prefer standard concepts when an existing concept fits, which implies
that duplicate/custom concepts still occur and have to be handled. The SEC's own financial statement
data sets also warn that the data sets help analysis but are not a substitute for reviewing full
filings.

That means the real differentiator between a good fundamentals database and a weak one is not "has an
income-statement endpoint." It is whether the provider maps messy XBRL tags and edge cases into stable
financial concepts correctly, preserves enough as-reported context, and exposes source/provenance so
we can audit.

Working principle:

```text
Prices can be provider-normalized.
Thesis-critical fundamentals must be filing-grounded or explicitly treated as screening.
```

---

## Evaluation Criteria

### Daily Market Data

Use these for D3 / D4:

- Daily OHLCV with raw close.
- Adjusted close or explicit split/dividend/total-return fields.
- Historical backfill depth.
- Bulk/multi-ticker fetch support for daily refresh.
- Clear source, timestamp, and adjustment semantics.
- Reliability under our expected universe size.
- Transparent pricing and licensing for personal/internal use.
- Clean API shape and stable SDK/docs.
- Upgrade path if we later need intraday, corporate actions, or commercial redistribution.

### Fundamentals / Research Data

Use these separately:

- Standardized and as-reported statements.
- XBRL concept mapping quality, including custom tags and dimensional data.
- Restatement handling and point-in-time availability.
- Segment, geography, and business-line support.
- Entity resolution across ticker changes, mergers, delistings, and reused tickers.
- Filing/source links for audit.
- Bulk throughput if we later screen many companies.
- Clear caveats around calculations, ratios, and estimates.

---

## Provider Shortlist

| Provider | Best Fit | Strengths | Risks / Caveats | Current Lean |
|---|---|---|---|---|
| **yfinance** | Free v1 daily bars | Easy Python integration; supports multi-ticker downloads, daily intervals, raw/unadjusted mode, actions option | Unofficial Yahoo access; reliability can break; not a fundamentals source of truth | Use first for Slice A/B; monitor failures |
| **Polygon / Massive** | Paid price-data upgrade | Strong OHLC aggregate API; clear stocks tiers; supports adjusted/unadjusted aggregates; good if we need more reliable historical bars | More price-feed oriented than fundamentals-oriented; cost rises with history/real-time needs | Strong price-data fallback if yfinance fails |
| **EODHD** | Paid compact fundamentals upgrade | Stock + ETF fundamentals line up with the v1 compact evidence pack; richer than AV free (forward P/S, balance-sheet debt/cash, next-earnings-date) | **Fundamentals are NOT in the free tier** (free = prices/splits/dividends/search only); paid Fundamentals Data Feed from $59.99/mo; screening-grade only | Paid upgrade; runs primary + spills to AV when an `EODHD_API_KEY` is configured |
| **Alpha Vantage** | Free compact fundamentals runner | Free tier (25 calls/day, 5/min) returns the core stock screening pack — verified live: revenue growth, margin, P/S, EV/EBITDA; also income statement, balance sheet, cash flow, ETF profile as separate calls | Free `OVERVIEW` is thinner than EODHD paid (no forward P/S / debt-cash / earnings-date in one call); 25/day cap; screening-grade only | **Default free runner** (default when only `ALPHA_VANTAGE_API_KEY` is set) |
| **FMP** | Paid fundamentals / events upgrade | Broad stock metrics, ratios, enterprise values, growth, estimates, calendars, SEC filing links, bulk endpoints, ETF and mutual-fund endpoints | ETF holdings may require a higher tier; fundamentals should not be decision-grade without validation; pricing/tier churn risk | First serious paid alternative if Alpha Vantage blocks normal use |
| **Tiingo** | Price data and possible fundamentals alternative | Market reputation for EOD price data; Reddit users mention moving from FMP to Tiingo for fundamentals | Official docs/pricing need direct verification before selection; fundamentals offering may require sales/beta access depending plan | Investigate before paid choice |
| **Intrinio** | Higher-quality paid fundamentals / enterprise data | Official docs advertise fundamentals, market data, options, sourcing/cleaning; pricing page shows EOD adjusted/unadjusted OHLCV and business-use licensing | Much more expensive than hobby APIs; likely overkill until workflow proves value | Serious later candidate, not v1 |
| **EODHD** | Paid stock + ETF fundamentals alternative | Covers EOD, live OHLCV, stock fundamentals, ETF fundamentals, corporate events, indices, and broad exchange coverage; ETF docs map well to expense / holdings / exposure eligibility | Paid; Reddit has recent anecdotes about historical gaps; must validate with our tickers before trust | Paid alternative if the free tier no longer carries the workflow |
| **Finnhub** | Broad secondary fundamentals / news / sentiment candidate | Market news, sentiment, fundamentals, and crypto coverage in one API | Free tier is limited and the bundle is broader than the compact v1 need | Keep on the shortlist if we want more non-price context later |
| **Alpaca Markets** | Trading API with market data and paper trading | Free access for data + trading API, paper trading path | Oriented around execution, not compact fundamentals | Useful if we later want a live brokerage-adjacent path |
| **Mboum API** | Time series / technical indicators candidate | Free tier available; inexpensive entry point for bar data and indicators | More technical-analysis oriented than fundamentals-oriented | Niche backup for indicator-heavy workflows |
| **SteadyAPI** | Time series / technical indicators candidate | Free tier available; low-cost option for price/indicator access | Smaller ecosystem; not the first choice for fundamentals | Niche backup for indicator-heavy workflows |
| **Xfinlink** | Research-grade fundamentals / entity resolution | Docs expose prices, fundamentals, metrics, ticker resolution, historical constituents; explicitly documents price adjustment semantics and caveats | Newer/smaller provider; terms say data may be inaccurate/as-is; needs bakeoff | High-interest fundamentals candidate |
| **edgartools / SEC** | Filing-grounded fundamentals | Free; directly tied to SEC filings / Company Facts; useful for decision-grade checks and source-audited extraction | Not ideal for large bulk screening; XBRL/filing complexity still requires careful mapping | Use for ground truth when activated |

---

## Recommended Bakeoff

Do not pick the paid provider from marketing pages. Test with a small, ugly benchmark set.

The first v1 adapter starts with Alpha Vantage (the free runner) so the product can be used before
committing to a paid feed. The bakeoff becomes an upgrade gate: run it before adding a paid
fundamentals provider (EODHD paid, FMP, or another).

### Price-Data Bakeoff

Candidate providers:

- yfinance baseline
- Polygon / Massive
- Alpha Vantage
- FMP
- EODHD
- Tiingo, once docs/pricing are verified

Test universe:

- 20 active large caps: AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, XOM, etc.
- 5 split/dividend edge cases.
- 5 ticker-history edge cases: GOOG/GOOGL, META/FB, BRK.B, old/reused tickers if supported.
- 5 ETFs: SPY, QQQ, VTI, IWM, SMH.

Checks:

- Can fetch latest completed daily OHLCV for all tickers.
- Can backfill at least 5 years.
- Raw close matches a known reference within tolerance.
- Adjusted close / return behavior is documented.
- Failure rate over two weeks of daily refresh.
- Latency and rate-limit behavior for our expected universe.

### Fundamentals Bakeoff

Candidate providers:

- edgartools / SEC Company Facts
- EODHD baseline
- Alpha Vantage fallback
- FMP
- Xfinlink
- Intrinio, if cost is justified
- Tiingo, if fundamentals access is clear
- Finnhub, if we want a broader secondary bundle
- Alpaca Markets, if a trading-adjacent API becomes desirable
- Mboum API, if indicator-heavy workflows become important
- SteadyAPI, if a low-cost technical indicator backup is useful

Test companies:

- Normal tech: AAPL, MSFT, NVDA.
- Financials: JPM, BAC.
- REIT: PLD or AMT.
- Insurance: BRK.B or CB.
- Retail/inventory: WMT, COST.
- Company with major segment reporting: AMZN, GOOGL.
- Ticker/entity edge case: META/FB, GOOG/GOOGL.

Checks:

- Revenue, gross profit, operating income, net income, CFO, capex, FCF, total assets, debt, shares.
- Annual and quarterly periods.
- Filing date, fiscal period, accession/source link.
- As-reported vs standardized field availability.
- Segment/geography support.
- Restatement behavior.
- Ticker/entity resolution.
- Agreement against latest 10-K / 10-Q for thesis-critical fields.

V1 Alpha Vantage smoke test (done 2026-07-04, passing):

- Providers: Alpha Vantage (free `OVERVIEW`) plus SEC/edgartools for filing-grounded spot checks.
- Tickers: verified live against NVDA; extend to AAPL, MSFT, JPM or BAC, AMZN or GOOGL for coverage.
- **Per-call harvest:** one free `OVERVIEW` call returns ~55 fields; we normalize **33** of them
  (verified live on NVDA) — valuation (P/E, forward P/E, PEG, P/B, P/S, EV/EBITDA, EV/Rev),
  returns/margins (ROE, ROA, operating margin, gross profit, net margin), growth (revenue + earnings
  YoY), size (market cap, revenue, EBITDA, EPS, book value, shares), dividend (yield, per-share,
  ex-date), risk (beta, 52wk hi/lo, 50/200-day MAs), analyst (target price + rating spread), and
  sector/industry/latest-quarter. Facts only, all `screening`-grade — no thresholds. Maximizes value
  per call so the 25/day cap goes further.
- Not in one free `OVERVIEW` call: forward P/S, balance-sheet debt/cash, next earnings date (need
  extra AV endpoints — `BALANCE_SHEET`/`EARNINGS`, +1 call each — or a paid provider); these surface
  as explicit gaps, never agent-filled numbers.
- ETF handling (SPY/QQQ/VOO): needs AV `ETF_PROFILE` (separate function) or a paid provider — the
  stock `OVERVIEW` path does not cover ETFs. Deferred until ETF eligibility is built.

Paid fundamentals upgrade triggers:

- Alpha Vantage's 25/day free cap blocks normal usage.
- ETF fundamentals are needed and `ETF_PROFILE` is insufficient.
- Stock fundamentals miss too many valuation fields (e.g. forward P/S, debt/cash needed routinely).
- Manual fundamentals gaps become common enough to slow product iteration.

When any trigger fires, compare EODHD (paid) and FMP first. EODHD is the cleaner stock + ETF
fundamentals candidate and is already wired (drop in an `EODHD_API_KEY`); FMP is the broader paid
bundle. Keep SEC/edgartools as the decision-grade check path either way.

---

## D3 / D4 Implication

**D3 provider trigger:** keep the current trigger shape, but generalize the destination:

```text
Start free with yfinance.
Move to Polygon / Massive or another paid price provider only if daily-bar fetches fail often,
adjusted/unadjusted semantics become hard to trust, analytics/backfill needs exceed yfinance
reliability, or the workflow needs intraday / production-grade market data. Choose the paid provider
via the price-data bakeoff, not by defaulting to a fundamentals provider.
```

**D4 snapshot universe:** provider choice depends on the refresh universe.

Recommended first universe:

```text
approved strategy sleeve instruments ∪ current holdings
```

Do not include the full research watchlist in the daily snapshot by default. Research watchlist
pricing can be fetched on demand or added later when research starts using quantitative readouts
regularly. This keeps daily refresh cheap and focused on planning.

---

## Source Log

- yfinance `download(...)` docs: https://ericpien.github.io/yfinance/reference/api/yfinance.download.html
- Polygon / Massive custom OHLC aggregate docs and plan access: https://massive.com/docs/rest/stocks/aggregates/custom-bars
- Alpha Vantage docs: https://www.alphavantage.co/documentation/
- Alpha Vantage premium pricing: https://www.alphavantage.co/premium/
- FMP docs: https://site.financialmodelingprep.com/developer/docs
- FMP pricing: https://intelligence.financialmodelingprep.com/pricing-plans?direct=true
- Intrinio pricing: https://intrinio.com/pricing
- Intrinio API docs: https://docs.intrinio.com/documentation/api_v2/getting_started
- EODHD fundamentals docs: https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds
- Xfinlink docs: https://xfinlink.com/
- edgartools Company Facts docs: https://edgartools.readthedocs.io/en/stable/guides/company-facts/
- SEC financial statement data sets: https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets
- SEC EDGAR XBRL guide: https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2025-07-10.pdf
- Reddit sentiment thread on stock-data APIs / FMP / Tiingo: https://www.reddit.com/r/algotrading/comments/1idhkr5/what_apis_are_you_guys_using_for_stock_data/
- Reddit sentiment thread on FMP fundamentals quality: https://www.reddit.com/r/algotrading/comments/144i9dv/fundamental_data_sources/
- Reddit sentiment thread on historic data-provider gaps: https://www.reddit.com/r/algotrading/comments/1s07rh1/psa_on_historic_data_providers/
