"""promote_to_strategy: explicit, user-confirmed research -> strategy handoff.

Assertions sit on the registered tool boundary and the rows it persists,
covering every acceptance criterion for the strategy-model slice:

- explicit confirmation is required;
- candidate state is snapshotted (later research edits do not mutate the
  created version);
- at most one ``active`` version is enforceable;
- an active strategy whose sleeve targets do not sum to 100% cannot drive
  a dollar draft;
- each ticker resolves to exactly one primary sleeve; explicit hard caps
  are stored when supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.helpers import FixedClock
from finance_hub import factories
from finance_hub.research import tools as research
from finance_hub.strategy import tools as strategy
from finance_hub.store import connection, migrations


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    p = tmp_path / "strategy.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    factories.reset()
    factories.set_clock(FixedClock(datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)))
    migrations.run()
    # A small approved research universe to promote from.
    research.set_theme(key="ai-infra", display_name="AI Infrastructure")
    research.map_instruments(
        theme_key="ai-infra",
        instruments=[
            {
                "ticker": "NVDA",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "conviction": 5,
                "conviction_note": "GPU monopoly",
                "rationale": "core thesis",
            },
            {
                "ticker": "VTI",
                "type": "etf",
                "instrument_role": "broad_market_etf",
                "status": "approved",
                "rationale": "broad base",
            },
        ],
    )
    yield p
    factories.reset()


def _promote(version_id="strat_v1", status="draft", confirm=True, **over):
    kwargs = dict(
        version_id=version_id,
        status=status,
        confirm=confirm,
        sleeves=[
            {"sleeve_key": "core", "display_name": "Core", "target_weight_pct": 70},
            {"sleeve_key": "ai", "display_name": "AI", "target_weight_pct": 30},
        ],
        instruments=[
            {"ticker": "VTI", "primary_sleeve_key": "core"},
            {
                "ticker": "NVDA",
                "primary_sleeve_key": "ai",
                "source_theme_key": "ai-infra",
                "hard_cap_pct": 10,
            },
        ],
    )
    kwargs.update(over)
    return strategy.promote_to_strategy(**kwargs)


class TestConfirmation:
    def test_requires_confirmation(self):
        with pytest.raises(ValueError, match="confirm=True"):
            _promote(confirm=False)

    def test_confirmed_creates_version(self):
        out = _promote()
        assert out["version_id"] == "strat_v1"
        assert out["status"] == "draft"
        assert len(out["sleeves"]) == 2
        assert len(out["instruments"]) == 2


class TestSnapshotImmutability:
    def test_research_edit_does_not_mutate_version(self):
        _promote()
        before = strategy.get_strategy(version_id="strat_v1")
        nvda_before = next(i for i in before["instruments"] if i["ticker"] == "NVDA")
        assert nvda_before["instrument_role"] == "single_stock"
        assert nvda_before["conviction"] == 5

        # Later research edit: re-classify the instrument and drop conviction.
        research.map_instruments(
            theme_key="ai-infra",
            instruments=[
                {
                    "ticker": "NVDA",
                    "type": "etf",
                    "instrument_role": "theme_etf",
                    "status": "watching",
                }
            ],
        )

        after = strategy.get_strategy(version_id="strat_v1")
        nvda_after = next(i for i in after["instruments"] if i["ticker"] == "NVDA")
        assert nvda_after["instrument_role"] == "single_stock"
        assert nvda_after["conviction"] == 5


class TestPrimarySleeveAndCaps:
    def test_each_ticker_one_primary_sleeve(self):
        with pytest.raises(ValueError, match="exactly one primary sleeve"):
            _promote(
                instruments=[
                    {"ticker": "NVDA", "primary_sleeve_key": "core"},
                    {"ticker": "NVDA", "primary_sleeve_key": "ai"},
                ]
            )

    def test_primary_sleeve_must_be_a_strategy_sleeve(self):
        with pytest.raises(ValueError, match="not one of this strategy's sleeves"):
            _promote(
                instruments=[{"ticker": "VTI", "primary_sleeve_key": "ghost"}]
            )

    def test_hard_cap_stored_when_supplied(self):
        out = _promote()
        nvda = next(i for i in out["instruments"] if i["ticker"] == "NVDA")
        vti = next(i for i in out["instruments"] if i["ticker"] == "VTI")
        assert nvda["hard_cap_bps"] == 1000  # 10%
        assert vti["hard_cap_bps"] is None

    def test_promote_only_known_research_candidates(self):
        with pytest.raises(LookupError, match="no research instrument"):
            _promote(instruments=[{"ticker": "TSLA", "primary_sleeve_key": "core"}])


class TestActiveAndDeployability:
    def test_only_one_active_via_promote(self):
        _promote("strat_v1", status="active")
        with pytest.raises(ValueError, match="already active"):
            _promote("strat_v2", status="active")

    def test_only_one_active_via_activate(self):
        _promote("strat_v1", status="active")
        _promote("strat_v2", status="draft")
        with pytest.raises(ValueError, match="already active"):
            strategy.activate_strategy(version_id="strat_v2", confirm=True)

    def test_active_summing_to_100_is_deployable(self):
        _promote("strat_v1", status="active")  # 70 + 30 = 100
        check = strategy.check_strategy_deployable(version_id="strat_v1")
        assert check["deployable"] is True
        assert check["targets_sum_pct"] == "100"

    def test_active_not_summing_to_100_cannot_drive_draft(self):
        _promote(
            "strat_v1",
            status="active",
            sleeves=[
                {"sleeve_key": "core", "target_weight_pct": 70},
                {"sleeve_key": "ai", "target_weight_pct": 20},
            ],
        )
        check = strategy.check_strategy_deployable(version_id="strat_v1")
        assert check["deployable"] is False
        assert any("not 100%" in r for r in check["reasons"])

    def test_draft_summing_to_100_still_not_deployable(self):
        _promote("strat_v1", status="draft")  # complete but not active
        check = strategy.check_strategy_deployable(version_id="strat_v1")
        assert check["deployable"] is False
        assert any("not 'active'" in r for r in check["reasons"])


class TestWeightParsing:
    def test_fractional_pct_to_bps(self):
        out = _promote(
            sleeves=[
                {"sleeve_key": "core", "target_weight_pct": "12.5"},
                {"sleeve_key": "ai", "target_weight_pct": "87.5"},
            ]
        )
        assert out["targets_complete"] is True
        assert {s["target_weight_bps"] for s in out["sleeves"]} == {1250, 8750}

    def test_sub_basis_point_rejected(self):
        with pytest.raises(ValueError, match="sub-basis-point"):
            _promote(
                sleeves=[
                    {"sleeve_key": "core", "target_weight_pct": "12.555"},
                    {"sleeve_key": "ai", "target_weight_pct": "87.445"},
                ]
            )
