"""CLI-headless stub runner — comparison and debug variant (spec §9.2)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil

from .runner import Runner, Transcript, TranscriptEvent, TrialEnv


class CLIRunner(Runner):
    """Thin CLI-headless runner behind the same seam as SDKRunner.

    Drives the SUT via ``claude --print ... --output-format stream-json``.
    Useful for spot-checking SDK/CLI behavioural parity; the SDK runner is
    primary (runner-choice.md §5).
    """

    def __init__(self, cli_path: str | None = None) -> None:
        self.cli_path = cli_path or shutil.which("claude") or "claude"

    async def run(self, prompt: str, env: TrialEnv) -> Transcript:
        mcp_config = json.dumps({"mcpServers": env.mcp_servers})
        cmd = [
            self.cli_path,
            "--print", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--model", env.model,
            "--max-turns", str(env.max_turns),
            "--strict-mcp-config",
            "--mcp-config", mcp_config,
        ]
        if env.max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(env.max_budget_usd)]

        trial_env = {**os.environ, **env.env}
        trial_env.pop("ANTHROPIC_API_KEY", None)

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
            msg_type = obj.get("type", "")
            if msg_type in ("assistant", "user", "result"):
                events.append(TranscriptEvent(type=msg_type, data=obj))

        return Transcript(events=events)
