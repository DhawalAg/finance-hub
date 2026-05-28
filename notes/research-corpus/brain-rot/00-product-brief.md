---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# BrainDrain — Product Brief

> Your tools store what you read. BrainDrain understands what you know.

---

## One-Liner

BrainDrain is a personal knowledge agent that maintains a living model of your understanding — it knows what you know, how well you know it, where you're conflicted, where you're thin, and what's changed.

## The Problem

Knowledge workers read 10-20+ articles, papers, and posts per week. They highlight, bookmark, and take scattered notes. Six weeks later, they can't find the insight they need, can't connect ideas across sources, and end up re-researching things they already learned.

But the real problem isn't findability. It's that **you have no model of your own knowledge.**

You don't know:
- What you know deeply vs. superficially
- Where your understanding is internally conflicted
- Which beliefs rest on strong evidence vs. opinion
- What's changed since you formed your views
- What adjacent things you *should* know but don't
- Whether your reading is building a balanced picture or an echo chamber

Every existing tool fails at this in the same way — they store content but never reason about what it means in the context of everything else you've stored:

- **ChatGPT** — reasons about what you paste *today*, forgets everything tomorrow
- **Pocket / Instapaper** — hoards links you'll never revisit
- **Notion** — stores notes y ou have to organize yourself
- **Obsidian** — connects notes, but you build every link by hand
- **NotebookLM** — synthesizes well within a session, but doesn't track how your understanding evolves or where it's weak

None of these tools maintain a *model* of your knowledge. None tell you the shape of what you know. None get smarter about *you* over time.

## The Product

BrainDrain is a knowledge state machine. You feed it what you read. It builds and maintains a model of your understanding at three levels:

1. **Claims** — what each source asserts, structured as testable propositions
2. **Relationships** — how claims relate across sources (supports, contradicts, extends, qualifies, supersedes)
3. **Clusters** — emergent topic areas with computed properties: depth, diversity, conflict level, recency, evidence quality

The reasoning layer operates on this model at every stage:

- **At ingestion:** reasons about what new content means for the existing model — not just classifying a pair, but propagating implications across the graph
- **At query time:** synthesizes an answer, then evaluates its own output — how well-supported is this answer? Is it anchored on one source? Are there conflicts I glossed over?
- **At rest:** autonomously assesses the state of your knowledge — what's changed, what's stale, what's thin, what shifted
- **At the meta level:** reasons about your epistemic habits — source quality, perspective balance, depth vs. breadth patterns

The system gets smarter as you use it. Not just because the graph is denser, but because richer state enables richer reasoning.

## The Bet

The current landscape maps along two axes:

```
                    Single-session           Persistent memory
                    (stateless)              (compounds over time)

Retrieve only       ChatGPT / Claude         Pocket / Instapaper
                                             Notion (manual)

Retrieve +          Perplexity               NotebookLM
synthesize                                   Open Notebook

Reason about        —                        BrainDrain ← HERE
knowledge STATE
(shape, quality,
conflicts, gaps,
evolution)
```

The next step for knowledge tools isn't better retrieval or better synthesis. It's **reasoning about the state of what you know** — its shape, strength, gaps, and trajectory over time.

Contradictions are one dramatic signal the system produces. But the durable value isn't "catches conflicts" — it's epistemic self-awareness. Knowing the *quality* of what you know, not just the *content*.

## V1 Scope (6 Weeks)

- **One persona:** Knowledge worker who reads broadly and needs to synthesize
- **One input:** Paste a URL or raw text
- **One model:** Three-level knowledge state (claims → relationships → clusters)
- **Core reasoning loops:**
  - Ingestion with propagation (reason about implications, not just classification)
  - Query with self-evaluation (audit the answer before returning it)
  - Knowledge state assessment (proactive briefing on what's changed)
- **Stack:** Next.js + Ollama + SQLite. Runs locally.

## Why This Matters for the Course

This project demonstrates what happens when you move from a **pipeline** to a **stateful reasoning system.**

Without the reasoning layer, BrainDrain is Open Notebook Lite — a retrieval tool with memory. With it, the system maintains a model of your understanding and reasons about that model at every stage. It catches conflicts you missed. It tells you when an answer is weak. It identifies gaps you didn't know you had. It audits its own output. It briefs you on how your knowledge has changed.

The delta — from "retrieves and summarizes" to "maintains a model and reasons about its integrity" — is the agentic thesis.

---

*For the full problem analysis, see [[01-problem-space]]. For the agentic reasoning loops, see [[09-agentic-loops]]. For the knowledge model, see [[11-knowledge-model]].*
