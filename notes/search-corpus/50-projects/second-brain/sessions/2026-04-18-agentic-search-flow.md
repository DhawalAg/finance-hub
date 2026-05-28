---
tags:
  - type/session
  - topic/search
  - topic/agents
  - status/seed
created: 2026-04-18
parent: "[[50-projects/second-brain/main/00-index]]"
---

# Session: Agentic Search Flow

> Working doc — brainstorming the search experience for Second Brain. This is a design exploration, not a spec.

---

## 1. The Idea in One Paragraph

Every search tool today — Perplexity, Brave, Google, even Claude with web search — treats search as a single-turn transaction: query in, results out. The user does all the hard work: scanning, evaluating, comparing, deciding what to read, extracting insights, and filing what they learned. Second Brain's search flow inverts this. It treats search as a **multi-turn, funnel-shaped process** where the system helps the user progressively narrow, evaluate, absorb, and integrate external knowledge into their structured knowledge base. The CLI becomes a research workstation, not a query box. Critically, the system decomposes each query into targeted sub-questions before fanning out to sources — the consensus architecture behind Perplexity, gpt-researcher, and STORM.

---

## 2. How This Fits the Broader Product

### The Discover → Absorb → Retrieve loop

The existing manifest ([[50-projects/second-brain/main/06-user-flows]]) defines four flows:

| Flow | What it does | Phase |
|------|-------------|-------|
| Flow 1: Ingest | Note → claims → relationships → conflicts | MVP |
| Flow 2: Query Knowledge | "What do I know about X?" → honest assessment | Phase 2-3 |
| Flow 3: Search + Absorb | External search → cross-reference vault → ingest selected | Phase 3-4 |
| Flow 4: Proactive Briefing | System-initiated knowledge state diffs | Phase 4-5 |

**The agentic search flow replaces and significantly expands Flow 3.** The current Flow 3 spec is thin — it's basically "web search + vault cross-reference + ingestion pipeline." The inbox note (`better-search.md`) and the research corpus (`20-notes/ai/search/`) describe something much richer: a **multi-stage research funnel with its own UX, scoring system, and feedback loops.**

### What changes in the manifest

1. **Flow 3 becomes a first-class experience**, not a bridge between Flow 2 and Flow 1. It has its own multi-step UX, its own state management, and its own eval surface.
2. **The search module (Layer 2b) grows.** The architecture currently scopes search as "BM25 + semantic + structured query + fusion." Agentic search adds: multi-source retrieval, query decomposition, strategy selection, session state, convergence detection, and a scoring/ranking pipeline.
3. **A new concept emerges: Source Configuration.** Users define which external sources to search (GitHub, Twitter/X, Substack, HuggingFace, research blogs, Brave web search) per search category. This is a persistent preference, not a per-query decision.
4. **The CLI gets a richer interaction model.** The current CLI spec (`brain search "..."`) assumes single-turn output. The agentic search flow is multi-turn: the user sees results, selects subsets, compares, skims, summarizes, and ingests — all within a single CLI session.
5. **Search scoring doubles as system eval.** The scoring columns shown to the user (relevance, recency, source authority, novelty-to-vault) also serve as an evaluation surface — a built-in benchmark the system can track across iterations to measure whether search quality is improving.

### What does NOT change

- The knowledge model (claims, relationships, clusters) remains the same.
- Flow 1 (ingestion) remains the terminal step — agentic search feeds into it.
- Flow 2 (query knowledge) remains internal-only vault search.
- The inside-out principle holds — the search flow builds on top of working ingestion, not instead of it.

---

## 3. The Search Funnel — Step by Step

The user's journey through a search session. Each stage narrows the funnel.

```
┌─────────────────────────────────────────────────────┐
│  STAGE 1: QUERY                                     │
│  User enters a natural language search query         │
│  System decomposes into sub-queries per source       │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2: DISCOVER                                  │
│  Distributed retrieval across configured sources     │
│  Results displayed as a tree, grouped by source      │
│  Each result has scoring columns                     │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3: EVALUATE                                  │
│  User multi-selects results to compare              │
│  System shows side-by-side scoring + reasoning       │
│  "Why was this cited?" for each result              │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 4: SKIM                                      │
│  User drills into individual sources                 │
│  System fetches full content, shows summary          │
│  Link to original URL for deep reading              │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 5: EXTRACT                                   │
│  User selects sources for deeper processing          │
│  System extracts key ideas, claims, insights         │
│  Options: summarize, extract claims, find key ideas  │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 6: ABSORB                                    │
│  Selected extractions enter the ingestion pipeline   │
│  Claims classified against existing knowledge base   │
│  Conflicts surfaced, placement proposed              │
│  → Feeds directly into Flow 1                        │
└─────────────────────────────────────────────────────┘

  Side channel (any stage):
  ┌─────────────────────────────────────────────────┐
  │  BACKLOG                                        │
  │  User can queue sources for later processing    │
  │  "Read later" / "Process in background"         │
  │  Creates tasks in the vault task system          │
  └─────────────────────────────────────────────────┘
```

### Stage 1: Query

What happens:
- User runs `brain search "agent memory architecture patterns"`
- System classifies intent (exploratory vs. factual vs. comparative)
- **Query decomposition** (dedicated planner step): A small/fast model via OpenRouter takes the original query and produces structured output — a list of targeted sub-questions, each tagged with the source type best suited to answer it. This is a distinct architectural step, not inline logic within retrieval. The planner call is cheap and fast, and its structured output drives everything downstream.
- The decomposed sub-questions fan out per source type:
  - GitHub: `agent memory architecture` (repos + READMEs)
  - Twitter/X: `agent memory` (recent discourse, takes, threads)
  - Substack: `agent memory patterns` (long-form analysis)
  - HuggingFace: `memory architecture` (papers, model cards)
  - Brave web: `agent memory architecture patterns 2026` (catch-all)
- Vault cross-reference runs in parallel: "what do I already know about this?"

What the user's research notes say:
- [[agentic-search-control-loop]]: Query Understanding → Decomposition, Entity Recognition, Intent Detection, Ambiguity Detection
- [[strategy-selection]]: Intent-driven strategy routing — factual lookup favors lexical precision; exploratory queries favor semantic breadth
- [[composable-tools]]: Atomic, predictable search functions as planning primitives

### Stage 2: Discover

What the user sees — a tree grouped by source, with scoring columns:

```
$ brain search "agent memory architecture patterns"

  Searching 5 sources... ████████████████ done (2.3s)
  47 results found. 3 already in vault.

  GITHUB (12 results)
  ┌─────┬────────────────────────────────────────┬───────┬────────┬─────────┬──────────┐
  │  #  │ Title                                  │ Rel.  │ Stars  │ Recency │ Novelty  │
  ├─────┼────────────────────────────────────────┼───────┼────────┼─────────┼──────────┤
  │  1  │ mem0ai/mem0 - Memory for AI agents     │ 0.92  │ 24.1k  │ 2d ago  │ NEW      │
  │  2  │ langchain-ai/memory-patterns           │ 0.87  │ 8.3k   │ 1w ago  │ NEW      │
  │  3  │ cpacker/MemGPT                         │ 0.84  │ 12.7k  │ 3w ago  │ IN VAULT │
  │  ...│                                        │       │        │         │          │
  └─────┴────────────────────────────────────────┴───────┴────────┴─────────┴──────────┘

  SUBSTACK (8 results)
  ┌─────┬────────────────────────────────────────┬───────┬────────┬─────────┬──────────┐
  │  #  │ Title                                  │ Rel.  │ Author │ Recency │ Novelty  │
  ├─────┼────────────────────────────────────────┼───────┼────────┼─────────┼──────────┤
  │  1  │ "Memory is the Moat" — latent.space    │ 0.91  │ swyx   │ 5d ago  │ NEW      │
  │  2  │ Agent Memory Taxonomy — by simonsarris │ 0.85  │ Simon  │ 2w ago  │ NEW      │
  │  ...│                                        │       │        │         │          │
  └─────┴────────────────────────────────────────┴───────┴────────┴─────────┴──────────┘

  TWITTER/X (15 results)  │  HUGGINGFACE (4 results)  │  WEB (8 results)
  ... (collapsed, expandable)

  [select #s to compare]  [expand source]  [refine query]  [→ next page]
```

Scoring columns per source type (not every column applies everywhere):

| Column | What it measures | Source |
|--------|-----------------|--------|
| Relevance | Semantic + keyword match to query | LLM scoring |
| Recency | How recently published/updated | Source metadata |
| Authority | Stars, citations, author reputation | Source-specific |
| Novelty | NEW (not in vault) vs. IN VAULT (already ingested) | Vault cross-reference |
| Depth | Estimated content depth (thread vs. paper vs. repo) | Content analysis |

Key design point from `better-search.md`: These scoring columns serve **dual purpose** — they inform the user AND they function as a self-eval trace. The system logs what it scored and why, creating a benchmark dataset for improving search quality over time.

### Stage 3: Evaluate (Compare)

User multi-selects results to compare side-by-side:

```
  > compare 1 2 5

  COMPARING 3 SOURCES
  ┌────────────────────────┬────────────┬────────────────────┬────────────────────┐
  │                        │ mem0/mem0  │ langchain/memory   │ MemGPT             │
  ├────────────────────────┼────────────┼────────────────────┼────────────────────┤
  │ Approach               │ Persistent │ Taxonomy of        │ Virtual context    │
  │                        │ memory     │ buffer/summary/    │ management via     │
  │                        │ layer      │ entity/graph       │ paging             │
  ├────────────────────────┼────────────┼────────────────────┼────────────────────┤
  │ Why cited              │ Most-used  │ Canonical taxonomy │ Novel approach to  │
  │                        │ memory lib │ for memory types   │ memory-as-OS       │
  ├────────────────────────┼────────────┼────────────────────┼────────────────────┤
  │ Your vault says        │ 1 claim    │ Not in vault       │ 2 claims           │
  │                        │ (partial)  │                    │ (from 01/2026)     │
  ├────────────────────────┼────────────┼────────────────────┼────────────────────┤
  │ Gap this fills         │ How mem0   │ Conceptual         │ Update: v0.4       │
  │                        │ actually   │ framework you      │ changes since      │
  │                        │ works      │ lack entirely      │ your notes         │
  └────────────────────────┴────────────┴────────────────────┴────────────────────┘

  [skim #]  [extract from selected]  [queue for later]  [back]
```

### Stage 4: Skim

User drills into a single source for a quick read:

```
  > skim 2

  langchain-ai/memory-patterns
  ──────────────────────────────
  URL: https://github.com/langchain-ai/memory-patterns
  Type: GitHub repo (README + docs)
  Last updated: 2026-04-11

  SUMMARY (auto-generated)
  A reference implementation of 4 memory architectures for LLM agents:
  buffer memory, summary memory, entity memory, and knowledge graph memory.
  Each pattern is implemented as a standalone module with benchmarks.
  Includes a comparison framework for evaluating memory approaches.

  KEY SECTIONS
  • Buffer Memory — sliding window, token-counted
  • Summary Memory — compressive, LLM-generated summaries
  • Entity Memory — entity extraction + structured storage
  • Graph Memory — knowledge graph with typed relationships

  [open in browser]  [extract claims]  [summarize deeper]  [queue]  [back]
```

### Stage 5: Extract

User selects sources for deeper processing:

```
  > extract 1 2

  Extracting key ideas from 2 sources...

  FROM: mem0/mem0
  ┌─────────────────────────────────────────────────────────────────────┐
  │ [1] "Mem0 uses a hybrid storage model: vector DB for semantic      │
  │      retrieval + graph DB for relational context"                  │
  │      evidence: primary (source code analysis)  strength: strong    │
  │                                                                    │
  │ [2] "Mem0 automatically categorizes memories into user, session,   │
  │      and agent-level scopes"                                       │
  │      evidence: documentation  strength: strong                     │
  │                                                                    │
  │ [3] "Memory retrieval in Mem0 uses a combined relevance +          │
  │      recency score, not just embedding similarity"                 │
  │      evidence: analysis  strength: moderate                        │
  └─────────────────────────────────────────────────────────────────────┘

  FROM: langchain-ai/memory-patterns
  ┌─────────────────────────────────────────────────────────────────────┐
  │ [4] "Buffer memory is simplest but fails at long conversations     │
  │      (>8k tokens) — not a memory architecture, a truncation one"   │
  │      evidence: analysis  strength: moderate                        │
  │                                                                    │
  │ [5] "Graph memory preserves relationships that summary memory      │
  │      destroys — entities stay connected even after compression"    │
  │      evidence: primary (benchmark)  strength: strong               │
  └─────────────────────────────────────────────────────────────────────┘

  5 claims extracted.  [ingest all]  [select claims]  [edit]  [queue]
```

### Stage 6: Absorb

This is where agentic search hands off to Flow 1 (Ingest). The extracted claims enter the existing ingestion pipeline:

- Relationship classification against existing knowledge base
- Conflict detection and surfacing
- Placement proposal (new claims, updated claims, new edges)
- User approval before any write

The loop closes: Search → Extract → Ingest → Knowledge model updated → Next search is smarter because the vault cross-reference is richer.

### Side Channel: Backlog

At any stage, the user can queue a source for later:

```
  > queue 3 5 7

  Queued 3 sources for later processing.
  Run `brain backlog` to see pending items.
  Run `brain process` to batch-extract queued sources.
```

This creates tasks in the vault's task system (`90-system/task-hq.md`), or optionally processes sources in the background with results ready for review next session.

---

## 4. Source Configuration — A New Concept

The `better-search.md` note introduces an idea not in the current manifest: **user-configured source profiles.**

```
$ brain sources

  ACTIVE SOURCES
  ┌──────────────┬───────────┬─────────────────────────────────┐
  │ Source       │ Status    │ Notes                           │
  ├──────────────┼───────────┼─────────────────────────────────┤
  │ Brave Web    │ ✓ enabled │ General web search (default)    │
  │ GitHub       │ ✓ enabled │ Repos, READMEs, discussions     │
  │ Twitter/X    │ ✓ enabled │ Threads, takes, discourse. X API free tier for testing, user's own account │
  │ Substack     │ ✓ enabled │ Long-form analysis              │
  │ HuggingFace  │ ✓ enabled │ Papers, model cards, datasets   │
  │ ArXiv        │ ○ off     │ Academic papers                 │
  │ Reddit       │ ○ off     │ r/LocalLLaMA, r/MachineLearning │
  └──────────────┴───────────┴─────────────────────────────────┘

$ brain sources add arxiv --categories cs.AI cs.CL
$ brain sources enable reddit --subreddits LocalLLaMA MachineLearning
```

The `better-search.md` note also mentions **meta-search categories** — predefined profiles for different research domains:

| Category | Sources prioritized | Example queries |
|----------|-------------------|-----------------|
| Applications | GitHub, ProductHunt, HN | "best agent frameworks 2026" |
| Agentic SDLCs | GitHub, Substack, Twitter | "agent testing patterns" |
| Frontier Models | ArXiv, HuggingFace, Twitter | "claude 4 architecture" |
| Jiu Jitsu | YouTube, Reddit, blogs | "half guard passing sequences" |

This is a **persistent user preference**, not a per-query decision. It shapes the default source set for each search. The user can override per-query (`brain search --sources github,arxiv "..."`).

---

## 5. The Control Loop — Under the Hood

Drawing from [[agentic-search-control-loop]] and the `20-notes/ai/search/` corpus, here's how the system actually works behind the CLI:

```
┌──────────────────────────────────────────────────────┐
│                AGENTIC SEARCH LOOP                   │
│                                                      │
│  ┌──────────────┐                                    │
│  │ 1. Query     │  Decompose, detect intent,         │
│  │ Understanding│  identify entities, flag ambiguity  │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │ 2. Strategy  │  Select retrieval approach per      │
│  │ Selection    │  source based on intent + policy    │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │ 3. Retrieval │  Fan out to configured sources      │
│  │ Execution    │  Aggregate, handle failures         │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │ 4. Relevance │  Score results (hybrid: LLM +       │
│  │ Assessment   │  behavioral signals + novelty)      │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │ 5. Adaptive  │  Update search state, adjust        │
│  │ Refinement   │  strategy weights for next iter.    │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌──────────────┐                                    │
│  │ 6. Converge/ │  Stop when quality threshold met    │
│  │ Terminate    │  or iteration budget exhausted      │
│  └──────────────┘                                    │
│                                                      │
│  State object (survives across iterations):          │
│  - Original query + reformulation trajectory         │
│  - Per-iteration embeddings + strategy log           │
│  - Confidence curves + diversity metrics             │
│  - Vault cross-reference results                     │
└──────────────────────────────────────────────────────┘
```

Key architectural points from the research notes:

- **Composable tools, not monolithic API** ([[composable-tools]]): BM25, semantic search, graph traversal, metadata filtering are separate tools the agent can reason about and compose.
- **Session state** ([[agentic-search-state]]): A structured object that tracks what was tried, what worked, and what the confidence trajectory looks like. Without this, the agent repeats itself.
- **Multi-turn reasoning** ([[multi-turn-reasoning]]): The agent can refine queries, change strategies, and combine results across iterations — not a single retrieval step.
- **Hybrid scoring** ([[hybrid-relevance-scoring]]): LLM relevance + behavioral signals with adaptive weighting. For a personal tool, "behavioral signals" start as explicit user actions (select, skip, queue, ingest) rather than passive tracking.
- **Strategy selection** ([[strategy-selection]]): Intent-driven routing. Factual queries get lexical precision; exploratory queries get semantic breadth.

---

## 6. Scoring as Self-Eval — The Dual-Purpose Insight

This is one of the most interesting ideas from `better-search.md`. The scoring columns shown to the user are not just UX — they are an **evaluation surface.**

Every search session produces a trace:
- What query was run
- What results were returned, with scores
- What the user selected, skipped, queued, or ingested
- What the system's scoring predicted vs. what the user actually found useful

Over time, this creates a **labeled dataset of search quality** — automatically, just from using the tool. The system can then:
1. Track whether search quality is improving across iterations
2. Identify which sources consistently produce high-value results
3. Detect scoring calibration drift (system says 0.9 relevance, user skips it)
4. Feed into the adaptive policy for hybrid scoring weights

This connects directly to the manifest's principle of **Eval from Day One** — but it's eval embedded in the UX, not eval as a separate harness.

---

## 7. Open Questions for Design

These are genuinely undecided. They shape the spec.

1. **Where does this land in the roadmap?** The current Phase 2 (Search) is scoped as vault-internal hybrid search. Agentic external search is closer to Phase 3-4. Does it replace Phase 2's external search scope, or is it a new phase?

2. **How interactive should the CLI be?** The funnel described above is highly interactive — multi-select, compare, skim, extract. Is this a single long-running CLI session (like a TUI), or a series of commands (`brain search` → `brain compare 1 2 5` → `brain skim 2` → `brain extract 1 2`)?

3. **Source API access.** GitHub, Brave Search, and HuggingFace have APIs. Twitter/X API is expensive and restrictive. Substack has no public API. How do we handle sources without clean API access? Scraping? Brave Search as a proxy? Twitter/X: The X API free tier (as of 2026) provides limited read access, sufficient for testing. The user authenticates with their own account. If rate limits are prohibitive, fall back to Brave Search with `site:x.com` as a proxy.

4. **How does the backlog work?** Is it a simple task list in the vault, or does the system actually process queued sources in the background and have results ready?

5. **Vault cross-reference at search time.** Comparing search results against the vault requires the knowledge model to exist and be populated. This implies ingestion (Phase 1) must be working before search is useful. Does this change the build order?

6. **Cost model.** Each search session involves multiple LLM calls (query decomposition, per-result scoring, comparison generation, claim extraction). What's the token budget per search? Is this sustainable with Claude API pricing?

7. **Does this change the MVP?** The current MVP is "ingest a note, extract claims, classify relationships." Should the MVP scope shift to include a minimal search flow, or does search remain Phase 2+?

8. **How much of the control loop is visible to the user?** Does the user see the agent's reformulation process, or just the final results? Transparency vs. simplicity.

9. **Assisted search flow.** Should the system support an 'assisted search' mode where a planner agent asks the user follow-up questions to refine their query before executing? This could improve result quality for vague queries but adds interaction friction. Design decision: make it opt-in (`brain search --assist "vague topic"`) rather than default.

10. **REPL session extensibility.** The REPL session needs to support multiple interaction patterns: compare, skim, queue, refine, free-form prompts, batch category select, quick-add top N. Not all need to ship in A5, but the session state model must be extensible enough to support them. What's the minimal session state object that enables all of these?

---

## 8. Relevant Research Notes in This Vault

These notes form the theoretical foundation for the design:

| Note | Key concept |
|------|------------|
| [[agentic-search-control-loop]] | The 6-step loop: Query Understanding → Strategy Selection → Retrieval → Assessment → Refinement → Convergence |
| [[agentic-search-state]] | Session state object: query trajectory, embeddings, strategies, confidence curves |
| [[composable-tools]] | Atomic search tools as planning primitives ("predictable > fancy") |
| [[multi-turn-reasoning]] | Iterative reformulation, not single-turn retrieval |
| [[strategy-selection]] | Intent-driven routing to retrieval approaches |
| [[hybrid-relevance-scoring]] | LLM + behavioral signals with adaptive weighting |
| [[session-memory]] | Ephemeral state within a single interaction |
| [[stateful-reasoning]] | Session-local memory that survives across tool calls |
| [[search-lexicon]] | Failure modes, IR foundations, vocabulary |
| [[adaptive-policy]] | Dynamic weighting between signal sources |
| [[behavioral-feedback-signals]] | User actions as grounding signals for scoring |
| [[intent-conditioned-embeddings]] | Embeddings constructed per classified intent |
| [[evaluation/convergence-rate]] | How many steps before termination |
| [[evaluation/information-gain-per-iteration]] | Quality improvement per step |
| [[evaluation/strategy-diversity]] | Variety of approaches explored |
| [[production/query-routing]] | Complexity-based tiering for cost control |
| [[harness-engineering]] | "The harness is everything. The model is almost irrelevant." |

---

## 9. What This Session Needs to Decide

Before this becomes a spec, we need answers to:

1. **Scope**: Is agentic search the next thing to build, or do we stay on the MVP (ingestion) track and come back to this?
2. **Interaction model**: TUI-style session vs. composable CLI commands?
3. **Source priority**: Which 2-3 sources to support first? (Brave + GitHub seem obvious)
4. **Minimal funnel**: What's the thinnest version of the funnel that's useful? (Maybe: search → score → extract → ingest, skipping compare/skim?)
5. **Integration point**: How tightly does this couple to the knowledge model, or can it work standalone?

---

---

## Updates from Steelman (2026-04-19)

Based on [[2026-04-19-steelman-search-flow|steelman analysis]]:
- Query decomposition confirmed as the highest-impact architectural addition
- Twitter/X confirmed as a source — X API free tier for testing with user's own account
- REPL session flows expanded: compare, skim, queue, refine, free-form prompts, assisted-search
- OpenRouter as the API gateway for all LLM calls (free models for testing)
- Model strategy: small/fast model for scoring, capable model for synthesis

---

*This is a working document. It will evolve into a spec after design decisions are made.*
