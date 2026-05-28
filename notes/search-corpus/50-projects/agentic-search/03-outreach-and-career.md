---
type: note
project: agentic-search
tags:
  - type/reference
  - topic/career
  - topic/search
  - topic/networking
---

# Outreach and Career Strategy

## Speaker Profile — Tosh

**Current role:** Senior Engineering Manager, AI/ML Engineering — AI for Ads at Meta

**Previous experience:**
- Lyft — Pink Subscriptions
- Amazon — Computer Vision / ML

**Personal details (mentioned in Q&A):**
- Hiked Everest base camp, Kilimanjaro, and Patagonia (host joked about him not yet climbing in Yosemite)
- Has a new baby
- Writing a book on search (in the making, no title or release date mentioned)
- Planning to publish content via a blog as well
- Dropped his LinkedIn in the chat during the live session

**Note for outreach:** The host called him "Tosh" — this appears to be his known professional name. Use it naturally when reaching out. He was the sole speaker for the session, and the host's closing remarks suggest this was a well-regarded invite, not a casual appearance.

---

## Outreach Strategy for Tosh

### What to reference from the talk

Do not lead with generic compliments. Reference specific ideas that show you actually absorbed the material:

1. **"BM25 with an agent outperforms a complex neural network without one"** — This was his self-described "favorite benchmarking slide." He argued that backend predictability matters more than sophistication. This is a strong conversation starter because it's counterintuitive and opinionated.

2. **The four-tier economics of reasoning** — He laid out a cost/latency table: cached patterns (~10ms, near-free), distilled models (~50ms), single-pass agent (~200ms, moderate cost), full reasoning (~500ms, high cost). He called this "the economic backbone of agentic search." Ask him how teams decide the routing thresholds between tiers.

3. **"Retrieval becomes understanding"** — His closing philosophical point: the better search gets, the less it resembles search. He drew a line from retrieval to anticipation to ambient intelligence. This is the kind of forward-looking framing that invites real conversation.

4. **Hybrid relevance scoring as adaptive policy** — In the Q&A, he explained that hybrid scoring is not a fixed formula but an adaptive policy where weights shift across regimes. He gave specific guidance: LLM relevance as prior (not ground truth), CTR/dwell as high-signal-high-variance, negative feedback as low-frequency-high-precision with veto power.

5. **Composable tools vs. monolithic API** — He contrasted a single search endpoint with dozens of parameters (brittle for LLMs) against atomic, transparent functions (keyword search, semantic search) that serve as agent primitives. This maps directly to how you think about tool design at Walmart.

### How to position yourself

- You work on "create decisions" at Walmart — this is fundamentally a ranking and relevance problem at retail scale
- You are building toward search engineering at companies like Meta or Google
- Frame yourself as someone actively studying the field, not passively consuming content — mention that you are building projects, writing about search concepts, and mapping the technical landscape
- Do not overstate your current depth; instead emphasize trajectory and genuine curiosity

### Draft LinkedIn message

> Hi Tosh — I watched your talk on agentic search (the one hosted on YouTube) and wanted to reach out. Two things stuck with me in particular:
>
> First, the benchmarking insight that BM25 paired with an agent outperforms a complex neural net without one. That reframing — that the backend needs to be predictable, not fancy — changed how I think about tool design in my own work.
>
> Second, your four-tier economics table for reasoning (cached patterns through full reasoning loops). I work on create decisions at Walmart, which is essentially a ranking and relevance problem for product recommendations, and I've been thinking about how to apply similar cost-aware routing to our retrieval pipeline.
>
> I saw you mentioned a book in the works on search — I'd love to follow along when that's available. Would also be happy to share what I'm learning as I map out the agentic search landscape from a practitioner's perspective.
>
> Either way, really appreciated the depth of the talk. Thanks for putting it out there.

**Why this works:**
- References two specific, non-obvious points from the talk
- Connects his ideas to your real work (create decisions as ranking)
- Mentions the book (gives him something to respond to)
- Does not ask for a job, a referral, or a call — just opens a door
- Tone is peer-curious, not fan-worship

### Follow-up angles

- **His book:** When he announces it, be one of the first to engage. Offer to review a chapter or share it with your network.
- **His blog:** Subscribe and comment substantively on early posts. Early readers of new blogs get disproportionate attention from the author.
- **Technical questions to revisit:**
  - How does he handle evaluation of agent trajectories in production (convergence rate, strategy diversity, information gain per iteration)?
  - What does the Flink-based query routing layer look like in practice at Meta?
  - How does hybrid relevance scoring handle cold-start users with no behavioral signals?
- **Shared content:** If you publish an article on any of the topics from his talk (see writing ideas below), share it with him directly and ask for feedback.

---

## Broader Industry Outreach Plan

### Target companies and teams

| Company | Relevant teams | Why it maps |
|---------|---------------|-------------|
| **Google** | Search ranking, Google Ads, Google Shopping | Core search at the largest scale; your Walmart product ranking experience is directly relevant |
| **Meta** | AI for Ads (Tosh's team), Instagram/Facebook search, recommendation systems | Tosh's talk is your entry point; recommendation and search converge here |
| **Pinterest** | Visual search, home feed ranking, shopping recommendations | Product discovery with strong visual/intent signals — close to retail |
| **Spotify** | Search and recommendations, podcast discovery | Multi-modal retrieval (audio, text, behavioral) with personalization |
| **Netflix** | Search and recommendations, content understanding | Ranking under ambiguity; their published research is accessible |
| **Airbnb** | Search ranking, pricing optimization | Two-sided marketplace search — structurally similar to retail |
| **Amazon** | Product search (A9/COSMO), Alexa, Ads | You already understand the retail domain; Amazon search is the most direct analog |

### Writing ideas (Substack / LinkedIn articles)

These are derived directly from concepts in Tosh's talk, positioned through your Walmart lens:

1. **"Your search backend doesn't need to be fancy — it needs to be predictable"** — Riff on Tosh's BM25-vs-neural-net insight. Use a Walmart example of when a simpler, more transparent approach outperformed a complex one.

2. **"The economics of reasoning in search"** — Break down the four-tier cost model. Map it to how retail search could route queries: simple product lookups go to cache, ambiguous "gift for dad" queries get full reasoning.

3. **"From create decisions to query understanding: what retail taught me about search"** — Position piece that bridges your Walmart work to the search industry. Explain what "create decisions" actually means and why it is a ranking problem.

4. **"Why negative feedback should have veto power in your ranking system"** — Based on Tosh's Q&A answer about hybrid scoring. Discuss the asymmetry between positive and negative signals.

5. **"Search is dissolving into understanding — what that means for product discovery"** — Take his philosophical closing and apply it to e-commerce. How does anticipatory search change retail?

6. **"Evaluating agentic search: convergence rate, strategy diversity, and information gain"** — Technical deep-dive on the evaluation framework Tosh described. Show you can think about measurement, not just architecture.

### How to position Walmart experience in outreach

When reaching out to anyone in the search industry, frame your Walmart work using their vocabulary:

- Do not say: "I work on product recommendations at Walmart"
- Say instead: "I work on ranking and relevance for product retrieval at Walmart scale — essentially deciding what surfaces to users given partial intent signals and a massive document corpus"

Key translation phrases:
- "Create decisions" → "real-time ranking under ambiguity"
- "Product catalog" → "document corpus with structured metadata"
- "Customer intent modeling" → "query understanding with underspecified input"
- "Personalization" → "user-adaptive retrieval with behavioral signals"

---

## Bridge: Walmart to Search Industry

This section maps your current Walmart work to search concepts discussed in the talk. Use this as a reference when writing articles, preparing for interviews, or framing outreach messages.

| Walmart domain | Search industry concept | Connection |
|----------------|----------------------|------------|
| **Create decisions** | Ranking and relevance | Both involve scoring candidates (products or documents) against inferred user intent and surfacing the best result. At Walmart, you are solving the same core optimization: given a user signal, what is the most relevant item to surface? |
| **Product catalog** | Document corpus | A product catalog is a structured document corpus. Product attributes (title, description, category, price) are analogous to document fields. Index design, schema evolution, and data freshness are shared challenges. |
| **Customer intent** | Query understanding | Walmart customers express partial intent — "gift for mom," "cheap laptop" — just like Tosh's "Python memory thing from last week" example. Both require entity extraction, intent classification, and disambiguation. |
| **Personalization** | User-adaptive search | Walmart's personalization (purchase history, browsing behavior, location) maps to behavioral signals in search — CTR, dwell time, session context. The hybrid relevance scoring Tosh described (LLM prior + behavioral feedback + human correction) is structurally identical to what retail recommendation systems do. |
| **Supply chain optimization** | Retrieval economics | Walmart's supply chain balances cost, speed, and availability — the same tradeoffs Tosh described in his four-tier reasoning economics (cache vs. distilled vs. single-pass vs. full reasoning). Both are resource allocation problems under latency constraints. |
| **A/B testing at scale** | Evaluation of agent paths | Walmart runs experiments on recommendation changes; search teams evaluate retrieval quality via convergence rate, strategy diversity, and information gain per iteration. The methodology transfers. |
| **Multi-channel (app, web, store)** | Multi-modal retrieval | Serving users across channels with different context signals is analogous to multi-modal search (text, voice, visual). The orchestration challenge is shared. |

---

## Action Items

1. **Send LinkedIn connection request to Tosh** — Use the draft message above. Personalize further if you find his LinkedIn profile and see recent posts or activity to reference. *Target: this week.*

2. **Find and bookmark Tosh's LinkedIn and any existing blog** — Check if the blog is already live. If so, subscribe and leave a substantive comment on the most recent post. *Target: this week.*

3. **Write your first article: "From create decisions to query understanding"** — This is your positioning piece. Publish on LinkedIn or Substack. Share it with Tosh when you reach out or as a follow-up. *Target: within 2 weeks.*

4. **Build a small agentic search demo project on GitHub** — Implement a minimal version of the architecture Tosh described: query understanding → strategy selection → multi-backend retrieval → confidence-based termination. Use BM25 as the backend (his own recommendation). *Target: within 4 weeks.*

5. **Identify 5-10 people at target companies to reach out to** — Use LinkedIn to find engineering managers and senior ICs on search/ranking/recommendations teams at Google, Meta, Pinterest, Spotify, Netflix, Airbnb, Amazon. Draft outreach messages using the framing from this note. *Target: within 3 weeks.*

6. **Write a second article on one of the technical topics** — Pick from the writing ideas list above. The economics of reasoning or the BM25-agent benchmarking insight are strongest for generating engagement. *Target: within 4 weeks.*

7. **Set up alerts for Tosh's book and blog announcements** — Follow him on LinkedIn, check periodically for updates. Being an early reader and commenter builds a real connection. *Target: ongoing.*

8. **Prepare a "Walmart to search" elevator pitch** — Using the bridge table above, write a 30-second version and a 2-minute version of how your Walmart experience translates to search engineering. Practice it. Use it in informational calls and interviews. *Target: within 2 weeks.*

9. **Study the technical foundations referenced in the talk** — BM25/TF-IDF, vector embeddings and KNN, Flink streaming, Temporal workflow orchestration, hybrid retrieval architectures, position-normalized click models. Build a study plan in the vault. *Target: start this week, ongoing.*

10. **Revisit this note monthly** — Update with new contacts, articles published, responses received, and evolving strategy. *Target: first review mid-May 2026.*
