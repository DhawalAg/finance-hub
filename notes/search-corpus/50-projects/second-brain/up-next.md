---
tags:
  - type/project
  - status/seed
created: 2026-04-18
updated: 2026-04-19
---

# Up Next

## Immediate (This Week)

- [ ] Set up project scaffolding: Bun + TypeScript + Commander.js
- [ ] Configure OpenRouter API key and Vercel AI SDK integration
- [ ] Build A1: single-source search (Brave) — `brain search "<query>"`
- [ ] Validate: results display in <3 seconds, clean terminal output

## Next (After A1)

- [ ] Build A2: multi-source fan-out + query decomposition
  - Add GitHub Search API client
  - Add Twitter/X API client (free tier, user's own account)
  - Implement query decomposition planner call (OpenRouter, small/fast model)
  - Source abstraction interface: `SearchSource { search(query): Result[] }`
- [ ] Build A3: LLM scoring columns
  - Rubric-anchored scoring prompts
  - Chain-of-thought before score in Zod schema
  - Trace logging to JSON

## Backlog

- [ ] A4: Vault cross-reference (MiniSearch BM25 + URL matching)
- [ ] A5: Interactive REPL session (compare, skim, queue, refine)
- [ ] User-defined search lenses (Kagi-style config files)
- [ ] Assisted search mode (`brain search --assist`)
- [ ] Composability layer (patterns-as-files, fabric-style)

## References

- [[2026-04-18-search-flow-chunked-v1]] — Chunked build plan
- [[2026-04-18-agentic-search-flow]] — Full search funnel design
- [[2026-04-19-steelman-search-flow]] — Steelman analysis with tactical upgrades
- Brave Search API: https://brave.com/blog/most-powerful-search-api-for-ai/
