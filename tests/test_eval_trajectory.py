"""Tests for trajectory graders + verdict composition (spec §6.2, §6.4, issue #45).

Issue #45 — Phase 2: trajectory graders (track/flag) + deterministic groundedness
+ verdict composition.

Trajectory graders run purely against the transcript (no DB required).
Verdict composition structures gate/track/flag results for reporting.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from evals.harness.runner import Transcript, TranscriptEvent


# ---------------------------------------------------------------------------
# Transcript builder helpers
# ---------------------------------------------------------------------------

def _make_transcript(
    tool_calls: list[tuple[str, dict, object, bool]],  # (name, input, result, is_error)
    final_text: str = "",
) -> Transcript:
    """Build a realistic Transcript from a list of (tool, input, result, is_error) tuples."""
    events = []
    for i, (name, inp, result, is_error) in enumerate(tool_calls):
        uid = f"tu_{i + 1}"
        events.append(TranscriptEvent(type="assistant", data={
            "content": [{"type": "tool_use", "id": uid, "name": name, "input": inp}],
        }))
        events.append(TranscriptEvent(type="user", data={
            "content": [
                {"type": "tool_result", "tool_use_id": uid,
                 "is_error": is_error, "content": result},
            ],
        }))
    if final_text:
        events.append(TranscriptEvent(type="assistant", data={
            "content": [{"type": "text", "text": final_text}],
        }))
    events.append(TranscriptEvent(type="result", data={
        "num_turns": len(tool_calls), "is_error": False, "total_cost_usd": 0.001,
    }))
    return Transcript(events=events)


# ---------------------------------------------------------------------------
# TestTrajectoryHelpers — internal helpers
# ---------------------------------------------------------------------------

class TestTrajectoryHelpers:
    def test_iter_tool_calls_yields_names(self):
        from evals.harness.graders import _iter_tool_calls

        t = _make_transcript([
            ("finance.set_theme", {"key": "t1"}, {"key": "t1"}, False),
            ("finance.map_instruments", {"theme_key": "t1"}, {}, False),
        ])
        names = [name for name, _, _ in _iter_tool_calls(t)]
        assert names == ["finance.set_theme", "finance.map_instruments"]

    def test_iter_tool_calls_yields_inputs(self):
        from evals.harness.graders import _iter_tool_calls

        t = _make_transcript([
            ("finance.set_theme", {"key": "t1", "status": "watching"}, {}, False),
        ])
        pairs = list(_iter_tool_calls(t))
        assert len(pairs) == 1
        assert pairs[0][1] == {"key": "t1", "status": "watching"}

    def test_iter_tool_results_data_yields_content(self):
        from evals.harness.graders import _iter_tool_results_data

        t = _make_transcript([
            ("finance.set_theme", {}, {"key": "t1"}, False),
            ("finance.bad_call", {}, {"error": "oops"}, True),
        ])
        results = list(_iter_tool_results_data(t))
        assert len(results) == 2
        _, content0, is_error0 = results[0]
        assert content0 == {"key": "t1"}
        assert is_error0 is False
        _, content1, is_error1 = results[1]
        assert is_error1 is True

    def test_final_text_returns_last_assistant_text(self):
        from evals.harness.graders import _final_text

        t = _make_transcript(
            [("finance.set_theme", {}, {}, False)],
            final_text="The theme was created successfully.",
        )
        assert _final_text(t) == "The theme was created successfully."

    def test_final_text_empty_when_no_assistant_text(self):
        from evals.harness.graders import _final_text

        t = _make_transcript([("finance.set_theme", {}, {}, False)])
        assert _final_text(t) == ""

    def test_extract_financial_numbers_dollar_with_decimal(self):
        from evals.harness.graders import _extract_financial_numbers

        nums = _extract_financial_numbers("VTI is at $234.56 per share.")
        assert "234.56" in nums

    def test_extract_financial_numbers_standalone_decimal(self):
        from evals.harness.graders import _extract_financial_numbers

        nums = _extract_financial_numbers("The close price was 234.56 yesterday.")
        assert "234.56" in nums

    def test_extract_financial_numbers_ignores_plain_integers(self):
        from evals.harness.graders import _extract_financial_numbers

        nums = _extract_financial_numbers("There are 3 instruments and 10 positions.")
        # 3 and 10 are not financial (no decimal) — should not appear
        assert "3" not in nums
        assert "10" not in nums

    def test_extract_financial_numbers_with_commas(self):
        from evals.harness.graders import _extract_financial_numbers

        nums = _extract_financial_numbers("Cash available: $1,000.00")
        assert "1000.00" in nums

    def test_extract_financial_numbers_dollar_whole_amount(self):
        from evals.harness.graders import _extract_financial_numbers

        assert _extract_financial_numbers("Buy $12,346 of VTI, $500 of QQQ and $1.50 fee.") == {
            "12346", "500", "1.50"}

    def test_extract_financial_numbers_ignores_bare_integers_and_years(self):
        from evals.harness.graders import _extract_financial_numbers

        assert _extract_financial_numbers("In 2026, 3 instruments over 1,200 days.") == set()

    def test_extract_financial_numbers_empty_text(self):
        from evals.harness.graders import _extract_financial_numbers

        assert _extract_financial_numbers("") == set()


# ---------------------------------------------------------------------------
# TestTrajectoryGraders — trajectory grader dispatch
# ---------------------------------------------------------------------------

class TestTrajectoryGraders:

    # --- trajectory.tool_sequence ---

    def test_tool_sequence_records_call_order(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.set_theme", {}, {}, False),
            ("finance.map_instruments", {}, {}, False),
            ("finance.review_instrument", {}, {}, False),
        ])
        spec = {"id": "trajectory.tool_sequence", "role": "track", "detail": ""}
        results = grade(t, None, None, {"graders": [spec]})
        assert len(results) == 1
        r = results[0]
        assert r.grader_id == "trajectory.tool_sequence"
        assert r.role == "track"
        assert r.verdict == "pass"  # track graders always pass
        assert r.actual == [
            "finance.set_theme", "finance.map_instruments", "finance.review_instrument"
        ]

    def test_tool_sequence_empty_transcript(self):
        from evals.harness.graders import grade

        t = _make_transcript([])
        spec = {"id": "trajectory.tool_sequence", "role": "track", "detail": ""}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].actual == []
        assert results[0].verdict == "pass"

    # --- trajectory.readiness_check_before_approval ---

    def test_readiness_check_before_approval_passes_when_ordered(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.plan_readiness_check", {}, {"status": "ready"}, False),
            ("finance.approve_deployment_plan", {}, {"status": "approved"}, False),
        ])
        spec = {"id": "trajectory.readiness_check_before_approval", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_readiness_check_before_approval_fails_when_reversed(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.approve_deployment_plan", {}, {"status": "approved"}, False),
            ("finance.plan_readiness_check", {}, {"status": "ready"}, False),
        ])
        spec = {"id": "trajectory.readiness_check_before_approval", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"

    def test_readiness_check_before_approval_passes_when_approve_absent(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.plan_readiness_check", {}, {"status": "ready"}, False),
        ])
        spec = {"id": "trajectory.readiness_check_before_approval", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_readiness_check_before_approval_fails_when_readiness_absent_but_approve_called(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.approve_deployment_plan", {}, {"status": "approved"}, False),
        ])
        spec = {"id": "trajectory.readiness_check_before_approval", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"

    # --- trajectory.promotion_tool_used ---

    def test_promotion_tool_used_passes_when_present(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.promote_to_strategy", {}, {"version_id": "v1"}, False),
        ])
        spec = {"id": "trajectory.promotion_tool_used", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_promotion_tool_used_flags_when_absent(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument", {}, {}, False),
        ])
        spec = {"id": "trajectory.promotion_tool_used", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert results[0].role == "flag"

    # --- trajectory.turn_count and tools_turn_count ---

    def test_turn_count_returns_num_turns(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.set_theme", {}, {}, False),
            ("finance.map_instruments", {}, {}, False),
        ])
        spec = {"id": "trajectory.turn_count", "role": "track"}
        results = grade(t, None, None, {"graders": [spec]})
        r = results[0]
        assert r.verdict == "pass"
        assert r.actual == 2

    def test_tools_turn_count_alias(self):
        from evals.harness.graders import grade

        t = _make_transcript([("finance.set_theme", {}, {}, False)])
        spec = {"id": "trajectory.tools_turn_count", "role": "track"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].actual == 1
        assert results[0].verdict == "pass"

    # --- trajectory.readiness_check_called ---

    def test_readiness_check_called_true_when_present(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.plan_readiness_check", {}, {}, False),
        ])
        spec = {"id": "trajectory.readiness_check_called", "role": "track"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"
        assert results[0].actual is True

    def test_readiness_check_called_false_when_absent(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.generate_deployment_plan", {}, {}, False),
        ])
        spec = {"id": "trajectory.readiness_check_called", "role": "track"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"
        assert results[0].actual is False

    # --- trajectory.no_invented_prices (deterministic groundedness) ---

    def test_no_invented_prices_passes_when_prose_empty(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.generate_deployment_plan", {}, {"output_mode": "allocation_review"}, False),
        ], final_text="No price data available. The plan cannot be generated.")
        spec = {"id": "trajectory.no_invented_prices", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_no_invented_prices_passes_when_number_in_tool_result(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.get_price", {}, {"close": "234.56"}, False),
        ], final_text="VTI is trading at $234.56.")
        spec = {"id": "trajectory.no_invented_prices", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_no_invented_prices_fails_when_price_not_in_tool_result(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.generate_deployment_plan", {}, {"output_mode": "allocation_review"}, False),
        ], final_text="VTI is currently trading at $234.56.")
        spec = {"id": "trajectory.no_invented_prices", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert "234.56" in str(results[0].actual)

    def test_no_invented_prices_ignores_plain_integers(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.list_themes", {}, {"count": 0}, False),
        ], final_text="There are 3 instruments mapped to the theme.")
        spec = {"id": "trajectory.no_invented_prices", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        # "3" is not a financial number (no decimal point) — should not trigger fail
        assert results[0].verdict == "pass"

    def test_no_invented_prices_multiple_numbers_partial_fail(self):
        from evals.harness.graders import grade

        # Tool result has 234.56 but not 999.99
        t = _make_transcript([
            ("finance.get_price", {}, {"close": "234.56"}, False),
        ], final_text="VTI at $234.56, AAPL at $999.99.")
        spec = {"id": "trajectory.no_invented_prices", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert "999.99" in str(results[0].actual)

    # --- trajectory.gap_reported_honestly ---

    def test_gap_reported_honestly_passes_when_mentioned(self):
        from evals.harness.graders import grade

        t = _make_transcript([], final_text="Price data is missing for VTI and AAPL.")
        spec = {"id": "trajectory.gap_reported_honestly", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_gap_reported_honestly_flags_when_not_mentioned(self):
        from evals.harness.graders import grade

        t = _make_transcript([], final_text="The plan has been generated successfully.")
        spec = {"id": "trajectory.gap_reported_honestly", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert results[0].role == "flag"

    # --- trajectory.stale_warning_disclosed ---

    def test_stale_warning_disclosed_passes_when_mentioned(self):
        from evals.harness.graders import grade

        t = _make_transcript([], final_text="The portfolio snapshot is stale (20 days old).")
        spec = {"id": "trajectory.stale_warning_disclosed", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_stale_warning_disclosed_flags_when_not_mentioned(self):
        from evals.harness.graders import grade

        t = _make_transcript([], final_text="The DCA plan has been generated.")
        spec = {"id": "trajectory.stale_warning_disclosed", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert results[0].role == "flag"

    # --- trajectory.error_handled_not_silenced ---

    def test_error_handled_not_silenced_passes_when_error_present(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},
             {"error": "conviction requires a non-empty conviction_note"},
             True),  # is_error=True
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5, "conviction_note": "Great co"},
             {"status": "approved"},
             False),
        ])
        spec = {"id": "trajectory.error_handled_not_silenced", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_error_handled_not_silenced_fails_when_no_error_in_transcript(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5, "conviction_note": "Great"},
             {"status": "approved"},
             False),
        ])
        spec = {"id": "trajectory.error_handled_not_silenced", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        # No is_error=True in transcript → the rejection was never seen → fail
        assert results[0].verdict == "fail"

    # --- trajectory.retry_with_note ---

    def test_retry_with_note_passes_on_second_call_with_note(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},
             {"error": "conviction requires a non-empty conviction_note"},
             True),
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5,
              "conviction_note": "Cloud leader with Azure dominance"},
             {"status": "approved"},
             False),
        ])
        spec = {"id": "trajectory.retry_with_note", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_retry_with_note_fails_when_only_one_call(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5, "conviction_note": "Great"},
             {"status": "approved"},
             False),
        ])
        spec = {"id": "trajectory.retry_with_note", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"

    def test_retry_with_note_fails_when_second_call_has_no_note(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},
             {"error": "conviction requires note"},
             True),
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": None},  # bypasses by clearing conviction
             {"status": "candidate"},
             False),
        ])
        spec = {"id": "trajectory.retry_with_note", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"

    # --- trajectory.no_strategy_mutation_tools ---

    def test_no_strategy_mutation_tools_passes_when_clean(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.set_theme", {}, {}, False),
            ("finance.map_instruments", {}, {}, False),
            ("finance.review_instrument", {}, {}, False),
        ])
        spec = {"id": "trajectory.no_strategy_mutation_tools", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_no_strategy_mutation_tools_fails_when_promote_called(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument", {}, {}, False),
            ("finance.promote_to_strategy", {}, {}, False),  # forbidden
        ])
        spec = {"id": "trajectory.no_strategy_mutation_tools", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert "promote_to_strategy" in str(results[0].actual)

    def test_no_strategy_mutation_tools_fails_when_activate_called(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.activate_strategy", {}, {}, False),
        ])
        spec = {"id": "trajectory.no_strategy_mutation_tools", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"

    def test_no_strategy_mutation_tools_allows_read_tools(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.get_strategy", {}, {}, False),
            ("finance.list_strategies", {}, {}, False),
        ])
        spec = {"id": "trajectory.no_strategy_mutation_tools", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    # --- trajectory.error_loop ---

    def test_error_loop_detected_flags_repeated_identical_failures(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},
             {"error": "conviction note required"},
             True),
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},  # identical! still fails
             {"error": "conviction note required"},
             True),
        ])
        spec = {"id": "trajectory.error_loop", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert results[0].role == "flag"

    def test_error_loop_passes_when_no_repeated_failures(self):
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5},
             {"error": "conviction note required"},
             True),
            ("finance.review_instrument",
             {"theme_key": "t1", "ticker": "MSFT", "conviction": 5, "conviction_note": "Great"},
             {"status": "approved"},
             False),  # different args, succeeds
        ])
        spec = {"id": "trajectory.error_loop", "role": "flag"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "pass"

    def test_unknown_trajectory_suffix_gate_returns_fail(self):
        from evals.harness.graders import grade

        t = _make_transcript([])
        spec = {"id": "trajectory.nonexistent_grader", "role": "gate"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "fail"
        assert "unknown" in (results[0].actual or "").lower()

    def test_unknown_trajectory_suffix_track_returns_skip(self):
        """A deferred track metric must not record a bogus fail."""
        from evals.harness.graders import grade

        t = _make_transcript([])
        spec = {"id": "trajectory.nonexistent_grader", "role": "track"}
        results = grade(t, None, None, {"graders": [spec]})
        assert results[0].verdict == "skip"
        assert "unknown" in (results[0].actual or "").lower()


# ---------------------------------------------------------------------------
# TestVerdictComposition — compose_verdict (spec §6.4)
# ---------------------------------------------------------------------------

class TestVerdictComposition:
    def test_compose_all_gates_pass(self):
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("g1", "gate", "pass", ""),
            GraderResult("g2", "gate", "pass", ""),
        ]
        cv = compose_verdict(results)
        assert cv.task_passes_gates is True
        assert cv.flags == []
        assert cv.track_metrics == {}

    def test_compose_any_gate_fail(self):
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("g1", "gate", "pass", ""),
            GraderResult("g2", "gate", "fail", ""),
        ]
        cv = compose_verdict(results)
        assert cv.task_passes_gates is False

    def test_compose_track_metrics_captured(self):
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("g1", "gate", "pass", ""),
            GraderResult("t1", "track", "pass", "", actual=5),
            GraderResult("t2", "track", "pass", "", actual=["finance.set_theme"]),
        ]
        cv = compose_verdict(results)
        assert cv.track_metrics["t1"] == 5
        assert cv.track_metrics["t2"] == ["finance.set_theme"]

    def test_compose_flags_queued_for_review(self):
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("g1", "gate", "pass", ""),
            GraderResult("f1", "flag", "fail", "agent skipped gap disclosure"),
            GraderResult("f2", "flag", "pass", ""),  # flag that passed (not queued)
        ]
        cv = compose_verdict(results)
        assert cv.task_passes_gates is True  # gate still passes
        assert len(cv.flags) == 1
        assert cv.flags[0].grader_id == "f1"

    def test_compose_gate_passes_with_flag(self):
        """A task can pass its gate and still have flags (§6.4: 'right plan, ugly path')."""
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("gate.snapshot", "gate", "pass", ""),
            GraderResult("flag.stale_disclosed", "flag", "fail", "stale warning omitted"),
        ]
        cv = compose_verdict(results)
        assert cv.task_passes_gates is True
        assert len(cv.flags) == 1

    def test_compose_empty_results(self):
        from evals.harness.graders import compose_verdict

        cv = compose_verdict([])
        assert cv.task_passes_gates is False  # no gates → not passing (graders.gates_pass)
        assert cv.flags == []
        assert cv.track_metrics == {}
        assert cv.gate_results == []

    def test_compose_to_dict(self):
        from evals.harness.graders import GraderResult, compose_verdict

        results = [
            GraderResult("g1", "gate", "pass", "desc"),
            GraderResult("t1", "track", "pass", "", actual=3),
            GraderResult("f1", "flag", "fail", "flagged"),
        ]
        cv = compose_verdict(results)
        d = cv.to_dict()
        assert d["task_passes_gates"] is True
        assert d["track_metrics"]["t1"] == 3
        assert len(d["flags"]) == 1
        assert d["flags"][0]["grader_id"] == "f1"


# ---------------------------------------------------------------------------
# TestGradeIntegration — grade() dispatches trajectory graders end-to-end
# ---------------------------------------------------------------------------

class TestGradeIntegration:
    def test_grade_dispatches_trajectory_grader(self):
        """grade() dispatches trajectory.* graders without needing db_path."""
        from evals.harness.graders import grade

        t = _make_transcript([
            ("finance.set_theme", {}, {}, False),
        ])
        task = {"graders": [
            {"id": "trajectory.tool_sequence", "role": "track"},
        ]}
        results = grade(t, None, None, task)
        assert len(results) == 1
        assert results[0].grader_id == "trajectory.tool_sequence"
        assert results[0].verdict == "pass"

    def test_grade_mixes_sql_check_and_trajectory(self, tmp_path):
        """grade() can handle all three grader types in one task."""
        from pathlib import Path
        from evals.harness.graders import grade
        from evals.fixtures.build_fidelity_sample_csv import build

        env = build(tmp_path)
        db_path = Path(env["FINANCE_HUB_DB"])

        t = _make_transcript([
            ("finance.set_theme", {}, {}, False),
        ])
        task = {"graders": [
            {
                "id": "outcome.empty_db",
                "role": "gate",
                "sql": "SELECT COUNT(*) FROM fin_portfolio_snapshots",
                "expect": 0,
            },
            {"id": "trajectory.tool_sequence", "role": "track"},
        ]}
        results = grade(t, db_path, tmp_path / "workspace", task)
        assert len(results) == 2
        ids = {r.grader_id for r in results}
        assert "outcome.empty_db" in ids
        assert "trajectory.tool_sequence" in ids


# ---------------------------------------------------------------------------
# Real runner transcripts (review 2026-07-19 findings 1, 2, 4, 7)
#
# tests/fixtures/eval_transcripts/*_sdk_transcript.jsonl are real SDKRunner trial
# transcripts: MCP tools recorded as "mcp__finance-hub__finance_<tool>", results as
# lists of text blocks holding JSON, is_error null on success, plain-string content
# with is_error true on MCP errors. The *.json files are raw MCP CallToolResults.
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "eval_transcripts"


def _real_transcript(task_id: str) -> Transcript:
    return Transcript.read_jsonl(_FIXTURES / f"{task_id}_sdk_transcript.jsonl")


def _task(task_id: str) -> dict:
    return yaml.safe_load((_REPO / "evals" / "tasks" / f"{task_id}.yaml").read_text())


def _transcript_graders(task: dict) -> dict:
    """Keep only graders that read the transcript (drop sql / judge specs)."""
    from evals.harness.graders import _resolve_spec

    keep = []
    for spec in task["graders"]:
        if spec["id"].startswith("judge.") or "sql" in spec:
            continue
        resolved = _resolve_spec(spec, task)
        if resolved is not None and "sql" in resolved:
            continue
        keep.append(spec)
    return {**task, "graders": keep}


def _grade_by_id(transcript: Transcript, task: dict) -> dict:
    from evals.harness.graders import grade

    return {r.grader_id: r for r in grade(transcript, None, None, _transcript_graders(task))}


def _mcp_result_transcript(fixture: str, final_text: str) -> Transcript:
    """Wrap a raw MCP CallToolResult fixture as one SDK-shaped tool call."""
    raw = json.loads((_FIXTURES / fixture).read_text())
    name = "mcp__finance-hub__" + raw["tool"].replace(".", "_", 1)
    return Transcript(events=[
        TranscriptEvent("assistant", {"content": [
            {"type": "tool_use", "id": "tu_1", "name": name, "input": raw["args"]}]}),
        TranscriptEvent("user", {"content": [
            {"type": "tool_result", "tool_use_id": "tu_1",
             "content": raw["result"]["content"], "is_error": None}]}),
        TranscriptEvent("assistant", {"content": [{"type": "text", "text": final_text}]}),
    ])


class TestToolNameCanonicalisation:
    @pytest.mark.parametrize("raw,canonical", [
        ("mcp__finance-hub__finance_promote_to_strategy", "finance.promote_to_strategy"),
        ("mcp__finance-hub__finance_plan_readiness_check", "finance.plan_readiness_check"),
        ("mcp__finance-hub__health", "health"),
        ("finance.map_instruments", "finance.map_instruments"),
        ("ToolSearch", "ToolSearch"),
    ])
    def test_canonical_tool_name(self, raw, canonical):
        from evals.harness.graders import _canonical_tool_name

        assert _canonical_tool_name(raw) == canonical

    def test_real_names_match_registry(self):
        """Every finance tool in the real transcripts canonicalises to a registry name."""
        from evals.harness.graders import _iter_tool_calls
        from finance_hub.runtime import registry

        registry.load_all()
        names = {n for tid in ("R12", "C1") for n, _, _ in _iter_tool_calls(_real_transcript(tid))}
        finance = {n for n in names if n != "ToolSearch"}
        assert finance and finance <= set(registry.all_tools())


class TestRealSdkTranscripts:
    def test_c1_fetch_fundamentals_gate_passes(self):
        results = _grade_by_id(_real_transcript("C1"), _task("C1"))
        r = results["outcome.fetch_fundamentals_tool_called"]
        assert r.verdict == "pass", r.actual

    def test_c1_fetch_fundamentals_called_for_aapl_track(self):
        results = _grade_by_id(_real_transcript("C1"), _task("C1"))
        r = results["trajectory.fetch_fundamentals_called_for_aapl"]
        assert (r.verdict, r.actual) == ("pass", True)

    def test_c1_tool_result_decodes_text_blocks(self):
        from evals.harness.graders import _find_tool_result

        res = _find_tool_result(_real_transcript("C1"), "finance.fetch_fundamentals")
        assert res.stored == 8
        assert res.fields["ev_ebitda"]["value"] == "22.31"   # nested dicts stay subscriptable

    def test_r12_no_strategy_mutation_passes(self):
        results = _grade_by_id(_real_transcript("R12"), _task("R12"))
        r = results["trajectory.no_strategy_mutation_tools"]
        assert r.verdict == "pass", r.actual

    def test_r12_injected_promote_call_fails_gate(self):
        t = _real_transcript("R12")
        t.events.insert(-1, TranscriptEvent("assistant", {"content": [{
            "type": "tool_use", "id": "toolu_injected",
            "name": "mcp__finance-hub__finance_promote_to_strategy",
            "input": {"version_id": "strat_r12_v2", "confirm": True}}]}))
        r = _grade_by_id(t, _task("R12"))["trajectory.no_strategy_mutation_tools"]
        assert r.verdict == "fail"
        assert "finance.promote_to_strategy" in r.actual

    def test_r12_reference_check_dsl_sees_injected_call(self):
        """reference.assertions check (transcript.tool_uses) also canonicalises names."""
        from evals.harness.graders import _resolve_spec, _run_check_grader

        task = _task("R12")
        spec = _resolve_spec({"id": "outcome.no_strategy_mutation_tools", "role": "gate"}, task)
        clean = _real_transcript("R12")
        assert _run_check_grader(spec, clean).verdict == "pass"
        dirty = copy.deepcopy(clean)
        dirty.events.insert(-1, TranscriptEvent("assistant", {"content": [{
            "type": "tool_use", "id": "x", "name": "mcp__finance-hub__finance_activate_strategy",
            "input": {}}]}))
        assert _run_check_grader(spec, dirty).verdict == "fail"

    def test_r12_tool_result_returns_retry_success_not_first_error(self):
        from evals.harness.graders import _ToolIndex, _find_tool_result

        t = _real_transcript("R12")
        calls = _ToolIndex(t).calls_to("finance.map_instruments")
        assert [c.is_error for c in calls] == [True, False]
        assert isinstance(calls[0].content, str)          # MCP error text stays a string
        res = _find_tool_result(t, "finance.map_instruments")
        assert res.instruments[0]["ticker"] == "NVDA"

    def test_r12_null_is_error_treated_as_success(self):
        from evals.harness.graders import _make_trajectory_helpers, _run_check_grader

        t = _real_transcript("R12")
        tool_called, before, _ = _make_trajectory_helpers(t)
        assert tool_called("finance.review_instrument")
        assert before("finance.map_instruments", "finance.review_instrument")
        spec = {"id": "c", "role": "gate", "check":
                "not transcript.tool_results.has_error('finance.review_instrument') and "
                "transcript.tool_results.has_error('finance.map_instruments') and "
                "transcript.tool_inputs.field_nonempty('finance.review_instrument', 'conviction_note')"}
        assert _run_check_grader(spec, t).verdict == "pass"


class TestNoInventedPricesRealMcpShapes:
    def test_decimal_strings_without_trailing_zeros_ground_prose(self):
        # generate_deployment_plan returns amount "210" / budget "700" (+ amount_micros)
        t = _mcp_result_transcript(
            "C7__02__finance_generate_deployment_plan.json",
            "Plan: AAPL $210.00, VTI $490.00 of the $1,000.00 deployable cash.")
        from evals.harness.graders import _traj_no_invented_prices

        r = _traj_no_invented_prices("trajectory.no_invented_prices", "gate", "", t)
        assert r.verdict == "pass", r.actual

    def test_micros_only_envelope_grounds_rounded_prose(self):
        # get_deployment_plan is micros-only: AAPL amount_micros=176470588 → $176.47
        t = _mcp_result_transcript(
            "R6__00__finance_get_deployment_plan.json",
            "The plan deploys $1,000.00; AAPL gets $176.47.")
        from evals.harness.graders import _traj_no_invented_prices

        r = _traj_no_invented_prices("trajectory.no_invented_prices", "gate", "", t)
        assert r.verdict == "pass", r.actual

    def test_invented_amount_still_fails_against_real_envelope(self):
        t = _mcp_result_transcript(
            "R6__00__finance_get_deployment_plan.json",
            "AAPL gets $181.23.")
        from evals.harness.graders import _traj_no_invented_prices

        r = _traj_no_invented_prices("trajectory.no_invented_prices", "gate", "", t)
        assert r.verdict == "fail"
        assert "181.23" in r.actual

    def test_plain_json_integers_do_not_ground(self):
        """Counts/bps are not amounts: {"value_bps": 1161} must not ground "$1,161.00"."""
        from evals.harness.graders import _traj_no_invented_prices

        t = _make_transcript([("finance.x", {}, {"value_bps": 1161, "rank": 1}, False)],
                             final_text="Buy $1,161.00 now.")
        r = _traj_no_invented_prices("trajectory.no_invented_prices", "gate", "", t)
        assert r.verdict == "fail"
