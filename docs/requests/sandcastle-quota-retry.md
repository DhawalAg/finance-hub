# Sandcastle Quota-Aware Retry Spec

**Status:** Approved for implementation
**Updated:** 2026-06-22

## Problem

`npm run sandcastle` can fail every active agent when Claude Code reaches its session limit:

```text
You've hit your session limit · resets 7:10am (UTC)
```

Sandcastle currently treats that as an ordinary agent failure. In the parallel planner flow this means:

1. The planner may successfully choose a batch of issues.
2. Implementers start on deterministic branches such as `sandcastle/issue-3`.
3. Claude Code exits with code `1` for each implementer once quota is exhausted.
4. `Promise.allSettled(...)` records those issue pipelines as rejected.
5. The script reports zero completed branches and exits.

That behavior loses orchestration context even when local branch worktrees survive. Quota exhaustion is
not a task failure, review failure, merge failure, or code-quality signal. It is a provider-level
backoff condition, so the runner should pause and resume instead of terminating the current iteration.

This proposal should be evaluated alongside
[`sandcastle-sequential-reviewer.md`](./sandcastle-sequential-reviewer.md). The sequential workflow
reduces quota blast radius by processing one issue at a time, but it still needs the same
quota-aware retry behavior around its planner, implementer, reviewer, and merger calls.

## Goals

- Treat Claude session-limit errors as a retryable pause condition.
- Keep the current Sandcastle process alive so it can retain the planner output, issue list, branch
  names, sandbox/worktree handles, and phase.
- Resume the same agent operation after the reset time instead of requiring a human to re-run the
  command.
- Preserve deterministic issue branch behavior: `sandcastle/issue-{id}` remains the durable unit of
  continuation.
- Avoid a thundering herd after quota refresh when multiple parallel agents fail at once.
- Support both Sandcastle runners:
  - existing parallel runner: `.sandcastle/main.mts`
  - proposed sequential reviewer runner: `.sandcastle/main.sequential-reviewer.mts`
- Make terminal output clear enough that an unattended run can be inspected later.
- Provide an opt-out mode for users who prefer the process to exit instead of waiting.

## Non-Goals

- Do not change issue selection, branch naming, prompt contents, or merge behavior.
- Do not create commits, stashes, or git mutations solely because quota was reached.
- Do not attempt to bypass provider limits or rotate credentials.
- Do not require an outer shell loop around `npm run sandcastle`.
- Do not depend on Claude-specific internals beyond parsing the user-facing quota message.

## Desired Behavior

Every call that invokes an agent should be quota-aware.

For the existing parallel runner:

- planner: `sandcastle.run(...)`
- implementer: `sandbox.run(...)`
- reviewer: `sandbox.run(...)`
- merger: `sandcastle.run(...)`

For the proposed sequential reviewer runner:

- picker/planner: `sandcastle.run(...)`
- implementer: `sandbox.run(...)`
- reviewer: `sandbox.run(...)`
- merger: `sandcastle.run(...)`

The shared helper should be implemented even if only the parallel runner exists at first. Sequential
examples and smoke tests are conditional until `.sandcastle/main.sequential-reviewer.mts` and
`npm run sandcastle:sequential` exist.

If the call succeeds, behavior is unchanged.

If the call fails with a non-quota error, behavior is unchanged.

If the call fails with a recognized quota error:

1. Parse the reset time from the error message.
2. Compute a wait duration using the reset time plus a small safety buffer.
3. Print a clear pause message with the affected phase and retry time.
4. Sleep until the retry time.
5. Retry the same operation.

Example terminal output:

```text
[implementer issue 5] Claude quota reached. Reset: 2026-06-22 07:10 UTC.
[implementer issue 5] Waiting 43m 12s, then retrying in the same issue worktree.
```

## Error Classification

Add a helper that classifies thrown values:

```ts
type QuotaLimit = {
  kind: "quota-limit";
  provider: "claude-code";
  resetAt: Date | null;
  rawMessage: string;
  resetPhrase: string | null;
};

type RetryableAgentError = QuotaLimit;
```

The classifier should:

- Convert unknown thrown values to a string using the error message, stack, and/or `String(error)`.
- Walk ordinary `cause` chains when present so Sandcastle wrapper errors do not hide the provider
  message.
- Match the known Claude Code wording:

  ```text
  You've hit your session limit · resets 7:10am (UTC)
  ```

- Be tolerant of formatting differences:
  - `resets 7:10am (UTC)`
  - `resets 7:10AM (UTC)`
  - `resets 07:10 (UTC)`
  - `resets 19:10 (UTC)`
  - additional surrounding text from Sandcastle's `AgentError`

Initial recognition regex:

```ts
/hit your session limit[\s\S]*?resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*\(UTC\)/i
```

If a message says the session limit was reached but no reset time can be parsed, classify it as quota
with `resetAt: null`. The runner should then use `SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS`, defaulting to
15 minutes, while printing that the reset time could not be parsed.

Parsing rules:

- With `am`/`pm`, use standard 12-hour conversion: `12am` is `00:00`, `12pm` is `12:00`.
- Without `am`/`pm`, treat the hour as 24-hour UTC. Reject hours greater than `23` and minutes greater
  than `59`.
- Preserve the original reset phrase in `resetPhrase` for logging.

## Reset Time Rules

Claude's message gives a time of day in UTC, not a full date. Convert it to an absolute `Date`:

1. Use current wall-clock time.
2. Interpret the parsed time as UTC today.
3. If that timestamp is less than or equal to now, move it to UTC tomorrow.
4. Add `SANDCASTLE_QUOTA_BUFFER_MS`, defaulting to `120000` milliseconds.
5. Clamp tiny or negative waits to a minimum retry delay, defaulting to `60000` milliseconds.
6. If `resetAt` is `null`, skip date conversion and compute `retryAt` from
   `now + SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS`.

Example:

- Current time: `2026-06-22T06:30:00Z`
- Message: `resets 7:10am (UTC)`
- Parsed reset: `2026-06-22T07:10:00Z`
- Retry time with 2 minute buffer: `2026-06-22T07:12:00Z`

If current time is `2026-06-22T08:00:00Z`, the same message becomes:

```text
2026-06-23T07:12:00Z
```

## Retry Wrapper

Introduce a small wrapper around agent calls. This should be shared runner infrastructure, not copied
separately into each workflow.

Preferred location:

```text
.sandcastle/quota.mts
```

Both runners should import the shared helper:

```text
.sandcastle/main.mts
.sandcastle/main.sequential-reviewer.mts
```

Core wrapper:

```ts
async function runWithQuotaBackoff<T>(
  label: string,
  operation: () => Promise<T>,
  options: {
    workflow: "parallel" | "sequential";
    gate?: QuotaGate;
  },
): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      await options.gate?.waitIfPaused(label);
      return await operation();
    } catch (error) {
      const quota = parseQuotaLimit(error);
      if (!quota) {
        throw error;
      }

      if (!WAIT_FOR_QUOTA) {
        throw new Error(formatQuotaExitMessage(label, quota), { cause: error });
      }

      if (MAX_QUOTA_RETRIES !== undefined && attempt > MAX_QUOTA_RETRIES) {
        throw new Error(formatQuotaRetriesExceededMessage(label, quota, attempt - 1), {
          cause: error,
        });
      }

      const retryAt = computeRetryAt(quota.resetAt);
      const waitMs = Math.max(retryAt.getTime() - Date.now(), MIN_QUOTA_WAIT_MS);

      if (options.gate) {
        await options.gate.pauseUntil(label, retryAt, quota, attempt);
        continue;
      }

      console.log(formatQuotaWaitMessage(label, quota, retryAt, waitMs, attempt));
      await sleep(waitMs);
    }
  }
}
```

Apply it at the call site rather than inside Sandcastle internals:

```ts
const plan = await runWithQuotaBackoff("planner", () =>
  sandcastle.run({
    hooks,
    sandbox: docker(),
    name: "planner",
    maxIterations: 1,
    agent: sandcastle.claudeCode(PLAN_MODEL),
    promptFile: "./.sandcastle/plan-prompt.md",
    output: sandcastle.Output.object({ tag: "plan", schema: planSchema }),
  }),
  { workflow: "parallel" },
);
```

For implementers:

```ts
const implement = await runWithQuotaBackoff(`implementer issue ${issue.id}`, () =>
  sandbox.run({
    name: "implementer",
    maxIterations: 100,
    agent: sandcastle.claudeCode(IMPLEMENT_MODEL),
    promptFile: "./.sandcastle/implement-prompt.md",
    promptArgs: {
      TASK_ID: issue.id,
      ISSUE_TITLE: issue.title,
      BRANCH: issue.branch,
    },
  }),
  { workflow: "parallel", gate: quotaGate },
);
```

In sequential mode, this wrapper is enough for the core retry behavior. If the implementer for issue
`5` hits quota, the sequential runner should wait and retry that same implementer operation for
`sandcastle/issue-5`; it should not re-run the picker first.

Retry scope:

- `SANDCASTLE_MAX_QUOTA_RETRIES` is counted per wrapped operation, not globally across the whole run.
- A retry means re-invoking the same callback in the same surrounding control-flow frame. For
  implementer/reviewer calls this keeps the current sandbox object alive while sleeping and retries
  `sandbox.run(...)` in that same sandbox.
- The wrapper must not catch errors from `sandbox.close()` as quota errors. Close failures are cleanup
  failures and should remain ordinary failures.

## Parallel Batch Coordination

The current implementation starts all issue pipelines concurrently with `Promise.allSettled(...)`.
If quota is exhausted, every active implementer may observe the same quota failure. A naive wrapper
around each implementer would make every issue sleep independently and then wake at the same time.

This section is parallel-runner-specific. The sequential reviewer runner processes one issue at a
time, so it does not need a quota gate for multiple concurrent implementers.

Use a process-wide quota gate, preferably exported by `.sandcastle/quota.mts`, to coordinate parallel
retries:

```ts
class QuotaGate {
  private resumeAt: Date | undefined;
  private waiter: Promise<void> | undefined;
  private hasPaused = false;

  async waitIfPaused(label: string): Promise<void>;
  async pauseUntil(label: string, retryAt: Date, quota: QuotaLimit, attempt: number): Promise<void>;
  hasPausedForQuota(): boolean;
}
```

Behavior:

- Before each agent attempt, call `quotaGate.waitIfPaused(label)`.
- When any agent catches a quota error, call `quotaGate.pauseUntil(label, retryAt)`.
- If another agent also catches the same quota error, it should observe the same gate and join the
  existing sleep rather than creating an independent timer.
- If a later error reports a later reset time, extend the gate to the later time.
- If an agent reaches the gate after the pause has elapsed, it should continue immediately.
- Planner and merger calls may use the same gate for consistency, but the critical coordination point
  is implementer/reviewer concurrency.

Terminal output should only print the primary wait message once per pause window, then shorter
messages for other workers:

```text
[quota] Claude quota reached by implementer issue 3. Reset: 2026-06-22 07:10 UTC.
[quota] Pausing all agent calls until 2026-06-22 07:12 UTC.
[implementer issue 5] Joined existing quota pause.
[implementer issue 9] Joined existing quota pause.
```

## Concurrency After Resume

After a quota reset, immediately restarting three or more agents can consume the refreshed budget too
quickly. Add a configurable concurrency limiter for issue implementation.

This section is also parallel-runner-specific. The sequential reviewer is already limited to one
issue pipeline, so it should ignore `SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS` and
`SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA`.

Recommended config:

```text
SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS=3
SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA=1
```

Behavior:

- Normal runs keep the existing parallelism unless configured otherwise.
- Once a quota pause has occurred, remaining implementer attempts use
  `SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA`.
- Default after-quota concurrency should be `1` for safety.

This can be implemented by replacing unbounded `Promise.allSettled(issues.map(...))` with a small
local async pool. The pool must preserve the existing result shape and ordering:

- Return a `PromiseSettledResult` entry for every issue.
- Keep `settled[i]` aligned with `issues[i]`, because merge selection and error logging currently
  depend on that index relationship.
- Do not let one rejected issue stop the pool from starting later queued issues, unless the process is
  exiting because fail-fast quota mode, max quota retries, or a non-recoverable top-level error fired.
- Existing in-flight agents do not need to be canceled when quota is first detected; the gate controls
  retries and later queued starts.

## Configuration

Environment variables:

| Variable | Default | Meaning |
|---|---:|---|
| `SANDCASTLE_WAIT_FOR_QUOTA` | `1` | Wait and retry on recognized quota errors. Set to `0` to fail fast. |
| `SANDCASTLE_QUOTA_BUFFER_MS` | `120000` | Extra wait after the parsed reset time. |
| `SANDCASTLE_MIN_QUOTA_WAIT_MS` | `60000` | Minimum wait if reset parsing yields a past or near-current time. |
| `SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS` | `900000` | Fallback wait when quota is recognized but reset time cannot be parsed. |
| `SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS` | issue count | Normal implementer concurrency. |
| `SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA` | `1` | Implementer concurrency after at least one quota pause. |
| `SANDCASTLE_MAX_QUOTA_RETRIES` | unset | Optional cap. If unset, retry indefinitely. |

Fail-fast example:

```bash
SANDCASTLE_WAIT_FOR_QUOTA=0 npm run sandcastle
```

Conservative unattended example:

```bash
MAX_ITERATIONS=2 SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA=1 npm run sandcastle
```

Sequential unattended example:

```bash
MAX_ITERATIONS=3 npm run sandcastle:sequential
```

This command is only expected to work after the sequential reviewer spec has added the script.

In sequential mode, quota retry should still honor:

- `SANDCASTLE_WAIT_FOR_QUOTA`
- `SANDCASTLE_QUOTA_BUFFER_MS`
- `SANDCASTLE_MIN_QUOTA_WAIT_MS`
- `SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS`
- `SANDCASTLE_MAX_QUOTA_RETRIES`

Sequential mode should not need to honor:

- `SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS`
- `SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA`

## Git And Worktree Semantics

Quota-aware retry should not introduce new git behavior.

Expected semantics:

- If the same sandbox/worktree remains open while waiting, retry in that same worktree.
- Sandcastle documents that `sandbox.close()` preserves dirty worktrees and removes clean ones. The
  retry implementation should not change that lifecycle.
- If Sandcastle closes or preserves a worktree because of a failure or interruption, later runs still
  use deterministic branch names and should see branch commits.
- Uncommitted dirty work in preserved worktrees is local state. The retry system should not depend on
  it for correctness, but it should avoid deleting it.
- Existing logic that includes branches with unmerged commits should remain unchanged.

This keeps committed progress as the reliable continuation mechanism while allowing same-process
retries to continue from in-flight worktree state.

Sequential reviewer interaction:

- The sequential workflow intentionally prefers existing checkpoint branches such as
  `sandcastle/issue-3`, `sandcastle/issue-5`, and `sandcastle/issue-9`.
- If quota hits during sequential implementation, the retry should continue the selected issue before
  selecting a new one.
- If the process is interrupted while waiting, the next sequential run should still use deterministic
  branch names and the sequential spec's unmerged-commit check.
- Quota retry should not promote dirty worktree state into commits; the implementer or reviewer must
  still make normal commits as part of its task.

## Exit Behavior

If waiting is enabled and quota is recognized, the process should not exit merely because quota was
reached.

If waiting is disabled, exit with a clear nonzero error:

```text
Claude quota reached during implementer issue 5.
Reset: 2026-06-22 07:10 UTC.
SANDCASTLE_WAIT_FOR_QUOTA=0, so exiting instead of waiting.
```

If quota retry count exceeds `SANDCASTLE_MAX_QUOTA_RETRIES`, exit with a clear nonzero error:

```text
Claude quota reached during reviewer issue 3.
Maximum quota retries reached: 3.
Last reset: 2026-06-22 07:10 UTC.
```

If the process receives `SIGINT` while sleeping, it should exit promptly and rely on existing
Sandcastle cleanup/preservation behavior.

Implementation detail: `sleep(...)` should not swallow signals or keep retrying after an abort. If an
`AbortSignal` is introduced later, cancellation should reject the sleep and surface as an ordinary
interruption, not as a quota retry.

## Observability

Log enough information to understand unattended runs:

- phase label: planner, implementer issue id, reviewer issue id, merger
- workflow label: `parallel` or `sequential`
- original reset phrase
- computed absolute retry time
- wait duration
- retry attempt count
- whether the worker initiated or joined a shared quota pause
- concurrency reduction after quota recovery
- fail-fast or retry-exhausted reason when the wrapper exits instead of waiting

Avoid logging provider tokens or environment contents.

## Test Plan

Add unit tests around pure helpers if/when this is implemented:

1. Parses `You've hit your session limit · resets 7:10am (UTC)`.
2. Parses uppercase `AM` / `PM`.
3. Parses 24-hour format with no meridiem.
4. Converts `12am` to `00:00` and `12pm` to `12:00`.
5. Rejects invalid no-meridiem times such as `25:10 (UTC)`.
6. Finds quota text inside an error `cause` chain.
7. Ignores ordinary agent errors.
8. Converts a future reset time to today's UTC date.
9. Converts a past reset time to tomorrow's UTC date.
10. Adds the configured buffer.
11. Uses fallback wait when the message contains a quota phrase but no parseable reset time.
12. Honors `SANDCASTLE_WAIT_FOR_QUOTA=0`.
13. Stops after `SANDCASTLE_MAX_QUOTA_RETRIES` for a single wrapped operation.
14. Coordinates multiple simultaneous quota errors through one gate.
15. Extends the gate when a later reset time appears.
16. Keeps async-pool results aligned with the original `issues` array.
17. Reduces implementer concurrency after a quota pause.
18. Sequential mode retries the same selected issue after quota without re-running the picker.
19. Sequential mode ignores parallel-only concurrency settings.

Manual smoke test:

1. Temporarily wrap a fake operation that throws the known quota message.
2. Set a near-future reset time.
3. Run `npm run sandcastle` or a focused helper harness for the parallel runner.
4. Confirm the parallel runner waits, retries, and then proceeds.
5. If the sequential runner exists, run `npm run sandcastle:sequential` or a focused helper harness.
6. Confirm the sequential runner waits, retries the same selected issue, and then proceeds.

## Rollout Plan

1. Add pure helper functions to a sibling module under `.sandcastle/`, preferably
   `.sandcastle/quota.mts`.
2. Add focused tests for parsing, reset computation, and gate coordination if the repo has a suitable
   TypeScript test runner. Otherwise, keep the helpers small and manually smoke test them.
3. Wrap planner, implementer, reviewer, and merger agent calls in `.sandcastle/main.mts`.
4. If implementing the sequential reviewer spec at the same time, wrap picker/planner, implementer,
   reviewer, and merger calls in `.sandcastle/main.sequential-reviewer.mts`.
5. Replace unbounded implementer `Promise.allSettled(...)` with a small async pool only if
   after-quota concurrency control is implemented in the same change.
6. Run a short `MAX_ITERATIONS=1` smoke test for the parallel runner.
7. Run a short `MAX_ITERATIONS=1 npm run sandcastle:sequential` smoke test if the sequential runner
   exists.
8. Document the environment variables near the Sandcastle command in the README if the behavior proves
   useful.

## Acceptance Criteria

- A Claude session-limit message no longer causes the whole Sandcastle process to exit when
  `SANDCASTLE_WAIT_FOR_QUOTA` is enabled.
- The runner prints the parsed reset time and computed retry time.
- Multiple parallel implementers join one shared quota pause.
- After the pause, the failed agent operation is retried without re-running earlier phases in the same
  process.
- In sequential mode, after the pause, the failed agent operation is retried for the same selected
  issue and branch.
- Non-quota agent failures still behave as failures.
- `SANDCASTLE_WAIT_FOR_QUOTA=0` preserves fail-fast behavior.

## Grill-Me Focus Areas

When using `/grill-me` on this design, evaluate it together with
[`sandcastle-sequential-reviewer.md`](./sandcastle-sequential-reviewer.md). The key questions are:

1. Should quota-aware retry be implemented before, after, or alongside the sequential reviewer runner?
   Recommended answer: implement the shared `.sandcastle/quota.mts` helper first or in the same change,
   then use it from whichever runner exists.
2. Should the sequential workflow become the default way to avoid quota pressure?
   Recommended answer: keep both workflows. Sequential mode is safer for quota and recovery; parallel
   mode is still useful when provider budget is available.
3. Should quota retry wait indefinitely by default?
   Recommended answer: yes for local unattended Sandcastle runs, with `SANDCASTLE_WAIT_FOR_QUOTA=0`
   and `SANDCASTLE_MAX_QUOTA_RETRIES` as escape hatches.
4. Should the retry helper ever auto-commit, stash, or clean worktrees before sleeping?
   Recommended answer: no. Retry is provider scheduling behavior; git state remains the agent's job.
5. Does the parallel runner need a shared quota gate if sequential mode exists?
   Recommended answer: yes, if parallel mode remains available. Without the gate, concurrent workers
   can all sleep and wake independently after the same quota event.
