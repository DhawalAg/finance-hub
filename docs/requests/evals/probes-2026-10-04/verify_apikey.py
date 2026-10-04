"""No-LLM lockdown check: point the CLI at a local fake API that records the request
body (never headers) and returns a non-retryable 400. Captures the SystemMessage init
and what the model would have been sent (tools, system, first user message)."""
import asyncio, json, sys, tempfile, threading, shutil, dataclasses
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from claude_agent_sdk import query
from claude_agent_sdk.types import ClaudeAgentOptions, SystemMessage
from evals.harness import sdk_runner
from evals.harness.harness import _materialize_runtime_surface, _make_trial_env

MODE = sys.argv[1]  # "new" | "old"
OUT = Path(sys.argv[2])
bodies = []

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(n)
        try:
            bodies.append({"path": self.path, "body": json.loads(raw)})
        except Exception:
            bodies.append({"path": self.path, "raw_len": len(raw)})
        msg = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "fake api: lockdown probe"}}).encode()
        self.send_response(400); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(msg))); self.end_headers(); self.wfile.write(msg)
    def do_GET(self):
        self.send_response(404); self.end_headers()
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

td = Path(tempfile.mkdtemp(prefix="lockdown_probe_"))
_materialize_runtime_surface(td)
fixture_env = {"FINANCE_HUB_DB": str(td / "db.sqlite"), "FINANCE_HUB_WORKSPACE": str(td / "workspace")}
env = _make_trial_env({"id": "probe"}, td, fixture_env, "claude-sonnet-5", 2, td)
env.env.update({"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}", "ENABLE_TOOL_SEARCH": "true"})

if MODE.startswith("new"):
    sdk_runner.bridge_project_context(td)
    opts = sdk_runner.build_options(env)
else:  # pre-fix options, for the baseline
    opts = ClaudeAgentOptions(cwd=env.cwd, env=env.env, mcp_servers=env.mcp_servers,
        setting_sources=env.setting_sources, model=env.model, max_turns=env.max_turns,
        permission_mode="bypassPermissions")
opts.env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
opts.env["ENABLE_TOOL_SEARCH"] = "true"; opts.env["ANTHROPIC_API_KEY"] = ""
if MODE == "new_noenv": opts.env.pop("ENABLE_CLAUDEAI_MCP_SERVERS")
opts.extra_args["debug-file"] = str(OUT.with_suffix(".debug.log"))

init = None
async def main():
    global init
    async for m in query(prompt="probe", options=opts):
        if isinstance(m, SystemMessage) and m.subtype == "init":
            init = m.data
try:
    asyncio.run(asyncio.wait_for(main(), 90))
except Exception as e:
    print("query ended:", type(e).__name__, str(e)[:200])

res = {"init": init, "requests": []}
for b in bodies:
    body = b.get("body") or {}
    tools = [t.get("name") for t in body.get("tools", [])]
    sysblocks = body.get("system", [])
    systext = json.dumps(sysblocks)
    msgs = json.dumps(body.get("messages", []))
    res["requests"].append({"path": b["path"], "model": body.get("model"), "tools": tools,
        "deferred_tools": [t.get("name") for t in body.get("tools", []) if t.get("defer_loading")],
        "runtime_claude_md_in_context": "You are the finance-hub agent" in systext + msgs,
        "dev_claude_md_in_context": "Triage labels" in systext + msgs,
        "mentions_gmail": "gmail" in (systext + msgs + json.dumps(body.get("tools", []))).lower()})
res["raw_bodies"] = bodies
OUT.write_text(json.dumps(res, indent=1, default=str))
shutil.rmtree(td, ignore_errors=True)
print("written", OUT)
