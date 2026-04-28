#!/usr/bin/env python3
"""MCP server that exposes agentic code review as a tool for Claude Code."""

import os

from mcp.server.fastmcp import Context, FastMCP
from openai import OpenAI

from .git_utils import get_git_diff
from .prompts import build_system_prompt
from .reviewer import (
    build_user_message,
    format_review_output,
    run_agentic_review,
    run_self_critique,
)

mcp = FastMCP("mcp-agent-review")


@mcp.tool()
async def review_code(
    diff: str | None = None,
    base: str | None = None,
    task_description: str | None = None,
    review_focus: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Review code changes using an OpenAI-compatible model.

    Args:
        diff: Custom diff string to review. If not provided, automatically reads from git diff.
        base: Base branch/commit for PR review (e.g. 'main').
        task_description: What these changes are intended to accomplish (e.g. 'fix race condition in connection pool'). Helps catch intent-implementation mismatches.
        review_focus: Specific dimension to focus on (e.g. 'security', 'performance', 'concurrency safety'). Allows deeper review on a targeted area instead of spreading attention across all dimensions.
    """

    async def _progress(step: int, total: int, msg: str):
        if ctx:
            await ctx.report_progress(step, total, msg)
            await ctx.info(msg)

    await _progress(0, 4, "Collecting context (diff, changed files, project docs)...")
    if not diff:
        diff = get_git_diff(base)
    if not diff:
        return "No code changes detected. Nothing to review."

    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("GITHUB_TOKEN"),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://models.github.ai/inference"),
        max_retries=3,
    )

    messages = [
        {"role": "system", "content": build_system_prompt(task_description, review_focus)},
        {"role": "user", "content": build_user_message(diff, base)},
    ]

    await _progress(1, 4, "Model analyzing code (agentic review)...")

    progress_messages = []

    def on_tool_progress(round_num, msg):
        progress_messages.append(msg)

    raw_review = run_agentic_review(client, messages, on_progress=on_tool_progress)

    if progress_messages and ctx:
        await ctx.info(f"Completed {len(progress_messages)} tool rounds")

    if not raw_review:
        return "(max tool rounds reached, no final response)"

    await _progress(3, 4, "Self-critique: filtering low-confidence findings...")
    final = run_self_critique(client, messages) or raw_review

    await _progress(4, 4, "Review complete.")
    return format_review_output(final)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
