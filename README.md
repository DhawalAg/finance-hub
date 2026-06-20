# Finance Hub

Finance-focused agent tools exposed through a shared CLI/MCP tool runtime.

This repository keeps the useful runtime pattern from the earlier multi-hub scaffold:
plain Python functions register once, then become available to both a human-facing CLI
and an MCP server for agents. The domain is now finance only.

## Current Shape

```text
src/finance_hub/        installable Python package
docs/requests/finance/  request-scoped specs, plans, and generated design docs
notes/finance-corpus/   supporting finance source notes and raw intake
```

## Commands

After installing in editable mode:

```bash
pip install -e ".[dev]"
finance tools
finance run health
finance-mcp
```

## Design Rule

The runtime stays small and generic. Finance behavior lives under `src/finance_hub/`,
and specs/plans/todos stay in the relevant request folder under `docs/requests/finance/`.
