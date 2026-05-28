---
type: note
date-created: 2026-04-19
status: growing
source: "[[hamel-husain-llm-evals-faq]]"
tags:
  - type/note
  - topic/evals
  - topic/tooling
  - topic/infrastructure
  - status/growing
---

# Tooling & Infrastructure for Evals

The single most contrarian take in Hamel's guide: build your own annotation tools. Teams with custom tools "iterate ~10x faster."

## Build Custom Annotation Tools
- With AI-assisted dev tools (Cursor, etc.), building takes hours not weeks
- Custom tools show all context from multiple systems in one place
- Render data in product-specific ways (images, widgets, markdown, domain-specific views)
- Designed for YOUR specific workflow

### Off-the-shelf justified when:
- Coordinating dozens of distributed annotators
- Enterprise access controls needed
- You truly don't have domain-specific rendering needs

### Four Design Principles for Custom Interfaces

#### 1. Render Traces Intelligently, Not Generically
- Present traces intuitively for your domain
- Example: render generated emails to look like actual emails
- Show full trace (input, tool calls, reasoning) with collapsible sections for details

#### 2. Show Progress and Support Keyboard Navigation
- Keep reviewers in flow state
- Progress indicators ("Trace 45 of 100")
- Hotkeys: N for next, keyboard shortcuts for labels, save notes

#### 3. Trace Navigation: Clustering, Filtering, Search
- Filter by metadata, keyword search, semantic search
- Cluster similar traces (e.g., by user persona) to reveal recurring issues

#### 4. Prioritize Labeling Problematic Traces
- Surface traces flagged by guardrails, CI failures, automated evaluators
- Action buttons: add to datasets, file bugs, re-run tests
- Display context: pipeline version, eval scores, reviewer info

"Only incorporate these ideas if they provide a benefit that outweighs additional complexity."

## Gaps You'll Need to Fill Yourself

### 1. Error Analysis and Pattern Discovery
- Can your tooling cluster similar failures automatically?
- Build: AI-assisted grouping, taxonomy rewrites, semantic search for similar cases

### 2. AI-Powered Workflow Acceleration
- During error analysis: LLM categorizes observations into failure modes
- Proposing fixes: analyze 20 failures → suggest prompt modifications
- Data analysis: notebooks with AI discovering patterns (e.g., "location errors spike 3x with neighborhood names")
- Tools: Julius, Hex, SolveIt for AI-assisted notebook analysis

### 3. Custom Evaluators Over Generic Metrics
- Be prepared to build most evaluators from scratch
- "Successful teams spend most of their effort on application-specific metrics"

### 4. APIs Supporting Custom Annotation Apps
- Need: true bulk export, efficient annotation write-back APIs
- Common problems: difficult bulk export, timeout-prone endpoints, pagination burden

## Prompt Versioning — Store in Git
- Treat prompts as software artifacts: versioned, reviewed, deployed atomically with code
- GitHub web interface and Desktop make it approachable for non-technical users
- Alternative: vendor tools (Arize, Braintrust, LangSmith) offer prompt management
  - But they can't easily execute application code
  - "Even when they can, there's often significant indirection involved"
- Jupyter notebooks: great experimentation environment if code has Python entry points
  - Execute actual agents with full capabilities
  - Create widgets and UIs within notebooks

## Vendor Landscape (Honest Assessment)
- No favorite — "features are very similar"
- Vendors encountered: LangSmith, Arize, Braintrust
- Selection criteria: "weighs heavily towards who can offer the best support... mainly the human factor, and dare I say, vibes"
- Reality: you'll build custom tools on top of any vendor you choose

## For Our Project
- Build a simple trace viewer for search queries: show query → decomposition → sources → scoring → final output
- Keyboard-navigable annotation: pass/fail per dimension
- Store prompts in Git alongside our codebase
- Don't invest in vendor tooling yet — we're too early
- Jupyter/notebook-based experimentation for prompt iteration

---
See also: [[00-evals-hub]], [[03-annotation-and-humans]], [[06-production-evals]]
