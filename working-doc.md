# hub-hub — Working Doc

Living scratchpad for stack + architecture decisions. Last updated: 2026-05-28.

## What hub-hub is today

A **headless agent-capability spine**: a single tool registry that hubs register into,
exposed through thin "drivers" that all read the same registry.

- `core/registry.py` — the spine. `@tool` decorator registers plain Python functions.
- `cli.py` — CLI driver (`typer`): a human runs `hub run <tool>`.
- `mcp_server.py` — MCP driver (`fastmcp`): an agent calls the tools.
- `core/store.py` — thin SQLite store, shared across hubs.
- `core/llm.py` — Anthropic.
- Hubs: `outreach`, `search`, `research`, `finance`.

There is **no UI**. The "frontend" is Claude / an agent calling the MCP tools.

## Stack decision

**Keep the Python core.** It's the right tool for MCP/agent tooling, the spine already
works, and rewriting to TypeScript only buys type-sharing with a frontend that doesn't
exist yet — premature.

Key reframe: **TanStack / Next.js are not alternatives to the Python backend.** They're a
web-UI layer hub-hub doesn't currently have. The question splits into two independent
decisions:

- **(A) Backend language** — Python stays.
- **(B) Web UI** — optional, deferred, and needed by at most one hub (see below).

### The HTTP adapter (the bridge)

The registry currently has two drivers (CLI, MCP). An **HTTP adapter** is a third driver
of the same shape: a tiny FastAPI server that loops over `registry.all_tools()` and
exposes each as `POST /tools/<name>` (JSON in → JSON out). ~30 lines, no new logic.

Why it matters: a browser can't speak CLI or MCP, but it speaks HTTP. The HTTP adapter is
the *only* new thing a JS frontend needs, and since it reads the same registry, capability
code is never duplicated. This keeps the frontend choice (Next vs TanStack vs none)
deferred and decoupled.

### Frontend options (only if/when a UI is wanted)

- **Next.js** — React, opinionated, easy Vercel deploy; strongest hiring signal.
- **TanStack Start / Router / Query** — younger, more explicit, less magic; "tracks where
  the ecosystem is going" signal. Query+Router fit client-state-heavy apps well.
- **Skip the SPA** — thin FastAPI/HTMX or small Vite+React dashboard.

## Per-hub plan

### search (agentic-search) — the real architecture driver

A **persistent, branching tree of search states with a feedback loop** — not one-shot.

- **Node** = a search context: `{query, inherited filters, applied facets, result set,
  cherry-picked/shortlisted items}`.
- **Edge** = a user action: refine (narrow), sort/curate, drill (open new avenue → child
  node), or traverse up (back to an ancestor).
- Tree is **long-lived and per-user**, accretes over time — effectively a personal
  knowledge graph that grows as the user explores.
- On a query, the system serves an initial set of **facets/filters** (dropdowns/toggles,
  Amazon/Google-search style). Applying them morphs results: refine / sort / curate /
  shortlist / open new avenues.
- **Cherry-picked items** are a relevance signal: feed forward to refine downstream
  results AND become the harvest.
- **Intake / materialize** = turn the shortlist into a per-user **resource DB** (articles,
  blogs, repos, HF links, tools, websites, people, company articles, industry reports).
- **Deep-run mode** = lock in all filters/preferences, dispatch an autonomous agent for a
  "one-and-done search on steroids."

Architecture: the whole loop is a set of **stateful tool calls** living in the Python
core's store + registry:

```
search.start(query)            -> node, proposed facets
search.facets(node)            -> the dropdowns/toggles for this context
search.refine(node, filters)   -> new result set (same node, narrowed)
search.drill(node, avenue)     -> child node (new rabbit-hole)
search.shortlist(node, items)  -> record relevance
search.goto(node_id)           -> traverse up/sideways the tree
search.materialize(session)    -> per-user resource DB
search.deep_run(preferences)   -> the "one-and-done on steroids" mode
```

Two consequences:
1. **Backend doesn't change — it grows a real domain model** (tree, nodes, preference
   profile, shortlists, resource DB) in the store. Search loop = more registered tools.
2. **Human traversal and the deep-run agent are two drivers over one tool set.** Human
   stops to think between calls; agent loops them itself. The "on steroids" mode is nearly
   free once the tools exist.

This is the **sole UI candidate** (tree + facets benefit from visuals; client-state-heavy,
fits TanStack Query/Router). CLI path stays working since the agent drives via the same
tools.

### outreach — headless

Automations producing **documents + DB rows** as artifacts. No UI. More registered tools.

### finance — headless

Automations / sandbox for simulations (far future). **Documents, Excel/CSV, Python
scripts, Jupyter notebooks.** No UI.

### research

(TBD — not yet detailed.)

## Obsidian vault — harvest + exploration layer (DECIDED: option A)

Adopt Obsidian as the **harvest + exploration surface**, not the engine.

Key fact: an Obsidian vault is just a folder of `.md` files with `[[wikilinks]]` + YAML
frontmatter. The graph view / backlinks / "netted matrix" are *renderings* of that link
structure. So:
- Any program can **write** the vault (plain file I/O) — `search.materialize()` writing
  notes + wikilinks is trivial.
- But Obsidian is a **viewer, not a runtime**: no headless mode, no real API by default.
  You write the files; Obsidian passively reflects them. You CANNOT click a graph node and
  trigger `search.drill()`. Obsidian gives the **map, not the controls.**

Therefore Obsidian is **not the search engine** — that's ours to build. A separate custom
UI layer for the live search controls may come later (future task). Obsidian is where the
user lands and *explores* accumulated results.

**Fork — DECIDED: option (A) vault as projection.** SQLite owns the live transactional
state (active tree, facets, preference profile); the vault is a generated, browse-mostly
projection materialized from it. (Rejected option B = markdown-as-database; loses
transactional queries and creates who-owns-truth conflicts.)

Implementation: a new `vault` driver — a fourth mouth on the registry alongside CLI / MCP /
HTTP — that projects nodes + resources + relationships into an Obsidian vault folder.

Caveats: keep a frontmatter convention to distinguish tree edges from similarity edges
(else the graph is a hairball); graph view degrades past ~tens of thousands of notes, so
cap what deep-run materializes into the vault vs. what stays in SQLite.

### Vault projection convention (draft)

Node note (`nodes/<id>.md`):
```yaml
---
kind: node
id: n_0042
query: "agentic search frameworks"
facets: {language: python, stars: ">500"}
parent: "[[n_0041]]"
relevance: 0.0
---
```
Resource note (`resources/<id>.md`):
```yaml
---
kind: resource
id: r_1337
type: repo          # repo | article | person | hf | tool | company | report
source: github
url: https://github.com/...
found_in: "[[n_0042]]"
shortlisted: true
---
```
Link conventions (use frontmatter `rel` so graph filters cleanly):
- `parent` / `found_in` → tree edges (structure).
- a `related: ["[[r_...]]"]` list → similarity / cross-links.
Dataview can then query e.g. all `kind: resource` where `shortlisted: true`.

## The carve

- Python core for all four hubs — unchanged, just more tools + a richer store.
- agentic-search gets the new domain model; engine is ours to build.
- SQLite = engine source of truth; Obsidian vault = browse-mostly projection (option A).
- Drivers on the registry: CLI, MCP, HTTP (bridge), + a `vault` projector.
- A custom UI layer for live search controls is a possible later task, not now.
- outreach + finance stay headless artifact factories.
- No monolithic frontend across the product.

## Open design questions (agentic-search)

1. **Facets**: fixed per-domain generators vs. LLM-proposed dynamic facets per query?
2. **Data sources** per "space" (GitHub API, HF API, web search, arXiv...) — the connector
   layer.
3. **Relevance feedback** mechanism: embedding re-rank vs. LLM exemplars vs.
   filter-inheritance down the tree?
4. **Single-user for now** (no auth)? (assumed yes)
5. Is the harvested **resource DB the product**, or a byproduct of the exploration
   experience? (Leaning: the vault/resource-DB is a real product artifact, since it's now
   the harvest surface.)
