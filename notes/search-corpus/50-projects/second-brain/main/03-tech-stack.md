---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---
# Second Brain — Tech Stack

> Build manifest for the Second Brain project. For each layer, this document presents options considered, a recommended pick, and a confidence level. Companion to [[50-projects/second-brain/main/02-architecture]].

**Confidence scale:**
- **Locked** — decided, not revisiting unless something breaks.
- **Leaning** — strong preference, open to new evidence.
- **Open** — genuinely undecided, needs prototyping or benchmarking.

---

## 1. Language

The single highest-leverage decision. Determines framework availability, package ecosystem, and cognitive overhead.

| Option | Pros | Cons |
|---|---|---|
| **TypeScript** | One language across CLI, TUI, web, agent runtime. Strong type system. Existing prototype (`agentic-loop-v1`) is TS. | ML/NLP ecosystem thinner. Vector math less ergonomic. Fewer LLM framework options. |
| **Python** | Best-in-class ML/NLP libraries (numpy, scikit, spaCy). Every LLM framework exists in Python first. | Web UI story is weak (need a separate frontend language anyway). Two runtimes to manage. Packaging/distribution less clean. |
| **Hybrid (TS primary + Python services)** | Best of both — TS for app/CLI/web, Python for ML-heavy modules behind a thin API. | Operational complexity. IPC overhead. Two dependency trees. Overkill for a solo developer. |

**Recommendation: TypeScript (monoglot).**
Rationale: One language, one build system, one mental model. The ML/NLP gap is shrinking — `ml-distance` handles BM25, `@xenova/transformers` handles local embeddings, and the heavy reasoning is delegated to LLM APIs anyway. If a specific Python library proves irreplaceable (e.g., for clustering), wrap it as a subprocess — do not adopt a full hybrid architecture for one dependency.

**Confidence: Leaning.** The prototype is TS and working. Would switch only if BM25 or embedding quality proves unacceptable with JS-native libraries.

---

## 2. LLM Providers

The system needs two tiers: fast/cheap (embeddings, simple classification) and heavy reasoning (claim extraction, relationship classification, belief revision).

| Option                     | Pros                                                                       | Cons                                                            |
| -------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Ollama (local)**         | Zero cost. No network. Full privacy. Good for embeddings and simple tasks. | Slower for reasoning. Model quality ceiling. RAM-hungry.        |
| **Claude API (Anthropic)** | Best reasoning quality. Extended thinking. Strong structured output.       | Cost per call. Network dependency. Rate limits.                 |
| **OpenAI API**             | Largest model selection. Good function calling.                            | Cost. Less differentiated now that Claude matches on reasoning. |
| **OpenRouter** | Single API gateway to 100+ models. Free-tier models available. Model switching by changing a string, not code. Pay-per-token for premium models. | Additional abstraction layer. Dependent on OpenRouter uptime. |

**Recommendation: OpenRouter as the API gateway, with Ollama for local tasks.**
Use OpenRouter as the unified API endpoint for all cloud LLM calls. During development and testing, use free-tier models available through OpenRouter (e.g., free versions of Llama, Mistral, Gemma) — lower quality but zero cost, sufficient for validating flow and plumbing. For production quality, swap to paid models (Claude Sonnet/Opus, GPT-4o) by changing the model ID string — no code changes required. Use Ollama locally for embeddings and lightweight classification where network latency is unacceptable.

The Vercel AI SDK supports OpenRouter as a provider via the OpenAI-compatible endpoint. This gives us: one API key, access to all models, free testing, and a clean upgrade path to production quality.

**Model routing strategy for search flow:**
- Query decomposition (A2): small/fast model (free tier)
- Relevance scoring (A3): small/fast model with rubric-anchored prompts (free tier for testing)
- Synthesis/comparison (A5): capable model (paid tier when quality matters)
- Embeddings: Ollama local (nomic-embed-text)

**Confidence: Leaning.** OpenRouter + Ollama gives the right flexibility. Validate that Vercel AI SDK + OpenRouter integration is smooth in A1.

---

## 3. Agent Framework

How the [[50-projects/second-brain/main/02-architecture#Layer 1 CORE RUNTIME|agent loop]] is implemented.

| Option | Pros | Cons |
|---|---|---|
| **Hand-rolled** | Full control. Educational (shareable artifact). No dependency risk. Exactly what you need, nothing you don't. | Slower to start. Must implement tool calling, context management, retry logic from scratch. |
| **Vercel AI SDK** | Mature, well-typed TS. `generateText` / `streamText` with tool calling built in. Active maintenance. Lightweight — a library, not a framework. | Opinionated about streaming. Some abstractions may fight custom context management. |
| **LlamaIndex.TS** | Purpose-built for RAG. Best retrieval accuracy (~92% vs LangChain's ~85%). Native markdown loaders, multiple chunking strategies, broadest vector store integrations. TS-native (not a port). | RAG-focused — less flexible for non-RAG LLM tasks. Smaller community than LangChain. |
| **Mastra** | Agent-native framework. Built-in tool registry, memory, evals. TS-first. Growing fast (23k stars). Unified RAG + agents + workflows. Wraps Vercel AI SDK (portable LLM layer). | Young project (1.0 Jan 2026). API surface still shifting. Risk of coupling to their abstractions. |
| **LangChain (JS)** | Largest ecosystem. Many integrations. LangGraph for stateful agent workflows. | Notorious abstraction complexity. JS lags Python. Over-engineered for a single-agent system. Deepest lock-in of all options. |

**Recommendation: Vercel AI SDK as the LLM communication layer + hand-rolled agent loop + LlamaIndex.TS as a utility library for document loading/chunking.**

Rationale: The Vercel AI SDK handles the tedious parts — provider-agnostic API calls, streaming, tool call parsing, structured output via Zod schemas — without imposing an agent architecture. The agent loop itself (goal decomposition, tool selection, context management, termination logic) is hand-rolled. This gives framework-quality LLM interaction with full architectural control. It is also the most educational split: the interesting engineering is in the loop, not in HTTP calls to Claude.

**LlamaIndex.TS** is used surgically — import `MarkdownReader` and `SentenceSplitter` for document ingestion when Phase B (ingestion MVP) begins. Do NOT adopt their `VectorStoreIndex`, `QueryEngine`, or agent abstractions. The vector store and retrieval layer remain hand-rolled. LlamaIndex earns its keep by handling the genuinely hard part of markdown parsing (frontmatter, wikilinks, headings-based chunking, code blocks) without imposing a framework. The underlying data (embeddings in sqlite-vec) is fully portable — LlamaIndex does not own the storage layer.

Do not use Mastra yet. It solves problems (multi-agent orchestration, workflow graphs) that are premature for this project. Re-evaluate when the agentic claim extraction phase (Phase B, chunks B2-B4) demands stateful graph orchestration. Mastra's Vercel AI SDK foundation means the LLM call layer is portable if we migrate later.

Do not use LangChain. Deepest lock-in, heaviest abstraction layer, JS version lags Python.

**Lock-in assessment:** This is a two-way door. Embeddings in the vector store survive any framework swap. Prompts are text. Drizzle schemas are ours. The only non-portable artifacts are chain/workflow definitions and tool registries — application logic that would be rewritten anyway as the problem understanding matures. Estimated migration cost between frameworks: 1-2 weeks. See [[2026-04-19-sdk-audit]] for the full audit.

**Confidence: Leaning.** Hand-rolled-on-Vercel-AI-SDK is the default. LlamaIndex.TS for ingestion utilities in Phase B. Pure hand-rolled (raw fetch to APIs) is the fallback if the SDK fights the architecture.

**Revisit triggers:**
1. Hand-building retrieval primitives that LlamaIndex already solved (reranking, hybrid search, metadata filtering)
2. Agentic claim extraction needs stateful graph orchestration the hand-rolled loop can't cleanly express
3. Mastra hits 2.0+ and API stabilizes

---

## 4. Database

Per [[50-projects/second-brain/main/02-architecture#Layer 0 DATA|Layer 0]], three storage concerns: raw markdown (vault), structured data (claims, relationships, metadata), and embeddings (vector search).

| Option | Pros | Cons |
|---|---|---|
| **SQLite + sqlite-vec** | Zero infrastructure. Single file. Portable. `bun:sqlite` is built-in (no install, no native compilation). `sqlite-vec` adds vector search in-process. | sqlite-vec is young. No built-in HNSW (brute-force cosine). Write-locking limits concurrency. `sqlite-vec` + `bun:sqlite` extension loading needs validation. |
| **SQLite + FAISS** | SQLite for structured, FAISS for vectors. FAISS is battle-tested, fast ANN search. | FAISS is a C++ library with Python bindings. JS bindings exist but are second-class. Two storage systems to sync. |
| **Supabase (pgvector)** | Managed Postgres. pgvector is mature. Real concurrency. Scales to multi-device. | Cloud dependency violates local-first. Latency. Overkill for single-user. Monthly cost. |

**Recommendation: SQLite (`bun:sqlite`) + `sqlite-vec` for everything.**
Rationale: Local-first means local storage. SQLite handles structured data and vector search in one process, one file. `bun:sqlite` is Bun's built-in SQLite driver — no dependency to install, faster than `better-sqlite3`, and zero native compilation headaches. It supports `loadExtension()`, which is the hook for `sqlite-vec` when vector search enters scope. The MVP uses text similarity (BM25 + fusion), not embeddings, so `sqlite-vec` compatibility with `bun:sqlite` should be validated in Phase 2 — not blocking.

`sqlite-vec` supports cosine similarity over float32 vectors — sufficient for a corpus of thousands of claims (not millions). Brute-force search over <50k vectors is fast enough. If vector search latency becomes a problem at scale, migrate to pgvector then — not before.

ORM: Use **Drizzle** for schema management and typed queries. It is thin, SQL-transparent, does not hide what is happening, and supports the `bun:sqlite` driver natively.

**Confidence: Locked** (SQLite). **Leaning** (`bun:sqlite` — built-in and fast, but `sqlite-vec` extension loading via `loadExtension()` needs Phase 2 validation).

---

## 5. Search

Three search strategies feeding a fusion layer. Per [[50-projects/second-brain/main/02-architecture#2b Search|the Search module spec]].

| Component | Options | Recommendation |
|---|---|---|
| **BM25 (keyword)** | `orama` (full-text search, TS-native, fast), hand-rolled (educational), `minisearch` | **Hand-rolled BM25.** Educational, shareable, and the algorithm is simple enough (~200 lines). Publish as a standalone package. Fall back to `orama` if performance is inadequate. |
| **Vector search** | `sqlite-vec` (in-process), FAISS (external), Pinecone (cloud) | **sqlite-vec.** Consistent with the database decision. In-process, no network. |
| **Fusion / reranking** | Reciprocal Rank Fusion (RRF), learned weights, Cohere reranker API | **RRF to start.** Simple, well-understood, no training data needed. Weights: 0.5 BM25 + 0.5 vector as baseline, tune empirically against the eval set. |

**Confidence: Leaning** (BM25 hand-rolled). **Locked** (RRF for fusion — anything fancier is premature).

---

## 6. CLI Framework

The primary interface for the first several months. Per [[50-projects/second-brain/main/02-architecture#Layer 4 INTERFACE|Layer 4]], CLI first.

| Option | Pros | Cons |
|---|---|---|
| **Commander.js** | Simple, well-documented, zero magic. The standard. | No built-in rich output. Basic help formatting. |
| **oclif** | Plugin architecture. Auto-generated help. Testing utilities. | Heavy for a personal tool. Opinionated project structure. |
| **Ink (React for CLI)** | Component model for rich TUI output. Flexbox layout in the terminal. Natural upgrade path to TUI phase. | React mental model in the terminal is unusual. Heavier dependency. |

**Recommendation: Commander.js + chalk + ora for the CLI phase.**
Rationale: The CLI needs to do three things well — parse commands, format output, show progress. Commander handles parsing, chalk handles color, ora handles spinners. This is ~100 lines of scaffolding. When the TUI phase arrives, evaluate Ink then — do not pay for its complexity in the CLI phase.

Commands: `brain search "..."`, `brain ingest <path>`, `brain brief`, `brain status`, `brain trace <run-id>`.

**Distribution:** The CLI is compiled into a standalone binary via `bun build --compile` — no runtime needed on the target machine. The user downloads a single executable and runs `brain ingest <file>` directly. This is a significantly cleaner install story than requiring Node.js (or even Bun) on the target machine. For development, clone the repo and `bun install` as usual.

**Confidence: Locked.** This is commodity tooling. Do not overthink it.

---

## 7. Web UI (Future)

Not built until the data model and reasoning loops are proven. Included here for directional alignment only.

| Option | Pros | Cons |
|---|---|---|
| **Next.js + shadcn/ui** | TS end-to-end. Server components for data-heavy views. shadcn gives unstyled, composable primitives. | Framework overhead for what may be a simple dashboard. |
| **Astro + Svelte** | Lightweight. Fast. Good for content-heavy, low-interactivity pages. | Svelte is a second framework to learn. Smaller ecosystem. |
| **Electron + React** | Desktop app. Full filesystem access. Offline-first. | Electron is heavy. Distribution complexity. |

**Recommendation: Next.js + shadcn/ui when the time comes.**
Rationale: TS monoglot continues. Server components can query SQLite directly (local deployment). shadcn avoids the "everything looks like Material UI" problem. The three views from the product vision (What You Know, Conflicts, Gaps) are data-dense and benefit from server-side rendering.

**Confidence: Open.** This is months away. The recommendation is directional, not committed.

---

## 8. Testing

Three concerns: unit tests, integration tests, and LLM output evaluation.

| Concern | Options | Recommendation |
|---|---|---|
| **Unit / Integration** | Vitest, Jest, Node test runner | **Vitest.** Fast, ESM-native, good DX. Compatible with the TS toolchain. |
| **LLM Evals** | Promptfoo, Braintrust, hand-rolled eval harness | **Promptfoo.** Open-source, YAML-driven, supports custom assertions. Run evals as CI checks against the 20-note test set. Supplement with hand-rolled metrics for domain-specific measures (claim precision, relationship accuracy). |
| **Snapshot / golden tests** | Vitest snapshots, custom diff tooling | **Vitest inline snapshots** for structured output shapes. Custom diff for claim extraction regression testing. |

**Key principle:** The 20-note eval set (per [[50-projects/second-brain/main/02-architecture#5 Key Architectural Decisions|decision 4]]) is the ground truth. Every module runs against it. Eval is infrastructure, not a phase.

**Confidence: Locked** (Vitest). **Leaning** (Promptfoo — evaluate against Braintrust if prompt versioning becomes a need).

---

## 9. Observability

Per [[50-projects/second-brain/main/02-architecture#2e Observability|the Observability module]], this is wired from the first agent loop invocation.

| Concern | Options | Recommendation |
|---|---|---|
| **Trace format** | OpenTelemetry spans, custom JSON traces, Langfuse spans | **Custom JSON traces with OpenTelemetry-compatible structure.** Full OTel SDK is overkill for a local app. Use the span model (trace_id, span_id, parent_span_id, attributes) but write to SQLite, not an OTel collector. Export to OTel format if external tooling is needed later. |
| **Logging** | pino, winston, console.log | **pino.** Structured JSON logging. Fast. Pairs well with trace context. |
| **Cost tracking** | Manual token counting, LLM provider usage APIs, custom tracker | **Custom tracker in SQLite.** Log model, tokens_in, tokens_out, latency_ms, estimated_cost per LLM call. Aggregate by day/week/module. This is ~50 lines of code and gives full visibility. |
| **Trace viewer** | Langfuse (hosted), Langsmith, custom CLI viewer | **Custom CLI viewer (`brain trace <run-id>`) for MVP.** Prints the trace tree to terminal with timings and costs. Evaluate Langfuse (self-hosted) when traces exceed what terminal output can convey. |

**Confidence: Locked** (custom traces in SQLite + pino). **Leaning** (Langfuse for later visualization).

---

## 10. Stack Summary

| Layer | Technology | Status |
|---|---|---|
| Language | TypeScript (monoglot) | Leaning |
| Runtime | Bun | Leaning |
| LLM — local | Ollama (nomic-embed-text, llama3) | Locked |
| LLM — API | OpenRouter (free models for testing, Claude/GPT for production) | Leaning |
| LLM — gateway | OpenRouter | Leaning |
| LLM abstraction | Vercel AI SDK | Leaning |
| Agent loop | Hand-rolled on Vercel AI SDK | Leaning |
| Document loading (Phase B) | LlamaIndex.TS (utility only) | Leaning |
| Structured extraction (Phase B) | Instructor | Open |
| Database | SQLite via bun:sqlite + Drizzle | Leaning |
| Vector store | sqlite-vec | Leaning |
| BM25 search | Hand-rolled | Leaning |
| Search fusion | Reciprocal Rank Fusion | Locked |
| CLI framework | Commander.js + chalk + ora | Locked |
| Web UI (future) | Next.js + shadcn/ui | Open |
| Testing | Vitest + Promptfoo | Locked / Leaning |
| Logging | pino | Locked |
| Traces | Custom JSON spans in SQLite | Locked |
| Cost tracking | Custom tracker in SQLite | Locked |
| Package manager | bun (built-in) | Locked |
| Build | Bun (native TS execution, no transpile step) | Leaning |
| Distribution | bun build --compile (standalone executable) | Leaning |

---

## 11. What This Stack Optimizes For

1. **Velocity.** One language, one runtime, minimal infrastructure. A solo developer should be writing agent logic, not configuring build pipelines.
2. **Debuggability.** SQLite is inspectable with any DB browser. JSON traces are readable. No opaque framework state.
3. **Portability.** The CLI ships as a standalone compiled binary via `bun build --compile` — no runtime dependency on the target machine. Download the binary, run `brain ingest`. For developers, clone the repo and `bun install`.
4. **Graduatability.** SQLite -> Postgres, CLI -> Web, Ollama -> Claude — each layer can be upgraded independently without rewriting the layer above it.

---

*For the system architecture these choices implement, see [[50-projects/second-brain/main/02-architecture]]. For the strategic framing, see [[00-master-plan]]. For the critical review, see [[02-steelman-and-reframe]].*
