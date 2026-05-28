---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# 6-Week Build Plan

> Test the thesis first. Build the plumbing second. Polish last.

---

## The Principle

The original plan put relationship reasoning in Week 4. That gives zero buffer for the one thing that makes this product different. If Ollama can't classify contradictions, you need to know in Week 1 — not Week 4.

**Inverted approach:** Validate the hardest assumption first, then build infrastructure around a proven thesis.

---

## Week-by-Week

### Week 1: Validate the Thesis

**Goal:** Can a local LLM reliably classify relationships between article summaries?

| Task | Detail | Output |
|---|---|---|
| Build a test set | 10 article pairs: 3 contradict, 3 support, 2 extend, 2 unrelated | `test-set.json` |
| Test relationship reasoning | Run pairs through Ollama (Qwen3-14B, Llama 3.1-8B) with the relationship prompt | Accuracy scores per model |
| Test extraction quality | Run 10 real URLs through an extraction prompt | Extracted claims, rated manually |
| Make the model decision | Which model, local or cloud fallback? | Decision logged |

**Gate:** If relationship classification accuracy < 60%, pivot: try larger model, try OpenAI for this step only, or simplify to agreement clustering.

**Exit criteria:** Chosen model achieves ≥65% relationship accuracy on test set. Extraction produces 3-6 meaningful claims per article.

---

### Week 2: Ingestion Pipeline

**Goal:** End-to-end: paste a URL → get a stored knowledge card.

| Task | Detail | Output |
|---|---|---|
| URL → text extraction | Mozilla Readability integration | Clean article text from any URL |
| Text → knowledge card | Extraction prompt → structured JSON → SQLite | Working ingestion pipeline |
| Embedding generation | Ollama embedding model → store alongside card | Vector search ready |
| Basic card display | Simple Next.js UI showing card with claims + tags | Visual proof of ingestion |

**Exit criteria:** Paste a URL, see a knowledge card with claims, tags, and source type within 10 seconds.

---

### Week 3: The Reasoning Loop

**Goal:** New entries detect and label relationships with existing entries.

| Task | Detail | Output |
|---|---|---|
| Vector similarity search | On ingestion: find top 10 similar existing cards | Search working |
| Relationship reasoning | LLM compares new entry vs. each match, classifies relationship | Labels assigned |
| Relationship storage | Store edges in `relationships` table with type, explanation, confidence | Graph building |
| Contradiction badges | UI shows "⚠️ Contradicts Entry #X" on relevant cards | **First agentic moment visible** |

**Exit criteria:** Ingest an article that contradicts an existing one. System flags it with specific conflicting claims cited. This is the demo moment.

---

### Week 4: The Query Loop

**Goal:** "What do I know about X?" returns a structured synthesis.

| Task | Detail | Output |
|---|---|---|
| Query strategy generation | LLM generates 3-5 search angles from user question | Multi-angle retrieval |
| Multi-angle retrieval | Vector search per angle, deduplicate results | Rich result set |
| Conflict surfacing | Pull relationship edges between retrieved cards | Conflicts in answers |
| Synthesis output | Structured memo: themes, citations, conflicts, gaps | **Synthesis Draft working** |

**Exit criteria:** Query returns a multi-paragraph synthesis organized by themes, with at least one cited conflict and one identified gap.

---

### Week 5: Stretch Features + User Testing

**Goal:** Add credibility signals + gap radar. Get real users testing.

| Task | Detail | Output |
|---|---|---|
| Source credibility | Add source type classification to extraction prompt | Credibility badges on cards |
| Gap radar | After query: LLM identifies missing subtopics | Gap surfacing in synthesis |
| Confidence decay | Add timestamp awareness to synthesis prompt | Staleness warnings |
| User testing begins | 3-5 test users add 10-15 real articles each | First external feedback |

**Exit criteria:** Test users have working knowledge bases. Initial feedback on extraction quality, query usefulness, and conflict precision.

---

### Week 6: Polish + Demo + Eval

**Goal:** Ship-quality demo. Evaluation scores collected.

| Task | Detail | Output |
|---|---|---|
| UI polish | Clean card display, smooth query UX, contradiction highlighting | Demo-ready interface |
| Evaluation scoring | Collect ratings: query usefulness, conflict precision, gap quality | Final metrics |
| Demo sequence prep | Rehearsed 3-minute demo: ingest → contradict → query → synthesize | Presentation ready |
| Documentation | Update project docs, record demo video | Course submission |

**Exit criteria:** 70%+ useful query rating, ≥70% conflict precision, rehearsed demo that lands.

---

## The Demo Sequence (3 Minutes)

This is the moment that matters. Rehearse this.

| Step | What Happens | What the Audience Sees |
|---|---|---|
| 1 | "I've been reading about content moderation for my capstone" | Context setting |
| 2 | Show knowledge base: 15 entries, topic clusters visible | System has memory |
| 3 | Paste a new article arguing "AI moderation has 95% accuracy" | Live ingestion |
| 4 | System flags: "⚠️ Contradicts Entry #3 which cites 70% accuracy from a different study" | **The "whoa" moment** |
| 5 | Query: "What do I know about AI moderation accuracy?" | System synthesizes |
| 6 | Synthesis shows: 2 schools of thought, 1 conflict cited, 1 gap (no sources on appeal rates) | **Agent reasons, not just retrieves** |

**The pitch line:** "The system caught a contradiction I didn't notice, told me exactly which claims conflicted, and showed me what I'm still missing. That's what no existing tool does."

---

## Risk-Adjusted Timeline

| Risk | Impact | When You'd Know | Mitigation |
|---|---|---|---|
| Ollama can't do relationship reasoning | Fatal to thesis | **Week 1** | Larger model or OpenAI fallback for this step |
| Extraction quality is poor | Garbage in, garbage out | **Week 1** | Prompt engineering, model upgrade |
| URL parsing fails on real sites | 30% of ingestions broken | Week 2 | Fallback to raw text paste |
| Relationship reasoning is slow (>30s) | UX suffers | Week 3 | Async processing, show card immediately, add relationships after |
| Test users don't add enough entries | Can't prove compounding | Week 5 | Pre-load synthetic entries to supplement |
| Conflict precision < 60% | Can't demo the thesis | Week 4 | Raise confidence threshold, only show high-confidence conflicts |

---

## What "Done" Looks Like

At the end of Week 6, BrainDrain should:

- [ ] Ingest a URL in <10 seconds and produce a structured knowledge card
- [ ] Detect and label relationships (supports/contradicts/extends) on ingestion
- [ ] Surface a real contradiction with specific conflicting claims cited
- [ ] Answer "what do I know about X?" with a structured synthesis memo
- [ ] Include citations, conflict flags, gap identification, and source credibility in query responses
- [ ] Have 3+ test users with 10+ entries each who rate queries 70%+ useful
- [ ] Have a rehearsed 3-minute demo that produces a visible "whoa" moment

---

*Next: [[07-risks-and-mitigations]] — what could go wrong and how we handle it.*
