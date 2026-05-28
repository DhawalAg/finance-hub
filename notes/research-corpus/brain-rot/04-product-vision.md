---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# Product Vision & Architecture

> A knowledge agent that extracts, connects, reasons, and synthesizes — so you don't have to.

---

## What We're Building

BrainDrain is a local-first personal knowledge agent. You feed it what you read. It turns scattered articles into a structured, queryable, self-connecting knowledge base that gets smarter the more you use it.

**V1 ships with 8 capabilities across two tiers:**

### Core (Must Ship — the thesis)
1. **Smart Ingestion** — paste a URL or text, agent extracts structured knowledge cards
2. **Compounding Memory** — persistent knowledge base that grows over time
3. **Relationship Classification** — agent labels connections: supports, contradicts, extends
4. **Knowledge Graph** — directed relationship map between entries

### Stretch (High Impact, Low Cost — the elevation)
5. **Synthesis Drafts** — structured memo output, not chat-style answers
6. **Source Credibility Signals** — primary research vs. analysis vs. opinion vs. aggregation
7. **Gap Radar** — proactive identification of blind spots in your coverage
8. **Confidence Decay** — temporal awareness: flags when core sources are stale

---

## How It Works: The Two Loops

### Loop 1: Ingestion (runs every time you add content)

```
User pastes URL or text
       ↓
┌─────────────────────────────────────────────────┐
│  EXTRACT                                         │
│  LLM reads the content and pulls out:            │
│  • 3-7 key claims (specific, falsifiable)        │
│  • Main argument (author's central thesis)       │
│  • Domain tags (auto-generated)                  │
│  • Source type (research / analysis / opinion)    │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  SEARCH                                          │
│  Embedding model finds top 10 similar entries    │
│  from existing knowledge base                    │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  REASON  ← This is the agentic step             │
│  LLM compares new entry against each match:      │
│  • SUPPORTS — new evidence for existing claim    │
│  • CONTRADICTS — direct conflict (cites both)    │
│  • EXTENDS — adds new angle to existing topic    │
│  • UNRELATED — similar topic, no real link        │
│  Assigns confidence score (0.0-1.0) per link     │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  DECIDE                                          │
│  Agent chooses:                                  │
│  • Standalone card (no strong connections)        │
│  • Linked card (1-3 relationships found)         │
│  • Flagged card (high-confidence contradiction)   │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  STORE                                           │
│  KnowledgeCard → SQLite                          │
│  Relationships → SQLite (from_id, to_id, type)   │
│  Embedding → vector index                        │
└─────────────────────────────────────────────────┘
```

**User sees:** A knowledge card with extracted claims, auto-tags, and a list of connections — including any contradiction badges.

### Loop 2: Query (runs when user asks a question)

```
User asks: "What do I know about X?"
       ↓
┌─────────────────────────────────────────────────┐
│  STRATEGIZE                                      │
│  LLM generates 3-5 search angles                │
│  (not one keyword — a search strategy)           │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  RETRIEVE                                        │
│  Vector search each angle → top 5 cards each    │
│  Deduplicate results                             │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  ENRICH                                          │
│  Pull relationship edges between retrieved cards │
│  Check for CONTRADICTS links in the result set   │
│  Check source ages (confidence decay)            │
│  Check source types (credibility signals)        │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  SYNTHESIZE                                      │
│  LLM writes a structured response:               │
│  • Summary of what you know (with citations)     │
│  • Schools of thought / themes                   │
│  • Conflicts flagged explicitly                  │
│  • Gaps identified                               │
│  • Source credibility breakdown                  │
│  • Staleness warnings if applicable              │
└─────────────────────────────────────────────────┘
```

**User sees:** A synthesis memo — not a chat bubble. Organized by themes, with cited sources, flagged conflicts, and identified gaps.

---

## Data Model

Minimal. Two tables. That's the whole schema for V1.

```sql
CREATE TABLE knowledge_cards (
  id            TEXT PRIMARY KEY,
  source_url    TEXT,
  source_type   TEXT,       -- 'research' | 'analysis' | 'opinion' | 'aggregation'
  raw_text      TEXT,
  main_argument TEXT,
  claims        TEXT,       -- JSON array of claim strings
  tags          TEXT,       -- JSON array of tag strings
  embedding     BLOB,
  created_at    DATETIME
);

CREATE TABLE relationships (
  id            TEXT PRIMARY KEY,
  from_card_id  TEXT REFERENCES knowledge_cards(id),
  to_card_id    TEXT REFERENCES knowledge_cards(id),
  rel_type      TEXT,       -- 'SUPPORTS' | 'CONTRADICTS' | 'EXTENDS'
  explanation   TEXT,       -- LLM-generated: why this relationship exists
  confidence    REAL,       -- 0.0 to 1.0
  created_at    DATETIME
);
```

**Why this works:**
- Two tables can express a full knowledge graph
- JSON fields for claims and tags keep the schema flat
- Relationship table is the product differentiator — this is where "agentic" lives
- SQLite is fast, local, zero-config, works great for single-user

---

## Tech Stack

| Layer | Choice | Why | Cost |
|---|---|---|---|
| **Frontend** | Next.js on Vercel | Fast to build, good DX, free hosting | Free |
| **LLM** | Ollama (Qwen3 / Llama 3.1) | Local, private, zero API cost | Free |
| **Embeddings** | Ollama embedding model | Consistent with LLM stack | Free |
| **Storage** | SQLite | Simple, no server, portable | Free |
| **Vector Search** | sqlite-vss or LanceDB | Lightweight, local | Free |
| **URL Parsing** | Mozilla Readability | Best OSS article extractor | Free |
| **Deployment** | Local-first | No infra cost, privacy by default | Free |

**Total cost: $0.** The entire stack runs on a laptop.

**Fallback:** If Ollama quality is insufficient for relationship reasoning (the hardest task), use OpenAI API for that one step only (~$0.01/ingestion). Everything else stays local. This is a product decision, not a compromise — users choose: local (free, private, ~85% accuracy) or cloud (paid, ~95% accuracy).

---

## The User Experience (Simplified)

### Adding Knowledge
1. Open BrainDrain
2. Paste a URL or text into the input bar
3. Wait 5-10 seconds
4. See: knowledge card with extracted claims, auto-tags, source type badge
5. See: connection badges — "Extends Entry #12" or "⚠️ Contradicts Entry #7 — click to see"

### Querying Knowledge
1. Type: "What do I know about content moderation?"
2. Wait 5-15 seconds
3. See: structured synthesis memo
   - 3 themes identified across 8 sources
   - 1 conflict flagged with specific claims cited
   - 1 gap noted: "No sources on appeal processes"
   - Credibility breakdown: 2 research, 4 analysis, 2 opinion
   - Staleness note: oldest source is 14 months old

### The "Whoa" Moment
Entry #1-5: Normal. You add articles, get structured cards. Fine.
Entry #6: You add an article that **contradicts** Entry #2. The system flags it: "⚠️ This contradicts your earlier entry on [topic]. Entry #2 claims X. This article claims Y."

That moment — the system catching something you missed — is the product.

---

## V1 → V2 Arc

| Version | What Ships | What It Proves |
|---|---|---|
| **V1 Core** | Ingestion loop + query loop + knowledge graph | The reasoning loop creates value that RAG alone doesn't |
| **V1 Stretch** | Synthesis drafts + credibility signals + gap radar + confidence decay | The agent can be proactive, not just reactive |
| **V2** | "What Changed?" dashboard, Perspective Tracker, Teach It Back | The system becomes a daily-use advisor, not just a tool |
| **V3** | Multi-user, shared knowledge bases, RSS auto-ingest | Collaboration and scale |

**V1's job is to prove one thing:** when you add a reasoning loop to a retrieval pipeline, you unlock a category of insight that no existing tool provides. Everything after V1 is scaling that insight.

---

*Next: [[05-metrics-and-eval]] — how we measure success. [[06-build-plan]] — the 6-week plan.*
