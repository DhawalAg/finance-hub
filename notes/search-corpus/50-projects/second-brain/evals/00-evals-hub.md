---
type: moc
date-created: 2026-04-19
status: growing
tags:
  - type/moc
  - topic/evals
  - topic/ai
  - status/growing
---

# Evals Knowledge Base

Our working knowledge base on LLM evaluation — built from practitioner sources, not vendor marketing. Primary source: Hamel Husain & Shreya Shankar's comprehensive evals FAQ (700+ engineer course distillation).

---

## Why This Exists

We're building agentic search with LLM scoring, RAG pipelines, and multi-step workflows. Every layer — retrieval quality, generation faithfulness, agent decision-making — needs a feedback loop that tells us whether changes make things better or worse. Evals aren't optional; they're the mechanism that turns iteration into progress. Without them, we're shipping vibes.

---

## Core Methodology

- [[01-error-analysis]] — The foundational practice. Start here.
- [[02-eval-design]] — Binary evals, LLM-as-judge, custom evaluators
- [[03-annotation-and-humans]] — Benevolent dictator model, labeling, outsourcing traps

## Domain-Specific Evaluation

- [[04-rag-evals]] — Retrieval vs generation evaluation, chunk sizing
- [[05-agentic-evals]] — Multi-step workflows, multi-turn conversations, handoffs

## Production & Infrastructure

- [[06-production-evals]] — CI/CD integration, guardrails vs evaluators, monitoring
- [[07-tooling-and-infrastructure]] — Custom annotation tools, vendor landscape, prompt versioning

## For Our Project

- [[08-actionable-playbook]] — Concrete eval system design for second-brain

---

## Existing Vault Notes

- [[evals-dump]] — Early scratchpad notes on eval setup
- [[agentic-eval-layers]] — Three-layer eval framework (signal fidelity → policy quality → system intelligence)
- [[rag-implentations]] — RAG technique comparison table

---

## Source

- [[hamel-husain-llm-evals-faq]] — Full reference note for the source article
- Hamel Husain's blog: https://hamel.dev/blog/posts/evals-faq/
