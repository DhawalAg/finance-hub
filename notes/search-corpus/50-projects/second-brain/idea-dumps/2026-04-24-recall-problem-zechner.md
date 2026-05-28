---
tags:
  - type/note
  - topic/search
  - topic/agents
created: 2026-04-24
source: "[[mario-zechner-slowing-the-fuck-down]]"
---

# The Recall Problem in Agentic Search

From Mario Zechner's "Thoughts on slowing the fuck down" — his observations about agents searching codebases apply directly to our search tool design.

## The Problem

Agents suffer from low recall when searching large information spaces:
- "The bigger the codebase, the lower the recall"
- Missing existing code → duplication, inconsistencies
- Context windows are the obvious bottleneck, but search tools *inherently miss things*
- Low recall is the root cause of most quality problems in agent output

## Implications for Our Search Tool

### This is our core problem to solve

If we're building a search tool for a second brain / knowledge vault, **recall is the metric that matters most**. A search tool that misses relevant notes is worse than no tool — it gives false confidence.

### Design considerations

- **Multi-strategy retrieval** is essential — BM25 alone will miss semantic matches, embeddings alone will miss exact keyword matches. This validates the hybrid approach in [[2026-04-19-steelman-search-flow]].
- **Vault cross-reference (A4)** becomes more important, not less — if the tool can surface "you already have a note about this," it prevents the duplication problem Zechner describes.
- **Confidence signaling** — when recall is uncertain, the tool should say so. Don't present 3 results as if they're exhaustive when there might be 30.
- **Human-in-the-loop refinement** — the REPL mode (A5) is the right instinct. Let the human steer the search when the first pass misses.

### What Zechner gets wrong (for us)

His framing assumes agents search *autonomously*. Our tool is human-directed — the user types the query, sees results, refines. That's a fundamentally different recall problem. We can compensate with:
- Transparent retrieval (show which sources were checked)
- Iterative refinement (REPL)
- Explicit coverage metrics ("searched N sources, M returned results")

## Related

- [[2026-04-18-agentic-search-flow]] — our search funnel design
- [[2026-04-19-steelman-search-flow]] — multi-strategy validation
- [[agentic-search-state]] — state management for recall tracking
