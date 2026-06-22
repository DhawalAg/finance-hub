"""Research note tools: SQLite stores the *path*, markdown body lives on
disk under ``workspace/research/...``.

The workspace root is configurable so tests can point at tmp_path
without polluting the repo's gitignored workspace.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
def env(tmp_path, monkeypatch):
    p = tmp_path / "notes.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setenv("FINANCE_HUB_WORKSPACE", str(tmp_path / "workspace"))
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 22, tzinfo=timezone.utc)))
    migrations.run()
    yield tmp_path
    factories.reset()


class TestThemeNote:
    def test_writes_under_workspace_research_themes(self, env):
        research.set_theme(key="compute", display_name="Compute")
        out = research.set_research_note(
            scope="theme", key="compute", body="# compute thesis\n\nGPU TAM."
        )
        path = Path(out["path"])
        assert path.is_absolute()
        # path is stored relative under workspace/research/themes
        assert "research/themes/compute.md" in str(path).replace("\\", "/")
        assert path.read_text() == "# compute thesis\n\nGPU TAM."

    def test_stores_relative_note_path_on_theme(self, env):
        research.set_theme(key="compute", display_name="Compute")
        research.set_research_note(
            scope="theme", key="compute", body="body"
        )
        theme = research.get_theme(key="compute")
        assert theme["note_path"] == "research/themes/compute.md"

    def test_rewrite_overwrites_existing_body(self, env):
        research.set_theme(key="compute", display_name="Compute")
        research.set_research_note(scope="theme", key="compute", body="v1")
        research.set_research_note(scope="theme", key="compute", body="v2")
        out = research.get_research_note(scope="theme", key="compute")
        assert out["body"] == "v2"

    def test_unknown_theme_raises(self, env):
        with pytest.raises(LookupError):
            research.set_research_note(
                scope="theme", key="ghost", body="x"
            )


class TestInstrumentNote:
    def test_writes_under_research_instruments(self, env):
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
        out = research.set_research_note(
            scope="instrument", key="NVDA", body="# NVDA thesis"
        )
        path = Path(out["path"])
        assert "research/instruments/NVDA.md" in str(path).replace("\\", "/")
        assert path.read_text() == "# NVDA thesis"

    def test_unknown_instrument_raises(self, env):
        with pytest.raises(LookupError):
            research.set_research_note(
                scope="instrument", key="ZZZ", body="x"
            )


class TestGetResearchNote:
    def test_returns_body_and_path(self, env):
        research.set_theme(key="compute", display_name="Compute")
        research.set_research_note(scope="theme", key="compute", body="hi")
        out = research.get_research_note(scope="theme", key="compute")
        assert out["body"] == "hi"
        assert out["path"].endswith("research/themes/compute.md")

    def test_missing_note_returns_none_body(self, env):
        research.set_theme(key="compute", display_name="Compute")
        out = research.get_research_note(scope="theme", key="compute")
        assert out["body"] is None
        assert out["path"] is None


class TestScopeCheck:
    def test_invalid_scope_raises(self, env):
        with pytest.raises(ValueError):
            research.set_research_note(scope="moon", key="x", body="b")


class TestToolsRegistered:
    def test_note_tools_registered(self, env):
        from finance_hub.runtime import registry

        registry.load_all()
        names = set(registry.all_tools().keys())
        assert "finance.set_research_note" in names
        assert "finance.get_research_note" in names
