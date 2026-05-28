# BrainDrain: Feature Brainstorm

> What can BrainDrain do — explained in plain language, anchored to the pain it solves.

---

## The Core 4 (Already Designed)

### 1. Smart Ingestion
**Pain:** "I read something great but I won't remember it in a week."
Paste a URL or text. The agent reads it, pulls out the 3-7 key claims the author is making, tags it by topic, and stores a structured knowledge card. You don't organize anything — it does.

### 2. Compounding Memory
**Pain:** "I've read 50 articles this year. I can't tell you what any of them said."
Every entry lives in a persistent knowledge base. Entry #50 is more valuable than entry #1 because the system has more to connect it to. Unlike ChatGPT (which forgets) or Pocket (which hoards), BrainDrain accumulates and compounds.

### 3. Relationship Classification
**Pain:** "I read two articles that said opposite things. I didn't notice."
On ingestion, the agent compares new content against everything you've already saved and labels relationships: **supports**, **contradicts**, **extends**, or **unrelated**. When it finds a contradiction, it tells you exactly which claims conflict and from which sources. This is the thing nothing else does.

### 4. Knowledge Graph
**Pain:** "My notes are a flat list. Nothing connects to anything."
As you ingest content, the system builds a graph of relationships — not just tags, but directional links between cards. Article A *extends* Article B. Article C *contradicts* Article A. Over time, you get a living map of how your knowledge fits together, with topic clusters, hierarchies, and connection paths you didn't build manually.

---

## The Brainstorm: What Else Could This Do?

*Constraint: 6-week MVP, one dev, local LLM (Ollama), buildable, real value.*

---

### 5. Gap Radar
**Pain:** "I don't know what I don't know."

You've saved 12 articles on content moderation. 8 are about detection, 3 about policy, 1 about enforcement. Zero about appeals processes or creator communication. The agent notices and tells you:

> "You have deep coverage on detection and policy, but nothing on appeals workflows or creator-facing communication. These are adjacent areas based on your reading pattern."

**Why it's agentic:** The system *initiates* — it tells you something you didn't ask. It looks at your knowledge topology and identifies thin spots. This directly addresses the "what should I do next?" gap from the rubric. The agent goes from classifier to advisor.

**Buildable?** Yes. Cluster your cards by topic embedding. For each cluster, ask the LLM: "Given these articles about X, what adjacent subtopics are conspicuously absent?" One prompt, run on a schedule or after every 5th ingestion.

---

### 6. Confidence Decay
**Pain:** "I'm making decisions based on a 2023 article and I don't even realize it's outdated."

Every knowledge card has a timestamp. When you query "what do I know about remote work," the agent doesn't just synthesize — it flags staleness:

> "Your strongest source on this is from March 2024 (22 months old). Your most recent is from October 2025. Consider that the landscape may have shifted since your earliest entries."

If you add a newer article that contradicts an older one, the system can surface: "Your 2023 view on this was X. Your 2025 sources now suggest Y. Your mental model may be outdated."

**Why it's agentic:** Temporal reasoning. The agent understands that knowledge has a shelf life and proactively tells you when your picture might be stale — not because you asked, but because it noticed.

**Buildable?** Very. You already store timestamps. Add a recency weight to the query synthesis prompt. Flag any source older than N months when it's the primary basis for an answer.

---

### 7. Synthesis Drafts
**Pain:** "I have 15 articles on pricing strategy. I still have to write the memo myself from scratch."

You query: "Write a synthesis of everything I know about pricing strategy." Instead of a chat-style answer, the agent generates a structured first draft:

> **Synthesis: Pricing Strategy (15 sources, Jan-Feb 2026)**
>
> Three schools of thought emerge from your reading:
> 1. Value-based pricing (Sources 3, 7, 12) — argues pricing should reflect perceived value...
> 2. Competition-anchored pricing (Sources 1, 5) — argues pricing is relative to alternatives...
> 3. Cost-plus with behavioral nudges (Sources 9, 14) — argues margins matter more than positioning...
>
> **Key conflict:** Sources 7 and 5 directly disagree on whether competitor pricing should inform your own...
>
> **Gap:** None of your sources address pricing for freemium-to-enterprise transitions.

That's not a chat response. That's a deliverable.

**Why it's valuable:** This is the reframe from the pressure test — the knowledge base is the engine, but the *output* users care about is a document they can use. Senior PMs don't want to query a database. They want a draft they can edit.

**Buildable?** Yes. It's the query loop with a longer, more structured output prompt. Instead of "answer this question," the instruction is "write a synthesis memo organized by themes, with citations, conflicts, and gaps."

---

### 8. Perspective Tracker
**Pain:** "I keep reading things that confirm what I already believe. I have no idea if I'm in a filter bubble."

After 20+ entries, the agent can analyze your reading patterns:

> "On the topic of AI regulation, 9 of your 11 sources argue for lighter regulation. Only 2 present the case for stricter oversight. Your knowledge base has a perspective skew."

Or after ingesting a new article:

> "This is the 4th article you've saved arguing that remote work hurts collaboration. You have 1 article arguing the opposite. Want me to surface the counter-argument in more detail?"

**Why it's agentic:** The agent monitors your *epistemic balance* — not just what you know, but whether your knowledge is one-sided. It's doing something you'd never do manually: auditing your own biases.

**Buildable?** Yes. On query or after every N entries, cluster cards by stance (the relationship labels give you this — if 8 cards "support" each other and 2 "contradict" the cluster, that's a skew). One LLM call to summarize the imbalance.

---

### 9. Source Credibility Signals
**Pain:** "I saved a blog post and a peer-reviewed study. My system treats them the same."

On ingestion, the agent tags a basic credibility signal for each source:

- **Primary research** (original study, dataset, experiment)
- **Analysis** (author's interpretation of others' data)
- **Opinion** (argument without cited evidence)
- **Aggregation** (summary of multiple sources, e.g., a newsletter roundup)

When you query, the answer weights and labels accordingly:

> "Your view on this is supported by 2 primary research sources and 3 opinion pieces. The opinion pieces are more confident in their claims than the research supports."

**Why it's valuable:** Not all sources are equal. A strategy PM making a bet based on "5 articles agree" should know whether those are 5 independent studies or 5 blog posts citing the same study.

**Buildable?** Yes. Add a field to the extraction prompt: "Classify this source as: primary research, analysis, opinion, or aggregation. Cite your reasoning in one sentence." Cheap, one-line addition to the existing ingestion flow.

---

### 10. "Teach It Back" Flashcards
**Pain:** "I read it, I saved it, I still can't explain it."

For any knowledge card or topic cluster, the agent generates spaced-repetition-style challenge questions:

> **Card: Content Moderation at Scale (from your 6 articles)**
> - Q: What's the fundamental trade-off between automated moderation accuracy and coverage?
> - Q: Name two approaches to reducing false positives in hate speech detection.
> - Q: Your sources disagree on whether human review is scalable. What are the two positions?

The last question is a contradiction-based challenge — it tests whether you actually internalized the conflict the system surfaced.

**Why it's valuable:** Reading ≠ learning. The system helps you move from "I saved it" to "I can explain it." This is especially powerful for the course/student use case and for PMs prepping for a presentation.

**Buildable?** Yes. Take any card or cluster → one LLM call: "Generate 3-5 recall questions from these claims, including at least one that tests a conflict between sources." Display as a simple card UI.

---

### 11. Entry Point: "What Changed?"
**Pain:** "I haven't opened this in 3 days. I don't know what's worth looking at."

When you open BrainDrain after being away, instead of a blank search bar, you see:

> **Since you were last here:**
> - 📥 3 new entries ingested (from your queue / auto-ingest)
> - ⚡ 1 new contradiction detected: your article on AI hiring (Feb 16) conflicts with your earlier piece on structured interviews (Jan 28)
> - 🔗 2 new connections formed in your "pricing" cluster
> - 🕳️ Gap spotted: you have 8 entries on LLM evaluation but nothing on human-eval benchmarks

This is the "what should I do next" answer. The agent tells you where to look, not the other way around.

**Why it's agentic:** The system is proactive. It processed things while you were gone (or at least computed new insights from what you last added) and surfaces the most interesting changes. You open the app and it *briefs you*.

**Buildable?** Yes — it's a summary computed at login from your last-seen timestamp. "What cards were added since X? Any new relationships? Any new gaps?" One LLM call over the delta.

---

## Feature Tiers for Scoping

| Tier                                         | Features                                                                  | Why this tier                                                                                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **V1 Core (must ship)**                      | Smart Ingestion, Memory, Relationship Classification, Knowledge Graph     | The thesis. Without these, no product.                                                                                                        |
| **V1 Stretch (i want to add these as well)** | Synthesis Drafts, Source Credibility Signals, Gap Radar, Confidence Decay | Low build cost, high demo impact. Synthesis Drafts is the reframe that turns "knowledge base" into "deliverable."                             |
| **V2                                         | "What Changed?", Perspective Tracker, Teach It Back,                      | These make the agent *proactive* — the biggest gap in the current design. They turn BrainDrain from a tool you use into a tool that uses you. |
| **V3 (if this has legs)**                    | RSS feeds, multi-user shared knowledge bases                              | Deeper reasoning, more personas, collaboration                                                                                                |

---

## Answering the Rubric Gap

> "What should I do next?" moments are thin for V1.

The features that directly close this gap:
- **Gap Radar** — "Here's what's missing from your knowledge"
- **Confidence Decay** — "Here's what might be stale"
- **Perspective Tracker** — "Here's where you might be biased"

Taking it professional-grade:
- **"What Changed?"** — "Here's what happened since you last looked"
- Multi-Use

Let's build uptill V1 stretch.
