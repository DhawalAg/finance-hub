"""Outreach hub — research-fed, multi-channel first-contact drafting (see outreach-hub/docs).

One real tool is wired below to prove the registry -> CLI -> MCP path end to end.
The research (M2/M3), synthesis (M4), and delivery (M6) capabilities land here as more tools.
"""
from __future__ import annotations

from core import llm
from core.registry import tool


@tool(
    name="outreach.draft_intro",
    description="Draft a short, grounded first-contact message from a person/company dossier and an angle.",
)
def draft_intro(person: str, dossier: str, angle: str, channel: str = "email") -> str:
    prompt = (
        f"Write a {channel} first-contact message to {person}.\n\n"
        f"What we know (use only these facts, do not invent flattery):\n{dossier}\n\n"
        f"The reason to reach out (the angle):\n{angle}\n\n"
        "Constraints: specific, non-generic, no buzzwords, no fake familiarity. "
        "Lead with the concrete reason this is relevant to them. Keep it tight."
    )
    return llm.complete(prompt)
