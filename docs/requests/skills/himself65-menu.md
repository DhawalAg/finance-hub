# himself65/finance-skills as a Menu for ADR-0005 Skills

Research findings for issue #52 (child of skills map #51). Date: 2026-07-17.
Subject: [himself65/finance-skills](https://github.com/himself65/finance-skills)
(shallow-cloned at survey time; 6 plugins, 26 skills).

Per [ADR 0005](../../adr/0005-deterministic-tools-as-foundation-skills-as-orchestration-layer.md),
this repo is a **menu of which analyses matter**, never drop-in code: every subject skill
computes inline (yfinance calls + freehand Python in the model's head) with no evidence store,
which violates finance-hub's core invariant (the agent must not invent prices, metrics, budget
facts, or allocation math). Any adoption below means *rewriting* the analysis as an ADR-0005
skill that calls registered tools and persists evidence — and, per
[ADR 0006](../../adr/0006-skills-ship-with-capability-eval-tasks.md), shipping capability eval
tasks with it.

## Finance-hub surface used for mapping

Registered tools (from `bin/finance tools`, 26 tools): research
(`finance.set_theme/list_themes/get_theme/map_instruments/review_instrument/set_research_note/get_research_note/upsert_source/link_source/supersede_source_link/list_sources/sources_due_for_review/candidate_evidence/research_priorities`),
market-data (`finance.fetch_fundamentals` — Alpha Vantage OVERVIEW, ~33 stock fields incl.
PE/forward PE/PEG/P?B/EV-EBITDA/EV-Revenue, margins, ROE/ROA, beta, 52w range, MA50/200,
analyst target+rating; ETF fields expense_ratio/top_holdings/sector_exposure/AUM/perf_1y),
strategy (`finance.promote_to_strategy/get_strategy/list_strategies/activate_strategy/check_strategy_deployable`),
planning (`finance.import_portfolio_csv/generate_deployment_plan/get_deployment_plan/plan_readiness_check/approve_deployment_plan/reject_deployment_plan`), plus `health`.

Also relevant, **not yet registered as tools** (internal Python seams only):

- `market_data.tools.prices()` / `snapshot()` — cached daily OHLCV bars into `fin_price_bars`
  (1y history, provenance, fetch log). Volume is stored per bar.
- `market_data.metrics` — `simple_return`, `realized_volatility`, `max_drawdown`,
  `current_drawdown`, `daily_returns`, `compute_ticker_metrics` + `store_metrics`.

This matters for the mapping: several candidate analyses are computable *from data finance-hub
already stores*, but the compute step would need registration (a CLI/MCP-callable metric tool)
before a skill may orchestrate it.

## Candidate table (market-analysis plugin, 11 skills)

| Skill | What it computes | Workflow | Existing coverage | Gap size | Verdict |
|---|---|---|---|---|---|
| yfinance-data | Generic yfinance fetch playbook (prices, statements, options, dividends, holders, news) | market-data | Superseded by price provider + `fetch_fundamentals` | — | Redundant as a skill; useful only as a coverage checklist |
| company-valuation | DCF + relative + SOTP triangulation, WACC×g sensitivity, Bull/Base/Bear | research | Valuation multiples + analyst target already stored | Relative slice: small. Full DCF: large (statements + DCF tool) | **Strong** — adopt as staged "candidate valuation" skill, relative-first |
| earnings-preview | Consensus estimates, beat/miss history, analyst sentiment pre-earnings | research / market-data | `next_earnings_date` field (provider-dependent), analyst rating | Estimates data class not stored | Weak — only the "know the earnings date before a one-time buy" sliver fits |
| earnings-recap | Actual vs estimate, price reaction, margin trends post-earnings | research | Price reaction from `fin_price_bars`; margins via fundamentals refresh | Earnings-history data | **Strong** — as a "thesis refresh after earnings" playbook over existing supersession machinery |
| estimate-analysis | Estimate revision trends/breadth, growth projections | research | None | New estimates+revisions time-series store | Poor for v1 — revision momentum is trader-flavored |
| etf-premium | Premium/discount vs NAV; screener; gamma-squeeze decomposition | market-data | ETF fundamentals fields; no NAV | NAV data source | Sliver only — single-ETF premium check before an ETF one-time buy; rest is trading analytics |
| options-payoff | Black-Scholes payoff curves, interactive widgets | — | — | — | Out of scope — derivatives trading, not personal PM |
| saas-valuation-compression | ARR multiple compression between VC funding rounds | — | — | — | Out of scope — private-market VC analysis |
| sepa-strategy | Minervini trend template, VCP patterns, breakout entries, stops, position sizing | — | — | — | Out of scope — swing-trading methodology; conflicts with strategy-driven DCA model |
| stock-correlation | Pairwise/rolling correlation, sector clustering, pair trading | strategy | `daily_returns` seam over stored bars | Small: deterministic correlation tool + registration | **Strong** — as a portfolio concentration/correlation review; drop pair-trading sub-skills |
| stock-liquidity | Spreads, ADTV, Amihud, market impact, turnover | planning | Volume stored in `fin_price_bars` | Small for ADTV/Amihud; quote data needed for spreads | Medium — a liquidity sanity-check metric feeding one-time-buy plan warnings |

## Per-candidate notes

### yfinance-data (market-data)

A dispatch table from user intent to yfinance API calls, executed inline. Finance-hub already
owns this ground with discipline the skill lacks: the lazy-wired yfinance `PriceProvider` writes
provenance-stamped bars, and `finance.fetch_fundamentals` returns graded, citable envelopes.
Adopting this skill would be a regression — it teaches the agent to bypass the store.
Residual menu value: it enumerates yfinance surfaces finance-hub does not persist (dividends,
splits, statements, holders, news, options), a useful checklist when scoping future market-data
slices. **Verdict: do not adopt; keep as data-coverage reference.**

### company-valuation (research)

The most substantial analysis in the repo: 5-year FCFF DCF (growth fade, 3-yr median margins,
WACC from beta/rf/ERP, dual terminal value), peer-median relative valuation (fwd P/E, EV/Rev,
EV/EBITDA), optional SOTP, blended implied price, 5×5 sensitivity, Bull/Base/Bear. Sanity gates
(wacc ≤ g, TV share of EV) are genuinely good menu content.

- **Covered today**: the *relative* leg's inputs largely exist — `fetch_fundamentals` stores
  P/E, forward P/E, PEG, P/B, EV/EBITDA, EV/Revenue, margins, growth, beta, analyst target for
  target and peers alike.
- **Gaps**: no peer-set concept; no deterministic comparison/blend tool; the DCF leg needs
  statement-level data (revenue history, EBIT, D&A, capex, ΔNWC, tax) that no provider slice
  stores, plus a registered DCF tool so the math is deterministic and its assumptions persisted
  as evidence (the invariant forbids the model doing FCFF arithmetic freehand).
- **Fit**: valuation triangulation is exactly what candidate review / one-time-buy conviction
  needs. Stage it: (1) "relative valuation vs peers" skill orchestrating `fetch_fundamentals`
  over target+peers plus a small registered comparison tool, citing stored envelopes in the
  thesis note; (2) full DCF later as its own tool + data slice, if ever justified via grilling.

**Verdict: strongest research-workflow candidate; adopt staged, relative-first.**

### earnings-preview (research / market-data)

Assembles earnings date, consensus EPS/revenue estimates, 4-quarter beat/miss record, analyst
targets into a pre-earnings briefing. For a buy-and-hold DCA portfolio the briefing itself is
peripheral; its one durable idea is *awareness of the next earnings date when timing a one-time
buy*. `next_earnings_date` is already in the fundamentals vocabulary (provider-dependent —
absent from Alpha Vantage free OVERVIEW). Estimates and beat/miss history are a whole new data
class with no store schema. **Verdict: skip the skill; consider surfacing `next_earnings_date`
as a plan-readiness warning input instead.**

### earnings-recap (research)

Post-earnings: actual vs estimate, price reaction vs the stock's typical earnings-day move,
4-quarter margin/growth trend, "what changed". This maps beautifully onto machinery finance-hub
already has: the research workflow's *source supersession* and thesis-note updates are exactly
"my candidate reported; refresh the thesis with cited facts". Price reaction is computable
deterministically from `fin_price_bars`; a fresh `fetch_fundamentals` call captures the new
margin/valuation state as citable envelopes; `supersede_source_link` + `set_research_note`
persist the refresh. Gap: EPS actual-vs-estimate needs earnings-history data (not stored — can
be omitted in v1 or cited from a manual source). **Verdict: strong candidate — a "post-earnings
thesis refresh" skill that is mostly orchestration of existing tools; also a natural fit for
eval seed C5 (source supersession).**

### estimate-analysis (research)

Estimate levels, 7/30/60/90-day revision trends, up/down revision breadth ratios, growth vs
sector. Entirely dependent on an estimates time-series data class finance-hub does not store,
and the payoff (revision momentum) is a trading signal, not a portfolio-management fact.
**Verdict: not a v1 candidate; revisit only if candidate review ever wants consensus context.**

### etf-premium (market-data)

Five sub-skills: single-ETF premium/discount vs NAV, multi-ETF comparison, screener, deep dive,
and a gamma-squeeze/GEX decomposition of premium surges. The last three are trading analytics.
The first — "is this ETF trading rich or cheap to NAV right now?" — is a legitimate pre-buy
check for a personal portfolio that holds bond/international/commodity ETFs. Gap: NAV is not in
the ETF fundamentals field set and yfinance NAV coverage is spotty; would need a NAV field on
the fundamentals pack and a tiny premium metric tool. **Verdict: adopt at most the single-ETF
premium check as a one-time-buy readiness input; exclude the decomposition/screener machinery.**

### options-payoff, saas-valuation-compression, sepa-strategy (rejected candidates)

- **options-payoff**: Black-Scholes payoff visualization for multi-leg options structures.
  Derivatives trading UI; finance-hub v1 has no options surface and personal PM here is
  buy-only equities/ETFs. Out of scope.
- **saas-valuation-compression**: round-to-round ARR-multiple compression for VC-backed private
  companies, data gathered by web search. Private-market analysis, no portfolio linkage. Out of
  scope.
- **sepa-strategy**: Minervini swing-trading system — stage analysis, trend template, VCP
  breakouts, stop-loss ladders, pyramiding. A trading methodology that directly conflicts with
  the strategy-promotion + DCA deployment model (allocation math belongs to
  `generate_deployment_plan`, not chart-pattern position sizing). Out of scope. Its only
  transferable atom — MA50/MA200 posture and 52-week range as *context* — is already stored by
  `fetch_fundamentals`.

### stock-correlation (strategy)

Pairwise return correlation, rolling correlation with regime conditioning, sector clustering,
and pair-trade discovery. Drop the pair-trading framing and what remains is the one analysis in
the whole repo that serves *portfolio construction*: "how correlated are my holdings/sleeves —
am I diversified or holding one bet five ways?" Inputs are fully covered: `fin_price_bars`
holds 1y daily closes for the holdings universe and `metrics.daily_returns` already exists.
Gap is small and well-shaped: a deterministic correlation tool (matrix over stored bars,
results persisted as metric rows with window/provenance), registered on the CLI/MCP surface,
then a "portfolio concentration review" skill orchestrating it against the active strategy's
sleeves. **Verdict: strongest strategy-workflow candidate; small tool gap, high fit.**

### stock-liquidity (planning)

Liquidity dashboard: bid-ask spread, ADTV/dollar volume, Amihud illiquidity, square-root-law
market impact, turnover. For personal-scale orders most of this is trader tooling, but the core
question — "can this one-time buy execute in a thin ETF/small cap without material impact?" —
is a reasonable plan-readiness concern. ADTV, dollar volume, and Amihud are computable from
volume already stored in `fin_price_bars`; spreads/depth would need quote data finance-hub does
not store (skip). **Verdict: medium — a small ADTV/dollar-volume metric tool feeding a
plan-readiness warning for one-time buys; not a standalone dashboard skill.**

## Excluded by ADR 0005 (listed, not analyzed)

Social readers and specialized data providers — trading/monitoring tooling, not personal
portfolio management:

- **discord-reader** — read-only Discord channel research via opencli.
- **twitter-reader** — read-only Twitter/X research via opencli.
- **telegram-reader** — read-only Telegram channel reader via tdl.
- **yc-reader** — Y Combinator company data via yc-oss API.
- **linkedin-reader** — read-only LinkedIn feed/job search via opencli (same social-reader class).
- **opencli-reader** — generic read-only fallback for 90+ opencli source adapters.
- **hormuz-strait** — Strait of Hormuz geopolitical/shipping/oil-impact monitoring.
- **hyperliquid-reader** — read-only Hyperliquid perp/spot crypto market reader.
- **tradingview-reader** — read-only TradingView desktop app reader via CDP.

Additional non-candidates in the same spirit:

- **finance-sentiment** — cross-platform social-sentiment scores via the Adanos API; a social
  data provider in all but name.
- **funda-data** — external Funda AI MCP/REST provider whose headline surface is *analyst-grade
  synthesis returned as prose* — precisely the ungrounded, uncitable analysis path ADR 0005
  forbids.
- **startup-analysis** — VC/job-offer/founder due-diligence framework for private companies;
  no portfolio linkage.
- **generative-ui** — widget/design-system tooling for Claude conversations; no finance content.
- **skill-creator** — meta-tooling for authoring skills; finance-hub follows its own
  `writing-great-skills` reference and ADR 0006 instead.

## Summary: strongest candidates

Ranked by fit × feasibility for personal portfolio management:

1. **stock-correlation → "portfolio concentration review" (strategy)** — the only analysis in
   the repo aimed at portfolio construction; inputs fully stored; needs one small registered
   correlation-metric tool.
2. **earnings-recap → "post-earnings thesis refresh" (research)** — mostly orchestration of
   existing tools (`fetch_fundamentals`, price bars, `supersede_source_link`,
   `set_research_note`); dovetails with eval seed C5.
3. **company-valuation → staged "candidate valuation" (research)** — relative-valuation leg is
   near-term feasible from stored fundamentals envelopes plus a small comparison tool; the DCF
   leg is a large, separately-grilled investment.
4. **stock-liquidity (sliver) → one-time-buy liquidity warning (planning)** — ADTV/Amihud from
   stored volume as a plan-readiness input, not a dashboard.
5. **etf-premium (sliver) → ETF premium check (market-data)** — worthwhile only if a NAV field
   is added to the ETF fundamentals pack.

Cross-cutting observation: three of the five depend on the market-data metric layer
(`prices`/`snapshot`/`metrics`) being **registered** on the CLI/MCP surface — today those are
internal Python seams only. Registering a small set of deterministic price/metric tools is the
common enabler for adopting anything from this menu, and per ADR 0006 each adopted skill ships
with at least one capability eval task per workflow it orchestrates.
