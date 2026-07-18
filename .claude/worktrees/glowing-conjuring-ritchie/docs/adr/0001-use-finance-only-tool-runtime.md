# ADR 0001: Use A Finance-Only Tool Runtime

## Status

Accepted

## Context

The repo came from a broader multi-hub scaffold. The useful part is the runtime pattern: write a
plain Python function once, register it as a tool, and expose it through both a CLI and MCP server.

## Decision

Keep the runtime generic and finance-only:

- package code under `src/finance_hub/`;
- expose human usage through the `finance` CLI;
- expose agent usage through `finance-mcp`;
- keep domain behavior in finance package modules, not in the runtime registry itself.

## Consequences

The initial repo can stay small while remaining agent-ready. New finance slices should add focused
tools and tests without widening the runtime abstraction.
