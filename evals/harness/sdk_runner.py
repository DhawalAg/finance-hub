"""Agent SDK runner — primary runner implementation (spec §9.2, runner-choice.md)."""

from __future__ import annotations

import dataclasses
from typing import Any

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from .runner import (
    TRIAL_BUILTIN_TOOLS,
    TRIAL_PERMISSION_MODE,
    Runner,
    Transcript,
    TranscriptEvent,
    TrialEnv,
    bridge_project_context,
    resolve_mcp_servers,
    trial_allowed_tools,
    trial_process_env,
)

# Streaming progress ticks — dozens per trial, no information graders or humans use.
_DROPPED_SYSTEM_SUBTYPES = frozenset({"thinking_tokens"})


def _assistant_to_dict(msg: AssistantMessage) -> dict[str, Any]:
    content = []
    for block in msg.content:
        if isinstance(block, TextBlock):
            content.append({"type": "text", "text": block.text})
        elif isinstance(block, ToolUseBlock):
            content.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
        elif isinstance(block, ThinkingBlock):
            content.append({"type": "thinking"})
        else:
            content.append({"type": type(block).__name__.lower()})
    return {
        "model": msg.model,
        "content": content,
        "parent_tool_use_id": msg.parent_tool_use_id,
        "usage": msg.usage,
        "session_id": msg.session_id,
        "message_id": msg.message_id,
        "stop_reason": msg.stop_reason,
        "error": msg.error,
    }


def _user_to_dict(msg: UserMessage) -> dict[str, Any]:
    if isinstance(msg.content, str):
        return {"content": msg.content}
    content = []
    for block in msg.content:
        if isinstance(block, ToolResultBlock):
            content.append({
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                # The SDK reports None (not False) for successful MCP results.
                "is_error": bool(block.is_error),
            })
        elif isinstance(block, TextBlock):
            content.append({"type": "text", "text": block.text})
        else:
            content.append({"type": type(block).__name__.lower()})
    return {"content": content}


def _system_to_dict(msg: SystemMessage) -> dict[str, Any]:
    """System message payload, verbatim.  The ``init`` message is the only record of
    what the trial actually ran with (tools, mcp_servers, cwd, apiKeySource, model,
    permissionMode) — the isolation evidence for every transcript."""
    return {**msg.data, "subtype": msg.subtype}


def _result_to_dict(msg: ResultMessage) -> dict[str, Any]:
    return dataclasses.asdict(msg)


def build_options(env: TrialEnv) -> ClaudeAgentOptions:
    """ClaudeAgentOptions for one trial, with the runner.py lockdown applied."""
    return ClaudeAgentOptions(
        cwd=env.cwd,
        env=trial_process_env(env.env),
        mcp_servers=resolve_mcp_servers(env.mcp_servers),
        strict_mcp_config=True,
        tools=list(TRIAL_BUILTIN_TOOLS),
        allowed_tools=trial_allowed_tools(env.mcp_servers),
        permission_mode=TRIAL_PERMISSION_MODE,
        setting_sources=env.setting_sources,
        model=env.model,
        max_turns=env.max_turns,
        max_budget_usd=env.max_budget_usd,
    )


class SDKRunner(Runner):
    """Drives the SUT in-process via ``claude_agent_sdk.query()``.

    Per-trial control: ``cwd``, ``env``, ``mcp_servers``, ``model``, ``max_turns``,
    ``max_budget_usd``.  ``setting_sources`` is pinned to ``["project"]`` via
    ``TrialEnv`` so the trial never loads the developer's ``~/.claude`` settings;
    tools, MCP servers and permissions are locked down per ``runner.py`` so the
    agent reaches only the finance-hub MCP tools (no built-ins, no claude.ai
    connectors).

    Auth: inherits the CLI's credential chain (OAuth subscription by default);
    ``ANTHROPIC_API_KEY`` must be absent from ``env`` — ``TrialEnv`` strips it.
    """

    async def run(self, prompt: str, env: TrialEnv) -> Transcript:
        bridge_project_context(env.cwd)
        options = build_options(env)
        events: list[TranscriptEvent] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                events.append(TranscriptEvent(type="assistant", data=_assistant_to_dict(msg)))
            elif isinstance(msg, UserMessage):
                events.append(TranscriptEvent(type="user", data=_user_to_dict(msg)))
            elif isinstance(msg, ResultMessage):
                events.append(TranscriptEvent(type="result", data=_result_to_dict(msg)))
            elif isinstance(msg, SystemMessage):
                if msg.subtype not in _DROPPED_SYSTEM_SUBTYPES:
                    events.append(TranscriptEvent(type="system", data=_system_to_dict(msg)))
            elif isinstance(msg, RateLimitEvent):
                events.append(TranscriptEvent(type="system", data={
                    "subtype": "rate_limit_event",
                    "rate_limit_info": dataclasses.asdict(msg.rate_limit_info),
                    "session_id": msg.session_id,
                }))
        return Transcript(events=events)
