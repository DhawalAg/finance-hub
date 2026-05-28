---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# Metrics & Evaluation

> Measure the reasoning, not the retrieval. If the agent catches a contradiction the user missed — that's the metric.

---

## The Value Hierarchy

BrainDrain delivers value at three levels:

```
Level 1 (Table Stakes):   Content is stored and retrievable
Level 2 (Expected):       Queries return useful, synthesized answers
Level 3 (Differentiator): Agent surfaces what you missed — conflicts, gaps, staleness
```

Level 1 is a bookmark manager. Level 2 is RAG. **Level 3 is the product.**
Every metric should ladder to Level 3.

---

## North Star Metric

> **Useful query rate from users with ≥10 entries**

**Definition:** % of queries rated "useful" or "very useful" by users who have at least 10 entries in their knowledge base.

**Why this and not something simpler:**
- Requires the knowledge base to be real (≥10 = actual usage, not a test)
- Requires the query answer to be genuinely helpful (user-rated, not assumed)
- Captures compounding — useful answers depend on a rich knowledge base
- Fails fast — if users add entries but queries are useless, the reasoning is broken

**Week 6 target:** 70%+ useful rating across test users.

---

## Supporting Metrics

### Input Quality: Is the knowledge base growing well?

| Metric | What It Tells You | Week 6 Target |
|---|---|---|
| Entries added / user / week | Are users feeding the system? | ≥3 for engaged users |
| Ingestion success rate | Can we handle real URLs? | ≥90% |
| Claims per entry (avg) | Is extraction meaningful? Too few = broken. | 3-6 per entry |
| Tag accuracy | Do auto-tags match the actual content? | 80%+ human-rated |

### Agent Quality: Is the reasoning useful?

| Metric | What It Tells You | Week 6 Target |
|---|---|---|
| **Conflict precision** | When the agent says "contradicts," is it real? | **≥70%** |
| **Conflict recall** | % of actual conflicts the agent catches | ≥50% |
| Relationship accuracy | Are supports/extends labels correct? | ≥75% human-rated |
| Query relevance | Are retrieved cards on-topic? | ≥80% |
| Gap quality | Are surfaced gaps genuinely missing (not just unrelated)? | ≥60% |

**Conflict precision is the most important metric.** Better to surface 3 real contradictions than 10 guesses. False positives destroy trust faster than false negatives.

### User Signal: Does it stick?

| Metric | What It Tells You | Priority |
|---|---|---|
| Conflict click rate | Do users engage with surfaced contradictions? | High — proves value |
| Queries per session | Are users asking meaningful questions? | Medium |
| Return rate (D7) | Did they come back after first session? | High |
| Entries at churn | How many entries did inactive users have? | Medium — tells you the activation threshold |

---

## Evaluation Plan (Weeks 3-6)

### Week 3: Extraction Quality Test

**Method:** Build a test set of 20 real articles across 4-5 domains.
- Manually label ground-truth claims for each (what are the 3-7 key assertions?)
- Run through the extraction pipeline
- Score: precision (are extracted claims real?) and recall (did it miss important ones?)
- Score: tag accuracy (do auto-tags match the content?)

**Pass criteria:** ≥80% claim precision, ≥70% claim recall, ≥80% tag accuracy.

**If it fails:** Prompt engineering first. Model upgrade (larger Ollama model) second. OpenAI fallback third.

### Week 4: Relationship Reasoning Test

**Method:** Build a synthetic dataset with known relationships:
- 5 article pairs that clearly **contradict** each other
- 5 article pairs that clearly **support** each other
- 5 article pairs that **extend** each other
- 5 article pairs that are **unrelated** (similar topic, no real link)

Run ingestion on all 20. Score: does the system correctly classify each pair?

**Pass criteria:** ≥70% conflict precision, ≥60% overall relationship accuracy.

**This is the most important test.** If relationship reasoning doesn't work, the product thesis fails. Test this early.

### Week 5-6: End-to-End User Test

**Method:** 3-5 test users (course peers, friends, colleagues). Each:
1. Adds 10-15 real articles they've actually read
2. Queries 5 things they want to synthesize
3. Rates each answer: useful / partially useful / not useful
4. For surfaced conflicts: "Is this a real conflict?"
5. For surfaced gaps: "Is this genuinely missing from my reading?"

**Pass criteria:** 70%+ useful query rating, 70%+ conflict precision.

---

## Metrics Anti-Patterns

| Vanity Metric | Why It's Misleading |
|---|---|
| Total entries added | Users can add 100 entries and never query — that's a data dump, not a product |
| Total queries | Doesn't tell you if the knowledge base was rich enough to be useful |
| Conflict count | Agent can hallucinate conflicts — precision > volume |
| DAU/MAU | Too early. 6 weeks ≠ retention measurement |
| Time on site | BrainDrain is a tool for short, focused bursts — long sessions aren't the goal |
| "It works for me" | Creator bias. Must test with users who didn't build it |

---

## Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| North star timing | Query-time, not ingestion-time | Value is proven at retrieval, not at storage |
| Entry threshold | 10 entries | Below 10, insufficient density for meaningful relationships |
| Precision vs. recall | Precision-first | False positives destroy trust; false negatives are invisible |
| Evaluation method | Human rating (Week 5-6) | No automated ground truth yet — human judgment is the standard |
| Conflict recall target | 50% (lower than precision) | Missing a conflict is forgivable; hallucinating one isn't |

---

*Next: [[06-build-plan]] — the week-by-week execution plan.*
