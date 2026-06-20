"""Thin Claude wrapper. One place to set the default model and read the API key."""
from __future__ import annotations

import os

# Lean-budget default; bump to a larger model per-call when a task needs it.
DEFAULT_MODEL = "claude-sonnet-4-6"


def complete(prompt: str, *, system: str = "", model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> str:
    """Single-shot completion. Raises if ANTHROPIC_API_KEY is unset."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "You are a precise research and drafting assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")
