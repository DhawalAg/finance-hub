"""Graded-provenance envelope: every quantitative value crossing a seam
carries (value, source, grade, as_of). Composite grade = min(inputs).
"""
from __future__ import annotations

import pytest

from finance_hub.envelope import DECISION, SCREENING, Envelope, composite_grade


class TestEnvelopeShape:
    def test_construct(self):
        env = Envelope(value=10, source="yfinance", grade=SCREENING, as_of="2026-06-01")
        assert env.value == 10
        assert env.source == "yfinance"
        assert env.grade == SCREENING
        assert env.as_of == "2026-06-01"

    def test_rejects_unknown_grade(self):
        with pytest.raises(ValueError):
            Envelope(value=1, source="x", grade="guess", as_of="2026-01-01")


class TestCompositeGrade:
    def test_all_decision_is_decision(self):
        assert composite_grade([DECISION, DECISION]) == DECISION

    def test_any_screening_downgrades(self):
        assert composite_grade([DECISION, SCREENING]) == SCREENING
        assert composite_grade([SCREENING, DECISION]) == SCREENING

    def test_all_screening_is_screening(self):
        assert composite_grade([SCREENING, SCREENING]) == SCREENING

    def test_single(self):
        assert composite_grade([DECISION]) == DECISION
        assert composite_grade([SCREENING]) == SCREENING

    def test_accepts_envelopes(self):
        env1 = Envelope(value=1, source="edgar", grade=DECISION, as_of="2026-01-01")
        env2 = Envelope(value=2, source="fmp", grade=SCREENING, as_of="2026-01-01")
        assert composite_grade([env1, env2]) == SCREENING

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            composite_grade([])

    def test_rejects_unknown_grade_input(self):
        with pytest.raises(ValueError):
            composite_grade([DECISION, "guess"])
