"""Tests for capability eval tasks C1/C2/C3/C7 — fixture builders and bootstrap wiring.

Issue #49 — Phase 4 capability frontier: one-time-buy + market-data tasks.
Spec §7 (capability suite), §10 seed table, §11 Phase 4, ADR 0006.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from finance_hub import bootstrap as bootstrap_module
from finance_hub import factories

_REPO_ROOT = Path(__file__).parent.parent
_EODHD_AAPL = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_aapl.json"
_EODHD_SPY = _REPO_ROOT / "tests" / "fixtures" / "fundamentals" / "eodhd_spy.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}


def _count(db_path: Path, table: str, where: str = "") -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchone()[0]


def _scalar(db_path: Path, sql: str) -> object:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql).fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# bootstrap: FINANCE_HUB_FUNDAMENTALS_FIXTURE
# ---------------------------------------------------------------------------

class TestFundamentalsFixtureBootstrap:
    """FINANCE_HUB_FUNDAMENTALS_FIXTURE wires a recorded EODHDAdapter (spec §5.2)."""

    _ENV_KEY = "FINANCE_HUB_FUNDAMENTALS_FIXTURE"

    def setup_method(self):
        factories.reset()
        os.environ.pop(self._ENV_KEY, None)
        os.environ.pop("EODHD_API_KEY", None)
        os.environ.pop("ALPHA_VANTAGE_API_KEY", None)

    def teardown_method(self):
        factories.reset()
        os.environ.pop(self._ENV_KEY, None)
        os.environ.pop("EODHD_API_KEY", None)
        os.environ.pop("ALPHA_VANTAGE_API_KEY", None)

    def test_fixture_env_var_wires_eodhd_adapter(self, tmp_path):
        """When FINANCE_HUB_FUNDAMENTALS_FIXTURE is set, bootstrap uses EODHDAdapter."""
        from finance_hub.market_data.fundamentals import EODHDAdapter

        responses_path = tmp_path / "responses.json"
        aapl_data = json.loads(_EODHD_AAPL.read_text())
        responses_path.write_text(json.dumps({"AAPL": aapl_data}))

        os.environ[self._ENV_KEY] = str(responses_path)
        bootstrap_module.bootstrap()

        provider = factories.get_fundamentals_provider()
        assert isinstance(provider, EODHDAdapter)

    def test_fixture_adapter_returns_normalized_records(self, tmp_path):
        """EODHDAdapter configured from fixture serves AAPL records."""
        responses_path = tmp_path / "responses.json"
        aapl_data = json.loads(_EODHD_AAPL.read_text())
        responses_path.write_text(json.dumps({"AAPL": aapl_data}))

        os.environ[self._ENV_KEY] = str(responses_path)
        bootstrap_module.bootstrap()

        provider = factories.get_fundamentals_provider()
        records = provider.fetch_fundamentals("AAPL")
        assert len(records) == 8
        fields = {r.field for r in records}
        assert "revenue_growth" in fields
        assert "profitability" in fields

    def test_fixture_takes_priority_over_api_keys(self, tmp_path):
        """FINANCE_HUB_FUNDAMENTALS_FIXTURE wins over EODHD_API_KEY."""
        from finance_hub.market_data.fundamentals import EODHDAdapter

        responses_path = tmp_path / "responses.json"
        responses_path.write_text(json.dumps({"AAPL": json.loads(_EODHD_AAPL.read_text())}))

        os.environ[self._ENV_KEY] = str(responses_path)
        os.environ["EODHD_API_KEY"] = "should-be-ignored"
        bootstrap_module.bootstrap()

        provider = factories.get_fundamentals_provider()
        assert isinstance(provider, EODHDAdapter), (
            "FINANCE_HUB_FUNDAMENTALS_FIXTURE should take priority over live API keys"
        )

    def test_unknown_ticker_returns_no_records(self, tmp_path):
        """EODHDAdapter from fixture returns empty list for unknown tickers."""
        responses_path = tmp_path / "responses.json"
        responses_path.write_text(json.dumps({"AAPL": json.loads(_EODHD_AAPL.read_text())}))

        os.environ[self._ENV_KEY] = str(responses_path)
        bootstrap_module.bootstrap()

        provider = factories.get_fundamentals_provider()
        records = provider.fetch_fundamentals("GOOGL")
        assert records == []

    def test_missing_fixture_path_raises(self, tmp_path):
        """FINANCE_HUB_FUNDAMENTALS_FIXTURE set to non-existent path raises at bootstrap."""
        os.environ[self._ENV_KEY] = str(tmp_path / "nonexistent.json")
        with pytest.raises((FileNotFoundError, OSError)):
            bootstrap_module.bootstrap()


# ---------------------------------------------------------------------------
# C1: fetch_fundamentals_fixture
# ---------------------------------------------------------------------------

class TestC1Fixture:
    """C1: empty DB + AAPL candidate + recorded EODHD fixture for the provider."""

    def test_build_creates_required_layout(self, tmp_path):
        from evals.fixtures.build_fetch_fundamentals_fixture import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()
        assert "FINANCE_HUB_FUNDAMENTALS_FIXTURE" in env
        assert Path(env["FINANCE_HUB_FUNDAMENTALS_FIXTURE"]).exists()

    def test_db_has_schema(self, tmp_path):
        from evals.fixtures.build_fetch_fundamentals_fixture import build

        env = build(tmp_path)
        tables = _tables(Path(env["FINANCE_HUB_DB"]))
        assert "fin_fundamentals" in tables
        assert "fin_instruments" in tables

    def test_aapl_registered_as_candidate(self, tmp_path):
        from evals.fixtures.build_fetch_fundamentals_fixture import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        n = _count(db, "fin_instruments", "ticker = 'AAPL'")
        assert n == 1

    def test_fin_fundamentals_empty_before_trial(self, tmp_path):
        """No fundamentals pre-seeded — fetching them is the action under test."""
        from evals.fixtures.build_fetch_fundamentals_fixture import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_fundamentals")
        assert n == 0

    def test_eodhd_responses_file_contains_aapl(self, tmp_path):
        from evals.fixtures.build_fetch_fundamentals_fixture import build

        env = build(tmp_path)
        responses = json.loads(Path(env["FINANCE_HUB_FUNDAMENTALS_FIXTURE"]).read_text())
        assert "AAPL" in responses

    def test_provider_wired_via_env_var(self, tmp_path):
        """After bootstrap with the fixture env var, provider returns AAPL records."""
        from evals.fixtures.build_fetch_fundamentals_fixture import build
        from finance_hub.market_data.fundamentals import EODHDAdapter

        env = build(tmp_path)
        os.environ["FINANCE_HUB_FUNDAMENTALS_FIXTURE"] = env["FINANCE_HUB_FUNDAMENTALS_FIXTURE"]
        factories.reset()
        try:
            bootstrap_module.bootstrap()
            provider = factories.get_fundamentals_provider()
            assert isinstance(provider, EODHDAdapter)
            records = provider.fetch_fundamentals("AAPL")
            assert len(records) == 8
        finally:
            factories.reset()
            os.environ.pop("FINANCE_HUB_FUNDAMENTALS_FIXTURE", None)


# ---------------------------------------------------------------------------
# C2: fundamentals_eligibility
# ---------------------------------------------------------------------------

class TestC2Fixture:
    """C2: AAPL with pre-seeded fundamentals + approved candidate + active strategy."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_fundamentals_pre_seeded_for_aapl(self, tmp_path):
        """8 AAPL fundamentals rows stored from EODHD fixture."""
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_fundamentals", "ticker = 'AAPL'")
        assert n == 8

    def test_aapl_has_thesis_note(self, tmp_path):
        """AAPL instrument row has note_path set (required for single_stock DCA eligibility)."""
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        note_path = _scalar(
            Path(env["FINANCE_HUB_DB"]),
            "SELECT note_path FROM fin_instruments WHERE ticker = 'AAPL'"
        )
        assert note_path is not None

    def test_aapl_approved_in_theme(self, tmp_path):
        """AAPL is approved in theme_c2 (conviction + note present)."""
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        status = _scalar(
            Path(env["FINANCE_HUB_DB"]),
            "SELECT status FROM fin_theme_instruments WHERE ticker = 'AAPL' LIMIT 1"
        )
        assert status == "approved"

    def test_active_strategy_contains_aapl(self, tmp_path):
        """strat_c2_v1 is active and contains AAPL."""
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        active = _scalar(
            db,
            "SELECT version_id FROM fin_strategy_versions WHERE status = 'active' LIMIT 1"
        )
        assert active == "strat_c2_v1"
        aapl_in_strat = _count(
            db,
            "fin_strategy_instruments",
            "version_id = 'strat_c2_v1' AND ticker = 'AAPL'"
        )
        assert aapl_in_strat == 1

    def test_portfolio_snapshot_present(self, tmp_path):
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        n = _count(
            Path(env["FINANCE_HUB_DB"]),
            "fin_portfolio_snapshots",
            "snapshot_id = 'snap_c2_fixture'"
        )
        assert n == 1

    def test_price_bar_present_for_aapl(self, tmp_path):
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        n = _count(
            Path(env["FINANCE_HUB_DB"]),
            "fin_price_bars",
            "ticker = 'AAPL'"
        )
        assert n >= 1

    def test_thesis_file_in_workspace(self, tmp_path):
        from evals.fixtures.build_fundamentals_eligibility import build

        env = build(tmp_path)
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        thesis = workspace / "research" / "instruments" / "AAPL.md"
        assert thesis.exists()


# ---------------------------------------------------------------------------
# C3: one_time_ready_deployment
# ---------------------------------------------------------------------------

class TestC3Fixture:
    """C3: VTI + AAPL with fundamentals, both DCA- and one-time-eligible."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_fundamentals_seeded_for_both_instruments(self, tmp_path):
        """AAPL (8 rows) + VTI (5 rows) = 13 rows in fin_fundamentals."""
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        aapl_n = _count(db, "fin_fundamentals", "ticker = 'AAPL'")
        vti_n = _count(db, "fin_fundamentals", "ticker = 'VTI'")
        assert aapl_n == 8
        assert vti_n == 5

    def test_active_strategy_has_both_instruments(self, tmp_path):
        """strat_c3_v1 is active; contains both VTI and AAPL."""
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        active = _scalar(
            db,
            "SELECT version_id FROM fin_strategy_versions WHERE status = 'active' LIMIT 1"
        )
        assert active == "strat_c3_v1"
        instruments = _count(
            db, "fin_strategy_instruments", "version_id = 'strat_c3_v1'"
        )
        assert instruments == 2

    def test_portfolio_snapshot_present(self, tmp_path):
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        n = _count(
            Path(env["FINANCE_HUB_DB"]),
            "fin_portfolio_snapshots",
            "snapshot_id = 'snap_c3_fixture'"
        )
        assert n == 1

    def test_price_bars_for_both_instruments(self, tmp_path):
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        for ticker in ("VTI", "AAPL"):
            n = _count(db, "fin_price_bars", f"ticker = '{ticker}'")
            assert n >= 1, f"expected price bar for {ticker}"

    def test_aapl_has_thesis_note(self, tmp_path):
        from evals.fixtures.build_one_time_ready_deployment import build

        env = build(tmp_path)
        note_path = _scalar(
            Path(env["FINANCE_HUB_DB"]),
            "SELECT note_path FROM fin_instruments WHERE ticker = 'AAPL'"
        )
        assert note_path is not None


# ---------------------------------------------------------------------------
# C7: dca_ready_no_fundamentals
# ---------------------------------------------------------------------------

class TestC7Fixture:
    """C7: VTI + AAPL plan-ready but NO fundamentals — one-time-buy must be refused."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_no_fundamentals_in_db(self, tmp_path):
        """fin_fundamentals must be empty — this is the key invariant for C7."""
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_fundamentals")
        assert n == 0

    def test_active_strategy_has_both_instruments(self, tmp_path):
        """strat_c7_v1 active with VTI + AAPL (DCA-eligible once PROMOTION_REQUIRED excluded)."""
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        active = _scalar(
            db,
            "SELECT version_id FROM fin_strategy_versions WHERE status = 'active' LIMIT 1"
        )
        assert active == "strat_c7_v1"
        instruments = _count(
            db, "fin_strategy_instruments", "version_id = 'strat_c7_v1'"
        )
        assert instruments == 2

    def test_portfolio_snapshot_present(self, tmp_path):
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        n = _count(
            Path(env["FINANCE_HUB_DB"]),
            "fin_portfolio_snapshots",
            "snapshot_id = 'snap_c7_fixture'"
        )
        assert n == 1

    def test_price_bars_present(self, tmp_path):
        """Price bars exist (so DCA plan lines can be generated)."""
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        n = _count(db, "fin_price_bars")
        assert n >= 2

    def test_aapl_has_thesis_for_dca_eligibility(self, tmp_path):
        """AAPL must have a thesis note (DCA eligibility for single_stock)."""
        from evals.fixtures.build_dca_ready_no_fundamentals import build

        env = build(tmp_path)
        note_path = _scalar(
            Path(env["FINANCE_HUB_DB"]),
            "SELECT note_path FROM fin_instruments WHERE ticker = 'AAPL'"
        )
        assert note_path is not None


# ---------------------------------------------------------------------------
# C4: multi_instrument_theme_brief
# ---------------------------------------------------------------------------

class TestC4Fixture:
    """C4: VTI + AAPL both approved in theme_c4 with sources + fundamentals."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_theme_c4_has_two_approved_instruments(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        total = _count(db, "fin_theme_instruments", "theme_key = 'theme_c4'")
        approved = _count(db, "fin_theme_instruments", "theme_key = 'theme_c4' AND status = 'approved'")
        assert total == 2
        assert approved == 2

    def test_fundamentals_seeded_for_both_instruments(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        aapl_n = _count(db, "fin_fundamentals", "ticker = 'AAPL'")
        vti_n = _count(db, "fin_fundamentals", "ticker = 'VTI'")
        assert aapl_n == 8
        assert vti_n >= 1

    def test_source_links_for_both_instruments(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        aapl_links = _count(
            db, "fin_research_source_links",
            "scope = 'instrument' AND key = 'AAPL' AND status = 'active'"
        )
        vti_links = _count(
            db, "fin_research_source_links",
            "scope = 'instrument' AND key = 'VTI' AND status = 'active'"
        )
        assert aapl_links >= 2
        assert vti_links >= 2

    def test_aapl_has_thesis_note_in_workspace(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        assert (workspace / "research" / "instruments" / "AAPL.md").exists()

    def test_theme_brief_workspace_dir_exists(self, tmp_path):
        from evals.fixtures.build_multi_instrument_theme_brief import build

        env = build(tmp_path)
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        assert (workspace / "research").is_dir()


# ---------------------------------------------------------------------------
# C5: stale_source_workflow
# ---------------------------------------------------------------------------

class TestC5Fixture:
    """C5: AAPL with one stale source link (review_after < now) to supersede."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_aapl_approved_in_theme(self, tmp_path):
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        status = _scalar(db, "SELECT status FROM fin_theme_instruments WHERE ticker = 'AAPL' LIMIT 1")
        assert status == "approved"

    def test_aapl_has_stale_source_link(self, tmp_path):
        """One active link with review_after before fixture now (2026-06-23)."""
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        n = _count(
            db,
            "fin_research_source_links",
            "scope = 'instrument' AND key = 'AAPL'"
            " AND status = 'active' AND review_after < '2026-06-23'",
        )
        assert n >= 1

    def test_aapl_has_current_source_link(self, tmp_path):
        """One active link with no review_after (or future)."""
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        n = _count(
            db,
            "fin_research_source_links",
            "scope = 'instrument' AND key = 'AAPL' AND status = 'active'"
            " AND (review_after IS NULL OR review_after >= '2026-06-23')",
        )
        assert n >= 1

    def test_aapl_thesis_in_workspace(self, tmp_path):
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        assert (workspace / "research" / "instruments" / "AAPL.md").exists()

    def test_no_superseded_links_before_trial(self, tmp_path):
        """No links superseded at fixture time — supersession is the action under test."""
        from evals.fixtures.build_stale_source_workflow import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_research_source_links", "status = 'superseded'")
        assert n == 0


# ---------------------------------------------------------------------------
# C6: new_theme_chain
# ---------------------------------------------------------------------------

class TestC6Fixture:
    """C6: fresh DB with price bars + snapshot; agent builds everything from scratch."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_no_themes_pre_seeded(self, tmp_path):
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_themes")
        assert n == 0

    def test_no_strategy_pre_seeded(self, tmp_path):
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_strategy_versions")
        assert n == 0

    def test_price_bars_for_seed_instruments(self, tmp_path):
        """Price bars for VTI + AAPL pre-seeded so the agent can plan."""
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        vti_bars = _count(db, "fin_price_bars", "ticker = 'VTI'")
        aapl_bars = _count(db, "fin_price_bars", "ticker = 'AAPL'")
        assert vti_bars >= 1
        assert aapl_bars >= 1

    def test_portfolio_snapshot_pre_seeded(self, tmp_path):
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        n = _count(
            Path(env["FINANCE_HUB_DB"]),
            "fin_portfolio_snapshots",
            "snapshot_id = 'snap_c6_fixture'",
        )
        assert n == 1

    def test_db_has_schema(self, tmp_path):
        from evals.fixtures.build_new_theme_chain import build

        env = build(tmp_path)
        tables = _tables(Path(env["FINANCE_HUB_DB"]))
        assert "fin_themes" in tables
        assert "fin_instruments" in tables
        assert "fin_deployment_plans" in tables


# ---------------------------------------------------------------------------
# C8: skill_workflow_stub
# ---------------------------------------------------------------------------

class TestC8Fixture:
    """C8: research-queue placeholder — two unreviewed candidates in a theme."""

    def test_build_creates_db_and_workspace(self, tmp_path):
        from evals.fixtures.build_skill_workflow_stub import build

        env = build(tmp_path)
        assert Path(env["FINANCE_HUB_DB"]).exists()
        assert Path(env["FINANCE_HUB_WORKSPACE"]).is_dir()

    def test_theme_c8_exists(self, tmp_path):
        from evals.fixtures.build_skill_workflow_stub import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_themes", "key = 'theme_c8'")
        assert n == 1

    def test_two_candidate_instruments(self, tmp_path):
        """Two instruments in 'candidate' state — not yet reviewed."""
        from evals.fixtures.build_skill_workflow_stub import build

        env = build(tmp_path)
        db = Path(env["FINANCE_HUB_DB"])
        n = _count(db, "fin_theme_instruments", "status = 'candidate'")
        assert n == 2

    def test_no_approved_instruments(self, tmp_path):
        from evals.fixtures.build_skill_workflow_stub import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_theme_instruments", "status = 'approved'")
        assert n == 0

    def test_no_strategy_exists(self, tmp_path):
        """No strategy yet — skill workflow includes promotion if all candidates pass review."""
        from evals.fixtures.build_skill_workflow_stub import build

        env = build(tmp_path)
        n = _count(Path(env["FINANCE_HUB_DB"]), "fin_strategy_versions")
        assert n == 0
