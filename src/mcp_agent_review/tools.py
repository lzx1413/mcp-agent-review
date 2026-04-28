import json
import os
import subprocess
from fnmatch import fnmatch

from .git_utils import get_git_root, run_in_repo

MAX_FILE_LINES = int(os.environ.get("MAX_FILE_LINES", "1000"))

SENSITIVE_PATTERNS = [
    ".env", ".env.*",
    "*.pem", "*.key", "*.p12", "*.pfx",
    "*.jks", "*.keystore",
    "id_rsa", "id_ed25519", "id_ecdsa",
    "credentials.json", "service-account*.json",
    ".netrc", ".pgpass", ".my.cnf",
    "*.secret", "secrets.*",
]


def _is_sensitive(path: str) -> bool:
    basename = os.path.basename(path)
    return any(fnmatch(basename, pat) for pat in SENSITIVE_PATTERNS)


GREP_INCLUDES = [
    "--include=*.kt",
    "--include=*.java",
    "--include=*.cpp",
    "--include=*.h",
    "--include=*.c",
    "--include=*.py",
    "--include=*.gradle",
    "--include=*.kts",
    "--include=*.xml",
    "--include=*.toml",
    "--include=*.cmake",
    "--include=*.md",
    "--include=*.json",
    "--include=*.properties",
    "--include=*.ts",
    "--include=*.tsx",
    "--include=*.js",
    "--include=*.jsx",
    "--include=*.go",
    "--include=*.rs",
    "--include=*.swift",
    "--include=*.rb",
    "--include=*.yaml",
    "--include=*.yml",
]

GPT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_code",
            "description": "Search for a regex pattern across the codebase",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (relative to repo root)",
                        "default": ".",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional glob to narrow file types, e.g. '*.kt' or '*.cpp'",
                        "default": "",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_blame",
            "description": "Show git blame for a specific file and line range",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "line_start": {
                        "type": "integer",
                        "description": "Start line number",
                    },
                    "line_end": {
                        "type": "integer",
                        "description": "End line number",
                    },
                },
                "required": ["path", "line_start", "line_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories to understand project structure",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to repo root",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list up to 3 directory levels deep",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_git_history",
            "description": "Search git history for a string (pickaxe) or show history of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "String to search for in commit diffs (git log -S). Leave empty for file history.",
                        "default": "",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path to show history for (optional)",
                        "default": "",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_test_files",
            "description": "Find test files related to a given source file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Source file path to find tests for",
                    },
                },
                "required": ["path"],
            },
        },
    },
]


def _safe_resolve(root: str, relative: str) -> str | None:
    resolved = os.path.realpath(os.path.join(root, relative))
    if not resolved.startswith(os.path.realpath(root) + os.sep) and resolved != os.path.realpath(root):
        return None
    return resolved


def execute_tool_call(name: str, args: dict) -> str:
    root = get_git_root()
    try:
        if name == "read_file":
            path = _safe_resolve(root, args["path"])
            if path is None:
                return f"Access denied: path escapes repository"
            if _is_sensitive(args["path"]):
                return f"Access denied: sensitive file blocked: {args['path']}"
            if not os.path.exists(path):
                return f"File not found: {args['path']}"
            with open(path) as f:
                lines = f.readlines()
            content = "".join(lines[:MAX_FILE_LINES])
            if len(lines) > MAX_FILE_LINES:
                content += f"\n... [{len(lines)} lines total, truncated]"
            return content

        elif name == "grep_code":
            search_path = args.get("path", ".")
            if _safe_resolve(root, search_path) is None:
                return "Access denied: path escapes repository"
            file_pattern = args.get("file_pattern", "")
            if file_pattern:
                includes = [f"--include={file_pattern}"]
            else:
                includes = list(GREP_INCLUDES)
            excludes = [f"--exclude={pat}" for pat in SENSITIVE_PATTERNS]
            return run_in_repo(
                ["grep", "-rn", "--no-follow"] + includes + excludes + ["-E", args["pattern"], search_path],
                max_lines=100,
                timeout=5,
            )

        elif name == "git_blame":
            if _safe_resolve(root, args["path"]) is None:
                return "Access denied: path escapes repository"
            if _is_sensitive(args["path"]):
                return f"Access denied: sensitive file blocked: {args['path']}"
            return run_in_repo(
                [
                    "git",
                    "blame",
                    f"-L{args['line_start']},{args['line_end']}",
                    args["path"],
                ]
            )

        elif name == "list_files":
            target = _safe_resolve(root, args.get("path", "."))
            if target is None:
                return "Access denied: path escapes repository"
            if not os.path.isdir(target):
                return f"Not a directory: {args.get('path', '.')}"
            recursive = args.get("recursive", False)
            if recursive:
                return run_in_repo(
                    [
                        "find",
                        args.get("path", "."),
                        "-maxdepth",
                        "3",
                        "-not",
                        "-path",
                        "*/.git/*",
                    ],
                    max_lines=150,
                )
            entries = sorted(os.listdir(target))
            result_lines = []
            for e in entries:
                full = os.path.join(target, e)
                prefix = "d " if os.path.isdir(full) else "f "
                result_lines.append(prefix + e)
            return "\n".join(result_lines) or "(empty directory)"

        elif name == "search_git_history":
            query = args.get("query", "")
            path = args.get("path", "")
            cmd = ["git", "log", "--oneline", "--no-decorate", "-20"]
            if query:
                cmd += ["-S", query]
            if path:
                cmd += ["--", path]
            return run_in_repo(cmd, max_lines=30)

        elif name == "find_test_files":
            src_path = args["path"]
            basename = os.path.splitext(os.path.basename(src_path))[0]
            patterns = [
                f"*{basename}Test*",
                f"*{basename}Spec*",
                f"*test*{basename}*",
                f"*Test{basename}*",
            ]
            cmd = ["find", ".", "-type", "f", "("]
            for i, p in enumerate(patterns):
                if i > 0:
                    cmd.append("-o")
                cmd += ["-name", p]
            cmd += [")", "-not", "-path", "*/.git/*"]
            return run_in_repo(cmd, max_lines=30, timeout=5)

        return f"Unknown tool: {name}"
    except subprocess.TimeoutExpired:
        return f"Tool {name} timed out"
    except Exception as e:
        return f"Tool {name} error: {e}"
