---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/error-analysis
  - status/growing
---

# Error Analysis — The Foundation of LLM Evals

Error analysis is "the most important activity in evals" (Hamel Husain). It's adapted from qualitative research methodologies and should be the starting point for any eval effort. Before you build infrastructure, pick metrics, or choose tools — look at your data.

## Why Error Analysis First

- Don't start with infrastructure, metrics, or tools — start by looking at your data. The temptation to jump to dashboards and automation is strong. Resist it.
- 60-80% of development time should go to understanding failures. This is not wasted time; it is the work.
- "If you're passing 100% of your evals, you're likely not challenging your system enough." A green board means your evals are too easy, not that your system is good.
- This is debugging for AI — not a separate budget item. Error analysis is not some luxury "eval infrastructure" project. It is the same thing engineers have always done: find the bugs, understand them, fix them.

## The Four-Step Process

### 1. Creating a Dataset

Gather representative traces of real user interactions. A trace is a "complete record of all actions, messages, tool calls, and data retrievals from a single initial user query through to the final response." This is the raw material — everything starts here.

- Pull traces from production logs, staging environments, or manual testing sessions.
- If you lack real traffic, generate synthetic data (see below), but real data is always preferable.
- Target: start with **20-50 outputs** for manual review. This should take roughly **30 minutes**.
- Don't over-engineer the dataset format early on. A spreadsheet or markdown table works fine.

### 2. Open Coding

A domain expert reviews traces and writes open-ended notes about what went wrong. This is "akin to journaling" — a practice adapted from qualitative research.

- Read each trace end-to-end. Note anything that feels off, wrong, or surprising.
- Focus on the **first upstream failure** in each trace. Downstream failures cascade from earlier ones — fixing the root cause often fixes everything below it.
- Write in natural language. No rubrics, no scores, no checkboxes. Just describe what you see.
- This builds intuition about your system's failure modes. Don't skip it, don't outsource it to LLMs. The point is for a human to develop a mental model of what's breaking.

### 3. Axial Coding (THE MOST IMPORTANT STEP)

Take your open-ended notes and categorize them into a failure taxonomy.

- Group similar failures into distinct categories. For example: "hallucinated source," "ignored user constraint," "retrieved irrelevant context," "correct answer but poor formatting."
- Count failures per category. This gives you a prioritized list — fix the most common failure mode first.
- The taxonomy itself is the deliverable. It tells you what your evals need to measure.
- You can use LLM assistance here (after you've done the thinking yourself). An LLM can help cluster notes, but the human must validate the categories.

### 4. Iterative Refinement

Continue until "theoretical saturation" — no new failure modes appearing in new traces.

- Target: review at least **100 traces** total across iterations.
- Re-run the full process when: new features ship, prompts are updated, models are switched, or major bug fixes land.
- Cadence: **2-4 week cycles** for major analysis rounds. Between rounds, review **10-20 traces weekly** to catch regressions.
- Each cycle should refine your taxonomy — merge categories that overlap, split categories that are too broad.

## Surfacing Problematic Traces

Three approaches for finding the traces worth reviewing:

1. **Random sampling** — simplest starting point. If random traces look fine, escalate to stress testing because your sample may not be representative.
2. **Use existing evals as screening filters** — if you already have basic evals, use them to flag traces that score poorly. Review those first.
3. **Efficient sampling** — more sophisticated techniques:
   - Outlier detection (traces with unusual latency, token counts, or tool call patterns)
   - Metric-based sorting (lowest-scoring traces by any available signal)
   - Stratified sampling (ensure coverage across user segments, query types, etc.)
   - Embedding clustering (group similar traces, sample from each cluster)

Generic metrics (latency, token count, etc.) are "exploration signals" not quality measures. They help you find interesting traces to review, not judge output quality.

## Synthetic Data That Works

The common mistake: prompting an LLM for generic "test queries" — this produces repetitive garbage that doesn't reflect real usage patterns.

The structured dimensional approach:

1. **Define dimensions** relevant to your domain. For a search system: query complexity (simple/compound/ambiguous), domain (technical/casual/specialized), intent type (factual/exploratory/comparative).
2. **Create 20 tuples manually first.** Each tuple is a combination of dimension values, e.g., (compound, technical, comparative). Hand-write these to ensure realistic coverage.
3. **Scale with two-step generation:**
   - Step 1: LLM generates additional tuples following the pattern of your manual ones.
   - Step 2: A separate prompt converts each tuple into a natural-language query.
4. Fix obvious problems FIRST before generating synthetic data. If your system breaks on simple queries, synthetic stress tests are premature.
5. Run **100 synthetic queries** through your actual system to get full traces, then apply the four-step process above.

## When Synthetic Data Fails

Synthetic data is not a universal solution. It breaks down when:

- **Complex domain-specific content** — the LLM can't generate realistic medical records, legal filings, or proprietary data formats.
- **Low-resource languages** — LLMs produce unnatural text in languages with limited training data.
- **When you can't validate realism** — if you don't have domain expertise to tell real from fake, synthetic data gives false confidence.
- **High-stakes domains** (medicine, law) — the cost of testing with unrealistic data is too high.
- **Underrepresented user groups** — synthetic data inherits the biases of the generating model and may not represent edge-case users.

## The Anti-Pattern: Eval-Driven Development

Writing evaluators BEFORE implementing features usually fails.

- LLMs have "infinite surface area for potential failures — you can't anticipate what will break." Pre-written evals test for what you imagined would go wrong, not what actually goes wrong.
- **Exception:** known hard constraints like "never mention competitors," "always cite sources," or "never output PII." These are worth encoding upfront.
- **Better approach:** build the feature, run error analysis on real outputs, then write evaluators for the discovered failure modes. Let the data tell you what to test.

## For Our Project

How this applies to [[08-actionable-playbook]]:

- Our search pipeline produces traces: query -> decomposition -> retrieval -> scoring -> synthesis. Each step is a potential failure point.
- Error analysis = reviewing those traces manually before building automated scoring. No shortcuts.
- Start with **50 real queries**, manually annotate quality of retrieval + synthesis.
- Build a failure taxonomy specific to search quality (e.g., "retrieved wrong section," "missed relevant note," "synthesized answer contradicts source," "hallucinated link").

---

See also: [[00-evals-hub]], [[02-eval-design]], [[03-annotation-and-humans]]
