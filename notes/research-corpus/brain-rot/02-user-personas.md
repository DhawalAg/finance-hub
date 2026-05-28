---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# User Personas

> Build for one. Validate with many. Scale to all.

---

## Persona Selection Logic

We evaluated 5 personas (full analysis in `hist/05-persona-map.md`). The selection criteria for a 6-week MVP:

1. **Pain must be acute and repeated** — not a nice-to-have
2. **Agentic fit must be high** — contradiction detection must matter to them
3. **Demo-able in 6 weeks** — we need a "whoa" moment with 15-20 entries
4. **Relatable to course evaluators** — Google/Meta PMs are the audience

**Primary persona: The Research-Heavy Knowledge Worker**
**Secondary persona: The Active Learner**

We're not building for casual readers. BrainDrain is a power tool for people who read with intent and need to produce something from what they've read.

---

## Primary: The Research-Heavy Knowledge Worker

*"I read 15 sources last month on this topic. I can't tell you where they agree or disagree."*

### Who They Are
- **Roles:** Strategy PM, analyst, consultant, policy researcher, grad student doing lit review
- **Reading volume:** 10-20 sources/week, often concentrated on a few topics
- **Output they produce:** Strategy docs, memos, competitive analyses, lit reviews, investment theses, recommendations
- **Current workflow:** Read → highlight → dump into Notion/Google Docs → manually synthesize when deadline hits

### The Pain (Specific)

| Moment | What Happens | Emotional State |
|---|---|---|
| Reading article #12 on a topic | "Didn't I read something that contradicts this?" | Uncertain, can't verify |
| Writing a strategy memo | Re-reads 6 articles to find the key claims | Frustrated, wasteful |
| Presenting a recommendation | "What about the counterargument?" — they can't cite it | Exposed, underprepared |
| Onboarding to a new domain | 30 articles in 2 weeks, zero structure | Overwhelmed |

### Jobs to Be Done
1. **Build a knowledge base on a topic** without manually organizing it
2. **Synthesize across sources** when writing a deliverable
3. **Know where sources disagree** before someone else points it out
4. **Query accumulated knowledge** instead of re-searching

### Why BrainDrain Fits

| Dimension | Score | Why |
|---|---|---|
| Pain intensity | 5/5 | They produce deliverables from synthesis — this is their job |
| Agentic fit | 5/5 | Contradiction detection maps directly to "did I miss something?" |
| Demo-ability | 5/5 | Topic-focused reading = rich demo with 15 entries |
| Willingness to act | 5/5 | If it saves 3 hours per memo, they'll use it immediately |

### The Quote
> "I have a Google Doc with 40 bullet points from different articles. I don't know which ones agree with each other. I'm going to spend 4 hours turning this into a coherent memo."

### Design Implications
- Extraction quality must be high — they'll notice if claims are wrong
- Citations matter — "which source said this?" must be answerable
- The synthesis draft is the killer feature for this persona (not the knowledge graph)
- They think in topics/projects, not a single global stream

---

## Secondary: The Active Learner

*"I'm taking a course, reading broadly, and I want my learning to actually stick and connect."*

### Who They Are
- **Roles:** Student in a professional course, self-directed learner, career switcher ramping on a new domain
- **Reading volume:** 5-15 sources/week across a learning arc (course materials + supplementary reading)
- **Output they produce:** Study notes, project deliverables, exam prep, "what I learned" reflections
- **Current workflow:** Read → take notes in a doc → forget which week covered what → cram before deadline

### The Pain (Specific)

| Moment | What Happens | Emotional State |
|---|---|---|
| Week 4 of a course | "What did we cover in Week 1 that connects to this?" | Lost, fragmented |
| Working on a capstone project | Needs to pull from 6 weeks of readings + research | Overwhelmed, starting from scratch |
| Studying for an assessment | "I know I read about this but I can't find it" | Anxious, inefficient |
| Trying to build expertise | Reads 30 articles over 2 months, can't articulate what they know | Discouraged |

### Jobs to Be Done
1. **Accumulate course + supplementary reading** into one queryable system
2. **See connections across weeks/topics** they wouldn't notice manually
3. **Query "what do I know about X?"** when working on a project
4. **Identify gaps** in their understanding before they're exposed

### Why BrainDrain Fits

| Dimension | Score | Why |
|---|---|---|
| Pain intensity | 4/5 | Real but time-bounded (course duration) |
| Agentic fit | 4/5 | Gap detection + contradiction surfacing helps learning |
| Demo-ability | 4/5 | Course reading = structured topic arc, great for demo |
| Willingness to act | 4/5 | Motivated learners adopt tools fast |

### The Quote
> "I've read 25 articles for this course. If you asked me to connect them into a coherent worldview, I'd stare at you blankly."

### Design Implications
- "Teach It Back" flashcards are especially relevant (V2)
- Gap Radar maps to "what should I study next?"
- The knowledge graph visually shows learning progression — motivating
- Lower bar for extraction quality — they're learning, not producing client deliverables

---

## Who We're NOT Building For (V1)

| Persona | Why Not Now |
|---|---|
| **Casual reader** (3 articles/week, no synthesis need) | Pain is too low. They don't need a tool — they're fine. |
| **Writer / journalist** (needs connection discovery more than contradiction detection) | Different core job. They want inspiration, not audit. V2. |
| **Investor / due diligence** (highest WTP, highest accuracy bar) | Needs financial data, named entities, compliance-grade citations. Too much for 6 weeks. |

---

## Persona → Feature Mapping

| Feature | Knowledge Worker | Active Learner |
|---|---|---|
| Smart Ingestion | Must-have | Must-have |
| Compounding Memory | Must-have | Must-have |
| Relationship Classification | **Core value** — this is why they use it | High value — helps connect course material |
| Knowledge Graph | High value — visual audit of topic coverage | High value — visual learning map |
| Synthesis Drafts | **Killer feature** — replaces 4 hours of memo writing | Useful for project deliverables |
| Source Credibility Signals | High value — "is my view based on research or opinion?" | Medium — less critical for learning |
| Gap Radar | High value — "what am I missing before I present?" | **Core value** — "what should I study next?" |
| Confidence Decay | Medium — useful for long research arcs | Lower — course material is recent |

---

## Decision: Build for the Knowledge Worker, Validate with the Learner

The knowledge worker is the **design target** — their pain is sharper, their deliverable is concrete, and contradiction detection is directly valuable to them.

The active learner is the **validation cohort** — we can recruit 3-5 course peers to test BrainDrain with their own reading. Their feedback tells us if the system works for a broader audience.

If BrainDrain works for someone writing a strategy memo from 15 articles, it works for a student synthesizing 15 course readings. The reverse isn't guaranteed.

---

*Next: [[03-why-agentic]] — why this requires an agent, not rules or a RAG pipeline.*
