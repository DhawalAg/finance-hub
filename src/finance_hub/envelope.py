"""Graded-provenance envelope.

Every quantitative value that crosses a layer seam carries one of these.
The grade tells callers how much to trust the value:

- ``decision``  — filing-grounded, safe to drive recommendations.
- ``screening`` — aggregator/provider-derived, fine for sorting/filtering
  but never to be laundered into a decision-grade conclusion.

When several envelopes combine into a derived value, the composite grade
collapses to the *weakest* input grade (``min``), so screening can't
silently turn into decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Union

DECISION = "decision"
SCREENING = "screening"

_GRADE_RANK = {DECISION: 1, SCREENING: 0}
_VALID_GRADES = frozenset(_GRADE_RANK)


@dataclass(frozen=True)
class Envelope:
    value: object
    source: str
    grade: str
    as_of: str

    def __post_init__(self) -> None:
        if self.grade not in _VALID_GRADES:
            raise ValueError(
                f"grade must be one of {sorted(_VALID_GRADES)}, got {self.grade!r}"
            )


def _grade_of(item: Union[str, Envelope]) -> str:
    grade = item.grade if isinstance(item, Envelope) else item
    if grade not in _VALID_GRADES:
        raise ValueError(f"unknown grade: {grade!r}")
    return grade


def composite_grade(items: Iterable[Union[str, Envelope]]) -> str:
    """Return the minimum grade among inputs (decision > screening)."""
    grades = [_grade_of(i) for i in items]
    if not grades:
        raise ValueError("composite_grade requires at least one input")
    return min(grades, key=_GRADE_RANK.__getitem__)
