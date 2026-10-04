"""Capture raw MCP CallToolResult wire shapes against frozen eval fixtures."""
import asyncio, hashlib, json, os, sqlite3, sys, tempfile
from pathlib import Path

REPO = Path(str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(REPO))
os.chdir(REPO)
OUT = Path(os.environ["OUT"])
OUT.mkdir(parents=True, exist_ok=True)
LIVE_DB = REPO / "finance-hub.db"

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from evals.harness.harness import _build_fixture

NOW = "2026-06-23T12:00:00+00:00"

PLANS = {
    "C1": ("fetch_fundamentals_fixture", [
        ("finance.fetch_fundamentals", {"ticker": "AAPL"}),
        ("finance.candidate_evidence", {"ticker": "AAPL", "theme_key": "theme_c1"}),
        ("finance.import_portfolio_csv", {"csv_path": "fixture/does_not_exist.csv"}),  # error
        ("finance.no_such_tool", {}),  # unknown-tool error
        ("finance.fetch_fundamentals", {}),  # arg-validation error
    ]),
    "C2": ("fundamentals_eligibility", [
        ("finance.candidate_evidence", {"ticker": "AAPL", "theme_key": "theme_c2"}),
    ]),
    "C7": ("dca_ready_no_fundamentals", [
        ("finance.candidate_evidence", {"ticker": "AAPL", "theme_key": "theme_c7"}),
        ("finance.candidate_evidence", {"ticker": "VTI", "theme_key": "theme_c7"}),
        ("finance.generate_deployment_plan", {"portfolio_snapshot_id": "snap_c7_fixture",
            "strategy_version_id": "strat_c7_v1", "deployable_cash": "1000",
            "dca_budget": "700", "one_time_buy_budget": "300"}),
    ]),
    "R1": ("fidelity_sample_csv", [
        ("finance.import_portfolio_csv", {"csv_path": "fixture/fidelity_sample.csv"}),
    ]),
    "R6": ("proposed_plan_ready_for_approval", [
        ("finance.get_deployment_plan", {"plan_id": "plan_r6_fixture"}),
        ("finance.plan_readiness_check", {"plan_id": "plan_r6_fixture"}),
        ("finance.approve_deployment_plan", {"plan_id": "plan_r6_fixture"}),
        ("finance.approve_deployment_plan", {"plan_id": "plan_r6_fixture", "confirm": True}),
    ]),
    "R8": ("plan_ready_no_price_data", [
        ("finance.generate_deployment_plan", {"portfolio_snapshot_id": "snap_r8_fixture",
            "strategy_version_id": "strat_r8_v1", "deployable_cash": "1000", "dca_budget": "1000"}),
    ]),
}


def live_db_fingerprint():
    out = {}
    for p in [LIVE_DB, Path(str(LIVE_DB) + "-wal")]:
        if p.exists():
            st = p.stat()
            out[p.name] = {"mtime": st.st_mtime, "size": st.st_size,
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    return out


def dump(obj):
    return obj.model_dump(mode="json", by_alias=True, exclude_none=False)


async def run_task(task, fixture, calls, meta):
    td = Path(tempfile.mkdtemp(prefix=f"mcpgt_{task}_"))
    fx_env = _build_fixture(fixture, td)
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(fx_env)
    env["FINANCE_HUB_NOW"] = NOW
    params = StdioServerParameters(command=str(REPO / "py3env/bin/finance-mcp"), args=[],
                                   env=env, cwd=str(td))
    errlog = open(OUT / f"{task}__server_stderr.log", "w")
    tmeta = {"trial_dir": str(td), "fixture_env": fx_env, "calls": []}
    async with stdio_client(params, errlog=errlog) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            if task == "C1":
                tools = await s.list_tools()
                (OUT / "list_tools.json").write_text(json.dumps(dump(tools), indent=2))
                (OUT / "initialize.json").write_text(json.dumps(dump(init), indent=2))
            for i, (name, args) in enumerate(calls):
                try:
                    res = await s.call_tool(name, args)
                    raw = dump(res)
                except Exception as e:  # protocol-level error
                    raw = {"__client_exception__": f"{type(e).__name__}: {e}"}
                fn = OUT / f"{task}__{i:02d}__{name.replace('.', '_')}.json"
                fn.write_text(json.dumps({"tool": name, "args": args, "result": raw}, indent=2))
                tmeta["calls"].append(str(fn))
    errlog.close()
    # fixture DB evidence
    con = sqlite3.connect(fx_env["FINANCE_HUB_DB"])
    tbls = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    counts = {}
    for t in ["fin_portfolio_snapshots", "fin_fundamentals", "fin_deployment_plans", "fin_price_bars"]:
        if t in tbls:
            counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
    tmeta["fixture_db_counts_after"] = counts
    con.close()
    meta[task] = tmeta


async def main():
    meta = {"live_db_before": live_db_fingerprint()}
    for task, (fixture, calls) in PLANS.items():
        await run_task(task, fixture, calls, meta)
    meta["live_db_after"] = live_db_fingerprint()
    (OUT / "_meta.json").write_text(json.dumps(meta, indent=2))


asyncio.run(main())
