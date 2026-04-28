# mcp-agent-review

An MCP (Model Context Protocol) server that provides **agentic code review** powered by OpenAI-compatible models. Designed for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

## Features

- **Deep analysis** — focuses on logic errors, architecture issues, doc-code consistency, and security risks (not style/lint)
- **Agentic review** — the model can read files, grep code, check git blame, explore project structure, and search git history to verify findings
- **False-positive suppression** — mandatory tool verification, confidence rating, and self-critique phase
- **Intent-aware review** — pass `task_description` to catch mismatches between intent and implementation
- **Directed focus** — pass `review_focus` to get deeper analysis on a specific dimension (security, performance, concurrency, etc.)
- **Any OpenAI-compatible API** — works with GitHub Models (free), OpenAI, Azure OpenAI, or any compatible provider
- **Zero config for git repos** — auto-detects diffs, reads CLAUDE.md for project context
- **Sensitive file protection** — blocks access to `.env`, `*.pem`, `*.key`, credentials, and other sensitive files

## Installation

```bash
# From PyPI
pip install mcp-agent-review

# From source
git clone https://github.com/lzx1413/gpt-review.git
cd gpt-review
pip install .
```

## Claude Code Integration

Add to your Claude Code settings (`~/.claude.json` or `.claude/settings.json`):

### GitHub Models (free)

```json
{
  "mcpServers": {
    "code-review": {
      "command": "mcp-agent-review",
      "env": {
        "GITHUB_TOKEN": "your-github-token"
      }
    }
  }
}
```

### OpenAI (or other providers)

```json
{
  "mcpServers": {
    "code-review": {
      "command": "mcp-agent-review",
      "env": {
        "OPENAI_API_KEY": "your-api-key",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "REVIEW_MODEL": "gpt-4o"
      }
    }
  }
}
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes* | — | GitHub personal access token (free via GitHub Models) |
| `OPENAI_API_KEY` | Yes* | — | API key for OpenAI or compatible provider (takes priority over `GITHUB_TOKEN`) |
| `OPENAI_BASE_URL` | No | `https://models.github.ai/inference` | Base URL for the API |
| `REVIEW_MODEL` | No | `gpt-4o` | Model to use for review |
| `MAX_TOOL_ROUNDS` | No | `8` | Max agentic tool-use rounds |
| `MAX_FILE_LINES` | No | `1000` | Max lines to read per file |

*One of `GITHUB_TOKEN` or `OPENAI_API_KEY` is required.

## Tool Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `diff` | No | Custom diff string. If omitted, auto-reads from `git diff` |
| `base` | No | Base branch/commit for PR review (e.g. `main`) |
| `task_description` | No | What the changes are intended to accomplish (e.g. `fix race condition in pool`). Enables intent-vs-implementation mismatch detection |
| `review_focus` | No | Specific dimension to prioritize (e.g. `security`, `performance`, `concurrency safety`). Deeper analysis on this area |

## Usage

Once configured in Claude Code, the `review_code` tool is available:

- **Auto-detect changes**: just call `review_code` with no arguments — it reads `git diff`
- **PR review**: pass `base='main'` to review all changes since diverging from main
- **Custom diff**: pass a diff string directly via the `diff` parameter
- **Intent-aware review**: pass `task_description` to describe what the changes are for — helps catch gaps between intent and implementation
- **Directed focus**: pass `review_focus` (e.g. `'security'`, `'performance'`) to get deeper analysis on a specific dimension

### Example prompts in Claude Code

```
Review my current changes
```

```
Review the changes on this branch against main
```

```
Review my changes, the task is to fix the race condition in the connection pool, focus on concurrency safety
```

## How It Works

1. **Context collection** — reads CLAUDE.md, git log, commit messages, and full source of changed files
2. **Agentic review** — sends context + diff to the model, which can use tools (read_file, grep_code, git_blame, list_files, search_git_history, find_test_files) to investigate
3. **Self-critique** — a second pass filters out low-confidence or speculative findings
4. **Structured output** — returns findings with confidence level, category, file location, and explanation

## License

MIT
