---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
ground-truth: true
parent: "[[00-master-plan]]"
---

# User Flow v0 — Raw Interaction Model

> A rough decomposition of how a user interacts with the Second Brain, what the system does behind the scenes, and how each piece maps to the architecture in [[00-master-plan]].

---

## The Core Loop

Everything the user does falls into one of three modes. The system supports all three, and they feed each other:

```
        ┌──────────────┐
        │   DISCOVER   │  "Find me things about X"
        │   (search)   │
        └──────┬───────┘
               │ user picks what's relevant
               ▼
        ┌──────────────┐
        │   ABSORB     │  "Add this to what I know"
        │   (ingest)   │
        └──────┬───────┘
               │ knowledge base grows
               ▼
        ┌──────────────┐
        │   RETRIEVE   │  "What do I know about Y?"
        │   (recall)   │
        └──────┬───────┘
               │ feeds back into discovery
               └──────────► loops back to DISCOVER
```

These aren't separate features — they're the same session. A user might discover, absorb, and retrieve all in one sitting, or just do one.

---

## The Full User Journey — Step by Step

Below is ONE continuous session showing all three modes. Each step shows:
- **What the user sees / does**
- **What the system does behind the scenes**
- **Which layer/module from the master plan is responsible**

---

### Act 1: DISCOVER — "Find me things about X"

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Main Surface                                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  🔍  What are you looking for?                              │    │
│  │                                                             │    │
│  │  > "open source agent frameworks in typescript that have    │    │
│  │     built-in memory and eval support"                       │    │
│  │                                                             │    │
│  │  [Search Vault]  [Search Web]  [Search Both]  [Deep Search] │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Step 1 — User states intent**

| | Detail |
|---|---|
| **User does** | Types a natural-language query. Optionally selects scope (vault, web, both, deep). |
| **Screen** | Input field + scope buttons. "Deep Search" is the premium option — slower, more thorough. |

**Step 2 — System interprets the query**

| | Detail |
|---|---|
| **System does** | **Query Understanding Agent** parses the input. Extracts: intent (find repos/projects), domain (agent frameworks), constraints (TypeScript, open source, memory, evals). Decides search strategy: this needs web + vault (user has notes on Mastra, LangGraph already). |
| **Layer** | L1 (Core Runtime — orchestrator decides strategy) |
| **Module** | L2b (Search — query parsing, strategy selection) |

```
SYSTEM INTERNALS — Query Understanding

Input:  "open source agent frameworks in typescript that have
         built-in memory and eval support"

Parsed:
  intent:       find_projects
  domain:       agent frameworks
  language:     TypeScript
  constraints:  [open source, memory support, eval support]
  sources:      [vault (user has prior notes), github, web]

Strategy:
  1. Search vault first (check what user already knows)
  2. Search GitHub repos (code-specific, filter by stars/activity)
  3. Search web (broader context, articles, comparisons)
  4. Cross-reference and deduplicate
```

> **Inflection Point #1:** How much query understanding do we build vs. delegate to the LLM?
>
> Option A: Heavy NLP pipeline (entity extraction, intent classification, constraint parsing) — more control, more code, slower.
> Option B: Pass the raw query + system prompt to the LLM and let it decompose — less code, faster to build, but less predictable.
> Option C: Hybrid — lightweight extraction for the obvious stuff (language, open-source filter), LLM for intent and strategy.
>
> **Not decided yet.** This is where the agentic search research feeds in. The answer depends on what we learn building the search module.

**Step 3 — System searches (parallel)**

| | Detail |
|---|---|
| **System does** | Fires multiple search operations concurrently. |
| **Layer** | L2b (Search) + L1 (orchestrator coordinates) |

```
SYSTEM INTERNALS — Parallel Search Execution

┌─────────────┐     ┌──────────────────┐     ┌───────────────┐
│ Vault Search │     │  GitHub Search    │     │  Web Search   │
│              │     │                  │     │               │
│ BM25 + vector│     │ Repos matching:  │     │ Brave API     │
│ over user's  │     │ - "agent"        │     │ query:        │
│ existing     │     │ - "framework"    │     │ enhanced from  │
│ notes        │     │ - lang:ts        │     │ parsed intent │
│              │     │ - stars:>500     │     │               │
│ Found:       │     │ - recent commits │     │ Found:        │
│ - mastra.md  │     │                  │     │ - blog posts  │
│ - langgraph  │     │ Found:           │     │ - comparisons │
│   notes      │     │ - mastra/mastra  │     │ - HN threads  │
│ - ai-app-    │     │ - langchain-ai/  │     │               │
│   stack-2026 │     │   langgraphjs    │     │               │
│              │     │ - CopilotKit/    │     │               │
│              │     │   CopilotKit     │     │               │
└──────┬──────┘     └────────┬─────────┘     └───────┬───────┘
       │                     │                       │
       └─────────────┬───────┘───────────────────────┘
                     ▼
            ┌────────────────┐
            │  Merge + Rank  │
            │  + Deduplicate │
            │  + Cross-ref   │
            │  with user's   │
            │  existing      │
            │  knowledge     │
            └────────────────┘
```

> **This is where we add value over vanilla search.** Three things happen that don't happen in a normal Google/Brave search:
>
> 1. **Vault cross-reference** — results are annotated with "you already have notes on this" or "this is new to you"
> 2. **Enhanced query** — we don't just pass the raw string to Brave. We decompose it into multiple targeted queries (one for repos, one for comparisons, one for recent news)
> 3. **Source-specific search** — GitHub API for repos, Brave for articles, HuggingFace for models. Each gets a tailored query, not the same string.

**Step 4 — User sees results**

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Search Results                                              │
│                                                                     │
│  Query: "open source agent frameworks in typescript..."             │
│  Found: 12 results across vault (3), GitHub (5), web (4)           │
│                                                                     │
│  ── FROM YOUR VAULT (you already know about these) ──────────────  │
│                                                                     │
│  📓 mastra.md                                        depth: ████░  │
│     "TS-native agents, workflows, memory, evals (23k stars)"       │
│     Last updated: 2026-04-18 — your notes are current              │
│                                                                     │
│  📓 ai-app-stack-2026.md                             depth: ███░░  │
│     Contains comparison table of Mastra, LangGraph, CopilotKit     │
│     Missing: no hands-on evaluation notes                          │
│                                                                     │
│  ── NEW TO YOU ──────────────────────────────────────────────────── │
│                                                                     │
│  ◻ 🔗 github.com/browserbase/stagehand         ⭐ 14.2k          │
│     Browser automation framework by Browserbase. TS. Active.       │
│     Relevance: agent tooling (not a framework itself — adjacent)   │
│                                                                     │
│  ◻ 🔗 github.com/pydantic/pydantic-ai          ⭐ 16.5k          │
│     ⚠️  Python, not TypeScript — included because it matches       │
│     memory + evals criteria. Consider for comparison.              │
│                                                                     │
│  ◻ 🔗 "Building Agents with Mastra in 2026"    — dev.to article   │
│     Walkthrough of Mastra's workflow + memory system.              │
│     Published: 2026-04-10                                          │
│                                                                     │
│  ◻ 🔗 "Mastra vs LangGraph.js: A Practical..."  — blog post       │
│     Side-by-side comparison with code examples.                    │
│                                                                     │
│  [more results...]                                                  │
│                                                                     │
│  ── ACTIONS ─────────────────────────────────────────────────────── │
│  [ ] Select results to save    [Absorb Selected]   [Refine Search] │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| | Detail |
|---|---|
| **User sees** | Results split into "already in your vault" vs. "new to you." Vault results show depth indicators and freshness. New results have checkboxes. |
| **Key UX detail** | The system tells you what you already know and how well you know it. This is the Lattice "knowledge state" concept applied to search. |
| **Layer** | L4 (Interface — rendering), L2b (Search — results), L2c (Reasoning — depth assessment of existing notes) |

> **Inflection Point #2:** How do we measure "depth" of existing notes?
>
> Simple version: word count, link count, last-modified date.
> Agentic version: the system has actually read the note, extracted claims, and knows the granularity of the user's understanding.
>
> The simple version ships in Phase 2. The agentic version requires Phase 3 (Reasoning module). **Both are valid starting points.** The UX is the same either way — just the quality of the depth indicator improves over time.

---

### Act 2: ABSORB — "Add this to what I know"

**Step 5 — User selects what to absorb**

| | Detail |
|---|---|
| **User does** | Checks 3 results: the Mastra walkthrough, the comparison blog post, and the Stagehand repo. Clicks "Absorb Selected." |
| **Screen** | Selection checkboxes → confirmation with options. |

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Absorb — Confirm & Configure                                │
│                                                                     │
│  You selected 3 sources to absorb:                                  │
│                                                                     │
│  1. "Building Agents with Mastra in 2026"         — article        │
│  2. "Mastra vs LangGraph.js: A Practical..."      — blog post      │
│  3. github.com/browserbase/stagehand              — repo           │
│                                                                     │
│  How should I handle this?                                          │
│                                                                     │
│  ● Smart merge — add new info to existing notes where relevant,    │
│    create new notes only for genuinely new topics                   │
│  ○ Separate notes — one new note per source, link to existing      │
│  ○ Append — add a section to a specific note I choose              │
│  ○ Just save raw — clip the sources, I'll organize later           │
│                                                                     │
│  Advanced:                                                          │
│  [x] Extract claims and tag with confidence                        │
│  [x] Find where this connects to existing notes                    │
│  [ ] Generate a summary note across all 3 sources                  │
│                                                                     │
│                                    [Preview Plan]  [Absorb Now]     │
└─────────────────────────────────────────────────────────────────────┘
```

**Step 6 — System plans the absorption**

|                 | Detail                                                                                                                                          |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **System does** | The **Ingestion Agent** reads each source, extracts claims, then the **Placement Agent** figures out where things go in the vault.              |
| **Layer**       | L2a (Ingestion — extract claims from sources), L2c (Reasoning — match claims to existing knowledge), L2b (Search — find related existing notes) |

```
SYSTEM INTERNALS — Absorption Pipeline

Source 1: "Building Agents with Mastra in 2026"
│
├── Fetch content (web scrape / reader mode)
├── Extract claims:
│   ├── "Mastra supports graph-based workflows natively"    [strong]
│   ├── "Memory in Mastra persists across agent sessions"   [strong]
│   ├── "Mastra integrates with Vercel AI SDK for UI"       [strong]
│   └── "Mastra's eval system can run offline"              [moderate]
│
├── Cross-reference with vault:
│   ├── ai-app-stack-2026.md — already mentions Mastra comparison → MERGE
│   ├── mastra.md — if exists, append new claims → MERGE
│   └── No existing note on Mastra workflows specifically → NEW NOTE candidate
│
└── Proposed action:
    ├── Update ai-app-stack-2026.md: add detail to Mastra row
    ├── Create 20-notes/ai/agents/mastra-deep-dive.md (new topic)
    └── Link from existing mastra references

Source 3: github.com/browserbase/stagehand
│
├── Fetch: README + package.json + key source files
├── Extract claims:
│   ├── "Stagehand is for browser automation, not agent orchestration" [strong]
│   ├── "Built on Playwright under the hood"                          [strong]
│   └── "Can be used as a tool within an agent framework"             [moderate]
│
├── Cross-reference with vault:
│   ├── ai-app-stack-2026.md — listed under Web Automation → MERGE
│   └── No existing deep note → NEW NOTE only if user wants depth
│
└── Proposed action:
    ├── Update ai-app-stack-2026.md: enrich Browserbase/Stagehand entry
    └── Optionally create 20-notes/ai/agents/stagehand.md
```

**Step 7 — User reviews the plan (if they clicked "Preview Plan")**

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Absorption Plan — Review Before Applying                    │
│                                                                     │
│  Here's what I'll do:                                               │
│                                                                     │
│  📝 UPDATE  ai-app-stack-2026.md                                   │
│     + Expand Mastra section with workflow details, eval notes       │
│     + Enrich Stagehand entry with architecture details             │
│     (2 sections affected, ~15 lines added)                         │
│                                                                     │
│  📄 CREATE  20-notes/ai/agents/mastra-deep-dive.md                 │
│     New note: Mastra's workflow system, memory model, eval setup   │
│     Claims: 6 extracted, 4 strong, 2 moderate                     │
│     Links to: [[ai-app-stack-2026]], [[effective-agent-design]]    │
│                                                                     │
│  📄 CREATE  20-notes/ai/agents/mastra-vs-langgraph.md              │
│     New note: Side-by-side comparison (from blog post)             │
│     Claims: 8 extracted, 5 strong, 3 moderate                     │
│     Links to: [[ai-app-stack-2026]], [[mastra-deep-dive]]          │
│                                                                     │
│  📓 SKIP    Stagehand — only a minor update to existing note,      │
│     not enough new info to warrant a separate note.                │
│     (Override: [Create note anyway])                                │
│                                                                     │
│                          [Edit Plan]  [Approve & Apply]  [Cancel]   │
└─────────────────────────────────────────────────────────────────────┘
```

| | Detail |
|---|---|
| **User sees** | A diff-style preview of what will be created/updated. Can edit, approve, or cancel. |
| **Key UX detail** | The system makes a judgment call (skip Stagehand as a separate note) but lets the user override. Transparent reasoning. |
| **Layer** | L4 (Interface), L2a (Ingestion — the extraction), L2c (Reasoning — the placement logic) |

**Step 8 — System executes the absorption**

| | Detail |
|---|---|
| **System does** | Writes/updates files. Stores claims + relationships in SQLite. Generates embeddings for new content. Updates the knowledge graph. |
| **Layer** | L0 (Data — write to vault + SQLite + vectors), L2a (Ingestion — execute), L2e (Observability — log what was done) |

> **Inflection Point #3:** Who decides where notes go — the user or the system?
>
> This is a real tension. Too much automation and the user loses ownership of their vault structure. Too little and we're just a fancy clipboard.
>
> **Current stance:** System proposes, user approves. The "Preview Plan" step is mandatory for structural changes (new files, moving content). For appending to existing notes, the system can act with less friction.
>
> This matches the principle from [[00-master-plan]]: "the agent knows when to stop."

---

### Act 3: RETRIEVE — "What do I know about Y?"

**Step 9 — User asks a knowledge question (later session, or same session)**

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Main Surface (Chat Mode)                                    │
│                                                                     │
│  💬 Chat                          🔍 Search                        │
│  ─────────────────────────────────────────────                      │
│                                                                     │
│  You: "What do I actually know about agent memory?                  │
│        Am I deep enough to write about it?"                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| | Detail |
|---|---|
| **User does** | Asks a retrieval question — not "search the web" but "what's in MY knowledge base." |
| **Screen** | Chat interface. The toggle between Chat and Search is important — different intent, different behavior. |

**Step 10 — System retrieves and assesses**

| | Detail |
|---|---|
| **System does** | The **Retrieval Agent** searches the vault (BM25 + vector), pulls relevant claims from SQLite, then the **Reasoning Agent** assesses the user's knowledge state on this topic. |
| **Layer** | L2b (Search — vault retrieval), L2c (Reasoning — knowledge state assessment), L2d (Memory — recall past interactions on this topic) |

```
SYSTEM INTERNALS — Knowledge State Assessment

Query: "What do I know about agent memory?"

Step 1 — Retrieve relevant content:
  Vault hits:
    - agentic-loop-v1/skills.md (mentions memory briefly)
    - ai-app-stack-2026.md (Mem0 listed, Mastra memory mentioned)
    - mastra-deep-dive.md (memory persistence across sessions)
    - lattice/11-knowledge-model.md (memory as knowledge graph)

  Claim database:
    - 4 claims about Mem0 (surface-level, from reference notes)
    - 3 claims about Mastra memory (moderate depth, from article)
    - 6 claims about knowledge graph as memory (deep, from Lattice design)
    - 0 claims about memory architectures in general (gap!)

Step 2 — Assess knowledge state:
  Coverage:    ██░░░ (2/5) — you know a few tools, but not the design space
  Depth:       ██░░░ (2/5) — Lattice design is deep, everything else is surface
  Diversity:   █░░░░ (1/5) — all your sources are tool docs, no research papers
  Recency:     ████░ (4/5) — your notes are from the last 2 weeks
  Conflicts:   none detected

Step 3 — Generate assessment:
  "You know about specific tools (Mem0, Mastra) but lack a
   conceptual framework for agent memory as a design space.
   Your Lattice knowledge model is the deepest work here,
   but it's about YOUR memory model, not agent memory in general.
   You could write a tools comparison. You can't yet write
   about memory architecture patterns."
```

**Step 11 — User sees the assessment**

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCREEN: Knowledge Assessment                                        │
│                                                                     │
│  Topic: Agent Memory                                                │
│                                                                     │
│  Coverage  ██░░░  You know specific tools, not the design space     │
│  Depth     ██░░░  Lattice model is deep; rest is surface            │
│  Diversity █░░░░  All tool docs, no research or papers              │
│  Recency   ████░  Notes are current (last 2 weeks)                  │
│                                                                     │
│  📋 What you know:                                                  │
│  • Mem0 — persistent memory layer, learns preferences (surface)     │
│  • Mastra — memory persists across sessions (moderate)              │
│  • Your Lattice design uses a knowledge graph approach (deep)       │
│                                                                     │
│  🕳️ What's missing:                                                │
│  • No framework for memory architectures (buffer, summary,          │
│    entity, graph — the taxonomy)                                    │
│  • No understanding of how memory interacts with context windows    │
│  • No research papers or foundational sources                       │
│                                                                     │
│  💡 Verdict: You could write a tools comparison today. You can't    │
│  yet write about memory architecture patterns.                      │
│                                                                     │
│  [Find sources to fill gaps]  [Show me my notes]  [I'll write anyway│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| | Detail |
|---|---|
| **User sees** | An honest assessment of their knowledge state, with specific gaps identified and actionable next steps. |
| **Key UX detail** | Clicking "Find sources to fill gaps" loops back to Act 1 (DISCOVER), but now with a targeted query generated from the gaps. The loop closes. |
| **Layer** | L4 (Interface), L2c (Reasoning — the assessment), L3 (Skills — the assessment skill could be extracted and used standalone) |

---

## The Complete System Flow

```
USER                          SYSTEM                           LAYER
─────                         ──────                           ─────

"Find me TS agent             Query Understanding Agent         L1
 frameworks with              parses intent, constraints        L2b
 memory + evals"
                              ┌─── Vault Search (BM25+vec) ──→ L2b
                              ├─── GitHub API Search ─────────→ L2b
         ◄── search ────────  └─── Brave Web Search ──────────→ L2b
             results                Merge + Rank + Dedup        L2b
             (vault vs new)         Cross-ref with vault        L2c

"Save these 3 to              Ingestion Agent                  L2a
 my notes"                    fetches content, extracts claims
                              Placement Agent                   L2c
         ◄── plan ────────    proposes where to put things      L2b
             (preview)        (update vs. create vs. skip)

"Looks good,                  Writes files to vault             L0
 approve"                     Stores claims in SQLite           L0
                              Generates embeddings              L0
                              Logs the action                   L2e

[later]
"What do I know               Retrieval Agent                   L2b
 about agent memory?          searches vault + claim DB
 Can I write about it?"
                              Reasoning Agent                   L2c
         ◄── assessment ──    assesses coverage, depth,
             with gaps        diversity, conflicts
                              Memory Agent                      L2d
                              recalls past queries on topic

"Fill my gaps"                → loops back to DISCOVER          L1
                              with gap-derived query             L2b
```

---

## Agents Required

Each agent is a specific configuration of the core runtime (L1) with particular tools and instructions.

| Agent | Purpose | Tools It Uses | Layer |
|---|---|---|---|
| **Orchestrator** | Routes user intent to the right agent/workflow. The "brain" that decides what to do. | All other agents (as sub-tasks) | L1 |
| **Query Understanding** | Parses natural language into structured search intent: entities, constraints, strategy. | None (pure LLM reasoning) | L2b |
| **Search Executor** | Runs searches across multiple sources in parallel. Merges, ranks, deduplicates. | Vault search, GitHub API, Brave API, HuggingFace API | L2b |
| **Ingestion** | Fetches source content, extracts atomic claims, assigns confidence and evidence type. | Web scraper/reader, claim extractor, SQLite writer | L2a |
| **Placement** | Decides where absorbed content belongs in the vault. Proposes file operations. | Vault search, file reader, file writer | L2a + L2c |
| **Retrieval** | Finds relevant content from the vault and claim database for a user question. | BM25 search, vector search, SQLite query | L2b |
| **Reasoning** | Assesses knowledge state: coverage, depth, diversity, conflicts, gaps. Classifies relationships between claims. | Claim DB reader, relationship classifier | L2c |
| **Memory** | Tracks session history, user preferences, past queries. Enables "since last time" awareness. | Session store, user model DB | L2d |

> **Inflection Point #4:** Are these truly separate agents or just different tool sets + system prompts on the same agent loop?
>
> Architecturally, each "agent" above is the SAME core runtime (L1) with different:
> - System prompt (who you are, what you do)
> - Tool set (what you can call)
> - Guardrails (what you're not allowed to do)
>
> Whether they run as separate processes or are just configs within one loop is an implementation detail. For now, think of them as **roles**, not separate programs. This aligns with the single-agent finding from [[single-vs-multi-agent-reasoning]].

---

## Where We Add Value Over Vanilla Claude Code

A user can already do much of this in Claude Code or Wibey today — just more manually. Here's where the Second Brain app is genuinely different:

| Capability | Claude Code / Wibey Today | Second Brain App |
|---|---|---|
| **Search** | User writes the query, reads results, decides what's relevant | System decomposes query, searches multiple sources in parallel, cross-references with existing knowledge, annotates "you already know this" |
| **Ingest** | User copies text, manually creates notes, organizes files | System extracts claims, proposes placement, merges with existing notes, maintains links |
| **Retrieve** | User searches files with grep/glob, asks LLM questions about them | System searches claims + embeddings + files, assesses knowledge *state* (depth, gaps, conflicts), not just content |
| **Memory** | Starts fresh each session | Remembers past queries, tracks what changed, enables "since last time" |
| **Knowledge model** | None — files are flat text | Claims, relationships, confidence scores, source provenance — structured knowledge graph |
| **Proactive** | Only responds to prompts | Can surface: "your notes on X are stale", "new conflict detected", "you're deep on A but thin on B" |

> **The core differentiator is the knowledge model.** Everything else (search, ingest, retrieve) is made better by having a structured understanding of what the user knows, not just what files exist.

---

## How This Maps to Shareable Artifacts

Each piece of the flow above produces something independently useful:

```
Flow Step              Shareable Artifact              Audience
──────────             ──────────────────              ────────

Query Understanding    skill: query-decomposer         Coding agent users
                       (decompose vague queries)       (Claude Code, Wibey)

Search Execution       package: bm25-from-scratch      Developers learning IR
                       package: hybrid-search           Developers building search
                       skill: github-repo-scout         Coding agent users

Ingestion              skill: extract-claims            Coding agent users
                       package: claim-extractor         Developers building KM tools

Placement              skill: smart-note-merger         Obsidian users
                       (merge new info into vault)

Knowledge Assessment   skill: analyze-notes             Coding agent users
                       (assess depth/gaps/conflicts)

Observability          package: agent-trace-viewer      Developers building agents
                       blog: "what my agent actually    AI builders (content)
                        does in 47 steps"
```

---

## Interaction Modes — Chat vs. Search vs. Proactive

The app has three interaction modes, not just one:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   💬 CHAT          🔍 SEARCH        🔔 BRIEFING    │
│   ──────────       ──────────       ──────────      │
│   Conversational   Structured       System-initiated│
│   back-and-forth   query → results  "here's what    │
│                    → absorb flow     changed"        │
│                                                     │
│   "What do I know  "Find me TS      "3 notes on     │
│    about RAG?"     agent frameworks  RAG are stale.  │
│                    with evals"       2 new conflicts │
│   Uses: Retrieval  Uses: Search,    detected."      │
│   + Reasoning      Ingestion                        │
│                                     Uses: Reasoning │
│   → answer with    → results with   + Memory        │
│     assessment       vault cross-                    │
│                      reference      → digest with    │
│                                       action items   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

> **Inflection Point #5:** Do we build all three modes, or just Chat first?
>
> The Search flow is the most complex (multiple agents, parallel sources, absorption pipeline). Chat is simpler (retrieval + reasoning, no web search needed). Briefing is proactive (runs on a schedule, no user trigger).
>
> **Suggested sequence:** Chat first (Phase 2-3), Search second (Phase 3-4), Briefing last (Phase 4-5). But the user journey described above starts with Search because that's the most compelling demo.
>
> **No decision forced here.** This is a build-order question we'll resolve when we get to phase planning.

---

## Open Questions (Captured, Not Resolved)

These surfaced while mapping the flow. They're here so we don't lose them, not because they need answers now.

1. **How does the user authenticate with external APIs?** (GitHub, Brave, HuggingFace) — do we manage keys, or does the user bring their own?
2. **How do we handle content that requires login?** (paywalled articles, private repos)
3. **What's the latency budget?** Search should feel fast (<3s for vault, <10s for web). Absorption can be slower (async).
4. **How do we handle conflicting claims from different sources?** Surface both? Auto-resolve? Ask the user?
5. **Can the user undo an absorption?** If the system modified 3 files, can they roll it back? (Git integration?)
6. **How does this work offline?** Vault search and retrieval should work without internet. Web search obviously can't.
7. **What's the minimum viable knowledge model?** Can we ship value with just claims + tags (no relationships), and add relationship reasoning later?
8. **How do skills get distributed?** A GitHub repo of markdown files? An npm package? A Wibey skill registry?

---

## What This Document Is (and Isn't)

**Is:** A raw v0 decomposition of one user journey through the system. It maps user actions to system behavior to architecture layers. It surfaces inflection points where decisions are needed.

**Isn't:** A spec. Nothing here is committed. The screens are sketches of information architecture, not UI designs. The agent list is roles, not final implementations. The flow will change as we build.

**Next:** We can double-click on any section — the search pipeline, the ingestion pipeline, the knowledge assessment, the agent architecture, or the tech stack choices that enable each layer.

---

*See also: [[00-master-plan]] for the layer architecture and build sequence.*
