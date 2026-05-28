---
tags:
  - type/project
  - topic/agents
  - status/seed
created: 2026-04-19
---

# People as Sources

When the second-brain search tool gains people-source support, these are the first candidates — writers who publish frequently, have deep archives, and whose signal-to-noise ratio justifies building dedicated source adapters or scrapers.

## Tier 1 — High Priority

| Person | Site / Feed | Why |
|--------|-------------|-----|
| Simon Willison | [simonwillison.net](https://simonwillison.net) | Prolific TILs + long-form; LLM tooling, agents, practical AI. Has RSS. See [[simon-willison]] |
| Steve Yegge | [steve-yegge.medium.com](https://steve-yegge.medium.com) | Vibe coding, agentic systems, strong opinions. See [[steve-yegge]] |

## Tier 2 — Worth Adding

| Person | Site / Feed | Why |
|--------|-------------|-----|
| Lilian Weng | [lilianweng.github.io](https://lilianweng.github.io) | Deep technical posts on agents, RAG, alignment. Slow cadence but high quality |
| Ethan Mollick | [oneusefulthing.org](https://www.oneusefulthing.org) | Research-grounded takes on AI in work and education |
| Andrej Karpathy | [karpathy.ai](https://karpathy.ai) + [YouTube](https://www.youtube.com/@AndrejKarpathy) | Foundations, LLM internals, teaching-first style |
| swyx (Shawn Wang) | [swyx.io](https://www.swyx.io) | AI engineering ecosystem, latent space podcast, community pulse |
| Ben Thompson | [stratechery.com](https://stratechery.com) | AI strategy + business model analysis (paywalled, but worth it) |

## Source Adapter Notes

- Simon Willison's site has clean RSS: `https://simonwillison.net/atom/everything/`
- TIL site also has RSS: `https://til.simonwillison.net/tils/feed.atom`
- Medium (Yegge) has RSS per author: `https://medium.com/feed/@steve-yegge`
- Lilian Weng's blog is Jekyll — straightforward to scrape or use RSS

## Related

- [[up-next]] — current build queue
- [[20-notes/ai/resources/list-people]] — master people list

