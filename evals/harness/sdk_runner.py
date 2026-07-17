"""Agent SDK runner — primary runner implementation (spec §9.2, runner-choice.md)."""

from __future__ import annotations

import dataclasses
from typing import Any

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from .runner import Runner, Transcript, TranscriptEvent, TrialEnv


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
        else:
            content.append({"type": type(block).__name__.lower()})
    return {
        "model": msg.model,
        "content": content,
        "parent_tool_use_id": msg.parent_tool_use_id,
        "usage": msg.usage,
        "session_id": msg.session_id,
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
                "is_error": block.is_error,
            })
        else:
            content.append({"type": type(block).__name__.lower()})
    return {"content": content}


def _result_to_dict(msg: ResultMessage) -> dict[str, Any]:
    return dataclasses.asdict(msg)


class SDKRunner(Runner):
    """Drives the SUT in-process via ``claude_agent_sdk.query()``.

    Per-trial control: ``cwd``, ``env``, ``mcp_servers``, ``model``, ``max_turns``,
    ``max_budget_usd``.  ``setting_sources`` is pinned to ``["project"]`` via
    ``TrialEnv`` so the trial never loads the developer's ``~/.claude`` settings.

    Auth: inherits the CLI's credential chain (OAuth subscription by default);
    ``ANTHROPIC_API_KEY`` must be absent from ``env`` — ``TrialEnv`` strips it.
    """

    async def run(self, prompt: str, env: TrialEnv) -> Transcript:
        options = ClaudeAgentOptions(
            cwd=env.cwd,
            env=env.env,
            mcp_servers=env.mcp_servers,
            setting_sources=env.setting_sources,
            model=env.model,
            max_turns=env.max_turns,
            max_budget_usd=env.max_budget_usd,
            permission_mode="bypassPermissions",
        )
        events: list[TranscriptEvent] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                events.append(TranscriptEvent(type="assistant", data=_assistant_to_dict(msg)))
            elif isinstance(msg, UserMessage):
                events.append(TranscriptEvent(type="user", data=_user_to_dict(msg)))
            elif isinstance(msg, ResultMessage):
                events.append(TranscriptEvent(type="result", data=_result_to_dict(msg)))
        return Transcript(events=events)
