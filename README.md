# Finance Hub

Finance-focused agent tools exposed through a shared CLI/MCP tool runtime.

Plain Python functions register once, then become available to both a human-facing CLI
and an MCP server for agents. The domain is now finance only.

## Quickstart

Get from install to an approved DCA deployment plan in one pass.

> **DCA-only today.** One-time buys require a live fundamentals client (EODHD/Alpha
> Vantage) which is the immediate next step after this bootstrapping slice. DCA flows
> run end-to-end without it.

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Open .env and fill in ANTHROPIC_API_KEY if you plan to use the in-process
# LLM helper. All other variables have working defaults for a local DCA run.
```

### 3. Verify your setup

```bash
finance check
```

Each line reports green / yellow / red with a remediation hint. Yellow is non-blocking
for DCA (fundamentals and `ANTHROPIC_API_KEY` are always yellow until those slices land).
No red lines means you are ready to proceed.

Add `--live` to include a real price-provider ping:

```bash
finance check --live
```

### 4. Import your Fidelity portfolio

Export your positions from Fidelity as a CSV (`Portfolio_Positions_*.csv`), then:

```bash
finance run finance.import_portfolio_csv \
  --args '{"csv_path": "/path/to/Portfolio_Positions_Jun-23-2026.csv"}'
```

The tool auto-extracts `as_of` from the Fidelity "Date downloaded" footer line and
returns a summary of supported / cash / unsupported / skipped positions. Pass
`"as_of": "2026-06-23T15:42:00-04:00"` to override the timestamp.

### 5. Research (agent-driven via MCP or CLI)

Use `finance run` (or drive via MCP — see [MCP Setup](#mcp-setup)) to build out the
research layer. Typical sequence:

```bash
# Create a research theme
finance run finance.set_theme \
  --args '{"key": "us-large-cap", "display_name": "US Large Cap", "status": "watching"}'

# Attach candidate instruments
finance run finance.map_instruments \
  --args '{"theme_key": "us-large-cap", "instruments": [{"ticker": "WMT", "instrument_role": "single_stock"}, {"ticker": "NVDA", "instrument_role": "single_stock"}, {"ticker": "AVGO", "instrument_role": "single_stock"}]}'

# Mark candidates reviewed with conviction (a conviction score requires a note)
finance run finance.review_instrument \
  --args '{"theme_key": "us-large-cap", "ticker": "WMT", "status": "approved", "rationale": "defensive anchor", "conviction": 4, "conviction_note": "stable cash flows through cycles"}'

# Write a thesis note
finance run finance.set_research_note \
  --args '{"scope": "instrument", "key": "WMT", "body": "Recession-resilient, DCA priority."}'
```

Check what is missing before promoting:

```bash
finance run finance.research_priorities --args '{}'
```

### 6. Promote to strategy

```bash
finance run finance.promote_to_strategy --args '{
  "version_id": "v1",
  "sleeves": [{"sleeve_key": "core", "display_name": "Core", "target_weight_pct": 100}],
  "instruments": [
    {"ticker": "WMT", "primary_sleeve_key": "core"},
    {"ticker": "NVDA", "primary_sleeve_key": "core"}
  ],
  "confirm": true
}'
```

You choose the `version_id` (here `v1`); it is echoed back in the result. Activate it:

```bash
finance run finance.activate_strategy --args '{"version_id": "v1", "confirm": true}'
```

### 7. Take a price snapshot

Fetch current prices for all positions in the snapshot universe. This step is most
naturally driven by your MCP agent ("take a price snapshot for the current portfolio
holdings"), but can also be called directly from Python:

```python
from finance_hub.market_data.tools import snapshot
result = snapshot()
print(result)
```

### 8. Generate a deployment plan

```bash
finance run finance.generate_deployment_plan --args '{
  "strategy_version_id": "v1",
  "portfolio_snapshot_id": "<snapshot_id>",
  "deployable_cash": "5000.00",
  "dca_budget": "5000.00",
  "requested_output_mode": "deployment_draft"
}'
```

Note the `plan_id` returned.

### 9. Check plan readiness

```bash
finance run finance.plan_readiness_check --args '{"plan_id": "<plan_id>"}'
```

Status `still_approvable` means you are clear to approve. `approval_warning` proceeds
with caveats; `approval_blocked` requires fixing the flagged issues first.

### 10. Approve

```bash
finance run finance.approve_deployment_plan \
  --args '{"plan_id": "<plan_id>", "confirm": true}'
```

An immutable memo is written to `workspace/approved/`. The plan is now on record.

---

## MCP Setup

Register finance-hub as an MCP server so an agent (e.g. Claude) can drive the full
pipeline on your behalf. The `finance-mcp` server self-loads `.env` at startup — no
secrets go in the MCP config.

### Claude Desktop

Add the following entry to `~/Library/Application\ Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "finance-hub": {
      "command": "finance-mcp"
    }
  }
}
```

If `finance-mcp` is not on your `PATH` (e.g. installed inside a virtualenv), use the
absolute path:

```json
{
  "mcpServers": {
    "finance-hub": {
      "command": "/path/to/venv/bin/finance-mcp"
    }
  }
}
```

### Generic MCP clients (`.mcp.json`)

```json
{
  "mcpServers": {
    "finance-hub": {
      "command": "finance-mcp"
    }
  }
}
```

### What the agent can do

Once registered, the agent has access to the full tool surface (`finance tools` lists
them all). A typical prompt to kick off the full flow:

```
I've imported my Fidelity CSV. Please run research_priorities, then guide me through
building a DCA deployment plan for my portfolio.
```

The agent calls the registered tools (`finance.research_priorities`,
`finance.promote_to_strategy`, `finance.generate_deployment_plan`, etc.) and returns
structured results at each step.

---

## Current Shape

```text
src/finance_hub/        installable Python package
docs/requests/          durable finance specs and request-scoped plans
docs/notes/finance-corpus/   supporting finance source notes and raw intake
CONTEXT.md              domain glossary and current build map
docs/adr/               architecture decisions
```

## Commands

```bash
finance tools                              # list every registered tool
finance run <name> --args '<json>'         # invoke a tool with JSON kwargs
finance check [--live]                     # read-only setup diagnostic
finance-mcp                                # start the MCP server (stdio)
```

## Design Rule

The runtime stays small and generic. Finance behavior lives under `src/finance_hub/`,
and specs/plans/todos stay in the relevant request folder under `docs/requests/`.
