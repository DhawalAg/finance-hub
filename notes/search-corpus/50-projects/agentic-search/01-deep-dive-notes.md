---
type: note
project: agentic-search
tags:
  - type/study
  - topic/search
  - topic/agents
  - topic/ml-systems
---
# Agentic Search — Deep Dive Notes

**Speaker:** Tosh — Senior Engineering Manager, AI/ML at Meta (ex-Lyft, ex-Amazon CV/ML)
**Source:** [YouTube talk](https://www.youtube.com/watch?v=WAkcj_Kvg9Y)
**Transcript:** [[agentic-search-meta-transcript]]

---

## Chapter 1: Why IR Breaks Under Real-World Ambiguity

### What Was Said

Tosh opens by framing the central thesis: a shift is happening quietly underneath nearly every retrieval system in production today. For about two decades, search was built around the assumption that users express fully formed intent. That is no longer true — interfaces have changed, user expectations have changed, and the world in the past five years has changed significantly. Search systems that were once deterministic and stateless — and "flew brutally light" — now need to behave more like distributed reasoning systems.

He traces the architectural evolution of search in three stages:

1. **Lexical pipelines** — [[BM25]], [[20-notes/ai/ml-algos/TF-IDF]]. These were deterministic and extremely fast. They relied on sparse interpretations and had no semantic structure. Every token was treated as an independent statistical event. These systems fell apart when vocabulary diverged from user phrasing.

2. **Vector-based RAG systems** — Introduced embeddings, dense representation, and semantic similarity. But they came with new challenges: chunking heuristics, KNN latency, and a fundamentally stateless generation step. As embeddings got better, chunk collapses, vector drifts, and irrelevance became a significant operational cost.

3. **Agentic search** — An entirely different category. Instead of a single retrieval step, you get multi-turn reasoning, strategies, tool calls, and state. Retrieval becomes part of a control loop, not an endpoint. Tosh explicitly says: "This is not search 2.0. It's a different computational model."

The reason for this shift becomes obvious when looking at user behavior. Tosh presents what he calls a "2x2 diagram" that captures a fundamental truth: users are increasingly operating in the high-ambiguity, high-complexity region. Most queries today are underspecified by design. Users say things like "find that Python memory thing from last week" or "a laptop for editing but light."

Static information retrieval assumes that text is truth. But what users are doing is expressing partial intent, not instructions. The failure modes — zero session memory, intent collapse, lexical brittleness — are all natural outcomes of this architectural mismatch. The system does exactly what you tell it, which is precisely the problem.

To make it concrete, he uses the example "Python memory thing from last week." This is incomplete, fuzzy, and partially recalled intent with temporal grounding. It is not a keyword retrieval problem — it is an interpretation problem. The system needs to: detect entities (Python is an entity), resolve temporal constraints ("last week"), classify the domain (programming resources), and infer the missing structure (is it an article, tutorial, or code snippet?). Without reasoning, this query is impossible to answer well. This is the canonical example that motivates the agentic approach.

### Key Concepts Introduced

- **Lexical pipelines** `[INFRA]` — Deterministic search systems based on token frequency statistics (BM25, TF-IDF); no semantic understanding
- **Vector-based RAG systems** `[INFRA]` — Retrieval-augmented generation using dense embeddings and semantic similarity; stateless generation step
- **Agentic search** `[STRATEGY]` — A computational model where retrieval is part of a multi-turn control loop with state, tool calls, and reasoning strategies
- **Intent collapse** `[MENTAL MODEL]` — When a search system reduces a complex, multi-faceted user intent into a single keyword match, losing critical context
- **Partial intent** `[MENTAL MODEL]` — The observation that modern users express incomplete, fuzzy, contextual queries rather than fully-formed search instructions
- **Chunk collapse** `[ML]` — Degradation in retrieval quality when chunking heuristics cause semantically important content to be split or merged incorrectly
- **Vector drift** `[ML]` — Embedding representations shifting over time as the underlying data distribution changes, causing retrieval quality to degrade

### Cross-References

- The "Python memory thing from last week" example recurs throughout — it is the running case study through Chapters 1-3
- The three-stage evolution (lexical -> vector -> agentic) is the structural backbone of the entire talk; Chapter 3 builds the engineering blocks for stage 3
- "Retrieval becomes part of a control loop, not an endpoint" directly sets up the stateful reasoning architecture in Chapter 2

### Industry Context

The lexical-to-vector-to-agentic evolution is broadly recognized across the search industry, not Meta-specific. [[BM25]] and TF-IDF are foundational IR algorithms dating back decades. RAG (retrieval-augmented generation) became the dominant paradigm in 2023-2024 across the industry. The framing of agentic search as a "different computational model" rather than an incremental improvement is a perspective gaining traction among ML systems engineers but is not yet consensus.

---

## Chapter 2: When Retrieval Becomes Stateful Reasoning

### What Was Said

Tosh presents the core data structure for an agentic search engine — what he calls the "agentic search state." This state object holds: the original query, a reformulation trajectory, embeddings associated with each iteration, a set of retrieval strategies, confidence curves, and diversity metrics.

This is session-local memory, which means a consistent internal representation that survives across tool calls and across iterations. The engineering challenges are: how do you do adaptive strategies, how do you perform failure signal detection, how do you do atomic component updates, and how do you handle diversity analysis. Tosh emphasizes these are system problems, not model problems. What is needed is a distributed stateful multi-turn controller.

With that state, the system can execute a controlled reasoning loop. Returning to the "Python memory thing" example, Tosh walks through the realistic conversion process:

- Initial query: "Python memory thing from last week" — result entropy is extremely high, the system is essentially blind
- First reformulation: "Python memory leak detection" — still high entropy, but the strategy is ineffective
- Each stage of the loop involves: query understanding (entity extraction, intent classification, ambiguity detection), then strategy selection (lexical, semantic, graph-based, hybrid), then execution against multiple backends orchestrated with fault tolerance

This loop is fundamentally a form of online optimization.

Tosh then contrasts two design philosophies for building these systems:

1. **Monolithic API** — A single search endpoint with dozens of parameters. Brittle for LLMs because they are nondeterministic. Nearly impossible to reason about.

2. **Composable tools** — Atomic, transparent functions like "keyword search" or "semantic search." These serve as primitives for the agent. They make planning tractable, improve determinism, simplify debugging, and make the policy space easier to manage.

Those primitives only work if the substrate is understandable. Tosh presents what he calls his "favorite benchmarking slide for search": a simple [[BM25]], when paired with an agent, outperforms a complex neural network without an agent. Agents need predictable score distributions and semantics. Opaque re-rankers and blackbox embeddings make reasoning difficult — it becomes hard to understand cause and effect. Transparent systems like [[BM25]] make the agent's hypothesis accurate and refinement much more meaningful. The takeaway: "Your backend doesn't need to be fancy. It needs to be predictable."

### Key Concepts Introduced

- **Agentic search state** `[INFRA]` — A session-local data structure holding the original query, reformulation trajectory, per-iteration embeddings, retrieval strategies, confidence curves, and diversity metrics
- **Reformulation trajectory** `[ML]` — The sequence of query rewrites and their associated embeddings across reasoning iterations
- **Confidence curves** `[ML]` — Per-iteration confidence scores tracking how certain the system is about its retrieval results across the reasoning loop
- **Composable tools** `[STRATEGY]` — Atomic, transparent search primitives (keyword search, semantic search) that agents can plan with, as opposed to monolithic multi-parameter APIs
- **Online optimization** `[MENTAL MODEL]` — Framing the agentic search loop as a real-time optimization process rather than a static retrieval pipeline
- **Failure signal detection** `[INFRA]` — The system's ability to detect when a retrieval strategy has failed and trigger re-planning
- **Score distribution predictability** `[MENTAL MODEL]` — The property that an agent's backend must have understandable, consistent score distributions for the agent to reason effectively about retrieval quality

### Cross-References

- The "Python memory thing" example from Chapter 1 is walked through the reasoning loop here, showing entropy reduction across iterations
- The composable tools philosophy directly enables the production architecture described in Chapter 4 (Flink streams, Temporal orchestrator)
- "BM25 with agent beats complex neural net without agent" is a foundational claim that underpins the design choices in Chapter 3 (intent-conditioned embeddings, hybrid scoring)
- -> see Chapter 3: [[intent-conditioned embeddings]] for how the query understanding step produces intent-specific feature vectors
- -> see Chapter 4: the Temporal-based agent service is the production realization of the "distributed stateful multi-turn controller"

### Industry Context

The monolithic-vs-composable debate is industry-wide. The OpenAI function-calling paradigm, LangChain tool abstractions, and Anthropic's tool-use patterns all reflect the composable tools philosophy. The finding that BM25+agent outperforms complex neural net alone is a provocative but increasingly validated result in the retrieval community — it echoes findings from papers on REALM and RETRO showing that simpler retrieval with better reasoning often wins. The emphasis on predictability over sophistication in retrieval backends is a distinctive engineering insight, more practitioner wisdom than academic consensus.

---

## Chapter 3: Building Blocks of Agentic Systems

### What Was Said

Tosh shifts to the components that make agentic systems work, starting with modern query interpretation. In agentic systems, the task is transforming free text into structured meaning. Traditional NLU pipelines were sequential and brittle — they produced linear labels, not reasoning artifacts.

Agentic interpretation instead generates a structured output: query type, semantic intent, and temporal constraints. For the "Python memory thing" example, the system produces multiple hypotheses for disambiguation. The goal is to build a probabilistic space for interpretation, not a single answer. This makes downstream strategies much more targeted, and it is this grounding in linguistics that enables reasoning.

Once user intent is known, the system classifies the task being performed. Tosh presents [[intent-conditioned embeddings]] through three examples of intent-specific feature vectors:

- **"Laptop for coding"** — the system emphasizes CPU, RAM, dev environment
- **"Video editing computer"** — emphasizes GPU throughput, display surface
- **"Portable workstation"** — emphasizes mobility and energy constraints

This is structurally different from document embeddings. What is being built here is query embeddings that are conditioned on intent. The outcome: roughly **35% lift in precision**, with minimal latency overhead. Tosh describes this as "high frequency semantic inference."

Interpretation alone is not enough — relevance requires real human feedback. Tosh addresses the limitations of LLM-based relevance scoring: it has useful priors but it does not personalize, it does not adapt to drift, and it is not interpretable when it fails.

[[Hybrid relevance scoring]] combines LLM signals with behavioral feedback. Tosh presents a hybrid relevance scaling equation. The behavioral signals provide grounding, human feedback corrects model hallucinations, and weighting gives control. This closes the loop: retrieval to reasoning to user to refinement.

He then addresses the economics of reasoning with a tiered cost table:

| Tier | Mechanism | Latency | Cost | Use Case |
|------|-----------|---------|------|----------|
| 1 | Cache patterns | ~10ms | Free-ish | Deterministic, repeated intents |
| 2 | Distilled models | ~50ms | Inexpensive | Simple reasoning |
| 3 | Single-pass agent | ~200ms | Moderate | Standard agentic queries |
| 4 | Full reasoning | ~500ms | High | Complex queries |

The key insight: only complex queries receive the depth of full reasoning. The majority of traffic remains extremely efficient. This is what Tosh calls "the economic backbone of search in an agentic context."

### Key Concepts Introduced

- **[[Intent-conditioned embeddings]]** `[ML]` — Query embeddings that are dynamically constructed based on classified user intent, producing different feature vectors for different task types even when surface queries overlap; yielded ~35% precision lift
- **[[Hybrid relevance scoring]]** `[ML]` — A scoring function that combines LLM relevance signals with behavioral feedback (clicks, dwell time) and human feedback, using adaptive weighting to balance the components
- **Probabilistic interpretation space** `[ML]` — Generating multiple disambiguation hypotheses for a query rather than collapsing to a single interpretation
- **Intent-specific feature vectors** `[ML]` — Dense representations that weight different attributes (CPU vs GPU vs mobility) depending on the classified intent
- **Tiered reasoning economics** `[STRATEGY]` — A cost architecture that routes queries to different computational tiers (cache -> distilled -> single-pass agent -> full reasoning) based on complexity
- **Reasoning artifacts** `[MENTAL MODEL]` — Structured outputs from query interpretation (query type, semantic intent, temporal constraints) as opposed to flat labels from traditional NLU
- **Behavioral feedback signals** `[ML]` — Click-through rate, dwell time, negative signals (fast bounce, explicit "not helpful") used to ground and correct LLM-based relevance scoring

### Cross-References

- -> see Chapter 1: The "Python memory thing" example is used again here to illustrate probabilistic interpretation and multiple hypothesis generation
- -> see Chapter 2: The composable tools philosophy enables the tiered routing — cache patterns, distilled models, and full agent reasoning are distinct primitives
- -> see Chapter 4: The tiered cost table directly maps to the production architecture's query routing layer (Flink streams for complexity assessment)
- -> see Q&A Section: Hybrid scoring weights are addressed in detail during the audience Q&A

### Industry Context

[[Intent-conditioned embeddings]] represent an approach that goes beyond standard bi-encoder or cross-encoder retrieval. The idea of conditioning embeddings on classified intent is an active research area — related to query-aware document representation in academic IR. The 35% precision lift is a strong claim and likely reflects Meta-scale data and infrastructure. The tiered reasoning economics pattern is industry-wide — Google, Microsoft (Bing/Copilot), and Perplexity all implement some form of query complexity routing to manage inference costs. The hybrid scoring approach (combining LLM priors with behavioral signals) is common practice at major search companies, though the specific formulation and weighting strategies are proprietary.

---

## Chapter 4: What These Systems Look Like in Production

### What Was Said

Tosh describes what a modern production-grade agentic search system looks like. The architecture has several layers:

1. **Query routing** — Using Apache Flink streams for real-time complexity assessment
2. **Cache layer** — Serving deterministic, repeated intents at minimal cost
3. **Agent service** — A stateful orchestrator, which Tosh says can be built on [[Temporal]] (the workflow orchestration framework)
4. **Search backend** — Hybrid lexical plus vector retrieval, along with multi-stage ranking

This is what it looks like when reasoning meets production constraints. Tosh shares specific production metrics:

- **~100ms p5 latency** (95th percentile latency)
- **6% zero result rate**

### Key Concepts Introduced

- **Flink-based query routing** `[INFRA]` — Using Apache Flink streaming for real-time assessment of query complexity to route queries to the appropriate reasoning tier
- **[[Temporal]]-based agent orchestration** `[INFRA]` — Using the Temporal workflow engine as the stateful orchestrator for agentic search, managing tool calls, retries, and state persistence
- **Multi-stage ranking** `[INFRA]` — A ranking pipeline with multiple scoring passes (likely candidate generation -> re-ranking -> final scoring)
- **Hybrid lexical plus vector retrieval** `[INFRA]` — Production backend combining BM25-style lexical matching with dense vector retrieval
- **P5 latency** `[INFRA]` — 95th percentile latency; the system achieves ~100ms at this threshold
- **Zero result rate** `[INFRA]` — Percentage of queries returning no results; 6% in production (a measure of system coverage)

### Cross-References

- -> see Chapter 2: The "distributed stateful multi-turn controller" is realized here as the Temporal-based agent service
- -> see Chapter 3: The tiered cost table maps directly to this architecture — cache layer (Tier 1), agent service routing to distilled models (Tier 2), single-pass agent (Tier 3), or full reasoning (Tier 4)
- -> see Chapter 2: Composable tools philosophy is what makes Flink-based routing feasible — each tool has predictable cost and latency characteristics
- -> see Chapter 5: The production system described here is the current state; the horizons in Chapter 5 describe where it evolves

### Industry Context

Apache Flink for real-time stream processing in search routing is a Meta-specific choice — other companies use Kafka Streams, Apache Beam, or custom solutions. [[Temporal]] for workflow orchestration is gaining adoption across the industry (Uber, Netflix, Stripe use it), but its application specifically as an agentic search orchestrator appears to be a Meta practice. The 100ms p5 latency is competitive with industry standards for complex search — traditional search engines target sub-50ms, but agentic systems with reasoning loops inherently add latency. A 6% zero result rate is a meaningful production metric; for context, mature e-commerce search systems typically target below 5%.

---

## Chapter 5: How AGI Dissolves the Boundary Between Search and Understanding

### What Was Said

Tosh presents the future trajectory across three horizons:

**Near-term (end of this year):**
- Multi-turn clarification
- Cross-session memory
- Real-time user learning

**Mid-term (~2026):**
- Domain-specialized agents
- Microservices for reasoning (already happening in some spaces)
- Anticipatory search

**Long-term:**
- Ambient intelligence — always available
- Multimodal agents operating across all devices and contexts
- Search becomes conversational, conversation becomes predictive, predictive becomes embedded

On a philosophical note, Tosh posits that search may disappear entirely. If AGI fully understands intent, context, and world state, what does search become? He offers three possible futures:

1. **Search dissolves** — AGI anticipates needs. Information flows without explicit queries.
2. **AGI as knowledge router** — AGI routes knowledge between specialized agents or humans.
3. **Reality querying** — Simulation becomes a query primitive. "What if" becomes computable at scale.

Tosh identifies a paradox: the better search gets, the less it resembles search. At some point, retrieval becomes understanding.

He closes: "We're at a moment where search is transforming into something fundamentally more capable and more aligned with how humans actually think."

### Key Concepts Introduced

- **Cross-session memory** `[INFRA]` — Persistent state across multiple user sessions, enabling the system to remember past interactions and build user models over time
- **Anticipatory search** `[STRATEGY]` — Systems that predict what users will need before they ask, moving from reactive retrieval to proactive information delivery
- **Ambient intelligence** `[STRATEGY]` — Always-available, context-aware AI operating across all devices; search as a background capability rather than an explicit action
- **Domain-specialized agents** `[STRATEGY]` — Purpose-built reasoning agents for specific verticals (legal, medical, code, etc.) rather than general-purpose search
- **Microservices for reasoning** `[INFRA]` — Decomposing reasoning capabilities into independently deployable services, analogous to microservice architecture in traditional software
- **Reality querying** `[MENTAL MODEL]` — A speculative future where simulation and "what if" computations become a search primitive, replacing static document retrieval
- **The search paradox** `[MENTAL MODEL]` — The observation that as search systems improve, they increasingly stop resembling search; retrieval converges with understanding

### Cross-References

- -> see Chapter 1: The three-stage evolution (lexical -> vector -> agentic) extends here into a fourth implicit stage: search dissolving into understanding
- -> see Chapter 2: The stateful reasoning architecture is a prerequisite for cross-session memory and anticipatory search
- -> see Chapter 4: The production metrics (100ms p5, 6% zero result rate) represent the current baseline that these future horizons build from
- -> see Speaker Insights: The host's YouTube recommendation analogy directly illustrates the anticipatory search concept

### Industry Context

The three horizons framework roughly aligns with industry roadmaps from Google (Gemini integration into Search), Microsoft (Copilot), and Perplexity (conversational search). Cross-session memory is already partially implemented in ChatGPT's memory feature and Google's personalized search. Domain-specialized agents are emerging across the industry (Harvey for legal, Hippocratic AI for medical). The "search dissolves" thesis is a view shared by several industry leaders — Sam Altman has made similar claims about the future of search. Reality querying / simulation-as-search is more speculative and aligns with research on world models (Meta's own JEPA work, DeepMind's Genie). The three possible AGI futures Tosh outlines are philosophical framing, not technical predictions.

---

## Q&A Section

### Question 1: Hybrid Scoring Weights (from Apurva)

**Q:** For hybrid scoring, how do you weigh the different terms?

**Tosh's response:** The hybrid scoring system combines several signal types, and they should not be treated symmetrically because each carries different statistical properties:

- **LLM relevance** — A good prior but not a proper ground truth. Useful as a starting point but insufficient alone.
- **CTR and dwell time** — High signal but high variance. Good short-term indicators for relevance, but very sensitive to personalization and position bias. Tosh recommends applying sharper normalization, specifically a **position-normalized click model**.
- **Negative feedback** (user says "not helpful," fast bounce) — Low frequency but extremely high precision. Tosh says they give disproportionate influence to negative signals, sometimes even a **veto power**, because negative signals tend to be sparse but unambiguous.

The right way to think about hybrid scoring is not as a fixed formula but as an **adaptive policy** where the weights change across different regimes — sometimes one factor influences more than others depending on context.

### Question 2: Evaluation of Agentic Systems (from Apurva)

**Q:** Any inputs on the evaluation phase, either of retrieval or of agent paths?

**Tosh's response:** Evaluating agentic systems is fundamentally different from traditional IR because you are no longer measuring a single hop — you are measuring a trajectory. The evaluation metrics to consider are more like those for a planning algorithm:

- **Convergence rate** — How many steps does the reasoning loop take before termination?
- **Strategy diversity** — How many distinct strategies were explored? (lexical first vs. graph first, etc.)
- **Information gain per iteration** — How much quality improvement happens at each step?

Evaluation is layered:
- **Retrieval evaluation** tells you signal fidelity
- **Agent evaluation** tells you policy quality
- **Combined retrieval + agent evaluation** gives you system intelligence

Joint metrics — convergence rate, entropy reduction, quality of the reasoning path — tell you whether the entire loop is working as intended.

---

## Speaker Insights

### Host's YouTube Recommendation Analogy

The host draws a parallel between the future of search and the evolution of YouTube. In the early days of YouTube, users searched using the search bar. As recommendation systems improved, explicit search became unnecessary — "who uses the search bar on YouTube?" The host suggests that search may follow a similar trajectory: the system predicting, embedding, surfacing, and almost recommending the right content at the right time.

Tosh validates this analogy. He says YouTube recommendations are "a really good early signal of where search is headed." Modern recommendation systems (YouTube, TikTok, Instagram Reels) have shifted from "how do we retrieve relevant items" to "predict the next embedding." YouTube recommendation models "what are you probably going to watch next" — future search systems will model "what are you probably going to ask next." In both cases, the system is no longer matching but **forecasting**. This is the essence of search dissolving into understanding.

### Host's ChatGPT Forecasting Behavior Observation

The host shares a personal observation: when interacting with ChatGPT, he gives it a "seed of thought" and then for the next five or six prompts mostly says "sure," "yeah, go for it," "okay, I want to see it." The system is pulling him forward — showing him what he should be interested in. It is a form of recommendation, and the host imagines it is "forecastable internally on their end."

This observation illustrates the anticipatory search thesis from Chapter 5 in action — the system is already beginning to predict and lead rather than wait for explicit queries.

---

## Concepts Index

| Concept | Definition | Chapter |
|---------|-----------|---------|
| **Adaptive policy (scoring)** | Hybrid scoring approach where weights between signals change dynamically across different query regimes rather than remaining fixed | Q&A |
| **Agentic search** | A computational model where retrieval is embedded in a multi-turn control loop with state, tool calls, and reasoning strategies | Ch 1, Ch 2 |
| **Agentic search state** | Session-local data structure holding query, reformulation trajectory, embeddings, strategies, confidence curves, and diversity metrics | Ch 2 |
| **Ambient intelligence** | Always-available, context-aware AI operating across devices where search is a background capability | Ch 5 |
| **Anticipatory search** | Systems that predict user needs before explicit queries, moving from reactive to proactive retrieval | Ch 5 |
| **Behavioral feedback signals** | CTR, dwell time, bounce rate, and explicit negative feedback used to ground LLM-based relevance | Ch 3, Q&A |
| **[[BM25]]** | Best Matching 25 — a probabilistic lexical ranking function based on term frequency and document length; foundational IR algorithm | Ch 1, Ch 2 |
| **Cache patterns** | Tier 1 of reasoning economics; deterministic repeated intents served at ~10ms for near-zero cost | Ch 3, Ch 4 |
| **Chunk collapse** | Degradation in retrieval when chunking heuristics incorrectly split or merge semantically important content | Ch 1 |
| **Composable tools** | Atomic, transparent search functions (keyword search, semantic search) that serve as agent planning primitives | Ch 2 |
| **Confidence curves** | Per-iteration confidence scores tracking retrieval certainty across the reasoning loop | Ch 2 |
| **Convergence rate** | Evaluation metric: number of reasoning loop steps before the system terminates with a result | Q&A |
| **Cross-session memory** | Persistent state across multiple user sessions enabling long-term user modeling | Ch 5 |
| **Distilled models** | Tier 2 of reasoning economics; lightweight models handling simple reasoning at ~50ms | Ch 3 |
| **Domain-specialized agents** | Purpose-built reasoning agents for specific verticals (legal, medical, code) | Ch 5 |
| **Entropy reduction** | Evaluation metric measuring how much uncertainty is removed at each reasoning iteration | Q&A |
| **Failure signal detection** | The system's ability to recognize when a retrieval strategy is ineffective and trigger re-planning | Ch 2 |
| **Flink-based query routing** | Using Apache Flink streams for real-time complexity assessment to route queries to appropriate reasoning tiers | Ch 4 |
| **Full reasoning** | Tier 4 of reasoning economics; complete agentic reasoning at ~500ms and high cost for complex queries | Ch 3 |
| **[[Hybrid relevance scoring]]** | Scoring function combining LLM relevance, behavioral feedback, and human feedback with adaptive weighting | Ch 3, Q&A |
| **Information gain per iteration** | Evaluation metric: quality improvement at each step of the reasoning loop | Q&A |
| **Intent collapse** | When a system reduces complex multi-faceted intent into a single keyword match | Ch 1 |
| **[[Intent-conditioned embeddings]]** | Query embeddings dynamically constructed based on classified user intent; yielded ~35% precision lift | Ch 3 |
| **Intent-specific feature vectors** | Dense representations weighting different attributes based on classified intent (CPU/GPU/mobility) | Ch 3 |
| **KNN latency** | Performance cost of K-nearest-neighbor search in vector retrieval systems | Ch 1 |
| **Lexical brittleness** | Failure mode where keyword-based systems break when user phrasing diverges from indexed vocabulary | Ch 1 |
| **Microservices for reasoning** | Decomposing reasoning into independently deployable services | Ch 5 |
| **Monolithic API** | Single search endpoint with many parameters; brittle for LLM-based agents | Ch 2 |
| **Multi-stage ranking** | Ranking pipeline with multiple scoring passes (candidate generation, re-ranking, final scoring) | Ch 4 |
| **Online optimization** | Framing the agentic search loop as real-time optimization rather than static retrieval | Ch 2 |
| **P5 latency** | 95th percentile latency; production system achieves ~100ms | Ch 4 |
| **Partial intent** | The observation that modern users express incomplete, fuzzy, contextual queries | Ch 1 |
| **Position-normalized click model** | A normalization technique that accounts for position bias in click-through data | Q&A |
| **Probabilistic interpretation space** | Generating multiple disambiguation hypotheses rather than collapsing to a single interpretation | Ch 3 |
| **RAG (Retrieval-Augmented Generation)** | Architecture combining document retrieval with LLM generation; the second stage of search evolution | Ch 1 |
| **Reality querying** | Speculative future where simulation becomes a query primitive and "what if" is computable at scale | Ch 5 |
| **Reasoning artifacts** | Structured outputs from query interpretation (query type, intent, constraints) vs. flat NLU labels | Ch 3 |
| **Reformulation trajectory** | Sequence of query rewrites and associated embeddings across reasoning iterations | Ch 2 |
| **Score distribution predictability** | Property that agent backends must have understandable, consistent score distributions for effective reasoning | Ch 2 |
| **Search paradox** | The better search gets, the less it resembles search; retrieval converges with understanding | Ch 5 |
| **Single-pass agent** | Tier 3 of reasoning economics; standard agentic query at ~200ms and moderate cost | Ch 3 |
| **Strategy diversity** | Evaluation metric: how many distinct retrieval strategies were explored in a reasoning path | Q&A |
| **[[Temporal]]** | Workflow orchestration framework used as the stateful orchestrator for agentic search | Ch 4 |
| **TF-IDF** | Term Frequency-Inverse Document Frequency; classic lexical scoring method | Ch 1 |
| **Tiered reasoning economics** | Cost architecture routing queries to computational tiers (cache/distilled/single-pass/full) based on complexity | Ch 3, Ch 4 |
| **Vector drift** | Embedding representations shifting over time as underlying data distribution changes | Ch 1 |
| **Zero result rate** | Percentage of queries returning no results; 6% in production | Ch 4 |
