# Finance Hub Agent Evals

Spec: [`docs/requests/evals/spec.md`](../docs/requests/evals/spec.md)

## Directory Layout

```
evals/
  tasks/              # Task definitions (one YAML per task; per-task golden/ subdir)
    R1.yaml
    R1/golden/        # Witnessed-run transcripts (§8.3)
    R3.yaml
    R5.yaml
    R7.yaml
    R10.yaml
  fixtures/           # Fixture build scripts (scripts only; materialized DBs are .gitignored)
  rubrics/            # Versioned LLM-judge rubrics (§6.3)
  harness/            # Runner, grader registry, report (Phase 1 — not yet)
  results/            # Run artifacts — gitignored wholesale (§8.3)
```

## Phase Status

| Phase | Description | Status |
|---|---|---|
| 0 | Task collection (no code) | In progress — see below |
| 1 | Harness MVP (R1 end-to-end) | Not started |
| 2 | Trajectory + breadth | Not started |
| 3 | Judge + calibration | Not started |
| 4 | Capability frontier | Not started |

## Phase 0 Tasks Authored

| ID | Suite | Workflow | Status |
|---|---|---|---|
| R1 | regression | planning | Full (prompt + reference + golden run) |
| R3 | regression | research | Prompt + reference + judge-grader config |
| R5 | regression | planning | Prompt + reference |
| R7 | regression | chain | Prompt + reference |
| R10 | regression | planning | Prompt + reference |

Golden runs for R3, R5, R7, R10 are deferred to bulk-authoring (#42).

## Fixtures

Fixture scripts (Phase 1 deliverable) live under `evals/fixtures/`. Each fixture is a Python
script that runs real migrations and real tools against a temp DB — never hand-crafted SQL
(§5.2). The fixture name in each task YAML is the script's stem.

Fixture names authored in Phase 0:
- `fidelity_sample_csv` — for R1: empty migrated DB + sample CSV file
- `dca_ready_deployment` — for R5: portfolio snapshot + active strategy + price bars
- `chain_quickstart` — for R7: minimal state for the full chain (no snapshot yet)
- `instrument_candidate_aapl` — for R3: AAPL registered as candidate, empty thesis
- `plan_with_block_warning` — for R10: plan with block-severity UNKNOWN_SLEEVE_EXPOSURE

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
Current rubrics: `thesis_quality_v1.yaml` (used by R3).

Calibration happens at Phase 3: SME reviews sampled judge verdicts and tunes thresholds.
