"""Ground-truth trial wrapper: runs harness.run() for one task, k=1, but
(a) tees every raw SDK message (incl. SystemMessage/thinking) to OUT/<task>_raw_sdk_messages.jsonl,
(b) dumps the harness Transcript to OUT/<task>_raw_transcript.jsonl right after runner.run returns,
(c) snapshots the trial dir (fixture DB, workspace) before harness cleanup,
(d) records any exception from run()."""
import dataclasses, json, shutil, sys, traceback
from pathlib import Path

OUT = Path(sys.argv[2])
TASK = sys.argv[1]
MODEL = sys.argv[3] if len(sys.argv) > 3 else None

import evals.harness.sdk_runner as sr
from evals.harness.harness import run
from evals.harness.sdk_runner import SDKRunner

_orig_query = sr.query
raw_f = open(OUT / f"{TASK}_raw_sdk_messages.jsonl", "w")

def _ser(m):
    try:
        d = dataclasses.asdict(m)
    except Exception:
        d = {"repr": repr(m)}
    return {"cls": type(m).__name__, "data": d}

async def tee_query(*a, **kw):
    opts = kw.get("options")
    raw_f.write(json.dumps({"cls": "__options__", "data": {
        "cwd": str(opts.cwd), "model": opts.model, "setting_sources": opts.setting_sources,
        "mcp_servers": opts.mcp_servers, "max_turns": opts.max_turns,
        "env_has_api_key": "ANTHROPIC_API_KEY" in (opts.env or {}),
        "env_FINANCE": {k: v for k, v in (opts.env or {}).items() if k.startswith("FINANCE")},
    }}, default=str) + "\n")
    async for m in _orig_query(*a, **kw):
        raw_f.write(json.dumps(_ser(m), default=str) + "\n"); raw_f.flush()
        yield m

sr.query = tee_query

class DumpingRunner(SDKRunner):
    async def run(self, prompt, env):
        t = await super().run(prompt, env)
        t.write_jsonl(OUT / f"{TASK}_raw_transcript.jsonl")
        snap = OUT / f"{TASK}_trial_dir_snapshot"
        shutil.copytree(env.cwd, snap, dirs_exist_ok=True)
        return t

kw = dict(k=1, results_root=OUT / "runs")
if MODEL:
    kw["model"] = MODEL
try:
    rd = run(Path(f"evals/tasks/{TASK}.yaml"), DumpingRunner(), **kw)
    print("RUN_DIR", rd)
except Exception:
    tb = traceback.format_exc()
    (OUT / f"{TASK}_run_exception.txt").write_text(tb)
    print("RUN_EXCEPTION\n" + tb)
finally:
    raw_f.close()
