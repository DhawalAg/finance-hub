# 0007 Runtime Surface Lives In A Top-Level `runtime/` Directory

Date: 2026-07-17

## Status

Accepted (ratified via issue #38; extends ADRs 0005/0006 and the agent-evals spec §2/§8.1/§8.3)

## Context

The agent-evals spec (`docs/requests/evals/spec.md` §2) draws a hard line through the repo: the
**runtime surface** — the deployed finance-hub's runtime-only CLAUDE.md, its ADR-0005 skills, and its
MCP config — is part of the System Under Test, while **dev scaffolding** — the root CLAUDE.md,
`docs/agents/**`, triage/process docs — is the factory, not the product, and must never leak into a
trial. The harness materializes exactly the runtime surface into each trial dir from a checked-in
**materialization list** under `evals/`, and the §8.3 prompt hash is computed over exactly what gets
materialized. Spec §2 deferred one thing to Phase 1: *where the runtime surface physically lives* —
naming `evals/sut/` or `runtime/` as candidates. That placement is the decision this ADR settles.

The decision is shared between two live efforts — the eval rollout (umbrella #34, this issue's parent)
and the parallel ADR-0005 skills-plan effort (wayfinder map #51). Neither map may own it unilaterally,
so it lives here as a standalone ADR both efforts block on, with precedent: issue #28 owned a *question*
while ADR 0006 owned the *answer*.

Three facts about the environment constrain the choice:

- **Nothing consumes the runtime surface yet.** There is no runtime CLAUDE.md, no `.mcp.json`, and no
  `.claude/skills/` in the repo today. The files are authored fresh (eval issue #40).
- **The eval harness reads explicit paths.** The runner is the Claude Agent SDK (issue #25); it takes
  a system-prompt path, a skills dir, and an MCP config path as arguments, so it works identically
  regardless of where the files live.
- **Claude Code's interactive loaders are fixed convention, not configurable.** The CLI discovers
  project skills only under `.claude/skills/`, MCP only from a root `.mcp.json`, and project context
  only from a root `CLAUDE.md`. It will never read `runtime/` on its own. Interactive use of the
  runtime surface therefore requires a bridge from the canonical home to those fixed paths.

The user intends, once the runtime surface exists, to run interactive Claude Code sessions that load
the finance-hub tools and skills — sometimes alongside side-channel dev work in the same repo.

## Decision

- **The runtime surface lives in a new top-level `runtime/` directory:** `runtime/CLAUDE.md`,
  `runtime/skills/`, and `runtime/mcp.json`. The whole deployed agent is legible in one glance, and a
  path under `runtime/` visibly signals "editing this changes the product." This is chosen over the
  two alternatives:
  - **`evals/sut/`** frames the deployed agent as eval plumbing, contradicting spec §2's own framing
    of the runtime CLAUDE.md as "a real versioned artifact… not just eval plumbing," and would file the
    user's daily-driver tools under an evals subfolder. Rejected.
  - **`.claude/`-native (no dedicated folder)** needs zero wiring but makes the product/dev boundary
    invisible in the filesystem — a product skill would sit indistinguishably beside a dev-tooling
    skill, and only the materialization list would know which edit changes the SUT. In a heavily
    agent-operated repo, path-visible boundaries are respected where "consult the list before editing"
    silently erodes. Rejected.

- **MCP config is canonical at `runtime/mcp.json`, bridged to root by a symlink.** The root `.mcp.json`
  Claude Code expects is a symlink into `runtime/`, keeping the entire runtime surface under one root.
  The MCP *server code* stays in `src/finance_hub` — code is versioned by the repo; the runtime surface
  is prompt files and config only.

- **Interactive use is bridged by symlinks; the workbench persona comes later.** Each shipped skill
  gets a `.claude/skills/<name>` symlink into `runtime/skills/<name>`, and root `.mcp.json` symlinks
  into `runtime/`. Symlinks are one real file visible at two paths, so they cannot drift from the
  canonical `runtime/` copy, and the materialization list still names the `runtime/` paths as the sole
  source of truth. Everyday sessions thus run a **hybrid persona** — runtime tools and skills loaded
  alongside dev scaffolding — which is acceptable and even useful for the user's workflow, because the
  SUT boundary is enforced by the materialization list, not by what an interactive session happens to
  load. A **pure-runtime workbench** (materialize the runtime surface into a scratch dir against the
  real store and launch `claude` there — exactly what the harness does for a trial) is deferred until
  the materialization machinery (#40) exists; a custom Agent SDK "deployed finance-hub" app is deferred
  further still, since Claude Code already provides the interactive UX.

- **Three roles stay separate — Decision, Enforcement, Navigation:**
  - **Decision → this ADR.** It defines what the runtime surface is and where it lives — the SUT
    boundary the §8.3 prompt hash depends on.
  - **Enforcement → the materialization list under `evals/`** (built in eval issue #40). Trials load
    only listed files; the prompt hash is computed over exactly them. The list *is* the mechanism, so
    it cannot drift from reality.
  - **Navigation → the wayfinder maps and the interactive symlinks reflect, never own.** Neither a map,
    nor a symlink, nor a directory listing is ever the authority — the list is.

- **Files enter and change the runtime surface by fixed rules:**
  - **New skills enter only via the ADR-0006 skill DoD.** The shipping PR adds the skill under
    `runtime/skills/`, its ≥1 capability eval task (per workflow the skill orchestrates), its
    materialization-list entry, and its `.claude/skills/` symlink — all in one PR. (Skill-authoring
    conventions #56 encode the symlink step into the checklist.)
  - **Non-skill runtime edits** (runtime CLAUDE.md wording, `runtime/mcp.json` changes) are ordinary
    PRs. They change the prompt hash; spec §8.1's hash rule decides whether a suite run is triggered.
  - **A file added under `runtime/` without a list entry simply never reaches a trial.** That is the
    enforcement working as designed, not a bug.

## Consequences

The deployed finance-hub agent has a single, legible home from before its first file exists, so eval
issue #40 authors the runtime CLAUDE.md and materialization list directly into `runtime/` rather than a
provisional spot to be `git mv`'d later. The product/dev boundary is visible in the filesystem, which an
agent-operated repo can enforce by convention where an invisible boundary would erode. Interactive
sessions get the real tools and skills for near-free via symlinks that cannot drift, at the cost of one
symlink line added to the skill-shipping checklist and a hybrid (not pure-runtime) persona in daily use;
the pure-runtime workbench remains available later as a dogfooding mode. The materialization list under
`evals/` remains the sole authority on what is in the SUT, so maps and symlinks can be added, moved, or
removed without ever changing the eval boundary. Per the repo convention set in ADR 0006, this ADR is
not retro-edited into 0005/0006; those carry dated cross-references and this decision stands as a new
number.
