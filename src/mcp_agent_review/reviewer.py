import json
import os

from openai import OpenAI

from .git_utils import (
    get_changed_files,
    get_claude_md,
    get_commit_messages,
    get_git_log,
    read_changed_files_context,
)
from .prompts import SELF_CRITIQUE_PROMPT
from .tools import GPT_TOOLS, execute_tool_call

DEFAULT_MODEL = "gpt-4o"
MAX_TOOL_ROUNDS = int(os.environ.get("MAX_TOOL_ROUNDS", "8"))


def build_user_message(diff: str, base: str | None = None) -> str:
    claude_md = get_claude_md()
    git_log = get_git_log()
    commit_msgs = get_commit_messages(base)
    changed_files = get_changed_files(base)
    files_content = read_changed_files_context(changed_files, diff)

    parts = []
    if claude_md:
        parts.append(f"## Project Guidelines (CLAUDE.md)\n\n{claude_md}")
    parts.append(f"## Recent Git Log\n\n```\n{git_log}\n```")
    if commit_msgs and commit_msgs != "(empty)":
        parts.append(
            f"## Commit Messages (for this change)\n\n```\n{commit_msgs}\n```"
        )
    if files_content:
        parts.append(f"## Changed Files (context around changes)\n\n{files_content}")
    parts.append(f"## Diff to Review\n\n```diff\n{diff}\n```")
    parts.append(
        "Review the diff above for logic errors, architecture issues, doc-code inconsistency, "
        "and security risks. Use tools to VERIFY findings before reporting — grep for usages, "
        "read related files, check project structure. Do NOT report style/lint issues. "
        "Only report HIGH and MEDIUM confidence findings."
    )
    return "\n\n---\n\n".join(parts)


def run_agentic_review(
    client: OpenAI, messages: list, on_progress=None
) -> str | None:
    for round_num in range(MAX_TOOL_ROUNDS):
        model = os.environ.get("REVIEW_MODEL", DEFAULT_MODEL)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=GPT_TOOLS,
            temperature=0.3,
        )
        choice = response.choices[0]
        messages.append(choice.message)

        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            return choice.message.content

        tool_names = [tc.function.name for tc in choice.message.tool_calls]
        if on_progress:
            on_progress(
                round_num + 1, f"Tool round {round_num + 1}: {', '.join(tool_names)}"
            )

        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool_call(tc.function.name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )
    return None


def run_self_critique(client: OpenAI, messages: list) -> str | None:
    model = os.environ.get("REVIEW_MODEL", DEFAULT_MODEL)
    critique_messages = messages + [{"role": "user", "content": SELF_CRITIQUE_PROMPT}]
    response = client.chat.completions.create(
        model=model,
        messages=critique_messages,
        temperature=0.2,
    )
    return response.choices[0].message.content


def format_review_output(raw: str) -> str:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

    findings = data.get("findings", [])
    assessment = data.get("assessment", "")

    if not findings:
        return f"No issues found.\n\n{assessment}" if assessment else "No issues found."

    lines = []
    for f in findings:
        conf = f.get("confidence", "?")
        cat = f.get("category", "?")
        summary = f.get("summary", "")
        file_path = f.get("file", "")
        line_num = f.get("line", "")
        explanation = f.get("explanation", "")
        loc = f"{file_path}:{line_num}" if line_num else file_path
        lines.append(f"**[{conf}] {cat}**: {summary}")
        if loc:
            lines.append(f"  File: `{loc}`")
        if explanation:
            lines.append(f"  {explanation}")
        lines.append("")

    if assessment:
        lines.append(f"**Overall**: {assessment}")

    return "\n".join(lines)
