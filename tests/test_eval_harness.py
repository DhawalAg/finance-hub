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

from evals.harness.graders import GraderResult
from evals.harness.runner import Runner, Transcript, TranscriptEvent, TrialEnv

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
                "id": "outcome.some_future_grader",
                "role": "gate",
                "detail": "deferred: no assertion registered yet",
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
        run_dir = run(TASK_R1, runner, k=1, results_root=results_root)
        assert run_dir.is_dir()

    def test_run_writes_meta_json(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, k=1, results_root=results_root)
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
        run_dir = run(TASK_R1, runner, k=1, results_root=results_root)
        transcript_path = run_dir / "trial_0" / "transcript.jsonl"
        assert transcript_path.exists()

        lines = [l for l in transcript_path.read_text().splitlines() if l.strip()]
        assert len(lines) > 0

    def test_run_writes_verdicts_jsonl(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, runner, k=1, results_root=results_root)
        verdicts_path = run_dir / "trial_0" / "verdicts.jsonl"
        assert verdicts_path.exists()

        lines = [l for l in verdicts_path.read_text().splitlines() if l.strip()]
        verdicts = [json.loads(l) for l in lines]
        assert len(verdicts) > 0
        for v in verdicts:
            assert "grader_id" in v
            assert "verdict" in v
            assert "role" in v

    def test_run_verdicts_have_graded_at(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        run_dir = run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)
        verdicts_path = run_dir / "trial_0" / "verdicts.jsonl"
        for line in verdicts_path.read_text().splitlines():
            if line.strip():
                v = json.loads(line)
                assert "graded_at" in v

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
        run(TASK_R1, CapturingRunner(), k=1, results_root=results_root)
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
        run_dir = run(TASK_R1, runner, k=1, results_root=results_root)

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
        run_dir = run(TASK_R1, RealImportRunner(), k=1, results_root=results_root)

        verdicts_path = run_dir / "trial_0" / "verdicts.jsonl"
        verdicts = [json.loads(l) for l in verdicts_path.read_text().splitlines() if l.strip()]
        failing = [v for v in verdicts if v["verdict"] != "pass"]
        assert failing == [], f"Some graders failed: {failing}"

    def test_run_id_contains_task_id(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        runner = self._make_mock_runner()
        run_dir = run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)
        assert "R1" in run_dir.name

    def test_trial_dir_cleaned_up_after_run(self, tmp_path, monkeypatch):
        """All k ephemeral trial dirs should be cleaned up after run()."""
        import tempfile
        from evals.harness.harness import run

        created_dirs: list[str] = []
        real_tmp_dir = tempfile.TemporaryDirectory

        class TrackingTmpDir:
            def __init__(self, **kwargs):
                self._inner = real_tmp_dir(**kwargs)
                created_dirs.append(self._inner.name)

            @property
            def name(self):
                return self._inner.name

            def cleanup(self):
                self._inner.cleanup()

        monkeypatch.setattr(tempfile, "TemporaryDirectory", TrackingTmpDir)

        results_root = tmp_path / "results"
        run(TASK_R1, self._make_mock_runner(), k=2, results_root=results_root)

        assert len(created_dirs) == 2, f"Expected 2 trial dirs, got {len(created_dirs)}"
        for d in created_dirs:
            assert not Path(d).exists(), f"trial dir {d} was not cleaned up"


# ---------------------------------------------------------------------------
# Fixture builders R2-R7: unit tests
# ---------------------------------------------------------------------------

TASK_R2 = REPO_ROOT / "evals" / "tasks" / "R2.yaml"
TASK_R3 = REPO_ROOT / "evals" / "tasks" / "R3.yaml"
TASK_R4 = REPO_ROOT / "evals" / "tasks" / "R4.yaml"
TASK_R5 = REPO_ROOT / "evals" / "tasks" / "R5.yaml"
TASK_R6 = REPO_ROOT / "evals" / "tasks" / "R6.yaml"
TASK_R7 = REPO_ROOT / "evals" / "tasks" / "R7.yaml"


class TestFixtureBuildersR2R7:
    """Basic contracts for each new fixture builder."""

    def _common_assertions(self, env: dict, tmp_path: Path) -> None:
        assert "FINANCE_HUB_DB" in env
        assert "FINANCE_HUB_WORKSPACE" in env
        db_path = Path(env["FINANCE_HUB_DB"])
        workspace = Path(env["FINANCE_HUB_WORKSPACE"])
        assert db_path.exists()
        assert workspace.is_dir()
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "fin_portfolio_snapshots" in tables
        assert "fin_themes" in tables

    def test_r2_builds_empty_db(self, tmp_path):
        from evals.fixtures.build_dividend_growth_empty import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            count = conn.execute("SELECT COUNT(*) FROM fin_themes").fetchone()[0]
        assert count == 0

    def test_r2_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_dividend_growth_empty import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original

    def test_r3_builds_db_with_aapl_candidate(self, tmp_path):
        from evals.fixtures.build_instrument_candidate_aapl import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            row = conn.execute(
                "SELECT status FROM fin_theme_instruments "
                "WHERE theme_key='theme_r3' AND ticker='AAPL'"
            ).fetchone()
        assert row is not None
        assert row[0] == "candidate"
        assert (Path(env["FINANCE_HUB_WORKSPACE"]) / "research" / "instruments").is_dir()

    def test_r3_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_instrument_candidate_aapl import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original

    def test_r4_builds_db_with_approved_candidates(self, tmp_path):
        from evals.fixtures.build_approved_candidates_ready_for_promotion import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fin_theme_instruments "
                "WHERE theme_key='theme_r4' AND status='approved'"
            ).fetchone()[0]
        assert count == 3

    def test_r4_aapl_thesis_written_to_workspace(self, tmp_path):
        from evals.fixtures.build_approved_candidates_ready_for_promotion import build
        env = build(tmp_path)
        note = Path(env["FINANCE_HUB_WORKSPACE"]) / "research" / "instruments" / "AAPL.md"
        assert note.exists()
        assert note.stat().st_size >= 200

    def test_r4_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_approved_candidates_ready_for_promotion import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original

    def test_r5_builds_db_with_snapshot_and_strategy(self, tmp_path):
        from evals.fixtures.build_dca_ready_deployment import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            snap = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_snapshots "
                "WHERE snapshot_id='snap_r5_fixture'"
            ).fetchone()[0]
            strat = conn.execute(
                "SELECT status FROM fin_strategy_versions WHERE version_id='strat_r5_v1'"
            ).fetchone()
            bars = conn.execute(
                "SELECT COUNT(DISTINCT ticker) FROM fin_price_bars"
            ).fetchone()[0]
        assert snap == 1
        assert strat is not None and strat[0] == "active"
        assert bars >= 3

    def test_r5_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_dca_ready_deployment import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original

    def test_r6_builds_db_with_proposed_plan(self, tmp_path):
        from evals.fixtures.build_proposed_plan_ready_for_approval import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            row = conn.execute(
                "SELECT status FROM fin_deployment_plans WHERE plan_id='plan_r6_fixture'"
            ).fetchone()
        assert row is not None
        # concentration warnings may push status to proposed_with_warnings — both are approvable
        assert row[0] in ("proposed", "proposed_with_warnings")

    def test_r6_approved_dir_starts_empty(self, tmp_path):
        from evals.fixtures.build_proposed_plan_ready_for_approval import build
        env = build(tmp_path)
        approved_dir = Path(env["FINANCE_HUB_WORKSPACE"]) / "approved"
        assert approved_dir.is_dir()
        assert not list(approved_dir.glob("*.md")), "approved/ must start empty"

    def test_r6_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_proposed_plan_ready_for_approval import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original

    def test_r7_builds_db_with_candidates_and_price_bars(self, tmp_path):
        from evals.fixtures.build_chain_quickstart import build
        env = build(tmp_path)
        self._common_assertions(env, tmp_path)
        import sqlite3
        with sqlite3.connect(Path(env["FINANCE_HUB_DB"])) as conn:
            cands = conn.execute(
                "SELECT COUNT(*) FROM fin_theme_instruments "
                "WHERE theme_key='theme_chain' AND status='candidate'"
            ).fetchone()[0]
            bars = conn.execute(
                "SELECT COUNT(DISTINCT ticker) FROM fin_price_bars"
            ).fetchone()[0]
            snap = conn.execute(
                "SELECT COUNT(*) FROM fin_portfolio_snapshots"
            ).fetchone()[0]
        assert cands == 3
        assert bars >= 3
        assert snap == 0  # no snapshot — agent imports it

    def test_r7_csv_file_present(self, tmp_path):
        from evals.fixtures.build_chain_quickstart import build
        env = build(tmp_path)
        csv_path = tmp_path / "fixture" / "fidelity_sample.csv"
        assert csv_path.exists()

    def test_r7_does_not_mutate_connection_db_path(self, tmp_path):
        from finance_hub.store import connection
        from evals.fixtures.build_chain_quickstart import build
        original = connection.DB_PATH
        build(tmp_path)
        assert connection.DB_PATH == original


# ---------------------------------------------------------------------------
# Grader check-expression validation: ensure no invalid Python in check fields
# ---------------------------------------------------------------------------

class TestGraderCheckExpressionsR2R7:
    """Verify the fixed check expressions evaluate without SyntaxError/NameError."""

    def _empty_transcript(self):
        return Transcript(events=[
            TranscriptEvent(type="result", data={"num_turns": 0, "is_error": False}),
        ])

    def _run(self, check_expr: str, workspace=None) -> str:
        from evals.harness.graders import _run_check_grader
        import tempfile
        ws = Path(tempfile.mkdtemp()) if workspace is None else workspace
        spec = {"id": "test.check", "role": "gate", "check": check_expr}
        result = _run_check_grader(spec, self._empty_transcript(), ws)
        return result.verdict

    def test_r5_memo_artifact_check_is_valid_python(self, tmp_path):
        verdict = self._run("bool(workspace('drafts/').glob('*.md'))", tmp_path)
        assert verdict in ("pass", "fail"), "should evaluate without error"

    def test_r5_memo_artifact_check_passes_when_file_present(self, tmp_path):
        (tmp_path / "drafts").mkdir()
        (tmp_path / "drafts" / "plan_draft.md").write_text("content")
        verdict = self._run("bool(workspace('drafts/').glob('*.md'))", tmp_path)
        assert verdict == "pass"

    def test_r5_memo_artifact_check_fails_when_empty(self, tmp_path):
        (tmp_path / "drafts").mkdir()
        verdict = self._run("bool(workspace('drafts/').glob('*.md'))", tmp_path)
        assert verdict == "fail"

    def test_r6_approved_memo_check_is_valid_python(self, tmp_path):
        verdict = self._run("bool(workspace('approved/').glob('*plan_r6_fixture*'))", tmp_path)
        assert verdict in ("pass", "fail")

    def test_r7_approved_memo_check_is_valid_python(self, tmp_path):
        verdict = self._run("bool(workspace('approved/').glob('*.md'))", tmp_path)
        assert verdict in ("pass", "fail")

    def test_r4_trajectory_promote_check_is_valid_python(self):
        from evals.harness.graders import _run_check_grader
        spec = {
            "id": "trajectory.promotion_tool_used",
            "role": "gate",
            "check": "tool_called('finance.promote_to_strategy') and tool_input('finance.promote_to_strategy', 'confirm') == True",
        }
        result = _run_check_grader(spec, self._empty_transcript())
        assert result.verdict == "fail"  # tool not in empty transcript

    def test_r6_readiness_check_before_approve_is_valid_python(self):
        from evals.harness.graders import _run_check_grader
        spec = {
            "id": "trajectory.readiness_check_called",
            "role": "gate",
            "check": "tool_call_before('finance.plan_readiness_check', 'finance.approve_deployment_plan')",
        }
        result = _run_check_grader(spec, self._empty_transcript())
        assert result.verdict == "fail"

    def test_r6_approve_with_confirm_check_is_valid_python(self):
        from evals.harness.graders import _run_check_grader
        spec = {
            "id": "trajectory.approve_called_with_confirm",
            "role": "gate",
            "check": "tool_called('finance.approve_deployment_plan') and tool_input('finance.approve_deployment_plan', 'confirm') == True",
        }
        result = _run_check_grader(spec, self._empty_transcript())
        assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Integration tests: harness.run() with real tool calls — all graders pass
# ---------------------------------------------------------------------------

import os
from datetime import datetime, timezone


def _runner_env_ctx(env):
    """Return a context manager that sets process globals for mock runners."""
    from evals.fixtures._common import seed_context
    from pathlib import Path
    db_p = Path(env.env["FINANCE_HUB_DB"])
    ws_p = Path(env.env["FINANCE_HUB_WORKSPACE"])
    now_str = env.env.get("FINANCE_HUB_NOW", "2026-06-23T12:00:00+00:00")
    clock_dt = datetime.fromisoformat(now_str)
    return seed_context(db_p, ws_p, clock_dt)


def _tool_use_event(tool_id: str, tool_name: str, input_dict: dict) -> TranscriptEvent:
    return TranscriptEvent(type="assistant", data={
        "content": [{"type": "tool_use", "id": tool_id, "name": tool_name, "input": input_dict}],
    })


def _result_event() -> TranscriptEvent:
    return TranscriptEvent(type="result", data={"num_turns": 1, "is_error": False})


class TestHarnessRunR2:
    def test_r2_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        class R2Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.research import tools as research
                    research.set_theme(
                        key="theme_r2", display_name="Dividend Growth", status="watching",
                        description="Income-generating dividend growth.",
                    )
                    research.map_instruments(
                        theme_key="theme_r2",
                        instruments=[
                            {"ticker": "JNJ", "type": "stock", "instrument_role": "single_stock"},
                            {"ticker": "PG",  "type": "stock", "instrument_role": "single_stock"},
                            {"ticker": "KO",  "type": "stock", "instrument_role": "single_stock"},
                        ],
                    )
                    for ticker, conviction, note, rationale in [
                        ("JNJ", 4, "Strong dividend history; Kenvue spin-off removes liability overhang",
                         "Healthcare giant with 60+ year dividend growth track record."),
                        ("PG",  4, "Best-in-class brand portfolio; 67-year dividend growth streak",
                         "Consumer staples fortress with global distribution."),
                        ("KO",  3, "Buffett core holding; franchise network is wide-moat",
                         "Global beverage network with decades of dividend compounding."),
                    ]:
                        research.review_instrument(
                            theme_key="theme_r2", ticker=ticker, status="approved",
                            rationale=rationale, conviction=conviction, conviction_note=note,
                        )
                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.set_theme", {"key": "theme_r2"}),
                    _tool_use_event("tu_2", "finance.map_instruments", {"theme_key": "theme_r2"}),
                    _tool_use_event("tu_3", "finance.review_instrument", {"theme_key": "theme_r2", "ticker": "JNJ"}),
                    _tool_use_event("tu_4", "finance.review_instrument", {"theme_key": "theme_r2", "ticker": "PG"}),
                    _tool_use_event("tu_5", "finance.review_instrument", {"theme_key": "theme_r2", "ticker": "KO"}),
                    _result_event(),
                ])

        run_dir = run(TASK_R2, R2Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R2: {failing}"


class TestHarnessRunR3:
    def test_r3_graders_pass(self, tmp_path, monkeypatch):
        from evals.harness import graders as graders_mod
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        _THESIS = "# AAPL Thesis\n\n" + ("Apple is a great company. " * 20)
        _STUB_JUDGE = '{"groundedness": {"score": 4, "justification": "ok"}, "coverage": {"score": 4, "justification": "ok"}, "source_quality": {"score": 4, "justification": "ok"}}'
        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: _STUB_JUDGE)

        class R3Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.research import tools as research
                    s1 = research.upsert_source(
                        url="https://example.com/aapl-1", title="AAPL Annual Report"
                    )
                    research.link_source(source_id=s1["id"], scope="instrument", key="AAPL")
                    s2 = research.upsert_source(
                        url="https://example.com/aapl-2", title="AAPL Yahoo Finance"
                    )
                    research.link_source(source_id=s2["id"], scope="instrument", key="AAPL")
                    research.set_research_note(scope="instrument", key="AAPL", body=_THESIS)
                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.upsert_source", {"url": "https://example.com/aapl-1"}),
                    _tool_use_event("tu_2", "finance.link_source", {"scope": "instrument", "key": "AAPL"}),
                    _tool_use_event("tu_3", "finance.upsert_source", {"url": "https://example.com/aapl-2"}),
                    _tool_use_event("tu_4", "finance.link_source", {"scope": "instrument", "key": "AAPL"}),
                    _tool_use_event("tu_5", "finance.set_research_note", {"scope": "instrument", "key": "AAPL"}),
                    _result_event(),
                ])

        run_dir = run(TASK_R3, R3Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R3: {failing}"


class TestHarnessRunR4:
    def test_r4_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        class R4Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.strategy import tools as strategy
                    strategy.promote_to_strategy(
                        version_id="strat_r4_v1",
                        label="Core Equities v1",
                        confirm=True,
                        sleeves=[
                            {"sleeve_key": "broad_market", "target_weight_pct": 70},
                            {"sleeve_key": "single_stock", "target_weight_pct": 30},
                        ],
                        instruments=[
                            {"ticker": "VTI", "primary_sleeve_key": "broad_market", "source_theme_key": "theme_r4"},
                            {"ticker": "QQQ", "primary_sleeve_key": "broad_market", "source_theme_key": "theme_r4"},
                            {"ticker": "AAPL", "primary_sleeve_key": "single_stock", "source_theme_key": "theme_r4"},
                        ],
                    )
                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.promote_to_strategy", {
                        "version_id": "strat_r4_v1", "confirm": True,
                        "sleeves": [], "instruments": [],
                    }),
                    _result_event(),
                ])

        run_dir = run(TASK_R4, R4Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R4: {failing}"


class TestHarnessRunR5:
    def test_r5_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        class R5Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.strategy import tools as strategy
                    strategy.generate_deployment_plan(
                        portfolio_snapshot_id="snap_r5_fixture",
                        strategy_version_id="strat_r5_v1",
                        deployable_cash="1000",
                        dca_budget="1000",
                        one_time_buy_budget="0",
                    )
                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.generate_deployment_plan", {
                        "portfolio_snapshot_id": "snap_r5_fixture",
                        "strategy_version_id": "strat_r5_v1",
                        "deployable_cash": "1000",
                    }),
                    _result_event(),
                ])

        run_dir = run(TASK_R5, R5Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R5: {failing}"


class TestHarnessRunR6:
    def test_r6_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        class R6Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.strategy import tools as strategy
                    strategy.plan_readiness_check(plan_id="plan_r6_fixture")
                    strategy.approve_deployment_plan(plan_id="plan_r6_fixture", confirm=True)
                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.plan_readiness_check", {"plan_id": "plan_r6_fixture"}),
                    _tool_use_event("tu_2", "finance.approve_deployment_plan", {
                        "plan_id": "plan_r6_fixture", "confirm": True,
                    }),
                    _result_event(),
                ])

        run_dir = run(TASK_R6, R6Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R6: {failing}"


class TestHarnessRunR7:
    def test_r7_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        class R7Runner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                with _runner_env_ctx(env):
                    from finance_hub.ingestion import tools as ingestion
                    from finance_hub.research import tools as research
                    from finance_hub.strategy import tools as strategy

                    # Step 1: import CSV
                    result = ingestion.import_portfolio_csv(
                        csv_path=str(Path(env.env["FINANCE_HUB_WORKSPACE"]).parent / "fixture" / "fidelity_sample.csv")
                    )
                    snapshot_id = result["snapshot_id"]

                    # Step 2: approve candidates
                    for ticker, conviction, note in [
                        ("VTI",  4, "Core broad-market holding for DCA spine"),
                        ("QQQ",  3, "Tech-weighted complement to VTI"),
                        ("AAPL", 3, "Quality single-stock allocation"),
                    ]:
                        research.review_instrument(
                            theme_key="theme_chain", ticker=ticker, status="approved",
                            rationale=f"{ticker} approved for chain", conviction=conviction,
                            conviction_note=note,
                        )

                    # Step 3: promote to active strategy
                    strategy.promote_to_strategy(
                        version_id="strat_chain_v1",
                        label="Chain v1",
                        status="active",
                        confirm=True,
                        sleeves=[
                            {"sleeve_key": "broad_market", "target_weight_pct": 70},
                            {"sleeve_key": "single_stock", "target_weight_pct": 30},
                        ],
                        instruments=[
                            {"ticker": "VTI",  "primary_sleeve_key": "broad_market", "source_theme_key": "theme_chain"},
                            {"ticker": "QQQ",  "primary_sleeve_key": "broad_market", "source_theme_key": "theme_chain"},
                            {"ticker": "AAPL", "primary_sleeve_key": "single_stock", "source_theme_key": "theme_chain"},
                        ],
                    )

                    # Step 4: generate plan
                    plan = strategy.generate_deployment_plan(
                        portfolio_snapshot_id=snapshot_id,
                        strategy_version_id="strat_chain_v1",
                        deployable_cash="1000",
                        dca_budget="1000",
                        one_time_buy_budget="0",
                    )
                    plan_id = plan["plan_id"]

                    # Step 5: readiness check then approve
                    strategy.plan_readiness_check(plan_id=plan_id)
                    strategy.approve_deployment_plan(plan_id=plan_id, confirm=True)

                return Transcript(events=[
                    _tool_use_event("tu_1", "finance.import_portfolio_csv",
                                    {"csv_path": "fixture/fidelity_sample.csv"}),
                    _tool_use_event("tu_2", "finance.review_instrument",
                                    {"theme_key": "theme_chain", "ticker": "VTI"}),
                    _tool_use_event("tu_3", "finance.review_instrument",
                                    {"theme_key": "theme_chain", "ticker": "QQQ"}),
                    _tool_use_event("tu_4", "finance.review_instrument",
                                    {"theme_key": "theme_chain", "ticker": "AAPL"}),
                    _tool_use_event("tu_5", "finance.promote_to_strategy",
                                    {"version_id": "strat_chain_v1", "confirm": True}),
                    _tool_use_event("tu_6", "finance.generate_deployment_plan", {}),
                    _tool_use_event("tu_7", "finance.plan_readiness_check", {"plan_id": "plan_id"}),
                    _tool_use_event("tu_8", "finance.approve_deployment_plan",
                                    {"plan_id": "plan_id", "confirm": True}),
                    _result_event(),
                ])

        run_dir = run(TASK_R7, R7Runner(), results_root=tmp_path / "results")
        import json
        verdicts = [json.loads(l) for l in (run_dir / "trial_0" / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R7: {failing}"


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

    def test_built_in_trajectory_grader_runs_without_assertion(self, tmp_path):
        # Known trajectory handlers (issue #45) run even without reference.assertions.
        from evals.harness.graders import grade

        db = self._make_db(tmp_path)
        task = {
            "graders": [{"id": "trajectory.no_invented_prices", "role": "track"}],
            # no reference.assertions — built-in handler runs directly
        }
        results = grade(Transcript(), db, tmp_path / "workspace", task)
        # Empty transcript has no financial numbers → passes groundedness check
        assert results[0].verdict == "pass"
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


# ---------------------------------------------------------------------------
# k-trial support: concurrent trials + pass^k / pass@k
# ---------------------------------------------------------------------------

class TestHarnessKTrials:
    """k=3 concurrent trials, run dir layout, pass^k/pass@k composition."""

    def _make_mock_runner(self) -> Runner:
        class MockRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                return _make_import_transcript()
        return MockRunner()

    def test_run_k1_creates_trial_0(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        assert (run_dir / "trial_0").is_dir()
        assert (run_dir / "trial_0" / "transcript.jsonl").exists()
        assert (run_dir / "trial_0" / "verdicts.jsonl").exists()

    def test_run_k3_creates_three_trial_dirs(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=3,
                      results_root=tmp_path / "results")
        for i in range(3):
            assert (run_dir / f"trial_{i}").is_dir(), f"trial_{i} missing"
            assert (run_dir / f"trial_{i}" / "transcript.jsonl").exists()
            assert (run_dir / f"trial_{i}" / "verdicts.jsonl").exists()

    def test_meta_k_field(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=3,
                      results_root=tmp_path / "results")
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["k"] == 3

    def test_meta_has_pass_k_and_pass_at_k(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        meta = json.loads((run_dir / "meta.json").read_text())
        assert "pass_k" in meta
        assert "pass_at_k" in meta
        assert isinstance(meta["pass_k"], bool)
        assert isinstance(meta["pass_at_k"], bool)

    def test_meta_trials_array(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=2,
                      results_root=tmp_path / "results")
        meta = json.loads((run_dir / "meta.json").read_text())
        assert "trials" in meta
        assert len(meta["trials"]) == 2
        for t in meta["trials"]:
            assert "trial_idx" in t
            assert "gate_pass" in t

    def test_each_trial_has_own_transcript(self, tmp_path):
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=2,
                      results_root=tmp_path / "results")
        for i in range(2):
            t = run_dir / f"trial_{i}" / "transcript.jsonl"
            lines = [l for l in t.read_text().splitlines() if l.strip()]
            assert len(lines) > 0, f"trial_{i} transcript is empty"

    def test_pass_k_true_when_all_gate_pass(self):
        from evals.harness.harness import _compute_pass_k
        from evals.harness.graders import GraderResult

        all_verdicts = [
            [GraderResult("g1", "gate", "pass", "")],
            [GraderResult("g1", "gate", "pass", "")],
            [GraderResult("g1", "gate", "pass", "")],
        ]
        assert _compute_pass_k(all_verdicts) is True

    def test_pass_k_false_when_any_fail(self):
        from evals.harness.harness import _compute_pass_k
        from evals.harness.graders import GraderResult

        all_verdicts = [
            [GraderResult("g1", "gate", "pass", "")],
            [GraderResult("g1", "gate", "fail", "")],
            [GraderResult("g1", "gate", "pass", "")],
        ]
        assert _compute_pass_k(all_verdicts) is False

    def test_pass_at_k_true_when_one_passes(self):
        from evals.harness.harness import _compute_pass_at_k
        from evals.harness.graders import GraderResult

        all_verdicts = [
            [GraderResult("g1", "gate", "fail", "")],
            [GraderResult("g1", "gate", "pass", "")],
            [GraderResult("g1", "gate", "fail", "")],
        ]
        assert _compute_pass_at_k(all_verdicts) is True

    def test_pass_at_k_false_when_all_fail(self):
        from evals.harness.harness import _compute_pass_at_k
        from evals.harness.graders import GraderResult

        all_verdicts = [
            [GraderResult("g1", "gate", "fail", "")],
            [GraderResult("g1", "gate", "fail", "")],
        ]
        assert _compute_pass_at_k(all_verdicts) is False

    def test_regression_policy_is_pass_k(self, tmp_path):
        """Regression suite should show pass^k verdict in meta."""
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["suite"] == "regression"

    def test_k3_trials_run_concurrently_independent(self, tmp_path):
        """k=3 trials complete successfully with independent transcripts."""
        from evals.harness.harness import run

        run_dir = run(TASK_R1, self._make_mock_runner(), k=3,
                      results_root=tmp_path / "results")
        for i in range(3):
            lines = [
                l for l in (run_dir / f"trial_{i}" / "transcript.jsonl")
                .read_text().splitlines() if l.strip()
            ]
            assert len(lines) > 0, f"trial_{i} transcript empty"


# ---------------------------------------------------------------------------
# Re-grading: graders re-run against stored transcripts
# ---------------------------------------------------------------------------

class TestHarnessRegrade:
    """regrade() re-runs graders, appends to verdicts.jsonl (spec §9 req 5)."""

    def _make_mock_runner(self) -> Runner:
        class MockRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                return _make_import_transcript()
        return MockRunner()

    def test_regrade_appends_rows_to_verdicts_jsonl(self, tmp_path):
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        verdicts_path = run_dir / "trial_0" / "verdicts.jsonl"
        initial_count = sum(1 for l in verdicts_path.read_text().splitlines() if l.strip())

        regrade(run_dir, TASK_R1)

        after_count = sum(1 for l in verdicts_path.read_text().splitlines() if l.strip())
        assert after_count > initial_count

    def test_regrade_returns_verdicts_per_trial(self, tmp_path):
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=2,
                      results_root=tmp_path / "results")
        results = regrade(run_dir, TASK_R1)
        assert len(results) == 2
        for trial_verdicts in results:
            assert isinstance(trial_verdicts, list)

    def test_regrade_check_graders_run_from_transcript(self, tmp_path):
        """check graders re-run even without a db_path (transcript-only)."""
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        results = regrade(run_dir, TASK_R1)

        check_results = [
            v for v in results[0]
            if v.verdict in ("pass", "fail")
        ]
        assert len(check_results) > 0

    def test_regrade_sql_graders_skip_without_db_path(self, tmp_path):
        """sql graders return 'skip' when no db_path provided."""
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        results = regrade(run_dir, TASK_R1)  # no db_paths

        sql_skipped = [v for v in results[0] if v.verdict == "skip"]
        # R1 has sql graders — they should be skipped without a db_path
        assert len(sql_skipped) > 0

    def test_regrade_verdicts_have_graded_at(self, tmp_path):
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        results = regrade(run_dir, TASK_R1)

        for v in results[0]:
            assert v.graded_at is not None

    def test_regrade_multiple_passes_keep_accumulating(self, tmp_path):
        """Multiple regrade calls keep appending; initial rows are never overwritten."""
        from evals.harness.harness import run, regrade

        run_dir = run(TASK_R1, self._make_mock_runner(), k=1,
                      results_root=tmp_path / "results")
        verdicts_path = run_dir / "trial_0" / "verdicts.jsonl"
        initial = sum(1 for l in verdicts_path.read_text().splitlines() if l.strip())

        regrade(run_dir, TASK_R1)
        after_one = sum(1 for l in verdicts_path.read_text().splitlines() if l.strip())

        regrade(run_dir, TASK_R1)
        after_two = sum(1 for l in verdicts_path.read_text().splitlines() if l.strip())

        assert after_one > initial
        assert after_two > after_one


# ---------------------------------------------------------------------------
# Suite report
# ---------------------------------------------------------------------------

class TestEmitSuiteReport:
    """emit_suite_report reads run dirs and prints aggregated summary."""

    def _make_mock_runner(self) -> Runner:
        class MockRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                return _make_import_transcript()
        return MockRunner()

    def test_emit_suite_report_no_results(self, tmp_path, capsys):
        from evals.harness.harness import emit_suite_report

        emit_suite_report(tmp_path / "empty_results")
        out = capsys.readouterr().out
        assert "No results" in out

    def test_emit_suite_report_shows_task_row(self, tmp_path, capsys):
        from evals.harness.harness import run, emit_suite_report

        results_root = tmp_path / "results"
        run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        assert "R1" in out

    def test_emit_suite_report_shows_pass_k(self, tmp_path, capsys):
        from evals.harness.harness import run, emit_suite_report

        results_root = tmp_path / "results"
        run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        assert "pass^k" in out.lower() or "PASS" in out or "FAIL" in out


# ---------------------------------------------------------------------------
# LLM-judge grader (issue #47)
# ---------------------------------------------------------------------------

_JUDGE_TASK_R3 = Path(__file__).parent.parent / "evals" / "tasks" / "R3.yaml"

_JUDGE_SPEC = {
    "id": "judge.thesis_quality",
    "role": "flag",
    "judge_model": "claude-sonnet-5",
    "rubric": "rubrics/thesis_quality_v1.yaml",
    "rubric_version": "1",
    "dimensions": ["groundedness", "coverage", "source_quality"],
    "coverage_key_facts": ["fact A", "fact B"],
    "flag_threshold": "any dimension score < 3/5",
}

_FAKE_JUDGE_RESPONSE = """{
    "groundedness": {"score": 4, "justification": "Most claims cited; minor gaps."},
    "coverage": {"score": 3, "justification": "Core topics addressed adequately."},
    "source_quality": {"score": 5, "justification": "All authoritative sources."}
}"""

_FAKE_JUDGE_RESPONSE_LOW = """{
    "groundedness": {"score": 2, "justification": "Several uncited claims."},
    "coverage": {"score": 1, "justification": "Major topics missing."},
    "source_quality": {"score": 3, "justification": "Mixed quality sources."}
}"""


def _make_gate_passing_results():
    """Return a list of gate GraderResults that all pass."""
    return [
        GraderResult("outcome.a", "gate", "pass", ""),
        GraderResult("outcome.b", "gate", "pass", ""),
    ]


def _make_gate_failing_results():
    """Return a list where one gate grader failed."""
    return [
        GraderResult("outcome.a", "gate", "pass", ""),
        GraderResult("outcome.b", "gate", "fail", ""),
    ]


class TestJudgeGrader:
    """LLM-judge grader: per-dimension rows, versioned rubric, flag-not-gate, gate-conditional."""

    def _grade_with_judge(self, tmp_path, monkeypatch, judge_response, gates_pass=True):
        """Helper: run grade() with one judge grader, mocked judge, optional gate."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: judge_response)

        gate_verdict = "pass" if gates_pass else "fail"
        task = {
            "graders": [
                {"id": "outcome.gate1", "role": "gate",
                 "sql": "SELECT 1", "expect": 1 if gates_pass else 0},
                _JUDGE_SPEC,
            ]
        }
        db = tmp_path / "test.db"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
        return grade(Transcript(), db, tmp_path, task)

    def test_judge_skips_when_a_gate_fails(self, tmp_path, monkeypatch):
        """Judge grader returns skip verdicts when any gate grader fails."""
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE, gates_pass=False)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == len(_JUDGE_SPEC["dimensions"])
        assert all(r.verdict == "skip" for r in judge_results), (
            f"Expected all judge results to be 'skip', got: {[r.verdict for r in judge_results]}"
        )

    def test_judge_emits_per_dimension_rows_when_gates_pass(self, tmp_path, monkeypatch):
        """Judge returns one GraderResult per dimension when gates pass."""
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE, gates_pass=True)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == 3
        assert {r.grader_id for r in judge_results} == {
            "judge.thesis_quality.groundedness",
            "judge.thesis_quality.coverage",
            "judge.thesis_quality.source_quality",
        }

    def test_judge_rows_record_rubric_and_judge_version(self, tmp_path, monkeypatch):
        """Each dimension row's actual dict includes rubric_version and judge_version."""
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE, gates_pass=True)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        for r in judge_results:
            assert isinstance(r.actual, dict), f"actual should be dict, got {type(r.actual)}"
            assert r.actual.get("rubric_version") == "1", f"rubric_version missing in {r.actual}"
            assert r.actual.get("judge_version") == "claude-sonnet-5", f"judge_version missing in {r.actual}"

    def test_judge_above_threshold_verdict_is_pass(self, tmp_path, monkeypatch):
        """Dimension score >= flag_below threshold → verdict='pass'."""
        # All scores in _FAKE_JUDGE_RESPONSE are >= 3
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE, gates_pass=True)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert all(r.verdict == "pass" for r in judge_results), (
            f"All scores >= 3 should pass, got: {[(r.grader_id, r.verdict, r.actual) for r in judge_results]}"
        )

    def test_judge_below_threshold_verdict_is_fail(self, tmp_path, monkeypatch):
        """Dimension score < flag_below threshold → verdict='fail'."""
        # _FAKE_JUDGE_RESPONSE_LOW has scores 2, 1, 3
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE_LOW, gates_pass=True)
        judge_results = {r.grader_id: r for r in results if r.grader_id.startswith("judge.")}
        assert judge_results["judge.thesis_quality.groundedness"].verdict == "fail"
        assert judge_results["judge.thesis_quality.coverage"].verdict == "fail"
        assert judge_results["judge.thesis_quality.source_quality"].verdict == "pass"

    def test_judge_role_is_always_flag(self, tmp_path, monkeypatch):
        """Judge grader rows always have role='flag', never 'gate'."""
        results = self._grade_with_judge(tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE, gates_pass=True)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert all(r.role == "flag" for r in judge_results), (
            f"Judge rows should have role=flag, got: {[(r.grader_id, r.role) for r in judge_results]}"
        )

    def test_judge_fail_does_not_affect_gate_pass(self, tmp_path, monkeypatch):
        """A failed judge verdict (role=flag) does not count against gate pass."""
        from evals.harness.graders import compose_verdict
        results = self._grade_with_judge(
            tmp_path, monkeypatch, _FAKE_JUDGE_RESPONSE_LOW, gates_pass=True
        )
        cv = compose_verdict(results)
        # Gate graders all pass; judge verdicts are flag role and don't affect task_passes_gates
        assert cv.task_passes_gates is True

    def test_judge_rubric_loaded_from_file(self, tmp_path, monkeypatch):
        """Rubric dimensions come from the YAML file on disk."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        calls = []
        def fake_judge(prompt, model):
            calls.append(prompt)
            return _FAKE_JUDGE_RESPONSE

        monkeypatch.setattr(graders_mod, "_invoke_judge", fake_judge)

        # Use a spec that names the real rubric file
        task = {"graders": [_JUDGE_SPEC]}
        grade(Transcript(), None, tmp_path, task)

        # The judge was NOT called because there are no gate graders to pass
        # (no gates → gates trivially pass → judge runs)
        assert len(calls) == 1
        # The prompt should mention rubric dimensions
        assert "groundedness" in calls[0]

    def test_judge_no_gates_means_trivially_passes(self, tmp_path, monkeypatch):
        """When there are no gate graders, judge runs (gates trivially pass)."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        invoked = []
        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: (invoked.append(1), _FAKE_JUDGE_RESPONSE)[1])

        task = {"graders": [_JUDGE_SPEC]}
        results = grade(Transcript(), None, tmp_path, task)
        assert invoked, "Judge should have been invoked when no gates exist"
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == 3

    def test_judge_score_stored_in_actual(self, tmp_path, monkeypatch):
        """Each dimension row's actual dict includes the numeric score."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: _FAKE_JUDGE_RESPONSE)
        task = {"graders": [_JUDGE_SPEC]}
        results = grade(Transcript(), None, tmp_path, task)
        by_dim = {r.grader_id.split(".")[-1]: r for r in results if r.grader_id.startswith("judge.")}
        assert by_dim["groundedness"].actual["score"] == 4
        assert by_dim["coverage"].actual["score"] == 3
        assert by_dim["source_quality"].actual["score"] == 5

    def test_judge_justification_in_detail(self, tmp_path, monkeypatch):
        """Each dimension row's detail field contains the justification text."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: _FAKE_JUDGE_RESPONSE)
        task = {"graders": [_JUDGE_SPEC]}
        results = grade(Transcript(), None, tmp_path, task)
        by_dim = {r.grader_id.split(".")[-1]: r for r in results if r.grader_id.startswith("judge.")}
        assert "Most claims cited" in by_dim["groundedness"].detail
        assert "Core topics" in by_dim["coverage"].detail

    def test_judge_skip_rows_when_gates_fail_have_correct_count(self, tmp_path, monkeypatch):
        """When gates fail, skip rows are emitted for each declared dimension."""
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        not_invoked = []
        monkeypatch.setattr(graders_mod, "_invoke_judge",
                            lambda p, m: not_invoked.append(1) or _FAKE_JUDGE_RESPONSE)

        task = {
            "graders": [
                {"id": "outcome.gate1", "role": "gate",
                 "check": "False"},
                {**_JUDGE_SPEC, "dimensions": ["groundedness", "coverage"]},
            ]
        }
        results = grade(Transcript(), None, tmp_path, task)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == 2
        assert all(r.verdict == "skip" for r in judge_results)
        assert not not_invoked, "Judge backend must not be invoked when gates fail"

    def test_r3_task_judge_grader_dispatched(self, tmp_path, monkeypatch):
        """grade() with R3 task dispatches judge.thesis_quality correctly."""
        import yaml
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: _FAKE_JUDGE_RESPONSE)

        task = yaml.safe_load(_JUDGE_TASK_R3.read_text())
        # Remove deterministic graders so we can skip DB setup; inject always-pass gate
        task["graders"] = [
            {"id": "outcome.gate_always_pass", "role": "gate",
             "check": "True"},
            next(g for g in task["graders"] if g["id"].startswith("judge.")),
        ]
        results = grade(Transcript(), None, tmp_path, task)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        # Should emit one row per dimension declared in R3 judge spec
        assert len(judge_results) == 3


# ---------------------------------------------------------------------------
# Five-version recording in meta.json (spec §7, §8.3, issue #50)
# ---------------------------------------------------------------------------

class TestFiveVersionRecording:
    """meta.json records harness_version + fixture_version (spec §7 five-version row)."""

    def _make_mock_runner(self):
        class MockRunner(Runner):
            async def run(self, prompt, env):
                return _make_import_transcript()
        return MockRunner()

    def test_meta_includes_harness_version(self, tmp_path):
        from evals.harness.harness import run, _HARNESS_VERSION

        results_root = tmp_path / "results"
        run_dir = run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)
        meta = json.loads((run_dir / "meta.json").read_text())
        assert "harness_version" in meta
        assert meta["harness_version"] == _HARNESS_VERSION

    def test_meta_includes_fixture_version(self, tmp_path):
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        run_dir = run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)
        meta = json.loads((run_dir / "meta.json").read_text())
        assert "fixture_version" in meta
        assert isinstance(meta["fixture_version"], str)

    def test_fixture_version_from_module_constant(self, tmp_path):
        """Fixture builders with VERSION = '1' report '1' in meta.json."""
        from evals.harness.harness import _get_fixture_version

        version = _get_fixture_version("multi_instrument_theme_brief")
        assert version == "1"

    def test_fixture_version_defaults_to_1_if_no_constant(self, tmp_path):
        """Older fixture builders without VERSION attribute still report '1'."""
        from evals.harness.harness import _get_fixture_version

        # fidelity_sample_csv was authored before VERSION constant was added
        version = _get_fixture_version("fidelity_sample_csv")
        assert version == "1"

    def test_no_fixture_task_reports_na_fixture_version(self, tmp_path):
        """Tasks without a fixture report fixture_version='n/a'."""
        from evals.harness.harness import run
        import yaml
        import tempfile

        task_content = {
            "id": "T_nofixture",
            "version": "1",
            "suite": "regression",
            "prompt": "Hello.",
            "graders": [],
        }
        task_path = tmp_path / "T_nofixture.yaml"
        task_path.write_text(yaml.dump(task_content))

        results_root = tmp_path / "results"
        run_dir = run(task_path, self._make_mock_runner(), k=1, results_root=results_root)
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["fixture_version"] == "n/a"

    def test_task_version_present_in_meta(self, tmp_path):
        """task_version is already recorded (pre-existing; verify not broken)."""
        from evals.harness.harness import run

        results_root = tmp_path / "results"
        run_dir = run(TASK_R1, self._make_mock_runner(), k=1, results_root=results_root)
        meta = json.loads((run_dir / "meta.json").read_text())
        assert "task_version" in meta
        assert meta["task_version"] == "1"


# ---------------------------------------------------------------------------
# Saturation signal in emit_suite_report (spec §7, issue #50)
# ---------------------------------------------------------------------------

class TestSaturationSignal:
    """emit_suite_report flags saturated regression tasks (spec §7)."""

    def _write_fake_run(self, results_root: Path, task_id: str, n: int, pass_k: bool) -> None:
        """Write a fake run dir for task_id with a deterministic name based on n."""
        run_id = f"{task_id}_20260101_{n:06d}"
        run_dir = results_root / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "meta.json").write_text(json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "task_version": "1",
            "suite": "regression",
            "model": "claude-sonnet-5",
            "prompt_hash": "abc123",
            "fixture": "",
            "fixture_version": "1",
            "harness_version": "2",
            "now": None,
            "k": 1,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "pass_k": pass_k,
            "pass_at_k": pass_k,
            "trials": [],
        }) + "\n")

    def test_no_saturation_below_threshold(self, tmp_path, capsys):
        from evals.harness.harness import emit_suite_report, _SATURATION_THRESHOLD

        results_root = tmp_path / "results"
        for i in range(_SATURATION_THRESHOLD - 1):
            self._write_fake_run(results_root, "R1", i, pass_k=True)

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        assert "SATURATION" not in out

    def test_saturation_signal_at_threshold(self, tmp_path, capsys):
        from evals.harness.harness import emit_suite_report, _SATURATION_THRESHOLD

        results_root = tmp_path / "results"
        for i in range(_SATURATION_THRESHOLD):
            self._write_fake_run(results_root, "R1", i, pass_k=True)

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        assert "SATURATION" in out
        assert "R1" in out

    def test_saturation_broken_by_failing_run(self, tmp_path, capsys):
        from evals.harness.harness import emit_suite_report, _SATURATION_THRESHOLD

        results_root = tmp_path / "results"
        # A failing run in the middle breaks the consecutive streak
        for i in range(_SATURATION_THRESHOLD + 2):
            # The last run (highest i = most recent) is a failure
            pass_k = i < (_SATURATION_THRESHOLD + 1)
            self._write_fake_run(results_root, "R1", i, pass_k=pass_k)

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        # Most recent run failed; streak is broken at 0
        assert "SATURATION" not in out

    def test_saturation_only_checks_regression_suite(self, tmp_path, capsys):
        from evals.harness.harness import emit_suite_report, _SATURATION_THRESHOLD

        results_root = tmp_path / "results"
        # Write many passing runs but mark them as 'capability'
        for i in range(_SATURATION_THRESHOLD + 1):
            run_id = f"C1_20260101_{i:06d}"
            run_dir = results_root / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "meta.json").write_text(json.dumps({
                "run_id": run_id, "task_id": "C1", "task_version": "1",
                "suite": "capability", "model": "claude-sonnet-5",
                "prompt_hash": "abc", "fixture": "", "fixture_version": "1",
                "harness_version": "2", "now": None, "k": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "pass_k": True, "pass_at_k": True, "trials": [],
            }) + "\n")

        emit_suite_report(results_root)
        out = capsys.readouterr().out
        assert "SATURATION" not in out


# ---------------------------------------------------------------------------
# C4 judge grader dispatch (issue #50)
# ---------------------------------------------------------------------------

class TestC4JudgeGraderDispatch:
    """grade() with C4 task dispatches judge.theme_brief_quality with 3 dimensions."""

    _TASK_C4 = Path(__file__).parent.parent / "evals" / "tasks" / "C4.yaml"

    _FAKE_JUDGE_RESPONSE = """{
        "coverage": {"score": 4, "justification": "Both VTI and AAPL covered."},
        "groundedness": {"score": 3, "justification": "Most claims sourced."},
        "cross_instrument_synthesis": {"score": 2, "justification": "Little synthesis."}
    }"""

    def test_c4_judge_grader_emits_three_skip_rows_when_gates_fail(self, tmp_path, monkeypatch):
        """When gate graders fail, judge emits skip rows for each dimension."""
        import yaml
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: self._FAKE_JUDGE_RESPONSE)

        task = yaml.safe_load(self._TASK_C4.read_text())
        results = grade(Transcript(), None, tmp_path, task)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == 3
        assert all(r.verdict == "skip" for r in judge_results)

    def test_c4_judge_grader_emits_three_rows_when_gates_pass(self, tmp_path, monkeypatch):
        """When all gate graders pass, judge emits 3 per-dimension rows."""
        import yaml
        from evals.harness import graders as graders_mod
        from evals.harness.graders import grade

        monkeypatch.setattr(graders_mod, "_invoke_judge", lambda p, m: self._FAKE_JUDGE_RESPONSE)

        task = yaml.safe_load(self._TASK_C4.read_text())
        # Replace all gate graders with always-pass checks
        task["graders"] = [
            {"id": "outcome.always_pass", "role": "gate", "check": "True"},
            next(g for g in task["graders"] if g["id"].startswith("judge.")),
        ]
        results = grade(Transcript(), None, tmp_path, task)
        judge_results = [r for r in results if r.grader_id.startswith("judge.")]
        assert len(judge_results) == 3
        dim_ids = {r.grader_id.split(".")[-1] for r in judge_results}
        assert dim_ids == {"coverage", "groundedness", "cross_instrument_synthesis"}

    def test_c4_judge_rubric_loads_correctly(self, tmp_path):
        """theme_brief_quality_v1.yaml is a valid rubric with 3 dimensions."""
        import yaml
        from pathlib import Path

        rubric = yaml.safe_load(
            (Path(__file__).parent.parent / "evals" / "rubrics" / "theme_brief_quality_v1.yaml")
            .read_text()
        )
        assert rubric["id"] == "theme_brief_quality"
        assert set(rubric["dimensions"].keys()) == {"coverage", "groundedness", "cross_instrument_synthesis"}
        assert all(d.get("flag_below") == 3 for d in rubric["dimensions"].values())
