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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R2: {failing}"


class TestHarnessRunR3:
    def test_r3_graders_pass(self, tmp_path):
        from evals.harness.harness import run
        from evals.harness.runner import Runner

        _THESIS = "# AAPL Thesis\n\n" + ("Apple is a great company. " * 20)

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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
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
        verdicts = [json.loads(l) for l in (run_dir / "verdicts.jsonl").read_text().splitlines() if l]
        failing = [v for v in verdicts if v["role"] == "gate" and v["verdict"] != "pass"]
        assert failing == [], f"Gate graders failed for R7: {failing}"
