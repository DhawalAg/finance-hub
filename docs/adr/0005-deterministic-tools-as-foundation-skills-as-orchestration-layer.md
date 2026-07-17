# 0005 Deterministic Tools As Foundation, Skills As Orchestration Layer

Date: 2026-07-04

## Status

Accepted

> 2026-07-16: the skill definition-of-done is extended by
> [ADR 0006](0006-skills-ship-with-capability-eval-tasks.md) — skills ship with capability eval
> tasks.
> 2026-07-17: skills' physical home is fixed by
> [ADR 0007](0007-runtime-surface-lives-in-a-top-level-runtime-directory.md) — the runtime surface,
> skills included, lives under a top-level `runtime/`.

## Context

Agent-facing finance systems can be built at two layers, and it is tempting to treat them as
alternatives:

- **Tools** — deterministic Python functions in the shared registry, exposed through the CLI and MCP
  server. They own math and facts; the store owns durable records; plans cite evidence references
  (see ADR 0001–0004).
- **Skills** — on-demand folders of procedural instructions (plus optional scripts) that tell an
  agent *when and how* to orchestrate tools and reasoning into a workflow.

Existing skill libraries for financial analysis exist and are attractive as a shortcut. The reference
case examined was [`himself65/finance-skills`](https://github.com/himself65/finance-skills). Its
`finance-market-analysis` skills are built on **yfinance**, which finance-hub already lazy-wires, so
there is real overlap. However, those skills perform computation inline and do not persist results to
a durable, citable evidence store. Adopting them as-is would reintroduce exactly the failure this repo
was built to prevent: the agent producing numbers with no grounded, referenceable source. It would
also violate the core invariant that the agent must not invent prices, metrics, budget facts, or
allocation math.

## Decision

Treat tools and skills as **complementary layers, not competitors**:

- **Deterministic tools remain the foundation.** Math lives in tools; facts live in the SQLite store;
  generated plans and memos cite evidence references. This grounding discipline is retained
  unchanged and is the repo's differentiator.
- **Skills are an orchestration layer on top.** A finance skill encodes a workflow (e.g. "review my
  allocation", "research a candidate") and must reach data and computation by **calling registered
  tools** and **writing to the store**, never by doing freehand analysis. A skill is a playbook over
  the tools, not a replacement for them.
- **Adapt, do not adopt, from external skill libraries.** `himself65/finance-skills` is used as a
  *menu of which analyses matter*, not as drop-in code. Only skills that serve personal portfolio
  management are candidates; each is rewritten to call finance-hub tools and persist evidence. The
  social-reader and specialized data-provider skills (Discord/Twitter/Telegram/YC, geopolitical,
  Hyperliquid, TradingView) are out of scope — they are trading/monitoring tooling, not personal
  portfolio management.
- **Scope skills through the normal flow.** Which skills to add is decided per idea via
  `/grill-with-docs`, so each skill's scope is justified before it is built (YAGNI). Authoring follows
  the `writing-great-skills` reference.

## Consequences

The tool/MCP core continues to guarantee that every number is grounded and citable. Skills can be
added incrementally without weakening that guarantee, because they are constrained to orchestrate
tools rather than compute independently. External skill libraries accelerate *what to build* without
dictating *how*, so their lack of an evidence store does not leak into finance-hub. The cost is that
adopted skills must be rewritten rather than copied, and each new skill carries an explicit scoping
step.
