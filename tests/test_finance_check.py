"""Tests for finance check: run_checks(env) returning structured CheckResult list.

Deterministic suite (no network). The live twin verifies a real yfinance fetch.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from finance_hub import factories
from finance_hub.checks import CheckResult, run_checks


def _get(results: list[CheckResult], name: str) -> CheckResult:
    for r in results:
        if r.name == name:
            return r
    raise KeyError(f"No check named {name!r}; found: {[r.name for r in results]}")


# ---------------------------------------------------------------------------
# Python version
# ---------------------------------------------------------------------------

class TestPythonVersionCheck:
    def test_python_version_green(self):
        results = run_checks({})
        r = _get(results, "python_version")
        assert r.severity == "green"
        assert "3." in r.message

    def test_python_version_contains_version_string(self):
        import sys
        results = run_checks({})
        r = _get(results, "python_version")
        expected = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert expected in r.message


# ---------------------------------------------------------------------------
# SQLite store
# ---------------------------------------------------------------------------

class TestStoreCheck:
    def test_store_yellow_db_not_found(self, tmp_path):
        env = {"FINANCE_HUB_DB": str(tmp_path / "nonexistent.db")}
        results = run_checks(env)
        r = _get(results, "store")
        assert r.severity == "yellow"
        assert r.fix is not None

    def test_store_green_with_initialized_db(self, tmp_path):
        db_path = tmp_path / "finance-hub.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE fin_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO fin_schema_migrations VALUES (1, '2026-06-23T00:00:00+00:00')"
            )
            conn.execute(
                "INSERT INTO fin_schema_migrations VALUES (12, '2026-06-23T01:00:00+00:00')"
            )
            conn.commit()
        env = {"FINANCE_HUB_DB": str(db_path)}
        results = run_checks(env)
        r = _get(results, "store")
        assert r.severity == "green"
        assert "12" in r.message   # latest version
        assert "2" in r.message    # migration count

    def test_store_yellow_db_exists_but_no_schema(self, tmp_path):
        db_path = tmp_path / "empty.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE foo (id INTEGER)")
            conn.commit()
        env = {"FINANCE_HUB_DB": str(db_path)}
        results = run_checks(env)
        r = _get(results, "store")
        assert r.severity == "yellow"

    def test_store_red_unreadable(self, tmp_path):
        db_dir = tmp_path / "finance-hub.db"
        db_dir.mkdir()  # directory where a file is expected → sqlite3 will fail
        env = {"FINANCE_HUB_DB": str(db_dir)}
        results = run_checks(env)
        r = _get(results, "store")
        assert r.severity == "red"
        assert r.fix is not None


# ---------------------------------------------------------------------------
# Workspace directory
# ---------------------------------------------------------------------------

class TestWorkspaceCheck:
    def test_workspace_green_when_dir_exists(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        env = {"FINANCE_HUB_WORKSPACE": str(ws)}
        results = run_checks(env)
        r = _get(results, "workspace")
        assert r.severity == "green"

    def test_workspace_yellow_when_dir_missing(self, tmp_path):
        env = {"FINANCE_HUB_WORKSPACE": str(tmp_path / "no_such_dir")}
        results = run_checks(env)
        r = _get(results, "workspace")
        assert r.severity == "yellow"
        assert "first write" in r.message.lower() or "created" in r.message.lower()

    def test_workspace_fix_hint_present_when_missing(self, tmp_path):
        env = {"FINANCE_HUB_WORKSPACE": str(tmp_path / "no_such_dir")}
        results = run_checks(env)
        r = _get(results, "workspace")
        assert r.fix is not None


# ---------------------------------------------------------------------------
# Price provider wiring
# ---------------------------------------------------------------------------

class TestPriceProviderCheck:
    def test_price_provider_green_yfinance_importable(self):
        pytest.importorskip("yfinance")
        env = {}  # defaults to yfinance
        results = run_checks(env)
        r = _get(results, "price_provider")
        assert r.severity == "green"

    def test_price_provider_green_explicit_yfinance(self):
        pytest.importorskip("yfinance")
        env = {"FINANCE_HUB_PRICE_PROVIDER": "yfinance"}
        results = run_checks(env)
        r = _get(results, "price_provider")
        assert r.severity == "green"

    def test_price_provider_yellow_when_none(self):
        env = {"FINANCE_HUB_PRICE_PROVIDER": "none"}
        results = run_checks(env)
        r = _get(results, "price_provider")
        assert r.severity == "yellow"
        assert r.fix is not None

    def test_price_provider_red_unknown(self):
        env = {"FINANCE_HUB_PRICE_PROVIDER": "polygon"}
        results = run_checks(env)
        r = _get(results, "price_provider")
        assert r.severity == "red"
        assert r.fix is not None


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

class TestFundamentalsCheck:
    def test_yellow_when_no_key_configured(self):
        results = run_checks({})
        r = _get(results, "fundamentals")
        assert r.severity == "yellow"

    def test_message_names_dca_consequence_when_unconfigured(self):
        results = run_checks({})
        r = _get(results, "fundamentals")
        assert "dca" in r.message.lower() or "one-time" in r.message.lower()

    def test_fix_points_at_provider_keys_when_unconfigured(self):
        results = run_checks({})
        r = _get(results, "fundamentals")
        assert r.fix is not None
        assert "EODHD_API_KEY" in r.fix or "ALPHA_VANTAGE_API_KEY" in r.fix

    def test_green_when_eodhd_key_set(self):
        results = run_checks({"EODHD_API_KEY": "k"})
        r = _get(results, "fundamentals")
        assert r.severity == "green"
        assert "EODHD" in r.message

    def test_green_when_alpha_vantage_key_set(self):
        results = run_checks({"ALPHA_VANTAGE_API_KEY": "k"})
        r = _get(results, "fundamentals")
        assert r.severity == "green"


# ---------------------------------------------------------------------------
# ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------

class TestAnthropicKeyCheck:
    def test_anthropic_key_yellow_when_absent(self):
        env = {}  # no ANTHROPIC_API_KEY
        results = run_checks(env)
        r = _get(results, "anthropic_api_key")
        assert r.severity == "yellow"

    def test_anthropic_key_green_when_set(self):
        env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
        results = run_checks(env)
        r = _get(results, "anthropic_api_key")
        assert r.severity == "green"

    def test_anthropic_key_yellow_has_optional_note(self):
        results = run_checks({})
        r = _get(results, "anthropic_api_key")
        msg = r.message.lower()
        assert "optional" in msg or "mcp" in msg or "llm" in msg


# ---------------------------------------------------------------------------
# Env vars reporting
# ---------------------------------------------------------------------------

class TestEnvVarsCheck:
    def test_env_vars_reported_when_defaulted(self):
        env = {}
        results = run_checks(env)
        names = [r.name for r in results]
        assert "env_finance_hub_db" in names
        assert "env_finance_hub_workspace" in names
        assert "env_finance_hub_price_provider" in names

    def test_env_vars_green_when_set(self):
        env = {
            "FINANCE_HUB_DB": "/tmp/test.db",
            "FINANCE_HUB_WORKSPACE": "/tmp/ws",
            "FINANCE_HUB_PRICE_PROVIDER": "yfinance",
        }
        results = run_checks(env)
        r = _get(results, "env_finance_hub_db")
        assert r.severity == "green"
        assert "/tmp/test.db" in r.message

    def test_env_vars_green_when_defaulted(self):
        env = {}
        results = run_checks(env)
        r = _get(results, "env_finance_hub_db")
        assert r.severity == "green"
        assert "default" in r.message.lower()


# ---------------------------------------------------------------------------
# --live flag: deterministic twin using a factory-injected stub
# ---------------------------------------------------------------------------

class TestLiveCheckDeterministicTwin:
    def setup_method(self):
        factories.reset()

    def teardown_method(self):
        factories.reset()

    def test_live_price_check_green_with_stub_provider(self):
        """Deterministic twin: stub provider returns bars → live check is green."""
        from finance_hub.market_data.tools import DailyBarEnvelope

        stub_bars = [
            DailyBarEnvelope(
                ticker="SPY",
                session_date="2026-06-02",
                open_micros=536_000_000,
                high_micros=537_000_000,
                low_micros=535_000_000,
                close_micros=536_500_000,
                adj_close_micros=536_500_000,
                volume=80_000_000,
                currency="USD",
                source="stub",
                first_fetched_at="2026-06-23T00:00:00+00:00",
                last_refreshed_at="2026-06-23T00:00:00+00:00",
            )
        ]

        class _StubProvider:
            def fetch_daily_bars(self, tickers, *, start=None, end=None):
                return stub_bars

        factories.set_price_provider(_StubProvider())
        results = run_checks({}, live=True)
        r = _get(results, "price_live")
        assert r.severity == "green"
        assert "1" in r.message  # 1 bar returned

    def test_live_price_check_red_when_provider_raises(self):
        """Deterministic twin: provider error → live check is red with fix hint."""
        class _FailingProvider:
            def fetch_daily_bars(self, tickers, *, start=None, end=None):
                raise RuntimeError("network timeout")

        factories.set_price_provider(_FailingProvider())
        results = run_checks({}, live=True)
        r = _get(results, "price_live")
        assert r.severity == "red"
        assert r.fix is not None

    def test_live_price_check_not_present_without_live_flag(self):
        """Without --live, the price_live check should not be in the results."""
        results = run_checks({}, live=False)
        names = [r.name for r in results]
        assert "price_live" not in names

    def test_live_price_check_yellow_when_no_bars(self):
        """Provider returns empty list → live check is yellow."""
        class _EmptyProvider:
            def fetch_daily_bars(self, tickers, *, start=None, end=None):
                return []

        factories.set_price_provider(_EmptyProvider())
        results = run_checks({}, live=True)
        r = _get(results, "price_live")
        assert r.severity == "yellow"


# ---------------------------------------------------------------------------
# Live network test (opt-in, excluded from default suite)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_live_price_ping_real_network():
    """Bootstrap wires yfinance; real SPY fetch succeeds."""
    try:
        factories.reset()
        from finance_hub import bootstrap as bootstrap_module
        bootstrap_module.bootstrap()
        results = run_checks({}, live=True)
        r = _get(results, "price_live")
        assert r.severity in ("green", "yellow")  # green if bars returned
    finally:
        factories.reset()
