"""Theme tools: create/update, list by status+parent, read with structured JSON.

These are the registered tool boundary; assertions sit on the JSON shape
the tool returns and the rows it persists, not on private helpers.
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
    p = tmp_path / "themes.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
    migrations.run()
    yield p
    factories.reset()


class TestSetTheme:
    def test_create_minimum(self):
        out = research.set_theme(key="compute", display_name="Compute")
        assert out["key"] == "compute"
        assert out["display_name"] == "Compute"
        assert out["status"] == "exploring"
        assert out["parent_key"] is None
        assert out["created_at"] == out["updated_at"]

    def test_create_with_parent_and_status(self):
        research.set_theme(key="compute", display_name="Compute")
        out = research.set_theme(
            key="model-providers",
            display_name="Model Providers",
            parent_key="compute",
            status="watching",
            description="LLM API providers",
        )
        assert out["parent_key"] == "compute"
        assert out["status"] == "watching"
        assert out["description"] == "LLM API providers"

    def test_update_keeps_created_at_bumps_updated_at(self, monkeypatch):
        research.set_theme(key="energy", display_name="Energy")
        # Move the clock forward and update.
        later = datetime(2026, 6, 23, 8, 0, tzinfo=timezone.utc)
        factories.set_clock(FixedClock(later))
        out = research.set_theme(
            key="energy", display_name="Energy & Power", status="watching"
        )
        assert out["display_name"] == "Energy & Power"
        assert out["status"] == "watching"
        assert out["created_at"] != out["updated_at"]
        assert out["updated_at"] == later.isoformat()

    def test_rejects_unknown_status(self):
        with pytest.raises(ValueError):
            research.set_theme(key="compute", display_name="Compute", status="cooked")

    def test_unknown_parent_raises(self):
        with pytest.raises(ValueError):
            research.set_theme(
                key="orphan", display_name="Orphan", parent_key="nope"
            )


class TestListThemes:
    def _seed(self):
        research.set_theme(key="compute", display_name="Compute")
        research.set_theme(
            key="model-providers",
            display_name="Model Providers",
            parent_key="compute",
        )
        research.set_theme(
            key="energy", display_name="Energy", status="watching"
        )
        research.set_theme(
            key="legacy", display_name="Legacy", status="archived"
        )

    def test_list_all_default(self):
        self._seed()
        out = research.list_themes()
        keys = [t["key"] for t in out["themes"]]
        # archived themes are excluded by default; everything else returned
        assert set(keys) == {"compute", "model-providers", "energy"}

    def test_filter_by_status(self):
        self._seed()
        out = research.list_themes(status="watching")
        assert [t["key"] for t in out["themes"]] == ["energy"]

    def test_filter_by_parent(self):
        self._seed()
        out = research.list_themes(parent_key="compute")
        assert [t["key"] for t in out["themes"]] == ["model-providers"]

    def test_filter_by_status_and_parent(self):
        self._seed()
        research.set_theme(
            key="storage",
            display_name="Storage",
            parent_key="compute",
            status="watching",
        )
        out = research.list_themes(status="watching", parent_key="compute")
        assert [t["key"] for t in out["themes"]] == ["storage"]

    def test_archived_only_when_asked(self):
        self._seed()
        out = research.list_themes(status="archived")
        assert [t["key"] for t in out["themes"]] == ["legacy"]


class TestGetTheme:
    def test_get_returns_theme_payload(self):
        research.set_theme(key="compute", display_name="Compute")
        out = research.get_theme(key="compute")
        assert out["key"] == "compute"
        # children / instruments / sources / notes refs are part of the payload
        assert "children" in out
        assert "instruments" in out
        assert "sources" in out
        assert out["children"] == []
        assert out["instruments"] == []
        assert out["sources"] == []

    def test_unknown_theme_raises(self):
        with pytest.raises(LookupError):
            research.get_theme(key="ghost")

    def test_children_listed(self):
        research.set_theme(key="compute", display_name="Compute")
        research.set_theme(
            key="model-providers",
            display_name="Model Providers",
            parent_key="compute",
        )
        out = research.get_theme(key="compute")
        assert [c["key"] for c in out["children"]] == ["model-providers"]


class TestToolsRegistered:
    def test_set_list_get_in_registry(self):
        from finance_hub.runtime import registry

        registry.load_all()
        names = set(registry.all_tools().keys())
        for n in (
            "finance.set_theme",
            "finance.list_themes",
            "finance.get_theme",
        ):
            assert n in names, f"missing {n} in registry"
