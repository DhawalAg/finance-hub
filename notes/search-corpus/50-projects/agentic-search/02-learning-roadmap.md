---
type: note
project: agentic-search
tags:
  - type/reference
  - topic/search
  - topic/career
  - topic/agents
---

# Agentic Search — Concept Map & Learning Roadmap

Based on Tosh's talk (Sr. Engineering Manager AI/ML, Meta) on the evolution from classical IR to agentic search systems.

---

## Concept Map

### Classical IR
- [[BM25]] / [[20-notes/ai/ml-algos/TF-IDF]] — deterministic, extremely fast scoring
- **Lexical pipelines** — sparse representations, token-level matching
- **Sparse interpretations** — every token treated as independent statistical event
- **Vocabulary mismatch** — systems break when user phrasing diverges from indexed terms
- **Lexical brittleness** — natural outcome of stateless, keyword-only matching
- *Bridges to:* [[Hybrid relevance scoring|Hybrid scoring]] (BM25 still serves as a transparent, predictable backend for agents); [[Composable tools]] (keyword search as an atomic primitive)

### Vector / RAG Era
- **Embeddings** — dense representations capturing semantic similarity
- **Chunking heuristics** — splitting documents for vector indexing; introduces chunk collapse risk
- [[20-notes/ai/ml-algos/knn|KNN search]] — k-nearest-neighbor retrieval; latency challenges at scale
- **Semantic similarity** — moving beyond exact-match to meaning-level retrieval
- **Vector drift** — embedding quality degrades over time as data/models shift
- **Stateless generation step** — RAG still lacks session memory or multi-turn reasoning
- *Bridges to:* [[Intent-conditioned embeddings|query embeddings conditioned on intent]] (intent-specific feature vectors improve on generic document embeddings); **Hybrid lexical + vector backends** (production systems combine both)

### Agentic Search
- [[20-notes/ai/search/stateful-reasoning|stateful-reasoning]] — retrieval becomes part of a control loop, not an endpoint
- [[Multi-turn reasoning]] — iterative reformulation trajectories across tool calls
- [[00-inbox/agentic-search-control-loop]] — the agent continuously refines queries based on intermediate results
- **Tool calls** — atomic operations the agent invokes (keyword search, semantic search, etc.)
- [[Session memory]] — session-local state that survives across iterations
- **Reformulation trajectory** — tracked history of query rewrites and their outcomes
- **Confidence curves** — per-iteration confidence tracking to decide when to stop
- **Diversity metrics** — measuring whether the agent explored varied retrieval strategies
- **Adaptive strategies** — dynamically switching between lexical, semantic, graph-based, hybrid
- **Failure signal detection** — recognizing when a strategy is ineffective and pivoting
- *Bridges to:* [[Convergence rate]] (evaluation); **Economics of reasoning** (cost tiers govern which queries get full agent treatment)

### Query Understanding
- **Entity extraction** — identifying entities like "Python" from ambiguous queries
- **Intent classification** — determining domain (programming resources, product search, etc.)
- **Temporal constraints** — resolving references like "last week" into date ranges
- **Disambiguation** — generating multiple hypotheses for underspecified queries
- **Probabilistic interpretation space** — producing a distribution over possible meanings, not a single answer
- **Intent-specific feature vectors** — query embeddings weighted by inferred intent (e.g., CPU/RAM emphasis for "laptop for coding" vs. GPU/display for "video editing computer")
- **Partial intent** — users express fragments, not fully formed instructions
- *Bridges to:* **Agentic interpretation** (replaces linear NLP labels with structured reasoning artifacts); [[Strategy selection]] (interpretation drives which retrieval approach to use)

### Relevance & Ranking
- **LLM relevance scoring** — useful prior but doesn't personalize, adapt to drift, or explain failures
- [[Hybrid relevance scoring|Hybrid scoring]] — combines LLM signals with behavioral feedback using adaptive weights
- [[Behavioral feedback signals|Behavioral feedback]] — clicks, dwell time as high-signal but high-variance indicators
- [[Position-normalized click model]] — corrects for position bias in click-through rates
- [[Negative signals]] — fast bounces, "not helpful" feedback; low frequency but extremely high precision
- **Disproportionate influence / veto power** — negative signals given outsized weight due to their unambiguous nature
- **Multi-objective optimization** — weighting heterogeneous signals (LLM relevance, CTR, dwell time, negative feedback)
- [[Adaptive policy]] — weights shift across different regimes rather than using a fixed formula
- *Bridges to:* [[00-inbox/agentic-search-control-loop]] (relevance scoring closes the loop from retrieval to reasoning to user refinement); **Hybrid lexical + vector backends** (ranking operates over mixed result sets)

### Production Systems
- [[Flink streams]] — real-time query complexity routing
- [[Temporal orchestrator]] — stateful agent service coordination (workflow engine)
- [[Cache layers]] — first tier of the cost model; deterministic repeated intents at ~10ms
- **Hybrid lexical + vector backends** — production search backend combining both retrieval paradigms
- **Multi-stage ranking** — progressive filtering and re-ranking pipeline
- [[Query routing]] — classifying queries by complexity to decide processing depth
- **P95 latency ~100ms** — production constraint for agentic search systems
- **6% zero-result rate** — real-world quality metric
- *Bridges to:* **Economics of reasoning** (production architecture implements the cost tiers); [[Composable tools]] (atomic functions vs. monolithic API design)

### Economics of Reasoning
- **Tier 1: Cache patterns** — ~10ms latency, near-free cost, deterministic repeated intents
- **Tier 2: Distilled models** — ~50ms latency, inexpensive, simple reasoning tasks
- **Tier 3: Single-pass agent** — ~200ms latency, moderate cost, structured retrieval
- **Tier 4: Full reasoning** — ~500ms latency, high cost, complex multi-turn queries
- Key insight: majority of traffic stays in efficient tiers; only complex queries receive depth
- *Bridges to:* **Production systems** (architecture implements tiered routing); [[Query routing]] (Flink classifies which tier handles each query)

### Evaluation
- [[Convergence rate]] — how many steps before the reasoning loop terminates
- [[Strategy diversity]] — how many distinct strategies were explored (lexical-first vs. graph-first, etc.)
- [[Information gain per iteration]] — quality of each reasoning step
- [[Entropy reduction]] — measuring how much uncertainty decreases across the loop
- **Signal fidelity** (retrieval eval) vs. **Policy quality** (agent eval) vs. **System intelligence** (joint eval)
- *Bridges to:* [[00-inbox/agentic-search-control-loop]] (evaluation measures the loop's effectiveness); **Adaptive strategies** (diversity metrics track strategy breadth)

### Future Horizons
- **Near-term (end of 2025):** **Multi-turn clarification**, **Cross-session memory**, real-time user learning
- **Mid-term (2026):** **Domain-specialized agents**, microservices for reasoning, anticipatory search
- **Long-term:** **Ambient intelligence** — always-available, multimodal agents across all devices and contexts
- **AGI futures:**
  - Search dissolves — AGI anticipates needs, information flows without explicit queries
  - Knowledge routing — AGI routes knowledge between specialized agents or humans
  - **Reality querying** — simulation as a query primitive; "what if" becomes computable at scale
- Core paradox: "The better search gets, the less it resembles search"
- *Bridges to:* [[Stateful reasoning]] (multi-turn clarification is an incremental step from current agentic patterns); **Recommendation systems** (YouTube recommendations as an early signal of search dissolving into understanding)

---

## Learning Roadmap

### Phase 1: Foundations — Classical IR (Weeks 1-3)

**What to study:**
- BM25 and TF-IDF scoring mechanics — understand term frequency, inverse document frequency, and why these remain the backbone of transparent retrieval
- Inverted indexes, tokenization, and lexical matching pipelines
- Why vocabulary mismatch breaks lexical search
- Sparse representations and their tradeoffs (speed vs. semantic understanding)

**Resources & papers:**
- "Introduction to Information Retrieval" (Manning, Raghavan, Schutze) — chapters 1-8
- Elasticsearch / Lucene documentation (hands-on BM25)
- Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond" (2009)
- Stanford CS276: Information Retrieval and Web Search (free lectures)

**Project idea — `bm25-search-engine`:**
Build a BM25 search engine from scratch in Python. Index a dataset (Wikipedia abstracts or ArXiv papers), implement tokenization, inverted index, and BM25 scoring. Add a simple CLI and API. Demonstrate understanding of the scoring math, not just library calls.

---

### Phase 2: Modern Retrieval — Embeddings & RAG (Weeks 4-7)

**What to study:**
- Dense embeddings (sentence-transformers, OpenAI embeddings) and how they capture semantic similarity
- Chunking strategies and their failure modes (chunk collapse, boundary artifacts)
- KNN / approximate nearest neighbor search (FAISS, HNSW)
- Vector drift — why embeddings degrade and how to detect it
- RAG architecture: retrieval + generation pipeline, its strengths and stateless limitations

**Resources & papers:**
- Karpathy, "Let's build GPT" and embedding intuitions
- "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (Lewis et al., 2020)
- "Sentence-BERT" (Reimers & Gurevych, 2019)
- Pinecone / Weaviate / Qdrant documentation for vector DB patterns
- "ColBERT: Efficient and Effective Passage Search" (Khattab & Zaharia, 2020)

**Project idea — `hybrid-retrieval-bench`:**
Build a hybrid retrieval system that combines BM25 (from Phase 1) with vector search. Benchmark lexical-only vs. semantic-only vs. hybrid on the same dataset. Visualize the precision/recall tradeoffs. Show where each approach wins and loses.

---

### Phase 3: Agentic Patterns — Stateful Search & Reasoning Loops (Weeks 8-12)

**What to study:**
- Agentic search architecture: control loops, reformulation trajectories, session-local state
- Tool composition: atomic, composable search tools vs. monolithic APIs
- Query understanding pipeline: entity extraction, intent classification, temporal constraint resolution, disambiguation
- Multi-turn reasoning: how the agent decides when to refine, pivot strategy, or terminate
- The key insight from the talk: "BM25 paired with an agent outperforms a complex neural network without an agent" — predictability over sophistication

**Resources & papers:**
- "ReAct: Synergizing Reasoning and Acting in Language Models" (Yao et al., 2023)
- "Toolformer: Language Models Can Teach Themselves to Use Tools" (Schick et al., 2023)
- "Self-RAG: Learning to Retrieve, Generate, and Critique" (Asai et al., 2023)
- LangChain / LlamaIndex agent documentation (for implementation patterns)
- OpenAI function calling and tool-use patterns

**Project idea — `agentic-search-agent`:**
Build a stateful search agent that takes an ambiguous query (like "that Python memory thing from last week"), performs entity extraction, intent classification, and temporal resolution, then iteratively searches across multiple backends (BM25 + vector). Track the reformulation trajectory and confidence at each step. Show the reasoning trace. This directly implements the core architecture from Tosh's talk.

---

### Phase 4: Production Systems — Cost, Latency & Infrastructure (Weeks 13-16)

**What to study:**
- The 4-tier economics of reasoning: cache patterns, distilled models, single-pass agent, full reasoning
- Query routing and complexity classification (when to invoke expensive reasoning)
- Stream processing for real-time query routing (Apache Flink concepts)
- Workflow orchestration for stateful agents (Temporal.io patterns)
- Hybrid backends in production: combining lexical + vector retrieval with multi-stage ranking
- Latency budgets: targeting P95 ~100ms while supporting agentic depth

**Resources & papers:**
- "Serving Deep Learning Models at Scale" (Meta engineering blog posts)
- Apache Flink documentation — streaming concepts
- Temporal.io documentation — workflow orchestration patterns
- "Are More LLM Calls All You Need? Towards Scaling Laws for Compound AI Systems" (2024)
- Google "Scaling Personalized Web Search" and Meta search infrastructure talks

**Project idea — `tiered-search-router`:**
Build a query router that classifies incoming queries into the four cost tiers from the talk. Simple/cached queries get instant BM25 responses. Medium complexity gets a distilled model pass. Complex queries trigger the full agentic loop. Instrument latency and cost metrics at each tier. Deploy with a simple dashboard showing query distribution across tiers.

---

### Phase 5: Evaluation & Measurement (Weeks 17-20)

**What to study:**
- Why traditional IR metrics (precision, recall, NDCG) are insufficient for agentic systems
- Trajectory-level evaluation: convergence rate, strategy diversity, information gain per iteration
- Entropy reduction as a measure of reasoning quality
- Separating signal fidelity (retrieval quality) from policy quality (agent decision quality) from system intelligence (joint quality)
- A/B testing and online evaluation for search systems
- Position-normalized click models and behavioral feedback interpretation

**Resources & papers:**
- "Beyond Accuracy: Behavioral Testing of NLP Models" (Ribeiro et al., 2020)
- TREC evaluation methodologies
- "Offline Evaluation to Make Decisions About Retrieval-Augmented Generation" (2024)
- Google "Interleaving Experiments" papers on online search evaluation
- "Expected Reciprocal Rank for Graded Relevance" (Chapelle et al., 2009)

**Project idea — `agent-eval-framework`:**
Build an evaluation framework for agentic search. Given a set of test queries, run them through your Phase 3 agent and measure: convergence rate (steps to termination), strategy diversity (how many distinct retrieval approaches used), information gain per step, and final answer quality. Compare against a single-shot RAG baseline. Publish results as a blog post with visualizations.

---

## Project Ideas for GitHub Portfolio

### 1. `bm25-from-scratch` — Transparent Retrieval Engine

**What to build:** A complete BM25 search engine implemented from scratch (no Lucene/Elasticsearch). Include tokenization, inverted index construction, BM25 scoring with tunable parameters, and a REST API. Add a benchmarking suite that shows precision/recall on standard datasets.

**Concepts demonstrated:** BM25/TF-IDF scoring, sparse representations, inverted indexes, lexical retrieval pipelines — the foundational layer that Tosh emphasizes as still critical because agents need predictable, transparent backends.

**Why it impresses:** Shows you understand search from first principles, not just API calls. Google and Meta search teams value engineers who understand the math underneath. The talk's key point — "BM25 paired with an agent outperforms complex neural networks without one" — makes this foundation directly relevant to agentic systems.

**Complexity:** Weekend to 1 week

---

### 2. `agentic-search-loop` — Stateful Multi-Turn Search Agent

**What to build:** A search agent that implements the full reasoning loop from the talk. Given an ambiguous query, it: (1) parses entities, intent, and temporal constraints, (2) selects a retrieval strategy (lexical, semantic, hybrid), (3) executes retrieval, (4) evaluates results and decides whether to refine, pivot, or terminate, (5) tracks the full reformulation trajectory with confidence scores at each step.

**Concepts demonstrated:** Stateful reasoning, control loops, tool composition, query understanding (entity extraction, intent classification, disambiguation), adaptive strategy selection, session memory, failure signal detection.

**Why it impresses:** This is the core architecture Tosh described. It shows you can build the system that Meta is actively working on. The reasoning trace output demonstrates you understand why agentic search is a different computational model, not just "search 2.0."

**Complexity:** 2-3 weeks

---

### 3. `hybrid-relevance-scorer` — Multi-Signal Ranking System

**What to build:** A relevance scoring system that implements hybrid scoring by combining LLM relevance judgments with simulated behavioral signals (clicks, dwell time, negative feedback). Implement position-normalized click models, negative signal veto logic, and adaptive weight tuning across different query regimes.

**Concepts demonstrated:** Hybrid scoring, multi-objective optimization, behavioral feedback integration, position bias correction, negative signals as high-precision indicators, adaptive policy for weight adjustment.

**Why it impresses:** Ranking is the core competency of search teams at Google and Meta. This project shows you understand how to combine heterogeneous signals, handle position bias, and build adaptive scoring — exactly the nuances Tosh described in the Q&A section.

**Complexity:** 1-2 weeks

---

### 4. `search-cost-router` — Economics of Reasoning in Practice

**What to build:** A query routing system that classifies queries into the four cost tiers (cache hit, distilled model, single-pass agent, full reasoning) and routes them to appropriate backends. Include a query complexity classifier, latency instrumentation at each tier, a cost simulator, and a dashboard showing real-time tier distribution. Demonstrate that the majority of traffic stays efficient while complex queries get depth.

**Concepts demonstrated:** The 4-tier cost model, query routing, Flink-style stream processing concepts, latency budgets, production search architecture, the economic backbone of agentic search.

**Why it impresses:** This shows production thinking — not just "can you build an agent" but "can you build an agent system that's economically viable at scale." This is the gap between a demo and a real system, and it's exactly what hiring managers at Meta/Google care about.

**Complexity:** 2 weeks

---

### 5. `agent-trajectory-eval` — Evaluation Framework for Agentic Search

**What to build:** An evaluation harness that measures agentic search quality beyond traditional IR metrics. Implement: convergence rate tracking, strategy diversity scoring, information gain per iteration, entropy reduction curves, and joint retrieval+agent evaluation. Run against a test suite of ambiguous queries and publish a comparison between single-shot RAG vs. agentic search.

**Concepts demonstrated:** Trajectory-level evaluation, convergence rate, strategy diversity, information gain per iteration, entropy reduction, signal fidelity vs. policy quality vs. system intelligence — the evaluation framework Tosh outlined in the Q&A.

**Why it impresses:** Evaluation is an unsolved problem in agentic search. Anyone can build a demo agent; very few people build rigorous evaluation frameworks. This signals research maturity and production readiness — you don't just build systems, you know how to measure whether they work.

**Complexity:** 2-3 weeks

---

## Key Quotes

> "For about two decades search was built around the assumption that users express this fully formed intent. That is no longer true."

Why it matters: This frames the entire paradigm shift. Classical IR assumed users knew what they wanted and could articulate it. Agentic search exists because that assumption collapsed.

---

> "This is not search 2.0. It's a different computational model."

Why it matters: Tosh is making a sharp distinction — agentic search isn't an incremental improvement. It's a fundamentally different architecture where retrieval is part of a control loop, not an endpoint. This reframes how to think about career positioning in this space.

---

> "A simple BM25, when paired with an agent, outperforms a complex neural network without an agent."

Why it matters: This is the most actionable insight in the talk. It means the agent layer matters more than the retrieval backend sophistication. It also means your backend needs to be predictable, not fancy — which has direct implications for system design.

---

> "Your backend doesn't need to be fancy. It needs to be predictable."

Why it matters: This is the design principle that separates production agentic search from demos. Agents reason better over transparent, interpretable systems (BM25) than opaque black-box embeddings. It inverts the assumption that more complex models are always better.

---

> "What we're trying to build is a probabilistic space for interpretation and not a single answer."

Why it matters: This describes the shift from deterministic query parsing to probabilistic query understanding. The system generates multiple hypotheses for disambiguation rather than committing to one interpretation — a fundamentally different architecture for query understanding.

---

> "The better search gets, the less it resembles search."

Why it matters: This is the philosophical thesis of the entire talk. As search evolves toward anticipatory, ambient intelligence, the act of "searching" dissolves into "understanding." It frames where the industry is heading over the next decade.

---

> "Negative signals tend to be sparse but unambiguous. We give them disproportionate influence, sometimes even a veto."

Why it matters: This is a practical production insight about ranking. In hybrid scoring, not all signals are equal — a "not helpful" click or fast bounce is rare but extremely high-precision. Giving negative signals veto power is a non-obvious design choice that reveals how real search ranking works at Meta's scale.
