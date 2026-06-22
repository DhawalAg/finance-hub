"""Source tools: upsert idempotently by URL, link to a theme/instrument with
a review_after date, mark links superseded without deleting prior rows, and
surface links due for review.

These are the registered tool boundary; assertions sit on the JSON shape the
tool returns and the rows it persists.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from finance_hub import factories
from finance_hub.research import tools as research
from finance_hub.store import connection, migrations


class FixedClock:
    def __init__(self, instant):
        self._instant = instant

    def now(self):
        return self._instant


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "sources.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
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
                "rationale": "x",
            }
        ],
    )
    yield p
    factories.reset()


class TestUpsertSource:
    def test_create_returns_stable_id(self):
        out = research.upsert_source(
            url="https://example.com/a",
            title="A",
            publisher="Acme",
            source_type="article",
            published_on="2026-01-01",
        )
        assert isinstance(out["id"], int)
        assert out["url"] == "https://example.com/a"
        assert out["title"] == "A"

    def test_upsert_by_url_is_idempotent(self):
        first = research.upsert_source(url="https://example.com/a", title="A")
        second = research.upsert_source(
            url="https://example.com/a", title="A (updated)", publisher="Acme"
        )
        # same row reused, no duplicate id
        assert second["id"] == first["id"]
        assert second["title"] == "A (updated)"
        assert second["publisher"] == "Acme"
        out = research.list_sources()
        assert len(out["sources"]) == 1


class TestLinkSource:
    def test_link_to_theme_with_review_after(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        link = research.link_source(
            source_id=src["id"],
            scope="theme",
            key="compute",
            note="backs the GPU thesis",
            review_after="2026-09-01",
        )
        assert link["scope"] == "theme"
        assert link["key"] == "compute"
        assert link["status"] == "active"
        assert link["review_after"] == "2026-09-01"

    def test_link_reusable_across_targets(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        research.link_source(source_id=src["id"], scope="theme", key="compute")
        research.link_source(source_id=src["id"], scope="instrument", key="NVDA")
        out = research.list_sources(scope="instrument", key="NVDA")
        assert [s["id"] for s in out["sources"]] == [src["id"]]

    def test_unknown_source_raises(self):
        with pytest.raises(LookupError):
            research.link_source(source_id=9999, scope="theme", key="compute")

    def test_unknown_target_raises(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        with pytest.raises(LookupError):
            research.link_source(source_id=src["id"], scope="theme", key="ghost")

    def test_invalid_scope_raises(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        with pytest.raises(ValueError):
            research.link_source(source_id=src["id"], scope="moon", key="compute")


class TestSupersede:
    def test_supersede_retains_old_row(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        research.link_source(source_id=src["id"], scope="theme", key="compute")
        link = research.supersede_source_link(
            source_id=src["id"], scope="theme", key="compute"
        )
        assert link["status"] == "superseded"
        # the row is still present (not deleted), now marked superseded
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT status FROM fin_research_source_links "
                "WHERE source_id = ? AND scope = 'theme' AND key = 'compute'",
                (src["id"],),
            ).fetchall()
        assert [r["status"] for r in rows] == ["superseded"]


class TestDueForReview:
    def test_due_links_surfaced(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        research.link_source(
            source_id=src["id"],
            scope="theme",
            key="compute",
            review_after="2026-01-01",
        )
        out = research.sources_due_for_review(as_of="2026-06-22")
        assert len(out["due"]) == 1
        assert out["due"][0]["key"] == "compute"

    def test_not_yet_due_excluded(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        research.link_source(
            source_id=src["id"],
            scope="theme",
            key="compute",
            review_after="2026-12-01",
        )
        out = research.sources_due_for_review(as_of="2026-06-22")
        assert out["due"] == []

    def test_superseded_links_not_due(self):
        src = research.upsert_source(url="https://example.com/a", title="A")
        research.link_source(
            source_id=src["id"],
            scope="theme",
            key="compute",
            review_after="2026-01-01",
        )
        research.supersede_source_link(
            source_id=src["id"], scope="theme", key="compute"
        )
        out = research.sources_due_for_review(as_of="2026-06-22")
        assert out["due"] == []


class TestToolsRegistered:
    def test_source_tools_registered(self):
        from finance_hub.runtime import registry

        registry.load_all()
        names = set(registry.all_tools().keys())
        for n in (
            "finance.upsert_source",
            "finance.link_source",
            "finance.supersede_source_link",
            "finance.list_sources",
            "finance.sources_due_for_review",
        ):
            assert n in names, f"missing {n}"
