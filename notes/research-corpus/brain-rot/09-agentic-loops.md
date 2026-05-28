---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# BrainDrain — Agentic Reasoning Loops

> A pipeline processes data. An agent maintains a model and reasons about its integrity. BrainDrain has six reasoning loops, not one.

---

## Why This Document Exists

The previous design had one agentic moment: the classification step at ingestion. That's a pipeline with a smart step — not a loop, and vulnerable to the "just RAG with a classifier" critique.

This document defines six reasoning loops that operate at different stages of the system. Together, they make BrainDrain a stateful reasoning system rather than a retrieval pipeline with a classification layer.

**What makes a loop a loop:** The system generates output, evaluates that output against the knowledge model, and modifies its behavior based on what it finds. If there's no evaluation and no behavior change, it's a pipeline step — not a loop.

---

## Loop 1: Ingestion with Propagation

**When it fires:** Every time new content enters the system.

**Current design (pipeline):**
```
New content → Extract claims → Find similar entries → Classify relationship → Store
```

**Reframed (loop):**
```
New content arrives
  → [Extract]    Pull key claims as structured assertions
  → [Retrieve]   Find related entries by embedding similarity
  → [Classify]   Label the relationship to each related entry
  → [Evaluate]   How confident is this classification? (0-1)
      → If low confidence: re-retrieve with alternate queries,
        attempt reclassification with more context
      → If high confidence: proceed
  → [Propagate]  Reason about implications on the existing graph:
      → Does this change the confidence of any downstream relationships?
      → Does this entry shift the consensus in a cluster?
      → Does it resolve a previously flagged conflict?
      → Does it introduce a conflict into a previously stable cluster?
  → [Store]      Card + relationships + propagation effects saved
  → [Surface]    If propagation found anything significant, tell the user:
                 "This article doesn't just extend your pricing cluster —
                  it contradicts the foundation that 3 other entries built on."
```

**What makes it agentic:**
- **Self-evaluation:** The system assesses its own classification confidence and retries when uncertain, rather than storing a weak label.
- **Graph reasoning:** It doesn't just label one edge — it reasons about how a new edge affects the subgraph. A contradiction against a well-connected node has different implications than one against an isolated entry.
- **Behavior change:** The propagation step can downgrade the confidence of existing relationships, flag clusters as newly unstable, or resolve previously open conflicts. The model *changes* based on the reasoning, not just the data.

**Concrete example:**
You ingest a meta-analysis on remote work that contradicts Entry #7 ("remote work reduces collaboration"). Entries #12, #15, and #18 all "support" Entry #7.

Pipeline behavior: Label the new entry as "contradicts #7." Done.

Loop behavior: Label the contradiction. Then: "Entry #7 is the anchor for a 4-node cluster. This contradiction weakens the cluster's consensus. Entries #12, #15, #18 may need re-evaluation — their support was for a claim that's now contested. Flagging this cluster as unstable."

---

## Loop 2: Query-Time Self-Evaluation

**When it fires:** Every time the user queries their knowledge base.

**Current design (pipeline):**
```
User query → Retrieve relevant entries → Synthesize answer → Return
```

**Reframed (loop):**
```
User query: "What do I know about content moderation?"
  → [Strategize]   Generate multiple search angles, not one keyword
  → [Retrieve]     Vector search + relationship-edge traversal
  → [Synthesize]   Draft an answer with citations and conflict flags
  → [Self-Eval]    Evaluate the draft against quality criteria:
      → Coverage: Did I draw on enough sources, or is this answer
        dominated by 1-2 entries?
      → Conflict honesty: Are there conflicts I retrieved but
        didn't surface in the synthesis?
      → Evidence quality: Is this answer resting on primary research
        or opinion pieces?
      → Recency: Is the answer anchored on stale sources?
      → Confidence: Given the above, how much should the user
        trust this answer?
  → [Refine]       Based on the self-eval:
      → If coverage is thin: caveat the answer ("Note: this answer
        draws primarily on 2 sources. Your knowledge here is narrow.")
      → If conflicts were glossed: add them back
      → If evidence is weak: flag it ("Your view is based on
        4 opinion pieces and 0 primary research.")
      → If stale: note it ("Your most recent source on this
        is 14 months old.")
  → [Return]       Answer + confidence assessment + caveats
```

**What makes it agentic:**
- **Self-critique:** The system audits its own output before returning it. RAG generates and returns. This system generates, evaluates, and refines.
- **Meta-information:** The user doesn't just get an answer — they get an answer with an honest assessment of its reliability. "Here's what your notes say, and here's how much that's worth."
- **Behavior change:** A self-eval that finds weak evidence triggers a different output format (caveats, flags) than one that finds strong, diverse support. The system's output adapts based on its assessment.

**Why this matters for the demo:**
This is the "whoa" moment that doesn't depend on curated contradictions. Any query can demonstrate it. User asks a question, system answers, and then says: *"But I should note — this answer rests on 3 opinion pieces from the same author. You have no primary research on this topic. Confidence: moderate."* That's something no existing tool does.

---

## Loop 3: Knowledge State Assessment

**When it fires:** After every N ingestions, or when the user opens the app after inactivity.

**This is the loop that makes BrainDrain proactive.**

```
[Trigger]  5 new entries since last assessment (or user returns after 3+ days)
  → [Cluster]     Group entries by topic (embedding-based clustering)
  → [Assess]      For each cluster, compute state properties:
      → Depth: How many entries?
      → Diversity: How many distinct perspectives/voices?
      → Conflict level: Internal disagreement score
      → Recency: Coverage freshness distribution
      → Evidence quality: Source-type breakdown
  → [Compare]     Diff against the previous assessment:
      → Which clusters grew?
      → Which clusters have new conflicts?
      → Which clusters became stale (no new entries, aging sources)?
      → Did any new clusters emerge?
  → [Prioritize]  Decide what's worth reporting:
      → New conflict in a previously stable cluster → high priority
      → A cluster growing but only from one perspective → medium
      → Stale cluster the user hasn't queried → low
  → [Brief]       Generate a "state of your knowledge" report:
      "Since you were last here:
       - Your pricing cluster deepened: 3 new entries. But all 3 are
         from the same author — diversity hasn't improved.
       - New conflict in your AI regulation cluster: Entry #31
         contradicts the consensus from entries #8, #12, #19.
       - Your remote work cluster is aging — nothing newer than
         October 2025. Consider whether your view still holds.
       - A new cluster is emerging around 'creator economy'
         (3 entries, no conflicts yet, mostly opinion pieces)."
```

**What makes it agentic:**
- **Autonomous execution:** Runs without a user trigger. The system decides when to assess and what to report.
- **Temporal reasoning:** Compares current state against prior state. It understands *change*, not just *status*.
- **Editorial judgment:** Not everything that changed is worth reporting. The system reasons about priority — a new conflict in a deep cluster matters more than a thin cluster getting one more entry.
- **Feedback loop:** The assessment feeds future behavior. If it flagged low diversity last week and diversity still hasn't improved, it can escalate. If a stale cluster gets a fresh entry, it can note the update.

---

## Loop 4: Belief Revision

**When it fires:** When a conflict is detected that's strong enough to challenge an existing cluster consensus.

**This is the most ambitiously agentic loop.**

```
[Trigger]  New entry contradicts a well-supported cluster
  → [Assess Weight]  Compare evidence quality:
      → Is the new entry primary research? Opinion? Meta-analysis?
      → What's the evidence quality of the cluster it challenges?
      → What's the count (1 contradicting source vs. N supporting)?
      → Does count matter here, or does evidence type dominate?
  → [Reason]    Form a judgment:
      "You have 8 entries supporting 'remote work hurts collaboration.'
       Entry #23 is a meta-analysis of 47 studies finding no clear effect.
       This is 1-vs-8 by count, but the 1 is primary research and the 8
       are opinion pieces. By evidence weight, the new entry is stronger
       than the cluster it challenges."
  → [Propose]   Suggest a revision to the user:
      "Your mental model on remote work may need updating.
       Would you like me to re-synthesize this cluster
       incorporating the new evidence?"
  → [Execute]   (With user consent):
      → Re-evaluate all relationships in the cluster
      → Update relationship confidence scores
      → Produce a revised synthesis
      → Record the revision event:
        "Feb 20, 2026: Understanding of 'remote work and collaboration'
         shifted from 'likely harmful' to 'evidence is mixed, meta-analysis
         finds no clear effect.' Triggered by Source #23 (meta-analysis)."
  → [Track]     Over time, build a revision history:
      A log of how the user's understanding evolved
      and what caused each shift.
```

**What makes it agentic:**
- **Evaluative reasoning:** The system doesn't just detect a conflict — it weighs the evidence on both sides and forms a judgment about which side is stronger.
- **Proposes action:** It suggests a concrete change to the knowledge model, explains its reasoning, and asks for consent.
- **State modification:** With consent, it modifies the existing model — updating relationships, changing confidence scores, producing a revised synthesis.
- **Memory of change:** The revision history is a first-class concept. Over time, the user can see *how their understanding evolved* — something no knowledge tool tracks.

**Why this is hard to copy:** Any tool can classify a pair of texts. Reasoning about evidence weight, proposing model revisions, maintaining a revision history, and tracking epistemic evolution — that's a fundamentally different level of system intelligence.

---

## Loop 5: Structural Gap Reasoning

**When it fires:** Periodically (as part of knowledge state assessment), or on-demand when the user queries a topic.

**Current gap detection:** "You have 8 entries on detection, 0 on appeals."

**Reframed — gap reasoning:**

```
[Analyze]     Identify thin spots in the knowledge graph
  → [Cross-reference]  Check whether existing sources REFERENCE the gap:
      → Do any of your moderation sources mention appeals processes?
      → If 3 of 8 sources reference appeals as critical, this
        isn't just an adjacent topic — it's a dependency.
  → [Assess Impact]   Reason about why the gap matters:
      "Your understanding of moderation policy is structurally
       incomplete. 3 of your policy sources cite appeals as a
       downstream consequence of detection decisions. Without
       coverage on appeals, your synthesis of moderation will
       miss a key feedback loop."
  → [Generate Questions]  Produce specific questions the gap represents:
      "To fill this gap, you'd want to answer:
       1. What happens after content is flagged — what's the appeals flow?
       2. What error rates do appeals processes reveal about detection?
       3. How do appeals outcomes inform future detection policy?"
  → [Recommend]   "If you find an article addressing these questions,
                   ingesting it would close the most significant hole
                   in your moderation cluster."
```

**What makes it agentic:**
- **Structural reasoning:** It doesn't just count — it analyzes dependencies between topics by looking at what existing sources reference.
- **Impact assessment:** It reasons about *why* a gap matters, not just *that* it exists. A gap that's referenced by 3 existing sources is structurally important. A gap that's merely topically adjacent is nice-to-know.
- **Directed guidance:** It generates specific questions, turning a vague "you don't know about X" into a concrete search brief.

---

## Loop 6: Epistemic Habit Analysis

**When it fires:** After a meaningful volume of entries (20+), periodically thereafter.

**This is meta-reasoning — reasoning about the user's patterns of knowledge building, not just their knowledge.**

```
[Observe]    Analyze patterns across the entire knowledge base:
  → Source diet: What types of sources does the user save?
      "85% opinion pieces. 12% analysis. 3% primary research."
  → Perspective balance: Within contested topics, how one-sided?
      "On AI regulation: 9 of 11 sources favor lighter regulation."
  → Depth vs. breadth: Shallow across many topics or deep on few?
      "14 topic clusters, but only 2 with more than 5 entries.
       You're reading broadly but building depth nowhere."
  → Recency distribution: Over-indexing on old or new?
      "You cite your 2024 sources more than your 2025 sources,
       but the 2024 sources are opinion and the 2025 are research."
  → Confirmation patterns: Does new reading mostly reinforce?
      "Your last 10 entries all 'support' existing clusters.
       Nothing has challenged your existing views in 6 weeks."

  → [Assess]   Form a meta-judgment:
      "Your knowledge base has a weak evidential foundation.
       Most of your views are built on opinion pieces, not research.
       Your AI regulation view is one-sided.
       You haven't encountered a challenging perspective recently."

  → [Advise]   Generate actionable recommendations:
      "Consider seeking out a primary study on AI regulation
       outcomes. Your current view is internally consistent
       but built on a narrow source base."
```

**What makes it agentic:**
- **Meta-cognition:** The system reasons about *how you think*, not just *what you know*. It monitors epistemic habits as a first-class concept.
- **Pattern detection:** It identifies systematic biases — confirmation bias, source-type bias, perspective skew — that emerge from patterns the user would never see.
- **Advisory posture:** It doesn't just flag problems — it recommends corrective action. "Seek out a primary study" is more useful than "you have a skew."

**Why this is the hardest feature to replicate:** Modeling a user's epistemic habits requires the full knowledge state — claims, relationships, source metadata, temporal data, cluster properties. No tool that stores-and-retrieves can do this, because the reasoning operates on the *structure* of the knowledge base, not its *content*.

---

## How the Loops Interact

The loops aren't independent — they feed each other:

```
                    ┌──────────────────────┐
                    │  Loop 3: State       │
                    │  Assessment          │◄──── runs periodically
                    │  (what changed?)     │
                    └──────┬───────────────┘
                           │ identifies conflicts,
                           │ stale areas, new clusters
                           ▼
┌──────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  Loop 1:     │───►│  Loop 4: Belief      │───►│  Loop 6:         │
│  Ingestion   │    │  Revision            │    │  Epistemic       │
│  + Propagate │    │  (should your view   │    │  Habit Analysis  │
└──────────────┘    │   change?)           │    │  (how do you     │
       │            └──────────────────────┘    │   build knowledge?)│
       │                                        └──────────────────┘
       │            ┌──────────────────────┐           │
       │            │  Loop 5: Gap         │           │
       └───────────►│  Reasoning           │◄──────────┘
                    │  (what's missing     │
                    │   and why it matters)│
                    └──────────────────────┘
                           ▲
                           │ gap context enriches
                           │ query answers
                    ┌──────┴───────────────┐
                    │  Loop 2: Query       │
                    │  Self-Evaluation     │◄──── user-triggered
                    │  (how good is this   │
                    │   answer?)           │
                    └──────────────────────┘
```

- **Ingestion** feeds **State Assessment** (new data changes the picture)
- **State Assessment** feeds **Belief Revision** (identified conflicts trigger deeper evaluation)
- **Belief Revision** feeds **Epistemic Habits** (revision patterns reveal how the user builds knowledge)
- **Gap Reasoning** draws from **Epistemic Habits** (source-type gaps are a habit problem, not just a content problem)
- **Query Self-Eval** draws from **Gap Reasoning** (gap context enriches the answer with "here's what I couldn't cover")

---

## Prioritization for Build

Not all loops are equally hard or equally impactful for a demo.

| Loop | Build Complexity | Demo Impact | Agentic Signal | Recommendation |
|---|---|---|---|---|
| 1. Ingestion + Propagation | Medium | High | Strong | Core — the thesis lives here |
| 2. Query Self-Evaluation | Low (1 extra LLM call) | Very High | Strong | Core — best "whoa" moment per effort |
| 3. Knowledge State Assessment | Medium | High | Very Strong | Core — makes the system proactive |
| 4. Belief Revision | High | Very High | Strongest | Stretch — most impressive but most complex |
| 5. Structural Gap Reasoning | Medium | Medium | Strong | Stretch — builds on Loop 3 naturally |
| 6. Epistemic Habit Analysis | Medium | Medium | Strong | Stretch — needs volume (20+ entries) to demonstrate |

**The minimum viable agentic system is Loops 1 + 2 + 3.** That gives you: smart ingestion that propagates, queries that audit themselves, and a proactive briefing that tells you what changed. Together, they defeat the "just RAG" critique at every stage.

---

*For the knowledge model these loops operate on, see [[11-knowledge-model]]. For the product brief, see [[00-product-brief]].*
