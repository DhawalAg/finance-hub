// Parallel Planner with Review — four-phase orchestration loop
//
// This template drives a multi-phase workflow:
//   Phase 1 (Plan):             An opus agent analyzes open issues, builds a
//                               dependency graph, and outputs a <plan> JSON
//                               listing unblocked issues with branch names.
//   Phase 2 (Execute + Review): For each issue, a sandbox is created via
//                               createSandbox(). The implementer runs first
//                               (100 iterations). If it produces commits, a
//                               reviewer runs in the same sandbox on the same
//                               branch (1 iteration). Issue pipelines run
//                               through an ordered async pool.
//   Phase 3 (Merge):            A single agent merges all completed branches
//                               into the current branch.
//
// The outer loop repeats up to MAX_ITERATIONS times so that newly unblocked
// issues are picked up after each round of merges.
//
// Usage:
//   npx tsx .sandcastle/main.mts
// Or add to package.json:
//   "scripts": { "sandcastle": "npx tsx .sandcastle/main.mts" }

import * as sandcastle from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { z } from "zod";
import {
  DynamicLimiter,
  QuotaGate,
  parseQuotaLimit,
  readPositiveInteger,
  runSettledPool,
  runWithQuotaBackoff,
} from "./quota.mts";

// The planner emits its plan as JSON inside <plan> tags; Output.object extracts
// and validates it against this schema. We use Zod here, but any Standard
// Schema validator works just as well — Valibot, ArkType, etc. See
// https://standardschema.dev.
const planSchema = z.object({
  issues: z.array(
    z.object({ id: z.string(), title: z.string(), branch: z.string() }),
  ),
});

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Maximum number of plan→execute→merge cycles before stopping.
// Override with MAX_ITERATIONS=1 for a quick smoke-test run.
const MAX_ITERATIONS = Number.parseInt(process.env.MAX_ITERATIONS ?? "10", 10);
if (!Number.isInteger(MAX_ITERATIONS) || MAX_ITERATIONS < 1) {
  throw new Error("MAX_ITERATIONS must be a positive integer.");
}

const PLAN_MODEL = process.env.SANDCASTLE_PLAN_MODEL ?? "claude-opus-4-8";
const IMPLEMENT_MODEL =
  process.env.SANDCASTLE_IMPLEMENT_MODEL ?? "claude-sonnet-4-6";
const REVIEW_MODEL =
  process.env.SANDCASTLE_REVIEW_MODEL ?? "claude-opus-4-8";
const MERGE_MODEL = process.env.SANDCASTLE_MERGE_MODEL ?? "claude-sonnet-4-6";
const DEFAULT_AGENT = (process.env.SANDCASTLE_AGENT ?? "claude").toLowerCase();
const quotaGate = new QuotaGate();
const codexHome = join(homedir(), ".codex");
const sandboxMounts = existsSync(codexHome)
  ? [{ hostPath: codexHome, sandboxPath: "/home/agent/.codex" }]
  : [];

// Hooks run inside the sandbox before the agent starts each iteration.
// Install the Python project editable with all optional dependency groups used
// by this repo so agents can run pytest against the mounted worktree.
const hooks = {
  sandbox: {
    onSandboxReady: [{ command: 'pip install -e ".[dev,market-data,analysis]"' }],
  },
};

// No host dependency directories are copied for this Python project. The
// sandbox image owns its virtualenv, and the hook installs the mounted worktree.
const copyToWorktree: string[] = [];
const sandboxProvider = docker({ mounts: sandboxMounts });

const resolveAgent = (
  phase: "PLAN" | "IMPLEMENT" | "REVIEW" | "MERGE",
  claudeModel: string,
) => {
  const provider = (
    process.env[`SANDCASTLE_${phase}_AGENT`] ?? DEFAULT_AGENT
  ).toLowerCase();

  if (provider === "codex") {
    const model =
      process.env[`SANDCASTLE_${phase}_CODEX_MODEL`] ??
      process.env.SANDCASTLE_CODEX_MODEL ??
      "gpt-5.5";
    const effort = process.env.SANDCASTLE_CODEX_EFFORT ?? "medium";
    const approvalsReviewer = process.env.SANDCASTLE_CODEX_APPROVALS_REVIEWER;
    const codexOptions: Parameters<typeof sandcastle.codex>[1] = {
      env: {
        CODEX_HOME: "/home/agent/.codex",
      },
    };

    codexOptions.effort = effort as "low" | "medium" | "high" | "xhigh";

    if (approvalsReviewer === "user" || approvalsReviewer === "auto_review") {
      codexOptions.approvalsReviewer = approvalsReviewer;
    }

    return sandcastle.codex(model, codexOptions);
  }

  return sandcastle.claudeCode(
    process.env[`SANDCASTLE_${phase}_MODEL`] ?? claudeModel,
  );
};

const branchHasUnmergedCommits = (branch: string) => {
  try {
    const count = execFileSync("git", ["rev-list", "--count", `HEAD..${branch}`], {
      encoding: "utf8",
    });
    return Number.parseInt(count.trim(), 10) > 0;
  } catch {
    return false;
  }
};

const issueConcurrency = (issueCount: number) =>
  readPositiveInteger(
    process.env.SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS,
    issueCount,
    "SANDCASTLE_MAX_PARALLEL_IMPLEMENTERS",
  );

const afterQuotaConcurrency = () =>
  readPositiveInteger(
    process.env.SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA,
    1,
    "SANDCASTLE_MAX_PARALLEL_AFTER_QUOTA",
  );
const afterQuotaAgentLimiter = new DynamicLimiter(afterQuotaConcurrency);

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
  console.log(`\n=== Iteration ${iteration}/${MAX_ITERATIONS} ===\n`);

  // -------------------------------------------------------------------------
  // Phase 1: Plan
  //
  // The planning agent (opus, for deeper reasoning) reads the open issue list,
  // builds a dependency graph, and selects the issues that can be worked in
  // parallel right now (i.e., no blocking dependencies on other open issues).
  //
  // It outputs a <plan> JSON block — Output.object parses and validates it.
  // -------------------------------------------------------------------------
  const plan = await runWithQuotaBackoff(
    "planner",
    () =>
      sandcastle.run({
        hooks,
        sandbox: sandboxProvider,
        name: "planner",
        // One iteration is enough: the planner just needs to read and reason,
        // not write code. (Structured output requires maxIterations: 1.)
        maxIterations: 1,
        agent: resolveAgent("PLAN", PLAN_MODEL),
        promptFile: "./.sandcastle/plan-prompt.md",
        // Extract and validate the <plan> JSON into a typed object. Throws
        // StructuredOutputError if the tag is missing, the JSON is malformed, or
        // validation fails — which aborts the loop.
        output: sandcastle.Output.object({ tag: "plan", schema: planSchema }),
      }),
    { workflow: "parallel", gate: quotaGate },
  );

  const issues = plan.output.issues;

  if (issues.length === 0) {
    // No unblocked work — either everything is done or everything is blocked.
    console.log("No unblocked issues to work on. Exiting.");
    break;
  }

  console.log(
    `Planning complete. ${issues.length} issue(s) to work in parallel:`,
  );
  for (const issue of issues) {
    console.log(`  ${issue.id}: ${issue.title} → ${issue.branch}`);
  }

  // -------------------------------------------------------------------------
  // Phase 2: Execute + Review
  //
  // For each issue, create a sandbox via createSandbox() so the implementer
  // and reviewer share the same sandbox instance per branch. The implementer
  // runs first; if it produces commits, the reviewer runs in the same sandbox.
  //
  // The settled pool means one failing pipeline doesn't cancel the others.
  // -------------------------------------------------------------------------

  let loggedQuotaConcurrencyReduction = false;
  const normalIssueConcurrency = issueConcurrency(issues.length);
  const settled = await runSettledPool(
    issues,
    async (issue) => {
      const issueSandbox = await sandcastle.createSandbox({
        branch: issue.branch,
        sandbox: sandboxProvider,
        hooks,
        copyToWorktree,
      });

      try {
        // Run the implementer
        const implement = await runWithQuotaBackoff(
          `implementer issue ${issue.id}`,
          () =>
            issueSandbox.run({
              name: "implementer",
              maxIterations: 100,
              agent: resolveAgent("IMPLEMENT", IMPLEMENT_MODEL),
              promptFile: "./.sandcastle/implement-prompt.md",
              promptArgs: {
                TASK_ID: issue.id,
                ISSUE_TITLE: issue.title,
                BRANCH: issue.branch,
              },
            }),
          {
            workflow: "parallel",
            gate: quotaGate,
            afterQuotaLimiter: afterQuotaAgentLimiter,
          },
        );

        // Only review if the implementer produced commits
        if (implement.commits.length > 0) {
          try {
            const review = await runWithQuotaBackoff(
              `reviewer issue ${issue.id}`,
              () =>
                issueSandbox.run({
                  name: "reviewer",
                  maxIterations: 1,
                  agent: resolveAgent("REVIEW", REVIEW_MODEL),
                  promptFile: "./.sandcastle/review-prompt.md",
                  promptArgs: {
                    BRANCH: issue.branch,
                  },
                }),
              {
                workflow: "parallel",
                gate: quotaGate,
                afterQuotaLimiter: afterQuotaAgentLimiter,
              },
            );

            // Merge commits from both runs so the merge phase sees all of them.
            // Each sandbox.run() only returns commits from its own run.
            return {
              ...review,
              commits: [...implement.commits, ...review.commits],
            };
          } catch (error) {
            if (parseQuotaLimit(error)) {
              throw error;
            }
            console.error(
              `  ✗ ${issue.id} (${issue.branch}) review failed after implementation commits; keeping implementer result for merge: ${error}`,
            );
            return implement;
          }
        }

        return implement;
      } finally {
        await issueSandbox.close();
      }
    },
    {
      getConcurrency: () => {
        if (!quotaGate.hasPausedForQuota()) {
          return normalIssueConcurrency;
        }

        const concurrency = afterQuotaConcurrency();
        if (!loggedQuotaConcurrencyReduction) {
          console.log(
            `[quota] Reducing parallel implementer concurrency to ${concurrency} after quota pause.`,
          );
          loggedQuotaConcurrencyReduction = true;
        }
        return concurrency;
      },
    },
  );

  // Log any agents that threw (network error, sandbox crash, etc.).
  for (const [i, outcome] of settled.entries()) {
    if (outcome.status === "rejected") {
      console.error(
        `  ✗ ${issues[i]!.id} (${issues[i]!.branch}) failed: ${outcome.reason}`,
      );
    }
  }
  const quotaFailure = settled.find(
    (outcome) =>
      outcome.status === "rejected" && parseQuotaLimit(outcome.reason),
  );
  if (quotaFailure?.status === "rejected") {
    throw quotaFailure.reason;
  }

  // Only pass branches that actually produced commits to the merge phase.
  // Also include branches that already have unmerged commits from a prior run,
  // so a failed reviewer or quota reset does not strand useful work.
  const completedIssues = settled
    .map((outcome, i) => ({ outcome, issue: issues[i]! }))
    .filter(
      (entry) =>
        (entry.outcome.status === "fulfilled" &&
          entry.outcome.value.commits.length > 0) ||
        branchHasUnmergedCommits(entry.issue.branch),
    )
    .map((entry) => entry.issue);

  const completedBranches = completedIssues.map((i) => i.branch);

  console.log(
    `\nExecution complete. ${completedBranches.length} branch(es) with commits:`,
  );
  for (const branch of completedBranches) {
    console.log(`  ${branch}`);
  }

  if (completedBranches.length === 0) {
    // All agents ran but none made commits — nothing to merge this cycle.
    console.log("No commits produced. Nothing to merge.");
    break;
  }

  // -------------------------------------------------------------------------
  // Phase 3: Merge
  //
  // One agent merges all completed branches into the current branch,
  // resolving any conflicts and running tests to confirm everything works.
  //
  // The {{BRANCHES}} and {{ISSUES}} prompt arguments are lists that the agent
  // uses to know which branches to merge and which issues to close.
  // -------------------------------------------------------------------------
  await runWithQuotaBackoff(
    "merger",
    () =>
      sandcastle.run({
        hooks,
        sandbox: sandboxProvider,
        name: "merger",
        maxIterations: 1,
        agent: resolveAgent("MERGE", MERGE_MODEL),
        promptFile: "./.sandcastle/merge-prompt.md",
        promptArgs: {
          // A markdown list of branch names, one per line.
          BRANCHES: completedBranches.map((b) => `- ${b}`).join("\n"),
          // A markdown list of issue IDs and titles, one per line.
          ISSUES: completedIssues.map((i) => `- ${i.id}: ${i.title}`).join("\n"),
        },
      }),
    { workflow: "parallel", gate: quotaGate },
  );

  console.log("\nBranches merged.");
}

console.log("\nAll done.");
