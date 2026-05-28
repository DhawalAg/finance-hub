---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/eval-design
  - topic/llm-as-judge
  - status/growing
---

# Evaluation Design — Binary Evals, Judges, and Custom Metrics

## Binary Over Likert — The Core Principle

Likert scales (1-5) introduce more problems than they solve. Adjacent points are subjective and inconsistent — what separates a 3 from a 4 depends entirely on who is labeling. Annotators default to middle values to avoid making hard decisions, which collapses your signal into noise.

Binary forces clear thinking: **pass or fail**. There is no hiding behind a 3.

For gradual improvement tracking, use **multiple binary sub-checks** instead of a single numeric score:
- Instead of "accuracy 1-5", track "fact 1 present ✓", "fact 2 present ✓", "no hallucinated claims ✓", etc.
- Your pass rate across sub-checks gives you a more interpretable and reproducible score than any Likert average.

> "Start with binary labels to understand what 'bad' looks like. Numeric labels are advanced and usually not necessary."

## Don't Use Off-the-Shelf Metrics

> "All you get from using these prefab evals is you don't know what they actually do and in the best case they waste your time and in the worst case they create an illusion of confidence."

Generic metrics like "helpfulness" or "coherence" may not matter for YOUR use case. They measure someone else's definition of quality, not yours.

**Metrics to avoid in most AI applications:**
- BERTScore, ROUGE, BLEU — designed for tasks with well-defined reference outputs; misleading for open-ended generation
- Generic similarity metrics — unless you are doing search/retrieval

**Exceptions where off-the-shelf metrics DO work:**
- **Search and retrieval** — cosine similarity, recall@k, precision@k have clear, task-aligned semantics
- **Experienced practitioners** can use generic metrics as exploration tools to find interesting traces worth investigating — but this requires knowing what you are looking for

## The Correct Process

1. Conduct error analysis ([[01-error-analysis]])
2. Define binary failure modes based on real problems discovered
3. Create custom evaluators targeting those specific failures
4. Validate evaluators against human judgment

The sequence matters. You cannot design meaningful evaluations without first understanding how your system actually fails on real data.

## Cost-Benefit Hierarchy for Evaluators

Not all evaluators cost the same to build and maintain. Match effort to impact:

| Tier | Examples | Cost | Guidance |
|------|----------|------|----------|
| Cheap | Simple assertions, regex, structural validation, JSON schema checks | Low | Use freely — first line of defense |
| Moderate | Reference-based checks, execution tests, deterministic comparisons | Medium | Good for well-defined correctness criteria |
| Expensive | LLM-as-Judge | High — requires 100+ labeled examples, weekly maintenance, team coordination | Reserve for persistent problems you will iterate on repeatedly |

**Rule of thumb:** many issues can be fixed by improving prompts directly. Don't build an evaluator for something you can fix. Only invest in expensive evaluators for failure modes that persist across prompt iterations and that you need ongoing visibility into.

## LLM-as-Judge

Using the same model for the task and for evaluation is generally fine. The judge performs a fundamentally different task than the pipeline — it is classifying output quality, not generating the output.

**What matters:** alignment with human judgments, measured by True Positive Rate and True Negative Rate against your labeled examples.

**Process:**
1. Start from error analysis — understand what "bad" looks like
2. Write and iterate on the judge prompt
3. Collect 100+ labeled examples (human ground truth)
4. Measure judge accuracy against human labels
5. Start with the most capable model available → optimize cost later

Don't use off-the-shelf judge prompts either. Your judge prompt needs to encode YOUR quality criteria, discovered through YOUR error analysis.

## Evaluating Uncertainty / Abstention

**Abstention Ability** — the model's calibrated refusal when it lacks sufficient information to answer well.

Your test set needs both:
- **Answerable questions** — where the model should respond confidently
- **Unanswerable questions** — false premises, missing context, out-of-domain queries

Binary evaluation: pass = answers good questions correctly AND refuses bad ones appropriately.

When building the unanswerable set, diversity and difficulty matter more than exact ratio balance. Include edge cases that probe the boundary of the model's knowledge.

## Should I Automate Prompt Writing?

Be skeptical. Manual prompt writing forces you to clarify your assumptions about what good output looks like.

> "Good writing is good thinking."

**Problems with automated prompt optimization:**
- Tools hill-climb on predefined metrics but don't discover new failure modes
- **Criteria drift** — evaluation criteria shift after reviewing outputs; this is a natural, iterative human sensemaking process that automated tools cannot replicate
- You lose the forcing function that makes you understand your own requirements

**Pragmatic middle ground:** use LLMs to improve prompts based on YOUR open coding observations from error analysis. Keep the human in the loop for defining what matters and when criteria should change.

## For Our Project

- Our search scoring rubrics should be binary pass/fail per dimension
- LLM-as-judge for relevance scoring needs validation against our own manual labels — no shortcuts
- Don't adopt generic search quality metrics — build evaluators from [[01-error-analysis]] of our actual results

---

See also: [[00-evals-hub]], [[01-error-analysis]], [[03-annotation-and-humans]]
