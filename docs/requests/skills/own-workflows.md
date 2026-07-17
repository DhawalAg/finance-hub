# Skills Map — Inventory Of Finance-Hub's Own Workflows

**Status:** Research finding (wayfinder ticket #54, child of skills map #51)
**Updated:** 2026-07-17
**Sources:** `CONTEXT.md`, `README.md` quickstart, `docs/requests/README.md` (spec map),
`docs/requests/{research,strategy,market-data,ingestion,bootstrapping,evals}/spec.md`,
ADR 0005 / ADR 0006, and the live tool registry (`bin/finance tools`).

This is an internal inventory: the workflows finance-hub **already performs** — manually, via the
`finance` CLI, or via the MCP server — assessed as candidates for ADR-0005 skill orchestration.
Under ADR 0005 a skill is a playbook over registered tools (never freehand computation); under
ADR 0006 adopting one is a capability claim that ships with ≥1 eval task per orchestrated workflow
(or a declared no-mutation exemption).

## Registered Tool Surface (ground truth)

`bin/finance tools` lists **26 `finance.*` tools** plus `health`, grouped:

- **Research** (14): `set_theme`, `list_themes`, `get_theme`, `map_instruments`,
  `review_instrument`, `set_research_note`, `get_research_note`, `upsert_source`, `link_source`,
  `supersede_source_link`, `list_sources`, `sources_due_for_review`, `candidate_evidence`,
  `research_priorities`
- **Ingestion / snapshot intake** (1): `import_portfolio_csv`
- **Market data** (1): `fetch_fundamentals`
- **Strategy** (5): `promote_to_strategy`, `get_strategy`, `list_strategies`,
  `activate_strategy`, `check_strategy_deployable`
- **Planning** (5): `generate_deployment_plan`, `get_deployment_plan`, `plan_readiness_check`,
  `approve_deployment_plan`, `reject_deployment_plan`

**Registration gap (finding):** the price-envelope read `prices()` and the batch acquisition
`snapshot()` in `src/finance_hub/market_data/tools.py` are plain Python functions — **not
registered tools**. The README quickstart (step 7) says the price snapshot "is most naturally
driven by your MCP agent," but an MCP agent cannot call an unregistered function; today that step
requires a Python one-liner. Any market-data or chain skill is blocked on registering these (a
skill must reach data by *calling registered tools*, per ADR 0005). This should be resolved before
or alongside the first chain skill.

## Workflow Inventory

Categories use the eval spec's workflow taxonomy (`docs/requests/evals/spec.md` §5.1):
`research | market-data | strategy | planning | chain`. Eval overlap references the §10 seed
tasks (R1–R12 regression, C1–C8 capability). Durable outcome surfaces per workflow are §4.

| # | Workflow | Category | Registered tools touched | Eval overlap | Frequency / value |
|---|---|---|---|---|---|
| W1 | Setup verification & bootstrap | (setup; outside eval taxonomy) | none mutating — `finance check [--live]` CLI, `health` | none directly; precondition for every chain task | Once per install + after any config change; low frequency, high leverage when it runs |
| W2 | Portfolio snapshot import | planning | `import_portfolio_csv` | R1; feeds R7, C6 | Per Fidelity export (roughly per planning cycle) |
| W3 | Candidate research loop (theme → candidates → review → thesis) | research | `set_theme`, `map_instruments`, `review_instrument`, `set_research_note`, `upsert_source`, `link_source`, `get_theme`, `list_themes`, `get_research_note`, `list_sources` | R2, R3, R11, R12; C4 | Recurring, agent-driven; the prose-quality (L2) surface |
| W4 | Source hygiene & supersession | research | `sources_due_for_review`, `supersede_source_link`, `upsert_source`, `link_source`, `list_sources` | C5 | Periodic; keeps evidence citable instead of silently stale |
| W5 | Research readiness / gap scan | research (read-only) | `research_priorities`, `candidate_evidence` | Trajectory input to R4, R7, C2, C6 | Before every promotion and every plan; cheapest to skill |
| W6 | Price acquisition & envelope reads | market-data | **none registered** — `snapshot()` / `prices()` Python-only | Implicit in R5, R7, R8, R9 (frozen fixtures replace live calls) | Every planning cycle; blocked as a skill target until registered |
| W7 | Fundamentals fetch & screening | market-data | `fetch_fundamentals` (33 fields/call since PR #20), `candidate_evidence` | C1, C7 | New capability; quota-bound (Alpha Vantage free tier: 25 calls/day) |
| W8 | Strategy promotion & activation | strategy | `promote_to_strategy`, `activate_strategy`, `check_strategy_deployable`, `get_strategy`, `list_strategies` | R4; negative side of R12 | Infrequent but irreversible-ish (immutable versions); consistency matters most |
| W9 | DCA deployment plan chain (generate → readiness → approve) | planning / chain | `generate_deployment_plan`, `plan_readiness_check`, `approve_deployment_plan`, `reject_deployment_plan`, `get_deployment_plan`, `check_strategy_deployable` | R5, R6, R7, R9, R10; C3 | The recurring core loop (monthly DCA cadence); works end-to-end today |
| W10 | One-time-buy flow (fundamentals screen → eligibility → mixed plan) | chain | `fetch_fundamentals`, `candidate_evidence`, `generate_deployment_plan`, `plan_readiness_check`, `approve_deployment_plan` | C2, C3, C7; touches C6 | **The live frontier** (eval spec §1): just unlocked by the fundamentals HTTP client, PR #20; orchestration not yet hardened |
| W11 | Full research→plan chain for a new theme | chain | union of W3 + W8 + W9 | C6, R7 | Occasional (new theme adoption); the longest single flow |
| W12 | Statement ingestion → historical surplus | (ingestion; parked) | none yet registered | Explicitly out of eval scope (§12) | Parked with the ingestion slice; not a near-term skill candidate |

## Per-Workflow Notes: What A Skill Would Add

Ad-hoc orchestration already works for most of these (the README quickstart is proof for W2–W9).
A skill earns its place only where it adds *when-to-run guidance, ordering discipline, readiness
checks, or evidence-citation discipline* beyond what tool contracts already enforce.

### W1 — Setup verification

A guidance-only playbook: run `finance check` before any session touching providers, interpret
green/yellow/red (yellow is non-blocking for DCA; fundamentals/`ANTHROPIC_API_KEY` stay yellow
until wired), use `--live` before a real planning run, remediate in dependency order. Invokes no
mutating tools and produces no durable artifacts → qualifies for the ADR-0006 **declared
exemption**. Cheap to write, but also cheap to skip — the CLI's own remediation hints cover most
of it.

### W2 — Portfolio snapshot import

The tool already refuses to silently stamp `now` and returns rich buckets. A skill adds: when to
re-import (any real-world position change → new snapshot, per ADR 0004's immutable-snapshot rule),
how to react to `unsupported`/`skipped` buckets (surface, don't ignore), and the discipline of
carrying the returned `snapshot_id` forward instead of re-deriving state. Small; probably folded
into a chain skill rather than standalone. Measured by R1.

### W3 — Candidate research loop

The highest-value *quality* target. Tool contracts enforce the mechanical rules (conviction
requires a note — R11), but nothing enforces: citation discipline (every material thesis claim
backed by `[source:N]` from `upsert_source`/`link_source` — the L2 groundedness rubric),
thesis coverage (the key facts a competent thesis addresses — the C4 coverage rubric), and
**scope discipline** — research must never mutate strategy state (Boundary Decision 1, graded by
R12). A research skill is the natural home for the workflow the LLM-judge tier (§6.3) exists to
grade; skill quality shows up directly as R3/C4 judge-score deltas.

### W4 — Source hygiene

A skill adds cadence and ordering: run `sources_due_for_review` before any promotion or plan;
replace stale links via `supersede_source_link` (never delete — historical citations must stay
explainable); update the dependent note after supersession. Exactly the C5 task. Small enough to
be a section of the research skill rather than its own.

### W5 — Readiness / gap scan

Read-only pair (`research_priorities` + `candidate_evidence`) whose value is entirely
*when-to-run* knowledge: before promotion, before plan generation, and when choosing what to
research next (gaps are ranked by deployment-blocking impact). Qualifies for the ADR-0006
exemption. Its real payoff is as the **entry step of every chain skill** — the pattern the README
already teaches ("run research_priorities, then guide me…").

### W6 — Price acquisition

Not skillable today: `snapshot()`/`prices()` are unregistered (see finding above). Once
registered, the skill content is thin — take a snapshot before plan generation, check freshness
bands, respect the cache-first contract — and mostly merges into the W9 chain skill. The eval
suite sidesteps this via frozen fixtures, so the registration gap is invisible to R5/R7 fixtures
but very visible to real MCP use.

### W7 — Fundamentals fetch & screening

A skill adds quota-aware ordering (25 Alpha Vantage calls/day on the free tier: fetch for
one-time-eligible candidates first, not the whole universe), interpretation of the
availability/value/source/grade envelope, and the refusal path — missing fundamentals means a
reported gap, never an invented metric (C7). Fresh surface (PR #20), so conventions are not yet
habits; a skill sets them before bad patterns form. Measured by C1/C7.

### W8 — Strategy promotion & activation

Consistency-critical, low-frequency. A skill adds pre-flight ordering: `research_priorities` →
`candidate_evidence` per ticker → resolve source-review debt (W4) → `promote_to_strategy` with
explicit `confirm` → `activate_strategy` → `check_strategy_deployable` (weights sum to 100, one
active version). The tools enforce each step's contract; the skill enforces that the steps happen
and in that order. Measured by R4, with R12 guarding the boundary from the research side.

### W9 — DCA deployment plan chain

The canonical README quickstart chain and the regression suite's spine (R7). A skill adds the
gate disciplines the negative tasks grade: **readiness before approval** (never approve without
`plan_readiness_check`; `approval_blocked` stops the flow — R10), **degradation honesty**
(present a degraded output mode as degraded — R9), budget arithmetic left to the tool
(`dca_budget + one_time_buy_budget ≤ deployable_cash` is validated, not computed by the agent),
and evidence references that resolve (§6.1's "citations are real" check). Because this flow is
money-adjacent it is graded pass^k — consistency is the product, which is exactly what a playbook
buys.

### W10 — One-time-buy flow

The frontier workflow. Orchestration is genuinely new: fundamentals screening (W7) → one-time
eligibility via `candidate_evidence` gaps → mixed DCA/one-time plan generation → readiness (with
the stricter 7% drift block on one-time approval) → approval. No hardened manual pattern exists
yet, so a skill here is **eval-driven development** in the §1 sense: C2/C3/C7 define what "the
one-time-buy workflow works" means, and the skill is the attempt to pass them. This is the
strongest case for writing the skill *and* its tasks together per ADR 0006.

### W11 — Full new-theme chain

W3 + W8 + W9 composed (C6). Better served by chaining the three skills than by a monolith; its
eval task measures whether the composition holds without a dedicated playbook.

### W12 — Ingestion

Parked with the slice itself; eval spec §12 excludes it. Revisit only when the capital-policy
layer becomes real.

## Strongest Skill Candidates From Our Own Usage

Ranked by (value of added discipline) × (frequency) × (measurability today):

1. **One-time-buy orchestration (W10 + W7).** The live frontier: tools exist (PR #20), workflow
   conventions do not. Ships with C1/C2/C3/C7 as its ADR-0006 tasks — several are already in the
   seed list, so the marginal eval cost is near zero. Expected to start low; that is the point.
2. **DCA deployment chain (W9, absorbing W2/W5/W6 steps).** Highest-frequency real usage
   (monthly cadence) and money-adjacent, so pass^k consistency is the product. The regression
   suite (R5–R7, R9, R10) already measures it — a rare case where the skill's safety net predates
   the skill. Prerequisite: register `prices`/`snapshot` as tools.
3. **Candidate research playbook (W3 + W4).** Where skill guidance changes *quality*, not just
   ordering: citation discipline, thesis coverage, scope discipline. Measured by R2/R3/R11/R12
   plus the judge-graded C4/C5 — the only candidate whose value shows in L2 scores.
4. **Readiness & gap-scan guidance (W5 + W1).** Read-only, ADR-0006-exempt (with the exemption
   declared), trivially cheap, and reused as the entry step of every chain skill. A good first
   skill to exercise the adoption mechanics end-to-end at minimal risk — though C8 (first adopted
   skill exercised end-to-end) is better spent on a mutating candidate.

Two cross-cutting findings for the skills map:

- **Registration gap:** `prices()`/`snapshot()` must become registered tools before any
  market-data or chain skill can honestly claim ADR-0005 compliance (skills reach data by calling
  registered tools). The README's step 7 already over-promises MCP drivability here.
- **Skill-shape guidance:** most small workflows (W2, W4, W5, W6) want to be *sections of* the
  three big skills rather than standalone skills — each standalone skill carries ADR-0006 task
  cost, so composition is cheaper than proliferation.
