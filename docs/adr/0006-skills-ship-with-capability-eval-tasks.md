# 0006 Skills Ship With Capability Eval Tasks

Date: 2026-07-16

## Status

Accepted (ratified via issue #28; extends the skill definition-of-done in ADR 0005)

> 2026-07-17: the skill definition-of-done is extended further by
> [ADR 0007](0007-runtime-surface-lives-in-a-top-level-runtime-directory.md) — a skill-shipping PR
> also places the skill under `runtime/skills/`, adds its materialization-list entry, and creates its
> `.claude/skills/` symlink.

## Context

ADR 0005 makes skills the orchestration layer over deterministic tools, and the agent-evals spec
(`docs/requests/evals/spec.md`) defines the SUT as the whole stack — model, prompt, skills, tool
registry, store. That makes adopting a skill an SUT change like any other, but at the time skills
were defined no eval system existed, so nothing said how a new skill's behavior becomes measurable.
An unevaluated skill can silently do freehand math, skip readiness checks, or write uncited prose —
exactly the failure modes ADR 0005 exists to prevent — and nothing would catch it.

A subtlety shapes the whole policy: eval tasks grade **workflows**, not skills. A task is a prompt +
fixture + graders over durable outcomes (store rows, artifacts); it never invokes a skill directly,
and whether the agent loads the skill mid-flight is the agent's business. A skill's value — or harm —
shows up as pass-rate deltas on the tasks of the workflow it orchestrates.

## Decision

- **Adopting a skill is a capability claim, and claims ship with their measurement.** The change
  that adopts an ADR 0005 skill must add at least one capability-suite eval task per workflow the
  skill orchestrates. Tasks belong to the workflow and outlive the skill.
- **Tasks must exist and run; passing is not required.** Capability tasks are the frontier and are
  expected to start low. Each shipped task meets a *definition + witnessed run* bar: an unambiguous
  prompt, a fixture, outcome graders, plus one recorded run against the current stack with the skill
  loaded — graders execute, transcript saved, pass/fail outcome irrelevant. This proves the task is
  runnable and gradeable at adoption time; golden/reference transcripts are deferred to the task's
  migration-to-regression moment (spec §7).
- **Bounded exemption for guidance-only skills.** A skill is exempt from the task requirement only
  if it invokes no mutating tools and produces no durable artifacts (read-only tool calls and pure
  guidance qualify; a single mutation step anywhere in the playbook voids the exemption). The
  exemption must be explicitly declared in the skill's adoption record — every adoption states its
  position: tasks, or a declared reason for none. Exempt skills remain indirectly measured, since
  they operate inside workflows the suite already grades.
- **Authoring constraint: do not rely on SKILL.md `allowed-tools`.** The eval runner is the Claude
  Agent SDK (issue #25), which ignores the `allowed-tools` frontmatter (it is CLI-only). Tool
  restriction for eval runs belongs in the runner's `allowed_tools` configuration; a skill whose
  safety story depends on frontmatter restriction is unsound under the harness.

## Consequences

Every capability claim is measurable the day it is made, and a harmful skill is caught as a
pass-rate drop rather than by vibes. The per-skill cost is real — prompt, fixture, graders, and one
witnessed run on top of authoring the skill — and fixture authoring can exceed the skill's own cost;
this is accepted as the price of no unmeasured SUT surface. The declared-exemption rule keeps the
carve-out from becoming a default path: silence is not an option. Because tasks are workflow-owned,
deleting or rewriting a skill never orphans its tasks. This ADR also sets a repo convention:
accepted ADRs are not retro-edited; new decisions get new numbers and cross-references (ADR 0005
carries a dated pointer here).
