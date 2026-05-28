---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/rag
  - topic/retrieval
  - status/growing
---

# RAG Evaluation — Retrieval and Generation, Separately

RAG is NOT dead. The viral "RAG is dead" articles specifically argue against naive vector database retrieval for coding agents. RAG just means "using retrieval to provide relevant context." The core principle is essential.

## The Two-Component Framework

### 1. Retrieval Component (Search Problem)
Evaluate with traditional IR metrics:
- **Recall@k**: Of all relevant documents, how many retrieved in top k?
- **Precision@k**: Of k documents retrieved, how many were relevant?
- **MRR (Mean Reciprocal Rank)**: How high was the first relevant document?

Choose metrics based on your use case. Cross-reference with [[agentic-eval-layers]] Layer 1 (signal fidelity).

#### Creating Retrieval Eval Datasets
Synthetic approach: take documents from corpus → extract facts → generate questions those facts answer. This reverse process gives you query-document pairs without manual annotation.

### 2. Generation Component (LLM Quality)
Standard eval process applies:
- Error analysis identifying failure modes ([[01-error-analysis]])
- Human labels collection ([[03-annotation-and-humans]])  
- LLM-as-judge evaluator building ([[02-eval-design]])
- Judge validation against human annotations

### Jason Liu's "6 RAG Evals" Framework
- Tier 1: IR metrics (retrieval quality)
- Tier 2-3: Question-Context-Answer relationships
  - Context relevance given the question
  - Answer faithfulness to the context
  - Answer actually addresses the question

### Beyond Generic Metrics
Error analysis on YOUR data reveals domain-specific failures:
- Medical RAG failing to distinguish drug dosages by age group
- Legal RAG confusing jurisdictional boundaries
- These won't show up in generic metrics

## RAG Is Not Dead — It's Evolving
- Naive vector similarity search fails for code (complex contextual relationships)
- Modern tools like Claude Code use agentic search instead of just vector DBs
- Available strategies: keyword matching, embedding similarity, LLM-powered filtering, multi-hop retrieval
- "Focus on the ultimate goal: getting your LLM the context it needs to succeed"
- See [[rag-implentations]] for the technique comparison table

## Chunk Size as Hyperparameter

### Fixed-Output Tasks → Large Chunks
- Output length doesn't grow with input (extracting a number, classifying a section)
- Use largest chunk likely containing answer
- Reduces queries, avoids context fragmentation
- Caveat: models are "sensitive to distraction, especially with large inputs" — middle sections get under-attended

### Expansive-Output Tasks → Smaller Chunks
- Output grows with input (summarization, exhaustive extraction)
- Process chunks independently → aggregate (map-reduce pattern)
- Smaller chunks "preserve reasoning quality and output completeness"
- Respect content boundaries (paragraphs, sections, chapters)

### The Real Insight
- "No rule of thumb can perfectly determine the best chunk size"
- Chunk size is a hyperparameter to tune empirically
- Larger chunks = model reasons over more info at once, risks overlooking middle details
- Smaller chunks = model pays full attention to each section, but more queries needed

## Debug Retrieval First
"Debug retrieval first using IR metrics, then tackle generation quality using properly validated LLM judges."

Don't use off-the-shelf LLM-as-judge prompts for RAG eval — same rules apply: error analysis → prompt iteration → labeled examples → measuring judge accuracy.

## For Our Project
- Our search pipeline IS a RAG system: query → multi-source retrieval → LLM scoring → synthesis
- Retrieval eval: measure recall/precision of sources returned per query
- Generation eval: error analysis on synthesized summaries
- Chunk size matters for our document processing — treat as hyperparameter, experiment
- Link to [[agentic-eval-layers]] for the three-layer framework that applies directly

---
See also: [[00-evals-hub]], [[01-error-analysis]], [[agentic-eval-layers]], [[rag-implentations]]
