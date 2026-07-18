"""validate_snapshot_freshness — pure function tests (no DB, no clock).

The freshness bands drive which warnings are emitted and whether one-time
buys are blocked or require explicit confirmation.

Bands (days_old, inclusive on both ends):
  0-7   → fresh (no warnings)
  8-14  → mildly_stale + PORTFOLIO_SNAPSHOT_STALE warning
  15-30 → stale + PORTFOLIO_SNAPSHOT_STALE warning; one_time_blocked=True, requires confirm
  >30   → too_stale_for_one_time + PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME block; one_time_blocked=True
"""
from __future__ import annotations

import pytest

from finance_hub.strategy.deployment import (
    PORTFOLIO_CHANGED_AFTER_SNAPSHOT,
    PORTFOLIO_SNAPSHOT_STALE,
    PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME,
    validate_snapshot_freshness,
)


class TestBandBoundaries:
    def test_0_days_fresh(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-06-23", as_of="2026-06-23")
        assert r.band == "fresh"
        assert r.days_old == 0
        assert not r.one_time_blocked
        assert not r.one_time_requires_confirm
        assert not r.warnings

    def test_7_days_still_fresh(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-06-16", as_of="2026-06-23")
        assert r.band == "fresh"
        assert r.days_old == 7
        assert not r.one_time_blocked
        assert not r.warnings

    def test_8_days_mildly_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-06-15", as_of="2026-06-23")
        assert r.band == "mildly_stale"
        assert r.days_old == 8
        assert not r.one_time_blocked
        assert not r.one_time_requires_confirm
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_SNAPSHOT_STALE in codes
        severities = [w.severity for w in r.warnings]
        assert "block" not in severities

    def test_14_days_still_mildly_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-06-09", as_of="2026-06-23")
        assert r.band == "mildly_stale"
        assert r.days_old == 14

    def test_15_days_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-06-08", as_of="2026-06-23")
        assert r.band == "stale"
        assert r.days_old == 15
        assert r.one_time_blocked
        assert r.one_time_requires_confirm
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_SNAPSHOT_STALE in codes

    def test_30_days_still_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-05-24", as_of="2026-06-23")
        assert r.band == "stale"
        assert r.days_old == 30
        assert r.one_time_blocked
        assert r.one_time_requires_confirm

    def test_31_days_too_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-05-23", as_of="2026-06-23")
        assert r.band == "too_stale_for_one_time"
        assert r.days_old == 31
        assert r.one_time_blocked
        assert not r.one_time_requires_confirm
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME in codes
        severities = [w.severity for w in r.warnings]
        assert "block" in severities

    def test_60_days_too_stale(self):
        r = validate_snapshot_freshness(snapshot_as_of="2026-04-24", as_of="2026-06-23")
        assert r.band == "too_stale_for_one_time"
        assert r.one_time_blocked


class TestPortfolioChangedForcesBand:
    def test_fresh_snapshot_with_changed_becomes_stale(self):
        r = validate_snapshot_freshness(
            snapshot_as_of="2026-06-22", as_of="2026-06-23", portfolio_changed=True
        )
        assert r.band == "stale"
        assert r.days_old == 1  # actual days_old preserved
        assert r.one_time_blocked
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_CHANGED_AFTER_SNAPSHOT in codes
        assert PORTFOLIO_SNAPSHOT_STALE in codes

    def test_mildly_stale_snapshot_with_changed_becomes_stale(self):
        r = validate_snapshot_freshness(
            snapshot_as_of="2026-06-13", as_of="2026-06-23", portfolio_changed=True
        )
        assert r.band == "stale"
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_CHANGED_AFTER_SNAPSHOT in codes

    def test_already_stale_snapshot_with_changed_stays_stale(self):
        r = validate_snapshot_freshness(
            snapshot_as_of="2026-06-05", as_of="2026-06-23", portfolio_changed=True
        )
        assert r.band == "stale"
        assert r.days_old == 18
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_CHANGED_AFTER_SNAPSHOT in codes

    def test_too_stale_snapshot_with_changed_stays_too_stale(self):
        r = validate_snapshot_freshness(
            snapshot_as_of="2026-05-15", as_of="2026-06-23", portfolio_changed=True
        )
        assert r.band == "too_stale_for_one_time"
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_CHANGED_AFTER_SNAPSHOT in codes
        assert PORTFOLIO_SNAPSHOT_TOO_OLD_FOR_ONE_TIME in codes

    def test_changed_without_freshness_issues_emits_changed_warning(self):
        r = validate_snapshot_freshness(
            snapshot_as_of="2026-06-20", as_of="2026-06-23", portfolio_changed=True
        )
        codes = [w.code for w in r.warnings]
        assert PORTFOLIO_CHANGED_AFTER_SNAPSHOT in codes
