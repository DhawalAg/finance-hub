---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---

# Second Brain — Build Roadmap

> Phased execution plan for the Second Brain project. Supersedes the build sequence in [[00-master-plan]] and incorporates the strategic reframe from [[02-steelman-and-reframe]].

---

## Roadmap Philosophy

Three principles govern sequencing:

1. **Outside-in for search, inside-out for reasoning.** The search experience ships first because it delivers immediate personal utility and establishes the CLI foundation. Once search works, the ingestion and reasoning pipeline builds inward — each layer proving itself before the next builds on it.

2. **Ship every 2-3 weeks.** Every phase ends with at least one public artifact: an npm package, a prompt template bundle, or a blog post. If a phase has nothing shippable, the phase is scoped wrong.

3. **Eval-first.** The Week 0 test set is not a throwaway exercise. It becomes the eval baseline that every subsequent module is measured against. Evaluation is not Phase 5 — it is embedded in every phase from the start. Each module ships with a test harness that runs against the growing eval set.

---

## Phase Table

| Phase | Timeframe | Focus | Code Deliverables | Content Deliverables | Key Risk |
|-------|-----------|-------|-------------------|---------------------|----------|
| S | Weeks 0-4 | Search flow (outside-in) | `brain` CLI with search, query decomposition, LLM scoring | Blog: "Building search before building ingestion" | API rate limits, scoring calibration across sources |
| 0 | Week 5 | Thesis validation | Test dataset, eval prompts | Blog post + dataset | LLM can't classify relationships at >=65% accuracy |
| 1 | Weeks 6-8 | Core loop + claim extraction | `core-agent-loop`, `claim-extractor` | Blog: "Building an agent loop from scratch" | Agent loop scope creep (context mgmt, error handling) |
| 2 | Weeks 9-11 | Vault search + prompt templates | `bm25-from-scratch`, `hybrid-search` | Prompt template bundle v1, blog on hybrid search | Embedding quality on local models (Ollama) |
| 3 | Weeks 12-15 | Reasoning + conflict detection | `relationship-classifier` | Prompt template bundle v2, blog on knowledge state | Relationship taxonomy too coarse or too fine |
| 4 | Weeks 16-19 | CLI extensions + memory | `brain` CLI v1.0 | Prompt template bundle v3 | Session memory adds complexity without clear UX payoff |
| 5 | Weeks 20-25 | Observability + web UI | `agent-trace-viewer`, Lattice web v0.1 | Launch post: "What my agent actually does" | Web UI scope explosion — three Lattice views is a lot |

---

## Detailed Phase Breakdown

> **Strategy shift (April 2026):** The roadmap now starts with the search experience (Phase S) rather than ingestion. The search flow is built first because it delivers immediate personal utility and establishes the CLI foundation. The ingestion pipeline (Phase 0-1) follows, feeding into the search experience.

### Phase S: Search Flow (Weeks 0-4)

**Goal:** Build an external search experience from the outside in. Start with a single-source web search, expand to multi-source fan-out with LLM scoring, then bridge to the vault. The `brain` CLI ships as the first artifact — search is the entry point, not ingestion.

**Tasks:**
- [ ] **A1 — Single-source search.** Brave Search API integration, Commander.js CLI scaffold, `brain search "query"` returns ranked web results (Bun + TypeScript)
- [ ] **A2 — Multi-source fan-out.** Add GitHub and Twitter/X sources alongside Brave. Implement query decomposition via OpenRouter (small/fast model) to split complex queries into sub-queries per source
- [ ] **A3 — LLM scoring columns.** Score each result on relevance, recency, and depth using rubric-anchored prompts via OpenRouter. Results display as a scored table in the terminal
- [ ] **A4 — Vault cross-reference.** BM25 search over local vault via MiniSearch. Add a novelty column to scored results: NEW / IN VAULT / PARTIAL — surfacing what you already have vs. what's net-new
- [ ] **A5 — Interactive REPL session.** After initial results, enter a session: compare results, skim sources, queue items for later, refine the query, ask free-form follow-ups

**Tech stack:** Bun + TypeScript + Commander.js + Vercel AI SDK + OpenRouter

**Ship artifacts:**
- `brain` CLI v0.1 with `brain search` command
- Blog post: "Building search before building ingestion"
- Blog post: "Scoring search results with LLMs — rubric-anchored prompts"

**Success criteria:**
- `brain search "query"` returns scored, multi-source results in <5 seconds for typical queries
- Novelty column correctly identifies vault matches on >=80% of test queries where overlap exists
- REPL session supports at least: compare two results, refine query, free-form follow-up question
- The CLI runs as a single Bun-compiled binary with zero runtime dependencies

**Note:** The thesis test (Phase 0) runs after this phase. Search delivers daily utility immediately; the thesis test validates the deeper reasoning premise before investing in the ingestion pipeline.

---

### Phase 0: Thesis Test (Week 5)

**Goal:** Answer the foundational question before writing application code. Can an LLM classify relationships between knowledge claims at >=65% accuracy?

**Tasks:**
- [ ] Select 10-15 notes from the vault spanning different domains and depth levels
- [ ] Manually extract claims from each note — force a working definition of "claim"
- [ ] Create 30-50 claim pairs with hand-labeled relationships (supports, contradicts, extends, qualifies, supersedes)
- [ ] Run Claude and Ollama (local) against the labeled set
- [ ] Score precision and recall per relationship type per model
- [ ] Document the claim ontology: what counts as a claim, what doesn't, with 20+ examples
- [ ] Write up results regardless of outcome

**Ship artifacts:**
- Blog post: "Can an LLM reason about knowledge state? I tested it."
- Public dataset: labeled claims + relationships from 10-15 vault notes (anonymized if needed)
- Evaluation prompts used for classification

**Success criteria:**
- At least one model achieves >=65% accuracy on relationship classification
- The claim ontology document exists with 20+ real examples and clear inclusion/exclusion rules
- Results are published

**Eval baseline established:** The labeled dataset from this phase becomes the ground truth for all subsequent module testing.

---

### Phase 1: Core Loop + Claim Extraction (Weeks 6-8)

**Goal:** A working agent that reads vault files and extracts structured claims. The inner loop runs, observability is present from day one.

**Tasks:**
- [ ] Define SQLite schema for claims, relationships, sources (see [[00-master-plan]] Layer 0)
- [ ] Build the agent loop — message cycle with tool calling, evolve from [[50-projects/agentic-loop-v1/single-agent-harness|agentic-loop-v1]]
- [ ] Implement tool registry with 3 basic tools: `read-file`, `search-files`, `write-file`
- [ ] Build claim extraction module: markdown in, structured claims out
- [ ] Context window management: compression at token threshold
- [ ] Basic observability: every LLM call, tool invocation, and decision logged to JSON
- [ ] Run claim extractor against Phase 0 test set — measure precision/recall vs. hand-labeled claims
- [ ] Package `claim-extractor` as standalone npm module with clear API

**Ship artifacts:**
- `core-agent-loop` npm package
- `claim-extractor` npm package
- Blog post: "Building an agent loop from scratch"

**Success criteria:**
- Agent loop completes a multi-step task (read 3 files, extract claims, write results) without manual intervention
- Claim extractor achieves >=70% F1 against hand-labeled claims from Phase 0
- Every agent step is logged with timestamps, token counts, and tool inputs/outputs

---

### Phase 2: Vault Search + First Prompt Templates (Weeks 9-11)

**Goal:** The vault becomes queryable through hybrid search. First standalone prompt templates ship as shareable markdown files.

**Tasks:**
- [ ] Implement BM25 search over vault markdown files
- [ ] Generate vector embeddings using local model via Ollama
- [ ] Store embeddings in SQLite-vec (zero infrastructure)
- [ ] Build hybrid search: BM25 + semantic with reciprocal rank fusion
- [ ] Wire search into agent as tools: `search-vault-keyword`, `search-vault-semantic`, `search-vault-hybrid`
- [ ] Benchmark: hybrid vs. BM25-only vs. semantic-only on 20 test queries from vault
- [ ] Author first prompt templates as standalone markdown files:
  - [ ] `analyze-notes` — assess a folder of notes for depth, coverage, gaps
  - [ ] `extract-claims` — standalone version of claim extraction for coding agents
- [ ] Test prompt templates in Claude Code and verify they work without app infrastructure

**Ship artifacts:**
- `bm25-from-scratch` npm package (educational, well-documented)
- `hybrid-search` npm package
- Prompt template bundle v1 (GitHub repo)
- Blog post: "What I learned building hybrid search from scratch"

**Success criteria:**
- Hybrid search outperforms BM25-only on >=60% of test queries (measured by manual relevance judgment)
- Prompt templates produce useful output when run in Claude Code with zero setup
- Embedding generation completes for full vault in <5 minutes on local hardware

---

### Phase 3: Reasoning + Conflict Detection (Weeks 12-15)

**Goal:** The agent reasons about knowledge state. This is the core thesis in code — the module version of the Phase 0 experiment.

**Tasks:**
- [ ] Build relationship classification module: given two claims, classify as supports/contradicts/extends/qualifies/supersedes
- [ ] Implement batch classification: run across all claim pairs in a topic cluster
- [ ] Build conflict detection: surface contradictions across the vault automatically
- [ ] Implement confidence scoring: assign and propagate confidence across claim chains
- [ ] Build knowledge state assessment: coverage, depth, diversity metrics per topic (the bars from [[01-user-flow-v0]])
- [ ] Run relationship classifier against Phase 0 labeled set — measure accuracy improvement over raw prompting
- [ ] Author prompt templates:
  - [ ] `find-conflicts` — surface contradictions across a set of notes
  - [ ] `gap-analysis` — given what I know about X, what's missing?

**Ship artifacts:**
- `relationship-classifier` npm package
- Prompt template bundle v2
- Blog post: "How my agent detects what I don't know"

**Success criteria:**
- Relationship classifier achieves >=70% accuracy on Phase 0 test set (up from >=65% raw prompting baseline)
- Conflict detection surfaces at least 3 real contradictions in the vault that the author wasn't aware of
- Knowledge state assessment produces coherent depth/coverage/diversity ratings on 5 test topics

---

### Phase 4: CLI Extensions + Memory (Weeks 16-19)

**Goal:** A usable interface. The agent remembers across sessions and produces briefings.

**Tasks:**
- [ ] Build `brain` CLI with subcommands: `search`, `ingest`, `assess`, `brief`, `status`
- [ ] Implement session memory: persist what was asked, what was found, what changed (SQLite)
- [ ] Build user model: track topics the user engages with, depth per topic over time
- [ ] Implement daily/weekly briefing generation: "since last time, here's what changed"
- [ ] Wire all modules (search, ingestion, reasoning) into CLI subcommands
- [ ] Configure bun build --compile for standalone binary distribution — the brain CLI ships as a single executable, no runtime required on the target machine
- [ ] Author prompt templates:
  - [ ] `weekly-briefing` — summarize knowledge changes this week
  - [ ] `vault-health` — check for orphans, broken links, stale content
  - [ ] `daily-digest` — generate daily note with relevant context

**Ship artifacts:**
- `brain` CLI v1.0 (open-source, distributed as compiled binary via bun build --compile)
- Prompt template bundle v3

**Success criteria:**
- `brain search "topic"` returns results in <3 seconds for vault queries
- `brain brief` produces a coherent weekly briefing that references real vault changes
- Session memory persists across CLI invocations — the agent recalls what was discussed yesterday

---

### Phase 5: Observability + Web UI (Weeks 20-25)

**Goal:** Full visibility into agent behavior. The Lattice vision realized as a web interface.

**Tasks:**
- [ ] Build structured trace collection: OpenTelemetry-compatible spans for every agent run
- [ ] Build trace viewer: CLI tool to inspect, filter, and replay agent runs
- [ ] Build cost dashboard: tokens in/out, model, latency, cost per run and cumulative
- [ ] Formalize eval framework: automated regression suite using Phase 0 dataset + accumulated test cases
- [ ] Web UI — three Lattice views:
  - [ ] "What You Know" — topic map with depth indicators
  - [ ] "Conflicts" — contradictions across the vault with evidence
  - [ ] "Gaps" — what's missing per topic, with suggested sources
- [ ] Tech stack for web: Next.js + shadcn/ui (see [[ai-app-stack-2026]])

**Ship artifacts:**
- `agent-trace-viewer` npm package (CLI)
- Lattice web app v0.1
- Blog post: "What my agent actually does in 47 steps"

**Success criteria:**
- Trace viewer can display a full agent run with timings, token counts, and decision points
- Cost dashboard shows cumulative spend and cost-per-query trends
- Web UI renders all three views with real vault data
- Eval suite runs in <60 seconds and covers claim extraction, relationship classification, and search quality

---

## Dependencies

```
Phase S: Search Flow
  │
  ├── brain CLI scaffold ──────────► Phase 4 (CLI extensions build on this foundation)
  ├── multi-source search ─────────► Phase 2 (vault search integrates with external search)
  ├── LLM scoring pipeline ────────► Phase 3 (scoring patterns reused for reasoning)
  ├── vault BM25 index (A4) ───────► Phase 2 (hybrid search extends this)
  ├── REPL session pattern ────────► Phase 4 (interactive CLI sessions)
  │
  ▼
Phase 0: Thesis Test
  │
  ├── labeled dataset ──────────────► eval baseline (used by ALL subsequent phases)
  ├── claim ontology ───────────────► Phase 1 (claim extraction module design)
  │
  ▼
Phase 1: Core Loop + Claims
  │
  ├── agent loop ───────────────────► Phase 2, 3, 4 (all modules run inside it)
  ├── claim extractor ──────────────► Phase 3 (reasoning operates on claims)
  ├── SQLite schema ────────────────► Phase 2 (search indexes), Phase 3 (relationships)
  ├── observability hooks ──────────► Phase 5 (trace viewer consumes these)
  │
  ▼
Phase 2: Vault Search              Phase S ──► Phase 2 (external search informs vault search design)
  │
  ├── hybrid search ────────────────► Phase 3 (reasoning needs retrieval)
  ├── embeddings ───────────────────► Phase 3 (semantic similarity for claim matching)
  ├── prompt template pattern ──────► Phase 3, 4 (more templates follow same structure)
  │
  ▼
Phase 3: Reasoning              Phase 2 ──► Phase 4 (search powers CLI)
  │
  ├── relationship classifier ──────► Phase 4 (briefings reference conflicts)
  ├── knowledge state assessment ───► Phase 5 (web UI visualizes this)
  ├── conflict detection ───────────► Phase 5 ("Conflicts" view)
  │
  ▼
Phase 4: CLI Extensions + Memory   Phase 3 ──► Phase 5 (reasoning powers web views)
  │
  ├── session memory ───────────────► Phase 5 (web UI shows history)
  ├── briefing generation ──────────► Phase 5 (web UI adds proactive surface)
  │
  ▼
Phase 5: Observability + Web UI
  (terminal phase — consumes everything above)
```

**Critical path:** Phase S -> Phase 0 -> Phase 1 -> Phase 2 -> Phase 3. Search ships first, then the thesis test validates the reasoning premise before the ingestion pipeline is built.

**Parallelizable:** Prompt templates (Phase 2-4) can be authored independently of code modules. Blog posts can be written concurrently with development. Phase 0 (thesis test) can begin overlapping with late Phase S work once A4 is done.

---

## Public Artifact Timeline

```
Week 2   ----  Tool: brain CLI v0.1 (single-source search)
               Blog: "Building search before building ingestion"

Week 4   ----  Tool: brain CLI v0.2 (multi-source + scoring + REPL)
               Blog: "Scoring search results with LLMs — rubric-anchored prompts"

Week 5   ----  Blog: "Can an LLM reason about knowledge state?"
               Dataset: labeled claims + relationships
               Eval prompts

Week 8   ----  Package: core-agent-loop
               Package: claim-extractor
               Blog: "Building an agent loop from scratch"

Week 11  ----  Package: bm25-from-scratch
               Package: hybrid-search
               Prompt templates v1: analyze-notes, extract-claims
               Blog: "What I learned building hybrid search"

Week 15  ----  Package: relationship-classifier
               Prompt templates v2: find-conflicts, gap-analysis
               Blog: "How my agent detects what I don't know"

Week 19  ----  Tool: brain CLI v1.0
               Prompt templates v3: weekly-briefing, vault-health, daily-digest

Week 25  ----  Package: agent-trace-viewer
               App: Lattice web v0.1
               Blog: "What my agent actually does in 47 steps"
```

Total public artifacts by week 25: 6 npm packages, 1 CLI tool (versioned across phases), 1 web app, 7+ prompt templates, 7 blog posts.

---

## Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | **LLM relationship classification is unreliable.** The thesis test (Phase 0) shows <65% accuracy, meaning the core premise is shaky. | Medium | Critical | Run Phase 0 before any code investment. Test multiple models and prompt strategies. If accuracy is insufficient, pivot to simpler relationship types (related/unrelated/contradicts) or use human-in-the-loop confirmation. |
| 2 | **Claim extraction is noisy.** LLMs hallucinate claims not present in source text, or miss implicit claims, making the knowledge model unreliable. | High | High | Define strict claim ontology with inclusion/exclusion rules in Phase 0. Use source-grounded extraction (require verbatim evidence spans). Measure hallucination rate explicitly in evals. |
| 3 | **Local model quality is too low.** Ollama models underperform Claude on extraction and reasoning, making the "local-first" principle impractical for core tasks. | Medium | Medium | Design provider abstraction from Phase 1. Use Claude API for high-stakes tasks (reasoning, classification), local models for bulk tasks (embeddings, simple extraction). Track cost per query to keep API usage sustainable. |
| 4 | **Scope creep in the agent loop.** Context management, error recovery, and retry logic balloon Phase 1 beyond 3 weeks. | High | Medium | Timebox Phase 1 strictly. Ship a minimal loop: no retry logic, no context compression, no multi-turn memory. Those are Phase 4 concerns. The Phase 1 loop only needs to complete a single multi-step task. |
| 5 | **Prompt templates are too vault-specific.** Templates reference this vault's conventions (`00-inbox/`, `20-notes/`, specific tag taxonomy) and aren't useful to others. | Medium | Low | Write templates with a "vault conventions" preamble that users replace. Test each template against a fresh vault with different structure before publishing. |
| 6 | **Web UI scope explosion.** Three Lattice views (What You Know, Conflicts, Gaps) is a full product. Phase 5 becomes 10 weeks instead of 5. | High | Medium | Ship one view first ("What You Know" topic map), the other two as fast-follows. The CLI already exposes all underlying data — the web UI is visualization, not new logic. |
| 7 | **Building in public loses momentum.** Blog posts and packaging take time away from core development. The cadence slips and the public body of work stalls. | Medium | Medium | Write blog posts during the build, not after. Keep a running log per phase. Packaging should be a build step, not a separate project. If a phase runs long, ship the content artifact first and let the code catch up. |

---

*This roadmap is a living document. Phase boundaries will shift. The invariant is: eval from day one, ship every 2-3 weeks, search-first then inside-out.*
