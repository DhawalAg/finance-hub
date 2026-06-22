"""Candidate-instrument tools: attach instruments to themes (map_instruments)
and walk a candidate through lifecycle states (review_instrument).

The conviction-without-note check is enforced at the SQL CHECK level
(see test_research_schema.py), but the tool layer is the user-facing
contract — assert the error story is friendly and that omitting the
conviction note never sneaks through.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.helpers import FixedClock
from finance_hub import factories
from finance_hub.research import tools as research
from finance_hub.store import connection, migrations


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "instruments.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 22, tzinfo=timezone.utc)))
    migrations.run()
    research.set_theme(key="compute", display_name="Compute")
    yield p
    factories.reset()


class TestMapInstruments:
    def test_attach_single_stock(self):
        out = research.map_instruments(
            theme_key="compute",
            instruments=[
                {
                    "ticker": "NVDA",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "display_name": "NVIDIA",
                    "rationale": "GPU monopoly thesis",
                }
            ],
        )
        assert out["theme_key"] == "compute"
        assert len(out["instruments"]) == 1
        row = out["instruments"][0]
        assert row["ticker"] == "NVDA"
        assert row["status"] == "candidate"
        assert row["note"] == "GPU monopoly thesis"

    def test_attach_etf_with_role(self):
        out = research.map_instruments(
            theme_key="compute",
            instruments=[
                {
                    "ticker": "SMH",
                    "type": "etf",
                    "instrument_role": "theme_etf",
                    "rationale": "Semis basket",
                }
            ],
        )
        assert out["instruments"][0]["ticker"] == "SMH"

    def test_attach_many(self):
        out = research.map_instruments(
            theme_key="compute",
            instruments=[
                {
                    "ticker": "NVDA",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "rationale": "a",
                },
                {
                    "ticker": "AMD",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "rationale": "b",
                },
            ],
        )
        assert {r["ticker"] for r in out["instruments"]} == {"NVDA", "AMD"}

    def test_unknown_theme_raises(self):
        with pytest.raises(LookupError):
            research.map_instruments(
                theme_key="ghost",
                instruments=[
                    {
                        "ticker": "NVDA",
                        "type": "stock",
                        "instrument_role": "single_stock",
                        "rationale": "x",
                    }
                ],
            )

    def test_invalid_role_raises_value_error(self):
        with pytest.raises(ValueError):
            research.map_instruments(
                theme_key="compute",
                instruments=[
                    {
                        "ticker": "NVDA",
                        "type": "stock",
                        "instrument_role": "magic_role",
                        "rationale": "x",
                    }
                ],
            )


class TestReviewInstrument:
    def _attach(self):
        research.map_instruments(
            theme_key="compute",
            instruments=[
                {
                    "ticker": "NVDA",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "rationale": "initial",
                }
            ],
        )

    def test_walk_to_approved(self):
        self._attach()
        out = research.review_instrument(
            theme_key="compute",
            ticker="NVDA",
            status="approved",
            rationale="thesis confirmed",
        )
        assert out["status"] == "approved"
        assert out["note"] == "thesis confirmed"

    def test_set_conviction_requires_note(self):
        self._attach()
        with pytest.raises(ValueError):
            research.review_instrument(
                theme_key="compute",
                ticker="NVDA",
                status="watching",
                rationale="setting conviction",
                conviction=4,
            )

    def test_set_conviction_with_note_succeeds(self):
        self._attach()
        out = research.review_instrument(
            theme_key="compute",
            ticker="NVDA",
            status="watching",
            rationale="watching",
            conviction=4,
            conviction_note="GPU pricing power holds",
        )
        assert out["conviction"] == 4
        assert out["conviction_note"] == "GPU pricing power holds"

    def test_reject_invalid_status(self):
        self._attach()
        with pytest.raises(ValueError):
            research.review_instrument(
                theme_key="compute",
                ticker="NVDA",
                status="liked",
                rationale="x",
            )

    def test_reject_unknown_candidate(self):
        with pytest.raises(LookupError):
            research.review_instrument(
                theme_key="compute",
                ticker="ZZZ",
                status="rejected",
                rationale="no",
            )

    def test_clear_conviction_clears_note(self):
        self._attach()
        research.review_instrument(
            theme_key="compute",
            ticker="NVDA",
            status="watching",
            rationale="watch",
            conviction=3,
            conviction_note="initial conviction",
        )
        out = research.review_instrument(
            theme_key="compute",
            ticker="NVDA",
            status="watching",
            rationale="downgraded",
            conviction=None,
        )
        assert out["conviction"] is None
        assert out["conviction_note"] is None


class TestGetThemeShowsInstruments:
    def test_get_theme_includes_attached_candidates(self):
        research.map_instruments(
            theme_key="compute",
            instruments=[
                {
                    "ticker": "NVDA",
                    "type": "stock",
                    "instrument_role": "single_stock",
                    "rationale": "x",
                }
            ],
        )
        out = research.get_theme(key="compute")
        assert [i["ticker"] for i in out["instruments"]] == ["NVDA"]


class TestToolsRegistered:
    def test_instrument_tools_registered(self):
        from finance_hub.runtime import registry

        registry.load_all()
        names = set(registry.all_tools().keys())
        assert "finance.map_instruments" in names
        assert "finance.review_instrument" in names
