---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# BrainDrain — Knowledge Model

> The reasoning loops operate on a model. This document defines that model — the data structures, relationship types, and emergent properties that make agentic reasoning possible.

---

## Why a Three-Level Model

The previous design had two levels: knowledge cards and relationship labels. That's enough for a classifier. It's not enough for a system that reasons about the *state* of your knowledge.

The reframed model has three levels, each with distinct properties:

```
Level 3: Clusters  (emergent, computed)
  ↑ grouped by topic embedding
Level 2: Relationships  (between claims, across sources)
  ↑ classified at ingestion, updated by reasoning loops
Level 1: Claims  (atomic, from individual sources)
  ↑ extracted at ingestion
```

The reasoning loops operate *across* levels. Ingestion creates Level 1 and Level 2 data. State Assessment computes Level 3 properties. Query Self-Evaluation reads all three levels to assess answer quality. Belief Revision modifies Level 2 data based on Level 3 patterns.

---

## Level 1: Claims

A claim is the atomic unit of knowledge. It's a structured assertion extracted from a source — not a summary, not a highlight, but a *testable proposition.*

### Structure

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `source_id` | string | Which entry this came from |
| `text` | string | The claim as a clear assertion |
| `topic_tags` | string[] | Auto-assigned topic labels |
| `embedding` | vector | For similarity search |
| `evidence_type` | enum | See Source Metadata below |
| `assertion_strength` | enum | `strong` / `moderate` / `hedged` / `speculative` |
| `scope` | string | What context/domain this claim applies to (if identifiable) |
| `created_at` | timestamp | When the claim was ingested |

### Evidence Type (Source-Level Metadata)

Every claim inherits a source classification:

| Type | Definition | Example |
|---|---|---|
| **Primary research** | Original study, dataset, experiment, meta-analysis | "A 47-study meta-analysis found no significant effect..." |
| **Analysis** | Author's interpretation of others' data | "Looking at the BLS data, I argue that..." |
| **Opinion** | Argument without cited evidence | "I believe remote work is the future because..." |
| **Aggregation** | Summary of multiple sources (newsletter, roundup) | "This week in AI: three studies showed..." |

**Why this matters:** When the system synthesizes or evaluates, it needs to know whether "5 sources agree" means 5 independent studies or 5 blog posts citing the same study. Evidence type is the cheapest, highest-leverage metadata to extract — one field, massive impact on reasoning quality.

### Assertion Strength

How confidently does the source make this claim?

| Strength | Signal |
|---|---|
| **Strong** | "The data clearly shows..." / "This is unambiguous..." |
| **Moderate** | "Evidence suggests..." / "Research indicates..." |
| **Hedged** | "It's possible that..." / "Some argue..." |
| **Speculative** | "I suspect..." / "My hunch is..." |

This matters for conflict detection. Two "strong" claims that contradict each other are a real conflict. A "strong" claim vs. a "speculative" claim is an imbalanced conflict — the system should note that.

---

## Level 2: Relationships

A relationship is a labeled, directional edge between two claims (or between a new claim and an existing cluster).

### Relationship Types

The previous taxonomy had 4 types: supports, contradicts, extends, unrelated. That's too flat. Real intellectual relationships are richer:

| Relationship | Definition | Example |
|---|---|---|
| **Supports** | Same conclusion, from independent evidence or reasoning | Two studies both finding remote work doesn't reduce output |
| **Contradicts** | Incompatible conclusions | One study says X improves Y, another says X has no effect on Y |
| **Extends** | Adds a new dimension, detail, or application | Source A says remote work helps focus; Source B adds that it helps focus *specifically for deep technical work* |
| **Qualifies** | "True, but only under certain conditions" | "Remote work improves productivity — but only for experienced employees, not new hires" |
| **Supersedes** | Newer evidence/framework replaces an older claim | A 2025 longitudinal study replacing a 2023 cross-sectional one |

### Relationship Metadata

| Field | Type | Description |
|---|---|---|
| `source_claim_id` | string | The newer claim (the one being ingested) |
| `target_claim_id` | string | The existing claim it relates to |
| `type` | enum | supports / contradicts / extends / qualifies / supersedes |
| `confidence` | float (0-1) | How confident the system is in this classification |
| `reasoning` | string | One-sentence explanation of why this label was chosen |
| `conflict_subtype` | enum (optional) | For contradictions: `direct_refutation` / `scope_difference` / `different_interpretation` |
| `created_at` | timestamp | When classified |
| `last_evaluated` | timestamp | When last re-evaluated (by propagation or belief revision) |

### Contradiction Subtypes

Not all contradictions are equal. The system should distinguish:

| Subtype | What it means | Example |
|---|---|---|
| **Direct refutation** | "X is true" vs. "X is false" — same scope, opposite conclusion | "Remote work reduces output" vs. "Remote work does not reduce output" |
| **Scope difference** | Both may be true — they're talking about different contexts | "Remote work hurts collaboration" (for new teams) vs. "Remote work helps collaboration" (for distributed teams) |
| **Different interpretation** | Same data, opposite conclusions | Same productivity data read as "no significant effect" by one author and "modest decline" by another |

**Why this matters:** A scope difference isn't a real conflict — it's a nuance. The system should surface scope differences as "interesting" but reserve the "conflict" flag for direct refutations. This prevents alert fatigue and increases the signal quality of contradiction detection.

---

## Level 3: Clusters

A cluster is an emergent topic grouping — computed, not manually created. Clusters are where the *state* of your knowledge lives.

### How Clusters Form

Clusters are computed by grouping claims by topic embedding similarity. As new claims are ingested, they're assigned to existing clusters or seed new ones. This isn't static — cluster boundaries shift as the knowledge base grows.

### Cluster Properties (Computed)

These properties are what the reasoning loops read and reason about. They're recomputed periodically (by Loop 3: Knowledge State Assessment).

| Property | Definition | How It's Computed |
|---|---|---|
| **Depth** | How much coverage exists | Count of claims in the cluster |
| **Diversity** | How many independent perspectives | Count of distinct sources; penalize if many sources are the same type or cite the same underlying data |
| **Conflict level** | Internal disagreement | Proportion of relationship edges that are `contradicts` or `qualifies`. 0 = full consensus, 1 = deeply contested |
| **Consensus direction** | What the majority view is | The claim position supported by the most (and strongest) evidence |
| **Recency** | How fresh the coverage is | Distribution of `created_at` timestamps; flag if median age > N months |
| **Evidence quality** | Source-type breakdown | % primary research vs. analysis vs. opinion vs. aggregation |
| **Stability** | Has the view shifted recently? | Compare current consensus direction against prior assessment; if it flipped, the cluster is "under revision" |

### Example Cluster State

```
Cluster: "Remote Work and Collaboration"
  ├── Depth: 11 claims across 8 sources
  ├── Diversity: 6 distinct voices (moderate)
  ├── Conflict level: 0.35 (contested)
  │     Direct refutation: 1 (meta-analysis vs. opinion cluster)
  │     Scope differences: 2 (new hires vs. experienced employees)
  ├── Consensus direction: "Likely no clear effect" (shifted Feb 20)
  ├── Recency: Median age 8 months. Newest: Feb 2026. Oldest: Mar 2024.
  ├── Evidence quality: 1 meta-analysis, 2 analyses, 5 opinion pieces
  ├── Stability: UNDER REVISION (consensus shifted from "harmful"
  │              to "mixed" on Feb 20, triggered by Source #23)
  └── Revision history:
        - Jan 2026: Cluster formed. Consensus: "harmful." (8 opinion sources)
        - Feb 20, 2026: Meta-analysis ingested. Consensus shifted to "mixed."
```

This is the state that the reasoning loops read. When a user queries "what do I know about remote work?", the system doesn't just retrieve claims — it reads the cluster state and says: *"Your view here shifted recently. Evidence is contested. Your strongest source is a meta-analysis that challenged 8 opinion pieces. Here's the synthesis, but note: this is an active area of revision in your knowledge base."*

---

## How the Levels Connect

```
USER READS AN ARTICLE
        │
        ▼
   ┌─────────────┐
   │   Level 1   │  "Remote work has no significant effect on
   │   Claims    │   team output." (primary research, strong assertion)
   └──────┬──────┘
          │ compared against existing claims
          ▼
   ┌─────────────┐
   │   Level 2   │  CONTRADICTS: "Remote work reduces collaboration"
   │   Relations │  (confidence: 0.87, type: direct_refutation)
   │             │  QUALIFIES: "Remote work hurts new hire onboarding"
   │             │  (confidence: 0.72, type: scope_difference)
   └──────┬──────┘
          │ propagated to cluster
          ▼
   ┌─────────────┐
   │   Level 3   │  Cluster "Remote Work": conflict level ↑ 0.15→0.35
   │   Clusters  │  Consensus direction: shifted from "harmful" to "mixed"
   │             │  Stability: now "UNDER REVISION"
   │             │  Evidence quality: now includes primary research
   └─────────────┘
          │
          ▼
   REASONING LOOPS FIRE:
   - Loop 1: Propagation updates downstream relationship confidence
   - Loop 3: State Assessment notes the shift for next briefing
   - Loop 4: Belief Revision proposes re-synthesis to user
```

---

## The "Epistemic Spectrum" — Why This Model Matters

The three-level model enables something no retrieval tool can do: **distinguishing between different qualities of knowing.**

| State | What it means | System behavior |
|---|---|---|
| **Empty** | No claims on this topic | Report as gap. If referenced by other clusters, flag as structural gap. |
| **Thin** | 1-2 claims, single source | Caveat any query answer: "Your knowledge here is narrow." |
| **Shallow** | Multiple claims, but all opinion / low evidence quality | Flag: "You have coverage but weak evidence." |
| **One-sided** | Multiple claims, but all support the same position | Flag: "Your view is internally consistent but untested — no opposing sources." |
| **Contested** | Claims with genuine conflicts (direct refutations) | Surface the conflict. If evidence weight is unequal, note which side is stronger. |
| **Nuanced** | Claims with qualifications and scope differences | Synthesize the conditions under which different views apply. |
| **Deep** | Many claims, diverse sources, includes primary research, conflicts resolved or well-understood | High-confidence synthesis. Note this is your strongest area. |

A system that can distinguish "one-sided" from "deep" and "thin" from "contested" is doing something fundamentally different from retrieval. It's reasoning about the *quality and structure* of knowledge — not just its *existence.*

---

## Implementation Notes

### What's extracted at ingestion (Level 1 + 2)
One LLM call per source, structured output:
- 3-7 claims as assertions
- Evidence type classification
- Assertion strength per claim
- Topic tags

One LLM call per relevant existing entry (top 5-10 by similarity):
- Relationship type
- Confidence score
- Reasoning (one sentence)
- Conflict subtype (if applicable)

### What's computed periodically (Level 3)
One clustering pass (embedding-based, can be simple k-means or DBSCAN).
One LLM call per cluster to assess state properties.
Diff against previous assessment to detect changes.

### What's stored
- Claims: SQLite table + vector store for embeddings
- Relationships: SQLite edges table with metadata
- Clusters: SQLite table with computed properties + assessment history
- Revision history: append-only log of cluster state changes

---

*For the reasoning loops that operate on this model, see [[09-agentic-loops]]. For the product brief, see [[00-product-brief]].*
