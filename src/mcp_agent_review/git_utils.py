import os
import re
import subprocess
from fnmatch import fnmatch

from .constants import SENSITIVE_PATTERNS


def get_git_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return result.stdout.strip() or "."


def run_in_repo(cmd: list[str], max_lines: int = 200, timeout: int = 30) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=get_git_root(), timeout=timeout
    )
    output = result.stdout.strip()
    if result.returncode != 0 and result.stderr:
        output = f"[stderr] {result.stderr.strip()}\n{output}"
    lines = output.splitlines()
    if len(lines) > max_lines:
        output = (
            "\n".join(lines[:max_lines])
            + f"\n... [truncated, {len(lines)} lines total]"
        )
    return output or "(empty)"


def get_git_diff(base: str | None = None) -> str:
    cwd = get_git_root()
    if base:
        result = subprocess.run(
            ["git", "diff", "-U20", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.stdout.strip()
    result = subprocess.run(
        ["git", "diff", "-U20", "HEAD"], capture_output=True, text=True, cwd=cwd
    )
    diff = result.stdout.strip()
    if not diff:
        result = subprocess.run(
            ["git", "diff", "-U20", "--cached"], capture_output=True, text=True, cwd=cwd
        )
        diff = result.stdout.strip()
    return diff


def get_claude_md() -> str:
    path = os.path.join(get_git_root(), "CLAUDE.md")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def get_git_log(n: int = 10) -> str:
    return run_in_repo(["git", "log", f"-{n}", "--oneline", "--no-decorate"])


def get_changed_files(base: str | None = None) -> list[str]:
    if base:
        output = run_in_repo(["git", "diff", f"{base}...HEAD", "--name-only"])
    else:
        output = run_in_repo(["git", "diff", "HEAD", "--name-only"])
        if output == "(empty)":
            output = run_in_repo(["git", "diff", "--cached", "--name-only"])
    return [f for f in output.splitlines() if f and not f.startswith("[")]


def get_commit_messages(base: str | None = None) -> str:
    if base:
        return run_in_repo(
            ["git", "log", f"{base}...HEAD", "--format=%h %s%n%b", "--no-decorate"],
            max_lines=60,
        )
    return run_in_repo(
        ["git", "log", "-5", "--format=%h %s%n%b", "--no-decorate"], max_lines=60
    )


def parse_diff_line_ranges(diff: str) -> dict[str, list[tuple[int, int]]]:
    file_ranges: dict[str, list[tuple[int, int]]] = {}
    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif line.startswith("@@ ") and current_file:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                file_ranges.setdefault(current_file, []).append(
                    (start, start + count - 1)
                )
    return file_ranges


CONTEXT_PADDING = 50


def merge_ranges(
    ranges: list[tuple[int, int]], total: int
) -> list[tuple[int, int]]:
    if not ranges:
        return []
    padded = [
        (max(1, s - CONTEXT_PADDING), min(total, e + CONTEXT_PADDING))
        for s, e in ranges
    ]
    padded.sort()
    merged = [padded[0]]
    for s, e in padded[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def read_changed_files_context(
    files: list[str], diff: str, max_file_lines: int = 1000
) -> str:
    root = get_git_root()
    file_ranges = parse_diff_line_ranges(diff)
    parts = []
    for f in files:
        basename = os.path.basename(f)
        if any(fnmatch(basename, pat) for pat in SENSITIVE_PATTERNS):
            continue
        full = os.path.join(root, f)
        if not os.path.exists(full):
            continue
        try:
            with open(full) as fh:
                all_lines = fh.readlines()
        except Exception:
            continue
        total = len(all_lines)
        ranges = file_ranges.get(f)
        if not ranges:
            content = "".join(all_lines[:max_file_lines])
            if total > max_file_lines:
                content += f"\n... [{total} lines total, truncated]"
            parts.append(f"### {f}\n```\n{content}\n```")
            continue
        merged = merge_ranges(ranges, total)
        snippets = []
        for start, end in merged:
            header = f"[lines {start}-{end}]"
            snippet = "".join(all_lines[start - 1 : end])
            snippets.append(f"{header}\n{snippet}")
        parts.append(
            f"### {f} ({total} lines total)\n```\n{''.join(snippets)}```"
        )
    return "\n\n".join(parts)
