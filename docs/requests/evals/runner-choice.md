# Eval Runner Choice: Claude Code CLI Headless vs Claude Agent SDK

**Status:** Ratified by the user 2026-07-16 — resolves eval spec open question §13.1 (issue #25, map #24).
Ratification added a funding criterion, re-researched in the same-day follow-up (see
[Funding](#funding-claude-max-subscription) below and the
[re-research comment](https://github.com/DhawalAg/finance-hub/issues/25#issuecomment-4993572830)
on #25 for full citations).
**Date:** 2026-07-16
**Question:** Which runner should the eval harness use to drive the SUT — Claude Code CLI
headless mode (`claude -p` with an MCP config) or the Claude Agent SDK?
**Sources:** Official Anthropic docs only — [code.claude.com/docs](https://code.claude.com/docs)
(headless, CLI reference, sessions, Agent SDK overview / python / typescript / skills /
agent-loop / streaming-output / mcp), plus flag verification against the locally installed
CLI (`claude --version` → 2.1.211). Each claim cites its page.

## Recommendation

**Use the Claude Agent SDK (Python) as the primary runner, behind the pluggable runner seam
the spec already mandates (§9.2).** Keep a thin CLI-headless runner as a comparison/debug
variant behind the same seam, since the seam makes it nearly free.

Why, in one paragraph: both options drive the *identical* SUT (the SDK is Claude Code
packaged as a library — same agent loop, tools, skills, CLAUDE.md, MCP), but the SDK gives
the harness typed, structured message objects for every assistant turn, tool_use block, and
tool_result — no parsing of a JSON event stream — plus programmatic per-trial control of
`cwd`, `env`, `mcp_servers`, `setting_sources`, `model`, `max_turns`, and `max_budget_usd`
as plain Python option fields. The harness is Python (graders are "plain Python functions
registered once", §9.4), so the SDK runner is in-process, versioned via `pip`, and
reproducible; the CLI runner requires subprocess management, stream-json parsing, and
inherits whatever `~/.claude` user config exists on the machine unless carefully stripped.

## The two options are the same SUT

The Agent SDK is Claude Code as a library: "the Claude Code harness + built-in tools", with
`query(prompt, options)` driving the full loop — subagents, hooks, permissions, sessions,
skills included ([Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview.md)).
The TypeScript SDK "bundles a native Claude Code binary for your platform"; the docs state
"You don't need the Claude Code CLI installed to use it"
([agent-loop](https://code.claude.com/docs/en/agent-sdk/agent-loop.md)). So this is not a
choice between two agent stacks — it is a choice of *control surface* over the same stack.
That matters for §2 of the spec: either runner exercises the real
`model + CLAUDE.md + skills + tool registry + MCP + SQLite` stack, so neither disqualifies
on SUT fidelity.

## Findings per decision criterion

### 1. Transcript fidelity (spec §6.2, §9.2, §9.5)

| | CLI headless | Agent SDK |
|---|---|---|
| Full trajectory recoverable | ✅ yes, via `--output-format stream-json --verbose` (optionally `--include-partial-messages`) — but tool calls/results arrive as **raw API stream events** you must parse and reassemble | ✅✅ yes, as **typed message objects**: `AssistantMessage` (text + tool_use blocks with parsed `input`), `UserMessage` (tool_results), `ResultMessage` (`total_cost_usd`, `usage`, `num_turns`, `session_id`) |
| Persist as JSONL for re-grading (§9.5) | serialize the parsed stream yourself | serialize each yielded message (`.model_dump()` / dataclass) — trivially JSONL |
| On-disk session transcript | Both write `~/.claude/projects/<cwd-slug>/<session-id>.jsonl`, but the docs explicitly warn the format is internal: "scripts that parse these files directly can break on any release" ([sessions](https://code.claude.com/docs/en/sessions.md)) — **do not build graders on it** with either runner | same |

Sources: [headless](https://code.claude.com/docs/en/headless.md),
[agent-loop](https://code.claude.com/docs/en/agent-sdk/agent-loop.md),
[streaming-output](https://code.claude.com/docs/en/agent-sdk/streaming-output.md).

**Conclusion:** both can feed trajectory graders and support re-grading from stored
transcripts. The SDK removes an entire error-prone layer (stream-event reassembly) and gives
the harness the exact objects the §9.4 grader registry wants. The harness must persist its
*own* transcript JSONL from the message stream — never the `~/.claude` session files.

### 2. Skill loading (ADR-0005 — skills must load exactly as in real interactive use)

- **CLI headless:** `-p` mode discovers `.claude/skills/` and CLAUDE.md from cwd + parents
  exactly like interactive mode, *unless* `--bare` is passed (verified: `--bare` "skips
  hooks, LSP, plugins, CLAUDE.md dirs"). But it also auto-loads **user-level**
  `~/.claude/settings.json` and `~/.claude/skills/` — per-machine state that contaminates
  the SUT definition unless the harness scrubs `$HOME` or uses `--settings`/`--strict-mcp-config`
  hygiene. ([headless](https://code.claude.com/docs/en/headless.md))
- **Agent SDK:** skill discovery is governed by `setting_sources`; with `"project"` included,
  skills load from `<cwd>/.claude/skills/` (and parents to repo root) via the same discovery
  path as the CLI — same SKILL.md, same progressive disclosure
  ([Agent SDK skills](https://code.claude.com/docs/en/agent-sdk/skills.md)). The docs warn:
  if you set `setting_sources` explicitly, include `"project"` (or `"user"`) or skills do
  **not** load — this is the SDK's one loaded footgun, and the harness should pin
  `setting_sources=["project"]` deliberately.
- **Fidelity caveat (either direction):** the `allowed-tools` frontmatter field in SKILL.md
  "is only supported when using Claude Code CLI directly. It does not apply when using
  Skills through the SDK" ([skills](https://code.claude.com/docs/en/agent-sdk/skills.md)).
  None of the repo's future ADR-0005 skills should rely on `allowed-tools` frontmatter for
  correctness; if one ever does, the CLI runner variant covers it.

**Conclusion:** parity on the mechanism that matters (filesystem SKILL.md discovery +
model-driven invocation). The SDK is actually *better* for eval reproducibility because
`setting_sources=["project"]` makes the SUT exactly "this repo's skills + CLAUDE.md",
excluding the developer's `~/.claude` — which the CLI includes by default.

### 3. Per-trial environment injection (`FINANCE_HUB_DB` / `FINANCE_HUB_WORKSPACE`, MCP per trial)

The repo reads both vars from process env (`src/finance_hub/store/connection.py`), and the
SUT's MCP server is the stdio `finance-mcp` command (README §MCP Setup), so per-trial
isolation means: launch the agent with trial-specific env so the spawned MCP server inherits
it (or set `env` on the MCP server config directly).

- **CLI:** `--mcp-config <json>` + `--strict-mcp-config` (ignore all other MCP sources,
  including `.mcp.json`) — verified flags. Env vars per trial via the subprocess env or
  `${VAR}` expansion inside the MCP config. Workable, but it's shell/subprocess plumbing per
  trial. ([headless](https://code.claude.com/docs/en/headless.md),
  [cli-reference](https://code.claude.com/docs/en/cli-reference.md))
- **SDK:** `ClaudeAgentOptions` takes `cwd` (per-trial temp dir), `env`, and `mcp_servers`
  as a dict — e.g. `{"finance-hub": {"command": "finance-mcp", "env": {"FINANCE_HUB_DB": db,
  "FINANCE_HUB_WORKSPACE": ws, "FINANCE_HUB_NOW": frozen}}}` — all constructed in Python per
  trial. `allowed_tools`, `permission_mode`, and `system_prompt` are sibling options.
  ([python](https://code.claude.com/docs/en/agent-sdk/python.md),
  [mcp](https://code.claude.com/docs/en/agent-sdk/mcp.md))
- **Concurrency (§9.3):** the SDK runs trials as concurrent async `query()` calls in one
  process; the CLI needs one subprocess per trial. Both isolate fine; the SDK is less
  process babysitting.

**Conclusion:** both satisfy §9.1; the SDK does it as data, the CLI as flags + subprocess
env. Advantage SDK.

### 4. Model pinning & reproducibility

- Both accept full dated model IDs (e.g. `claude-sonnet-4-5-20250929`): CLI `--model`,
  SDK `model` option. ([cli-reference](https://code.claude.com/docs/en/cli-reference.md),
  [python](https://code.claude.com/docs/en/agent-sdk/python.md))
- Reproducibility of the *harness itself*: the SDK is a pip dependency (`claude-agent-sdk`)
  pinnable in `py3env`; the results row's "SUT description" (§8) can record
  `claude_agent_sdk.__version__` + model id. The CLI is a globally installed, auto-updating
  binary — pinning requires managing the CLI install per run environment.
- Subagent/model caveat: neither doc set documents a haiku-for-subtasks caveat; model choice
  is fully caller-controlled. Record the pinned model per result row as §8 requires.

**Conclusion:** equal on model pinning; SDK wins on pinning the runner itself.

### 5. Maintenance cost as Claude Code evolves

- The CLI runner's contract is the `stream-json` wire format + flag surface of an
  auto-updating binary. The stream format is documented but the harness owns a parser for it.
- The SDK runner's contract is a typed, semver'd library API with its own changelog
  ([claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md)),
  updated deliberately via `pip`. Breakage shows up as a failing import/type at upgrade
  time, not as a silently changed JSON shape mid-eval-run.
- Docs positioning: CLI for "one-off tasks / CI scripts", SDK for "production automation";
  "Many teams use both: CLI for daily development, SDK for production"
  ([overview](https://code.claude.com/docs/en/agent-sdk/overview.md)).

**Conclusion:** SDK, clearly. The pluggable seam (§9.2) caps the cost of ever swapping.

### 6. Cost/latency for pass^3 regression runs

- Both expose `total_cost_usd` and token usage per trial (CLI: `result` message of
  json/stream-json output; SDK: `ResultMessage.total_cost_usd`, `.usage`, `.num_turns`) —
  exactly the §6.4 track metrics (tool calls, turns, tokens, cost per task).
- Both support hard caps: CLI `--max-turns`, `--max-budget-usd`; SDK `max_turns`,
  `max_budget_usd` (result subtype `error_max_budget_usd` makes budget-kill a detectable
  gate/flag condition rather than a hang). ([headless](https://code.claude.com/docs/en/headless.md),
  [agent-loop](https://code.claude.com/docs/en/agent-sdk/agent-loop.md))
- Inference cost is identical (same stack, same model). The marginal difference is harness
  overhead: N subprocesses + JSON parsing vs N async tasks. For k=3 × ~20 tasks this is
  noise; the real §13.6 pass^k economics question is about trial count, not runner choice.

**Conclusion:** tie on inference economics; SDK slightly better on enforcement/observability
plumbing.

## Decision summary

| Criterion | CLI headless | Agent SDK | Winner |
|---|---|---|---|
| Transcript fidelity / re-grading | full, via stream-json parsing | full, typed objects | SDK |
| ADR-0005 skill loading parity | default-on (plus unwanted `~/.claude` user state) | `setting_sources=["project"]`, explicit and hermetic | SDK (with pinned setting_sources) |
| Per-trial env/MCP injection | flags + subprocess env | option fields (`cwd`, `env`, `mcp_servers`) | SDK |
| Model pinning | ✅ `--model` full id | ✅ `model` full id, plus pip-pinned runner | SDK (narrowly) |
| Maintenance cost | parse an evolving binary's output | semver'd library, changelog, typed API | SDK |
| pass^3 cost/latency | `--max-turns`/`--max-budget-usd`, `total_cost_usd` | same, plus typed result subtypes | tie |

## Funding: Claude Max subscription

Decisive constraint added at ratification: eval runs must be funded by the user's Claude Max
subscription — no API credits. The SDK clears it (re-researched 2026-07-16, primary sources
cited in the [#25 comment](https://github.com/DhawalAg/finance-hub/issues/25#issuecomment-4993572830)):

- **Auth**: the SDK inherits the CLI's credential chain, which falls through to "Subscription
  OAuth credentials from `/login` — the default for Pro, Max, Team, and Enterprise users"
  ([authentication docs](https://code.claude.com/docs/en/authentication)). No `ANTHROPIC_API_KEY`
  required.
- **Policy**: ["Use the Claude Agent SDK with your Claude plan"](https://support.claude.com/en/articles/15036540)
  states the Agent SDK, `claude -p`, and third-party apps "draw from your subscription's usage
  limits." A June 2026 "Agent SDK credit" restructuring was **paused before taking effect** —
  re-verify this article before Phase 2 starts.
- **Capacity**: a full pass^3 regression run (~36 short sessions + judge calls) ≈ one moderate
  interactive coding session against the 5-hour window; daily full runs are realistic on Max 5x
  (limits doubled May 2026).

Constraints the harness must encode:

1. **Strip `ANTHROPIC_API_KEY` from trial env** — it silently outranks subscription auth in
   non-interactive mode.
2. **Judge calls go through the same runner** (SDK `query()`), never the raw Messages API,
   or they'd need API credits. `total_cost_usd` becomes a metric, not a bill.
3. **Unattended runs use `claude setup-token`** (`CLAUDE_CODE_OAUTH_TOKEN`, 1-year,
   inference-only, Pro/Max-required); `/login` credentials expire.
4. **Watch `--bare`**: it skips OAuth/keychain and ignores `CLAUDE_CODE_OAUTH_TOKEN`, and docs
   say it will become the headless default in a future release — pin the runner version and
   re-test on upgrades.

If Anthropic ever restricts subscription use here, the policy article governs `claude -p` and
the SDK *as one category* — the fallback in that world is API credits, not a runner switch, so
this does not weaken the SDK recommendation.

## Implementation notes for the harness (Phase 1)

1. Runner seam stays as specified (§9.2): `run_trial(task, fixture_env) -> Transcript`.
   First implementation: `claude_agent_sdk.query()` with
   `ClaudeAgentOptions(cwd=trial_dir, env=..., mcp_servers={"finance-hub": {...}},
   setting_sources=["project"], model=<pinned full id>, permission_mode=...,
   allowed_tools=[...], max_turns=..., max_budget_usd=...)`.
2. Persist the harness's own transcript JSONL by serializing every yielded message; never
   read `~/.claude/projects/**.jsonl` (documented as unstable).
3. Pin `claude-agent-sdk` in `py3env` and record its version + model id in every result row
   (§8 versioning).
4. Do not use `allowed-tools` frontmatter in ADR-0005 skills (SDK ignores it); enforce tool
   restriction via the runner's `allowed_tools` option instead.
5. Optional: a `claude -p --output-format stream-json --strict-mcp-config` runner variant
   behind the same seam for spot-checking SDK/CLI behavioral parity.
