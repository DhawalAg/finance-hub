"""End-to-end chain tests: CSV import → promote → snapshot/prices → metrics →
generate_deployment_plan → plan_readiness_check → approve.

Purpose: prove the layers actually connect. Seeded-state tests can be green
while the wiring (CSV adapter, snapshot loop, metrics computation) is broken.
These tests drive the *real* intake + acquisition paths (via a fixture provider)
to confirm the full pipeline hangs together end-to-end.

Two chains exercised:
  1. Happy path — clean snapshot, DCA-only plan, approved.
  2. Portfolio-changed path — advisory_only plan, blocked at approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

import pytest

from tests.helpers import FixedClock
from finance_hub import factories
from finance_hub.market_data import metrics as M
from finance_hub.market_data.tools import DailyBarEnvelope, snapshot, prices
from finance_hub.research import tools as research
from finance_hub.store import connection, migrations
from finance_hub.strategy import tools as strategy, memo
from finance_hub.strategy.portfolio_snapshot import FidelityPortfolioCsvAdapter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLOCK = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
_AS_OF_DATE = date(2026, 6, 23)
_SNAP_DATE = "2026-06-20"   # 3 days before clock → "fresh" band
_NOW_STR = "2026-06-23T12:00:00+00:00"

# ---------------------------------------------------------------------------
# Fake PriceProvider
# ---------------------------------------------------------------------------


@dataclass
class _FixedProvider:
    """Returns canned bars for each ticker; calls are recorded."""

    bars_by_ticker: dict
    source: str = "yfinance"
    calls: list = field(default_factory=list)

    def fetch_daily_bars(self, tickers, *, start=None, end=None):
        self.calls.append(tuple(tickers))
        out = []
        for t in tickers:
            out.extend(self.bars_by_ticker.get(t, []))
        return out


def _make_bar(ticker: str, session_date: str, close_micros: int) -> DailyBarEnvelope:
    return DailyBarEnvelope(
        ticker=ticker,
        session_date=session_date,
        open_micros=close_micros,
        high_micros=close_micros,
        low_micros=close_micros,
        close_micros=close_micros,
        adj_close_micros=close_micros,
        volume=1_000_000,
        currency="USD",
        source="yfinance",
        first_fetched_at=_NOW_STR,
        last_refreshed_at=_NOW_STR,
    )


def _daily_bars(ticker: str, close_micros: int, days: int = 60) -> list[DailyBarEnvelope]:
    """Generate `days` consecutive daily bars ending on _AS_OF_DATE."""
    end = _AS_OF_DATE
    bars = []
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).isoformat()
        bars.append(_make_bar(ticker, d, close_micros))
    return bars


# ---------------------------------------------------------------------------
# Fidelity CSV helpers
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Current Value,Cost Basis Total,Type\n"
)


def _write_fidelity_csv(path: Path) -> Path:
    csv = path / "positions.csv"
    csv.write_text(
        dedent(
            _CSV_HEADER
            + 'X1,Brokerage,VTI,Vanguard Total Stock,10,$200.00,$2000.00,$1500.00,ETF\n'
            + 'X2,Brokerage,NVDA,NVIDIA Corp,2,$500.00,$1000.00,$800.00,Stock\n'
        )
    )
    return csv


# ---------------------------------------------------------------------------
# Research seeding helpers
# ---------------------------------------------------------------------------


def _seed_research_with_thesis():
    """Set theme, instruments, thesis note, and source for NVDA."""
    research.set_theme(key="tech", display_name="Technology")
    research.map_instruments(
        theme_key="tech",
        instruments=[
            {
                "ticker": "VTI",
                "type": "etf",
                "instrument_role": "broad_market_etf",
                "status": "approved",
                "rationale": "broad market core",
            },
            {
                "ticker": "NVDA",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "conviction": 5,
                "conviction_note": "AI accelerator monopoly",
                "rationale": "dominant GPU + CUDA stack",
            },
        ],
    )
    research.set_research_note(scope="instrument", key="NVDA", body="NVDA thesis body")
    src = research.upsert_source(url="https://example.com/nvda-thesis", title="NVDA thesis")
    research.link_source(source_id=src["id"], scope="instrument", key="NVDA")


def _promote_strategy():
    strategy.promote_to_strategy(
        version_id="strat_e2e",
        status="active",
        confirm=True,
        sleeves=[
            {"sleeve_key": "broad", "target_weight_pct": 60},
            {"sleeve_key": "growth", "target_weight_pct": 40},
        ],
        instruments=[
            {"ticker": "VTI", "primary_sleeve_key": "broad"},
            {"ticker": "NVDA", "primary_sleeve_key": "growth", "source_theme_key": "tech"},
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "e2e.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(memo, "WORKSPACE_ROOT", tmp_path / "workspace")
    factories.reset()
    factories.set_clock(FixedClock(_CLOCK))
    migrations.run()
    yield p
    factories.reset()


@pytest.fixture()
def provider(tmp_path):
    """Fixture provider serving 60 days of bars for VTI, NVDA, and SPY."""
    prov = _FixedProvider(
        bars_by_ticker={
            "VTI": _daily_bars("VTI", 200_000_000, days=60),
            "NVDA": _daily_bars("NVDA", 500_000_000, days=60),
            "SPY": _daily_bars("SPY", 540_000_000, days=60),
        }
    )
    factories.set_price_provider(prov)
    return prov


# ---------------------------------------------------------------------------
# Chain test 1: happy path — CSV import → promote → snapshot → metrics →
#               generate_deployment_plan → plan_readiness_check → approve
# ---------------------------------------------------------------------------


class TestHappyPathChain:
    def test_csv_to_approval_full_chain(self, provider, tmp_path):
        # --- Step 1: import portfolio CSV ---
        csv_path = _write_fidelity_csv(tmp_path)
        adapter = FidelityPortfolioCsvAdapter()
        snapshot_id = adapter.import_csv(csv_path, as_of=f"{_SNAP_DATE}T10:00:00-04:00")
        assert snapshot_id.startswith("snap_")

        # --- Step 2: set up research + promote strategy ---
        _seed_research_with_thesis()
        _promote_strategy()

        # --- Step 3: snapshot() fetches and stores price bars ---
        snap_result = snapshot(["VTI", "NVDA", "SPY"], as_of=_AS_OF_DATE)
        assert {o.ticker for o in snap_result.ok} == {"VTI", "NVDA", "SPY"}
        assert snap_result.failures == ()

        # --- Step 4: compute and store metrics from stored bars ---
        with connection.connect() as conn:
            spy_series = M.series_from_bars(conn, "SPY", "yfinance", _AS_OF_DATE)
            for ticker in ("VTI", "NVDA"):
                series = M.series_from_bars(conn, ticker, "yfinance", _AS_OF_DATE)
                assert series, f"no bars for {ticker}"
                mv = M.compute_ticker_metrics(
                    series,
                    ticker=ticker,
                    as_of=_AS_OF_DATE,
                    source="yfinance",
                    benchmark_series=spy_series,
                    benchmark_ticker="SPY",
                )
                M.store_metrics(conn, mv)

        # --- Step 5: prices() serves cached envelopes ---
        envelopes = prices(["VTI", "NVDA"], as_of=_AS_OF_DATE)
        assert set(envelopes.keys()) == {"VTI", "NVDA"}
        assert not envelopes["VTI"].stale
        assert not envelopes["NVDA"].stale

        # --- Step 6: generate deployment plan ---
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snapshot_id,
            strategy_version_id="strat_e2e",
            deployable_cash="2000",
            dca_budget="2000",
            one_time_buy_budget="0",
            benchmark_ticker="SPY",
        )
        assert plan["output_mode"] == "deployment_draft"
        assert plan["status"] in ("proposed", "proposed_with_warnings")
        assert plan["snapshot_freshness_band"] == "fresh"
        assert len(plan["lines"]) > 0
        # Lines must reference evidence stored in DB
        assert plan["evidence"]

        plan_id = plan["plan_id"]

        # --- Step 7: plan_readiness_check ---
        readiness = strategy.plan_readiness_check(plan_id=plan_id)
        assert readiness["readiness_status"] == "still_approvable"
        assert readiness["approvable"] is True
        assert readiness["blocking_reasons"] == []

        # --- Step 8: approve ---
        approval = strategy.approve_deployment_plan(plan_id=plan_id, confirm=True)
        assert approval["status"] == "approved"
        assert approval["approved_at"]

        # Approved memo written to workspace/approved/
        memo_path = Path(approval["memo_path"])
        assert memo_path.exists()

        # DB reflects approved status
        with connection.connect() as conn:
            row = conn.execute(
                "SELECT status FROM fin_deployment_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        assert row["status"] == "approved"

    def test_csv_snapshot_id_flows_into_plan_inputs(self, provider, tmp_path):
        """The snapshot_id from CSV intake appears verbatim in the plan's stored inputs."""
        csv_path = _write_fidelity_csv(tmp_path)
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv_path, as_of=f"{_SNAP_DATE}T10:00:00-04:00"
        )
        _seed_research_with_thesis()
        _promote_strategy()
        snapshot(["VTI", "NVDA", "SPY"], as_of=_AS_OF_DATE)

        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snapshot_id,
            strategy_version_id="strat_e2e",
            deployable_cash="1000",
            dca_budget="1000",
        )

        with connection.connect() as conn:
            row = conn.execute(
                "SELECT portfolio_snapshot_id FROM fin_deployment_plans WHERE plan_id = ?",
                (plan["plan_id"],),
            ).fetchone()
        assert row["portfolio_snapshot_id"] == snapshot_id


# ---------------------------------------------------------------------------
# Chain test 2: portfolio_changed_after_snapshot → advisory_only, blocked at
#               approval; validates the degraded-path wiring
# ---------------------------------------------------------------------------


class TestAdvisoryOnlyChain:
    def test_portfolio_changed_blocks_approval(self, provider, tmp_path):
        csv_path = _write_fidelity_csv(tmp_path)
        snapshot_id = FidelityPortfolioCsvAdapter().import_csv(
            csv_path, as_of=f"{_SNAP_DATE}T10:00:00-04:00"
        )
        _seed_research_with_thesis()
        _promote_strategy()
        snapshot(["VTI", "NVDA", "SPY"], as_of=_AS_OF_DATE)

        # Generate with portfolio_changed flag → advisory_only
        plan = strategy.generate_deployment_plan(
            portfolio_snapshot_id=snapshot_id,
            strategy_version_id="strat_e2e",
            deployable_cash="2000",
            dca_budget="2000",
            portfolio_changed_after_snapshot=True,
        )
        assert plan["status"] == "advisory_only"
        warning_codes = {w["code"] for w in plan["warnings"]}
        assert "PORTFOLIO_CHANGED_AFTER_SNAPSHOT" in warning_codes

        plan_id = plan["plan_id"]

        # Readiness check detects non-approvable status
        readiness = strategy.plan_readiness_check(plan_id=plan_id)
        assert readiness["readiness_status"] == "approval_blocked"
        assert readiness["approvable"] is False
        assert any("advisory_only" in r for r in readiness["blocking_reasons"])

        # Approval fails
        with pytest.raises(Exception, match=r"approval_blocked|advisory_only|cannot be approved"):
            strategy.approve_deployment_plan(plan_id=plan_id, confirm=True)
