---
tags:
  - type/session
  - topic/search
  - topic/agents
  - status/seed
created: 2026-04-19
parent: "[[2026-04-18-search-flow-chunked-v1]]"
---

# Steelman: Search Flow Chunked v1

> Multi-lens analysis of the chunked build plan. Five research agents attacked the plan from different angles: CLI tool landscape, LLM scoring patterns, PKM integration, delivery strategy, and competitive intelligence. This document synthesizes their findings into actionable upgrades.

---

## The One Thing Every Lens Agreed On

**Add query decomposition before fan-out.** The plan currently fans the raw user query to Brave + GitHub simultaneously. Every successful research tool — Perplexity, gpt-researcher, STORM — decomposes the query into 3-5 sub-questions first, then fans out per sub-question. This is the single highest-impact architectural gap.

**Tactical fix:** Insert a lightweight planner call between user query and fan-out in A2. One LLM call (small/fast model via OpenRouter), structured output: `{ subQueries: string[] }`. Cost: ~$0.001. Time: ~1s. Quality uplift: massive. This transforms flat breadth into structured depth.

---

## Lens 1: CLI AI Tool Landscape

### What's Actually Working (2025-2026)

| Tool | Key Architectural Pattern | Relevance to Plan |
|------|--------------------------|-------------------|
| **Perplexity (Sonar API)** | Hybrid retrieval with multi-stage reranking. Retrieves at sub-document level, not whole pages. Staged scoring: fast embedding scorers first, cross-encoder rerankers last. | The plan should score in stages, not one monolithic LLM batch call |
| **fabric** (Daniel Miessler) | Composable prompt patterns as markdown files, Unix-piped together. 200+ patterns, 300 contributors. Succeeded on developer ergonomics, not retrieval quality. | The plan lacks a composability/customization layer — patterns-as-files |
| **gpt-researcher** | Planner→executor→publisher with parallel fan-out. Decomposes query into sub-questions, fans out parallel crawler agents per sub-question. SourceCurator ranks by credibility. | Query decomposition before fan-out is the consensus architecture |
| **Tavily** | Pre-structured JSON output shaped for LLM consumption. ~998ms avg latency. Acquired by Nebius for up to $400M. | LLM-ready structured responses reduce token waste vs raw Brave HTML |
| **Exa** | End-to-end transformer embeddings over proprietary web-scale index. "Highlights" feature returns only relevant paragraphs, cutting token budgets 50%+. | Semantic search beats aggregating third-party APIs when precision matters |
| **Phind/Devv** | Code-aware ranking with version detection. Devv indexes GitHub issues + discussions. | Developer-specific source integration outperforms general search for technical queries |

### Alignment with the Plan

| Pattern                                    | Plan Status                                          |
| ------------------------------------------ | ---------------------------------------------------- |
| Query decomposition → parallel fan-out     | ❌ **Missing — biggest gap**                          |
| Composable prompt patterns (files)         | ❌ **Missing — no customization layer**               |
| LLM-ready structured JSON from search APIs | ⚠️ Plan uses Brave (raw HTML links) — more glue code |
| Source abstraction interface               | ✅ Plan has this (A2)                                 |
| Trace logging of scores                    | ✅ **Differentiator** — most tools hide scoring       |
| Interactive REPL session                   | ✅ **Genuine whitespace** — nobody does this well     |

### Key Divergences

1. **No query decomposition before fan-out (HIGH RISK).** Without a planner stage, "brain" gets breadth without depth. Fix: add to A2.
2. **Brave Search instead of Tavily/Exa (MODERATE RISK).** Brave returns raw HTML links requiring scraping. Tavily/Exa return pre-structured JSON. For a solo dev, the engineering overhead of Brave parsing may not be worth the cost savings. Consider Tavily as a source alongside or instead of Brave.
3. **No composability layer (RISK for growth).** fabric's 300-contributor ecosystem grew because patterns are markdown files anyone can write. Without composable, shareable research patterns, "brain" stays a single-user tool.
4. **Interactive REPL session (STRENGTH).** None of the six tools above offer a persistent interactive comparison session. This is where "brain" carves real territory.
5. **Vault as knowledge base (STRENGTH).** No existing tool cross-references external search against a local Obsidian vault. Strongest differentiator.

---

## Lens 2: LLM Scoring Tactics

### Batch Scoring Is Correct

The plan's A3 approach to batch scoring is sound. Real numbers:

| Configuration | Cost per Search | Latency | Verdict |
|--------------|----------------|---------|---------|
| 20 results, small/fast model (e.g. Haiku-class via OpenRouter) | ~$0.004 | 1-1.5s | ✅ Ideal for scoring |
| 20 results, mid-tier model (e.g. Sonnet-class) | ~$0.045 | 2-3s | ✅ Feasible |
| The <3 second target | — | — | ✅ Realistic with fast models |

**Token math:** Each snippet ~150 words = ~200 tokens. 20 snippets = 4,000 tokens input. System prompt + instructions: ~800 tokens. Output with reasoning: ~2,000 tokens. Total: ~6,800 tokens per batch. Trivially cheap.

### Three Patterns to Steal

1. **Rubric anchoring** — Include 3-4 calibration examples in the scoring prompt. "0.9 means: directly answers the query with primary evidence. 0.5 means: tangentially related, different focus. 0.2 means: shares keywords but different domain." Without anchors, LLMs cluster scores in 0.6-0.8 and fail to discriminate.

2. **Chain-of-thought BEFORE the score** — Force a 1-2 sentence `reasoning` field before the `score` field in the JSON schema. The Vercel AI SDK's `generateObject` with a Zod schema that orders `reasoning` before `score` gets this for free. Improves calibration ~10-15%.

3. **Judge model pattern** — Use a small/fast model for scoring, reserve capable models for synthesis (A5 compare step). Scoring is a classification task — smaller models handle it well.

### Biggest Risk: Calibration Drift

Score distributions shift when models update. The rubric-anchored prompt with explicit examples is the defense. Also: **log user implicit feedback** (which results they clicked, compared, skimmed, queued, ingested). After 100-200 searches, this creates a real eval dataset to measure drift.

### Model Strategy: OpenRouter + Free Models for Testing

Per user direction: use OpenRouter as the API gateway for all model calls. During development and testing, use free-tier models available through OpenRouter. This means:
- Scoring prompts should work across model quality levels (rubric anchoring helps here)
- The Vercel AI SDK supports OpenRouter as a provider — use it from A1
- Quality will be lower during testing but the flow/plumbing gets validated
- When ready for production quality, swap to paid models by changing the OpenRouter model ID — no code changes

---

## Lens 3: PKM × Search Integration

### The Novelty Column Is Genuinely Novel

**No Obsidian plugin does vault-aware external search cross-referencing.** Smart Connections does semantic similarity within the vault. Omnisearch does BM25 within the vault. Neither takes external search results and flags "you already know this." Khoj comes closest — it can search web + vault — but doesn't produce a novelty column.

### Vault Indexing: The Right V1 Call

| Approach | Speed (500 files) | Quality | Complexity |
|----------|-------------------|---------|------------|
| URL exact match | Milliseconds | High precision, low recall | Trivial |
| MiniSearch (JS BM25) | 1-3 seconds | Good for PARTIAL detection | Low |
| Local embeddings | 5-10 seconds | Best semantic matching | Medium |
| Hybrid | 5-10 seconds | Best overall | High |

**Verdict:** URL match + MiniSearch BM25 is the right v1. Steal Omnisearch's MiniSearch integration pattern — proven, fast, JS-native, handles BM25 indexing in a few hundred lines. <10 seconds for 500 files is conservative by 3-5x.

### Biggest Trap: False Positives on PARTIAL

A BM25 score of 0.3 might mean "shares common words" not "you know this." Marking something IN VAULT when it's actually new destroys trust fast.

**Rule:** Threshold conservatively. Default to NEW when uncertain. A missed IN VAULT is annoying; a false IN VAULT erodes the tool's core promise.

### One Thing to Steal: Tana's Structured Note Types

When cross-referencing the vault, weight matches differently by note type. A match in a curated reference note (`20-notes/`) means more than a passing mention in a daily journal (`01-daily/`). The vault's folder structure already encodes this — use it.

---

## Lens 4: Solo Dev Delivery Strategy

### Outside-In Is Correct — With a Caveat

The outside-in strategy works when you have strong taste about UX and use the tool yourself immediately. If A1 ships and you don't start using `brain search` for your own real questions the next day, the feedback signal dies.

### Chunk Assessment

| Chunk | Weekend-buildable? | "Usable day 1" realistic? | Risk |
|-------|-------------------|--------------------------|------|
| A1: Single-source search | ✅ Yes | ✅ Yes | Low |
| A2: Multi-source fan-out + query decomposition | ✅ Yes | ✅ Yes | Low |
| A3: LLM scoring columns | ✅ Yes (if you resist building a scoring framework) | ✅ Yes | Medium — scope creep on scoring prompts |
| A4: Vault cross-reference | ⚠️ Tight | ⚠️ Only if scoped narrowly | HIGH — "cross-reference" invites scope creep |
| A5: Interactive REPL session | ⚠️ Tight | ⚠️ Only as thin wrapper over existing commands | Medium — interactive edge cases |

### Strategic Recommendation: Consider Swapping A4 ↔ A5

Build the full external research workflow first (A1→A2→A3→A5-thin), live in it for weeks, then add vault integration informed by real usage. You'll build a better A4 after you've done 50 real searches and know what "cross-reference" actually needs to mean.

However: the REPL flow is also central to the whole UX vision (per user input). The key is that A5 should be a **convenience layer on top of one-shot commands**, not a separate system. One-shot + piping for automation, REPL for exploration sessions.

### Stack Verdict

- **Bun + TypeScript + Commander.js** = ✅ Correct. No notes.
- **OpenRouter as API gateway** = ✅ Gives model flexibility, free testing, easy production swap.
- **Vercel AI SDK** = ✅ Handles provider abstraction, structured output, streaming.
- Resist Rust (iteration speed), resist oclif (overengineered), resist LangChain (abstraction tax).

### API Key Management

Use environment variables as primary, with a config file at `~/.config/brain/.env` as convenience. Add `brain config set <key> <value>` as sugar. Don't use system keychain — not worth the complexity.

---

## Lens 5: Steal-Worthy Patterns

### One Pattern Per Category

| Tool Category | Tool | Pattern to Steal | For Which Chunk |
|--------------|------|-----------------|----------------|
| Deep research agents | Perplexity | Per-claim citation granularity (cite specific facts, not whole sources) | A3, A5 |
| Developer research | Kagi | User-defined "lenses" — named search scope configs stored as files | A2 |
| CLI-native AI | fabric | Patterns-as-markdown-files composability | Future — but design for it |
| PKM AI tools | Tana | Structured note types — weight vault matches by note type | A4 |
| Open-source research | gpt-researcher | Parallel sub-question decomposition before fan-out | A2 |

### The Whitespace Is Real

Nobody does "search that diffs against what you know." Perplexity treats everyone as a blank slate. Notion AI can't search the web. Mem.ai tried to bridge this and failed.

**The killer output isn't "here's a summary" — it's "here are 3 things that contradict or extend what's in your vault, and here are 2 things you already know that the search results got wrong."**

### The Anti-Pattern That Kills AI Search Tools

**"Demo magic, daily disappointment."** Stunning 30-second demo → users get 2 bad results in 5 tries → back to Google + ChatGPT. Tools that survive (Perplexity, Phind, Kagi) invested in source transparency and consistent reliability over flashy one-shot quality.

**Defense:** Build trust mechanics from A1. Citations, confidence scores, "I don't know" signals, trace logging. Users forgive low quality when they can see why and verify sources. They don't forgive confident wrong answers.

---

## Decisions Made This Session

### 1. Query Decomposition Added to A2

A lightweight planner call decomposes the user's query into 3-5 sub-questions before fan-out. This is the consensus architecture across Perplexity, gpt-researcher, and STORM. Added to A2 scope.

### 2. Model Strategy: OpenRouter + Free Models for Testing

All LLM calls go through OpenRouter. During development/testing, use free-tier models. Production quality comes from swapping model IDs, not code changes. The scoring prompts use rubric anchoring to work across model quality levels.

### 3. Twitter/X as a Source

Added to the source list. The Twitter/X API (now X API) has a free tier that allows basic search — limited but usable for testing. The user will authenticate with their own account. Twitter is valuable for real-time discourse, hot takes, and emerging patterns in the AI/agents space.

**API access note:** The X API free tier (as of 2026) provides limited read access. For testing, this is sufficient. If rate limits become a problem, consider scraping via Brave Search with `site:x.com` as a fallback.

### 4. REPL Flow Is Central

The interactive session is not a nice-to-have — it's the core UX. Build one-shot search first (A1-A3), then the REPL as a session wrapper. Key commands within a session:

- `compare 1 3 5` — side-by-side comparison
- `skim 3` — drill into a single result
- `queue 1 5` — save for later processing
- `refine "graph memory vs summary memory"` — narrow the search
- Free-form prompts after first turn — the session has context

Additional flows to design for (not all in A5, but the architecture should enable):
- **Assisted search:** A planner agent asks follow-up questions to refine the query before executing
- **Batch select:** User likes all results in a category, selects the category
- **Quick add:** User likes top 3, immediately selects from output
- Build the foundation for extensibility — we can't map every flow yet, but the session state model should support them

### 5. Sources for V1

Priority sources for the search experience, focused on AI/agents/SDLC learning:

| Source | API | Priority | Notes |
|--------|-----|----------|-------|
| Brave Web | Brave Search API | A1 | General catch-all |
| GitHub | GitHub Search API | A2 | Repos, READMEs, discussions |
| Twitter/X | X API (free tier) | A2 | Real-time discourse, takes |
| HuggingFace | HF API | A2-A3 | Papers, models, datasets |
| Substack | Via Brave `site:` filter | Future | No public API — proxy through Brave |
| ArXiv | ArXiv API | Future | Academic papers |

---

## Refined Build Sequence

```
A1 ─────► A2 ─────────────► A3 ─────► A4 ─────► A5
single    multi-source       scoring   vault      REPL
source    fan-out +          columns   cross-ref  session
search    query decomp       + LLM     + novelty  + compare
          + Twitter/GitHub

│         │                  │         │          │
│ proves: │ proves:          │ proves: │ proves:  │ proves:
│ plumbing│ source abstrac-  │ LLM     │ internal │ research
│ works   │ tion + sub-query │ scoring │ + extern │ workstation
│         │ decomposition    │ works   │ connected│ UX
│         │ works            │         │          │
▼         ▼                  ▼         ▼          ▼
usable    usable             usable    usable     usable
day 1     day 1              day 1     day 1      day 1
```

**Key change from v1:** A2 now includes query decomposition (the planner call) and adds GitHub + Twitter/X as sources. This is the most impactful upgrade — it transforms flat breadth into structured depth.

---

## What This Steelman Did NOT Change

- The overall 5-chunk decomposition is sound. Each chunk proves a distinct capability.
- The outside-in strategy is correct.
- The Bun + TypeScript + Commander.js + Vercel AI SDK stack is right.
- The vault cross-reference as the core differentiator is confirmed by competitive analysis.
- The inside-out build order (search → score → compare, not ingestion → search) is validated.

---

## Top 5 Tactical Upgrades (Ranked by Impact)

1. **Add query decomposition to A2** — One small-model call, ~$0.001, ~1s. Split query into 3-5 sub-questions before fan-out.
2. **Use rubric-anchored scoring prompts in A3** — Include calibration examples. Chain-of-thought before score. Use fast model for scoring, capable model for synthesis.
3. **Threshold PARTIAL conservatively in A4** — Default to NEW when BM25 score is ambiguous. Trust > coverage.
4. **Add user-defined search lenses** — Named config files (`~/.config/brain/lenses/ai-agents.yaml`) that define source filters. Steal from Kagi. Trivial to implement, immediately personal.
5. **Design for composability** — Even if not building fabric-style patterns yet, make each pipeline stage (search, score, compare, cross-reference) a composable unit that can be piped or customized.

---

*This steelman was produced by 5 parallel research agents analyzing the plan from different angles: CLI tool landscape, LLM scoring patterns, PKM integration, delivery strategy, and competitive intelligence. The findings are synthesized above with specific tactical recommendations.*
