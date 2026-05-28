---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---

# Second Brain — Architecture

> System architecture for a locally-deployed autonomous intelligence layer over an Obsidian vault. This document is the technical reference — what gets built, how it connects, and why.

---

## 1. System Diagram

```
                         ┌─────────────────────────────────────┐
                         │        LAYER 4: INTERFACE            │
                         │   CLI  ──►  TUI  ──►  Web UI        │
                         │   (progressive, not simultaneous)    │
                         └──────────────────┬──────────────────┘
                                            │ invokes
                         ┌──────────────────▼──────────────────┐
                         │        LAYER 3: SKILLS               │
                         │                                      │
                         │  ┌─────────────┐  ┌───────────────┐  │
                         │  │ App Modules │  │ Prompt         │  │
                         │  │ (code,      │  │ Templates      │  │
                         │  │  infra      │  │ (markdown,     │  │
                         │  │  access)    │  │  portable)     │  │
                         │  └──────┬──────┘  └───────────────┘  │
                         │         │  related but separate       │
                         └─────────┼───────────────────────────┘
                                   │ calls
                         ┌─────────▼───────────────────────────┐
                         │        LAYER 2: MODULES              │
                         │                                      │
                         │  Ingestion ─► Search ─► Reasoning    │
                         │       │                    │          │
                         │  Observability ◄──── Memory          │
                         │                                      │
                         └──────────────────┬──────────────────┘
                                            │ registered as tools
                         ┌──────────────────▼──────────────────┐
                         │        LAYER 1: CORE RUNTIME         │
                         │                                      │
                         │  Agent Loop ── Tool Registry          │
                         │       │              │               │
                         │  Context Mgr ── Orchestrator         │
                         │       │                              │
                         │  Observability Hooks (emit traces)   │
                         │                                      │
                         └──────────────────┬──────────────────┘
                                            │ reads / writes
                         ┌──────────────────▼──────────────────┐
                         │        LAYER 0: DATA                 │
                         │                                      │
                         │  ┌──────────┐ ┌────────┐ ┌────────┐ │
                         │  │ Obsidian │ │ SQLite │ │ Vector │ │
                         │  │ Vault    │ │ (claims│ │ Store  │ │
                         │  │ (md)     │ │  rels, │ │ (embed-│ │
                         │  │          │ │  meta) │ │  dings)│ │
                         │  └──────────┘ └────────┘ └────────┘ │
                         │                                      │
                         └─────────────────────────────────────┘
```

**Data flow:** Content enters via Ingestion (L2) which extracts claims and writes to SQLite + vector store (L0). The agent loop (L1) orchestrates modules (L2) via the tool registry. Skills (L3) are either code modules with infra access OR portable markdown prompts — never a single artifact trying to be both. Interface (L4) is a thin shell that calls into the runtime.

---

## 2. Layer-by-Layer Breakdown

### Layer 0: DATA

**Purpose:** The storage substrate — everything reads from and writes to this layer.

**Components:**

| Component | Role | Technology |
|---|---|---|
| Obsidian vault | Raw knowledge (markdown files) | Filesystem (`~/my-obsidian/`) |
| SQLite | Structured claims, relationships, cluster state, ingestion logs, revision history | SQLite via bun:sqlite + Drizzle ORM |
| Vector store | Embeddings for semantic search | SQLite-vec (start), pgvector via Supabase (later) |

**Key decisions:**
- SQLite-first. Zero infrastructure. Single file. Portable. Graduate to Supabase only if multi-device or auth is needed.
- Vault stays read-mostly. The system reads markdown; structured data lives in SQLite. The vault is not a database.
- Append-only revision history. Cluster state changes are logged, never overwritten.

**Dependencies:** None. This is the foundation.

---

### Layer 1: CORE RUNTIME

**Purpose:** The agentic engine — takes a goal, selects tools, executes steps, manages context, knows when to stop.

**Components:**

| Component | Role |
|---|---|
| Agent loop | Message cycle: user -> LLM -> tool call -> result -> LLM -> ... -> done |
| Tool registry | Declares available tools, validates inputs, routes execution to L2 modules |
| Context manager | Tracks token budget, compresses history at threshold, manages what the LLM sees |
| Orchestrator | Routes high-level intents to the right module/skill combination |
| Observability hooks | Emits traces, timings, token counts, costs at every step — not optional, wired from day one |

**Key decisions:**
- Single-agent, not multi-agent. Per [[effective-agent-design]], single-agent matches or beats multi-agent at equal token budgets. Complexity cost of multi-agent is not justified here.
- Model-agnostic. Provider abstraction supports Ollama (local, fast, cheap) and Claude/OpenAI (API, heavy reasoning). The orchestrator picks based on task.
- Stateless between runs. All persistent state lives in L0. The runtime is a pure function: (goal, context, tools) -> (actions, outputs).

**Dependencies:** Layer 0 (reads/writes data).

---

### Layer 2: MODULES

**Purpose:** Discrete capabilities the agent invokes as tools. Each module is a self-contained package with a clear interface.

#### 2a. Ingestion

Markdown file (or URL) -> extract atomic claims -> classify relationships to existing claims -> propagate implications -> store.

- Structured output: 3-7 claims per source with evidence type, assertion strength, topic tags
- Relationship classification against top 5-10 similar existing claims
- Propagation: updates downstream confidence, flags cluster instability
- Eval hook: measure extraction precision against the test set from day one

#### 2b. Search

Two search modes: **internal** (vault search) and **external** (web/API search). Both feed into the same scoring and fusion pipeline.

**Internal search:** keyword (BM25) + semantic (vector) + structured (SQLite queries).
- BM25 over vault markdown content (hand-rolled, educational, shareable)
- Semantic search over claim embeddings
- Result fusion and reranking
- Graph traversal: follow relationship edges from search hits to connected claims

**External search (agentic):** multi-source fan-out with query decomposition.
- Query decomposition: a lightweight planner call (small/fast model via OpenRouter) splits the user query into 3-5 targeted sub-questions before retrieval
- Multi-source fan-out: parallel retrieval across configured sources (Brave Web, GitHub, Twitter/X, HuggingFace, others)
- Source abstraction: common `SearchSource` interface — adding a source means implementing one interface
- Vault cross-reference: compare external results against vault content to flag novelty (NEW / IN VAULT / PARTIAL)
- LLM relevance scoring: batch score results with rubric-anchored prompts
- Trace logging: every score + reasoning logged for eval dataset construction

See [[2026-04-18-search-flow-chunked-v1]] for the chunked build plan and [[2026-04-18-agentic-search-flow]] for the full search funnel design.

#### 2c. Reasoning

The core differentiator. Operates on the [[11-knowledge-model|knowledge model]] to reason about knowledge *state*, not just content.

- Relationship classification: supports, contradicts, extends, qualifies, supersedes
- Conflict detection with subtypes: direct refutation, scope difference, different interpretation
- Confidence scoring and propagation across the graph
- Cluster property computation: depth, diversity, conflict level, consensus, recency, evidence quality, stability

#### 2d. Memory

Cross-session persistence. What was asked, what was found, what changed.

- Session logs: queries, results, actions taken
- User model: tracks depth of engagement per topic cluster
- Proactive surfacing: "Since last week, 3 new articles contradicted your view on X"

#### 2e. Observability

Not a Phase 5 bolt-on. Wired from the first agent loop invocation.

- Trace collection: every LLM call, tool invocation, decision point
- Cost tracking: tokens in/out, model used, latency per step
- Eval hooks: claim extraction accuracy, relationship classification quality
- Export: OpenTelemetry-compatible format, Langfuse-compatible spans

**Dependencies:** Layer 1 (registered as tools), Layer 0 (reads/writes data).

---

### Layer 3: SKILLS

**Purpose:** Intelligence that can be invoked by the agent or used standalone — but NOT as a single artifact trying to serve both contexts.

The [[02-steelman-and-reframe|steelman critique]] was right: "dual-surface" as originally conceived is a trap. Clean separation:

| Type | Description | Has infra access | Distribution |
|---|---|---|---|
| App modules | Code packages called by the agent | Yes (SQLite, vectors, graph) | Internal to the app |
| Prompt templates | Markdown files for any coding agent | No (filesystem only) | GitHub, skill registries |

A prompt template may be *inspired by* an app module. It is not the same artifact.

**Skill categories:** Knowledge (analyze-notes, extract-claims, find-conflicts), Research (deep-research, gap-analysis), Writing (draft-from-notes, thread-writer), System (vault-health, daily-digest, tag-auditor).

**Dependencies:** App modules depend on Layer 2. Prompt templates are self-contained.

---

### Layer 4: INTERFACE

**Purpose:** How the user interacts with the system. Built last — the layers underneath must work first.

**Progression:**
1. **CLI** — `brain search "..."`, `brain ingest ./notes/`, `brain brief`. This is the primary interface for months.
2. **TUI** — Rich terminal output (Ink or similar). Only if CLI proves limiting.
3. **Web UI** — The [[04-product-vision|Lattice vision]] with three views: What You Know, Conflicts, Gaps. Only when the data model is proven.

**Key decision:** The CLI is a reference implementation and learning artifact, not a general-purpose product. It works for this vault, this structure, this user. Extracted components are what get generalized.

**Dependencies:** All layers below.

---

## 3. Knowledge Model

Three levels. Each level adds structure and enables reasoning the level below cannot.

```
Level 3: Clusters    (emergent, computed by Loop 3)
  |  grouped by topic embedding
Level 2: Relationships  (classified at ingestion, updated by reasoning loops)
  |  labeled edges between claims
Level 1: Claims      (atomic assertions extracted from sources)
  |  extracted at ingestion
```

### Level 1: Claims

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Unique identifier |
| `source_id` | string | Origin document/URL |
| `text` | string | The assertion as a clear, testable proposition |
| `evidence_type` | enum | primary_research, analysis, opinion, aggregation |
| `assertion_strength` | enum | strong, moderate, hedged, speculative |
| `topic_tags` | string[] | Auto-assigned topics |
| `embedding` | vector | For semantic search |
| `scope` | string | Domain/context qualifier |
| `created_at` | timestamp | Ingestion time |

**Critical constraint:** A claim must be a testable proposition, not a summary or highlight. "Mastra has 23k stars" is a claim. "Mastra is interesting" is not. The ontology must be defined with 20+ real examples from this vault before any code is written.

### Level 2: Relationships

| Field | Type | Purpose |
|---|---|---|
| `source_claim_id` | string | The newer claim |
| `target_claim_id` | string | The existing claim |
| `type` | enum | supports, contradicts, extends, qualifies, supersedes |
| `confidence` | float (0-1) | System confidence in this classification |
| `reasoning` | string | One-sentence justification |
| `conflict_subtype` | enum (nullable) | direct_refutation, scope_difference, different_interpretation |
| `created_at` | timestamp | When classified |
| `last_evaluated` | timestamp | When last re-evaluated |

### Level 3: Clusters

Computed, not manually created. Properties are recomputed by Loop 3 (Knowledge State Assessment).

| Property | What it measures |
|---|---|
| Depth | Claim count |
| Diversity | Distinct sources; penalized for same-type or shared citations |
| Conflict level | Proportion of contradicts/qualifies edges (0 = consensus, 1 = contested) |
| Consensus direction | Majority position by evidence weight |
| Recency | Timestamp distribution; flagged if median age > threshold |
| Evidence quality | % primary research vs. analysis vs. opinion vs. aggregation |
| Stability | Did consensus direction flip since last assessment? |

These properties enable the [[11-knowledge-model|epistemic spectrum]]: Empty -> Thin -> Shallow -> One-sided -> Contested -> Nuanced -> Deep.

---

## 4. Reasoning Loops

Six loops. Each generates output, evaluates it against the knowledge model, and modifies behavior. If there is no self-evaluation and no behavior change, it is a pipeline step, not a loop.

| # | Loop | Trigger | Purpose | MVP Priority |
|---|---|---|---|---|
| 1 | Ingestion + Propagation | New content enters | Extract claims, classify relationships, propagate implications across graph | **P0 — the thesis lives here** |
| 2 | Query Self-Evaluation | User queries | Draft answer, self-critique (coverage, conflicts, evidence quality, recency), refine | P1 — comes with CLI |
| 3 | Knowledge State Assessment | Every N ingestions or after inactivity | Cluster, assess state, diff against prior, prioritize, generate briefing | P1 — powers briefings |
| 4 | Belief Revision | Strong conflict detected | Weigh evidence, form judgment, propose model revision to user, execute with consent | P2 — needs volume |
| 5 | Structural Gap Reasoning | Periodic or on-demand | Identify gaps, cross-reference with existing source mentions, assess impact, generate questions | P1 — lightweight version |
| 6 | Epistemic Habit Analysis | 20+ entries accumulated | Analyze source diet, perspective balance, confirmation patterns, advise | P2 — needs volume |

**MVP scope:** Loop 1 is the minimum viable agentic system. If ingestion with propagation works — self-evaluating classification, graph-level reasoning, proactive conflict surfacing — the thesis is proven. Loops 2, 3, and 5 (lightweight) follow in the CLI phase. Loops 4 and 6 require knowledge volume and are post-MVP.

For full loop specifications, see [[09-agentic-loops]].

---

## 5. Key Architectural Decisions

1. **Single-agent, not multi-agent.** Multi-agent adds coordination overhead without proportional gain at this scale. Single-agent with good tool selection and context management is the right architecture for a personal knowledge system. Revisit only if task parallelism becomes a bottleneck.

2. **Local-first.** Data stays on-machine. SQLite + filesystem. No cloud dependency for core functionality. API calls to LLM providers are the only network dependency, and even those can be replaced with Ollama.

3. **SQLite-first.** Zero-infrastructure persistence. Claims, relationships, cluster state, and revision history in one portable file. Graduate to Supabase only when multi-device sync or auth is actually needed — not before.

4. **Eval from day one.** The 20-note test set (manually labeled claims and relationships) exists before the first module is built. Every module runs against it. If claim extraction hallucinates or the relationship classifier defaults to "supports" 80% of the time, we know immediately. Eval is not Phase 5.

5. **Separate app modules from prompt templates.** The steelman was right. An app module (code, infra access, structured I/O) and a prompt template (markdown, filesystem only, natural language I/O) serve different contexts. Trying to make one artifact work in both creates lowest-common-denominator skills. Related but separate.

6. **Personal tool first, extract shareable pieces.** The app is optimized for this vault, this tag taxonomy, this folder structure. It does not need onboarding or configuration. Shareable artifacts are components extracted from it — `claim-extractor`, `bm25-from-scratch`, prompt template bundles — not the app itself.

7. **Model-agnostic with intent-based routing.** Ollama for fast/cheap tasks (embedding, simple classification). Claude/OpenAI for heavy reasoning (relationship classification, belief revision). The orchestrator picks based on task requirements, not user configuration.

8. **Observability is infrastructure, not a feature.** Every LLM call, tool invocation, and decision point emits a trace. Cost tracking from the first run. This is how you debug an agent — you read its traces. Without this, development is flying blind.

9. **Stateless runtime, stateful data.** The agent loop holds no state between runs. All persistence is in Layer 0 (SQLite + vault + vectors). This makes the system restartable, debuggable, and testable — any run can be replayed from its inputs.

10. **Progressive interface.** CLI first. TUI only if the CLI proves limiting. Web UI only when the data model is proven. Do not build UI to compensate for an unproven backend.

11. **Query decomposition before fan-out.** External search decomposes the user query into sub-questions before retrieving from sources. This is the consensus architecture behind Perplexity, gpt-researcher, and STORM. A single raw query produces breadth; decomposed sub-queries produce depth. The planner call uses a small/fast model via OpenRouter — cost is negligible (~$0.001), latency is ~1 second.

---

## 6. Open Questions

These are genuinely undecided. Not deferred — open.

1. ~~**TypeScript or Python?**~~ **DECIDED: TypeScript.** Bun provides native TS execution without a compile step. One language across CLI, TUI, web, and agent runtime. Python's ML/NLP library advantage is less relevant given the LLM-first architecture.

2. ~~**Agent framework or hand-rolled?**~~ **DECIDED: Vercel AI SDK + hand-rolled loop.** Vercel AI SDK provides the provider abstraction and streaming primitives. The agent loop itself is hand-rolled — full control, educational value, and a shareable artifact. Mastra evaluated and rejected: too opinionated, too much magic, not enough control over the loop internals.

3. **Embedding model for local use.** Which Ollama-compatible model for claim embeddings? Tradeoff is embedding quality vs. speed vs. memory. Needs benchmarking against the test set.

4. **Claim extraction accuracy floor.** What precision/recall threshold makes the system useful vs. noise? The Week 0 thesis test should answer this empirically. If extraction quality is below ~70% precision, the entire architecture above it produces garbage.

5. **Cluster algorithm.** K-means, DBSCAN, or hierarchical? Clusters need to be stable enough that adding one claim does not reorganize the entire topology, but flexible enough that new topics emerge naturally.

6. **Confidence calibration.** Relationship confidence scores (0-1) are currently LLM-assigned. Are they calibrated? Does 0.8 actually mean "right 80% of the time"? If not, every downstream computation that uses confidence is unreliable. May need a calibration step or learned thresholds.

7. **Propagation depth.** When a new claim contradicts claim X, and claim X supports claims Y and Z, how far does re-evaluation propagate? Unbounded propagation is expensive. Fixed-depth propagation may miss important implications.

8. **Vault write-back.** Should the system ever modify vault markdown files (e.g., add metadata frontmatter, insert backlinks)? Current assumption is read-mostly, but some skills (daily-digest, vault-health) imply writes.

9. **Concurrency model.** Can multiple ingestions run in parallel? SQLite has write-locking constraints — `bun:sqlite` is synchronous with the same single-writer limitation as `better-sqlite3`. If ingestion is slow (multiple LLM calls per source), serial processing could be a bottleneck. Runtime choice does not change this constraint.

10. **Skill registry format.** How are prompt templates discovered and versioned? A Git repo of markdown files? A manifest file? Integration with Wibey's skill registry? This affects distribution but not core architecture.

11. ~~**OpenRouter model selection for search stages.**~~ **DECIDED: tiered model strategy.** Small/fast models (via OpenRouter) for query decomposition and relevance scoring — cost is negligible, latency ~1s. Capable models for synthesis and comparison where reasoning quality matters. Documented in steelman session. Specific model IDs determined empirically per stage.

---

## 7. Search Flow Architecture

Search is the first module being built. Outside-in strategy: start with the user-facing capability that exercises the most components (LLM calls, source abstraction, scoring, vault integration), then work inward toward ingestion and reasoning.

The build plan is chunked into five sequential pieces. Each chunk is independently shippable and testable.

### Build Sequence (A1 → A5)

| Chunk | Scope | What ships |
|---|---|---|
| **A1** | Query decomposition | User query → 3-5 sub-questions via small/fast model. Eval: sub-question quality against hand-labeled set. |
| **A2** | Source fan-out + retrieval | Sub-questions → parallel retrieval across Brave Web + one additional source. `SearchSource` interface established. |
| **A3** | Scoring + fusion | Raw results → relevance-scored, deduplicated, ranked. Rubric-anchored LLM scoring with trace logging. |
| **A4** | Vault cross-reference | Scored results → compared against vault content. Novelty flags: NEW / IN VAULT / PARTIAL. |
| **A5** | Synthesis + CLI surface | Fused results → structured answer with citations. Wired into `brain search "..."` CLI command. |

### Build Sequence Diagram

```
A1: Decomposition ──► A2: Fan-out ──► A3: Scoring ──► A4: Vault XRef ──► A5: Synthesis
     (planner)         (retrieval)      (fusion)        (novelty)          (answer + CLI)
         │                  │               │                │                   │
         ▼                  ▼               ▼                ▼                   ▼
    eval: sub-q        eval: recall    eval: precision   eval: novelty     eval: end-to-end
    quality            + latency       + ranking         accuracy          answer quality
```

Each chunk has its own eval hook. No chunk ships without measurable quality on a hand-labeled test set.

### References

- [[2026-04-18-agentic-search-flow]] — full search funnel design (April 18 session)
- [[2026-04-18-search-flow-chunked-v1]] — chunked build plan with acceptance criteria (April 18-19 sessions)

---

*This is the architectural reference for the Second Brain project. For the strategic framing, see [[00-master-plan]]. For the critical review that shaped these decisions, see [[02-steelman-and-reframe]]. For the knowledge model deep-dive, see [[11-knowledge-model]]. For reasoning loop specifications, see [[09-agentic-loops]].*
