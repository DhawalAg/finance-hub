# Eval Suite Trigger Policy

Spec: §8.1 (pass^k policy + run triggers).

## When to run the regression suite

Run the regression suite **before adopting** any change to a versioned SUT component:

- **Model pin change** — different model name in the harness `model=` argument.
- **Runtime surface change** — any file named in `evals/materialization_list.txt`
  (`runtime/CLAUDE.md`, `runtime/mcp.json`, any future skill files).

A change is SUT-changing **iff** it changes the §8.3 prompt hash **or** the model pin.
No per-edit relevance judgments ("does this touch an evaluated flow?") — those rot into
silent regressions.

## How to check: hash comparison

The prompt hash is recorded in every run's `meta.json`:

```
evals/results/runs/<run_id>/meta.json  →  "prompt_hash": "<64-char hex>"
```

To compare:

1. Find the most recent run for the task you care about in `evals/results/runs/`.
2. Read its `prompt_hash`.
3. Materialise the runtime surface into a temp dir and compute:

```python
from evals.harness.harness import _materialize_runtime_surface, compute_prompt_hash
import tempfile, pathlib

with tempfile.TemporaryDirectory() as td:
    _materialize_runtime_surface(pathlib.Path(td))
    print(compute_prompt_hash(pathlib.Path(td)))
```

If the computed hash differs from the stored hash → the runtime surface changed → run
the suite before adopting.

## k=3, regression = pass^k

Run 3 concurrent trials per task. The regression suite gate is **pass^k** (all 3 must
pass). A drop from 100% to 70% still passes k=1 ~70% of the time; k=3 catches it.

Capability tasks use **pass@k** (at least 1 passes).

```python
from pathlib import Path
from evals.harness.harness import run
from evals.harness.runner import SDKRunner  # or CLIRunner for debug

runner = SDKRunner()
run_dir = run(Path("evals/tasks/R1.yaml"), runner, k=3)
```

## Carve-outs

- **Development k=1 hand-runs** (debugging, not gates) — never recorded as verdicts.
- **CI wiring** — out of scope for v1 (spec §9). The rule is manual, hash-detected,
  applied at each adoption boundary.
- **Escape hatch** — if quota pressure materialises, amend k or the trigger as an
  explicit data-backed decision (same pattern as the §27 budget policy).

## Standing habit

**Read transcripts every run.** Graders are verified by reading; grader bugs (rigid
matching, bypassable checks) are found by eyes, not more graders.
