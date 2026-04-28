import os
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from mcp_agent_review.git_utils import (
    parse_diff_line_ranges,
    merge_ranges,
    read_changed_files_context,
    get_git_root,
    run_in_repo,
)


class TestParseDiffLineRanges:
    def test_single_file_single_hunk(self):
        diff = textwrap.dedent("""\
            diff --git a/foo.py b/foo.py
            --- a/foo.py
            +++ b/foo.py
            @@ -10,6 +10,8 @@ def hello():
                 pass
            +    new_line
        """)
        result = parse_diff_line_ranges(diff)
        assert "foo.py" in result
        assert result["foo.py"] == [(10, 17)]

    def test_single_file_multiple_hunks(self):
        diff = textwrap.dedent("""\
            +++ b/foo.py
            @@ -1,3 +1,4 @@
             a
            +b
            @@ -50,2 +51,3 @@
             c
            +d
        """)
        result = parse_diff_line_ranges(diff)
        assert len(result["foo.py"]) == 2
        assert result["foo.py"][0] == (1, 4)
        assert result["foo.py"][1] == (51, 53)

    def test_multiple_files(self):
        diff = textwrap.dedent("""\
            +++ b/a.py
            @@ -5,4 +5,4 @@
             x
            +++ b/b.py
            @@ -20,2 +20,3 @@
             y
        """)
        result = parse_diff_line_ranges(diff)
        assert "a.py" in result
        assert "b.py" in result

    def test_single_line_hunk(self):
        diff = "+++ b/x.py\n@@ -0,0 +1 @@\n+new\n"
        result = parse_diff_line_ranges(diff)
        assert result["x.py"] == [(1, 1)]

    def test_empty_diff(self):
        assert parse_diff_line_ranges("") == {}

    def test_no_hunk_headers(self):
        diff = "+++ b/foo.py\nsome random text\n"
        result = parse_diff_line_ranges(diff)
        assert result == {}


class TestMergeRanges:
    def test_empty_list(self):
        assert merge_ranges([], 100) == []

    def test_single_range(self):
        result = merge_ranges([(50, 60)], 200)
        assert len(result) == 1
        assert result[0] == (1, 110)  # 50-50=0 -> clamped to 1, 60+50=110

    def test_non_overlapping(self):
        result = merge_ranges([(10, 20), (200, 210)], 500)
        assert len(result) == 2

    def test_overlapping_after_padding(self):
        result = merge_ranges([(10, 20), (60, 70)], 500)
        assert len(result) == 1

    def test_clamps_to_bounds(self):
        result = merge_ranges([(1, 5)], 10)
        assert result[0][0] == 1
        assert result[0][1] == 10  # 5+50=55, clamped to total=10

    def test_already_overlapping(self):
        result = merge_ranges([(10, 30), (20, 40)], 500)
        assert len(result) == 1


class TestReadChangedFilesContext:
    def test_file_not_found_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        result = read_changed_files_context(["nonexistent.py"], "")
        assert result == ""

    def test_file_without_diff_ranges(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        f = tmp_path / "hello.py"
        f.write_text("line1\nline2\nline3\n")
        result = read_changed_files_context(["hello.py"], "")
        assert "hello.py" in result
        assert "line1" in result

    def test_file_with_diff_ranges(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        content = "\n".join(f"line{i}" for i in range(1, 201))
        f = tmp_path / "big.py"
        f.write_text(content)
        diff = "+++ b/big.py\n@@ -100,3 +100,4 @@\n ctx\n+new\n"
        result = read_changed_files_context(["big.py"], diff)
        assert "big.py" in result
        assert "200 lines total" in result

    def test_truncation(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        content = "\n".join(f"L{i}" for i in range(2000))
        f = tmp_path / "huge.py"
        f.write_text(content)
        result = read_changed_files_context(["huge.py"], "", max_file_lines=50)
        assert "truncated" in result


class TestRunInRepo:
    def test_truncates_long_output(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: "/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="\n".join(f"line{i}" for i in range(500)),
                returncode=0,
                stderr="",
            )
            result = run_in_repo(["echo", "test"], max_lines=10)
            assert "truncated" in result

    def test_empty_output(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: "/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0, stderr="")
            result = run_in_repo(["echo"])
            assert result == "(empty)"

    def test_stderr_included_on_error(self, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: "/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", returncode=1, stderr="fatal: error"
            )
            result = run_in_repo(["git", "log"])
            assert "[stderr]" in result


class TestSensitiveFileFiltering:
    def test_read_changed_files_skips_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        (tmp_path / ".env").write_text("SECRET=abc123")
        (tmp_path / "main.py").write_text("print('hello')")
        result = read_changed_files_context([".env", "main.py"], "")
        assert "main.py" in result
        assert "SECRET" not in result
        assert ".env" not in result.split("main.py")[0]

    def test_read_changed_files_skips_pem(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        (tmp_path / "cert.pem").write_text("-----BEGIN CERTIFICATE-----")
        result = read_changed_files_context(["cert.pem"], "")
        assert result == ""

    def test_read_changed_files_skips_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mcp_agent_review.git_utils.get_git_root", lambda: str(tmp_path))
        (tmp_path / "credentials.json").write_text('{"key": "secret"}')
        (tmp_path / "app.py").write_text("import os")
        result = read_changed_files_context(["credentials.json", "app.py"], "")
        assert "app.py" in result
        assert "secret" not in result
