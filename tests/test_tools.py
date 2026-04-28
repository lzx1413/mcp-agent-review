import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from mcp_agent_review.tools import _safe_resolve, _is_sensitive, execute_tool_call


class TestSafeResolve:
    def test_normal_path(self, tmp_path):
        result = _safe_resolve(str(tmp_path), "src/main.py")
        assert result is not None
        assert result.startswith(str(tmp_path.resolve()))

    def test_path_traversal_blocked(self, tmp_path):
        result = _safe_resolve(str(tmp_path), "../../etc/passwd")
        assert result is None

    def test_absolute_path_outside_blocked(self, tmp_path):
        result = _safe_resolve(str(tmp_path), "/etc/passwd")
        assert result is None

    def test_root_itself_allowed(self, tmp_path):
        result = _safe_resolve(str(tmp_path), ".")
        assert result is not None

    def test_dot_dot_in_middle_blocked(self, tmp_path):
        result = _safe_resolve(str(tmp_path), "src/../../etc/passwd")
        assert result is None

    def test_symlink_escape_blocked(self, tmp_path):
        target = tmp_path / "escape"
        target.symlink_to("/etc")
        result = _safe_resolve(str(tmp_path), "escape/passwd")
        assert result is None


class TestExecuteToolCall:
    def test_unknown_tool(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: "/tmp")
        result = execute_tool_call("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_read_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call("read_file", {"path": "does_not_exist.py"})
        assert "File not found" in result

    def test_read_file_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call("read_file", {"path": "../../etc/passwd"})
        assert "Access denied" in result

    def test_read_file_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        f = tmp_path / "hello.py"
        f.write_text("print('hello')\n")
        result = execute_tool_call("read_file", {"path": "hello.py"})
        assert "print('hello')" in result

    def test_read_file_truncation(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        monkeypatch.setattr("mcp_agent_review.tools.MAX_FILE_LINES", 5)
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"line{i}" for i in range(100)))
        result = execute_tool_call("read_file", {"path": "big.py"})
        assert "truncated" in result

    def test_grep_code_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call("grep_code", {"pattern": "test", "path": "../../etc"})
        assert "Access denied" in result

    def test_git_blame_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call(
            "git_blame",
            {"path": "../../etc/passwd", "line_start": 1, "line_end": 5},
        )
        assert "Access denied" in result

    def test_list_files_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call("list_files", {"path": "../../etc"})
        assert "Access denied" in result

    def test_list_files_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        (tmp_path / "subdir").mkdir()
        result = execute_tool_call("list_files", {"path": "."})
        assert "a.py" in result
        assert "b.py" in result
        assert "d subdir" in result

    def test_list_files_not_a_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        (tmp_path / "file.txt").touch()
        result = execute_tool_call("list_files", {"path": "file.txt"})
        assert "Not a directory" in result

    def test_tool_timeout(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: "/tmp")
        monkeypatch.setattr(
            "mcp_agent_review.tools.run_in_repo",
            MagicMock(side_effect=subprocess.TimeoutExpired(cmd="test", timeout=5)),
        )
        result = execute_tool_call("grep_code", {"pattern": "test"})
        assert "timed out" in result


class TestIsSensitive:
    def test_env_file(self):
        assert _is_sensitive(".env") is True

    def test_env_variant(self):
        assert _is_sensitive(".env.production") is True

    def test_pem_file(self):
        assert _is_sensitive("server.pem") is True

    def test_key_file(self):
        assert _is_sensitive("private.key") is True

    def test_credentials_json(self):
        assert _is_sensitive("credentials.json") is True

    def test_service_account(self):
        assert _is_sensitive("service-account-key.json") is True

    def test_ssh_key(self):
        assert _is_sensitive("id_rsa") is True
        assert _is_sensitive("id_ed25519") is True

    def test_netrc(self):
        assert _is_sensitive(".netrc") is True

    def test_normal_file_allowed(self):
        assert _is_sensitive("main.py") is False
        assert _is_sensitive("README.md") is False
        assert _is_sensitive("pyproject.toml") is False

    def test_path_with_directories(self):
        assert _is_sensitive("config/.env") is True
        assert _is_sensitive("certs/server.pem") is True


class TestSensitiveFileBlocking:
    def test_read_file_env_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        (tmp_path / ".env").write_text("SECRET=abc123")
        result = execute_tool_call("read_file", {"path": ".env"})
        assert "Access denied" in result
        assert "sensitive" in result

    def test_read_file_pem_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        (tmp_path / "server.pem").write_text("-----BEGIN CERTIFICATE-----")
        result = execute_tool_call("read_file", {"path": "server.pem"})
        assert "Access denied" in result

    def test_read_file_nested_env_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / ".env.production").write_text("KEY=val")
        result = execute_tool_call("read_file", {"path": "config/.env.production"})
        assert "Access denied" in result

    def test_git_blame_env_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        result = execute_tool_call(
            "git_blame", {"path": ".env", "line_start": 1, "line_end": 5}
        )
        assert "Access denied" in result

    def test_grep_excludes_sensitive_patterns(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.tools.get_git_root", lambda: str(tmp_path))
        calls = []

        def capture_run(cmd, **kwargs):
            calls.append(cmd)
            return "(empty)"

        monkeypatch.setattr("mcp_agent_review.tools.run_in_repo", capture_run)
        execute_tool_call("grep_code", {"pattern": "password"})
        assert len(calls) == 1
        cmd = calls[0]
        assert "--no-follow" in cmd
        assert any("--exclude=.env" in arg for arg in cmd)
