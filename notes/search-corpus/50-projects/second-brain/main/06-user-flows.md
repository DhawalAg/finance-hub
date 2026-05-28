---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[50-projects/second-brain/main/01-vision]]"
---

# Second Brain — User Flows

> How the user interacts with the system, what the system does in response, and which architectural layers handle each step. Supersedes [[dumps/01-user-flow-v0|user flow v0]].

---

## 1. Core Loop

Every interaction is one of three operations. They compose into a cycle.

```
                    ┌──────────┐
        ┌──────────►│ DISCOVER │
        │           │ (search) │
        │           └────┬─────┘
        │                │ user selects what matters
        │                ▼
        │           ┌──────────┐
        │           │  ABSORB  │
        │           │ (ingest) │
        │           └────┬─────┘
        │                │ knowledge base grows
        │                ▼
        │           ┌──────────┐
        │           │ RETRIEVE │
        │           │ (recall) │
        │           └────┬─────┘
        │                │ gaps identified
        └────────────────┘
```

The loop closes: retrieval surfaces gaps, gaps become discovery queries, discovery feeds absorption. A single session may touch one mode or all three. The system tracks where the user is in the loop and adjusts its behavior accordingly.

---

## 2. Flow 1: Ingest a Note — MVP

**Trigger:** User points the system at a file (or set of files) in the vault.
**Phase:** MVP (Phase 1)

### Step-by-step

| Step | User | System | Layer |
|------|------|--------|-------|
| 1. Initiate | `brain ingest ./notes/mastra.md` | Reads file content, validates it is parseable markdown. | L1 (orchestrator) |
| 2. Extract claims | Waits. | Runs claim extraction: markdown in, structured claims out. Each claim is a testable proposition with evidence type and assertion strength. Targets 3-7 claims per source. | L2a (ingestion) |
| 3. Classify relationships | Waits. | For each extracted claim, retrieves top 5-10 similar existing claims from [[50-projects/second-brain/main/02-architecture#Level 2 Relationships\|the knowledge model]]. Classifies each pair: supports, contradicts, extends, qualifies, supersedes. | L2a + L2c (reasoning) |
| 4. Surface conflicts | Reviews proposed changes. | If any relationship is typed `contradicts`, system surfaces both claims side-by-side with the conflict subtype (direct refutation, scope difference, different interpretation) and its confidence score. | L2c (reasoning) |
| 5. Propose placement | Reviews plan: which claims are new, which update existing entries, which conflicts need attention. | Generates a placement plan: new claims to store, existing claims to update, relationship edges to create. Shows diff. | L2a (ingestion) |
| 6. Approve | Accepts, edits, or rejects the plan. | -- | L4 (interface) |
| 7. Commit | -- | Writes claims + relationships to SQLite. Generates embeddings for new claims. Logs the action with full trace. | L0 (data), L2e (observability) |

### What the user sees (CLI output)

```
$ brain ingest ./notes/mastra.md

Extracting claims...  5 claims found.

  [1] "Mastra supports graph-based workflows natively"    strength: strong
  [2] "Memory in Mastra persists across agent sessions"   strength: strong
  [3] "Mastra integrates with Vercel AI SDK"              strength: strong
  [4] "Mastra's eval system runs offline"                 strength: moderate
  [5] "Mastra has 23k GitHub stars"                       strength: strong

Classifying relationships against 847 existing claims...

  CONFLICT DETECTED
  [2] "Memory in Mastra persists across agent sessions"
    contradicts (scope_difference, confidence: 0.72)
    existing: "Mastra memory requires explicit session IDs; no auto-persist"
    source: ai-app-stack-2026.md, ingested 2026-04-10

  NEW CONNECTIONS
  [1] extends "Agent frameworks support DAG-based workflows" (from effective-agent-design.md)
  [3] supports "Vercel AI SDK is the emerging standard for TS agent UIs" (from ai-stack-landscape.md)

Placement plan:
  STORE   5 new claims
  CREATE  4 new relationship edges
  FLAG    1 conflict for review

[approve / edit / reject] >
```

### Design constraints

- System proposes, user approves. No silent writes to the knowledge model.
- Conflict surfacing is mandatory, not optional. If two claims contradict, the user sees it before anything is stored.
- The ingestion trace (every LLM call, every classification decision) is logged regardless of approval outcome. Observability is unconditional.

---

## 3. Flow 2: Query Knowledge — MVP

**Trigger:** User asks "what do I know about X?"
**Phase:** MVP (Phase 2-3)

### Step-by-step

| Step | User | System | Layer |
|------|------|--------|-------|
| 1. Ask | `brain search "agent memory architectures"` | Parses query. Determines this is a retrieval intent (not web search). | L1 (orchestrator) |
| 2. Retrieve | Waits. | Runs hybrid search: BM25 over vault markdown + semantic search over claim embeddings + structured query against SQLite relationships. Merges and reranks. | L2b (search) |
| 3. Assess | Waits. | Runs [[02-architecture#Loop 3|knowledge state assessment]] over the result set. Computes cluster properties: depth, diversity, conflict level, recency, evidence quality. | L2c (reasoning) |
| 4. Deliver verdict | Reads assessment. Decides next action. | Presents: what you know, how well you know it, what is missing. Honest. No inflation. | L4 (interface) |
| 5. Act on gaps (optional) | `brain search --web "agent memory architecture patterns"` | Loops into Flow 3 (Discover) with a gap-derived query. | L1 (orchestrator) |

### What the user sees

```
$ brain search "agent memory architectures"

KNOWLEDGE STATE: agent memory

  Depth      ██░░░  4 claims across 3 sources
  Diversity  █░░░░  all tool documentation, no research
  Conflicts  ████░  1 active (Mastra memory persistence)
  Recency    ████░  most recent: 8 days ago
  Evidence   ██░░░  0 primary research, 3 analysis, 1 opinion

WHAT YOU KNOW:
  - Mem0 provides a persistent memory layer that learns user preferences
    (source: ai-app-stack-2026.md, evidence: analysis, strength: moderate)
  - Mastra memory persists across agent sessions
    (source: mastra.md, evidence: analysis, strength: strong)
    ** CONFLICT: contradicts claim from ai-app-stack-2026.md — see above
  - Your Lattice design uses a knowledge graph approach to memory
    (source: 11-knowledge-model.md, evidence: primary, strength: strong)

GAPS IDENTIFIED:
  - No taxonomy of memory architectures (buffer, summary, entity, graph)
  - No understanding of memory vs. context window tradeoffs
  - No research papers or foundational sources
  - No comparative evaluation across frameworks

VERDICT: You know specific tools but lack a conceptual framework.
         You could write a tools comparison. You cannot yet write
         about memory architecture patterns.

[fill gaps (web search)] [show sources] [export]
```

### Design constraints

- The assessment is honest. If coverage is thin, the system says so. No "you have great knowledge on this topic" when you have 4 claims from blog posts.
- Gaps are specific and actionable, not generic ("learn more about X"). Each gap should be convertible into a search query.
- Conflicts are surfaced inline. The user should never read a knowledge summary that silently omits contradictions.

---

## 4. Flow 3: Search + Absorb — Phase S

**Trigger:** User searches for external knowledge to fill a gap.
**Phase:** Phase S (first build phase)

> [!note] Build order change
> Search is now the entry point, not a later addition. This flow ships first because it delivers standalone value (find and absorb external knowledge) without requiring the full ingestion pipeline or knowledge model to be in place. Flows 1 and 2 build on top of the search infrastructure established here.

### Step-by-step

| Step | User | System | Layer |
|------|------|--------|-------|
| 1. Search | `brain search --web "memory architecture patterns for LLM agents"` | Runs query decomposition: a lightweight planner call (small/fast model via OpenRouter) splits the query into 3-5 targeted sub-questions. Fires parallel searches per sub-query across configured sources: vault (what you already know), web (Brave API), GitHub (repos), Twitter/X (discourse). See [[2026-04-18-agentic-search-flow]] for the full funnel. | L1 + L2b |
| 2. Cross-reference | Reviews results. | Annotates every result: "already in vault" vs. "new to you." Vault matches include depth indicator. | L2b + L2c |
| 3. Select | Picks 2-3 results to absorb. | -- | L4 |
| 4. Fetch + extract | Waits. | Fetches full content. Runs claim extraction on each source. | L2a (ingestion) |
| 5. Propose placement | Reviews plan. | Same as Flow 1 steps 3-6: classify relationships, surface conflicts, propose placement, show diff. | L2a + L2c |
| 6. Approve | Accepts. | Commits to knowledge model. | L0 |

### What distinguishes this from vanilla web search

Three things happen that do not happen in a browser:

1. **Vault cross-reference.** Results are split into "you already know this" and "this is new." Existing knowledge shows depth and recency.
2. **Query decomposition.** A dedicated planner call (small/fast model via OpenRouter, structured output) decomposes the raw query into 3-5 targeted sub-questions: one for research papers, one for framework docs, one for comparison articles, one for real-time discourse. Each sub-query is routed to the most relevant sources. This is the consensus architecture behind Perplexity, gpt-researcher, and STORM.
3. **Absorption pipeline.** Selected results do not just get bookmarked. They enter the same ingestion flow as local notes: claim extraction, relationship classification, conflict detection, structured storage.

The loop from Flow 2 closes here. Gaps become queries. Queries become results. Results become claims. Claims update the knowledge state.

---

## 5. Flow 4: Proactive Briefing — V3

**Trigger:** System-initiated, on schedule or after significant knowledge model changes.
**Phase:** V3 (Phase 4-5)

### Step-by-step

| Step | User | System | Layer |
|------|------|--------|-------|
| 1. Detect change | -- | Runs [[50-projects/second-brain/main/02-architecture#Loop 3\|Loop 3 (Knowledge State Assessment)]]. Diffs cluster properties against prior snapshot. Identifies: new conflicts, resolved conflicts, depth changes, stale clusters. | L2c + L2d |
| 2. Generate briefing | -- | Produces a structured digest: what changed, what is newly contested, what has gone stale, what gaps remain open. | L2c (reasoning) |
| 3. Deliver | Reads briefing in daily note or CLI. | Writes briefing to daily note template or presents on next `brain status`. | L4 + L2d (memory) |
| 4. Act (optional) | Clicks into a specific change or gap. | Routes to Flow 1 (re-ingest a stale source), Flow 2 (query updated topic), or Flow 3 (search for new sources). | L1 |

### What the user sees

```
$ brain status

BRIEFING — since 2026-04-15

  KNOWLEDGE CHANGES
  + 12 new claims ingested across 4 sources
  + 2 new relationship edges classified
  ~ 1 conflict resolved (Mastra memory: updated with v0.3 docs)

  ATTENTION NEEDED
  ! "RAG pipeline architectures" — 3 claims are >30 days old,
    2 sources have published updates since your last ingestion
  ! "Agent evaluation frameworks" — depth increased but diversity
    is still 1/5 (all from the same author)

  SUGGESTED ACTIONS
  > brain ingest ./notes/rag-pipeline.md --refresh
  > brain search --web "agent evaluation benchmarks 2026"
```

### Design constraints

- Briefings are information, not noise. The system only surfaces changes that are meaningful: conflicts, staleness, depth shifts. Not "you ingested 3 files."
- The user controls frequency. Daily, weekly, on-demand, or off.
- Every briefing item links to an action. Stale notes link to re-ingestion. Gaps link to search. Conflicts link to the specific claims.

---

## 5b. Flow 3b: Interactive Research Session (REPL)

**Trigger:** User enters a search session and wants to explore results interactively.
**Phase:** Phase S (A5), builds on Flow 3

> [!note] Incremental build
> One-shot search (A1-A3) ships before the REPL. The session model layers on top of the same search infrastructure — it does not require a separate architecture.

### The Session Model

After initial search results are displayed, the user enters an interactive session. The CLI maintains session state — search results, scores, selections, and conversation context persist across commands within the session.

### Session Commands

| Command | What it does | Example |
|---------|-------------|---------|
| `compare <nums>` | Side-by-side comparison of selected results with LLM reasoning | `compare 1 3 5` |
| `skim <num>` | Fetch full content, show LLM-generated summary of a single result | `skim 3` |
| `queue <nums>` | Save results for later processing (creates tasks in vault) | `queue 1 5` |
| `refine "<query>"` | Narrow the search with a refined query, keeping session context | `refine "graph memory vs summary memory"` |
| `add <nums>` | Select results for extraction/ingestion (feeds into Flow 1) | `add 1 2 3` |
| `add <source>` | Select all results from a source category | `add github` |
| `back` | Return to the results list from any sub-view | `back` |
| Free-form text | Ask a follow-up question with session context | `"what about episodic memory?"` |

### Assisted Search Mode

An opt-in mode where the system asks follow-up questions before executing the search:

```
$ brain search --assist "agent memory"

  I'd like to refine your search. A few questions:

  1. Are you looking for implementation patterns or conceptual frameworks?
  2. Any specific frameworks? (LangChain, Mem0, custom)
  3. Interested in recent discourse (last 30 days) or established literature?

  > implementation patterns, especially Mem0 and custom approaches, recent

  Understood. Decomposing into sub-queries...
  Searching 3 sources with 4 sub-queries... done (3.1s)
```

### Design Principles

- **Session state is ephemeral.** It lives in memory during the session and is discarded on exit. Persistent artifacts (queued items, ingested claims) write to the vault/SQLite.
- **Commands compose on top of one-shot.** Each session command maps to a capability that also works as a standalone CLI command. The REPL is convenience, not a separate system.
- **Extensibility over completeness.** Not all commands ship in v1. The session state model (results + scores + selections + context) must support future commands without architectural changes.
- **Quick interactions are first-class.** A user who likes the top 3 results should be able to `add 1 2 3` and exit in 5 seconds. Don't force deep interaction.

---

## 6. Agent Roles

These are not separate agents. They are role configurations on a single-agent loop: different system prompts, different tool sets, same runtime. See [[50-projects/second-brain/main/02-architecture#Layer 1 CORE RUNTIME]].

| Role | Purpose | Tools | Fires during |
|------|---------|-------|-------------|
| Orchestrator | Routes intent to the correct flow. Decides search strategy, picks model. | All tools (meta-level) | Every interaction (L1) |
| Query Understanding | Decomposes natural language into structured intent: entities, constraints, scope. | None (pure LLM reasoning) | Flow 2, Flow 3 step 1 |
| Search Executor | Runs parallel searches across vault, web, GitHub. Merges and reranks. | `search-vault-bm25`, `search-vault-semantic`, `search-web`, `search-github` | Flow 2 step 2, Flow 3 step 1 |
| Claim Extractor | Reads source content, produces atomic claims with evidence type and strength. | `read-file`, `fetch-url`, `write-claims` | Flow 1 step 2, Flow 3 step 4 |
| Relationship Classifier | Given two claims, classifies the relationship type with confidence. | `query-claims`, `write-relationship` | Flow 1 step 3, Flow 3 step 5 |
| Knowledge Assessor | Computes cluster properties. Produces honest depth/diversity/conflict verdicts. | `query-claims`, `query-relationships`, `compute-cluster-state` | Flow 2 step 3, Flow 4 step 1 |
| Memory Manager | Tracks session history, user engagement patterns, knowledge model diffs over time. | `read-session-log`, `write-session-log`, `diff-cluster-state` | Flow 4, cross-session recall |
| Query Decomposer | Splits a natural language query into targeted sub-questions for multi-source retrieval | None (pure LLM reasoning via OpenRouter) | Flow 3 step 1, Flow 3b |
| Source Manager | Manages configured search sources (Brave, GitHub, Twitter/X, HuggingFace). Handles source health checks, API key validation, rate limits, and source-specific query formatting. | `list-sources`, `check-source-health`, `configure-source` | Flow 3 step 1, Flow 3b |

### Model routing

Not every role needs the same model. The orchestrator selects based on task complexity:

| Task type | Model | Rationale |
|-----------|-------|-----------|
| Embedding generation | Ollama (local) | High volume, low reasoning requirement |
| Simple classification | Ollama (local) or OpenRouter (small/fast model) | Fast, cheap, good enough for binary decisions |
| Query decomposition | OpenRouter (small/fast model) | Speed matters more than reasoning depth; sub-queries just need to be relevant |
| Claim extraction | Claude API | Precision matters; hallucinated claims poison the model |
| Relationship classification | Claude API | Core thesis depends on accuracy here |
| Knowledge assessment | Claude API | Requires nuanced reasoning over structured data |

---

## 7. Interaction Principles

Six principles that govern every flow.

### 7.1 System proposes, user approves

The system never modifies the knowledge model silently. Every write operation (new claim, new relationship, updated confidence) is shown to the user first. The user can accept, edit, or reject. This is non-negotiable for trust.

### 7.2 Show what you know vs. what is new

Every search result, every ingestion, every briefing separates existing knowledge from new information. The user should always be able to answer: "did I already know this?" The vault cross-reference is not a feature — it is a foundational interaction pattern.

### 7.3 Honest assessment with specific gaps

Knowledge state verdicts do not flatter. If depth is 2/5, the system says 2/5 and explains why. Gaps are stated as specific missing knowledge, not vague suggestions. Each gap should map to a concrete search query or ingestion action.

### 7.4 Conflicts are first-class

Contradictions between claims are surfaced immediately and prominently — during ingestion, during retrieval, in briefings. The system does not silently pick a winner. Both sides are shown with evidence and confidence. Resolution is the user's decision.

### 7.5 The loop closes

Every flow should have a clear path to the next flow. Retrieval surfaces gaps. Gaps become search queries. Search results become ingestion candidates. Ingestion updates the knowledge state. Briefings surface what changed. The system actively offers these transitions rather than dead-ending.

### 7.6 Observe everything, explain anything

Every system decision — why this claim was extracted, why this relationship was classified as "contradicts," why this cluster is rated 2/5 depth — is logged and can be surfaced on demand. The user can always ask "why did you do that?" and get a real answer grounded in the trace log.

---

## Phase Mapping

| Flow | Phase | Depends on |
|------|-------|-----------|
| Flow 3: Search + Absorb | Phase S (first) | Brave API, source connectors, query decomposition |
| Flow 3b: REPL Session | Phase S (A5) | One-shot search (A1-A3), session state model |
| Flow 1: Ingest a Note | Phase 0-1 (after search) | Core loop, claim extractor, SQLite schema |
| Flow 2: Query Knowledge | Phase 2-3 | Hybrid search, reasoning module, knowledge model |
| Flow 4: Proactive Briefing | Phase 4-5 | Memory module, knowledge state diffing, daily note integration |

---

*See also: [[50-projects/second-brain/main/02-architecture]] for system layers, [[50-projects/second-brain/main/05-roadmap]] for phase details, [[50-projects/second-brain/main/01-vision]] for project identity.*
