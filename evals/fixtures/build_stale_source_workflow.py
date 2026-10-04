"""Fixture builder for 'stale_source_workflow' (used by C5, spec §5.2).

Builds a DB with AAPL in theme_c5 that has one stale source link:
- fin_themes: theme_c5 (status=watching, display_name="Research Candidates")
- fin_instruments: AAPL (stock/single_stock, approved, conviction=4)
- fin_research_source_links:
    src1 (active, review_after='2026-05-01' — stale vs now=2026-06-23)
    src2 (active, no review_after — current)
- workspace/research/instruments/AAPL.md: thesis note

Agent task (C5): identify the stale source via finance.sources_due_for_review,
supersede it with finance.supersede_source_link, add a replacement with
finance.upsert_source + finance.link_source, and update the research note
via finance.set_research_note. May also be judge-graded for note quality.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

VERSION = "1"

_NOW = "2026-06-23T12:00:00+00:00"
_STALE_REVIEW_AFTER = "2026-05-01"   # clearly past now


class _FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def build(trial_dir: Path) -> dict[str, str]:
    """Materialise the stale_source_workflow fixture into trial_dir."""
    trial_dir.mkdir(parents=True, exist_ok=True)
    workspace = trial_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    db_path = trial_dir / "db.sqlite"
    _setup_db(db_path, workspace)

    return {
        "FINANCE_HUB_DB": str(db_path),
        "FINANCE_HUB_WORKSPACE": str(workspace),
    }


def _setup_db(db_path: Path, workspace: Path) -> None:
    from finance_hub import factories
    from finance_hub.research import tools as research
    from finance_hub.store import connection, migrations

    now_dt = datetime.fromisoformat(_NOW)
    old_db = connection.DB_PATH
    old_migrated = frozenset(connection._migrated_paths)
    old_clock = factories._clock
    old_workspace_env = os.environ.get("FINANCE_HUB_WORKSPACE")

    connection.DB_PATH = db_path
    connection._migrated_paths.discard(str(db_path))
    factories.set_clock(_FixedClock(now_dt))
    os.environ["FINANCE_HUB_WORKSPACE"] = str(workspace)

    try:
        migrations.run()

        # 1. Theme + approved AAPL
        research.set_theme(key="theme_c5", display_name="Research Candidates")
        research.map_instruments(
            theme_key="theme_c5",
            instruments=[{
                "ticker": "AAPL",
                "type": "stock",
                "instrument_role": "single_stock",
                "status": "approved",
                "display_name": "Apple Inc",
                "conviction": 4,
                "conviction_note": "Quality franchise with durable margins",
            }],
        )

        # 2. Thesis note in workspace
        instruments_dir = workspace / "research" / "instruments"
        instruments_dir.mkdir(parents=True, exist_ok=True)
        research.set_research_note(
            scope="instrument",
            key="AAPL",
            body=(
                "# AAPL — Investment Thesis\n\n"
                "Apple's ecosystem moat supports durable pricing power. Services revenue "
                "growing at 12% YoY provides recurring cash flows. Conviction: 4/5.\n\n"
                "Sources: AAPL 10-K 2024 (filing), Q1 2025 earnings call.\n"
            ),
        )

        # 3. Stale source link (review_after in the past)
        stale_src = research.upsert_source(
            url="https://example.com/aapl-q1-2024-earnings",
            title="AAPL Q1 2024 Earnings Call",
            source_type="transcript",
        )
        # Link with a past review_after so it shows up in sources_due_for_review
        from finance_hub.research._store import upsert_source_link
        upsert_source_link(
            source_id=stale_src["id"],
            scope="instrument",
            key="AAPL",
            note="Q1 2024 earnings — due for supersession after Q4 2024 released",
            status="active",
            review_after=_STALE_REVIEW_AFTER,
            now=_NOW,
        )

        # 4. Current source link (no review_after)
        current_src = research.upsert_source(
            url="https://example.com/aapl-10k-2025",
            title="AAPL 10-K FY2025",
            source_type="filing",
        )
        research.link_source(source_id=current_src["id"], scope="instrument", key="AAPL")

    finally:
        connection.DB_PATH = old_db
        connection._migrated_paths = set(old_migrated)
        factories._clock = old_clock
        if old_workspace_env is None:
            os.environ.pop("FINANCE_HUB_WORKSPACE", None)
        else:
            os.environ["FINANCE_HUB_WORKSPACE"] = old_workspace_env
