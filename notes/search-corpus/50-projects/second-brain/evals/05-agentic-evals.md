---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/agents
  - topic/multi-turn
  - status/growing
---

# Agentic & Multi-Turn Evaluation

Evaluating agents and multi-turn conversations is harder than single-turn because failures cascade, context accumulates, and the surface area explodes. This covers practical approaches.

## Multi-Turn Conversation Traces

### Start Simple
- Check if the whole conversation met the user's goal: pass/fail
- Look at entire trace, focus on FIRST upstream failure
- Read user-visible parts first to understand failure, then dig into technical details

### Trace Logging for Multi-Agent Systems
- Assign session/trace ID to each request
- Log every message with: source (agent/tool), trace ID, sequence position
- Reconstruct full path from initial query → final result across all agents

### Annotation Strategy
- Annotate only the FIRST failure initially
- "Don't worry about downstream failures since these often cascade from the first issue"
- Fixing upstream failures often resolves downstream ones automatically
- As experience grows, annotate independent failure modes

### Simplify for Debugging
- Find failure → reproduce with simplest test case
- Example: shopping bot gives wrong return policy on turn 4 → simplify to single turn: "What is return window for product X1000?"
- If it still fails, the error isn't conversation context — it's a basic retrieval/knowledge issue

### Test Case Generation
- Simulate users with LLM creating realistic multi-turn conversations
- "N-1 testing": provide first N-1 turns of real conversation, test the next turn
  - Uses actual conversation prefixes (more realistic)
  - Less flexible than fully synthetic

## Evaluating Human Handoffs
- Trace continues until user's need is resolved — NOT when AI hands off to human
- Log: handoff decision/reasoning, context transferred, wait time, human actions, final resolution
- "Many failures occur at handoff boundaries where AI hands off too early, too late, or without proper context"
- Evaluate: Was handoff necessary? Did AI provide adequate context?
- Track handoff quality AND handoff rate
- "Sometimes the best improvement reduces handoffs entirely rather than improving handoff execution"

## Complex Multi-Step Workflows

### Two Metric Types
**Outcome metrics**: Did the final result meet requirements? (case complete? accurate? formatted?)

**Process metrics**: Was the execution efficient? (step count, time, resource usage)
- "Process failures are often easier to debug since they're more deterministic, so tackle them first"

### Segment by Workflow Stage
- Early failures (understanding input) differ from middle (data processing) and late (formatting output)
- "Early stage improvements have more impact since errors cascade in LLM chains"

### Transition Failure Matrices
- Rows = last successful state, columns = where first failure occurred
- Reveals failure hotspots and guides debugging investment

## Agentic Workflow Evaluation — Two Phases

### Phase 1: End-to-End Task Success
- Treat agent as black box: did we meet the user's goal?
- Define precise success rule per task type
- Measure with human or aligned LLM judges
- Note first upstream failure during error analysis

### Phase 2: Step-Level Diagnostics (after error analysis reveals failing workflows)
Score individual components:
- **Tool choice**: appropriate selection?
- **Parameter extraction**: inputs complete and well-formed?
- **Error handling**: recover from empty results or API failures?
- **Context retention**: preserved earlier constraints?
- **Efficiency**: steps, seconds, tokens spent?
- **Goal checkpoints**: key milestones verified?

Example breakdown for "Find Berkeley homes under $1M and schedule viewings":
- Parameters extracted correctly ✓/✗
- Relevant listings retrieved ✓/✗
- Availability checked ✓/✗
- Calendar invites sent ✓/✗

Each checkpoint passes/fails independently → tractable debugging.

### Transition Failure Matrices (Again)
Same concept: rows = last successful state, columns = first failure point. Critical for understanding which workflow segments are most fragile.

## Connection to [[agentic-eval-layers]]
This maps directly to the three-layer framework from Tosh's work:
1. Signal fidelity → retrieval quality within agent tools
2. Policy quality → agent decision-making (tool choice, when to stop)
3. System intelligence → end-to-end loop performance

## For Our Project
- Our search agent has a clear multi-step flow: query → decomposition → fan-out retrieval → scoring → synthesis
- Phase 1: does the final synthesis answer the user's question? (binary)
- Phase 2: which step failed? (decomposition? retrieval? scoring? synthesis?)
- Build transition failure matrix: track where queries succeed and where they break down
- Early-stage failures (bad query decomposition) cascade hardest — prioritize those

---
See also: [[00-evals-hub]], [[01-error-analysis]], [[agentic-eval-layers]], [[06-production-evals]]
