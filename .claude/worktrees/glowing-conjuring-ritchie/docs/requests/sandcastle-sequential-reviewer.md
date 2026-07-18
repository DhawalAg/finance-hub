# Sandcastle Sequential Reviewer Spec

**Status:** Proposed
**Updated:** 2026-06-22

## Goal

Add a second Sandcastle workflow that runs issues sequentially while preserving
the existing parallel workflow.

The existing parallel setup must remain available unchanged. The new sequential
setup should pick up from branches left by the failed parallel run, process one
issue at a time, review it, then merge it through the same agent-driven merge
semantics as the parallel workflow.

## Existing State

Current parallel workflow:

```text
.sandcastle/main.mts
  planner agent
  -> parallel implementer agents
  -> parallel reviewer agents
  -> merger agent
```

Current prompt files:

```text
.sandcastle/plan-prompt.md
.sandcastle/implement-prompt.md
.sandcastle/review-prompt.md
.sandcastle/merge-prompt.md
```

Known checkpoint branches may already exist:

```text
sandcastle/issue-2
sandcastle/issue-3
sandcastle/issue-5
sandcastle/issue-9
```

Do not delete or rename these.

## New Files

Add:

```text
.sandcastle/main.sequential-reviewer.mts
.sandcastle/sequential-plan-prompt.md
```

Update `package.json` scripts to expose both workflows:

```json
{
  "scripts": {
    "sandcastle": "npx tsx .sandcastle/main.mts",
    "sandcastle:parallel": "npx tsx .sandcastle/main.mts",
    "sandcastle:sequential": "npx tsx .sandcastle/main.sequential-reviewer.mts"
  }
}
```

## Sequential Flow

Each iteration processes exactly one issue:

```text
1. Run lightweight planner/picker.
2. Pick one ready issue.
3. Use deterministic branch: sandcastle/issue-{id}
4. Create/reuse sandbox on that branch.
5. Run implementer.
6. If implementation produced commits or branch already has unmerged commits, run reviewer.
7. Run merger agent for that one branch.
8. Merger runs pytest, resolves conflicts if needed, makes merge commit, closes issue.
9. Repeat up to MAX_ITERATIONS.
```

## Model Requirements

Use environment-overridable model constants.

Defaults:

```ts
const PLAN_MODEL = process.env.SANDCASTLE_PLAN_MODEL ?? "claude-sonnet-4-6";
const IMPLEMENT_MODEL =
  process.env.SANDCASTLE_IMPLEMENT_MODEL ?? "claude-opus-4-8";
const REVIEW_MODEL =
  process.env.SANDCASTLE_REVIEW_MODEL ?? "claude-sonnet-4-6";
const MERGE_MODEL =
  process.env.SANDCASTLE_MERGE_MODEL ?? "claude-sonnet-4-6";
```

Before running for real, confirm Claude Code accepts `claude-opus-4-8` as the
exact model string. If not, change only the default string, not the workflow
design.

## Repo-Specific Runtime

Keep the Python project setup from the existing parallel workflow:

```ts
const hooks = {
  sandbox: {
    onSandboxReady: [
      { command: 'pip install -e ".[dev,market-data,analysis]"' },
    ],
  },
};

const copyToWorktree: string[] = [];
```

Do not use the stock sequential template's `npm install` or `node_modules`
behavior.

## Planner/Pick Step

`sequential-plan-prompt.md` should output one issue, not a batch.

Output schema:

```ts
const issueSchema = z.object({
  issue: z
    .object({
      id: z.string(),
      title: z.string(),
      branch: z.string(),
    })
    .nullable(),
});
```

Expected output:

```xml
<issue>
{"issue":{"id":"5","title":"...", "branch":"sandcastle/issue-5"}}
</issue>
```

If no actionable issue exists:

```xml
<issue>
{"issue":null}
</issue>
```

Selection rules:

```text
- Read open GitHub issues with label ready-for-agent.
- Prefer existing checkpoint branches sandcastle/issue-{id}.
- Pick only one issue.
- Use branch name exactly sandcastle/issue-{id}.
- Avoid timestamp branches.
- Do not choose multiple parallel issues.
```

## Implementation Step

Reuse existing:

```text
.sandcastle/implement-prompt.md
```

Pass:

```ts
promptArgs: {
  TASK_ID: issue.id,
  ISSUE_TITLE: issue.title,
  BRANCH: issue.branch,
}
```

Run with:

```ts
agent: sandcastle.claudeCode(IMPLEMENT_MODEL)
```

## Review Step

Reuse existing:

```text
.sandcastle/review-prompt.md
```

Pass:

```ts
promptArgs: {
  BRANCH: issue.branch,
}
```

Run with:

```ts
agent: sandcastle.claudeCode(REVIEW_MODEL)
```

## Merge Step

Reuse existing:

```text
.sandcastle/merge-prompt.md
```

For sequential mode, pass a single branch and single issue:

```ts
promptArgs: {
  BRANCHES: `- ${issue.branch}`,
  ISSUES: `- ${issue.id}: ${issue.title}`,
}
```

Run with:

```ts
agent: sandcastle.claudeCode(MERGE_MODEL)
```

This intentionally mirrors the parallel workflow's agent-driven merge behavior.

## Checkpoint Behavior

Before deciding to skip an issue, the runner should detect whether the branch
already contains unmerged commits:

```text
git rev-list --count HEAD..sandcastle/issue-{id}
```

If the branch has unmerged commits from the failed parallel run, it should still
be eligible for review/merge even if the new implementer produces no commits.

## Stop Conditions

Stop when:

```text
- planner returns issue: null
- MAX_ITERATIONS is reached
- selected issue produces no commits and has no unmerged branch commits
```

Non-quota agent failures should behave like current Sandcastle failures: log and
stop/fail rather than silently continuing.

## Non-Goals

Do not modify the existing parallel `.sandcastle/main.mts`.

Do not remove `plan-prompt.md`, `merge-prompt.md`, logs, or worktrees.

Do not invent a new issue lifecycle.

Do not replace the current merge prompt with deterministic script merging.

Do not close issues outside the merger agent; keep closing behavior centralized
in `merge-prompt.md`.

## Expected Commands

After implementation:

```bash
npm run sandcastle:sequential
```

Existing behavior remains:

```bash
npm run sandcastle:parallel
npm run sandcastle
```
