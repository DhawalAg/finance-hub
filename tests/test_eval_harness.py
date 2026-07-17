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

    def test_grade_unknown_type_returns_fail(self, tmp_path):
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])
        task = {
            "graders": [{
                "id": "outcome.unknown",
                "role": "gate",
                "detail": "no sql or check",
            }]
        }
        results = grade(Transcript(), db_path, tmp_path / "workspace", task)
        assert results[0].verdict == "fail"


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
