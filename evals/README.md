# Finance Hub Agent Evals

Spec: [`docs/requests/evals/spec.md`](../docs/requests/evals/spec.md)

## Directory Layout

```
evals/
  tasks/              # Task definitions (one YAML per task; per-task golden/ subdir)
    R1.yaml           R1/golden/
    R2.yaml           R2/golden/
    R3.yaml           R3/golden/
    R4.yaml           R4/golden/
    R5.yaml           R5/golden/
    R6.yaml           R6/golden/
    R7.yaml           R7/golden/
    R8.yaml           R8/golden/
    R9.yaml           R9/golden/
    R10.yaml          R10/golden/
    R11.yaml          R11/golden/
    R12.yaml          R12/golden/
    C1.yaml           C1/
    C2.yaml           C2/
    C3.yaml           C3/
    C4.yaml           C4/
    C5.yaml           C5/
    C6.yaml           C6/
    C7.yaml           C7/
    C8.yaml           C8/
  fixtures/           # Fixture build scripts (scripts only; materialized DBs are .gitignored)
  rubrics/            # Versioned LLM-judge rubrics (§6.3)
  harness/            # Runner, grader registry, report
  results/            # Run artifacts — gitignored wholesale (§8.3)
```

## Phase Status

| Phase | Description | Status |
|---|---|---|
| 0 | Task collection (no code) | Complete — all 12 regression tasks authored |
| 1 | Harness MVP (R1 end-to-end) | Complete — fixture, graders, harness, report |
| 2 | pass^3, concurrent trials, re-grading, per-run report | Complete — #46 |
| 3 | Trajectory + breadth | Not started |
| 4 | Judge + calibration | Complete — LLM-judge grader (#47) |
| 5 | Capability frontier | Complete — all 8 C-tasks authored (#49, #50) |

## Phase 0 Tasks Authored

| ID | Suite | Workflow | Status |
|---|---|---|---|
| R1 | regression | planning | Full (prompt + reference + golden run) |
| R2 | regression | research | Full (prompt + reference + golden run) |
| R3 | regression | research | Full (prompt + reference + judge config + golden run) |
| R4 | regression | strategy | Full (prompt + reference + golden run) |
| R5 | regression | planning | Full (prompt + reference + golden run) |
| R6 | regression | planning | Full (prompt + reference + golden run) |
| R7 | regression | chain | Full (prompt + reference + golden run) |
| R8 | regression | planning (negative) | Full (prompt + reference + golden run) |
| R9 | regression | planning (negative) | Full (prompt + reference + golden run) |
| R10 | regression | planning (negative) | Full (prompt + reference + golden run) |
| R11 | regression | research (negative) | Full (prompt + reference + golden run) |
| R12 | regression | research (negative) | Full (prompt + reference + golden run) |

All 12 regression tasks from spec §10 are authored. Each has: prompt, reference solution,
manual golden-run transcript, and ambiguity notes. Phase 0 complete.

## Phase 4/5 Capability Tasks (issues #49, #50)

| ID | Suite | Workflow | Status |
|---|---|---|---|
| C1 | capability | market-data | Full (prompt + reference + graders + fixture) |
| C2 | capability | planning | Full (prompt + reference + graders + fixture) |
| C3 | capability | planning | Full (prompt + reference + graders + fixture) |
| C4 | capability | research | Full (judge-graded: theme_brief_quality_v1) |
| C5 | capability | research | Full (prompt + reference + graders + fixture) |
| C6 | capability | chain | Full (prompt + reference + graders + fixture) |
| C7 | capability | planning (negative) | Full (prompt + reference + graders + fixture) |
| C8 | capability | research (skill placeholder) | Full (prompt + reference + graders + fixture) |

All 8 capability tasks from spec §10 are now authored. Golden transcripts deferred to each
task's migration-to-regression moment (spec §7). Frontier tasks are tagged pass@k — one good
run demonstrates the capability exists. Passing is not required; the frontier starts low.

**Migration and saturation policy (spec §7):** A capability task passing ~100% across k trials
and two SUT versions moves to regression. `emit_suite_report` flags regression tasks that have
passed 100% for ≥5 consecutive runs as a saturation signal — the capability suite needs new tasks.
Every `meta.json` records five versions: task_version, fixture_version, harness_version (plus
rubric_version + judge_version in verdict rows for judge-graded tasks).

## Fixtures

Fixture scripts (Phase 1 deliverable) live under `evals/fixtures/`. Each fixture is a Python
script that runs real migrations and real tools against a temp DB — never hand-crafted SQL
(§5.2). The fixture name in each task YAML is the script's stem.

Fixture names authored in Phase 0:
- `fidelity_sample_csv` — for R1: empty migrated DB + sample CSV file
- `dividend_growth_empty` — for R2: empty DB (all state created by agent)
- `instrument_candidate_aapl` — for R3: AAPL registered as candidate, empty thesis
- `approved_candidates_ready_for_promotion` — for R4: 3 approved research candidates
- `dca_ready_deployment` — for R5: portfolio snapshot + active strategy + price bars
- `proposed_plan_ready_for_approval` — for R6: proposed plan (no block warnings)
- `chain_quickstart` — for R7: minimal state for full chain (no snapshot, no strategy)
- `plan_ready_no_price_data` — for R8: strategy + snapshot, NO price bars in fin_price_bars
- `stale_portfolio_snapshot` — for R9: 20-day-old snapshot (stale band), with fresh prices
- `plan_with_block_warning` — for R10: plan with block-severity UNKNOWN_SLEEVE_EXPOSURE
- `theme_with_candidate_msft` — for R11: theme + MSFT as candidate (not yet reviewed)
- `active_strategy_with_research_candidates` — for R12: active strategy (VTI only) + research theme

Fixture names authored in Phase 4/5 (issues #49, #50):
- `fetch_fundamentals_fixture` — for C1: AAPL candidate + empty fundamentals + EODHD fixture
- `fundamentals_eligibility` — for C2: AAPL + pre-seeded fundamentals + active strategy
- `one_time_ready_deployment` — for C3: VTI + AAPL both fully eligible (DCA + one-time)
- `multi_instrument_theme_brief` — for C4: VTI + AAPL with sources + fundamentals in theme_c4
- `stale_source_workflow` — for C5: AAPL with one stale source link (review_after in past)
- `new_theme_chain` — for C6: fresh DB with price bars + snapshot; no themes/strategy yet
- `dca_ready_no_fundamentals` — for C7: VTI + AAPL DCA-eligible, NO fundamentals
- `skill_workflow_stub` — for C8: two candidate instruments in theme_c8, neither reviewed

## Task Format

Task files follow the §5.1 schema (YAML):
- `id`, `title`, `version` — stable identity
- `suite`, `workflow` — classification
- `fixture` — named fixture (+ inline description comment)
- `now` — frozen timestamp for FINANCE_HUB_NOW (§5.2)
- `prompt` — user message given to the agent
- `reference` — concrete expected outcome (SQL assertions, filesystem checks)
- `graders` — ordered list with per-task parameters and judge config where applicable
- `provenance` — where the task came from
- `ambiguity_notes` — captured ambiguities and how each was resolved (§11)

## Rubrics

LLM-judge rubrics live in `evals/rubrics/`. Each rubric is a versioned YAML file.

Current rubrics:
- `thesis_quality_v1.yaml` — used by R3 (single-instrument thesis: groundedness, coverage, source_quality)
- `theme_brief_quality_v1.yaml` — used by C4 (multi-instrument brief: coverage, groundedness, cross_instrument_synthesis)

Calibration: SME reviews sampled judge verdicts and tunes thresholds. A rubric or judge model
change is a version bump — prior results remain comparable via the rubric_version and judge_version
recorded in each verdict row.
