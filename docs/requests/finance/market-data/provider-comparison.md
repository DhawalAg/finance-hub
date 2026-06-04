# Finance Market Data Provider Comparison — Working Note

**Status:** Working comparison for D3 / D4 sharpening
**Updated:** 2026-06-04
**Owner spec:** [acquisition](./acquisition.md)

This note compares stock-market data providers for two different jobs:

1. **Daily market data:** reliable daily OHLCV bars, raw close, adjusted close / return support,
   historical backfill, corporate actions, and daily refresh.
2. **Fundamentals / research data:** standardized financial statements, ratios, estimates, filings,
   segment data, and source traceability.

Do not collapse these into one provider decision too early. The best price-data provider may not be
the best fundamentals provider.

---

## Current Working Decision

For build-now:

- Keep **yfinance** as the first free `PriceProvider.fetch_daily_bars(...)` implementation.
- Refresh the active universe **at least daily** once the snapshot loop exists.
- Store normalized daily OHLCV in `fin_price_bars`.
- Keep fundamentals out of v1 provider work unless a research workflow triggers them.

For provider escalation:

- Do **not** treat FMP as the automatic paid default.
- Run a small provider bakeoff before committing to a paid integration.
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
| **Alpha Vantage** | Low-cost broad fallback | Daily OHLCV, adjusted daily, fundamentals, economic data; free tier exists; premium starts at published request/min tiers | Free tier is small; output limits; fundamentals quality still needs validation | Good cheap fallback, not first fundamentals truth |
| **FMP** | Broad screening bundle | One API for prices, statements, profiles, estimates, transcripts, calendars, news; inexpensive relative to enterprise vendors | Reddit sentiment is mixed; fundamentals should not be decision-grade without validation; pricing/tier churn risk | Candidate for screening/events, not automatic default |
| **Tiingo** | Price data and possible fundamentals alternative | Market reputation for EOD price data; Reddit users mention moving from FMP to Tiingo for fundamentals | Official docs/pricing need direct verification before selection; fundamentals offering may require sales/beta access depending plan | Investigate before paid choice |
| **Intrinio** | Higher-quality paid fundamentals / enterprise data | Official docs advertise fundamentals, market data, options, sourcing/cleaning; pricing page shows EOD adjusted/unadjusted OHLCV and business-use licensing | Much more expensive than hobby APIs; likely overkill until workflow proves value | Serious later candidate, not v1 |
| **EODHD** | Broad low/mid-cost bundle | Covers EOD, live OHLCV, fundamentals, corporate events, indices, broad exchange coverage | Reddit has recent anecdotes about historical gaps; must validate with our tickers before trust | Candidate to test, not assume |
| **Xfinlink** | Research-grade fundamentals / entity resolution | Docs expose prices, fundamentals, metrics, ticker resolution, historical constituents; explicitly documents price adjustment semantics and caveats | Newer/smaller provider; terms say data may be inaccurate/as-is; needs bakeoff | High-interest fundamentals candidate |
| **edgartools / SEC** | Filing-grounded fundamentals | Free; directly tied to SEC filings / Company Facts; useful for decision-grade checks and source-audited extraction | Not ideal for large bulk screening; XBRL/filing complexity still requires careful mapping | Use for ground truth when activated |

---

## Recommended Bakeoff

Do not pick the paid provider from marketing pages. Test with a small, ugly benchmark set.

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
- Xfinlink
- FMP
- EODHD
- Alpha Vantage
- Intrinio, if cost is justified
- Tiingo, if fundamentals access is clear

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

---

## D3 / D4 Implication

**D3 provider trigger:** keep the current trigger shape, but generalize the destination:

```text
Start free with yfinance.
Move to a paid price provider only if daily refresh has >10% missing/error bars over 2 weeks,
or if analytics/backfill needs exceed yfinance reliability.
Choose the paid provider via the price-data bakeoff, not by defaulting to FMP.
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
