"""Tests for the eval runner seam (issue #37 — de-risk spike)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from evals.harness.runner import Runner, Transcript, TranscriptEvent, TrialEnv


# ---------------------------------------------------------------------------
# Transcript serialisation / deserialisation
# ---------------------------------------------------------------------------

class TestTranscriptJsonl:
    def _make_events(self):
        return [
            TranscriptEvent(type="assistant", data={"model": "claude-sonnet-5", "content": [{"type": "text", "text": "Hello!"}]}),
            TranscriptEvent(type="user", data={"content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}]}),
            TranscriptEvent(type="result", data={"num_turns": 1, "total_cost_usd": 0.001, "session_id": "sess-abc", "is_error": False}),
        ]

    def test_write_then_read_roundtrip(self, tmp_path):
        events = self._make_events()
        t = Transcript(events=events)
        p = tmp_path / "transcript.jsonl"
        t.write_jsonl(p)

        loaded = Transcript.read_jsonl(p)
        assert len(loaded.events) == len(events)
        for orig, read in zip(events, loaded.events):
            assert read.type == orig.type
            assert read.data == orig.data

    def test_each_line_is_valid_json(self, tmp_path):
        t = Transcript(events=self._make_events())
        p = tmp_path / "transcript.jsonl"
        t.write_jsonl(p)

        lines = [l for l in p.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "type" in obj
            assert "data" in obj

    def test_write_empty_transcript(self, tmp_path):
        t = Transcript(events=[])
        p = tmp_path / "transcript.jsonl"
        t.write_jsonl(p)
        assert p.read_text() == ""

    def test_result_property_returns_last_result_data(self):
        events = self._make_events()
        t = Transcript(events=events)
        assert t.result == {"num_turns": 1, "total_cost_usd": 0.001, "session_id": "sess-abc", "is_error": False}

    def test_result_property_none_when_no_result(self):
        t = Transcript(events=[TranscriptEvent(type="assistant", data={"content": []})])
        assert t.result is None

    def test_num_turns_from_result(self):
        t = Transcript(events=self._make_events())
        assert t.num_turns == 1

    def test_total_cost_usd_from_result(self):
        t = Transcript(events=self._make_events())
        assert t.total_cost_usd == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# TrialEnv — env hygiene
# ---------------------------------------------------------------------------

class TestTrialEnv:
    def _make_env(self, **extras):
        return TrialEnv(
            cwd=Path("/tmp/trial"),
            env={"FINANCE_HUB_DB": "/tmp/db.sqlite", **extras},
            mcp_servers={"finance-hub": {"command": "finance-mcp"}},
            model="claude-sonnet-5",
        )

    def test_setting_sources_defaults_to_project_only(self):
        env = self._make_env()
        assert env.setting_sources == ["project"]

    def test_anthropic_api_key_is_stripped(self):
        env = self._make_env(ANTHROPIC_API_KEY="sk-ant-abc123")
        assert "ANTHROPIC_API_KEY" not in env.env

    def test_other_env_vars_are_preserved(self):
        env = self._make_env(FINANCE_HUB_NOW="2026-07-17T00:00:00Z")
        assert env.env["FINANCE_HUB_NOW"] == "2026-07-17T00:00:00Z"
        assert env.env["FINANCE_HUB_DB"] == "/tmp/db.sqlite"

    def test_no_api_key_in_env_is_fine(self):
        env = self._make_env()
        assert "ANTHROPIC_API_KEY" not in env.env


# ---------------------------------------------------------------------------
# Runner seam (ABC)
# ---------------------------------------------------------------------------

class TestRunnerSeam:
    def test_runner_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            Runner()

    def test_concrete_runner_must_implement_run(self):
        class BadRunner(Runner):
            pass

        with pytest.raises(TypeError):
            BadRunner()

    def test_concrete_runner_with_run_works(self):
        class FakeRunner(Runner):
            async def run(self, prompt: str, env: TrialEnv) -> Transcript:
                return Transcript(events=[
                    TranscriptEvent(type="assistant", data={"content": [{"type": "text", "text": f"Echo: {prompt}"}]}),
                    TranscriptEvent(type="result", data={"num_turns": 1, "total_cost_usd": 0.0, "is_error": False}),
                ])

        runner = FakeRunner()
        env = TrialEnv(cwd=Path("/tmp"), env={}, mcp_servers={}, model="claude-sonnet-5")
        t = asyncio.run(runner.run("hello", env))
        assert t.events[0].type == "assistant"
        assert t.events[1].type == "result"


# ---------------------------------------------------------------------------
# SDKRunner — unit tests via mocked query()
# ---------------------------------------------------------------------------

class TestSDKRunner:
    def _make_env(self, tmp_path):
        return TrialEnv(
            cwd=tmp_path,
            env={"FINANCE_HUB_DB": str(tmp_path / "db.sqlite")},
            mcp_servers={"finance-hub": {"command": "finance-mcp", "env": {"FINANCE_HUB_DB": str(tmp_path / "db.sqlite")}}},
            model="claude-sonnet-5",
            max_turns=10,
        )

    def _fake_query_result(self):
        """Return an async generator that yields fake SDK messages."""
        from claude_agent_sdk.types import (
            AssistantMessage, ResultMessage, TextBlock, ToolUseBlock,
            UserMessage, ToolResultBlock,
        )

        async def _gen():
            yield AssistantMessage(
                content=[
                    TextBlock(text="I'll help with that."),
                    ToolUseBlock(id="tu_1", name="Read", input={"path": "/tmp/x"}),
                ],
                model="claude-sonnet-5",
                session_id="sess-123",
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="tu_1", content="file contents", is_error=False),
                ],
            )
            yield AssistantMessage(
                content=[TextBlock(text="Done.")],
                model="claude-sonnet-5",
                session_id="sess-123",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=1200,
                duration_api_ms=1000,
                is_error=False,
                num_turns=2,
                session_id="sess-123",
                total_cost_usd=0.005,
            )

        return _gen()

    def test_sdk_runner_maps_messages_to_transcript_events(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello world", env))

        assert len(t.events) == 4
        assert t.events[0].type == "assistant"
        assert t.events[1].type == "user"
        assert t.events[2].type == "assistant"
        assert t.events[3].type == "result"

    def test_sdk_runner_captures_text_blocks(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello", env))

        first_assistant = t.events[0].data
        assert any(b["type"] == "text" for b in first_assistant["content"])
        text_block = next(b for b in first_assistant["content"] if b["type"] == "text")
        assert text_block["text"] == "I'll help with that."

    def test_sdk_runner_captures_tool_use_blocks(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello", env))

        first_assistant = t.events[0].data
        tool_use = next(b for b in first_assistant["content"] if b["type"] == "tool_use")
        assert tool_use["name"] == "Read"
        assert tool_use["input"] == {"path": "/tmp/x"}
        assert tool_use["id"] == "tu_1"

    def test_sdk_runner_captures_tool_result_blocks(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello", env))

        user_event = t.events[1].data
        tool_result = next(b for b in user_event["content"] if b["type"] == "tool_result")
        assert tool_result["tool_use_id"] == "tu_1"
        assert tool_result["content"] == "file contents"
        assert tool_result["is_error"] is False

    def test_sdk_runner_captures_result_message(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello", env))

        assert t.num_turns == 2
        assert t.total_cost_usd == pytest.approx(0.005)
        assert t.result["session_id"] == "sess-123"
        assert t.result["is_error"] is False

    def test_sdk_runner_passes_setting_sources_as_project(self, tmp_path):
        """SDKRunner must restrict setting_sources to trial dir — no user settings."""
        from evals.harness.sdk_runner import SDKRunner
        from claude_agent_sdk.types import ClaudeAgentOptions

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        captured_options: list[ClaudeAgentOptions] = []

        async def fake_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            return
            yield  # make it an async generator

        with patch("evals.harness.sdk_runner.query", side_effect=fake_query):
            t = asyncio.run(runner.run("hello", env))

        assert len(captured_options) == 1
        assert captured_options[0].setting_sources == ["project"]

    def test_sdk_runner_passes_cwd_and_env(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner
        from claude_agent_sdk.types import ClaudeAgentOptions

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        captured_options: list[ClaudeAgentOptions] = []

        async def fake_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            return
            yield

        with patch("evals.harness.sdk_runner.query", side_effect=fake_query):
            asyncio.run(runner.run("hello", env))

        opts = captured_options[0]
        assert opts.cwd == tmp_path
        assert opts.env["FINANCE_HUB_DB"] == str(tmp_path / "db.sqlite")
        assert "ANTHROPIC_API_KEY" not in opts.env

    def test_sdk_runner_passes_model_and_max_turns(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner
        from claude_agent_sdk.types import ClaudeAgentOptions

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        captured_options: list[ClaudeAgentOptions] = []

        async def fake_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            return
            yield

        with patch("evals.harness.sdk_runner.query", side_effect=fake_query):
            asyncio.run(runner.run("hello", env))

        opts = captured_options[0]
        assert opts.model == "claude-sonnet-5"
        assert opts.max_turns == 10

    def test_sdk_runner_transcript_is_jsonl_serialisable(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner

        runner = SDKRunner()
        env = self._make_env(tmp_path)

        with patch("evals.harness.sdk_runner.query", return_value=self._fake_query_result()):
            t = asyncio.run(runner.run("hello", env))

        out = tmp_path / "transcript.jsonl"
        t.write_jsonl(out)
        loaded = Transcript.read_jsonl(out)
        assert len(loaded.events) == len(t.events)
        assert loaded.num_turns == t.num_turns


# ---------------------------------------------------------------------------
# CLIRunner — stub construction and config
# ---------------------------------------------------------------------------

class TestCLIRunner:
    def test_cli_runner_is_a_runner(self):
        from evals.harness.cli_runner import CLIRunner
        from evals.harness.runner import Runner

        runner = CLIRunner()
        assert isinstance(runner, Runner)

    def test_cli_runner_accepts_custom_cli_path(self):
        from evals.harness.cli_runner import CLIRunner

        runner = CLIRunner(cli_path="/usr/local/bin/claude")
        assert runner.cli_path == "/usr/local/bin/claude"
