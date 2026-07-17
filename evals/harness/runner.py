"""Runner seam — abstract base and shared types (spec §9.2)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class TranscriptEvent:
    """One message event in a trial transcript (assistant/user/result)."""

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
