"""The research read contract into strategy/planning (PRD stories 12-13).

`candidate_evidence(ticker)` returns one candidate's theme/sleeve mapping,
research status, thesis note location, supporting source IDs, stale-source
flags, promotion-required state, and the evidence gaps blocking DCA vs
one-time eligibility — as stable references + readiness, not rendered prose.

`research_priorities()` is a gap scan over current stored facts, ranked by
deployment-blocking impact, degrading gracefully when downstream tables are
still empty.

Both are read-only: neither mutates strategy or the investable universe.
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
    p = tmp_path / "evidence.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setenv("FINANCE_HUB_WORKSPACE", str(tmp_path / "ws"))
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 22, tzinfo=timezone.utc)))
    migrations.run()
    research.set_theme(key="compute", display_name="Compute")
    research.map_instruments(
        theme_key="compute",
        instruments=[
            {
                "ticker": "NVDA",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "rationale": "GPU leader",
            }
        ],
    )
    yield p
    factories.reset()


def _add_thesis_and_source(review_after=None):
    research.set_research_note(
        scope="instrument", key="NVDA", body="# NVDA thesis\n[source:1]"
    )
    src = research.upsert_source(url="https://example.com/nvda", title="10-K")
    research.link_source(
        source_id=src["id"],
        scope="instrument",
        key="NVDA",
        review_after=review_after,
    )
    return src


class TestCandidateEvidence:
    def test_unknown_candidate_raises(self):
        with pytest.raises(LookupError):
            research.candidate_evidence(ticker="GHOST")

    def test_reference_shape_for_bare_candidate(self):
        out = research.candidate_evidence(ticker="NVDA")
        assert out["ticker"] == "NVDA"
        assert out["instrument"]["instrument_role"] == "single_stock"
        # theme/sleeve mapping is a stable reference list
        assert [t["theme_key"] for t in out["themes"]] == ["compute"]
        assert out["themes"][0]["status"] == "approved"
        assert out["research_status"] == "approved"
        # readiness + gaps buckets are always present
        assert set(out["readiness"]) == {"dca", "one_time"}
        assert set(out["gaps"]) == {"dca", "one_time"}

    def test_bare_candidate_lists_missing_thesis_and_citation_gaps(self):
        out = research.candidate_evidence(ticker="NVDA")
        assert out["thesis_note_path"] is None
        assert out["supporting_source_ids"] == []
        assert "MISSING_THESIS_NOTE" in out["gaps"]["dca"]
        assert "MISSING_CITATIONS" in out["gaps"]["dca"]
        # promotion is always required until the strategy handoff exists
        assert out["promotion_required"] is True
        assert "PROMOTION_REQUIRED" in out["gaps"]["dca"]
        assert out["readiness"]["dca"] is False
        assert out["readiness"]["one_time"] is False

    def test_thesis_and_citation_clear_those_gaps(self):
        src = _add_thesis_and_source()
        out = research.candidate_evidence(ticker="NVDA")
        assert out["thesis_note_path"] == "research/instruments/NVDA.md"
        assert out["supporting_source_ids"] == [src["id"]]
        assert "MISSING_THESIS_NOTE" not in out["gaps"]["dca"]
        assert "MISSING_CITATIONS" not in out["gaps"]["dca"]

    def test_stale_source_flagged(self):
        src = _add_thesis_and_source(review_after="2026-01-01")
        out = research.candidate_evidence(ticker="NVDA")
        assert out["stale_source_ids"] == [src["id"]]
        assert "STALE_SOURCES" in out["gaps"]["dca"]

    def test_one_time_needs_fundamentals_beyond_dca(self):
        _add_thesis_and_source()
        out = research.candidate_evidence(ticker="NVDA")
        # one-time carries every dca gap plus the fundamentals bar
        assert "MISSING_FUNDAMENTALS" in out["gaps"]["one_time"]
        assert "MISSING_FUNDAMENTALS" not in out["gaps"]["dca"]
        # add a fundamentals row -> gap clears
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_fundamentals "
                "(ticker, field, as_of, value, source, grade, fetched_at) "
                "VALUES ('NVDA','pe','2026-06-01','30','eodhd','screening','2026-06-01')"
            )
            conn.commit()
        out2 = research.candidate_evidence(ticker="NVDA")
        assert "MISSING_FUNDAMENTALS" not in out2["gaps"]["one_time"]

    def test_broad_market_etf_exempt_from_thesis_gate(self):
        research.set_theme(key="core", display_name="Core")
        research.map_instruments(
            theme_key="core",
            instruments=[
                {
                    "ticker": "VOO",
                    "type": "etf",
                    "instrument_role": "broad_market_etf",
                    "rationale": "S&P 500",
                }
            ],
        )
        out = research.candidate_evidence(ticker="VOO")
        assert "MISSING_THESIS_NOTE" not in out["gaps"]["dca"]
        assert "MISSING_CITATIONS" not in out["gaps"]["dca"]

    def test_read_only_does_not_mutate(self):
        before = research.get_theme(key="compute")
        research.candidate_evidence(ticker="NVDA")
        after = research.get_theme(key="compute")
        assert before == after


class TestResearchPriorities:
    def test_does_not_error_with_empty_downstream_tables(self):
        out = research.research_priorities()
        assert "priorities" in out
        # global deployment-blocking gaps are surfaced, not raised
        kinds = {p["gap"] for p in out["priorities"]}
        assert "NO_ACTIVE_STRATEGY" in kinds
        assert "NO_PORTFOLIO_SNAPSHOT" in kinds

    def test_candidate_gaps_listed(self):
        out = research.research_priorities()
        cand = [p for p in out["priorities"] if p.get("ticker") == "NVDA"]
        assert cand, "expected NVDA candidate gaps"
        assert any(p["gap"] == "MISSING_THESIS_NOTE" for p in cand)

    def test_priorities_ranked_by_blocking_impact(self):
        out = research.research_priorities()
        sevs = [p["severity"] for p in out["priorities"]]
        assert sevs == sorted(sevs, reverse=True)

    def test_rejected_candidates_excluded(self):
        research.review_instrument(
            theme_key="compute",
            ticker="NVDA",
            status="rejected",
            rationale="thesis broke",
        )
        out = research.research_priorities()
        assert not [p for p in out["priorities"] if p.get("ticker") == "NVDA"]


class TestToolsRegistered:
    def test_read_contract_tools_registered(self):
        from finance_hub.runtime import registry

        registry.load_all()
        names = set(registry.all_tools().keys())
        assert "finance.candidate_evidence" in names
        assert "finance.research_priorities" in names
