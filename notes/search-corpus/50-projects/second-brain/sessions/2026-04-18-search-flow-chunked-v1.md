---
tags:
  - type/session
  - topic/search
  - topic/agents
  - status/seed
created: 2026-04-18
parent: "[[2026-04-18-agentic-search-flow]]"
---

# Search Flow — Chunked Build Plan v1

> Decomposition of Option A (Search → Score → Links) into shippable, testable increments. Each chunk is independently useful. PM sets scope, engineering executes.

---

## Decision Context

- Starting with search as the entry point, not ingestion
- Building outside-in: research experience first, knowledge model fills up through use
- Option A chosen: Search → Score → Compare. No extraction or ingestion yet.
- Each chunk should be a unit that can be built, tested, and used before the next one starts

---

## The Chunks

### A1: Single-Source Search + Raw Results

**What it does:**
One source (Brave Search), one query, flat list of results. No scoring, no grouping, no multi-select. Just:

```
$ brain search "agent memory architectures"

  Searching Brave...  10 results found.

  1. mem0ai/mem0 - Memory layer for AI agents
     https://github.com/mem0ai/mem0
     "Mem0 provides a smart, self-improving memory layer..."

  2. Building Agent Memory — latent.space
     https://www.latent.space/p/agent-memory
     "Memory is the missing piece in most agent architectures..."

  3. MemGPT: Towards LLMs as Operating Systems
     https://arxiv.org/abs/2310.08560
     "We introduce virtual context management for LLMs..."

  ...
```

**What it proves:**
- CLI scaffolding works (Commander.js, project structure, `brain` command)
- Brave Search API integration works
- Result parsing and display works
- The basic "query in, links out" loop is functional

**What it does NOT do:**
- No scoring columns
- No source grouping
- No multi-select or compare
- No vault cross-reference
- Single source only

**Engineering scope:**
- Project init (bun, TypeScript, Commander.js)
- Brave Search API client
- CLI command: `brain search "<query>"`
- Result formatter (terminal output)
- Basic error handling (API failures, rate limits)
- Environment config for API keys

**Definition of done:**
- `brain search "any query"` returns results from Brave in <3 seconds
- Results display cleanly in terminal with title, URL, snippet
- API key is configurable via env var, not hardcoded

---

### A2: Multi-Source Fan-Out + Query Decomposition

**What it does:**
Decomposes the user query into 3-5 sub-questions via a lightweight LLM planner call, then fans out across GitHub, Twitter/X, and Brave Search in parallel. Results grouped by source type — the tree view from the working doc.

```
$ brain search "agent memory architectures"

  Decomposing query... 4 sub-queries generated.
  Searching 3 sources... done (2.1s)
  34 results found.

  BRAVE WEB (10 results)
  ──────────────────────
   1. Building Agent Memory — latent.space
      https://www.latent.space/p/agent-memory
   2. Memory Patterns for LLM Agents — simonwillison.net
      https://simonwillison.net/2026/Mar/12/memory-patterns/
   ...

  GITHUB (12 results)
  ──────────────────────
   1. mem0ai/mem0 ★ 24.1k
      https://github.com/mem0ai/mem0
   2. langchain-ai/memory-patterns ★ 8.3k
      https://github.com/langchain-ai/memory-patterns
   ...

  TWITTER/X (12 results)
  ──────────────────────
   1. @karpathy: "Memory in agents is basically the same problem as..."
      https://x.com/karpathy/status/...
   2. @swyx: "Four memory patterns I keep seeing in production agents..."
      https://x.com/swyx/status/...
   ...

  [expand source]  [refine query]
```

**What it proves:**
- Query decomposition improves recall by covering multiple facets of a topic
- Parallel retrieval across multiple sources works
- Source-specific API clients are composable (add a source, get results)
- Grouped display UX works in the terminal
- Source configuration pattern is established

**What it adds over A1:**
- Query decomposition via a lightweight LLM planner call (small/fast model via OpenRouter, structured output, ~1s)
- GitHub Search API client (repos + README search)
- Twitter/X API client (recent search, user tweets)
- Source abstraction layer (common interface for any source)
- Parallel fan-out (concurrent API calls)
- Grouped tree-view display
- Source-specific metadata (stars for GitHub, author for blogs, engagement for Twitter/X)

**Engineering scope:**
- Query decomposition module using Vercel AI SDK + OpenRouter, structured output via Zod schema returning `{ subQueries: string[] }`
- GitHub Search API client
- X API client (Twitter API v2, free tier for testing)
- Source interface: `SearchSource { search(query): Result[] }`
- Parallel execution (Promise.all or similar)
- Grouped terminal output formatter
- Source-specific result metadata

**Definition of done:**
- Query decomposition produces 3-5 relevant sub-queries for a given input
- `brain search "any query"` returns results from Brave, GitHub, and Twitter/X
- Results are grouped by source with clear visual separation
- Adding a new source means implementing one interface, not touching core logic
- Total search time < 5 seconds for 3 sources

---

### A3: Scoring Columns

**What it does:**
Adds per-result scoring across multiple dimensions. This is where the LLM enters the loop — it evaluates and scores results. Display shifts from a simple list to a table with scoring columns.

```
$ brain search "agent memory architectures"

  Searching 2 sources... scoring results... done (4.1s)

  BRAVE WEB (10 results)
  ┌─────┬──────────────────────────────────────┬───────┬─────────┬───────┐
  │  #  │ Title                                │ Rel.  │ Recency │ Depth │
  ├─────┼──────────────────────────────────────┼───────┼─────────┼───────┤
  │  1  │ Building Agent Memory — latent.space │ 0.92  │ 5d ago  │ deep  │
  │  2  │ Memory Patterns — simonwillison.net  │ 0.87  │ 2w ago  │ mid   │
  │  3  │ Agent Memory 101 — medium.com        │ 0.71  │ 1mo ago │ light │
  └─────┴──────────────────────────────────────┴───────┴─────────┴───────┘

  GITHUB (12 results)
  ┌─────┬──────────────────────────────────────┬───────┬────────┬─────────┐
  │  #  │ Repo                                 │ Rel.  │ Stars  │ Recency │
  ├─────┼──────────────────────────────────────┼───────┼────────┼─────────┤
  │  1  │ mem0ai/mem0                          │ 0.92  │ 24.1k  │ 2d ago  │
  │  2  │ langchain-ai/memory-patterns         │ 0.87  │ 8.3k   │ 1w ago  │
  └─────┴──────────────────────────────────────┴───────┴────────┴─────────┘
```

**What it proves:**
- LLM-based relevance scoring works and is calibrated enough to be useful
- Source-specific scoring columns are renderable in the terminal
- The dual-purpose insight works: scores inform the user AND log as eval traces

**What it adds over A2:**
- LLM relevance scoring (batch-score results against query)
- Source-specific metadata scoring (recency from timestamps, authority from stars/citations)
- Depth estimation (LLM classifies: light / mid / deep based on snippet + metadata)
- Tabular display with aligned columns
- Trace logging: every score + reasoning written to a JSON log file

**Engineering scope:**
- Scoring module: `scoreResults(query, results[]): ScoredResult[]`
- LLM integration for relevance scoring (Vercel AI SDK + Claude)
- Source-specific metadata extractors (date parsing, star counts, etc.)
- Table formatter for terminal (cli-table3 or hand-rolled)
- JSON trace logger (append-only file, one entry per search session)

**Key design decision:**
Scoring columns vary per source type:

| Source | Columns |
|--------|---------|
| Brave Web | Relevance, Recency, Depth |
| GitHub | Relevance, Stars, Recency, Language |
| Substack | Relevance, Author, Recency, Depth |
| Twitter/X | Relevance, Engagement, Recency |
| HuggingFace | Relevance, Downloads, Recency, Type (paper/model/dataset) |

**Model strategy:**
All LLM calls go through OpenRouter. During development/testing, use free-tier models via OpenRouter for flow validation. Production quality comes from swapping model IDs. Scoring prompts use rubric anchoring (3-4 calibration examples in the prompt) to work across model quality levels. Use a small/fast model for scoring, reserve more capable models for synthesis in A5. Include chain-of-thought reasoning before the score in the Zod schema (reasoning field before score field).

**Definition of done:**
- Results display with scoring columns in a clean table
- Relevance scores are LLM-generated and generally sensible (manual spot-check)
- Every search session produces a JSON trace file with query, results, and scores
- Scoring adds < 3 seconds to total search time (batch scoring, not per-result)

---

### A4: Vault Cross-Reference (Novelty Column)

**What it does:**
Adds the "NEW" vs "IN VAULT" indicator by comparing search results against existing vault content. This is the first connection between external search and internal knowledge.

```
  BRAVE WEB (10 results)
  ┌─────┬──────────────────────────────────────┬───────┬─────────┬──────────┐
  │  #  │ Title                                │ Rel.  │ Recency │ Novelty  │
  ├─────┼──────────────────────────────────────┼───────┼─────────┼──────────┤
  │  1  │ Building Agent Memory — latent.space │ 0.92  │ 5d ago  │ NEW      │
  │  2  │ MemGPT: LLMs as Operating Systems   │ 0.84  │ 3w ago  │ IN VAULT │
  │  3  │ Memory Patterns — simonwillison.net  │ 0.87  │ 2w ago  │ NEW      │
  └─────┴──────────────────────────────────────┴───────┴─────────┴──────────┘
```

**What it proves:**
- The system can tell you what you already know vs. what's new
- Vault indexing works (at minimum text-similarity matching against markdown files)
- The value proposition of "search that understands your knowledge state" starts to show

**What it adds over A3:**
- Vault indexer: scan vault markdown files, build a searchable index (BM25 or simple text matching)
- Cross-reference engine: compare each search result (URL, title, content snippet) against vault index
- Novelty column in display: NEW / IN VAULT / PARTIAL (mentioned but not ingested)
- Vault match detail: when IN VAULT, show which file(s) reference it

**Engineering scope:**
- Vault scanner: read markdown files, extract URLs, titles, key phrases
- Simple matching: URL-exact match + fuzzy title match + BM25 text similarity
- Novelty classifier: NEW (no match), IN VAULT (strong match), PARTIAL (weak match)
- Cache the vault index (don't rescan every search)

**Key design decision:**
This does NOT require the full knowledge model (SQLite, claims, relationships). It works at the file level — "does this URL or topic already appear in your vault?" The structured knowledge model comes later when ingestion is built.

**Trust rule:** Threshold the PARTIAL label conservatively. Default to NEW when the BM25 score is ambiguous. A missed IN VAULT is a minor inconvenience; a false IN VAULT erodes the tool's core promise. Additionally, weight vault matches by note type — a match in a curated reference note (`20-notes/`) carries more signal than a mention in a daily journal (`01-daily/`).

**Definition of done:**
- Results that already exist in the vault are marked IN VAULT
- The match is based on URL and/or content similarity, not just exact title match
- Vault index builds in < 10 seconds for a vault of ~500 files
- False positive rate (marking NEW as IN VAULT) is < 10% on manual spot-check

---

### A5: Compare + Reasoning

**What it does:**
Adds multi-select and side-by-side comparison with "why was this cited" reasoning. The CLI becomes interactive — a session, not a single command.

```
  > compare 1 3 5

  COMPARING 3 SOURCES
  ┌──────────────────────┬───────────────┬────────────────┬───────────────┐
  │                      │ latent.space  │ simonwillison  │ mem0/mem0     │
  ├──────────────────────┼───────────────┼────────────────┼───────────────┤
  │ Focus                │ Why memory    │ Practical      │ Reference     │
  │                      │ matters for   │ taxonomy of    │ implementa-   │
  │                      │ agent         │ 4 memory       │ tion of       │
  │                      │ adoption      │ patterns       │ persistent    │
  │                      │               │                │ memory layer  │
  ├──────────────────────┼───────────────┼────────────────┼───────────────┤
  │ Why cited            │ High-signal   │ Most complete  │ Most-used     │
  │                      │ analysis of   │ pattern        │ open-source   │
  │                      │ the space     │ taxonomy found │ memory lib    │
  ├──────────────────────┼───────────────┼────────────────┼───────────────┤
  │ Vault status         │ NEW           │ NEW            │ IN VAULT      │
  │                      │               │                │ (partial)     │
  ├──────────────────────┼───────────────┼────────────────┼───────────────┤
  │ Complements          │ Conceptual    │ Architectural  │ Code-level    │
  │                      │ framing       │ reference      │ detail        │
  └──────────────────────┴───────────────┴────────────────┴───────────────┘

  [skim #]  [queue for later]  [back to results]
```

**What it proves:**
- Interactive CLI session model works (the user stays in a search session, not one-shot commands)
- LLM can generate useful comparative reasoning across sources
- The UX feels like a research workstation, not a search engine

**What it adds over A4:**
- Interactive session mode (REPL-like: user issues sub-commands within a search session)
- Multi-select: user picks results by number
- LLM comparison generation: side-by-side analysis of selected sources
- "Why cited" reasoning per result
- Complementarity analysis: how do these sources relate to each other?
- Session state: the search results persist in memory while the user explores

**Engineering scope:**
- Session manager: maintain state across user interactions within one search
- Interactive prompt (inquirer or similar, or raw readline)
- Comparison prompt: send selected results to LLM for side-by-side analysis
- Table formatter for comparison view
- Sub-commands within session: `compare`, `skim`, `queue`, `back`, `refine`

**Definition of done:**
- User can multi-select results and see a comparison table
- Comparison includes: focus, why cited, vault status, complementarity
- Session persists — user can go back to results, compare different sets
- Sub-commands are discoverable (help text within session)

---

## Build Sequence Summary

```
A1 ─────► A2 ─────────────► A3 ─────► A4 ─────► A5
single    multi source       scoring   vault      compare
source    fan-out + query    columns   cross-ref  + reason
search    decomp             + LLM     + novelty  + session
          + Twitter/X

│         │                  │         │          │
│ proves: │ proves:          │ proves: │ proves:  │ proves:
│ plumbing│ source           │ LLM     │ internal │ research
│ works   │ abstraction +    │ scoring │ + extern │ workstation
│         │ sub-query        │ works   │ connected│ UX
│         │ decomposition    │         │          │
│         │ works            │         │          │
▼         ▼                  ▼         ▼          ▼
usable    usable             usable    usable     usable
day 1     day 1              day 1     day 1      day 1
```

Each chunk is independently shippable. A1 replaces "open browser, type query." A2 replaces "search GitHub and Twitter/X separately." A3 replaces "manually judge which results matter." A4 replaces "try to remember if I've read this before." A5 replaces "open 5 tabs and compare mentally."

---

## What Comes After A5

Once the search funnel (A1-A5) is working, the next chunks continue the pipeline:

- **B1: Source skimming** — fetch full content, show LLM-generated summary
- **B2: Claim/insight extraction** — pull structured claims from selected sources
- **B3: Basic persistence** — save extracted claims to SQLite (knowledge model begins)
- **B4: Relationship classification** — classify new claims against existing ones
- **B5: Backlog + background processing** — queue sources, process later

But those are future scope. A1-A5 is the current build.

---

## Steelman Upgrades Applied

Changes made to this plan based on the [[2026-04-19-steelman-search-flow|steelman analysis]] (2026-04-19):

1. **A2: Query decomposition added** — Lightweight planner call decomposes query into sub-questions before fan-out. Consensus architecture across Perplexity, gpt-researcher, STORM.
2. **A2: Twitter/X added as source** — Real-time discourse and emerging AI/agents patterns. X API free tier for testing.
3. **A3: Model strategy documented** — OpenRouter as API gateway. Free models for testing. Rubric-anchored scoring prompts. Chain-of-thought before score.
4. **A4: Conservative thresholding rule added** — Default to NEW when uncertain. Weight matches by note type.
5. **All chunks: OpenRouter as LLM provider** — Replaces direct Claude API calls. Enables free testing, easy model swapping.

---

*This decomposition is a working draft. Chunk boundaries may shift as we learn from building.*
