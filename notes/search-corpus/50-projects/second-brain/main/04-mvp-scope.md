---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---

# Second Brain — MVP Scope

> What we build first, what we defer, and how we know if it works.
>
> **Current status (April 2026):** Ready to build A1 (single-source search). See [[#8. Search-First Build Path]].

---

## 1. MVP Definition

*Note: This ingestion MVP is now Phase B of the build plan. The search flow (section 8) ships first. Everything below remains the scope for the ingestion phase — it is deferred, not dropped.*

The MVP is a command-line system that ingests a markdown note, extracts atomic claims from it, classifies how those claims relate to existing claims in a SQLite store, and surfaces conflicts. That is the entire scope. It is not a search engine, not a knowledge graph browser, not a content pipeline, not a web app, and not a daily briefing system. It is the smallest possible system that answers the foundational question from [[50-projects/second-brain/main/01-vision]]: can an LLM reason about knowledge *state*, not just retrieve content? If claim extraction plus relationship classification works reliably, there is a product underneath everything else in the [[50-projects/second-brain/main/05-roadmap]]. If it does not, no amount of search, UI, or memory will compensate.

---

## 2. The Thesis Test (Week 0)

Before writing application code, validate the core premise with a manual experiment. This is the gate: if it fails, the structured knowledge model thesis is wrong and the project pivots or stops.

### Steps

1. **Select notes.** Pick 10-15 notes from the vault. Include variety: daily notes, clippings, project docs, literature notes. At least 3 domains (AI, product, recruiting).
2. **Extract claims by hand.** Read each note. Write out every atomic, testable proposition. Force a working definition of "claim" — see [[50-projects/second-brain/main/02-architecture#Level 1: Claims]] for the schema, but the ontology document (what counts, what does not, with 20+ real examples) is the actual deliverable here.
3. **Create labeled pairs.** From the extracted claims, build 30-50 pairs with hand-labeled relationship types: supports, contradicts, extends, qualifies, supersedes. Include ~10 pairs with no meaningful relationship (negative examples).
4. **Run LLM classification.** Feed each pair to Claude (API) and at least one Ollama model. Use a structured output prompt that returns relationship type + confidence + one-sentence reasoning.
5. **Score results.** Compute precision and recall per relationship type, per model. The target is >=65% overall accuracy on the 5-class taxonomy. Track per-class performance — if "contradicts" is reliable but "qualifies" is noise, that is a usable signal.
6. **Document the ontology.** Publish the claim definition with 20+ real examples from the vault, covering inclusions (testable propositions, data points, causal assertions) and exclusions (opinions without stakes, instructions, summaries, vague hedges).
7. **Write up results.** Publishable regardless of outcome. "It worked" and "it failed, here's why" are both valid posts.

### Week 0 Outputs

- Claim ontology document with 20+ examples
- Labeled dataset: 30-50 claim pairs with ground-truth relationships
- Evaluation prompts used for classification
- Results writeup (accuracy per model, per relationship type, failure analysis)
- Go/no-go decision for the MVP build

### Kill Criteria

- Below 50% overall accuracy after prompt iteration across all models tested: **kill the structured approach.** Pivot to simpler retrieval or stop.
- Between 50-65%: proceed with a reduced relationship taxonomy (collapse to 3 types: supports, contradicts, related) and re-test.
- At or above 65%: proceed to MVP build.

---

## 3. MVP Scope Table

| IN (build this) | OUT (defer this) |
|---|---|
| Claim extraction from a single markdown file | Batch ingestion across vault directories |
| SQLite schema for claims, relationships, sources | Vector store / embeddings |
| Relationship classification against top-N existing claims by text similarity | Semantic similarity via embeddings for claim matching |
| Conflict surfacing: list contradictions found during ingestion | Conflict resolution or belief revision (Loop 4) |
| Confidence scores on relationships (LLM-assigned) | Confidence propagation across the graph |
| Basic observability: JSON log of every LLM call, tool invocation, timing | Trace viewer, cost dashboard, OpenTelemetry export |
| CLI entry point: `brain ingest <file>` | `brain search`, `brain brief`, `brain assess`, `brain status` |
| Eval harness: run ingestion against the Week 0 labeled dataset, report accuracy | Automated regression suite, CI integration |
| Single-agent loop with tool registry (3 tools: read-file, extract-claims, classify-relationship) | Context window management, compression, multi-turn memory |
| Provider abstraction: Claude API + one Ollama model | Full model routing, intent-based model selection |
| Claim ontology document with real examples | Cluster computation, knowledge state assessment, depth bars |

---

## 4. MVP User Story

One flow. End to end. No branches.

```
User runs:  brain ingest ./20-notes/ai/llms/prompt-engineering.md

1. Agent reads the markdown file.
2. Claim extractor produces 3-7 atomic claims with evidence type,
   assertion strength, and topic tags.
3. For each new claim, the system retrieves the top 5 most similar
   existing claims from SQLite (text similarity, not embeddings).
4. Relationship classifier evaluates each (new claim, existing claim)
   pair. Returns: relationship type, confidence, one-sentence reasoning.
5. Results are written to SQLite: new claims stored, relationships stored.
6. Agent prints a summary to stdout:
   - Claims extracted (count + list)
   - Relationships classified (count by type)
   - Conflicts found (if any, with the contradicting claims and reasoning)
7. Every step is logged to a JSON trace file.
```

The user story is complete when a note goes in, claims come out, relationships are classified, conflicts are surfaced, and the trace file proves the system did what it says it did.

---

## 5. Definition of Done

The MVP is complete when all of the following are true:

- [ ] **Claim extraction F1 >= 70%** against the hand-labeled Week 0 dataset. Measured as: of the claims the system extracts, what fraction match a human-labeled claim (precision), and of the human-labeled claims, what fraction does the system find (recall).
- [ ] **Relationship classification accuracy >= 65%** on the Week 0 labeled pairs, when run through the full ingestion pipeline (not just raw prompting). This must improve on, or at minimum match, the Week 0 baseline.
- [ ] **Conflict surfacing works on real data.** Ingest 20+ notes from the vault. The system surfaces at least 1 genuine contradiction the author was not previously aware of.
- [ ] **Observability is present.** Every ingestion run produces a JSON trace with: timestamp, file ingested, claims extracted (with text), relationships classified (with types and confidence), LLM calls made (model, tokens in/out, latency).
- [ ] **The eval harness runs.** A single command (`bun test` or equivalent) runs the ingestion pipeline against the labeled dataset and prints precision, recall, and accuracy.
- [ ] **SQLite schema is populated and queryable.** After ingesting 20+ notes, a user can run SQL queries against the claims and relationships tables and get coherent results.
- [ ] **The claim ontology document exists** with 20+ real examples and clear inclusion/exclusion rules, and it has been tested against at least 3 note types.

---

## 6. What We Learn

The MVP is a bet. It answers specific questions.

### If the answer is "yes" (thesis holds)

| Question | Implication |
|---|---|
| Can the LLM extract claims reliably from heterogeneous vault notes? | Claim extraction is a real module, not a demo. Proceed to [[50-projects/second-brain/main/05-roadmap#Phase 2]] (search). |
| Can the LLM classify relationships at >= 65% accuracy in a pipeline context? | The knowledge model is viable. Reasoning loops can build on it. |
| Does text-similarity retrieval surface relevant existing claims for comparison? | Embeddings are an optimization, not a prerequisite. Search (Phase 2) can be deferred. |
| Do real conflicts exist in the vault, and can the system find them? | The "knowledge state" thesis has user-visible value, not just architectural elegance. |

### If the answer is "no" (thesis fails)

| Failure mode | Response |
|---|---|
| Claim extraction precision < 60% — too many hallucinated claims | Tighten the ontology. Require verbatim evidence spans. Try source-grounded extraction. If still noisy after 2 iterations, the claim abstraction layer is not viable with current models. |
| Relationship classification < 50% — the 5-class taxonomy is too fine | Collapse to 3 classes (supports, contradicts, related). Re-test. If 3-class is also below 50%, the structured relationship approach does not work. |
| No real conflicts found in 20+ notes | The vault may lack genuine contradictions, or the system cannot distinguish contradiction from nuance. Test with synthetic contradictions to isolate. If synthetic contradictions are missed, the classifier is broken. |
| Latency > 30 seconds per note — unusable as a workflow tool | Profile LLM calls. Reduce claim-pair comparisons (top-3 instead of top-5). Try smaller/faster models for initial filtering. If still slow, ingestion must be async. |

---

## 7. Anti-scope

Things that are tempting, adjacent, and explicitly not in the MVP. Each has a reason.

| Temptation | Why not now |
|---|---|
| **Web search / URL ingestion** | Adds input complexity before the core pipeline is proven. Markdown files are the only input surface for MVP.[^1] |
| **Web UI / Lattice views** | Visualization without a proven data model is decoration. CLI output is sufficient to validate. |
| **Vector embeddings / semantic search** | An optimization for claim retrieval. Text similarity (BF or BM25 over claim text) is good enough to test relationship classification. Embeddings are [[50-projects/second-brain/main/05-roadmap#Phase 2]]. |
| **Memory / session persistence** | The MVP is stateless between runs (except SQLite writes). Cross-session memory is [[50-projects/second-brain/main/05-roadmap#Phase 4]]. |
| **Daily briefings / proactive surfacing** | Requires Loop 3 (Knowledge State Assessment) and sufficient claim volume. [[50-projects/second-brain/main/05-roadmap#Phase 4]]. |
| **Prompt templates for external distribution** | Extracting shareable artifacts is a Phase 2+ activity. Build the private tool first. |
| **Multi-model routing** | One Claude model + one Ollama model. Intent-based routing is complexity that does not serve the thesis test. |
| **Cluster computation / depth bars** | Requires hundreds of claims. The MVP will have tens. Premature. |
| **Belief revision (Loop 4)** | Requires conflict volume and user trust in the system. Post-MVP. |
| **Confidence propagation** | Requires a populated graph. Assign confidence per-relationship in MVP; propagation is Phase 3. |
| **Batch ingestion / vault-wide crawl** | One file at a time. Batch is an operational convenience, not a thesis validator. |
| **BM25-from-scratch package** | Educational and shareable, but not needed to prove the thesis. Build it when search is the focus (Phase 2). |

---

## 8. Search-First Build Path

**Strategic pivot (April 2026):** Build outside-in. The original plan assumed ingestion first — prove the knowledge model, then layer search on top. Three design sessions flipped this. The search experience is the first thing a user touches, and it delivers value before a single claim is extracted. The knowledge model fills through use, not through a batch import phase nobody will finish.

The ingestion MVP (sections 1-7 above) is not abandoned. It becomes Phase B — the second build phase, after search proves the UX and gives the knowledge model a reason to exist.

### Build Chunks

| Chunk | What | Done when |
|---|---|---|
| **A1: Single-source search** | CLI scaffolding (`brain search <query>`). Brave Search API integration. Raw results table to stdout. | User types a query, gets a ranked results table from Brave. CLI is installable and the provider abstraction exists. |
| **A2: Multi-source fan-out** | Add GitHub and Twitter/X sources. Query decomposition via OpenRouter — one user query becomes source-appropriate sub-queries. | Fan-out runs in parallel. Results merge into a single table with source column. Query decomposition prompt is versioned. |
| **A3: LLM scoring columns** | Add relevance, recency, and depth columns. Each scored by LLM with rubric-anchored prompts (not vibes). | Columns appear in output. Rubrics are documented. Scoring is deterministic enough that re-running the same query produces stable rankings. |
| **A4: Vault cross-reference** | Novelty column: `NEW` / `IN VAULT` / `PARTIAL`. Each search result is checked against vault content. | User can see at a glance what they already know vs. what is genuinely new. False-positive rate on `IN VAULT` is tolerable (< 30%). |
| **A5: Interactive REPL** | Session mode with commands: `compare`, `skim`, `queue`, `refine`. Conversational search refinement. | User can enter a session, refine a search, queue results for later processing, and compare two results side-by-side. Session state persists within a run. |

### Sequencing rationale

A1-A2 deliver a usable multi-source search tool in days. A3 adds the LLM layer that differentiates this from raw API calls. A4 is where the vault starts to matter — this is the bridge to the knowledge model. A5 makes it a workflow, not a one-shot command.

After A5, the ingestion MVP (sections 2-7) becomes the next build phase. By then, the search flow has generated enough real usage to know which claims matter and which vault gaps are worth filling.

See [[2026-04-18-search-flow-chunked-v1]] for full design details.

[^1]: Web search is deferred from the *ingestion* MVP (sections 1-7) but is addressed in [[#8. Search-First Build Path]], where Brave Search API integration ships as chunk A1. The anti-scope entry here applies to ingestion inputs only — external web sources enter the system through the search flow, not the ingestion pipeline.

---

## Related Documents

- [[50-projects/second-brain/main/01-vision]] — project identity and success criteria
- [[50-projects/second-brain/main/02-architecture]] — system layers and knowledge model schema
- [[02-steelman-and-reframe]] — the critique that sharpened this scope
- [[50-projects/second-brain/main/03-tech-stack]] — technology decisions
- [[50-projects/second-brain/main/05-roadmap]] — full phased execution plan
- [[00-master-plan]] — original master plan (superseded in parts)
- [[2026-04-18-search-flow-chunked-v1]] — search-first build plan (A1-A5 chunk details)
