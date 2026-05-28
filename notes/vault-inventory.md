# Vault Inventory — material relevant to hub-hub

Scan of `~/Documents/workspace/my-obsidian/` (486 .md total) for notes relevant to hub-hub
(search / outreach / research / finance hubs + the agentic spine + Obsidian-as-projection).
Paths below are relative to `my-obsidian/`. Excluded as noise: `venv/`, `01-daily/`,
most of `51-recruiting/` (interview prep, resumes), `60-writing/`, templates.

Last scanned: 2026-05-28. Status: **catalog only — not yet triaged. Decide next what to pull
into hub-hub.**

---

## Tier 1 — Agentic search engine design (directly on-point)

**`50-projects/agentic-search/`** — dedicated project folder, almost certainly the closest prior art:
- 00-raw-notes, 01-deep-dive-notes, 02-learning-roadmap, 03-outreach-and-career
- agentic-search.md, agentic-search-meta.md, agentic-search-meta-transcript.md, future-horizons.md

**`20-notes/ai/search/`** — the search knowledge base:
- adaptive-policy, agentic-search-state, behavioral-feedback-signals, composable-tools,
  hybrid-relevance-scoring, intent-conditioned-embeddings, multi-turn-reasoning,
  search-lexicon, session-memory, stateful-reasoning, strategy-selection
- `evaluation/`: agentic-eval-layers, convergence-rate, entropy-reduction,
  information-gain-per-iteration, strategy-diversity
- `production/`: cache-layers, flink-streams, production-metrics, query-routing,
  temporal-orchestrator, tiered-reasoning-economics

**`50-projects/second-brain/`** — likely a predecessor of this exact idea (knowledge harvest + search):
- `main/`: 00-index, 01-vision, 02-architecture, 03-tech-stack, 04-mvp-scope, 05-roadmap,
  06-user-flows, 07-build-in-public
- `dumps/`: 00-master-plan, 01-user-flow-v0, 02-steelman-and-reframe
- `search/`: real-world-data-search-pain-points
- `sessions/`: 2026-04-18-agentic-search-flow, 2026-04-18-search-flow-chunked-v1,
  2026-04-19-sdk-audit, 2026-04-19-steelman-search-flow, 2026-04-20-evals
- `idea-dumps/`: repl-flow, sources-people, recall-problem-zechner, 2026-04-19, list-videos
- rag-implentations.md, repos.md, up-next.md

**`00-inbox/`**: agentic-search-control-loop.md, better-search.md

**`20-notes/ai/ml-algos/`**: BM25, TF-IDF, knn  ·  **`20-notes/ai/context/`**: rag.md

---

## Tier 2 — Agentic spine / harness / tooling (the registry+MCP architecture)

**`20-notes/ai/context/12-factor-agents/`** — full 13-factor set + history + index (own-your-context,
tools-as-structured-outputs, unify-execution-state, launch-pause-resume, own-your-control-flow,
stateless-reducer, etc.) — directly relevant to the stateful tool design.

**`20-notes/ai/agents/`**: agent-kpis, agent-tooling, agentic-ai-landscape, effective-agent-design,
single-vs-multi-agent-reasoning

**`20-notes/ai/agentic-engineering-deep-dive/`**: agentic-coding-playbook, coding-guidelines, session-state

**`50-projects/agentic-loop-v1/`**: single-agent-harness, skills

**`00-inbox/`**: agent- harness.md, harness-engineering.md, scaffold-pi-agentic.md,
combined-workflow.md, combining-plugins-and-skills.md, plugins-tldr.md

**`30-references/`**: armin-ronacher-skills-vs-mcp.md, mcp-clipping.md, claude-skills.md
**`20-notes/ai/context/context-engineering.md`**

---

## Tier 3 — Per-hub material

**Outreach** — `20-notes/outreach/`:
- automation.md, linkedin-outreach.md, todo.md
- `copy/`: copywriting-101, follow-ups, grey-hat, linkedin, phrases, platform-specifics, subject-lines
- `scraping/`: linkedin, scraping-101

**Finance** — `00-inbox/finance-dump.md`, `00-inbox/trading.md`

**Lattice** (`50-projects/lattice/`) — a knowledge-model/creative-output product; overlaps with the
resource-DB + agentic-loop ideas. Most relevant: 09-agentic-loops, 11-knowledge-model,
12-creative-output-layer, 06-build-plan, 04-product-vision, AGENTS.md (plus full 00–12 brief set).

---

## Tier 4 — Stack & infra (feeds the stack decision)

- `20-notes/ai/ai-app-infrastructure-tools-2026.md`
- `20-notes/ai/foundations/ai-stack-landscape.md`
- `20-notes/ai/resources/ai-app-stack-2026.md`
- `30-references/system-design-101.md`
- `assets/agentic-frameworks.md`

---

## Tier 5 — Evals (search quality / agentic eval)

- `20-notes/ai/evals/evals-dump.md`
- `00-inbox/00-evals-hub.md`, `00-inbox/05-agentic-evals.md`
- `50-projects/second-brain/evals/` (00-evals-hub … 08-actionable-playbook — full set)
- `30-references/hamel-husain-llm-evals-faq.md`

---

## Tier 6 — Resource lists / harvest targets (examples of what the resource-DB collects)

- `20-notes/ai/resources/`: list-blogs, list-mcp, list-people, list-plugins, list-projects,
  list-repos, skills-research, staying-updated
- `40-people/`: armin-ronacher, simon-willison, steve-yegge
- `50-projects/projects-brainstorm/research-agent-finds.md`

---

## Tier 7 — Portfolio / strategy context (why hub-hub exists)

- `55-career-strategy/portfolio/`: project-ideas-backlog, project-portfolio-strategy,
  project-scorecard, project-wish-list
- `55-career-strategy/distribution/github-portfolio-plan.md`
- `50-projects/projects-brainstorm/_brainstorm-hub.md`, `50-projects/final-final.md`,
  `career-projects-wishlist.md`

---

## Vault mechanics (useful when building the `vault` projection driver)

- `90-system/how-to-use-this-vault.md`, `90-system/wiki-transform-state.md`
- `AGENTS.md`, `index.md` (vault root conventions)
