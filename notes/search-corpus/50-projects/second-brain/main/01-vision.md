---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---

# Second Brain — Vision & Build Manifest

> A locally-deployed autonomous intelligence layer over an Obsidian vault that reasons about what you know, not just what you've saved.

---

## One-Liner

Second Brain is a personal knowledge agent that maintains a structured model of your understanding — claims, relationships, confidence, gaps — and uses it to reason about your knowledge state over time.

---

## The Bet

Stated as a falsifiable hypothesis:

**An LLM operating over a structured knowledge model (claims + typed relationships + confidence scores) can reason about knowledge *state* — depth, conflicts, gaps, epistemic habits — in ways that are measurably better than retrieval-augmented generation over raw notes.**

The test: given 10-15 notes from this vault, can the system classify relationships between extracted claims at >=65% accuracy? If yes, every downstream feature has a foundation. If no, this is just a fancy grep wrapper and should be killed.

See [[50-projects/second-brain/main/05-roadmap#Phase 0: Thesis Test (Week 0)]] for the concrete experiment.

---

## Identity

### What this IS

- A working agent on one person's machine, for one person's vault
- A personal tool, built in public — the private agent is the source, public artifacts are extracted from it
- A single-agent system (not multi-agent) — research consistently shows single-agent matches or beats multi-agent at equal token budgets
- Local-first: data stays on this machine, models run via Ollama or API
- Model-agnostic: works with local models (Ollama) and cloud APIs (Claude, OpenAI)
- An opinionated bet that knowledge *structure* enables reasoning that raw text cannot

### What this is NOT

- Not a product. Not a platform. Not something other people install.
- Not a RAG wrapper with a nice UI
- Not a multi-agent orchestration system
- Not a note-taking app or a replacement for Obsidian
- Not a startup — there is no GTM, no pricing, no onboarding flow
- Not dependent on any single model provider

The boundary is sharp: this is a **private instrument** that happens to produce **public artifacts**. The agent is never shipped. The learnings always are.

---

## Guiding Principles

### 1. Inside-Out

Each layer proves itself before the next layer builds on it. Claim extraction works before reasoning depends on it. Reasoning works before the UI visualizes it. No layer gets built on faith that the layer below will eventually work.

### 2. Ship Small, Ship Often

Every 2-3 week phase ends with at least one public artifact — a package, a prompt template, a blog post. If a phase produces nothing shippable, the phase is scoped wrong. The cadence is the accountability mechanism.

### 3. Eval-First

The Week 0 test set is not a throwaway exercise. It becomes the eval baseline every subsequent module is measured against. Evaluation is not a phase — it is embedded in every phase from the start. Each module ships with a test harness. See [[50-projects/second-brain/main/05-roadmap]] for how this cascades through the build sequence.

### 4. Personal-Then-Extract

Build for the private use case first. Generalize only when extracting a public artifact. The agent itself is never designed for portability — the packages, templates, and posts extracted from it are. This ordering prevents the most common failure mode: building infrastructure for users who don't exist.

### 5. Local-First, Cloud-Optional

The system runs entirely on a local machine. Cloud APIs (Claude, OpenAI) are optional accelerators, not dependencies. Every core capability must work with Ollama. If it can't run offline, it's a feature, not a foundation.

### 6. Structure Over Retrieval

The moat is the knowledge model — not the search index, not the embedding space, not the LLM. Claims, typed relationships, and confidence scores are the primitives. Every feature that doesn't build on or feed into this model should be questioned. RAG is a baseline to beat, not a design to adopt.

### 7. Observe Everything

Every agent action — tool calls, reasoning steps, token usage, latency, eval scores — is logged and queryable. Observability is not a Phase 5 add-on. It ships with the agent loop in Phase 1. You cannot improve what you cannot see.

---

## The Three Output Channels

Second Brain is one project with three distinct output surfaces:

### Channel 1: The Private Agent

The working system. Runs on this machine, operates on this vault. This is the source of truth — where ideas are tested, where the knowledge model lives, where the evals run. Never published. Never packaged for others.

### Channel 2: Extracted Packages

Modules pulled out of the private agent and published as standalone, reusable code:

- `core-agent-loop` — single-agent loop with tool registry and context management
- `claim-extractor` — extract atomic claims from unstructured text
- `bm25-from-scratch` — BM25 search implementation, no dependencies
- `hybrid-search` — BM25 + vector fusion with configurable weighting
- `relationship-classifier` — classify semantic relationships between claims
- `agent-trace-viewer` — observability UI for agent execution traces

Each package is self-contained. No dependency on the private agent's infrastructure.

### Channel 3: Prompt Templates and Writing

Portable knowledge artifacts that don't require code:

- **Prompt template bundles** — tested, versioned prompt sets for claim extraction, relationship classification, knowledge assessment, gap analysis
- **Blog posts** — one per phase, documenting what was built, what worked, what didn't
- **The build narrative** — the meta-story of building a knowledge agent, published as it unfolds

The extraction rule: if it requires access to the private vault or the SQLite store, it stays in Channel 1. If it works on any text, it moves to Channel 2 or 3.

---

## Success Criteria

### Month 1 — "The thesis holds"

- [ ] Phase 0 complete: relationship classification accuracy >=65% on the test set
- [ ] Phase 1 in progress: agent loop runs, executes tools, logs traces
- [ ] Claim extraction works on 5+ note types (clippings, daily notes, project docs)
- [ ] First blog post published
- [ ] Eval harness exists and runs on every commit

**Kill signal:** If relationship classification is below 50% after prompt iteration, the structured knowledge model thesis is wrong. Pivot to a simpler retrieval-based approach or stop.

### Month 3 — "It's useful daily"

- [ ] Search works: hybrid BM25 + vector search returns relevant results from the vault
- [ ] The knowledge model has 500+ claims with typed relationships
- [ ] Conflict detection surfaces at least one real contradiction the user didn't know about
- [ ] CLI exists: `brain search`, `brain ingest`, `brain status` are functional
- [ ] 3+ packages published, 2+ blog posts shipped
- [ ] Prompt template bundle v1 released

**Kill signal:** If the agent's knowledge-state reasoning is not noticeably better than "grep + Claude" after 3 months, the structured approach isn't earning its complexity cost.

### Month 5 — "It compounds"

- [ ] The agent proactively surfaces insights without being asked (daily briefing, conflict alerts)
- [ ] Knowledge assessment works: the system can describe depth, gaps, and confidence across topics
- [ ] Observability dashboard shows agent behavior patterns over time
- [ ] Web UI (Lattice view) renders the knowledge graph, depth map, and conflict view
- [ ] 5+ packages published, 4+ blog posts shipped
- [ ] At least one external person has used an extracted package or template for their own project

**Kill signal:** If the agent is not part of the daily workflow by month 5 — if it's a project being *maintained* rather than a tool being *used* — something is fundamentally wrong with the value proposition.

---

## Related Documents

- [[00-master-plan]] — original master plan (superseded in parts by this doc and the reframe)
- [[02-steelman-and-reframe]] — critical review that sharpened the project identity
- [[50-projects/second-brain/main/02-architecture]] — system architecture and layer design
- [[50-projects/second-brain/main/05-roadmap]] — phased execution plan with concrete deliverables
