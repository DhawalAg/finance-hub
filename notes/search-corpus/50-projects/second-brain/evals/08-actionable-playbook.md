---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/project-plan
  - topic/second-brain
  - status/growing
---

# Actionable Eval Playbook — What We Need to Build

This translates Hamel Husain's eval framework into concrete actions for the second-brain search project.

## What's Real vs What's Jargon

### Build This (Actionable, Consequential)
- **Error analysis practice** — manually review 50-100 search traces before automating anything
- **Binary pass/fail rubrics** per search quality dimension
- **Custom trace viewer** — see the full query → decomposition → retrieval → scoring → synthesis pipeline
- **Failure taxonomy** specific to our search quality problems
- **CI test dataset** — 100+ queries with expected behaviors, run on prompt changes
- **Guardrails** — JSON schema validation on LLM scoring output, hallucinated source detection
- **Prompt versioning in Git** — already natural for our codebase

### Skip This (Industry Jargon / Premature)
- Off-the-shelf eval metrics (BERTScore, ROUGE, generic "quality" scores)
- Vendor eval platforms (too early, too generic)
- Eval-driven development (we can't predict what will break)
- Automated prompt optimization (need manual understanding first)
- Complex LLM-as-judge setups (overkill before we have labeled data)
- Likert scale ratings (binary is better)

## Phase 1: Foundation (Build During MVP — Milestones A1-A3)

### Trace Logging
Every search query produces a trace:
```
{
  query: "original user query",
  decomposition: ["sub-query-1", "sub-query-2"],
  sources: { brave: [...], github: [...] },
  scoring: { model: "...", rubric: "...", scores: [...] },
  synthesis: "final output",
  metadata: { latency_ms, tokens_used, model_id, timestamp }
}
```
Log to JSON files. No database needed yet.

### Manual Error Analysis Sprint
After A1 (single-source search) is working:
1. Run 50 diverse queries through the pipeline
2. Open-code each result: what's wrong? what's good? what's surprising?
3. Axial code: group failures into categories
4. Expected categories (guesses — let data confirm):
   - Retrieval misses (relevant result not found)
   - Retrieval noise (irrelevant results ranked high)
   - Scoring miscalibration (LLM scores don't match our judgment)
   - Synthesis hallucination (claims not supported by retrieved sources)
   - Query decomposition failures (wrong sub-queries generated)
5. Count and prioritize

### Binary Eval Rubric (Per Search Result)
Define after error analysis, but likely dimensions:
- [ ] Source is accessible (URL works, content loads)
- [ ] Source is relevant to the query intent
- [ ] Source contains substantive information (not just a landing page)
- [ ] LLM score aligns with human judgment
- [ ] Synthesis accurately represents source content

## Phase 2: Automation (After Error Analysis — Milestone A3+)

### CI Test Dataset
- Start with 50 golden queries from manual review, grow to 100+
- Each query has: expected source types, minimum relevance threshold, known failure cases
- Run on every prompt change (scoring rubric, decomposition prompt, synthesis prompt)
- Assertions: mostly deterministic (JSON schema valid, sources present, no empty results)

### Guardrails (Inline)
- LLM scoring output must be valid JSON matching Zod schema (already planned)
- Source URLs must be real (basic HTTP HEAD check)
- Synthesis must reference at least one retrieved source
- These are fast, deterministic, non-controversial

### LLM-as-Judge (Async, Later)
- Only after we have 100+ manually labeled results
- Validate judge against our own labels (TPR/TNR)
- Use for: relevance scoring validation, synthesis quality assessment
- Start with most capable model, optimize cost later

## Phase 3: Production Monitoring (When Users Exist)

### Sampling Strategy
- Random sample of search sessions for review
- Flag outliers: unusually long latency, many retries, empty results
- Stratify by query type (discovered through error analysis)
- Feed new failures back into CI test dataset

### The Feedback Loop
Production failure → error analysis → new failure category → new evaluator → CI regression test → prevented in future

## What We Learn from [[agentic-eval-layers]]
Our search pipeline maps to the three layers:
1. **Signal fidelity**: Are Brave/GitHub/X returning relevant results? (IR metrics: recall@k, precision@k)
2. **Policy quality**: Is the query decomposition agent making good decisions? Is it picking the right sources?
3. **System intelligence**: Does the end-to-end pipeline satisfy the user's information need?

Evaluate layer by layer. Don't skip to layer 3.

## Key Decisions Already Made By This Analysis
1. Error analysis BEFORE building eval infrastructure
2. Binary pass/fail, not Likert scales
3. Custom trace viewer, not vendor platform
4. Prompts in Git
5. Guardrails for objective checks, evaluators for subjective quality
6. Build evaluators only for persistent failure modes discovered through error analysis

---
See also: [[00-evals-hub]], [[01-error-analysis]], [[04-rag-evals]], [[05-agentic-evals]], [[up-next]]
