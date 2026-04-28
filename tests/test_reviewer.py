import json
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from mcp_agent_review.prompts import build_system_prompt
from mcp_agent_review.reviewer import (
    build_user_message,
    format_review_output,
    run_agentic_review,
    run_self_critique,
)


class TestBuildSystemPrompt:
    def test_base_prompt_without_extras(self):
        result = build_system_prompt()
        assert "senior code reviewer" in result
        assert "Developer Intent" not in result
        assert "Directed Focus" not in result

    def test_with_task_description(self):
        result = build_system_prompt(task_description="fix race condition in pool")
        assert "Developer Intent" in result
        assert "fix race condition in pool" in result
        assert "achieves this intent" in result

    def test_with_review_focus(self):
        result = build_system_prompt(review_focus="security")
        assert "Directed Focus" in result
        assert "security" in result
        assert "dig deeper" in result

    def test_with_both(self):
        result = build_system_prompt(
            task_description="add caching layer",
            review_focus="performance",
        )
        assert "Developer Intent" in result
        assert "add caching layer" in result
        assert "Directed Focus" in result
        assert "performance" in result

    def test_none_values_same_as_no_args(self):
        assert build_system_prompt(None, None) == build_system_prompt()


class TestBuildUserMessage:
    def test_contains_diff(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.reviewer.get_claude_md", lambda: "")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_git_log", lambda: "abc123 init")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_commit_messages", lambda base=None: "(empty)")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_changed_files", lambda base=None: [])
        monkeypatch.setattr("mcp_agent_review.reviewer.read_changed_files_context", lambda files, diff: "")
        result = build_user_message("+ added line", base=None)
        assert "+ added line" in result
        assert "Diff to Review" in result

    def test_includes_claude_md(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.reviewer.get_claude_md", lambda: "Use pytest for tests.")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_git_log", lambda: "abc init")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_commit_messages", lambda base=None: "(empty)")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_changed_files", lambda base=None: [])
        monkeypatch.setattr("mcp_agent_review.reviewer.read_changed_files_context", lambda files, diff: "")
        result = build_user_message("diff")
        assert "Project Guidelines" in result
        assert "Use pytest for tests" in result

    def test_includes_commit_messages(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.reviewer.get_claude_md", lambda: "")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_git_log", lambda: "abc init")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_commit_messages", lambda base=None: "abc fix: bug")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_changed_files", lambda base=None: [])
        monkeypatch.setattr("mcp_agent_review.reviewer.read_changed_files_context", lambda files, diff: "")
        result = build_user_message("diff", base="main")
        assert "Commit Messages" in result

    def test_includes_file_context(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.reviewer.get_claude_md", lambda: "")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_git_log", lambda: "abc init")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_commit_messages", lambda base=None: "(empty)")
        monkeypatch.setattr("mcp_agent_review.reviewer.get_changed_files", lambda base=None: ["a.py"])
        monkeypatch.setattr("mcp_agent_review.reviewer.read_changed_files_context", lambda files, diff: "### a.py\n```\ncode\n```")
        result = build_user_message("diff")
        assert "Changed Files" in result


class TestFormatReviewOutput:
    def test_valid_json_with_findings(self):
        data = {
            "findings": [
                {
                    "confidence": "HIGH",
                    "category": "logic_error",
                    "file": "main.py",
                    "line": 42,
                    "summary": "Off-by-one error",
                    "explanation": "Loop iterates one too many times.",
                }
            ],
            "assessment": "One issue found.",
        }
        result = format_review_output(json.dumps(data))
        assert "**[HIGH] logic_error**" in result
        assert "main.py:42" in result
        assert "Off-by-one error" in result
        assert "One issue found" in result

    def test_valid_json_no_findings(self):
        data = {"findings": [], "assessment": "Code looks good."}
        result = format_review_output(json.dumps(data))
        assert "No issues found" in result
        assert "Code looks good" in result

    def test_plain_text_passthrough(self):
        raw = "This is not JSON, just a text review."
        result = format_review_output(raw)
        assert result == raw

    def test_empty_findings_no_assessment(self):
        data = {"findings": []}
        result = format_review_output(json.dumps(data))
        assert result == "No issues found."

    def test_finding_without_line_number(self):
        data = {
            "findings": [
                {
                    "confidence": "MEDIUM",
                    "category": "security",
                    "file": "config.py",
                    "summary": "Hardcoded secret",
                    "explanation": "API key in source.",
                }
            ],
            "assessment": "",
        }
        result = format_review_output(json.dumps(data))
        assert "config.py" in result
        assert ":**" not in result or "config.py:" not in result.split("File:")[1].split("`")[1] if ":" in result.split("File:")[1].split("`")[1] else True


def _make_mock_response(content=None, tool_calls=None, finish_reason="stop"):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    return response


class TestRunAgenticReview:
    def test_no_tool_calls_returns_content(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_response(
            content="All good.", finish_reason="stop"
        )
        messages = [{"role": "system", "content": "review"}, {"role": "user", "content": "diff"}]
        result = run_agentic_review(client, messages)
        assert result == "All good."

    def test_tool_loop_and_termination(self, monkeypatch):
        tc = MagicMock()
        tc.function.name = "read_file"
        tc.function.arguments = '{"path": "foo.py"}'
        tc.id = "call_1"

        resp_with_tools = _make_mock_response(
            tool_calls=[tc], finish_reason="tool_calls"
        )
        resp_final = _make_mock_response(content="Found a bug.", finish_reason="stop")

        client = MagicMock()
        client.chat.completions.create.side_effect = [resp_with_tools, resp_final]

        monkeypatch.setattr(
            "mcp_agent_review.reviewer.execute_tool_call",
            lambda name, args: "file content here",
        )

        messages = [{"role": "system", "content": "review"}, {"role": "user", "content": "diff"}]
        result = run_agentic_review(client, messages)
        assert result == "Found a bug."
        assert client.chat.completions.create.call_count == 2

    def test_max_rounds_returns_none(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.reviewer.MAX_TOOL_ROUNDS", 2)

        tc = MagicMock()
        tc.function.name = "grep_code"
        tc.function.arguments = '{"pattern": "test"}'
        tc.id = "call_1"

        resp = _make_mock_response(tool_calls=[tc], finish_reason="tool_calls")
        client = MagicMock()
        client.chat.completions.create.return_value = resp

        monkeypatch.setattr(
            "mcp_agent_review.reviewer.execute_tool_call",
            lambda name, args: "results",
        )

        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        result = run_agentic_review(client, messages)
        assert result is None
        assert client.chat.completions.create.call_count == 2

    def test_progress_callback(self, monkeypatch):
        tc = MagicMock()
        tc.function.name = "read_file"
        tc.function.arguments = '{"path": "x.py"}'
        tc.id = "call_1"

        resp_tools = _make_mock_response(tool_calls=[tc], finish_reason="tool_calls")
        resp_final = _make_mock_response(content="done", finish_reason="stop")

        client = MagicMock()
        client.chat.completions.create.side_effect = [resp_tools, resp_final]
        monkeypatch.setattr(
            "mcp_agent_review.reviewer.execute_tool_call",
            lambda name, args: "content",
        )

        progress = []
        run_agentic_review(
            client,
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            on_progress=lambda r, m: progress.append((r, m)),
        )
        assert len(progress) == 1
        assert progress[0][0] == 1


class TestRunSelfCritique:
    def test_does_not_mutate_messages(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_response(
            content='{"findings": []}'
        )
        original = [
            {"role": "system", "content": "review"},
            {"role": "user", "content": "diff"},
        ]
        messages = list(original)
        run_self_critique(client, messages)
        assert messages == original

    def test_returns_model_content(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_response(
            content='{"findings": [], "assessment": "all good"}'
        )
        result = run_self_critique(
            client,
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        )
        assert "all good" in result
