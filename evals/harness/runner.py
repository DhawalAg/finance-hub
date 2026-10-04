"""Runner seam — abstract base and shared types (spec §9.2)."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Trial lockdown — shared by SDKRunner and CLIRunner
# ---------------------------------------------------------------------------
#
# A trial agent must only be able to reach the SUT: the finance-hub MCP tools.
# Without this, Claude Code hands it the full built-in toolset (Bash, Write,
# WebFetch, CronCreate, RemoteTrigger, Task, ...) AND the developer's claude.ai
# account connectors (Gmail, Drive, Calendar, Notion, ...) — setting_sources
# does not exclude either.  Layers, each sufficient on its own for its target:
#
#   1. Built-ins: ``--tools`` is an allow-list of the built-in set.  Only
#      ToolSearch survives — Claude Code defers MCP tool schemas behind it, so
#      the agent needs it to load the finance tools (read-only; observed in the
#      2026-10-04 ground-truth trials).  Memos are written by the MCP tools
#      (finance.approve_deployment_plan), never by the agent, so no Read/Write.
#   2. MCP: ``--strict-mcp-config`` loads only the servers the runner passes
#      (no .mcp.json / user / plugin servers).  It does NOT stop the claude.ai
#      connector fetch (CLI 2.1.215 still fetches them) — the load-bearing
#      switch for connectors is ``ENABLE_CLAUDEAI_MCP_SERVERS=false``.
#   3. Permissions: ``dontAsk`` denies any tool not pre-approved, and only
#      ToolSearch + ``mcp__<server>`` for the trial's own servers are approved —
#      a tool that leaks past 1/2 (e.g. a future built-in) is denied, not run.
#      (Replaces bypassPermissions, which would have run anything reachable.)
#
# Each layer was verified against the bundled CLI with no LLM call: a local fake
# Messages API scripted tool_use turns — ToolSearch and mcp__finance-hub__health
# ran; Bash/Write → "not enabled"; with Bash/Write force-enabled → "denied ...
# don't ask mode"; mcp__claude_ai_Gmail__send_message → "No such tool".
#
# Shipping a runtime skill (ADR-0006) will need "Skill" added to both
# TRIAL_BUILTIN_TOOLS and the allow-list.
TRIAL_BUILTIN_TOOLS: tuple[str, ...] = ("ToolSearch",)
TRIAL_PERMISSION_MODE = "dontAsk"
TRIAL_ENV_LOCKDOWN: dict[str, str] = {
    "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    # Auto-memory reads/writes per-user state under ~/.claude/projects — not SUT.
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
}

# Where Claude Code discovers project context (CLAUDE.md) under setting_sources
# ["project"], and where materialisation puts the runtime CLAUDE.md.
_PROJECT_CONTEXT = "CLAUDE.md"
_RUNTIME_CONTEXT = Path("runtime") / "CLAUDE.md"


def trial_allowed_tools(mcp_servers: dict[str, Any]) -> list[str]:
    """Pre-approved tools for a trial: the lockdown built-ins + every trial MCP server."""
    return [*TRIAL_BUILTIN_TOOLS, *(f"mcp__{name}" for name in mcp_servers)]


def trial_process_env(env: dict[str, str]) -> dict[str, str]:
    """Trial env with the lockdown vars forced on and ANTHROPIC_API_KEY blanked.

    Blanked, not popped: the SDK launches the CLI with ``{**os.environ, **options.env}``,
    so a key in the harness's own environment would survive a pop and silently
    outrank the subscription OAuth (verified: init ``apiKeySource`` flips to
    ``ANTHROPIC_API_KEY``).  The CLI treats an empty key as unset (``none``).
    """
    return {**env, **TRIAL_ENV_LOCKDOWN, "ANTHROPIC_API_KEY": ""}


def resolve_mcp_servers(
    mcp_servers: dict[str, Any], root: Path = _REPO_ROOT
) -> dict[str, Any]:
    """Resolve repo-relative stdio commands (``py3env/bin/finance-mcp``) against *root*.

    runtime/mcp.json names the server by a repo-relative path so it stays portable
    (interactive sessions run from the repo root, where it resolves as-is).  A trial
    runs with cwd=<trial dir>, so the runner anchors it to the repo — otherwise the
    MCP server would not start, or a bare name would resolve via PATH to a non-py3env
    interpreter.  Bare names and absolute paths pass through unchanged.
    """
    resolved: dict[str, Any] = {}
    for name, cfg in mcp_servers.items():
        cfg = dict(cfg)
        cmd = cfg.get("command")
        if isinstance(cmd, str) and "/" in cmd and not os.path.isabs(cmd):
            cfg["command"] = str(root / cmd)
        resolved[name] = cfg
    return resolved


def bridge_project_context(cwd: Path) -> None:
    """Expose the materialised runtime CLAUDE.md where Claude Code loads it.

    Materialisation copies runtime/CLAUDE.md to <trial>/runtime/CLAUDE.md, but
    Claude Code only reads project context from <cwd>/CLAUDE.md (and parents), so
    the agent would never see its instructions while the prompt hash covers them.
    Mirrors ADR-0007's interactive bridge: a root CLAUDE.md symlink into runtime/.
    No-op if the trial has no runtime CLAUDE.md or already has a root CLAUDE.md.
    """
    src = cwd / _RUNTIME_CONTEXT
    dst = cwd / _PROJECT_CONTEXT
    if src.is_file() and not dst.exists() and not dst.is_symlink():
        dst.symlink_to(_RUNTIME_CONTEXT)


@dataclass
class TranscriptEvent:
    """One message event in a trial transcript (assistant/user/result/system)."""

    type: Literal["assistant", "user", "result", "system"]
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TranscriptEvent:
        return cls(type=d["type"], data=d["data"])


@dataclass
class Transcript:
    """Complete record of one trial — every turn, tool call, and result.

    Persisted as JSONL (one event per line) so graders can re-run without
    re-running trials (spec §9 req 5).  Never read ~/.claude session files —
    that format is documented as internal/unstable.
    """

    events: list[TranscriptEvent] = field(default_factory=list)

    def write_jsonl(self, path: Path) -> None:
        if not self.events:
            path.write_text("")
            return
        path.write_text("\n".join(json.dumps(e.to_dict()) for e in self.events) + "\n")

    @classmethod
    def read_jsonl(cls, path: Path) -> Transcript:
        events = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                events.append(TranscriptEvent.from_dict(json.loads(line)))
        return cls(events=events)

    @property
    def result(self) -> dict[str, Any] | None:
        for e in reversed(self.events):
            if e.type == "result":
                return e.data
        return None

    @property
    def num_turns(self) -> int:
        r = self.result
        return r.get("num_turns", 0) if r else 0

    @property
    def total_cost_usd(self) -> float | None:
        r = self.result
        return r.get("total_cost_usd") if r else None


@dataclass
class TrialEnv:
    """Per-trial environment passed to the runner.

    `setting_sources` defaults to ``["project"]`` so trials load only the
    trial dir's runtime surface — never the developer's ``~/.claude`` config
    (spec §9 req 2, runner-choice.md §2).

    `ANTHROPIC_API_KEY` is stripped on construction so the Max-subscription
    OAuth path is always used; an API key silently outranks it in headless mode
    (runner-choice.md Funding §1).
    """

    cwd: Path
    env: dict[str, str]
    mcp_servers: dict[str, Any]
    model: str
    max_turns: int = 20
    max_budget_usd: float | None = None
    setting_sources: list[Literal["user", "project", "local"]] = field(
        default_factory=lambda: ["project"]
    )

    def __post_init__(self) -> None:
        self.env.pop("ANTHROPIC_API_KEY", None)


class Runner(ABC):
    """Seam: run one agent trial and return the full typed transcript.

    Implementations: SDKRunner (primary), CLIRunner (comparison/debug stub).
    """

    @abstractmethod
    async def run(self, prompt: str, env: TrialEnv) -> Transcript:
        """Drive the SUT headless for one trial and return the transcript."""
        ...
