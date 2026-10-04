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
        # Blanked (not absent): the SDK merges os.environ under options.env.
        assert opts.env["ANTHROPIC_API_KEY"] == ""

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


# ---------------------------------------------------------------------------
# Trial lockdown — only the finance-hub MCP tools are reachable
# ---------------------------------------------------------------------------

# Seen in the 2026-10-04 ground-truth trial before the lockdown: built-ins that can
# exfiltrate, mutate the host, or act on the user's behalf.
_DANGEROUS_TOOLS = {
    "Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Task",
    "CronCreate", "RemoteTrigger", "PushNotification", "Workflow", "SendMessage",
    "Read", "Skill",
}


def _lockdown_env(tmp_path, **kw):
    return TrialEnv(
        cwd=tmp_path,
        env={"FINANCE_HUB_DB": str(tmp_path / "db.sqlite")},
        mcp_servers={"finance-hub": {"command": "py3env/bin/finance-mcp",
                                     "env": {"FINANCE_HUB_DB": str(tmp_path / "db.sqlite")}}},
        model="claude-sonnet-5",
        **kw,
    )


class TestSDKLockdown:
    def _opts(self, tmp_path):
        from evals.harness.sdk_runner import build_options
        return build_options(_lockdown_env(tmp_path))

    def _argv(self, tmp_path):
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
        import dataclasses
        opts = dataclasses.replace(self._opts(tmp_path), cli_path="claude")  # skip CLI discovery
        return SubprocessCLITransport(prompt="p", options=opts)._build_command()

    def test_builtin_tools_restricted_to_toolsearch(self, tmp_path):
        opts = self._opts(tmp_path)
        assert opts.tools == ["ToolSearch"]
        assert not _DANGEROUS_TOOLS & set(opts.tools)

    def test_only_trial_mcp_servers_preapproved(self, tmp_path):
        opts = self._opts(tmp_path)
        assert opts.allowed_tools == ["ToolSearch", "mcp__finance-hub"]
        assert not _DANGEROUS_TOOLS & set(opts.allowed_tools)

    def test_permission_mode_denies_unapproved_tools(self, tmp_path):
        assert self._opts(tmp_path).permission_mode == "dontAsk"

    def test_parent_process_api_key_masked(self, tmp_path, monkeypatch):
        """SDK merges os.environ under options.env — only an explicit blank masks it."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
        assert self._opts(tmp_path).env["ANTHROPIC_API_KEY"] == ""

    def test_strict_mcp_config_and_connectors_disabled(self, tmp_path):
        opts = self._opts(tmp_path)
        assert opts.strict_mcp_config is True
        assert opts.env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"
        assert opts.env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
        assert set(opts.mcp_servers) == {"finance-hub"}

    def test_cli_argv_built_by_sdk_carries_lockdown(self, tmp_path):
        argv = self._argv(tmp_path)
        assert argv[argv.index("--tools") + 1] == "ToolSearch"
        assert argv[argv.index("--allowedTools") + 1] == "ToolSearch,mcp__finance-hub"
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
        assert "--strict-mcp-config" in argv
        assert "--setting-sources=project" in argv
        assert "bypassPermissions" not in argv
        assert "--dangerously-skip-permissions" not in argv
        mcp = json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]
        assert set(mcp) == {"finance-hub"}

    def test_mcp_command_resolved_to_repo_py3env(self, tmp_path):
        from evals.harness.runner import _REPO_ROOT
        cmd = self._opts(tmp_path).mcp_servers["finance-hub"]["command"]
        assert cmd == str(_REPO_ROOT / "py3env" / "bin" / "finance-mcp")


class TestResolveMcpServers:
    def test_relative_path_command_anchored_to_root(self, tmp_path):
        from evals.harness.runner import resolve_mcp_servers
        out = resolve_mcp_servers({"s": {"command": "py3env/bin/x", "env": {"A": "1"}}}, root=tmp_path)
        assert out == {"s": {"command": str(tmp_path / "py3env/bin/x"), "env": {"A": "1"}}}

    def test_bare_and_absolute_commands_unchanged(self, tmp_path):
        from evals.harness.runner import resolve_mcp_servers
        servers = {"a": {"command": "finance-mcp"}, "b": {"command": "/usr/bin/x"}}
        assert resolve_mcp_servers(servers, root=tmp_path) == servers

    def test_input_not_mutated(self, tmp_path):
        from evals.harness.runner import resolve_mcp_servers
        servers = {"s": {"command": "py3env/bin/x"}}
        resolve_mcp_servers(servers, root=tmp_path)
        assert servers == {"s": {"command": "py3env/bin/x"}}

    def test_runtime_mcp_json_command_resolves_to_py3env_executable(self):
        """The shipped runtime/mcp.json must start the repo's py3env finance-mcp in a trial."""
        from evals.harness.runner import _REPO_ROOT, resolve_mcp_servers
        raw = json.loads((_REPO_ROOT / "runtime" / "mcp.json").read_text())["mcpServers"]
        cmd = Path(resolve_mcp_servers(raw)["finance-hub"]["command"])
        assert cmd.is_absolute() and "py3env" in cmd.parts
        assert cmd.exists(), f"{cmd} missing — trial MCP server would fail to start"


class TestBridgeProjectContext:
    def test_runtime_claude_md_exposed_at_trial_root(self, tmp_path):
        from evals.harness.runner import bridge_project_context
        (tmp_path / "runtime").mkdir()
        (tmp_path / "runtime" / "CLAUDE.md").write_text("# runtime")
        bridge_project_context(tmp_path)
        assert (tmp_path / "CLAUDE.md").read_text() == "# runtime"
        assert (tmp_path / "CLAUDE.md").is_symlink()

    def test_noop_without_runtime_claude_md(self, tmp_path):
        from evals.harness.runner import bridge_project_context
        bridge_project_context(tmp_path)
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_existing_root_claude_md_untouched(self, tmp_path):
        from evals.harness.runner import bridge_project_context
        (tmp_path / "runtime").mkdir()
        (tmp_path / "runtime" / "CLAUDE.md").write_text("# runtime")
        (tmp_path / "CLAUDE.md").write_text("# root")
        bridge_project_context(tmp_path)
        assert (tmp_path / "CLAUDE.md").read_text() == "# root"

    def test_idempotent(self, tmp_path):
        from evals.harness.runner import bridge_project_context
        (tmp_path / "runtime").mkdir()
        (tmp_path / "runtime" / "CLAUDE.md").write_text("# runtime")
        bridge_project_context(tmp_path)
        bridge_project_context(tmp_path)
        assert (tmp_path / "CLAUDE.md").read_text() == "# runtime"

    def test_sdk_runner_bridges_before_query(self, tmp_path):
        from evals.harness.sdk_runner import SDKRunner
        (tmp_path / "runtime").mkdir()
        (tmp_path / "runtime" / "CLAUDE.md").write_text("# runtime")
        seen = []

        async def fake_query(*, prompt, options=None, transport=None):
            seen.append((Path(options.cwd) / "CLAUDE.md").exists())
            return
            yield

        with patch("evals.harness.sdk_runner.query", side_effect=fake_query):
            asyncio.run(SDKRunner().run("p", _lockdown_env(tmp_path)))
        assert seen == [True]


# ---------------------------------------------------------------------------
# SDKRunner — message coverage (system init, rate limits, error flags)
# ---------------------------------------------------------------------------

class TestSDKRunnerMessageCoverage:
    def _run(self, tmp_path, msgs):
        from evals.harness.sdk_runner import SDKRunner

        async def _gen():
            for m in msgs:
                yield m

        with patch("evals.harness.sdk_runner.query", return_value=_gen()):
            return asyncio.run(SDKRunner().run("p", _lockdown_env(tmp_path)))

    def test_system_init_recorded(self, tmp_path):
        from claude_agent_sdk.types import SystemMessage
        init = {"type": "system", "subtype": "init", "tools": ["ToolSearch"],
                "mcp_servers": [{"name": "finance-hub", "status": "pending"}],
                "apiKeySource": "none", "cwd": str(tmp_path), "permissionMode": "dontAsk"}
        t = self._run(tmp_path, [SystemMessage(subtype="init", data=init)])
        assert [e.type for e in t.events] == ["system"]
        d = t.events[0].data
        assert d["subtype"] == "init"
        assert d["tools"] == ["ToolSearch"]
        assert d["mcp_servers"] == [{"name": "finance-hub", "status": "pending"}]
        assert d["apiKeySource"] == "none"
        assert d["cwd"] == str(tmp_path)

    def test_thinking_token_ticks_dropped(self, tmp_path):
        from claude_agent_sdk.types import SystemMessage
        t = self._run(tmp_path, [SystemMessage(subtype="thinking_tokens", data={"estimated_tokens": 5})])
        assert t.events == []

    def test_rate_limit_event_recorded_as_system(self, tmp_path):
        from claude_agent_sdk.types import RateLimitEvent, RateLimitInfo
        ev = RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed"), uuid="u", session_id="s")
        t = self._run(tmp_path, [ev])
        assert t.events[0].type == "system"
        assert t.events[0].data["subtype"] == "rate_limit_event"
        assert t.events[0].data["rate_limit_info"]["status"] == "allowed"

    def test_tool_result_is_error_none_becomes_false(self, tmp_path):
        from claude_agent_sdk.types import ToolResultBlock, UserMessage
        msg = UserMessage(content=[ToolResultBlock(tool_use_id="t", content=[{"type": "text", "text": "{}"}],
                                                   is_error=None)])
        t = self._run(tmp_path, [msg])
        assert t.events[0].data["content"][0]["is_error"] is False

    def test_assistant_stop_reason_and_error_recorded(self, tmp_path):
        from claude_agent_sdk.types import AssistantMessage, TextBlock, ThinkingBlock
        msg = AssistantMessage(content=[ThinkingBlock(thinking="", signature="sig"), TextBlock(text="hi")],
                               model="m", stop_reason="end_turn", error=None, message_id="msg_1")
        d = self._run(tmp_path, [msg]).events[0].data
        assert d["stop_reason"] == "end_turn"
        assert d["error"] is None
        assert d["message_id"] == "msg_1"
        assert d["content"] == [{"type": "thinking"}, {"type": "text", "text": "hi"}]

    def test_transcript_with_system_events_roundtrips(self, tmp_path):
        from claude_agent_sdk.types import SystemMessage
        t = self._run(tmp_path, [SystemMessage(subtype="init", data={"tools": []})])
        p = tmp_path / "t.jsonl"
        t.write_jsonl(p)
        assert Transcript.read_jsonl(p).events[0].data == {"tools": [], "subtype": "init"}


# ---------------------------------------------------------------------------
# CLIRunner — lockdown argv/env and stream-json → SDK event shape
# ---------------------------------------------------------------------------

def _fake_cli(tmp_path, lines):
    import stat
    import sys
    import textwrap
    dump = tmp_path / "invocation.json"
    script = tmp_path / "fake_claude"
    script.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, os, sys
        keys = ("ENABLE_CLAUDEAI_MCP_SERVERS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "ANTHROPIC_API_KEY")
        json.dump({{"argv": sys.argv, "env": {{k: os.environ.get(k) for k in keys}}}},
                  open({str(dump)!r}, "w"))
        for l in json.loads({json.dumps(lines)!r}):
            print(json.dumps(l))
        """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, dump


_STREAM_JSON = [
    {"type": "system", "subtype": "init", "tools": ["ToolSearch"], "apiKeySource": "none",
     "mcp_servers": [{"name": "finance-hub", "status": "pending"}], "session_id": "s"},
    {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 3},
    {"type": "assistant", "parent_tool_use_id": None, "session_id": "s", "message": {
        "id": "msg_1", "model": "m", "stop_reason": "tool_use", "usage": {"output_tokens": 1},
        "content": [{"type": "thinking", "thinking": "", "signature": "x"},
                    {"type": "tool_use", "id": "t1", "name": "mcp__finance-hub__health", "input": {}}]}},
    {"type": "user", "session_id": "s", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "{}"}]}]}},
    {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.01, "is_error": False},
]


class TestCLIRunnerLockdown:
    def _run(self, tmp_path):
        from evals.harness.cli_runner import CLIRunner
        script, dump = _fake_cli(tmp_path, _STREAM_JSON)
        t = asyncio.run(CLIRunner(str(script)).run("p", _lockdown_env(tmp_path)))
        return t, json.loads(dump.read_text())

    def test_argv_carries_lockdown(self, tmp_path):
        _, inv = self._run(tmp_path)
        argv = inv["argv"]
        assert argv[argv.index("--tools") + 1] == "ToolSearch"
        assert argv[argv.index("--allowedTools") + 1] == "ToolSearch,mcp__finance-hub"
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
        assert argv[argv.index("--setting-sources") + 1] == "project"
        assert "--strict-mcp-config" in argv
        mcp = json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]
        assert set(mcp) == {"finance-hub"}
        assert Path(mcp["finance-hub"]["command"]).is_absolute()

    def test_env_disables_connectors_and_strips_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
        _, inv = self._run(tmp_path)
        assert inv["env"] == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false",
                              "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                              "ANTHROPIC_API_KEY": ""}

    def test_events_match_sdk_shape(self, tmp_path):
        t, _ = self._run(tmp_path)
        assert [e.type for e in t.events] == ["system", "assistant", "user", "result"]
        init, asst, user, result = (e.data for e in t.events)
        assert init["subtype"] == "init" and init["tools"] == ["ToolSearch"]
        assert asst["content"] == [
            {"type": "thinking"},
            {"type": "tool_use", "id": "t1", "name": "mcp__finance-hub__health", "input": {}},
        ]
        assert asst["model"] == "m" and asst["stop_reason"] == "tool_use" and asst["message_id"] == "msg_1"
        assert user["content"] == [{"type": "tool_result", "tool_use_id": "t1",
                                    "content": [{"type": "text", "text": "{}"}], "is_error": False}]
        assert result["num_turns"] == 2 and t.total_cost_usd == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# Golden transcripts — harness Transcript format
# ---------------------------------------------------------------------------

_GOLDENS = sorted((Path(__file__).resolve().parent.parent / "evals" / "tasks").glob("*/golden/transcript.jsonl"))


@pytest.mark.parametrize("golden", _GOLDENS, ids=lambda p: p.parts[-3])
def test_golden_transcript_is_harness_format(golden):
    t = Transcript.read_jsonl(golden)
    assert {e.type for e in t.events} <= {"system", "user", "assistant"}
    assert t.events[0].type == "system" and t.events[0].data["subtype"] == "golden_metadata"
    uses = [b["id"] for e in t.events if e.type == "assistant"
            for b in e.data["content"] if b["type"] == "tool_use"]
    results = [b["tool_use_id"] for e in t.events if e.type == "user" and isinstance(e.data["content"], list)
               for b in e.data["content"] if b["type"] == "tool_result"]
    assert uses and uses == results, "every tool_use must be answered by its tool_result, in order"
    assert any(b["type"] == "text" for e in t.events if e.type == "assistant" for b in e.data["content"])
