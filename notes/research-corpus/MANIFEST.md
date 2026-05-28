# research-corpus — MANIFEST

**Triage area for the `research` hub.** Everything here was *copied* from a prior prototype,
**BrainDrain** (the `codex/brain-rot/` Next.js app), on **2026-05-28** to consolidate
research-hub design material in one place. The source directory was deleted after this copy —
these markdown docs are the only retained artifact.

Folder layout preserves provenance: `brain-rot/` holds the original product docs verbatim.

## Why this is here
BrainDrain was a prior, separate-stack prototype (Next.js + TypeScript + Ollama +
better-sqlite3) of a **personal knowledge agent / knowledge state machine**:
ingest → claim extraction → relationship reasoning → SQLite → cluster recompute, plus a
query loop (multi-angle retrieval → synthesis → self-evaluation) and a cluster-level state
view (conflict / depth / diversity signals).

It maps onto two parts of hub-hub:
- the **`research` hub** (currently "TBD — not yet detailed" in `working-doc.md`) — BrainDrain
  is essentially a fleshed-out version of it.
- the **`search` → `materialize()` → resource-DB** pipeline — BrainDrain reasons *over* the
  harvest the search hub produces. They're complementary stages: search = discovery/harvest,
  BrainDrain = synthesis/knowledge-model.

## Carry-over value vs. caveats
- **High value:** the product thinking (docs below) and the **claims → relationships →
  clusters** domain model.
- **Not reusable as code:** original was TypeScript/Next.js/Ollama; hub-hub's decided core is
  Python/Anthropic, headless. Any code reuse would be a port, not a copy. Only the docs were
  retained.

## Inventory (14 files) — status legend: [ ] untouched · [~] reviewing · [x] resolved

### From `codex/brain-rot/` — product docs
- [ ] brain-rot/00-product-brief.md
- [ ] brain-rot/01-problem-space.md
- [ ] brain-rot/02-user-personas.md
- [ ] brain-rot/03-why-agentic.md
- [ ] brain-rot/04-product-vision.md
- [ ] brain-rot/05-metrics-and-eval.md
- [ ] brain-rot/06-build-plan.md
- [ ] brain-rot/07-risks-and-mitigations.md
- [ ] brain-rot/08-competitive-landscape.md
- [ ] brain-rot/09-agentic-loops.md
- [ ] brain-rot/10-feature-brainstorms.md
- [ ] brain-rot/11-knowledge-model.md
- [ ] brain-rot/Project Self Evaluation Checklist.md
- [ ] brain-rot/README.md — V1 scaffold notes (Next.js/Ollama stack; reference only)

## Next steps
- Triage these against `working-doc.md`'s (empty) research-hub section to seed its spec.
- Decide what, if anything, the research hub borrows from the search hub's resource-DB /
  vault projection vs. owns independently.
