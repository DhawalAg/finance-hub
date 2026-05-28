---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
ground-truth: true
---

# Second Brain — Master Plan

> A locally-deployed autonomous intelligence layer over my Obsidian vault, built as a modular system where each piece is independently useful and publicly shareable.

---

## Guiding Principles

1. **Inside-out** — nail each inner layer before building the next
2. **Ship small** — every layer produces at least one standalone public artifact
3. **Ground truth lives here** — this project may diverge from earlier docs in `lattice/`, `agentic-search/`, etc. When it does, this is canonical
4. **Local-first** — runs on my machine, my data stays mine
5. **Dual-surface** — code modules power the app; skill files work in any coding agent (Claude Code, Wibey, etc.)

---

## Architecture — The Four Layers

```
┌─────────────────────────────────────────────────────┐
│  Layer 4: INTERFACE                                  │
│  How I interact with the system                      │
│  CLI → TUI → Web UI (progressive)                   │
├─────────────────────────────────────────────────────┤
│  Layer 3: SKILLS                                     │
│  Portable intelligence — prompts, instructions,      │
│  agent behaviors. Shareable as standalone files.      │
│  Works in this app AND in Claude Code / Wibey / etc. │
├─────────────────────────────────────────────────────┤
│  Layer 2: MODULES                                    │
│  Code capabilities — search, ingestion, reasoning,   │
│  memory. Each is an independent package.             │
├─────────────────────────────────────────────────────┤
│  Layer 1: CORE RUNTIME                               │
│  The agentic loop, orchestration, tool execution,    │
│  context management, observability hooks.             │
└─────────────────────────────────────────────────────┘
         ▼ sits on top of ▼
┌─────────────────────────────────────────────────────┐
│  Layer 0: DATA                                       │
│  Obsidian vault (markdown), SQLite (structured),     │
│  vector store (embeddings)                           │
└─────────────────────────────────────────────────────┘
```

---

## Layer 0: DATA

**What it is:** The foundation everything reads from and writes to. Not code I build — it's the storage substrate.

**Components:**
- **Obsidian vault** — markdown files, the raw knowledge (`~/my-obsidian/`)
- **SQLite** — structured metadata: claims, relationships, confidence scores, ingestion logs
- **Vector store** — embeddings for semantic search (pgvector via Supabase later; local FAISS or SQLite-vec to start)

**What's shareable:** Nothing directly — this is my data. But the *schema* for the SQLite knowledge model is shareable as a reference design.

**Key decision:** Start with SQLite + SQLite-vec (zero infrastructure). Graduate to Supabase when/if the app goes multi-device or needs auth.

---

## Layer 1: CORE RUNTIME

**What it is:** The engine that makes everything agentic. A single-agent loop that takes a goal, selects tools, executes steps, manages context, and knows when to stop.

**Components:**
- **Agent loop** — message cycle: user → LLM → tool call → result → LLM → ... → done
- **Tool registry** — declares available tools, validates inputs, routes execution
- **Context manager** — tracks token budget, compresses history when needed
- **Orchestrator** — decides which module/skill to invoke for a given task
- **Observability hooks** — emit traces, timings, token counts, costs at every step

**Key design choices:**
- Single-agent (not multi-agent) — per the research in [[single-vs-multi-agent-reasoning]], single-agent matches or beats multi-agent at equal token budgets
- Model-agnostic — works with Ollama (local) and Claude/OpenAI (API) via provider abstraction
- Stateless between runs — all persistent state lives in Layer 0

**What's shareable:**
- `core-agent-loop` — a minimal, well-documented agent loop package anyone can use as a starting point
- Blog post: "Building an agent loop from scratch"

**Depends on:** Layer 0 (reads/writes data)

---

## Layer 2: MODULES

**What it is:** Discrete capabilities the agent can use. Each module is a self-contained package with a clear interface. The agent calls them as tools.

**Modules (build order):**

### 2a. Ingestion
- Takes a markdown file (or URL) → extracts atomic claims → stores in SQLite with metadata
- Handles: note files, web articles, PDFs
- Key output: structured claims with source, confidence, evidence type

### 2b. Search
- Hybrid search across the vault: keyword (BM25) + semantic (vector) + structured (SQLite)
- Reranking and fusion of results
- The vault becomes queryable, not just browsable

### 2c. Reasoning
- Given a set of claims, classify relationships: supports, contradicts, extends, qualifies, supersedes
- Detect conflicts, compute confidence, propagate implications
- This is the core of what makes the system agentic — it reasons about knowledge *state*

### 2d. Memory
- Persistent memory across sessions — what was asked, what was found, what changed
- User model: tracks what the user knows deeply vs. superficially
- Enables proactive behavior: "Since last week, 3 new articles contradicted your view on X"

### 2e. Observability
- Trace collection: every LLM call, tool invocation, and decision logged
- Cost tracking: tokens in/out, model used, latency
- Eval hooks: measure claim extraction accuracy, relationship classification quality
- Export format compatible with Langfuse / OpenTelemetry

**What's shareable (per module):**
| Module | Public Artifact |
|--------|----------------|
| Ingestion | `claim-extractor` — extract claims from any markdown file |
| Search | `bm25-from-scratch` — educational BM25 implementation |
| Search | `hybrid-search` — combine keyword + semantic search |
| Reasoning | `relationship-classifier` — classify how two claims relate |
| Memory | Schema + design doc (the approach, not the personal data) |
| Observability | `agent-trace-viewer` — CLI tool to inspect agent runs |

**Depends on:** Layer 1 (called by the agent as tools), Layer 0 (reads/writes data)

---

## Layer 3: SKILLS

**What it is:** Portable intelligence in markdown. Skills are prompts + instructions that encode *how* to do something. They work in two contexts:

1. **Inside the app** — the agent loads them to gain capabilities
2. **Standalone** — users drop them into Claude Code, Wibey, Cursor, etc. and get the same behavior

**Skill categories:**

### 3a. Knowledge Skills
- `analyze-notes` — analyze a folder of notes, produce a knowledge map (topics, depth, gaps)
- `extract-claims` — parse a document into atomic, verifiable claims
- `find-conflicts` — surface contradictions across a set of notes
- `weekly-briefing` — summarize what changed in my knowledge this week

### 3b. Research Skills
- `deep-research` — multi-step research on a topic using vault + web sources
- `source-evaluation` — assess the quality and credibility of a source
- `gap-analysis` — given what I know about X, what should I read next?

### 3c. Writing Skills
- `draft-from-notes` — compose a draft from a set of linked notes
- `explain-like-five` — simplify complex notes for broader audiences
- `thread-writer` — turn a note into a Twitter/X thread

### 3d. System Skills
- `vault-health` — check for orphan notes, broken links, stale content
- `daily-digest` — generate today's daily note with relevant context
- `tag-auditor` — audit and normalize tags across the vault

**What's shareable:** ALL of them. Skills are the primary public distribution channel. Each skill is a markdown file someone can copy into their own setup.

**Depends on:** Layer 2 (skills often invoke modules), but many skills are self-contained prompts that work without the app

---

## Layer 4: INTERFACE

**What it is:** How I interact with the system. Built progressively — don't build UI until the layers underneath work.

**Progression:**
1. **CLI** (first) — command-line tool. `brain search "what do I know about RAG?"`, `brain ingest ./notes/`, `brain brief`
2. **TUI** (second) — terminal UI with rich output, maybe using Ink (React for CLIs)
3. **Web UI** (later) — Next.js + shadcn/ui, the full Lattice vision with the three views

**What's shareable:** The CLI itself is the public artifact. A tool anyone can point at their own vault.

**Depends on:** All layers below

---

## How Existing Projects Map

| Existing Project | Maps To | Status |
|---|---|---|
| `lattice/` | Overall vision + Layer 2c (Reasoning) + Layer 4 (Web UI) | Design done, not built |
| `agentic-search/` | Layer 2b (Search) — learning roadmap | Research phase |
| `agentic-loop-v1/` | Layer 1 (Core Runtime) — reference harness | Reference code exists |
| `ai-observability/` | Layer 2e (Observability) | Seed brief |

Everything fits. Nothing is wasted. This plan gives each project a home.

---

## Build Sequence — Inside Out

> Each phase ends with at least one shipped public artifact.

### Phase 1: Foundation (Weeks 1-3)
**Focus:** Layer 0 + Layer 1

- [ ] Define SQLite schema for claims, relationships, sources
- [ ] Build the agent loop (port/evolve from `agentic-loop-v1/`)
- [ ] Tool registry with 3 basic tools: read-file, search-files, write-file
- [ ] Context window management (compression at threshold)
- [ ] Basic observability: log every step to JSON

**Ship:** `core-agent-loop` — minimal agent loop package + blog post

### Phase 2: First Capability (Weeks 4-6)
**Focus:** Layer 2a (Ingestion) + Layer 2b (Search)

- [ ] Claim extraction from markdown files
- [ ] BM25 search over vault content
- [ ] Vector embeddings (local model via Ollama)
- [ ] Hybrid search: BM25 + semantic with simple fusion
- [ ] Wire into agent as tools

**Ship:** `claim-extractor` + `bm25-from-scratch` + blog posts

### Phase 3: Intelligence (Weeks 7-10)
**Focus:** Layer 2c (Reasoning) + Layer 3 (first skills)

- [ ] Relationship classification between claims
- [ ] Conflict detection across the vault
- [ ] Confidence scoring and propagation
- [ ] First batch of skills: `analyze-notes`, `extract-claims`, `find-conflicts`
- [ ] Skills work standalone in Claude Code / Wibey

**Ship:** Skills bundle (publicly shareable) + `relationship-classifier` + blog post

### Phase 4: Interface (Weeks 11-14)
**Focus:** Layer 4 (CLI) + Layer 2d (Memory)

- [ ] CLI tool: `brain` command with subcommands
- [ ] Session memory: what was asked, what changed
- [ ] Daily/weekly briefing generation
- [ ] Remaining skills: `weekly-briefing`, `vault-health`, `daily-digest`

**Ship:** `brain` CLI (open-source) + skills bundle v2

### Phase 5: Polish & Platform (Weeks 15-20)
**Focus:** Layer 2e (Observability) + Layer 4 (Web UI)

- [ ] Full trace collection and viewer
- [ ] Cost dashboard
- [ ] Web UI with the three Lattice views (What You Know, Conflicts, Gaps)
- [ ] Eval framework: measure quality of each module

**Ship:** `agent-trace-viewer` + Lattice web app v0.1

---

## Tech Stack (Decided Later — Noted Here for Reference)

> Language and framework decisions are deferred. When we're ready, we'll create `01-tech-stack.md` with the full breakdown per layer.

**Leaning toward:**
- TypeScript (single language for frontend + backend + CLI)
- Ollama for local LLM + Claude API for heavy reasoning
- SQLite (start) → Supabase (when needed)
- See [[ai-app-stack-2026]] for the full landscape

**Open questions:**
- TypeScript vs. Python — TS gives one language across all layers; Python has richer ML/NLP ecosystem
- Which agent framework (if any) — Mastra, raw Vercel AI SDK, or hand-rolled?
- Vector store: SQLite-vec, FAISS, or skip straight to pgvector?

---

## Credibility Playbook (Decided Later)

> Communication strategy, naming, and marketing are deferred. When we're ready, we'll create `02-credibility-playbook.md`.

**The pattern:**
- Each phase ships 1-2 public artifacts (packages, skills, tools)
- Each artifact gets a companion blog post (→ `60-writing/`)
- Skills are the easiest win — zero infrastructure, immediately useful
- Build in public: share progress, decisions, learnings

---

## File Index

| File | Purpose |
|---|---|
| `00-master-plan.md` | This file — architecture, layers, build sequence |
| `01-user-flow-v0.md` | Raw v0 user journey: Discover → Absorb → Retrieve |
| `02-steelman-and-reframe.md` | Critical review + strategic pivot: personal agent, built in public |
| `03-tech-stack.md` | Tech decisions per layer (TBD) |
| `04-credibility-playbook.md` | Marketing & sharing strategy (TBD) |
| `L0-data-schema.md` | SQLite schema design (TBD) |
| `L1-core-runtime.md` | Agent loop deep-dive (TBD) |
| `L2a-ingestion.md` | Ingestion module spec (TBD) |
| `L2b-search.md` | Search module spec (TBD) |
| `L2c-reasoning.md` | Reasoning module spec (TBD) |
| `L2d-memory.md` | Memory module spec (TBD) |
| `L2e-observability.md` | Observability module spec (TBD) |
| `L3-skills.md` | Skills catalog and authoring guide (TBD) |
| `L4-interface.md` | CLI / TUI / Web UI spec (TBD) |

---

*This is a living document. It is the single source of truth for the Second Brain project.*
