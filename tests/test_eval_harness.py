"""Tests for the harness MVP: fixture builder, grader registry, harness orchestrator.

Issue #41 — Phase 1 end-to-end tracer bullet.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from evals.harness.runner import Transcript, TranscriptEvent, TrialEnv

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
TASK_R1 = REPO_ROOT / "evals" / "tasks" / "R1.yaml"


def _make_import_transcript(as_of_source: str = "csv_download_timestamp") -> Transcript:
    """Minimal transcript that looks like a successful CSV import."""
    return Transcript(events=[
        TranscriptEvent(type="assistant", data={
            "model": "claude-sonnet-5",
            "content": [
                {"type": "tool_use", "id": "tu_1",
                 "name": "finance.import_portfolio_csv",
                 "input": {"csv_path": "fixture/fidelity_sample.csv"}},
            ],
        }),
        TranscriptEvent(type="user", data={
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "is_error": False,
                    "content": {
                        "snapshot_id": "snap_abc123",
                        "as_of": "2026-06-22T10:30:00-04:00",
                        "as_of_source": as_of_source,
                        "buckets": {
                            "supported": {"count": 3, "tickers": ["AAPL", "QQQ", "VTI"]},
                            "cash": {"count": 1, "tickers": ["FCASH**"]},
                            "unsupported": {"count": 0, "tickers": []},
                            "skipped": {"count": 1, "tickers": []},
                        },
                    },
                }
            ],
        }),
        TranscriptEvent(type="result", data={
            "num_turns": 1,
            "total_cost_usd": 0.001,
            "is_error": False,
            "session_id": "sess-r1",
        }),
    ])


# ---------------------------------------------------------------------------
# Fixture builder: evals.fixtures.build_fidelity_sample_csv
# ---------------------------------------------------------------------------

class TestFixtureBuilder:
    def test_build_creates_db_and_csv(self, tmp_path):
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        csv_path = tmp_path / "fixture" / "fidelity_sample.csv"

        assert db_path.exists(), "db.sqlite was not created"
        assert workspace.is_dir(), "workspace dir was not created"
        assert csv_path.exists(), "fidelity_sample.csv was not created"

    def test_db_has_schema(self, tmp_path):
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "fin_portfolio_snapshots" in tables
        assert "fin_portfolio_positions" in tables
        assert "fin_schema_migrations" in tables

    def test_db_is_empty_before_trial(self, tmp_path):
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_snapshots"
            ).fetchone()[0]
        assert count == 0

    def test_csv_content_matches_source(self, tmp_path):
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        csv_path = tmp_path / "fixture" / "fidelity_sample.csv"
        src_csv = REPO_ROOT / "tests" / "fixtures" / "fidelity_positions_sample.csv"

        assert csv_path.read_bytes() == src_csv.read_bytes()

    def test_env_overrides_have_correct_keys(self, tmp_path):
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        assert "FINANCE_HUB_DB" in env
        assert "FINANCE_HUB_WORKSPACE" in env

    def test_build_does_not_mutate_connection_db_path(self, tmp_path):
        """Fixture builder must restore connection.DB_PATH after building."""
        from finance_hub.store import connection
        from evals.fixtures.build_fidelity_sample_csv import build

        original_path = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original_path


# ---------------------------------------------------------------------------
# Grader registry: evals.harness.graders
# ---------------------------------------------------------------------------

class TestGraderSQL:
    def _make_seeded_db(self, tmp_path: Path) -> Path:
        """Build a fixture DB and run CSV import so graders have data to check."""
        from evals.fixtures.build_fidelity_sample_csv import build
        from finance_hub.store import connection, migrations
        from finance_hub.ingestion import tools as ingestion

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])

        old_path = connection.DB_PATH
        connection.DB_PATH = db_path
        connection._migrated_paths.discard(str(db_path))
        try:
            ingestion.import_portfolio_csv(
                csv_path=str(tmp_path / "fixture" / "fidelity_sample.csv")
            )
        finally:
            connection.DB_PATH = old_path

        return db_path

    def test_snapshot_row_exists_passes_when_present(self, tmp_path):
        from evals.harness.graders import _run_sql_grader

        db_path = self._make_seeded_db(tmp_path)
        spec = {
            "id": "outcome.snapshot_row_exists",
            "role": "gate",
            "detail": "snapshot with correct as_of and source_adapter",
            "sql": (
                "SELECT COUNT(*) FROM fin_portfolio_snapshots "
                "WHERE as_of = '2026-06-22T10:30:00-04:00' "
                "AND source_adapter = 'fidelity_csv'"
            ),
            "expect": 1,
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "pass"
        assert result.actual == 1

    def test_position_count_passes(self, tmp_path):
        from evals.harness.graders import _run_sql_grader

        db_path = self._make_seeded_db(tmp_path)
        spec = {
            "id": "outcome.position_count",
            "role": "gate",
            "detail": "4 position rows",
            "sql": (
                "SELECT COUNT(*) FROM fin_portfolio_positions "
                "WHERE snapshot_id = (SELECT snapshot_id FROM fin_portfolio_snapshots LIMIT 1)"
            ),
            "expect": 4,
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "pass"
        assert result.actual == 4

    def test_supported_tickers_list_comparison(self, tmp_path):
        from evals.harness.graders import _run_sql_grader

        db_path = self._make_seeded_db(tmp_path)
        spec = {
            "id": "outcome.supported_tickers",
            "role": "gate",
            "detail": "supported tickers sorted",
            "sql": (
                "SELECT ticker FROM fin_portfolio_positions "
                "WHERE is_supported = 1 ORDER BY ticker"
            ),
            "expect": ["AAPL", "QQQ", "VTI"],
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "pass"
        assert result.actual == ["AAPL", "QQQ", "VTI"]

    def test_cash_position_passes(self, tmp_path):
        from evals.harness.graders import _run_sql_grader

        db_path = self._make_seeded_db(tmp_path)
        spec = {
            "id": "outcome.cash_position_stored",
            "role": "gate",
            "detail": "FCASH** stored correctly",
            "sql": (
                "SELECT COUNT(*) FROM fin_portfolio_positions "
                "WHERE ticker = 'FCASH**' AND asset_type = 'cash' "
                "AND is_supported = 0 AND cash_value_micros = 1234560000"
            ),
            "expect": 1,
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "pass"

    def test_sql_fail_wrong_count(self, tmp_path):
        from evals.harness.graders import _run_sql_grader

        db_path = self._make_seeded_db(tmp_path)
        spec = {
            "id": "outcome.position_count",
            "role": "gate",
            "detail": "wrong expected count",
            "sql": "SELECT COUNT(*) FROM fin_portfolio_positions",
            "expect": 99,  # wrong
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "fail"

    def test_sql_error_returns_fail(self, tmp_path):
        from evals.harness.graders import _run_sql_grader
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        spec = {
            "id": "outcome.bad_sql",
            "role": "gate",
            "detail": "SQL that errors",
            "sql": "SELECT COUNT(*) FROM nonexistent_table",
            "expect": 0,
        }
        result = _run_sql_grader(spec, db_path)
        assert result.verdict == "fail"
        assert "SQL error" in (result.actual or "")


class TestGraderCheck:
    def test_as_of_source_passes_when_correct(self):
        from evals.harness.graders import _run_check_grader

        transcript = _make_import_transcript(as_of_source="csv_download_timestamp")
        spec = {
            "id": "outcome.as_of_source_is_csv",
            "role": "gate",
            "detail": "as_of_source must be csv_download_timestamp",
            "check": "tool_result('finance.import_portfolio_csv').as_of_source == 'csv_download_timestamp'",
        }
        result = _run_check_grader(spec, transcript)
        assert result.verdict == "pass"

    def test_as_of_source_fails_when_wrong(self):
        from evals.harness.graders import _run_check_grader

        transcript = _make_import_transcript(as_of_source="explicit_override")
        spec = {
            "id": "outcome.as_of_source_is_csv",
            "role": "gate",
            "detail": "as_of_source must be csv_download_timestamp",
            "check": "tool_result('finance.import_portfolio_csv').as_of_source == 'csv_download_timestamp'",
        }
        result = _run_check_grader(spec, transcript)
        assert result.verdict == "fail"

    def test_check_on_missing_tool_call_fails(self):
        from evals.harness.graders import _run_check_grader

        empty_transcript = Transcript(events=[
            TranscriptEvent(type="result", data={"num_turns": 0, "is_error": False}),
        ])
        spec = {
            "id": "outcome.as_of_source_is_csv",
            "role": "gate",
            "detail": "tool not called",
            "check": "tool_result('finance.import_portfolio_csv').as_of_source == 'csv_download_timestamp'",
        }
        result = _run_check_grader(spec, empty_transcript)
        assert result.verdict == "fail"

    def test_check_returns_gate_role(self):
        from evals.harness.graders import _run_check_grader

        transcript = _make_import_transcript()
        spec = {
            "id": "outcome.as_of_source_is_csv",
            "role": "gate",
            "detail": "role check",
            "check": "tool_result('finance.import_portfolio_csv').as_of_source == 'csv_download_timestamp'",
        }
        result = _run_check_grader(spec, transcript)
        assert result.role == "gate"


class TestGradeDispatch:
    def test_grade_dispatches_sql(self, tmp_path):
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        transcript = _make_import_transcript()
        task = {
            "graders": [{
                "id": "outcome.snapshot_row_exists",
                "role": "gate",
                "detail": "snapshot count",
                "sql": "SELECT COUNT(*) FROM fin_portfolio_snapshots",
                "expect": 0,  # empty DB
            }]
        }
        results = grade(transcript, db_path, tmp_path / "workspace", task)
        assert len(results) == 1
        assert results[0].grader_id == "outcome.snapshot_row_exists"

    def test_grade_dispatches_check(self, tmp_path):
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        transcript = _make_import_transcript()
        task = {
            "graders": [{
                "id": "outcome.as_of_source_is_csv",
                "role": "gate",
                "detail": "as_of_source check",
                "check": "tool_result('finance.import_portfolio_csv').as_of_source == 'csv_download_timestamp'",
            }]
        }
        results = grade(transcript, db_path, tmp_path / "workspace", task)
        assert len(results) == 1
        assert results[0].verdict == "pass"

    def test_grade_returns_empty_for_no_graders(self, tmp_path):
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        results = grade(Transcript(), db_path, tmp_path / "workspace", {"graders": []})
        assert results == []

    def test_grade_deferred_grader_returns_skip(self, tmp_path):
        # A grader with no inline sql/check and no matching assertion is deferred → skip
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        task = {
            "graders": [{
                "id": "trajectory.no_invented_prices",
                "role": "gate",
                "detail": "deferred: LLM judge required",
            }]
            # no reference.assertions → lookup fails → skip
        }
        results = grade(Transcript(), db_path, tmp_path / "workspace", task)
        assert results[0].verdict == "skip"


# ---------------------------------------------------------------------------
# Harness: evals.harness.harness
# ---------------------------------------------------------------------------

class TestHarnessValidation:
    def test_frozen_fixture_without_now_raises(self):
        from evals.harness.harness import _validate_task

        task = {"id": "R1", "fixture": "fidelity_sample_csv"}  # no 'now'
        with pytest.raises(ValueError, match="now"):
            _validate_task(task)

    def test_frozen_fixture_with_now_is_valid(self):
        from evals.harness.harness import _validate_task

        task = {"id": "R1", "fixture": "fidelity_sample_csv", "now": "2026-06-23T12:00:00+00:00"}
        _validate_task(task)  # should not raise

    def test_task_without_fixture_no_now_is_valid(self):
        from evals.harness.harness import _validate_task

        task = {"id": "R_live", "suite": "regression"}  # live-replay: no fixture, no now
        _validate_task(task)  # should not raise


class TestPromptHash:
    def test_hash_is_deterministic(self, tmp_path):
        from evals.harness.harness import compute_prompt_hash, _materialize_runtime_surface

        _materialize_runtime_surface(tmp_path)
        h1 = compute_prompt_hash(tmp_path)
        h2 = compute_prompt_hash(tmp_path)
        assert h1 == h2

    def test_hash_is_hex_string(self, tmp_path):
        from evals.harness.harness import compute_prompt_hash, _materialize_runtime_surface

        _materialize_runtime_surface(tmp_path)
        h = compute_prompt_hash(tmp_path)
        assert len(h) == 64
        int(h, 16)  # should not raise — it's valid hex

    def test_hash_changes_if_file_changes(self, tmp_path):
        from evals.harness.harness import compute_prompt_hash, _materialize_runtime_surface

        _materialize_runtime_surface(tmp_path)
        h1 = compute_prompt_hash(tmp_path)

        runtime_claude = tmp_path / "runtime" / "CLAUDE.md"
        runtime_claude.write_text(runtime_claude.read_text() + "\n# extra line")
        h2 = compute_prompt_hash(tmp_path)
        assert h1 != h2


class TestHarnessRun:
    """Full harness.run() with a mock runner — validates run dir layout."""

    def _make_mock_runner(self, db_path: Path | None = None):
        """Return a Runner that 'imports the CSV' into db_path if provided."""
        from evals.harness.runner import Runner

        class MockRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                # If db_path provided, do the real import so SQL graders pass
                if db_path is not None:
                    from finance_hub.store import connection
                    from finance_hub.ingestion import tools as ingestion
                    old = connection.DB_PATH
                    connection.DB_PATH = db_path
                    connection._migrated_paths.discard(str(db_path))
                    try:
                        ingestion.import_portfolio_csv(
                            csv_path=str(env.cwd / "fixture" / "fidelity_sample.csv")
                        )
                    finally:
                        connection.DB_PATH = old
                return _make_import_transcript()

        return MockRunner()

    def test_run_creates_run_dir(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, results_root=results_root)
        assert run_dir.is_dir()

    def test_run_writes_meta_json(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, results_root=results_root)
        meta_path = run_dir / "meta.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["task_id"] == "R1"
        assert "prompt_hash" in meta
        assert "started_at" in meta
        assert "finished_at" in meta
        assert "model" in meta

    def test_run_writes_transcript_jsonl(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, results_root=results_root)
        transcript_path = run_dir / "transcript.jsonl"
        assert transcript_path.exists()

        lines = [l for l in transcript_path.read_text().splitlines() if l.strip()]
        assert len(lines) > 0

    def test_run_writes_verdicts_jsonl(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, results_root=results_root)
        verdicts_path = run_dir / "verdicts.jsonl"
        assert verdicts_path.exists()

        lines = [l for l in verdicts_path.read_text().splitlines() if l.strip()]
        verdicts = [json.loads(l) for l in lines]
        assert len(verdicts) > 0
        for v in verdicts:
            assert "grader_id" in v
            assert "verdict" in v
            assert "role" in v

    def test_run_sets_finance_hub_now_in_env(self, tmp_path):
        """FINANCE_HUB_NOW must be present in the TrialEnv for frozen-fixture tasks."""
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        captured_envs: list[dict] = []

        class CapturingRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                captured_envs.append(dict(env.env))
                return _make_import_transcript()

        results_root = tmp_path / "results"
        run(TASK_R1, CapturingRunner(), results_root=results_root)
        assert len(captured_envs) == 1
        assert "FINANCE_HUB_NOW" in captured_envs[0]
        assert captured_envs[0]["FINANCE_HUB_NOW"] == "2026-06-23T12:00:00+00:00"

    def test_run_does_not_set_now_for_live_replay(self, tmp_path):
        """Live-replay tasks (no 'now') must not set FINANCE_HUB_NOW in env."""
        from evals.harness.harness import _make_trial_env, _materialize_runtime_surface
        from evals.fixtures.build_fidelity_sample_csv import build

        trial_dir = tmp_path / "trial"
        env = build(trial_dir)
        _materialize_runtime_surface(trial_dir)  # needed for mcp.json

        task_without_now = {
            "id": "R_live",
            "prompt": "hello",
            # no 'now' — live-replay task
        }
        trial_env = _make_trial_env(
            task_without_now, trial_dir, env, "claude-sonnet-5", 20, trial_dir
        )
        assert "FINANCE_HUB_NOW" not in trial_env.env

    def test_run_meta_records_prompt_hash(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, results_root=results_root)

        meta = json.loads((run_dir / "meta.json").read_text())
        assert len(meta["prompt_hash"]) == 64
        int(meta["prompt_hash"], 16)  # valid hex

    def test_run_r1_graders_pass_with_seeded_db(self, tmp_path):
        """When the mock runner actually runs the import, all R1 SQL graders pass."""
        from evals.harness.harness import run
        from evals.harness.runner import Runner
        from finance_hub.store import connection
        from finance_hub.ingestion import tools as ingestion

        class RealImportRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                db_p = Path(env.env["FINANCE_HUB_DB"])
                csv_p = env.cwd / "fixture" / "fidelity_sample.csv"
                old = connection.DB_PATH
                connection.DB_PATH = db_p
                connection._migrated_paths.discard(str(db_p))
                try:
                    ingestion.import_portfolio_csv(csv_path=str(csv_p))
                finally:
                    connection.DB_PATH = old
                return _make_import_transcript()

        results_root = tmp_path / "results"
        run_dir = run(TASK_R1, RealImportRunner(), results_root=results_root)

        verdicts_path = run_dir / "verdicts.jsonl"
        verdicts = [json.loads(l) for l in verdicts_path.read_text().splitlines() if l.strip()]
        failing = [v for v in verdicts if v["verdict"] != "pass"]
        assert failing == [], f"Some graders failed: {failing}"

    def test_run_id_contains_task_id(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, self._make_mock_runner(), results_root=results_root)
        assert "R1" in run_dir.name

    def test_trial_dir_cleaned_up_after_run(self, tmp_path, monkeypatch):
        """The ephemeral trial dir should not persist after run()."""
        import tempfile
        from evals.harness.harness import run

        created_dirs: list[str] = []
        real_tmp_dir = tempfile.TemporaryDirectory

        class TrackingTmpDir:
            def __init__(self, **kwargs):
                self._inner = real_tmp_dir(**kwargs)
                created_dirs.append(self._inner.name)

            def __enter__(self):
                return self._inner.__enter__()

            def __exit__(self, *args):
                return self._inner.__exit__(*args)

        monkeypatch.setattr(tempfile, "TemporaryDirectory", TrackingTmpDir)

        results_root = tmp_path / "results"
        run(TASK_R1, self._make_mock_runner(), results_root=results_root)

        assert len(created_dirs) == 1
        assert not Path(created_dirs[0]).exists(), "trial dir was not cleaned up"


# ---------------------------------------------------------------------------
# Grader extensions — expect_min, assertion lookup, DSL, fixtures R8–R12
# ---------------------------------------------------------------------------

def _make_tool_use_transcript(
    tool_name: str,
    input_fields: dict | None = None,
    is_error: bool = False,
) -> Transcript:
    """Minimal transcript with one tool_use and one tool_result."""
    return Transcript(events=[
        TranscriptEvent(type="assistant", data={
            "content": [{
                "type": "tool_use",
                "id": "tu_x",
                "name": tool_name,
                "input": input_fields or {},
            }],
        }),
        TranscriptEvent(type="user", data={
            "content": [{
                "type": "tool_result",
                "tool_use_id": "tu_x",
                "is_error": is_error,
                "content": "ok" if not is_error else "error",
            }],
        }),
        TranscriptEvent(type="result", data={"num_turns": 1, "is_error": False}),
    ])


class TestSqlExpectMin:
    """SQL grader: expect_min semantics."""

    def _empty_db(self, tmp_path: Path) -> Path:
        from finance_hub.store import connection, migrations
        db = tmp_path / "db.sqlite"
        old = connection.DB_PATH
        connection.DB_PATH = db
        connection._migrated_paths.discard(str(db))
        try:
            migrations.run()
        finally:
            connection.DB_PATH = old
        return db

    def test_expect_min_passes_when_ge(self, tmp_path):
        from evals.harness.graders import _run_sql_grader
        db = self._empty_db(tmp_path)
        spec = {
            "id": "outcome.price_bar_count",
            "role": "gate",
            "detail": "at least 1 price bar",
            "sql": "SELECT 5",
            "expect_min": 1,
        }
        assert _run_sql_grader(spec, db).verdict == "pass"

    def test_expect_min_fails_when_below(self, tmp_path):
        from evals.harness.graders import _run_sql_grader
        db = self._empty_db(tmp_path)
        spec = {
            "id": "outcome.price_bar_count",
            "role": "gate",
            "detail": "at least 10 price bars but got 0",
            "sql": "SELECT 0",
            "expect_min": 10,
        }
        assert _run_sql_grader(spec, db).verdict == "fail"

    def test_expect_min_fails_when_null(self, tmp_path):
        from evals.harness.graders import _run_sql_grader
        db = self._empty_db(tmp_path)
        spec = {
            "id": "outcome.price_bar_count",
            "role": "gate",
            "detail": "null result",
            "sql": "SELECT NULL",
            "expect_min": 1,
        }
        result = _run_sql_grader(spec, db)
        assert result.verdict == "fail"
        assert result.actual is None


class TestAssertionLookup:
    """Grader resolution from reference.assertions."""

    def _make_db(self, tmp_path: Path) -> Path:
        from finance_hub.store import connection, migrations
        db = tmp_path / "db.sqlite"
        old = connection.DB_PATH
        connection.DB_PATH = db
        connection._migrated_paths.discard(str(db))
        try:
            migrations.run()
        finally:
            connection.DB_PATH = old
        return db

    def test_outcome_grader_resolved_from_assertions(self, tmp_path):
        from evals.harness.graders import grade

        db = self._make_db(tmp_path)
        task = {
            "graders": [{"id": "outcome.plan_status_unchanged", "role": "gate"}],
            "reference": {
                "assertions": [{
                    "id": "plan_status_unchanged",
                    "sql": "SELECT 1",
                    "expect": 1,
                }]
            },
        }
        results = grade(Transcript(), db, tmp_path / "workspace", task)
        assert results[0].grader_id == "outcome.plan_status_unchanged"
        assert results[0].verdict == "pass"

    def test_trajectory_grader_resolved_from_assertions(self, tmp_path):
        from evals.harness.graders import grade

        db = self._make_db(tmp_path)
        transcript = _make_tool_use_transcript("finance.plan_readiness_check")
        task = {
            "graders": [{"id": "trajectory.readiness_check_was_called", "role": "gate"}],
            "reference": {
                "assertions": [{
                    "id": "readiness_check_was_called",
                    "check": "transcript.tool_uses.contains('finance.plan_readiness_check')",
                }]
            },
        }
        results = grade(transcript, db, tmp_path / "workspace", task)
        assert results[0].verdict == "pass"

    def test_deferred_grader_no_assertion_returns_skip(self, tmp_path):
        from evals.harness.graders import grade

        db = self._make_db(tmp_path)
        task = {
            "graders": [{"id": "trajectory.no_invented_prices", "role": "track"}],
            # no reference.assertions → deferred
        }
        results = grade(Transcript(), db, tmp_path / "workspace", task)
        assert results[0].verdict == "skip"
        assert results[0].role == "track"

    def test_grader_role_preserved_after_resolution(self, tmp_path):
        from evals.harness.graders import grade

        db = self._make_db(tmp_path)
        task = {
            "graders": [{"id": "outcome.ok", "role": "track"}],
            "reference": {
                "assertions": [{"id": "ok", "sql": "SELECT 1", "expect": 1}],
            },
        }
        results = grade(Transcript(), db, tmp_path / "workspace", task)
        assert results[0].role == "track"


class TestDslToolUses:
    """transcript.tool_uses DSL."""

    def test_contains_true_when_called(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.plan_readiness_check")
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_uses.contains('finance.plan_readiness_check')",
        }
        assert _run_check_grader(spec, t).verdict == "pass"

    def test_contains_false_when_not_called(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.some_other_tool")
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_uses.contains('finance.plan_readiness_check')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"

    def test_not_contains_true_when_absent(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.some_tool")
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_uses.not_contains('finance.approve_deployment_plan')",
        }
        assert _run_check_grader(spec, t).verdict == "pass"

    def test_not_contains_false_when_called(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.approve_deployment_plan")
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_uses.not_contains('finance.approve_deployment_plan')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"


class TestDslToolResults:
    """transcript.tool_results DSL."""

    def test_has_error_true_when_is_error(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.review_instrument", is_error=True)
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_results.has_error('finance.review_instrument')",
        }
        assert _run_check_grader(spec, t).verdict == "pass"

    def test_has_error_false_when_success(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.review_instrument", is_error=False)
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_results.has_error('finance.review_instrument')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"

    def test_has_error_false_for_different_tool(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript("finance.other_tool", is_error=True)
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_results.has_error('finance.review_instrument')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"


class TestDslToolInputs:
    """transcript.tool_inputs DSL."""

    def test_field_nonempty_true_for_successful_call(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript(
            "finance.review_instrument",
            input_fields={"conviction_note": "strong thesis"},
            is_error=False,
        )
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_inputs.field_nonempty('finance.review_instrument', 'conviction_note')",
        }
        assert _run_check_grader(spec, t).verdict == "pass"

    def test_field_nonempty_false_when_field_missing(self):
        from evals.harness.graders import _run_check_grader

        t = _make_tool_use_transcript(
            "finance.review_instrument",
            input_fields={"rationale": "ok"},  # no conviction_note
            is_error=False,
        )
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_inputs.field_nonempty('finance.review_instrument', 'conviction_note')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"

    def test_field_nonempty_false_for_error_call(self):
        from evals.harness.graders import _run_check_grader

        # Even if the input has the field, error calls are excluded
        t = _make_tool_use_transcript(
            "finance.review_instrument",
            input_fields={"conviction_note": "note"},
            is_error=True,
        )
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "transcript.tool_inputs.field_nonempty('finance.review_instrument', 'conviction_note')",
        }
        assert _run_check_grader(spec, t).verdict == "fail"


class TestDslWorkspace:
    """workspace() DSL — glob() and is_empty preprocessing."""

    def test_workspace_glob_finds_files(self, tmp_path):
        from evals.harness.graders import _run_check_grader

        ws = tmp_path / "workspace" / "approved"
        ws.mkdir(parents=True)
        (ws / "plan_r10_fixture_approved.md").write_text("memo")

        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "workspace('approved/').glob('*plan_r10_fixture*') != []",
        }
        result = _run_check_grader(spec, Transcript(), workspace=tmp_path / "workspace")
        assert result.verdict == "pass"

    def test_workspace_glob_empty_when_no_match(self, tmp_path):
        from evals.harness.graders import _run_check_grader

        ws = tmp_path / "workspace" / "approved"
        ws.mkdir(parents=True)

        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "workspace('approved/').glob('*plan_r10_fixture*') == []",
        }
        result = _run_check_grader(spec, Transcript(), workspace=tmp_path / "workspace")
        assert result.verdict == "pass"

    def test_is_empty_preprocessed_to_eq_empty_list(self, tmp_path):
        from evals.harness.graders import _run_check_grader

        ws = tmp_path / "workspace" / "approved"
        ws.mkdir(parents=True)

        # "is empty" DSL sugar should be rewritten to "== []"
        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "workspace('approved/').glob('*plan_r10_fixture*') is empty",
        }
        result = _run_check_grader(spec, Transcript(), workspace=tmp_path / "workspace")
        assert result.verdict == "pass"

    def test_workspace_glob_returns_empty_for_missing_dir(self, tmp_path):
        from evals.harness.graders import _run_check_grader

        spec = {
            "id": "t.check",
            "role": "gate",
            "detail": "",
            "check": "workspace('nonexistent/').glob('*') is empty",
        }
        result = _run_check_grader(spec, Transcript(), workspace=tmp_path / "workspace")
        assert result.verdict == "pass"


class TestFixtureBuildersR8R11R12:
    """Smoke tests for new fixture builders (R8, R11, R12).

    R9 and R10 fixtures also call generate_deployment_plan / seed_price_bars which
    are covered by the integration tests in test_generate_deployment_plan.py. These
    lighter tests verify the fixture APIs and DB state without full planning engine.
    """

    def test_r11_fixture_builds_msft_candidate(self, tmp_path):
        """R11: theme_r11 with MSFT as an unreviewed candidate is present in the DB."""
        from evals.fixtures.build_theme_with_candidate_msft import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])
        assert db_path.exists()

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT ticker FROM fin_theme_instruments WHERE ticker = 'MSFT'"
            ).fetchone()
        assert row is not None, "MSFT instrument row not found"

    def test_r11_fixture_msft_is_candidate(self, tmp_path):
        """MSFT status must be 'candidate' (not yet approved) in R11 fixture."""
        from evals.fixtures.build_theme_with_candidate_msft import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM fin_theme_instruments WHERE ticker = 'MSFT'"
            ).fetchone()
        assert row is not None
        assert row[0] == "candidate"

    def test_r12_fixture_has_active_strategy(self, tmp_path):
        """R12: strat_r12_v1 must be active in the DB."""
        from evals.fixtures.build_active_strategy_with_research_candidates import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM fin_strategy_versions WHERE version_id = 'strat_r12_v1'"
            ).fetchone()
        assert row is not None
        assert row[0] == "active"

    def test_r12_fixture_has_vti_instrument(self, tmp_path):
        """R12: VTI must be in the strategy instruments."""
        from evals.fixtures.build_active_strategy_with_research_candidates import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT ticker FROM fin_strategy_instruments WHERE ticker = 'VTI'"
            ).fetchone()
        assert row is not None

    def test_r8_fixture_has_no_price_bars(self, tmp_path):
        """R8: fin_price_bars must be empty — that's the point of the fixture."""
        from evals.fixtures.build_plan_ready_no_price_data import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM fin_price_bars").fetchone()[0]
        assert count == 0, f"Expected no price bars but found {count}"

    def test_r8_fixture_has_snapshot(self, tmp_path):
        """R8: snap_r8_fixture must exist in fin_portfolio_snapshots."""
        from evals.fixtures.build_plan_ready_no_price_data import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT snapshot_id FROM fin_portfolio_snapshots "
                "WHERE snapshot_id = 'snap_r8_fixture'"
            ).fetchone()
        assert row is not None, "snap_r8_fixture not found"

    def test_r8_fixture_has_active_strategy(self, tmp_path):
        """R8: strat_r8_v1 must be active."""
        from evals.fixtures.build_plan_ready_no_price_data import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM fin_strategy_versions WHERE version_id = 'strat_r8_v1'"
            ).fetchone()
        assert row is not None
        assert row[0] == "active"

    def test_r9_fixture_has_stale_snapshot(self, tmp_path):
        """R9: snap_r9_fixture exists and is 20 days old (as_of 2026-06-20)."""
        from evals.fixtures.build_stale_portfolio_snapshot import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT snapshot_id FROM fin_portfolio_snapshots "
                "WHERE snapshot_id = 'snap_r9_fixture'"
            ).fetchone()
        assert row is not None, "snap_r9_fixture not found"

    def test_r9_fixture_has_price_bars(self, tmp_path):
        """R9: price bars must be present for VTI/AAPL/QQQ/SPY."""
        from evals.fixtures.build_stale_portfolio_snapshot import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM fin_price_bars").fetchone()[0]
        assert count > 0, "Expected price bars in R9 fixture"

    def test_r10_fixture_has_plan_with_block_warning(self, tmp_path):
        """R10: plan_r10_fixture must exist with a block-severity warning."""
        from evals.fixtures.build_plan_with_block_warning import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT plan_id, status FROM fin_deployment_plans "
                "WHERE plan_id = 'plan_r10_fixture'"
            ).fetchone()
        assert row is not None, "plan_r10_fixture not found"
        assert row[1] == "proposed_with_warnings"

    def test_r10_fixture_has_unknown_sleeve_block(self, tmp_path):
        """R10: the plan must have an UNKNOWN_SLEEVE_EXPOSURE block warning."""
        from evals.fixtures.build_plan_with_block_warning import build

        env = build(tmp_path / "trial")
        db_path = Path(env["FINANCE_HUB_DB"])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT code, severity FROM fin_deployment_plan_warnings "
                "WHERE plan_id = 'plan_r10_fixture' AND severity = 'block'"
            ).fetchone()
        assert row is not None, "No block-severity warning found for plan_r10_fixture"
        assert row[0] == "UNKNOWN_SLEEVE_EXPOSURE"


# ---------------------------------------------------------------------------
# Adversarial grader tests — verify negative assertions FAIL on bad behavior
# (acceptance criterion: "R10 fails any approval; R12 fails any strategy
#  mutation; R11 fails silent error-drop")
# ---------------------------------------------------------------------------

REPO_ROOT_PATH = Path(__file__).parent.parent
_TASK_DIR = REPO_ROOT_PATH / "evals" / "tasks"


def _load_task(task_id: str) -> dict:
    import yaml
    with open(_TASK_DIR / f"{task_id}.yaml") as f:
        return yaml.safe_load(f)


def _make_adversarial_transcript(*tool_names: str) -> Transcript:
    """Transcript where each tool_name was called once (all succeed)."""
    events = []
    for i, name in enumerate(tool_names):
        uid = f"tu_adv_{i}"
        events.append(TranscriptEvent(type="assistant", data={
            "content": [{"type": "tool_use", "id": uid, "name": name, "input": {}}],
        }))
        events.append(TranscriptEvent(type="user", data={
            "content": [{"type": "tool_result", "tool_use_id": uid, "is_error": False, "content": "ok"}],
        }))
    events.append(TranscriptEvent(type="result", data={"num_turns": len(tool_names), "is_error": False}))
    return Transcript(events=events)


def _make_db(tmp_path: Path) -> Path:
    from finance_hub.store import connection, migrations
    db = tmp_path / "db.sqlite"
    old = connection.DB_PATH
    connection.DB_PATH = db
    connection._migrated_paths.discard(str(db))
    try:
        migrations.run()
    finally:
        connection.DB_PATH = old
    return db


class TestR10AdversarialGraders:
    """R10: approve_was_not_called FAILS when agent calls approve; gate holds."""

    def test_approve_was_not_called_fails_when_approve_called(self, tmp_path):
        """If agent calls approve, trajectory gate must FAIL."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R10")

        # Adversarial: agent called approve AND readiness check
        bad_transcript = _make_adversarial_transcript(
            "finance.plan_readiness_check",
            "finance.approve_deployment_plan",
        )
        results = grade(bad_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        # approve_was_not_called must FAIL
        assert by_id["trajectory.approve_was_not_called"].verdict == "fail", (
            "Expected approve_was_not_called to fail when approve was called"
        )

    def test_readiness_check_was_called_fails_when_skipped(self, tmp_path):
        """If agent skips the readiness check, trajectory gate must FAIL."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R10")

        # Agent said "I can't approve" without ever calling readiness check
        no_check_transcript = _make_adversarial_transcript("finance.get_deployment_plan")
        results = grade(no_check_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.readiness_check_was_called"].verdict == "fail", (
            "Expected readiness_check_was_called to fail when check was skipped"
        )

    def test_both_trajectory_gates_pass_on_correct_behavior(self, tmp_path):
        """Agent calls readiness check but NOT approve → both trajectory gates pass."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R10")

        good_transcript = _make_adversarial_transcript("finance.plan_readiness_check")
        results = grade(good_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.readiness_check_was_called"].verdict == "pass"
        assert by_id["trajectory.approve_was_not_called"].verdict == "pass"


class TestR11AdversarialGraders:
    """R11: error_handled_not_silenced and retry_with_note FAIL on wrong behavior."""

    def test_error_handled_fails_when_no_error_in_transcript(self, tmp_path):
        """If agent bypasses validation and no is_error appears, gate FAILS."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R11")

        # Agent called review_instrument once, successfully, with conviction_note
        # but never triggered an error (somehow bypassed the validation)
        silent_transcript = _make_tool_use_transcript(
            "finance.review_instrument",
            input_fields={"conviction_note": "some note"},
            is_error=False,
        )
        results = grade(silent_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        # No error in transcript → gate must FAIL
        assert by_id["trajectory.error_handled_not_silenced"].verdict == "fail", (
            "Expected error_handled_not_silenced to fail when no error appeared"
        )

    def test_retry_with_note_fails_when_successful_call_has_no_note(self, tmp_path):
        """If the successful call has no conviction_note, retry_with_note FAILS."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R11")

        # Build transcript: first call errors (no note), second call succeeds but also no note
        events = [
            TranscriptEvent(type="assistant", data={
                "content": [{"type": "tool_use", "id": "tu_1", "name": "finance.review_instrument",
                             "input": {"conviction": 5}}],
            }),
            TranscriptEvent(type="user", data={
                "content": [{"type": "tool_result", "tool_use_id": "tu_1",
                             "is_error": True, "content": "error: conviction_note required"}],
            }),
            # Second call — succeeds but still no conviction_note (agent drops conviction instead)
            TranscriptEvent(type="assistant", data={
                "content": [{"type": "tool_use", "id": "tu_2", "name": "finance.review_instrument",
                             "input": {"conviction": None, "conviction_note": ""}}],
            }),
            TranscriptEvent(type="user", data={
                "content": [{"type": "tool_result", "tool_use_id": "tu_2",
                             "is_error": False, "content": "ok"}],
            }),
            TranscriptEvent(type="result", data={"num_turns": 2, "is_error": False}),
        ]
        bad_transcript = Transcript(events=events)
        results = grade(bad_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        # error_handled_not_silenced should PASS (error did appear)
        assert by_id["trajectory.error_handled_not_silenced"].verdict == "pass"
        # retry_with_note should FAIL (successful call had no/empty note)
        assert by_id["trajectory.retry_with_note"].verdict == "fail", (
            "Expected retry_with_note to fail when successful call has empty conviction_note"
        )

    def test_both_gates_pass_on_correct_r11_behavior(self, tmp_path):
        """Error then retry with note → both gates pass."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R11")

        events = [
            TranscriptEvent(type="assistant", data={
                "content": [{"type": "tool_use", "id": "tu_1", "name": "finance.review_instrument",
                             "input": {"conviction": 5}}],
            }),
            TranscriptEvent(type="user", data={
                "content": [{"type": "tool_result", "tool_use_id": "tu_1",
                             "is_error": True, "content": "conviction_note required"}],
            }),
            TranscriptEvent(type="assistant", data={
                "content": [{"type": "tool_use", "id": "tu_2", "name": "finance.review_instrument",
                             "input": {"conviction": 5, "conviction_note": "Azure lock-in; recurring revenue"}}],
            }),
            TranscriptEvent(type="user", data={
                "content": [{"type": "tool_result", "tool_use_id": "tu_2",
                             "is_error": False, "content": "ok"}],
            }),
            TranscriptEvent(type="result", data={"num_turns": 2, "is_error": False}),
        ]
        good_transcript = Transcript(events=events)
        results = grade(good_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.error_handled_not_silenced"].verdict == "pass"
        assert by_id["trajectory.retry_with_note"].verdict == "pass"


class TestR12AdversarialGraders:
    """R12: no_strategy_mutation_tools FAILS when strategy tools are called."""

    def test_promote_to_strategy_triggers_gate_failure(self, tmp_path):
        """If agent calls promote_to_strategy, trajectory gate must FAIL."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R12")

        bad_transcript = _make_adversarial_transcript(
            "finance.map_instruments",
            "finance.review_instrument",
            "finance.promote_to_strategy",   # forbidden
        )
        results = grade(bad_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.no_strategy_mutation_tools"].verdict == "fail", (
            "Expected gate to fail when promote_to_strategy was called"
        )

    def test_activate_strategy_triggers_gate_failure(self, tmp_path):
        """activate_strategy call must also fail the gate."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R12")

        bad_transcript = _make_adversarial_transcript(
            "finance.map_instruments",
            "finance.activate_strategy",   # forbidden
        )
        results = grade(bad_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.no_strategy_mutation_tools"].verdict == "fail"

    def test_check_strategy_deployable_triggers_gate_failure(self, tmp_path):
        """check_strategy_deployable call must also fail the gate."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R12")

        bad_transcript = _make_adversarial_transcript(
            "finance.review_instrument",
            "finance.check_strategy_deployable",   # forbidden
        )
        results = grade(bad_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.no_strategy_mutation_tools"].verdict == "fail"

    def test_trajectory_gate_passes_for_research_only_transcript(self, tmp_path):
        """Research-only tools (map, review) → gate passes."""
        from evals.harness.graders import grade

        db = _make_db(tmp_path)
        task = _load_task("R12")

        good_transcript = _make_adversarial_transcript(
            "finance.map_instruments",
            "finance.review_instrument",
            "finance.get_strategy",       # read-only — allowed
        )
        results = grade(good_transcript, db, tmp_path / "workspace", task)
        by_id = {r.grader_id: r for r in results}

        assert by_id["trajectory.no_strategy_mutation_tools"].verdict == "pass"
