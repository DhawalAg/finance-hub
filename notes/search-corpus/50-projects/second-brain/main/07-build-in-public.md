---
tags:
  - type/project
  - topic/agents
  - topic/ai
  - status/seed
created: 2026-04-18
parent: "[[00-master-plan]]"
---

# Second Brain — Build in Public

> Credibility and distribution strategy. The agent is private infrastructure; the outputs are the public surface.

---

## Strategy in One Sentence

Ship small, opinionated artifacts at a steady cadence so that by month 3-4, there are 5-6 published pieces that cross-reference each other and establish a coherent body of work — not a portfolio, a compounding knowledge trail.

The bet: frequency beats magnitude, opinions beat abstractions, and learning artifacts are more honest than polished products. One well-scoped npm package with a real README teaches more than a launch post for a product nobody can use.

---

## The Three Channels

### Channel 1: Packages (npm / GitHub)

**Purpose:** Standalone, reusable code extracted from the private agent. Each package works without any Second Brain infrastructure.

**Distribution:** npm registry, GitHub with full README and usage examples. Cross-posted to dev.to for discovery. Announced on X/Twitter and LinkedIn.

**Why this works:** Packages are the hardest artifact to fake. They either work or they don't. A well-documented `bm25-from-scratch` with tests earns more credibility than a thought-leadership thread about search.

### Channel 2: Prompt Templates (Markdown)

**Purpose:** Tested prompt sets that work in any coding agent (Claude Code, Cursor, Copilot). No code dependency. Portable by design.

**Distribution:** GitHub repo (versioned bundles), linked from blog posts. Shared in AI builder communities and agent skill registries.

**Why this works:** Prompt templates are the fastest way for someone else to get value from this project. Zero setup. Copy the markdown, run it. If the template produces useful output, the author gains credibility. If it doesn't, the author learns fast.

### Channel 3: Writing (Blog Posts, Threads)

**Purpose:** Document the build as it happens — decisions, tradeoffs, failures, results. One post per roadmap phase minimum.

**Distribution:** Substack (long-form home), cross-posted to dev.to. Threads on X/Twitter. Summaries on LinkedIn. Each post links to the relevant package or template.

**Why this works:** Writing is the connective tissue. It contextualizes the code, explains the "why" that a README can't carry, and builds narrative over time. The first post stands alone; the fifth post references the first four.

---

## Content Calendar

Mapped to the [[50-projects/second-brain/main/05-roadmap|build roadmap]]. Each phase ships 1-2 public artifacts plus companion content.

| Phase | Timeframe | Artifact 1 | Artifact 2 | Blog Post |
|-------|-----------|-----------|-----------|-----------|
| 0 | Week 0 | Labeled dataset (GitHub) | Eval prompts (GitHub) | "Can an LLM reason about knowledge state? I tested it." |
| 1 | Weeks 1-3 | `core-agent-loop` (npm) | `claim-extractor` (npm) | "Building an agent loop from scratch" |
| 2 | Weeks 4-6 | `bm25-from-scratch` (npm) | Prompt templates v1 | "What I learned building hybrid search from scratch" |
| 3 | Weeks 7-10 | `relationship-classifier` (npm) | Prompt templates v2 | "How my agent detects what I don't know" |
| 4 | Weeks 11-14 | `brain` CLI v0.1 (GitHub) | Prompt templates v3 | -- |
| 5 | Weeks 15-20 | `agent-trace-viewer` (npm) | Lattice web v0.1 | "What my agent actually does in 47 steps" |

Supplementary threads (X/Twitter, LinkedIn) ship between major posts — short-form takes on specific decisions, surprising results, or tools discovered during the build.

---

## Artifact Catalog

Every planned shareable artifact across the full roadmap.

### Packages

| Artifact | Phase | Audience | Primary Channel |
|----------|-------|----------|----------------|
| `core-agent-loop` | 1 | Agent builders, TS developers | npm, GitHub, dev.to |
| `claim-extractor` | 1 | AI builders, knowledge mgmt | npm, GitHub |
| `bm25-from-scratch` | 2 | Developers learning search | npm, GitHub, dev.to |
| `hybrid-search` | 2 | Agent builders needing retrieval | npm, GitHub |
| `relationship-classifier` | 3 | AI researchers, agent builders | npm, GitHub, dev.to |
| `agent-trace-viewer` | 5 | Anyone building agents | npm, GitHub, dev.to |
| `brain` CLI v0.1 | 4 | Power users, agent enthusiasts | GitHub |

### Prompt Templates

| Artifact | Phase | Audience | Primary Channel |
|----------|-------|----------|----------------|
| `analyze-notes` | 2 | Anyone with a notes vault | GitHub, skill registries |
| `extract-claims` | 2 | AI builders, researchers | GitHub |
| `find-conflicts` | 3 | Knowledge workers, researchers | GitHub |
| `gap-analysis` | 3 | Students, researchers, PMs | GitHub |
| `weekly-briefing` | 4 | Knowledge workers | GitHub |
| `vault-health` | 4 | Obsidian users | GitHub |
| `daily-digest` | 4 | Obsidian users | GitHub |

### Writing

| Artifact | Phase | Audience | Primary Channel |
|----------|-------|----------|----------------|
| "Can an LLM reason about knowledge state?" | 0 | AI community broadly | Substack, dev.to |
| "Building an agent loop from scratch" | 1 | TS developers, agent builders | Substack, dev.to |
| "What I learned building hybrid search" | 2 | Developers, ML practitioners | Substack, dev.to |
| "How my agent detects what I don't know" | 3 | AI builders, knowledge mgmt | Substack, dev.to |
| "What my agent actually does in 47 steps" | 5 | Agent builders, hiring managers | Substack, dev.to |

---

## Content Principles

Six rules for everything published under this project.

### 1. Opinions over abstractions

State a position. "BM25 outperformed semantic search on my vault, and here's why I think that's common" is useful. "There are tradeoffs between keyword and semantic search" is filler. If a piece doesn't contain a claim that could be wrong, it doesn't ship.

### 2. Show the failures

Publish the Phase 0 results even if they're bad. Write about the prompt that didn't work before the one that did. Failures with analysis are more credible than curated success stories. The kill criteria in the [[50-projects/second-brain/main/05-roadmap]] exist for a reason — if one triggers, that gets documented too.

### 3. Document decisions, not just outcomes

The interesting part is never "I chose SQLite." It's "I chose SQLite over Supabase because I needed zero-infrastructure persistence for a personal tool, and here's when I'd choose differently." Decisions reveal thinking. Outcomes reveal luck.

### 4. Working code over architecture diagrams

Every blog post links to a package or template that the reader can run. Conceptual posts without runnable artifacts are not published. If the code isn't ready, the post waits.

### 5. Scope ruthlessly

A post about BM25 is about BM25. It is not also about the agent loop, the knowledge model, and the future of personal AI. Tightly scoped pieces are more useful, more shareable, and easier to write. The cross-references between pieces handle the bigger picture.

### 6. Write during the build, not after

Blog posts are drafted in the same sprint as the code. The running log of decisions, surprises, and dead ends is the raw material. If writing happens after the phase closes, it becomes revisionist history — cleaner but less honest.

---

## Distribution Playbook

Where each content type goes, and why.

| Content Type | Substack | dev.to | X/Twitter | LinkedIn | GitHub |
|-------------|----------|--------|-----------|----------|--------|
| Long-form blog post | Primary home | Cross-post (full) | Thread summary | Summary + link | -- |
| Package release | Announcement link | Tutorial post | Thread with demo | Announcement | Primary home |
| Prompt template | Linked from post | -- | Thread with example | -- | Primary home |
| Dataset / eval | Linked from post | -- | Thread with findings | -- | Primary home |
| Short-form take | -- | -- | Primary home | Adapted version | -- |

**Platform logic:**

- **Substack** is the canonical home for long-form. Owns the archive. Builds a subscriber list that doesn't depend on algorithm changes.
- **dev.to** is for developer discovery. Cross-post full articles (dev.to allows canonical URLs back to Substack). Good for SEO and reaching developers who don't use X.
- **X/Twitter** is for real-time signal and conversation. Threads summarize posts, short takes capture in-progress learnings. This is where other builders see the work.
- **LinkedIn** is for professional credibility. Shorter, less technical versions of posts. Useful for the "potential employers/collaborators" audience segment.
- **GitHub** is the source of truth for all code and templates. Stars and forks are the credibility metric that matters most for packages.

---

## Compounding Model

The pieces are designed to reference each other. By month 3-4, the body of work creates a network effect.

### How it compounds

```
Week 0:  Blog post (thesis test)
              |
Week 3:  Blog post (agent loop) ──── references thesis post
              |                        links to core-agent-loop package
              |
Week 6:  Blog post (hybrid search) ── references both prior posts
              |                         links to bm25-from-scratch package
              |                         links to prompt template v1
              |
Week 10: Blog post (reasoning) ─────── references all three prior posts
              |                          links to relationship-classifier
              |                          links to prompt template v2
              |                          references Phase 0 eval results
              |
Week 20: Blog post (full system) ────── references everything above
                                          links to trace viewer
                                          links to all prompt templates
                                          retrospective on what worked/failed
```

### Three compounding effects

1. **Cross-reference density.** Each new piece links to 2-3 prior pieces. A reader who finds any single artifact can trace backward to the full body of work. By week 10, there are 15+ internal cross-references across posts, packages, and templates.

2. **Credibility stacking.** A single npm package is interesting. Four packages from the same project, each with a companion blog post explaining the design decisions, tells a different story — this person ships, iterates, and thinks clearly about tradeoffs.

3. **Search surface expansion.** Each published artifact is a new entry point. Someone searching for "BM25 TypeScript" finds the package. Someone searching for "agent observability" finds the trace viewer. Someone searching for "knowledge graph LLM" finds the reasoning post. Different queries, same author, same project.

### The month 4 snapshot

By week 14, the public footprint looks like:

- 6 npm packages on the registry
- 7 prompt templates on GitHub
- 4 blog posts on Substack (cross-posted to dev.to)
- 12+ threads on X/Twitter
- A CLI tool on GitHub
- A labeled dataset for knowledge-state evaluation

None of these individually is remarkable. Together, they form a body of work that is hard to replicate by someone who hasn't actually built the thing. That's the moat — not any single artifact, but the density and coherence of the full set.

---

## Related Documents

- [[50-projects/second-brain/main/01-vision]] — project identity and guiding principles
- [[50-projects/second-brain/main/05-roadmap]] — phased execution plan with concrete deliverables
- [[50-projects/second-brain/main/02-architecture]] — system architecture and layer design
- [[00-master-plan]] — original master plan

---

*The rule is simple: if a phase produces nothing shippable, the phase is scoped wrong. If a post contains no claim that could be wrong, it doesn't ship. Build the thing, extract the artifacts, publish the learnings.*
