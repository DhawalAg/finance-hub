---
type: note
project: brain-rot
tags:
  - type/project
  - topic/product-management
  - topic/agents
---

# Risks & Mitigations

> Every 6-week project has 2-3 risks that can kill it. Know them early, test them first, have a fallback.

---

## Risk Severity Framework

| Level | Meaning |
|---|---|
| 🔴 **Critical** | Kills the product thesis if not resolved |
| 🟡 **Significant** | Degrades the demo or user experience meaningfully |
| 🟢 **Manageable** | Annoying but solvable with a workaround |

---

## The Risk Register

### 🔴 Risk 1: Local LLM Can't Do Relationship Reasoning

**What:** Ollama models (Qwen3-8B, Llama 3.1-8B) can't reliably classify supports/contradicts/extends across two article summaries. This is a cognitively demanding task — nuance matters.

**Impact:** Fatal. Without relationship reasoning, BrainDrain is just Open Notebook with a simpler stack. The entire product thesis fails.

**Likelihood:** Medium. 8B models struggle with nuance. 14B+ models are better but slower.

**Detection:** Week 1. The test set of 10 article pairs gives a clear accuracy signal.

**Mitigations:**
1. Test multiple models in Week 1 (Qwen3-8B, Qwen3-14B, Llama 3.1-8B, Llama 3.1-70B)
2. If local models score <60%: use OpenAI API for relationship reasoning only (~$0.01/ingestion)
3. If all models fail: simplify to "agreement clustering" (group similar content) and reposition as "knowledge synthesis" rather than "contradiction detection"
4. Frame the local-vs-cloud choice as a product feature: "Choose privacy (local) or precision (cloud)"

**Status:** Must resolve in Week 1. No build work starts until this is validated.

---

### 🔴 Risk 2: V1 Ends Up Being Just RAG

**What:** You build ingestion + query + memory but the reasoning loop is shallow — it retrieves and summarizes but doesn't genuinely reason about relationships. Evaluators see through it.

**Impact:** Critical for course evaluation. The agentic claim falls apart. Senior PMs will say "this is a nice RAG app."

**Likelihood:** Medium-high if you rush or cut corners on the reasoning step.

**Detection:** Week 3-4. Does the system flag a real contradiction in a test set? If not, it's RAG.

**Mitigations:**
1. Build the reasoning loop in Week 3, not Week 5 (plan already inverted for this)
2. The Week 1 thesis validation proves the LLM *can* reason — Week 3 just puts it in the pipeline
3. If relationship quality is marginal: raise the confidence threshold. Only show contradictions at >0.8 confidence. Fewer but real.
4. The demo must include a live contradiction surfacing. If it can't, the product isn't ready.

---

### 🟡 Risk 3: Extraction Quality Is Poor

**What:** The LLM extracts vague or wrong claims from articles. "This article is about pricing" instead of "The author claims value-based pricing outperforms cost-plus by 23% in SaaS."

**Impact:** Garbage in, garbage out. If claims are vague, relationship reasoning has nothing meaningful to compare.

**Likelihood:** Medium. Extraction is easier than reasoning, but article quality varies wildly.

**Detection:** Week 1-2. Manual review of 20 extractions gives a clear signal.

**Mitigations:**
1. Prompt engineering: "Extract specific, falsifiable claims — not topics or summaries"
2. Include few-shot examples in the extraction prompt
3. Test across diverse content: academic papers, blog posts, news articles, opinion pieces
4. Accept that some sources extract poorly — add a "quality" flag and let users edit extracted claims

---

### 🟡 Risk 4: URL Parsing Fails on Real Websites

**What:** Mozilla Readability can't extract clean text from 30% of URLs (paywalls, JavaScript-heavy sites, PDFs).

**Impact:** Users paste a URL and get an error. First-run experience is broken.

**Likelihood:** Medium. Readability is good but not perfect.

**Detection:** Week 2. Test with 50 real URLs from diverse sources.

**Mitigations:**
1. Always support raw text paste as a fallback — works for everything
2. Add error handling: "Couldn't extract this URL. Paste the text directly."
3. V1.5: add PDF parsing, screenshot OCR, reader-mode fallback
4. Prioritize sources your persona actually reads (articles, blog posts, newsletters — not paywalled academic journals)

---

### 🟡 Risk 5: No "Whoa" Moment in Demo

**What:** The demo feels incremental. Evaluators think "okay, it stores articles and answers questions." The contradiction surfacing doesn't land because the test data is too clean or too forced.

**Impact:** Course evaluation suffers. The product seems competent but not exciting.

**Likelihood:** Medium. Depends entirely on demo preparation.

**Detection:** Week 5. First rehearsal reveals whether it lands.

**Mitigations:**
1. Use real articles with genuine contradictions (they exist — Google "remote work productivity" and you'll find opposing studies)
2. Build the demo data set in Week 4 — don't improvise in Week 6
3. The demo script is already designed: ingest → contradict → query → synthesize
4. Practice the pitch line: "The system caught a contradiction I didn't notice"
5. Have a backup demo with pre-loaded data if live ingestion is flaky

---

### 🟡 Risk 6: Scope Creep

**What:** Adding "just one more feature" — PDF parsing, image OCR, browser extension, multi-user — before V1 core works.

**Impact:** Nothing ships properly. The reasoning loop is half-built because time went to plumbing.

**Likelihood:** High. This is the default failure mode for solo builders.

**Detection:** Ongoing. Every feature request should be asked: "Does this help the demo?"

**Mitigations:**
1. V1 scope is locked: 4 core + 4 stretch features. Nothing else.
2. Input formats: URL + text only. No PDFs, no images, no voice.
3. The stretch features (credibility, gaps, decay) are *cheap additions to existing prompts* — not new systems
4. Rule: if it takes more than 1 day to build and doesn't improve the demo, it's V2

---

### 🟢 Risk 7: Relationship Reasoning Is Slow

**What:** The ingestion loop takes 30-60 seconds because the LLM needs to compare against 10 existing entries.

**Impact:** UX feels sluggish. Users don't want to wait.

**Likelihood:** Medium with larger local models. Low with cloud APIs.

**Detection:** Week 3. Timing the full ingestion pipeline.

**Mitigations:**
1. Show the knowledge card immediately (extraction is fast). Add relationship badges asynchronously.
2. Limit similarity search to top 5 instead of top 10
3. Run relationship reasoning in parallel across matches (not sequentially)
4. Acceptable target: <15 seconds for full ingestion including relationship labeling

---

### 🟢 Risk 8: Test Users Don't Add Enough Entries

**What:** Test users add 3-5 articles instead of 10-15. Knowledge base is too sparse to demonstrate compounding.

**Impact:** Can't prove the "entry #50 > entry #1" thesis. Demo feels thin.

**Likelihood:** Medium. People are busy. Adding 15 articles is work.

**Detection:** Week 5.

**Mitigations:**
1. Pre-populate with 10 synthetic entries per user (curated articles on their chosen topic)
2. Make ingestion dead simple — paste and go. No friction.
3. Recruit test users who are actively researching something (course peers working on capstones)
4. Frame it as: "I need 15 minutes of your time over 3 days. Paste the last 10 articles you read."

---

## Risk Heatmap

```
                        Low Likelihood    Medium           High
                        ─────────────────────────────────────────
Critical (🔴)          │                │ LLM quality    │
                        │                │ Just-RAG risk  │
                        │                │                │
Significant (🟡)       │                │ Extraction     │ Scope creep
                        │                │ URL parsing    │
                        │                │ No whoa moment │
                        │                │                │
Manageable (🟢)        │                │ Slow reasoning │
                        │                │ Few test users │
```

**Week 1 resolves the two critical risks.** Everything else is manageable with discipline.

---

*Next: [[08-competitive-landscape]] — where BrainDrain sits in the market.*
