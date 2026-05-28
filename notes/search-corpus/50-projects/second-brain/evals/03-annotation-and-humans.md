---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/annotation
  - topic/human-in-loop
  - status/growing
---

# Annotation & The Human Element

The hardest part of evals isn't the code — it's the human process. This covers who annotates, how, and what NOT to outsource.

## The Benevolent Dictator Model
- Appoint a single domain expert as the definitive voice on quality
- Examples: psychologist for mental health chatbot, lawyer for legal analysis, service director for support automation
- Advantages: eliminates annotation conflicts, prevents "too many cooks" paralysis
- This person incorporates others' input but drives decisions
- For larger orgs with multiple domains: need multiple annotators → measure agreement with Cohen's Kappa
- "Start with a benevolent dictator whenever feasible. Only add complexity when your domain demands it."

## PM + Engineer Collaboration
- Initial phase: collaborate to establish shared context
  - Engineers catch technical issues (retrieval failures, tool errors)
  - PMs identify product failures (unmet expectations, confusing responses)
- Over time: shift toward benevolent dictator — usually the domain expert or PM who understands user needs
- Empower domain experts with custom annotation tools showing outcomes alongside traces
- Ask "Has an appointment been made?" not "Did the tool call succeed?"

## Why Outsourcing Annotation Is Usually a Mistake
- Breaks feedback loop between observing failures and improving product
- External teams lack domain nuance — superficial labeling
- Loss of tacit knowledge that can't be captured in rubrics
- "A critical misstep in error analysis is excluding domain experts from the labeling process"

### When External Help Works (Exceptions)
- Purely mechanical tasks AFTER rigorous internal rubric: phone number validation, email format checks
- Tasks without product context: translation (linguistic expertise, not product knowledge)
- External subject matter experts: e.g., AnkiHub hired 4th-year medical students for medical RAG evaluation

## Managing Capacity Constraints
- Smart sampling: 100 diverse traces reveal more than 1000 superficial labels
- Think-aloud protocol: expert verbalizes thinking while reviewing traces (one-hour session = deep insights)
- Build lightweight custom tools to increase throughput ([[07-tooling-and-infrastructure]])

## What LLMs Can and Can't Do in Annotation

### LLMs Help (with oversight):
- First-pass axial coding — after YOU manually open-code 30-50 traces
- Mapping annotations to failure mode categories
- Suggesting prompt improvements based on recurring problems
- Analyzing patterns in label data

### DO NOT Outsource to LLMs:
- Initial open coding — you need to read raw traces yourself, builds intuition
- Validating failure taxonomies — LLMs incorrectly group distinct issues
- Ground truth labeling — hand-validate labels for LLM-as-judge test sets
- Root cause analysis — only human review catches workflow-specific patterns

"Start by examining data manually to understand what's actually going wrong. Use LLMs to scale what you've learned, not to avoid looking at data."

## The Collaborative Workflow (When Multiple Annotators Needed)
1. Draft initial rubric with Pass/Fail definitions and examples
2. Each annotator independently labels shared traces
3. Measure Inter-Annotator Agreement (Cohen's Kappa)
4. Alignment sessions to discuss disagreements
5. Iterate until consistently high agreement

## For Our Project
- For second-brain search: we are the domain expert (benevolent dictator)
- Our annotation = manually reviewing search results and scoring relevance
- Don't outsource this to an LLM until we've built intuition from 100+ manual reviews
- Build a simple annotation interface in our tool for reviewing search traces

---
See also: [[00-evals-hub]], [[01-error-analysis]], [[07-tooling-and-infrastructure]]
