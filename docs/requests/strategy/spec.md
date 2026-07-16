# Finance Strategy & Deployment Recommendation — Working Spec

**Status:** Sharpened v1 contract; ready for PRD synthesis after final cross-doc checks
**Updated:** 2026-06-21

This spec defines the first strategy/deployment workflow: a reviewable, buy-only recommendation for
the next deployable-cash tranche. Detailed source material remains in
[`requirements-dump.md`](../../../notes/finance-corpus/00-inbox/requirements-dump.md), but this file is
now the durable strategy contract.

## 1. Workflow Target

Given CSV-supplied portfolio state, explicit `deployable_cash`, a DCA/one-time bucket split, an active
strategy, a research universe, and grounded market-data evidence, v1 proposes dollar allocations across
DCA and one-time buys.

V1 is a planning artifact only:

- buy-only recommendations;
- no trade execution;
- no sell/rebalance recommendations;
- no tax-aware/wash-sale/realized-gain workflows;
- no account-location optimization;
- no live brokerage/bank sync.

The recommended workflow is:

```text
Fidelity positions CSV -> portfolio snapshot
research + market data -> candidate evidence
active strategy + deployable_cash + buckets -> deployment_draft
deployment_draft -> plan_readiness_check -> explicit approval
manual trade execution outside the system
```

## 2. V1 Inputs

V1 uses explicit user-approved inputs:

- `portfolio_snapshot_id`;
- `portfolio_changed_after_snapshot`;
- active `strategy_version_id`;
- `deployable_cash`;
- `dca_budget`;
- `dca_cadence`, such as monthly;
- `one_time_buy_budget`;
- `benchmark_ticker`, defaulting to `SPY`;
- `risk_mode`: `conservative`, `balanced`, or `aggressive`;
- optional `candidate_tickers` to narrow a deployment draft;
- optional `exclude_tickers`.

Validation: `dca_budget + one_time_buy_budget <= deployable_cash`.

`deployable_cash` is the total dollars the user has approved for this plan, regardless of whether the
cash currently sits in brokerage, checking, savings, or elsewhere. Cash values present in the portfolio
snapshot are context only unless the user includes them in `deployable_cash`; the planner never assumes
brokerage cash is automatically deployable.

The supplied `deployable_cash` is assumed to be already net of cash reserves, emergency funds, and
near-term obligations. Reserve/capital-policy computation is deferred.

`dca_cadence` is memo context only. The planner may render "$X/month" or similar phrasing, but it does
not create schedules, reminders, or automated recurring investments.

`risk_mode` affects ranked reasoning and memo posture only, not allocation math. It cannot override
evidence gates, freshness blocks, explicit caps, or user exclusions.

## 3. Portfolio Snapshot Intake

Fidelity CSV export is the primary v1 account-state path. It is the secure/free portfolio-state
workflow until a sanctioned live account integration is worth paying for.

```text
Fidelity positions CSV
  -> FidelityPortfolioCsvAdapter
  -> canonical PortfolioSnapshot
  -> fin_portfolio_snapshots / fin_portfolio_positions
  -> deployment recommendation
```

The planner reads canonical snapshots, not Fidelity-specific CSV rows. Later integrations such as
SnapTrade or another sanctioned account aggregator must write the same canonical snapshot tables.

V1 canonical fields:

- `snapshot_id`;
- `as_of`;
- `source_adapter` (`fidelity_csv`, later `snaptrade`, etc.);
- `source_file`;
- `account_name`;
- `account_type`;
- `ticker`;
- `name`;
- `asset_type`;
- `quantity`;
- `market_value`;
- `cost_basis` when available;
- `cash_value` when applicable;
- `currency`;
- `source_row_hash`.

V1 stores account type/name, including separate Roth/IRA accounts when provided, but recommendations
are allocation-level only. The planner does not say which account should receive a buy.

Unsupported imported holdings count toward portfolio value, sleeve exposure, and concentration when a
market value is available, but they cannot receive DCA or one-time buy lines. If an unsupported
holding lacks market value, v1 surfaces a warning and excludes it from weight math. Manual
market-value overrides for unsupported holdings are out of scope.

Browser automation against Fidelity is out of scope because it creates credential, terms, 2FA, and
fragility risks.

## 4. Strategy Model

Strategy versions use:

```text
status = draft | active | archived
```

Only one strategy version may be active at a time. `deployment_draft` uses the active strategy unless
an explicit draft strategy is passed for review. `superseded` is a deployment-plan status, not a
strategy status.

A strategy version owns:

- sleeves;
- target weights;
- eligible instruments;
- the primary sleeve for each eligible ticker;
- explicit hard caps when the user supplies them.

Sleeves use target weight percentages (`sleeve_target_weight_pct`). An approved strategy version used
for `deployment_draft` must have sleeve targets summing to 100%. Draft strategies may be incomplete,
but they cannot drive dollar-denominated drafts until complete.

V1 does not support a cash sleeve. `deployable_cash` and unallocated cash are tracked separately from
strategy sleeve targets.

Research may tag a ticker to multiple themes, but promotion into strategy chooses one primary sleeve
per ticker for allocation math. ETFs are instruments, not sleeves; they must map to a sleeve like
stocks do.

## 5. Instrument Scope

V1 deployment recommendation lines support US-listed, USD-denominated stocks and ETFs only.

Out of scope for recommendation lines:

- crypto;
- options;
- bonds;
- mutual funds;
- non-US or non-USD instruments.

Unsupported holdings may still be represented as imported portfolio context.

Instrument classification is explicit metadata in shared `fin_instruments`, not ticker-name
inference:

```text
instrument_role = broad_market_etf | theme_etf | single_stock
```

Examples:

- VTI/SPY/ITOT may be marked `broad_market_etf`;
- SMH/ARKK/XLE are `theme_etf`.

## 6. Candidate Eligibility

A candidate may receive DCA or one-time dollars only when the system can attach the minimum evidence
pack:

- mapped theme/sleeve;
- latest price envelope;
- one year of daily price history when available, with an explicit waiver for newer tickers/IPOs/ETFs;
- 1m, 3m, 6m, and 1y return context;
- volatility, max drawdown, current drawdown, and 52-week-position context;
- portfolio weight impact after the proposed buy;
- cited research thesis.

Broad-market ETFs may use a compact ETF evidence pack instead of a full cited thesis. Single stocks
require a cited research thesis. Theme or sector ETFs require a cited thesis for the sleeve/theme they
express.

One-time buys require a higher bar: the minimum evidence pack plus basic valuation/fundamental context
and a written "why now" rationale. Without that higher bar, a candidate may be DCA-eligible but not
lump-sum eligible.

The compact v1 valuation/fundamental pack is provider-backed:

- stocks: revenue growth, margin/profitability signal, P/S or forward P/S, EV/EBITDA when available,
  debt/cash context, and next earnings date when available;
- ETFs: expense ratio, top holdings, sector/theme exposure, AUM/liquidity proxy, and 1y
  performance/tracking context versus a benchmark.

CSV/manual fundamentals remain an override and bootstrap path, not the primary workflow. Default
runner for the compact pack is EODHD until its free-tier cap is consumed; Alpha Vantage is the
spillover runner after that. Aggregator-sourced fundamentals are screening-grade, and high-conviction
or unusually large one-time buys later require filing-grounded confirmation. This pack is expected to
broaden after the first working recommendation loop proves which evidence is useful.

## 7. Capital Buckets And Recommendation Lines

DCA and one-time-buy budgets are separate buckets with separate eligibility gates. The planner does
not produce one blended allocation and leave cadence to interpretation.

Each recommendation line states its bucket. If a candidate qualifies for DCA but not one-time buys,
the plan says so explicitly.

The same ticker may appear in both DCA and one-time sections, but only as separate lines with separate
rationales:

- DCA line: explains gradual accumulation;
- one-time line: clears the higher evidence gate and includes a distinct "why now" rationale.

V1 drafts use dollar allocations only. They do not emit binding share-count instructions because
execution price, timing, and fractional-share support belong to the brokerage workflow. Estimated
shares can be added later only as clearly non-binding helper text.

Recommendations may leave part of `deployable_cash` unallocated. The planner must not force weak buys
just to exhaust the budget. Unallocated cash is tracked per bucket (`dca_unallocated`,
`one_time_unallocated`) plus total unallocated, with reasons such as failed evidence gates,
concentration warnings, lack of a "why now" case, or explicit user preference.

Default line policy:

- `minimum_line_amount = $100`;
- `max_dca_lines = 5`;
- `max_one_time_lines = 3`.

Sub-threshold amounts roll into bucket-specific unallocated cash or another eligible line. Additional
eligible candidates appear in the watchlist/do-not-buy section with ranking or gate rationale.

`exclude_tickers` removes tickers from DCA and one-time buy lines. Excluded tickers may still appear in
research/watchlist context and must appear in the memo with reason `excluded_by_user`. V1 does not
support force-including a ticker into buys.

## 8. Ranking, Benchmarks, And Warnings

V1 does not use:

- a blended ranking score;
- confidence labels such as high/medium/low;
- a hidden scoring model.

Recommendations use ranked reasoning with explicit factors such as target underweight, evidence gates
cleared, concentration impact, market setup, research conviction, and missing evidence.

`benchmark_ticker = SPY` by default. Benchmark-derived metrics are context, not hard eligibility
gates. Every recommendation or evidence appendix section that uses a benchmark-derived metric must
surface the benchmark ticker used. V1 supports one benchmark per plan; theme-specific benchmarks are
deferred to research theme configuration.

V1 does not model separate hard and soft caps. If the user supplies an explicit cap in the approved
strategy, the planner enforces it as a hard cap. If no cap is supplied, concentration concerns are
warnings only.

Default concentration warnings when no explicit cap exists:

- post-buy single ticker weight above 10% of portfolio value;
- post-buy sleeve/theme weight above target weight by more than 5 percentage points;
- missing or unknown sleeve/theme exposure when the recommendation relies on that exposure.

Unknown sleeve exposure thresholds are policy defaults:

- `unknown_sleeve_warning_pct = 5`;
- `unknown_sleeve_block_pct = 15`.

At more than 5% unknown exposure, add `UNKNOWN_SLEEVE_EXPOSURE`. At more than 15%, block
`deployment_draft` and allow `allocation_review` only. Store the effective policy values with each
generated plan and render threshold values in the memo when triggered.

## 9. Strategy Policy

Strategy policy is separate from strategy version.

Strategy version owns allocation intent:

- sleeves;
- target weights;
- eligible instruments.

Strategy policy owns configurable defaults:

- `minimum_line_amount`;
- `max_dca_lines`;
- `max_one_time_lines`;
- unknown sleeve exposure thresholds;
- price-move readiness thresholds;
- portfolio snapshot freshness bands;
- warning/block defaults.

Each generated plan stores a snapshot of the effective strategy policy values used. Future policy
changes must not reinterpret old plans.

## 10. Output Modes

V1 names outputs by decision strength rather than by capital bucket:

- `research_priorities`: what to investigate next across themes/candidates;
- `candidate_review`: portfolio-independent assessment of one candidate: thesis, evidence,
  market/fundamental context, gaps, and abstract DCA/one-time eligibility;
- `watchlist_review`: portfolio-independent ranking across candidates or a theme;
- `allocation_review`: portfolio-aware ranking/reasoning with no dollar amounts;
- `deployment_draft`: proposed dollars across DCA and/or one-time buckets, not approved;
- `plan_readiness_check`: pre-approval drift/validation check for a saved draft.

If a caller requests a stronger output than validation allows, the tool returns the strongest allowed
output mode plus blocked outputs. Example:

```text
requested_output = deployment_draft
portfolio_changed_after_snapshot = true
produced_output = allocation_review
status = advisory_only
blocked_outputs = deployment_draft, plan_readiness_check
```

`deployment_draft` defaults its candidate universe to the active strategy's eligible instruments.
Callers may pass `candidate_tickers` to narrow the run, but those tickers must already be eligible
active-strategy instruments. Tickers outside the active strategy can be explored through
`candidate_review`, `watchlist_review`, or `allocation_review`, but they cannot receive dollars until
promoted into strategy.

`allocation_review` may include non-strategy research/watchlist candidates because it has no dollar
amounts. It must label each candidate with `eligible_for_deployment` and `promotion_required`.
`allocation_review` requires a valid `portfolio_snapshot_id`; without one, the tool produces
`watchlist_review` and blocks `allocation_review` and `deployment_draft`.

`watchlist_review` can run on research evidence only. If market data is unavailable, it emits
`MARKET_DATA_MISSING`, avoids price/momentum/valuation claims, and surfaces the missing market-data
gaps.

`candidate_review` diagnoses readiness and gaps. It does not require a cited thesis, and it does not
browse, research, fetch missing data, or mutate state by default. It may return `status = incomplete`
with missing items such as cited thesis, fundamentals pack, or 1y price history. The agent can use that
gap list to propose follow-up research/data tool calls with user context.

## 11. Research Priorities And Gaps

Review and planning tools return `gaps[]` in structured JSON. `deployment_draft` persists the gaps it
used as plan warnings/evidence context when they affect the generated plan. V1 does not create a
dedicated `fin_candidate_gaps` table.

`research_priorities` is a deterministic gap-scan loop over current stored facts:

- active strategy;
- candidate universe;
- research notes/sources;
- market data;
- fundamentals;
- portfolio snapshot;
- recent plans.

It recomputes missing/stale evidence from those inputs rather than depending on ephemeral review
outputs. It then prioritizes computed gaps with this rubric:

1. Blocks `deployment_draft` for active strategy instruments.
2. Blocks one-time eligibility.
3. Blocks DCA eligibility.
4. Affects large or underweight sleeves.
5. Affects many candidates.
6. Stale or missing evidence for watchlist candidates.

Each priority points back to the stored fact, missing evidence type, stale evidence, or plan warning
that produced it. A dedicated gap table with `open | resolved | waived` lifecycle is deferred until
cross-session gap management proves useful.

## 12. Plan Statuses And Validation

V1 plan statuses:

- `proposed`;
- `proposed_with_warnings`;
- `advisory_only`;
- `blocked`;
- `approved`;
- `rejected`;
- `superseded`.

Plan warnings and blocks are deterministic tool outputs, not agent memory or prose advice. The
planning tool is the only path that creates recommendation rows:

```text
generate_deployment_plan(inputs)
  -> load portfolio_snapshot
  -> validate_snapshot_freshness(...)
  -> validate_candidate_evidence(...)
  -> validate_bucket_eligibility(...)
  -> compute_recommendation_lines(...)
  -> persist plan + warning/block rows
  -> return structured JSON
```

The agent renders the returned result; it does not decide whether to skip validation.

Initial warning/block codes:

- `PORTFOLIO_SNAPSHOT_STALE`;
- `PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME`;
- `PORTFOLIO_CHANGED_AFTER_SNAPSHOT`;
- `UNKNOWN_SLEEVE_EXPOSURE`;
- `MARKET_DATA_MISSING`.

A plan with any blocking row cannot be approved. Plans with warnings may be approved, and approval
persists the warnings that existed at approval time.

Approval requires explicit user intent such as `approve plan_001` or `mark plan_001 approved`. Casual
review language such as "looks good" or "sounds good" must not be interpreted as deployment approval.

## 13. Portfolio Snapshot Freshness

V1 uses deterministic freshness categories:

| Snapshot age | Category | Status | DCA | One-time buys | Approval behavior |
|---|---|---|---|---|---|
| 0-7 days | `fresh` | `proposed` | allowed | allowed | allowed |
| 8-14 days | `mildly_stale` | `proposed_with_warnings` + `PORTFOLIO_SNAPSHOT_STALE` | allowed | allowed | allowed with visible stale warning |
| 15-30 days | `stale` | `proposed_with_warnings` + `PORTFOLIO_SNAPSHOT_STALE` | allowed | draft only unless explicitly confirmed | DCA can be approved; one-time buys require explicit stale-snapshot confirmation |
| >30 days | `too_stale_for_one_time` | `blocked` for one-time-buy mode + `PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME` | stale-marked draft allowed | blocked | one-time buys cannot be approved; ask for a fresh Fidelity CSV |

Any known trade, deposit, withdrawal, or transfer after the snapshot adds
`PORTFOLIO_CHANGED_AFTER_SNAPSHOT`, sets status to `advisory_only`, and treats the snapshot as at least
`stale`. If `deployment_draft` is requested, the tool produces `allocation_review` instead. Blocked
outputs are `deployment_draft` and `plan_readiness_check`.

## 14. Plan Readiness Check

`plan_readiness_check(plan_id)` is a narrow pre-approval gate for a saved deployment draft, not a
second planning engine. It loads the immutable draft, re-runs current validation rules, refreshes
current price envelopes when allowed, and reports whether the draft is still approvable. It does not
recompute allocations or mutate draft lines.

Core input changes require a new `deployment_draft`:

- `portfolio_snapshot_id` changed;
- `strategy_version_id` changed;
- `deployable_cash` changed;
- `dca_budget` changed;
- `one_time_buy_budget` changed;
- `exclude_tickers` changed;
- requested scope changed.

V1 readiness outcomes:

- `still_approvable`;
- `approval_warning`;
- `approval_blocked`.

Readiness checks include snapshot freshness, `portfolio_changed_after_snapshot`, current
price-envelope freshness, price movement since draft, and required evidence availability. Price drift
uses deterministic thresholds:

- warn if latest price differs from draft price by more than 3%;
- block one-time approval and suggest a new draft if a one-time line differs by more than 7%.

If a required evidence reference is missing or invalid, block approval. If newer evidence exists, warn
but do not automatically block.

`plan_readiness_check` does not create a Markdown artifact by default. It returns structured JSON and a
terminal/Codex summary. Readiness output may be exported only when explicitly requested or useful for
debugging/audit.

## 15. Plan Lifecycle

V1 stops at recommendation approval. `approved` means the recommendation was approved for manual
action; it does not mean trades were placed. Execution tracking, fill prices, trade dates, account
placement, and post-trade reconciliation are deferred.

Plans are immutable once generated. A fresh Fidelity CSV creates a new `portfolio_snapshot_id` and a
new plan. Old plans may be marked `superseded` and linked with `supersedes_plan_id`, but they are never
silently upgraded in place.

Supersession is explicit: a new draft marks an old plan `superseded` only when generated with
`supersedes_plan_id` or when the user explicitly says the new draft replaces the old one. Multiple
alternative drafts may coexist.

Rejected plans do not generate a new Markdown memo by default. Mark the plan `rejected` in SQLite with
a short rejection reason; the existing draft memo remains the review artifact.

V1 does not include a first-class plan-comparison output or `compare_plans` tool. Stored plans make
ad-hoc agent summaries possible, but dedicated comparison waits until real drafts show which dimensions
matter.

## 16. Persistence And Evidence References

SQLite is canonical for structured deployment recommendation state. V1 stores:

- exact `portfolio_snapshot_id`;
- deployable cash, DCA budget, and one-time-buy budget;
- strategy version and target weights;
- effective strategy policy snapshot;
- recommendation lines and rationale summaries;
- warning/block rows;
- evidence references;
- approval status.

Do not keep manually edited prose numbers as canonical, provider raw payloads unless needed for
debug/audit, or every exploratory draft before a plan is generated.

Raw/evidence data is stored once. Deployment plans store references to the evidence they used.
Examples of source data stored once:

- portfolio snapshots in `fin_portfolio_snapshots` / `fin_portfolio_positions`;
- market bars in `fin_price_bars`;
- metrics in `fin_metrics`;
- fundamentals in the compact `fin_fundamentals` screening cache;
- research notes under `workspace/research/...`, with SQLite storing note pointers;
- research/source metadata in `fin_research_sources`.

Deployment-plan records use lightweight references:

```text
fin_deployment_plan_evidence
  line_id
  evidence_type       # price | metric | fundamental | research_note | research_source
  ref_table           # fin_price_bars | fin_metrics | fin_fundamentals | fin_research_notes | ...
  ref_key             # stable composite key/id for the row/file
  summary             # optional short human-readable label
```

The evidence appendix in a generated memo is rendered from these references. This lets the system
answer "why did we recommend this ticker?", compare old and new plans, audit which price/metric/source
was used at plan time, and regenerate memos from stored structured data without relying on agent
memory.

JSON is the interchange/test artifact. Planning tools return structured JSON so Codex, CLI, MCP,
tests, and future UI surfaces can consume one deterministic contract. Do not create JSON files for
every plan by default; export JSON only when requested, debugging, or creating regression fixtures.

## 17. Generated Markdown Artifacts

The `workspace/` tree is a private runtime artifact area ignored by git because it may contain
holdings, budgets, recommendations, and other personal financial context.

Default Markdown outputs:

```text
workspace/research/candidates/
workspace/research/watchlists/
workspace/research/priorities/
workspace/deployment/allocation-reviews/
workspace/deployment/drafts/
workspace/deployment/approved/
```

`candidate_review`, `watchlist_review`, `research_priorities`, `allocation_review`, and
`deployment_draft` generate Markdown by default. `plan_readiness_check` does not. Approved plans
generate a separate immutable approved memo; do not edit the draft memo in place to mark it approved.

Filename convention:

```text
workspace/deployment/drafts/2026-06-21_plan_001_deployment_draft.md
workspace/deployment/approved/2026-06-21_plan_001_approved.md
workspace/deployment/allocation-reviews/2026-06-21_allocation_review.md
workspace/research/candidates/2026-06-21_NVDA_candidate_review.md
workspace/research/watchlists/2026-06-21_ai_infra_watchlist_review.md
workspace/research/priorities/2026-06-21_research_priorities.md
```

Generated Markdown includes minimal front matter for identity/provenance only:

```yaml
---
generated: true
generated_by: finance.deployment_draft
generated_at: 2026-06-21T10:15:00-05:00
artifact_type: deployment_draft
plan_id: plan_001
portfolio_snapshot_id: snap_001
strategy_version_id: strat_v1
---
```

Do not use front matter as a database. Numbers, warning rows, evidence references, and plan state stay
in SQLite/tool output.

Every generated Markdown artifact includes a visible warning near the top:

```markdown
> GENERATED ARTIFACT - DO NOT EDIT AS SOURCE OF TRUTH.
> Regenerate this file from the finance tool that produced it.
```

## 18. Deployment Memo Shape

V1 deployment memos are generated from the stored plan:

1. **Status block**: requested output, produced output, plan status, snapshot freshness, warnings, and
   blocked outputs.
2. **Inputs used**: portfolio snapshot, strategy version, deployable cash, DCA budget,
   one-time-buy budget, research universe, and market-data/fundamental as-of dates.
3. **DCA lines**: ticker, dollar allocation, target sleeve, reason, evidence refs, risks, and missing
   evidence.
4. **One-time lines**: ticker, dollar allocation, "why now", valuation/fundamental context, evidence
   refs, risks, and missing evidence.
5. **Do-not-buy / watchlist**: candidate, reason, missing evidence, exclusion, or failed gate.
6. **Evidence appendix**: price refs, metric refs, fundamental refs, research-note refs, and research
   source refs.

## 19. Deferred Work

Deferred by design:

- trade execution and fill reconciliation;
- account-location optimization;
- sell/rebalance/tax workflows;
- live account integrations;
- strategy-design/capital-policy recommendations;
- DCA scheduling/automation;
- blended scoring models;
- confidence labels;
- theme-specific benchmarks;
- cash sleeve;
- hard/soft cap model;
- first-class plan comparison;
- structured candidate-gap table.

## 20. Responsibility

This spec owns:

- explicit promotion of approved [research](../research/spec.md) candidates into strategy;
- versioned strategies, sleeves, target weights, and eligible instruments;
- direct `deployable_cash` input now, with later capital-policy composition deferred;
- portfolio state and holdings as planner inputs, with Fidelity CSV first and live account acquisition
  deferred;
- deterministic deployment-recommendation arithmetic over strategy, capital, holdings, market data,
  fundamentals, and research evidence;
- plan persistence, generated artifacts, warning/block semantics, and approval lifecycle.

Research discovery does not mutate strategy state. Strategy authoring does not execute trades.
