---
tags:
  - type/reference
  - topic/agents
  - topic/ai
  - topic/search
  - status/seed
created: 2026-04-18
source: https://www.reddit.com/r/LLMDevs/comments/1mwdaus/my_experience_with_agents_realworld_data_search/
---

# Real-World Data Search Pain Points for AI Agents

> Community signal from r/LLMDevs on why search and retrieval — not model quality — is the bottleneck for agent performance.

---

## Core Thesis

**Better prompting and longer context windows don't matter if your context is weak, partial, or missing entirely.**

The most limiting factor for AI agents isn't the models — it's the *how and what* data we feed them. Once you move from synthetic/benchmark data to real-world context (research papers, web content, financial data), the cracks appear fast.

---

## Pain Points by Data Domain

### Web Search
- Results are **shallow with massive bloat** — headlines and links, not full source content
- Not the right section, not in a usable format
- If the agent needs to extract reasoning from web results, it doesn't work well and isn't token-efficient

### Academic Content
- Open science exists but is scattered
- Current papers in niche domains are **locked behind paywalls** or only available via abstract-level APIs
- [[Semantic Scholar]] is useful but limited to abstracts for many papers

### Financial Documents
- **EDGAR** filings are nightmarish — hundreds of thousands of lines of XML, sections scattered across exhibits/appendices
- You can't just "grab the management commentary" without an extremely sophisticated parser
- Inconsistency across document structures makes general-purpose extraction unreliable

---

## The Second-Order Problem

> Most retrieval APIs aren't designed for LLMs. They're designed for humans to click and read, not to parse and reason.

This is the key insight for our second brain: the search layer must return **LLM-ready content**, not human-browsable results.

---

## Tools & APIs Being Evaluated (as of mid-2025)

| Tool | Focus | Strengths | Weaknesses |
|------|-------|-----------|------------|
| **Valyu** | Web search API purpose-built for AI | Most reliable for getting information AI actually needs; strong for finance + general search | Newer, still being evaluated |
| **Tavily** | General web search for AI | Fast, easy to use; has page mapping + content extraction features | More general-purpose, less depth |
| **Exa** | Niche content / "RAG-the-web" | Good for finding niche content | Freshness issues (news); content can be messy with missing sections or raw HTML tags |

---

## Approaches People Are Taking

1. **Plugging in search APIs** (Valyu, Tavily, Exa)
2. **Writing custom parsers** — parsing filings into structured JSON, extracting full sections, cleaning web pages before ingestion
3. **Building vertical-specific pipelines** — domain-tuned retrieval for finance, legal, academic, etc.
4. **Using RAG frameworks** — LangChain, RAG-as-a-service platforms

The community consensus: the **custom preprocessing layer** (parsing, cleaning, structuring before ingestion) yields the biggest quality improvements.

---

## Implications for Second Brain Search

This validates several design choices for our project:

1. **Search quality > model quality** — invest heavily in the retrieval and preprocessing layer
2. **Return structured, LLM-ready content** — not links, not raw HTML, not abstracts
3. **Domain-aware parsing matters** — a single generic search layer won't cut it for high-stakes domains
4. **Freshness is a real concern** — especially for news and fast-moving domains; the search layer needs recency awareness
5. **Users are frustrated** — there's a real gap in the market for a better search experience that understands what the AI (and the human) actually needs

> This is the user pain we should be solving: people are building their own retrieval infrastructure because nothing off-the-shelf works well enough for agent-quality context.

---

## Related

- [[50-projects/second-brain/main/02-architecture]] — System design for the knowledge agent
- [[rag-implentations]] — RAG implementation notes
