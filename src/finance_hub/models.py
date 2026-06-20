"""Small shared finance value objects.

Domain-specific models should live near their owning package. This module is only for
objects that are used across multiple finance slices.
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
class Provenance:
    source: str
    grade: str
    as_of: str
