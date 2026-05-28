---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
ground-truth: true
parent: "[[00-master-plan]]"
---

# Steelman Review & Strategic Reframe

> A critical review of the master plan and user flow, followed by the strategic pivot that emerged from it. This document captures the reasoning that led to the project's sharpened identity: **a personal knowledge agent, built in public.**

---

## Part 1: The Steelman — Five Pushbacks

Reviewing [[00-master-plan]] and [[01-user-flow-v0]] as a skeptical staff engineer would review a PRD.

---

### Pushback 1: "Your knowledge model is the product, but it has no spec"

Everything hinges on **claims, relationships, and confidence scores**. That's the entire moat — the reason this isn't just a wrapper around Claude + grep. But across both documents, the knowledge model is described at the vibes level:

- "Extract atomic claims" — what constitutes a claim? Is "Mastra has 23k stars" a claim? Is "Mastra is the best TS agent framework" a claim? Are opinions claims? Are instructions claims?
- "Classify relationships: supports, contradicts, extends, qualifies, supersedes" — five categories. The original [[50-projects/lattice/09-agentic-loops|Lattice docs]] had a richer taxonomy. Is this final or placeholder?
- "Confidence scores" — on what scale? Assigned how? By the LLM? By the user? Calibrated against what?

**Why it matters:** The quality of every downstream feature — conflict detection, gap analysis, knowledge assessment, the depth bars in the UI — is bounded by the quality of claim extraction. If claim extraction is noisy (and it will be, especially on local LLMs), every layer above it shows the user garbage dressed up in nice progress bars.

**What to do:** Before writing any code, `L0-data-schema.md` must define what a claim IS, with 20+ real examples from this vault. Not the SQLite DDL — the *ontology*. This is the Lattice Week 1 validation ("can the LLM classify relationships at ≥65% accuracy?") that was designed months ago and never executed. Still the right first step. Still not done.

---

### Pushback 2: "You're building a search engine, a knowledge graph, a note-taking tool, and a content pipeline — pick one"

Count the verbs in the user flow: search the web, search GitHub, search HuggingFace, search the vault, extract claims, classify relationships, compute confidence, detect conflicts, assess depth, generate placement plans, merge notes, create notes, track memory, produce briefings. That's not an MVP. That's a platform roadmap masquerading as a v0.

The user flow doc acknowledges this with Inflection Point #5 ("do we build all three modes?") but then sidesteps it. The master plan's build sequence does the same — Phase 2 covers ingestion AND search AND BM25 AND vector embeddings AND hybrid fusion in 3 weeks.

**What to do:** Identify the **one thing** that, if it works, proves the thesis. The original Lattice bet was: "Can an LLM reason about knowledge *state*, not just retrieve content?" That's still the sharpest bet. Test it in isolation before building anything else.

Concretely: take 10 notes from the vault. Manually extract claims. Feed claim pairs to the LLM. Can it classify relationships reliably? If yes, there's a product. If no, the search UX and the absorption pipeline and the CLI are all dressing on a broken salad. Run that experiment before building anything else.

---

### Pushback 3: "The 'dual-surface' principle is a trap"

Principle #5 in [[00-master-plan]] says skills work both inside the app AND as standalone files in Claude Code/Wibey. This sounds elegant but creates a constraint that slows down every decision:

- **Inside the app**, a skill like `extract-claims` has access to the SQLite claim store, the vector index, the full knowledge graph. It writes structured output to a database.
- **In Claude Code**, that same skill has access to the filesystem. That's it. No SQLite, no vectors, no knowledge graph.

So either skills are dumbed down to work without infrastructure (in which case, what's the app for?), or there are two versions of each skill (in which case, "dual-surface" is really "double the maintenance").

**What to do:** Separate these cleanly:

| What | Description | Distribution |
|------|-------------|-------------|
| **App modules** | Code packages with full infrastructure access | npm packages, used inside the agent |
| **Prompt templates** | Markdown files that tell an LLM how to think | GitHub repo, usable in any coding agent |

They're related but not the same artifact. A prompt template might be *inspired by* an app module, but it shouldn't be constrained to be the same thing.

---

### Pushback 4: "Evaluation is at the end — it should be at the start"

The build sequence in [[00-master-plan]] goes: foundation → ingestion + search → reasoning → CLI → observability + web UI. Evaluation appears in Phase 5 (weeks 15-20) as "eval framework: measure quality of each module."

But evaluation isn't a Phase 5 bolt-on. It's the thing that tells you whether Phases 2 and 3 actually work. Without evals:

- How do you know claim extraction isn't hallucinating claims that aren't in the source?
- How do you know the relationship classifier isn't defaulting to "supports" 80% of the time?
- How do you know hybrid search ranking is better than just BM25 alone?
- How do you know the "depth" bar in the UI means anything?

The [[50-projects/ai-observability/00-project-brief|AI Observability project brief]] already identified this gap: "Evals test outputs but don't connect to root causes."

**What to do:** Pull evaluation into Phase 1. Not a fancy framework — just a test set. 20 notes, manually labeled with claims and relationships. Run modules against them. Measure precision and recall. This is the "validate LLM relationship reasoning at ≥65% accuracy" task from Lattice Week 1, and it belongs at the start.

---

### Pushback 5: "Personal tool or general tool — you can't defer this"

The master plan says "locally-deployed autonomous intelligence layer over **my** Obsidian vault." The user flow describes a generic user toggling between chat and search modes. The shareable artifacts table imagines npm packages and "a tool anyone can point at their own vault."

These are different products:

- **Personal tool:** Optimized for this vault's structure (`00-`, `10-`, `20-` prefixes, specific tag taxonomy). Can hardcode assumptions. Doesn't need onboarding.
- **General tool:** Must handle arbitrary vault structures. Needs configuration. Must degrade gracefully when conventions are absent.

Designing the general tool but building with personal-tool urgency creates tension. "Ship small" says release early, but releasing a tool that only works with one specific vault structure isn't useful to anyone.

**What to do:** Be explicit — this is a personal tool first. The shareable artifacts are *components extracted from it*, not the tool itself. The CLI can be "here's how I built my second brain" (a learning artifact), not "here's a second brain for everyone" (a product).

---

## Part 2: The Reframe

The five pushbacks converge on a single strategic shift.

### Before → After

| Before (implicit) | After (explicit) |
|---|---|
| Build a platform, extract shareable pieces | Build **my** agent, extract shareable pieces |
| App should work for anyone | App works for me; extracted tools work for anyone |
| Skills must work in both app and standalone | App modules are code; standalone skills are prompts. Related but separate. |
| Ship the CLI as a general-purpose tool | Ship the CLI as a reference implementation + learning artifact |
| Eval at the end | Eval from day one — the 20-note test set |
| Knowledge model is implicit | Knowledge model is the FIRST thing to spec, test, and write about |

### The Sharpened Identity

> **A personal knowledge agent, built in public.**

Not a platform. Not a product for others. A working agent on my machine, for my vault, that I build incrementally — extracting useful pieces and documenting the journey along the way.

---

## Part 3: The Three Output Channels

The app itself is private infrastructure. What gets shared are the outputs:

```
MY PRIVATE AGENT (the app)
│
├── runs on my machine, my data
├── optimized for MY vault, MY conventions
├── doesn't need to be general-purpose
│
│   extracts from it:
│
├──► STANDALONE PACKAGES (code)
│    Small, focused libraries anyone can use
│    Examples: claim-extractor, bm25-from-scratch, agent-trace-viewer
│    Distribution: npm / GitHub repos
│
├──► PROMPT TEMPLATES (markdown)
│    Drop-in files for Claude Code, Wibey, Cursor
│    Examples: analyze-notes, find-conflicts, gap-analysis
│    Distribution: GitHub repo, skill registries
│
└──► WRITING (content)
     "Here's what I learned building X"
     Each artifact gets a companion post
     Distribution: Substack, X/Twitter, LinkedIn, dev.to
```

**The crucial distinction:** The app doesn't need to be general or polished. It's the workshop. The tools extracted from the workshop are what get shared. This eliminates the "personal tool vs. general tool" tension entirely.

---

## Part 4: Why "Build in Public" Works for Credibility

### 1. Frequency beats magnitude

Shipping one small thing every 2-3 weeks beats shipping one big thing after 5 months. Stay visible, build a body of work, demonstrate consistency.

### 2. Opinions beat abstractions

"Here's how I extract claims from markdown and why I chose this approach" is more interesting than "here's a configurable extraction framework." People follow builders who have a point of view.

### 3. Learning artifacts are more honest

"I tried X, it didn't work, here's why, here's what I did instead" is the content that resonates in the AI space right now. Nobody's an expert on agent knowledge models in 2026. Being the person who documents the exploration is the play.

### 4. Compounding

By month 3-4, there are 5-6 published things. Someone stumbles on the BM25 post, sees the claim extractor, the skills bundle, the trace viewer. Each piece makes the others more credible. The portfolio tells a story: this person builds, ships, and thinks clearly about hard problems.

---

## Part 5: The Reoriented Build Sequence

Same architecture as [[00-master-plan]], different priorities and framing.

### Week 0: The Thesis Test (THIS WEEK)

**Goal:** Answer the foundational question before writing any application code.

- [ ] Pick 10-15 notes from the vault
- [ ] Manually extract claims from them (by hand — this forces a definition of what a claim IS)
- [ ] Feed claim pairs to Claude / Ollama — can it classify relationships reliably?
- [ ] Document the results: what worked, what didn't, what surprised you
- [ ] Write up the results as a publishable piece

**Ship:** Blog post: "Can an LLM reason about knowledge state? I tested it." + the test dataset + the prompts used.

**Why this is first:** If relationship classification doesn't work reliably, we know early and adjust. If it does, we have the first published piece AND validation that the project has legs. The post is interesting regardless of outcome — "it worked great" and "it failed, here's why" are both publishable.

### Weeks 1-3: Core Loop + Claim Extraction

**Goal:** A working agent that can read files and extract claims.

- [ ] Build the agent loop (evolve from [[50-projects/agentic-loop-v1/single-agent-harness|agentic-loop-v1]])
- [ ] Build claim extraction as the first module
- [ ] Run it against the Week 0 test set, measure accuracy
- [ ] Basic observability: log every step to JSON

**Ship:** `claim-extractor` package + blog post: "Building an agent loop from scratch"

### Weeks 4-6: Search + First Prompt Templates

**Goal:** The vault becomes queryable. First standalone shareable artifacts.

- [ ] BM25 search over vault content
- [ ] Vector embeddings (local model via Ollama)
- [ ] Hybrid search: BM25 + semantic with simple fusion
- [ ] Wire search into agent as tools
- [ ] First standalone prompt templates: `analyze-notes`, `extract-claims` (markdown files for coding agents)

**Ship:** `bm25-from-scratch` package + prompt template bundle v1 + blog post: "What I learned about hybrid search"

### Weeks 7-10: Reasoning + Conflict Detection

**Goal:** The agent can reason about knowledge state — the core thesis in code.

- [ ] Relationship classification between claims (the module version of the Week 0 experiment)
- [ ] Conflict detection across the vault
- [ ] Confidence scoring and propagation
- [ ] Knowledge state assessment (the depth/coverage/diversity bars from [[01-user-flow-v0]])
- [ ] More prompt templates: `find-conflicts`, `gap-analysis`

**Ship:** `relationship-classifier` package + prompt templates v2 + blog post: "How my agent detects what I don't know"

### Weeks 11-14: CLI + Memory

**Goal:** A usable interface. The agent remembers across sessions.

- [ ] CLI tool: `brain` command with subcommands
- [ ] Session memory: what was asked, what changed
- [ ] Daily/weekly briefing generation
- [ ] More prompt templates: `weekly-briefing`, `vault-health`, `daily-digest`

**Ship:** `brain` CLI (open-source, reference implementation) + prompt templates v3

### Weeks 15-20: Observability + Web UI

**Goal:** Full visibility into what the agent does. The Lattice vision realized.

- [ ] Trace collection and viewer
- [ ] Cost dashboard
- [ ] Web UI with the three views (What You Know, Conflicts, Gaps)
- [ ] Eval framework (formalized version of the Week 0 test set approach)

**Ship:** `agent-trace-viewer` + web app v0.1

---

## Part 6: What This Looks Like at Month 5

If the cadence holds — one artifact + one post every 2-3 weeks:

```
Published body of work:

 1. "Can an LLM reason about knowledge state?" (blog + test dataset)
 2. claim-extractor (package)
 3. "Building an agent loop from scratch" (blog + code)
 4. bm25-from-scratch (package + blog)
 5. Prompt template bundle v1: analyze-notes, extract-claims (GitHub)
 6. "What I learned about hybrid search" (blog)
 7. relationship-classifier (package)
 8. Prompt template bundle v2: find-conflicts, gap-analysis
 9. "How my agent detects what I don't know" (blog)
10. brain CLI v0.1 (open-source, reference implementation)

Plus: a working personal knowledge agent running on the vault
```

That's a body of work. That's what a hiring manager, collaborator, or community member looks at and says: this person builds, ships, and thinks clearly about hard problems.

---

## Part 7: The One Risk

There's been extended time in design mode. Lattice has full design docs — reasoning loops, knowledge model, build plan — and no code. This reframe could become another round of planning if it isn't followed by action.

**The antidote is Week 0.** It's small enough to do this weekend, concrete enough to produce results, and publishable regardless of outcome. Everything after Week 0 has momentum behind it.

---

## What This Document Changes

| Document | Impact |
|---|---|
| [[00-master-plan]] | Architecture is unchanged. Principles need updating (dual-surface → separate artifacts). Build sequence gets Week 0 prepended and evals pulled forward. Framing shifts from "platform" to "personal agent, built in public." |
| [[01-user-flow-v0]] | Still valid as a vision doc. The flows described are the eventual target. What changes is that we don't try to build all of it before shipping anything. |
| Future docs | `L0-data-schema.md` becomes the next priority — the claim ontology with real examples. |

---

*This document captures a strategic inflection point. The architecture didn't change. The identity sharpened.*
