Speaker: Santoshkalyan Rayadhurgam

## Search Architectures

> **Search systems that were once deterministic and stateless — and "flew brutally light" — now need to behave more like distributed reasoning systems.**

### Evolution
1. Lexical Search Pipelines
	1. [[20-notes/ai/ml-algos/TF-IDF]]/[[BM25]], Static Ranking:
	2. **Synonymy**, **Polysemy**, **Low Recall** -- 
2. Vector-Based RAG Systems
	1. [[Embeddings]], [[20-notes/ai/ml-algos/knn]] Search, LLM
	2. Chunking, Latency, Grounding
3. Autonomous Agentic Search
	1. [[assets/agentic-frameworks|agentic-frameworks]], Tool Orchestration
	2. Non-determinism, Cost, Statefulness


## Static IR (Info Retrieval) Pipelines Collapse Under Ambiguity
- High Ambiguity x High Complexity: **Semantic Fuzziness**
- High Ambiguity x Low Complexity: **Lexical Brittleness**
- Low Ambiguity x High Complexity: **Multi-Intent Collapse**
- Low Ambiguity x Low Complexity: **Zero Session Memory**


## Info Retrieval as an Agentic Process

Agentic Search State (e.g. core structure for an agentic search engine)
``` python
class AgenticSearchState:
	query_id: UUID
	original_query: str
	current_query_embedding: List[float]
	query_reforumulation_history: List[str]
	active_retrieval_strategies: List[str]
	session_confidence_score: float
	result_diversity_metric: float
	
```

the above is a session-local representation of the searchState, that sruvives across tool calls and iterations.
the challenge is how do you enable adaptive strategies, perform failure signal detection, and atomic component updates, or even diversity analysis.

Engineering / System Challenges
- dynamic strategy: adaptive feedback
- persistent context: state serialization
- failure signals: low confidence
- result analytics: diversity metrics
- scalalable transitions: atomic updates

> What we need is a distributed, tasteful, muti-turn controller


## Agentic Search Loop Architecture

> Treat what we're doing fundamentally as a reasoning pipeline. 
We're just converting the query into something more approachable, by reasoning at each iteration.

The Loop:
1. Query Understanding
2. Dynamic Strategy Selection
3. Distributed Retrieval Execution
4. Relevance Assessment
5. Adaptive Strategy Refinement
6. Convergence and Termination

The Query Refinement Pipeline:
- Initial: "Python memory thing" -> high result_entropy.
- Refinement: "Python memory leak detection" -> still high result_entropy, added to failed_strategies.
- Converged: "Python memory profiling article recent" -> High relevance, confidence_history plateaued.

### Stateful Reasoning & Control Loops
- Control loop: query understanding → strategy selection → execution → evaluation → refine/pivot/terminate
- Composable tools > monolithic API (atomic, transparent functions)
- Key insight: **BM25 + agent** > complex neural net without agent — 
	- agents need predictable distribution scores and semantics
	- opaque re-rankers and black-box embeddings makes reasoning difficult for the agents
	- in contrast, transpartent systems like BM25 make the agent hypothesis more accurat, and refinement becomes more feasable as well.
	- takeway: backend favor predictability over sophistication
- Link to: [[Agentic Search State]], [[00-inbox/agentic-search-control-loop]], [[Composable Tools]], [[Score Distribution Predictability]]

### Dynamic Query Understanding
#### Traditional NLP Limitations
- Sequential Pipelines
- Brittleness
- Ambiguity
#### Agentic Query Interpretation
- Initial Query: "Find that Python thing from last week"
- Semantic Parsing: Entitiest
- Domain Classification: Context
- Ambiguity Resolution: Hypothesis
- Temporal Processing: Dates
- Result: Scheduled Query

```json
{
	"query_type": "retrieve_document",
	"keywords": ["Python"],
	"semantic_intent": "programming_resource",
	"temporal_constraint": {"start": "2024-03-04", "end": "2024-03-10"},
	"disambiguation_candidates": ["article", "tutorial", "code_snippet"]
}
```

### Query-Time Content Classification

#### Semantic / Intent-Conditioned Embeddings / Feature Generations
- Query embeddings conditioned on classified intent → ~35% precision lift
- "Laptop for coding" (CPU/RAM in feature vectors) vs "video editing computer" (GPU/display in feature vectors) vs "portable workstation" (mobility in feature vectors)
- Structurally different from document embeddings — these are intent-aware
- Link to: [[Intent-Conditioned Embeddings]], [[Intent-Specific Feature Vectors]]


#### However, interpretation is not enough. Relevance is determined using human feedback.

### LLM-Based Scoring Challenges
- Nuance loss
- No adaptation to drift
- Static Data
- Opaque debugging - not interpretable when it fails
### Hybrid Relevance Scoring
Combine LLM-based scoring + correct model hallucinations + ther feedback

``` 
  final score = (a * S_LLM) + (b * S_CTR) + (y * S_dwell_time) + (z * S_neg_feedback)
```

- LLM relevance: cahced signal
- Behavioral feedback (human): CTR, dwell time 
- Explicity: direct input
- Negative signals: sparse but unambiguous → disproportionate influence, sometimes veto
- Weighting: 
	- A/B, RL tuned
	- Position-normalized click model to correct for position bias
	- Adaptive policy: weights shift across different query regimes
- Link to: [[Hybrid Relevance Scoring]], [[Behavioral Feedback Signals]], [[Negative Signals]], [[Position-Normalized Click Model]], [[Adaptive Policy]]

main things in scoring:
- how are you combining  the diff signals
	- llm relevance - it's a good prior to have but not a proper ground ttruth
	- clicks, dwell time - 
		- high signal, but high variance (good short term indicators for relevance, sensitive to things like personalization, pollution bias)
		- position-normalized click model may help by normalizing some of this
		- if the user says, "this isn't helpful" / does a fast-bounce, that's your negative feedback (low frequency, but extremely high signal and precision)
	- negative signals
		- -ve signals tend to be sparse but they're unambiguous.
- trying to build a multi-objective optimization function over diff kinds of heterogenous signals that we havej.
- how do we think of scoring an adaptive policy that changes as we go?
## Economics of Reasoning
- Tier 1: Cache patterns (~10ms, free-ish)
	- direct lookup
	- key-value stores
- Tier 2: Distilled models (~50ms, inexpensive)
	- low latency/cost
	- smaller llms
	- simple reasoning
- Tier 3: Single-pass agent (~200ms, moderate)
	- single chain
	- lightweight agent
	- moderate complexity
- Tier 4: Full reasoning (~500ms, high cost)
	- multi-loop
	- larger llms
	- complex retrieval
- Most traffic stays in **efficient tiers**; only complex queries get full depth
- Link to: [[Tiered Reasoning Economics]], [[Query Routing]]

## Production Architecture
1. Query Router
	1. routes by complexity
	2. uses Flink
2. Cache Layer
	1. distributed KV stores
	2. caches results (W-TinyLFU)
3. Agent Service
	1. stateful orchestrator → 
	2. orchestrates subagents 
	3. manages shared memory
4. Tool Suit
	1. stateless microservices
	2. agents invoke tools
5. Search Backend
	1. hybrid retrieval (lexical plus vector retrieval) along with multi-stage ranking
6. Results Merger
	1. aggregates results
	2. ranking heuristics
7. Progressive UI
	1. real-time
	2. displays fast path

- Metrics:
	- p50 latency (sub-second response): ~ 100ms P95 latency
	- cost per query (dynamic routing optimized): $0.0003
	- success rate (user satisfaction, A/B tested): 78%
	- zero-result rate (tool error handling): 6%
- Link to: [[Flink Streams]], [[Temporal Orchestrator]], [[Production Metrics]]

## Evaluation
- Not single-hop IR metrics — measure trajectories (like a planning algorithm)
- For measuring the dynanic agentic path, the evaluation metrics to look at:
	- Convergence rate, 
	- Entropy Reduction: information gain per iteration, entropy reduction
	- Quality of Reasoning Path
		- how many steps does the reasoning loop take before termination
		- strategy diversity: how many distrinct strategies were explored (lexical first vs graph first?)
- Combination Evaluation: signal fidelity (from retrieval) → policy quality (from agent path) → system intelligence (joint)
- Link to: [[Convergence Rate]], [[Strategy Diversity]], [[Entropy Reduction]], [[Agentic Eval Layers]]

## Future Horizons
![[assets/Screenshot 2026-04-16 at 5.27.33 PM.png|637]]
- Near-term: multi-turn clarification, cross-session memory, real-time user learning
- Mid-term: domain-specialized agents, micro-services for reasoning, anticipatory search
- Long-term: ambient intelligence — always-available multimodal agents
	- as agents eventually work across all our devices, across all our available context, search becomes more and more conversational, conversations becomes predictive. predictive becomes embedding
- The search paradox: "The better search gets, the less it resembles search"
- Link to: [[future-horizons]]


