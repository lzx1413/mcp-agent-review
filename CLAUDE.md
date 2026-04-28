# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
pip install -e .              # install in editable mode
pip install -e ".[dev]"       # install with test dependencies
mcp-agent-review               # run the MCP server (entry point)
```

## Testing

```bash
pytest                        # run all tests
pytest tests/test_tools.py    # run a single test file
pytest -k "TestSafeResolve"   # run a specific test class
pytest -k "test_path_traversal_blocked"  # run a single test
```

Tests use `monkeypatch` to stub `get_git_root` and git utility functions — no real git repo or API calls are needed. The `conftest.py` autouse fixture strips all API-related env vars.

## Architecture

This is an MCP server that exposes a single tool (`review_code`) to Claude Code. The review is performed by an external OpenAI-compatible model (not Claude itself), which gets agentic tool access to investigate the repo.

**Review pipeline** (`server.py` → `reviewer.py`):
1. Collect context: git diff, changed file contents (with ±50-line padding around hunks), CLAUDE.md, git log
2. Build system prompt via `build_system_prompt()` — injects `task_description` (developer intent) and `review_focus` (directed dimension) when provided
3. Send to OpenAI-compatible model with tool definitions, loop up to `MAX_TOOL_ROUNDS` (default 8) letting the model call tools
4. Run a self-critique pass (second model call) to filter low-confidence findings
5. Parse JSON output into formatted findings

**Key modules:**
- `server.py` — FastMCP server setup, `review_code` tool registration, orchestrates the pipeline
- `reviewer.py` — builds the user message, runs the agentic tool loop, self-critique, and output formatting
- `tools.py` — defines `GPT_TOOLS` (OpenAI function-calling schema) and `execute_tool_call` dispatcher; tools: `read_file`, `grep_code`, `git_blame`, `list_files`, `search_git_history`, `find_test_files`
- `git_utils.py` — git operations (diff, log, blame), diff parsing, changed-file context extraction with range merging
- `prompts.py` — `build_system_prompt()` dynamically assembles the system prompt (base + optional developer intent / directed focus sections), plus self-critique prompt

**Security boundary:** All tool file access goes through `_safe_resolve()` in `tools.py`, which blocks path traversal and symlink escapes outside the git root. Sensitive files (`.env`, `*.pem`, `*.key`, credentials, SSH keys) are blocked by `_is_sensitive()` in both tool execution and context collection.

## Environment Variables

`GITHUB_TOKEN` or `OPENAI_API_KEY` (one required), `OPENAI_BASE_URL` (default: GitHub Models), `REVIEW_MODEL` (default: `gpt-4o`), `MAX_TOOL_ROUNDS`, `MAX_FILE_LINES`.
