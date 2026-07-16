# Finance Hub — Requirements Dump

Last updated: 2026-05-28
Status: raw intake + first sharpening pass (decisions below supersede the raw dump where they conflict)

---

## Decisions — sharpening pass (2026-05-28)

Captured after a working session. The raw dump (preserved below) is the origin; this
section is the current spec. Where they disagree, this section wins.

### The reframe that resizes the whole build

hub-hub is a **headless tool registry** — there is no UI; **Claude/the agent is the
frontend**. A capability is a plain Python function exposed over MCP. This draws a hard
line through the requirements, anchored by the existing north star ("any numeric
recommendation traces to imported data or a tool result, not model freehand"):

- **Tools own:** facts, numbers, persisted state, real data fetches, emitted artifacts —
  the things an LLM can't do reliably.
- **The agent owns at runtime:** judgment, document extraction, "guidance," strategy
  authoring, scenario reasoning — the things we'd be tempted to *code* and shouldn't.

Consequences (where the squeeze disappears):
- **Statement ingestion** needs no PDF parser. The agent reads the statement and calls
  `record_transactions(...)`; the tool only persists + categorizes deterministically.
- **"Cost-cutting guidance"** is not a tool — it's the agent reasoning over a
  `spending_summary()` tool. No build.
- **"DCA strategy builder"** is not a builder (no UI) — it's a *persisted strategy object*
  the agent helps author and downstream tools read.

### The emotional core (sets build order)

**The deployment decision itself** — the recurring "put $X into these names this
week/month" moment that fuses budget + thesis + market. The budgeting lens exists to make
that decision defensible; the reporting lens exists so it doesn't require grinding.

### First-class object

The **sleeve** = a thesis/theme with a target weight (e.g. `compute @ 25%`). It is the join
point between thesis, capital, and cadence. Tickers hang off sleeves; budget feeds sleeve
allocation. (Resolves the theme-vs-ticker-vs-portfolio open question.)

### State location

Follow the search-hub pattern: **SQLite owns the numbers** (transactions, weights, prices,
holdings, deployments); **markdown/vault owns the prose** (theses, research notes).

### Market data — the only real engineering-risk dependency

The deployment decision needs essentially one input: **current prices** (delayed is fine
for a weekly/monthly DCA cadence). Earnings calendars / fundamentals belong to the
reporting + research lenses, which rank below the planner.

- **Now: free, yfinance-class**, behind a single `finance.prices()` tool so a later
  swap is a one-file change.
- **Later, only if reporting needs it** and free data gets flaky: Tiingo (~$10/mo, clean
  EOD prices) or FMP (~$22/mo, adds fundamentals + earnings). Polygon (~$30+) is overkill
  for one user; Alpha Vantage free tier too rate-limited.

### Triage verdicts

| Raw req | Verdict | Note |
|---|---|---|
| 1 DCA strategy across themes | **Spine** | Data model (sleeves), not a builder. |
| 2 Instrument discovery | **Spine-ish** | Agent + web maps theme→tickers; tool persists watchlist. |
| 3 Company/instrument research | **Cheap via agent** | Tool persists note + earnings dates. |
| 5 Deployment planner | **Spine — the wedge / first slice** | The join of 1+2+7. |
| 7 Statement→budget | **Spine, high personal value** | Shrinks to persist+categorize. |
| 8 Cost-cutting guidance | **Free at runtime** | Agent over `spending_summary()`. |
| 6 Reporting + delivery | **Cheap, deferred** | One data tool; delivery via existing Gmail/Drive/Calendar MCP + harness cron. |
| 4 Hypotheses/simulations | **Defer** | Don't build, don't block. |
| — Excel/.xlsx | **Cut for now** | Plan is a markdown/JSON artifact; revisit only for Drive delivery. |

### First slice — deployment planner as the integrating contract

Build the planner first with its inputs stubbed; defining the join *forces* the budget and
strategy models to a precise shape. Then backfill the producers into a socket that exists.

```
plan_deployment(deployable_capital, cadence)   ← the join (deterministic arithmetic)
  reads:
    • deployable_capital  $ this cycle      → manual now, budget tool later
    • sleeves             theme→weight→tickers → set_strategy() now
    • holdings            current positions  → set_holdings() now
    • prices              current px/ticker  → finance.prices() (yfinance, the one real dep)
  returns:
    • buys: "$X → TICKER (Y shares)" moving the portfolio toward target weights
    • a drift table + rationale per buy (so the agent can reason on top)
```

Math: value portfolio per sleeve → target_$ = (current_value + deployable) × weight →
fund the most-underweight sleeves with this cycle's cash → split within sleeve → ÷ price =
shares. The agent layers judgment on top; every number traces to a tool result.

**Skeleton tools (~4, all on the existing spine, one external dep):**
`finance.set_strategy` / `get_strategy`, `finance.set_holdings` / `get_holdings`,
`finance.prices`, `finance.plan_deployment`. Budget lens later *produces* the
`deployable_capital` number the planner already consumes.

### Allocation policy (the one real product choice in the planner)

When a cycle's cash can't fill every underweight sleeve:
- **Underweight-first (DEFAULT):** fund the sleeves furthest below target first;
  self-correcting toward thesis weights. Classic disciplined DCA.
- **Proportional:** split by target weight regardless of drift; simpler, never
  self-corrects.

Build underweight-first as default; expose as a parameter.

### Planner contract — detailed

**Pure-math core.** `compute_plan(...)` takes plain data and returns a plan dict — no DB,
no network. The registered tool `finance.plan_deployment(...)` is a thin wrapper that loads
state, fetches prices, calls `compute_plan`, and records the result. This keeps the math
deterministic and unit-testable, and is what makes "every number traces to a tool result"
literally true.

**Input shapes (what the tools persist / accept):**

```jsonc
// set_strategy(sleeves)  — relative weights, normalized at plan time
[
  {"name": "compute", "target_weight": 25, "note": "buildout silicon",
   "instruments": [
     {"ticker": "NVDA", "type": "stock", "weight_within": 2},  // intra-sleeve weight optional
     {"ticker": "AMD",  "type": "stock"}                       // absent -> equal split
   ]},
  {"name": "energy", "target_weight": 20, "instruments": [{"ticker": "VST"}]}
]

// set_holdings(positions)
[{"ticker": "NVDA", "shares": 10, "cost_basis": 120.50}, {"ticker": "VST", "shares": 5}]
```

**Algorithm (underweight-first default):**

1. Load strategy + holdings; collect the ticker universe (sleeve instruments ∪ holdings).
2. Get prices for the universe (provider seam; `price_overrides` wins, else cache, else fetch).
3. Value each holding (`shares × price`); sum per sleeve via the ticker→sleeve map.
   Holdings in tickers not mapped to any sleeve → **unassigned bucket** (reported, not targeted).
4. `base = assigned_value + deployable_capital`. Normalize sleeve weights to fractions
   (`w / Σw`). `target_value[sleeve] = base × w`. `gap = target_value − current_value`.
5. **Allocate `deployable_capital` per policy:**
   - `underweight_first`: split across positive gaps proportional to gap, capped at each
     gap; if capital exceeds the total gap, distribute the surplus by target weight
     (so once everything hits target, you maintain weights). If nothing is underweight,
     fall straight through to target-weight split.
   - `proportional`: split by target weight, ignoring drift.
6. **Within a sleeve**, split its allocation across instruments by `weight_within` (equal if
   none given). Convert `$ → shares = dollars / price`; if `allow_fractional=false`, floor to
   whole shares and recompute dollars.
7. Emit `buys`, a `drift` table (current% → target% → post% with a one-line rationale per
   sleeve), `cash_unallocated` (rounding remainder), and `unassigned_holdings`.
8. Persist the whole plan to `fin_deployments` (history) unless `save=false`.

**Output schema (the artifact the agent renders):**

```jsonc
{
  "policy": "underweight_first", "cadence": "monthly",
  "deployable_capital": 2000.0, "portfolio_value_assigned": 8200.0,
  "base_for_targets": 10200.0,
  "drift": [{"sleeve":"compute","target_weight_pct":35.7,"current_value":3000,
             "current_pct":36.6,"target_value":3641,"gap":641,"deploy":641,
             "post_value":3641,"post_pct":35.7,"rationale":"underweight by $641"}],
  "buys": [{"ticker":"NVDA","sleeve":"compute","dollars":427.0,"shares":0.51,"price":837.2}],
  "allocated": 2000.0, "cash_unallocated": 0.0,
  "unassigned_holdings": [{"ticker":"SPY","value":1200.0}],
  "prices": {"NVDA":837.2}, "deployment_id": 7
}
```

### Parameterization scan

What plan_deployment (and the strategy model) should expose as knobs. **Status**: ✅ in the
first slice · ⏳ planned (cheap add) · 🔌 better as a plugin seam (see below).

| Parameter | Default | Status | Notes |
|---|---|---|---|
| `deployable_capital` | — (required) | ✅ | manual now; produced by the budget tool later (CapitalSource seam) |
| `cadence` | `"monthly"` | ✅ | metadata now; later drives scheduled runs |
| `policy` | `underweight_first` | ✅ 🔌 | allocation strategy — the main plugin seam |
| `allow_fractional` | `true` | ✅ | whole-share flooring when false |
| `price_overrides` | `null` | ✅ | offline / manual prices; also the escape hatch when a fetch fails |
| `max_price_age_minutes` | `1440` | ✅ | cache staleness tolerance (belongs to the data pipeline) |
| `save` | `true` | ✅ | record to deployment history or dry-run |
| `cash_buffer` | `0` | ⏳ | hold back $X or X% as reserve before allocating |
| `min_buy` | `0` | ⏳ | suppress sub-$N buys to avoid dust orders |
| `max_position_pct` | none | ⏳ 🔌 | concentration cap per ticker (a ConstraintSet rule) |
| `no_trade_band_pct` | `0` | ⏳ | skip sleeves within ±X% of target (reduce churn) |
| `include_unassigned_in_base` | `false` | ⏳ | whether off-strategy holdings count toward target base |
| `sell_to_rebalance` | `false` | ⏳ 🔌 | DCA is buy-only by default; trims are a different policy |
| intra-sleeve split mode | `weight_within`/equal | ✅ 🔌 | equal vs explicit weights vs future (momentum/dip) |
| sleeve min/max weight, "locked" | none | ⏳ | per-sleeve constraints in the strategy model |
| `as_of` date | now | ⏳ | historical pricing — unlocks backtests/simulations later |
| currency / FX | USD | ⏳ | only if non-USD instruments enter |

### Plugin / provider seams

The clean extension points. Each is a small interface the rest of the planner treats as a
black box — add a new implementation, register it, select by parameter/config.

1. **PriceProvider** 🔌 *(realized in first slice)* — `fetch(tickers) -> {ticker: price}`.
   Free yfinance now; Tiingo/FMP/manual later by swapping one function. Owned by the data
   pipeline spec.
2. **AllocationPolicy** 🔌 *(two realized: underweight_first, proportional)* —
   `(sleeves, holdings, prices, capital, params) -> {sleeve: dollars}`. Strategy pattern;
   future: momentum-tilt, equal-weight-sleeves, glidepath.
3. **IntraSleeveSplitter** 🔌 *(equal / weight_within realized)* — distributes a sleeve's
   dollars across its instruments. Future: dip-weighted, conviction-weighted.
4. **CapitalSource** 🔌 *(manual realized)* — produces `deployable_capital`. This is the
   exact socket the **budget lens** plugs into later (`statement → spending → safe deploy $`).
5. **ConstraintSet** 🔌 *(planned)* — an ordered list of post-allocation filters
   (concentration cap, cash buffer, min-buy, no-trade band). Composable; each rule rewrites
   the allocation.
6. **ArtifactRenderer** 🔌 *(JSON realized; agent renders markdown)* — plan dict →
   markdown / CSV / (.xlsx only if Drive delivery is ever wanted). Kept out of the planner.

### Storage (first slice)

Finance owns its tables on the shared SQLite store (numbers live in SQLite per the state
decision), co-located with the finance code rather than bloating `core/store.py`:
`fin_sleeves`, `fin_instruments`, `fin_holdings`, `fin_prices` (cache), `fin_deployments`
(plan history — cheap recordkeeping that starts answering the "historical decisions" open
question).

### Data pipeline — sister spec

Price/data fetching is its own subsystem with its own decisions (source selection, fields,
cadence, caching, corporate actions, historical depth). It is specced separately so the
planner spec stays about the *join logic*:

→ **[data-pipeline-spec.md](./data-pipeline-spec.md)** (open questions to sharpen as we build).

The planner depends on it through exactly one seam (**PriceProvider**) and one parameter
(`price_overrides`), so the planner skeleton is fully buildable and testable before the
pipeline is sharpened.

### Research & financial-analysis lens — sister spec

Reqs 2 (instrument discovery) and 3 (company/instrument research) — plus the deferred
financial-analysis layers (fundamentals, filings, metrics) — are specced separately so this
master stays about the planner. The framing that makes it cohere: the research lens is the
**candidate-universe + evidence producer** for the planner: built top-down as *industry → key
players → deep research → explicit approval*. Approved candidates are promoted into versioned
planner strategy state; discovery never silently changes the buyable universe. On the budget side,
the active ingestion slice produces reconciled `historical_surplus` evidence; a later composition
layer turns that into planner-ready `deployable_capital`:

→ **[finance/research/spec.md](../../../requests/research/spec.md)** (open questions
R1–R15 to sharpen as we build).

Like the planner, the qualitative lens is fully buildable today on agent + persistence; every
quantitative dependency (metrics via `fin_metrics`, fundamentals via FMP, filings via edgartools)
sits behind a deferred seam.

---

## Working intent

Build the finance portion of `hub-hub` incrementally, using `@projects/finance-hub` as
the main reference point where it is useful, but tightening the product around how the
user actually wants to invest and budget.

This should be built functionality-by-functionality, not as a giant one-shot finance app.

## Main product lens

Two connected workstreams:

1. Investing lens
2. Budgeting lens

The budgeting lens should inform the investing lens by making the deployable investment
budget clearer and more defensible.

## Investing lens — raw requirements

### 1. DCA strategy builder across sectors / themes

Need a way to define a DCA-oriented investing strategy across themes such as:

- storage
- compute
- energy
- AI
- model providers
- infrastructure providers
- hyperscalers

Desired outcome:
- define target sectors / themes
- map those themes to investable instruments
- decide how much capital should go to each theme
- make the strategy explicit enough to deploy on a weekly or monthly cadence

### 2. Instrument discovery

From a theme / sector strategy, find relevant:

- stocks
- ETFs
- potentially other public-market instruments later

Desired outcome:
- move from abstract thesis areas to a concrete investable universe
- maintain a shortlist / watchlist per theme

### 3. Company and instrument research

Need workflows for:

- company research
- important dates like earnings calls
- important existing financial analysis from trusted sources
- investment strategy notes

Desired outcome:
- deep-dive research for a ticker or ETF
- a repeatable way to see what matters next
- a way to preserve trusted-source analysis and the user's own thesis

### 4. Hypotheses and simulations

Future workstream, intentionally vague for now:

- run hypotheses
- run simulations
- evaluate scenarios

This is not phase 1, but should remain in the requirements so the architecture does not
block it later.

### 5. Deployment strategy

Need the system to help define a:

- monthly deployment strategy
- weekly deployment strategy

Desired outcome:
- convert high-level strategy into an actual cadence
- determine what should be deployed this week or this month
- tie deployment decisions to budget constraints and current market context

### 6. Reporting and delivery

Need report generation and scheduled delivery, such as:

- weekly report for important dates in the coming week
- daily report for important dates in the coming day / near term
- movers, gainers, losers, and notable watch items
- delivery by email and/or an Excel file uploaded to Google Drive

Note:
- report generation is effectively its own workstream
- scheduling / distribution should probably come after the underlying data model and core
  analysis workflows exist

## Budgeting lens — raw requirements

### 7. Statement-driven investment budget

Need to ingest:

- credit card statements
- bank statements

Then assess:

- general spending
- realistic investment budget
- how much capital is safely deployable into the investment strategy

### 8. Cost-cutting and savings guidance

Need workflows to determine:

- where costs can be cut
- where spending can be reduced
- how budgeting can improve
- how the budget should inform investment deployment decisions

Desired outcome:
- a tighter feedback loop between actual cash flow and investment planning

## Product constraints and implications

- This is not just a portfolio tracker.
- This is not just a research assistant.
- This is not just a budgeting analyzer.
- The product should connect thesis -> instrument universe -> research -> deployment plan
  -> reporting, while grounding decisions in real budget capacity.

## Initial interpretation of build order

Likely early build slices:

1. Personal financial state and budget visibility
2. Investable universe / thesis mapping
3. Research and important-dates workflows
4. Deployment planning
5. Reporting and delivery automation
6. Simulations / hypotheses

This ordering is still provisional and should be challenged through follow-up questions.

## Open product questions

Resolved in the 2026-05-28 sharpening pass:

- ~~First-class object?~~ → **the sleeve** (thesis + target weight).
- ~~How opinionated vs decision-support?~~ → Moot: the **agent** carries opinion at
  runtime; **tools stay neutral/factual**. Don't bake opinion into code.
- ~~Report cadence to build first?~~ → Reporting deferred behind the planner entirely.

Still open (decide before the relevant slice, not now):

- Public equities only for v1, or leave room for ETFs/other instruments in the data model
  from day one? (Leaning: model `instrument {ticker, type}` so ETFs are free; defer
  anything non-public-market.)
- Deployment: pure recurring DCA, opportunistic buys, or hybrid? (The underweight-first
  planner is DCA-shaped; opportunistic tilts are the agent's judgment layer for now.)
- What counts as a trusted source for analysis? (Matters for the research lens, not the
  planner.)
- Budgeting: how much auto-categorization vs manual review of imported transactions?
- Historical recordkeeping depth for theses, reports, past deployments? (SQLite keeps
  deployment history cheaply; decide retention/auditing detail when the budget lens lands.)

## Notes for future implementation

- Reuse what already exists in `finance-hub` where possible, but do not inherit its prior
  assumptions blindly.
- Preserve a clean separation between:
  - raw imported financial data
  - generated analysis artifacts
  - user-authored strategy / thesis notes
  - scheduled report outputs
- Any future numeric investment recommendation should trace back to imported data or a
  tool result, not model freehand.
