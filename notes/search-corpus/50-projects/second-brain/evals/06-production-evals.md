---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/production
  - topic/cicd
  - topic/guardrails
  - status/growing
---

# Production Evals — CI/CD, Guardrails, and Monitoring

How evals live in production systems. The key insight: guardrails and evaluators are different tools for different problems.

## CI/CD vs Production Monitoring

### CI/CD Test Datasets
- Small: often 100+ curated examples
- Purpose-built: core features, regression tests for past bugs, known edge cases
- Run frequently → per-test cost matters
- Favor assertions or deterministic checks over LLM-as-judge
- Think of these like unit tests for your AI system

### Production Evaluation
- Sample live traces, run evals asynchronously
- Usually lack reference outputs → rely on reference-free evaluators (LLM-as-judge)
- Track confidence intervals; investigate when lower bound crosses threshold
- Think of these like monitoring/observability

### The Feedback Loop
When production monitoring reveals new failure patterns through error analysis → add representative examples to CI dataset → prevents regressions. This is how your CI suite grows organically from real failures.

## Guardrails vs Evaluators — Critical Distinction

### Guardrails: Inline Safety Checks
- Sit in the request/response critical path
- FAST and deterministic (milliseconds latency)
- Simple and explainable: regexes, block-lists, schema validators, lightweight classifiers
- Target clear-cut, high-impact failures:
  - PII leaks
  - Profanity
  - Disallowed instructions
  - SQL injection
  - Malformed JSON
  - Invalid code syntax
- Actions: redact, refuse, or regenerate
- User-visible when they fire → false positives are production bugs
- Version rules, log triggers, monitor rates conservatively

### Evaluators: Post-Production Assessment
- Run AFTER the response is produced
- Measure subjective qualities: factual correctness, completeness, tone
- Feed dashboards, regression tests, model-improvement loops
- Don't block the original answer
- Usually asynchronous or batch
- LLM-as-Judge possible inline ONLY with sufficient latency/reliability budget

### The Rule
"Apply guardrails for immediate protection against objective failures requiring intervention. Use evaluators for monitoring and improving subjective or nuanced criteria."

"Do not use LLM guardrails off the shelf blindly. Always look at the prompt."

## Can Evaluators Auto-Fix Production Outputs?
Yes, but only a specific subset. Decision criteria:
1. **Latency & Cost**: Can it run fast/cheap enough without degrading UX?
2. **Error rate trade-offs**:
   - High-stakes (medicine): false negatives more costly → accept more false positives
   - Creative apps: false positives (blocking good output) more harmful → accept more false negatives

"Most guardrails are designed to be fast and have very low false positive rate. You would almost never use a slow or non-deterministic LLM-as-Judge as a synchronous guardrail."

## Model Selection
- Don't fixate on model selection as primary improvement lever
- Start with error analysis to understand failure modes BEFORE considering model switching
- "Does error analysis suggest that your model is the problem?"

## For Our Project
- CI: build a test dataset of 100+ queries with expected behaviors, run on every prompt change
- Guardrails for our search: schema validation on LLM scoring output (must be valid JSON), check for hallucinated sources
- Evaluators: async assessment of search result quality, relevance scoring validation
- Production monitoring: sample search sessions, flag outliers (unusually long, many retries)

---
See also: [[00-evals-hub]], [[02-eval-design]], [[07-tooling-and-infrastructure]]
