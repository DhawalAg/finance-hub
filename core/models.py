"""Shared data model. The cross-hub spine: search/research/outreach all speak these.

Mirrors the entities in outreach-hub/docs/00-system-design.md §3. Every factual claim in a
dossier should carry a Source so drafts never rest on unattributed assertions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    url: str
    title: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Company:
    name: str
    domain: str = ""
    dossier: str = ""           # research summary (problems, signals, recency)
    sources: list[Source] = field(default_factory=list)
    id: int | None = None


@dataclass
class Person:
    name: str
    role: str = ""
    company: str = ""
    network_degree: int | None = None   # 1 / 2 / 3 / None (net-new)
    handles: dict[str, str] = field(default_factory=dict)  # email, linkedin, blog, github...
    dossier: str = ""
    sources: list[Source] = field(default_factory=list)
    id: int | None = None


@dataclass
class Outreach:
    person_id: int
    channel: str                # email | linkedin | blog-comment | ...
    angle: str = ""             # which side-project + why
    draft: str = ""
    status: str = "researched"  # researched -> drafted -> approved -> sent -> replied
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: int | None = None
