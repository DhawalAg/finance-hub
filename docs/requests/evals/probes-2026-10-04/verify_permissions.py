"""No-LLM permission check: a fake API scripts tool_use turns; the real CLI executes
them under the runner's lockdown; the tool_results come back in the next request."""
import asyncio, json, sys, tempfile, threading, shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from claude_agent_sdk import query
from evals.harness import sdk_runner
from evals.harness.harness import _materialize_runtime_surface, _make_trial_env

OUT = Path(sys.argv[1])
SCRIPT = [  # one tool_use per turn, then end
    ("ToolSearch", {"query": "select:mcp__finance-hub__health", "max_results": 5}),
    ("mcp__finance-hub__health", {}),
    ("Bash", {"command": "echo PWNED > /tmp/lockdown_probe_pwned"}),
    ("Write", {"file_path": "/tmp/lockdown_probe_pwned2", "content": "x"}),
    ("mcp__claude_ai_Gmail__send_message", {"to": "nobody@example.com"}),
]
turn = {"n": 0}
results = []

def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()

def tool_turn(i, name, inp):
    tid = f"toolu_probe_{i}"
    return [
        {"type": "message_start", "message": {"id": f"msg_probe_{i}", "type": "message", "role": "assistant", "model": "claude-sonnet-5", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": tid, "name": name, "input": {}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(inp)}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ]

def text_turn(i):
    return [
        {"type": "message_start", "message": {"id": f"msg_probe_{i}", "type": "message", "role": "assistant", "model": "claude-sonnet-5", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "done"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ]

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if "/v1/messages" not in self.path or body.get("max_tokens", 0) < 100 or not body.get("stream"):
            # side requests (titles, token counting...): minimal error
            msg = b'{"type":"error","error":{"type":"invalid_request_error","message":"probe"}}'
            self.send_response(400); self.send_header("content-length", str(len(msg))); self.end_headers(); self.wfile.write(msg); return
        msgs = body.get("messages", [])
        seen = {r["tool_use_id"] for r in results}
        for m in msgs:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if b.get("type") == "tool_result" and b["tool_use_id"] not in seen:
                        results.append(b); seen.add(b["tool_use_id"])
        i = turn["n"]; turn["n"] += 1
        events = tool_turn(i, *SCRIPT[i]) if i < len(SCRIPT) else text_turn(i)
        data = sse(events)
        self.send_response(200); self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
td = Path(tempfile.mkdtemp(prefix="perm_probe_"))
_materialize_runtime_surface(td)
fixture_env = {"FINANCE_HUB_DB": str(td / "db.sqlite"), "FINANCE_HUB_WORKSPACE": str(td / "workspace")}
env = _make_trial_env({"id": "probe"}, td, fixture_env, "claude-sonnet-5", 10, td)
env.env.update({"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}", "ENABLE_TOOL_SEARCH": "true"})
opts = sdk_runner.build_options(env)
opts.extra_args["debug-file"] = str(OUT.with_suffix(".debug.log"))

tx = []
async def main():
    async for m in query(prompt="probe", options=opts):
        tx.append(type(m).__name__)
try:
    asyncio.run(asyncio.wait_for(main(), 120))
except Exception as e:
    print("query ended:", type(e).__name__, str(e)[:300])
OUT.write_text(json.dumps({"turns": turn["n"], "results": results, "msgs": tx}, indent=1))
print("pwned files:", Path("/tmp/lockdown_probe_pwned").exists(), Path("/tmp/lockdown_probe_pwned2").exists())
shutil.rmtree(td, ignore_errors=True)
