"""CLI-headless stub runner — comparison and debug variant (spec §9.2)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any

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

# Keys SDKRunner records alongside each message's content (sdk_runner._assistant_to_dict).
_ASSISTANT_META = ("model", "usage", "stop_reason")


def _block(block: dict[str, Any]) -> dict[str, Any]:
    """Normalise one API content block to the shape SDKRunner records."""
    btype = block.get("type")
    if btype == "text":
        return {"type": "text", "text": block.get("text", "")}
    if btype == "tool_use":
        return {"type": "tool_use", "id": block.get("id"), "name": block.get("name"),
                "input": block.get("input", {})}
    if btype == "tool_result":
        return {"type": "tool_result", "tool_use_id": block.get("tool_use_id"),
                "content": block.get("content"), "is_error": bool(block.get("is_error"))}
    return {"type": btype}


def _message_to_data(obj: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a stream-json assistant/user line into SDKRunner's event-data shape.

    The CLI nests the API message under ``"message"``; graders read
    ``data["content"]``, so the content list must sit at the top level.
    """
    msg = obj.get("message") or {}
    content = msg.get("content", [])
    data: dict[str, Any] = {
        "content": content if isinstance(content, str) else [_block(b) for b in content],
    }
    if obj.get("type") == "assistant":
        data.update({k: msg.get(k) for k in _ASSISTANT_META})
        data["message_id"] = msg.get("id")
        data["error"] = obj.get("error")
        data["parent_tool_use_id"] = obj.get("parent_tool_use_id")
        data["session_id"] = obj.get("session_id")
    return data


def _event_from_line(obj: dict[str, Any]) -> TranscriptEvent | None:
    msg_type = obj.get("type", "")
    if msg_type in ("assistant", "user"):
        return TranscriptEvent(type=msg_type, data=_message_to_data(obj))
    if msg_type == "result":
        return TranscriptEvent(type="result", data={k: v for k, v in obj.items() if k != "type"})
    if msg_type == "system":
        if obj.get("subtype") == "thinking_tokens":
            return None
        return TranscriptEvent(type="system", data={k: v for k, v in obj.items() if k != "type"})
    if msg_type == "rate_limit_event":
        return TranscriptEvent(type="system", data={
            **{k: v for k, v in obj.items() if k != "type"}, "subtype": "rate_limit_event"})
    return None


class CLIRunner(Runner):
    """Thin CLI-headless runner behind the same seam as SDKRunner.

    Drives the SUT via ``claude --print ... --output-format stream-json``.
    Useful for spot-checking SDK/CLI behavioural parity; the SDK runner is
    primary (runner-choice.md §5).  Applies the same isolation as SDKRunner:
    ``--setting-sources`` from ``TrialEnv``, and the runner.py tool / MCP /
    permission lockdown; events carry the same data shape.
    """

    def __init__(self, cli_path: str | None = None) -> None:
        self.cli_path = cli_path or shutil.which("claude") or "claude"

    def build_command(self, prompt: str, env: TrialEnv) -> list[str]:
        mcp_config = json.dumps({"mcpServers": resolve_mcp_servers(env.mcp_servers)})
        cmd = [
            self.cli_path,
            "--print", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--model", env.model,
            "--max-turns", str(env.max_turns),
            "--setting-sources", ",".join(env.setting_sources),
            "--strict-mcp-config",
            "--mcp-config", mcp_config,
            "--tools", ",".join(TRIAL_BUILTIN_TOOLS),
            "--allowedTools", ",".join(trial_allowed_tools(env.mcp_servers)),
            "--permission-mode", TRIAL_PERMISSION_MODE,
        ]
        if env.max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(env.max_budget_usd)]
        return cmd

    async def run(self, prompt: str, env: TrialEnv) -> Transcript:
        bridge_project_context(env.cwd)
        cmd = self.build_command(prompt, env)
        trial_env = trial_process_env({**os.environ, **env.env})

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(env.cwd),
            env=trial_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        events: list[TranscriptEvent] = []
        for line in stdout.decode().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = _event_from_line(obj)
            if event is not None:
                events.append(event)

        return Transcript(events=events)
