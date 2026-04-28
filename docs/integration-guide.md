# MCP Code Review — 集成接入教程

本文档介绍如何将 `mcp-agent-review` 服务接入各种 IDE 和 Agent 框架。

## 目录

- [前置条件](#前置条件)
- [IDE 集成](#ide-集成)
  - [Claude Code](#claude-code)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [VS Code (GitHub Copilot)](#vs-code-github-copilot)
  - [Windsurf](#windsurf)
  - [JetBrains (IntelliJ / PyCharm)](#jetbrains-intellij--pycharm)
  - [Cline (VS Code 插件)](#cline-vs-code-插件)
- [Agent 框架集成](#agent-框架集成)
  - [LangChain / LangGraph](#langchain--langgraph)
  - [OpenAI Agents SDK](#openai-agents-sdk)
  - [Python MCP SDK 直连](#python-mcp-sdk-直连)
- [环境变量参考](#环境变量参考)
- [验证安装](#验证安装)
- [常见问题](#常见问题)

---

## 前置条件

```bash
# 安装（二选一）
pip install mcp-agent-review          # 从 PyPI
pip install .                         # 从源码

# 确认命令可用
which mcp-agent-review
```

需要准备以下任一 API 凭证：

| 方案 | 环境变量 | 费用 |
|------|---------|------|
| GitHub Models | `GITHUB_TOKEN` | 免费 |
| OpenAI | `OPENAI_API_KEY` | 按量付费 |
| 其他 OpenAI 兼容服务 | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | 视服务而定 |

---

## IDE 集成

### Claude Code

编辑 `~/.claude.json` 或项目级 `.claude/settings.json`：

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

使用方式 — 在 Claude Code 对话中直接输入：

```
Review my current changes
```

```
Review the changes on this branch against main
```

```
Review my changes, the task is to fix the race condition in the connection pool, focus on concurrency safety
```

---

### Claude Desktop

1. 打开 Claude Desktop → **Settings → Developer → Edit Config**
2. 编辑 `claude_desktop_config.json`：

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "code-review": {
      "command": "/full/path/to/mcp-agent-review",
      "env": {
        "GITHUB_TOKEN": "your-github-token"
      }
    }
  }
}
```

> **注意**：Claude Desktop 使用最小 PATH 启动子进程，`command` 必须使用**绝对路径**。
> 通过 `which mcp-agent-review` 获取完整路径。

3. 重启 Claude Desktop

---

### Cursor

**方式一：UI 配置**

Settings → Tools & MCP → Add new MCP server → 填入 Name: `code-review`，Type: `stdio`，Command: `mcp-agent-review`

**方式二：配置文件**

项目级 `.cursor/mcp.json`（仅当前项目）或全局 `~/.cursor/mcp.json`：

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

重启 Cursor 生效。在 Agent 模式下对话中即可使用 `review_code` 工具。

---

### VS Code (GitHub Copilot)

需要 VS Code 1.99+ 和 GitHub Copilot 订阅。

创建 `.vscode/mcp.json`（可提交到版本控制，团队共享）：

```json
{
  "servers": {
    "code-review": {
      "command": "mcp-agent-review",
      "env": {
        "GITHUB_TOKEN": "your-github-token"
      }
    }
  }
}
```

> **注意**：VS Code 的根键是 `"servers"`（不是 `"mcpServers"`），且 MCP 工具仅在 Copilot **Agent 模式** 下可用。

---

### Windsurf

编辑 `~/.codeium/windsurf/mcp_config.json`：

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

重启 Windsurf 生效。

---

### JetBrains (IntelliJ / PyCharm)

需要 IntelliJ IDEA 2025.1+ 并启用 AI Assistant 插件。

1. 打开 **Settings → Tools → AI Assistant → Model Context Protocol (MCP)**
2. 点击 **+** 添加服务器
3. 选择 **stdio** 类型，填入：
   - Name: `code-review`
   - Command: `mcp-agent-review`
4. 在 Environment Variables 中添加 `GITHUB_TOKEN`
5. 点击 Apply，重启 IDE

---

### Cline (VS Code 插件)

Cline 的配置文件位于：

**macOS**: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

**Windows**: `%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

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

---

## Agent 框架集成

### LangChain / LangGraph

安装依赖：

```bash
pip install langchain-mcp-adapters langgraph
```

**单服务器连接：**

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

async def main():
    server_params = StdioServerParameters(
        command="mcp-agent-review",
        env={
            "GITHUB_TOKEN": "your-github-token",
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await load_mcp_tools(session)

            llm = ChatOpenAI(model="gpt-4o")
            agent = create_react_agent(llm, tools)

            result = await agent.ainvoke({
                "messages": [{"role": "user", "content": "Review my current code changes"}]
            })
            print(result["messages"][-1].content)

asyncio.run(main())
```

**多服务器连接（MultiServerMCPClient）：**

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

async def main():
    async with MultiServerMCPClient({
        "code-review": {
            "command": "mcp-agent-review",
            "env": {"GITHUB_TOKEN": "your-github-token"},
            "transport": "stdio",
        },
        # 可同时连接其他 MCP 服务器
    }) as client:
        tools = client.get_tools()
        agent = create_react_agent(ChatOpenAI(model="gpt-4o"), tools)
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "Review changes against main"}]
        })
        print(result["messages"][-1].content)

asyncio.run(main())
```

---

### OpenAI Agents SDK

安装依赖：

```bash
pip install openai-agents mcp
```

```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    mcp_server = MCPServerStdio(
        command="mcp-agent-review",
        env={
            "GITHUB_TOKEN": "your-github-token",
        },
    )

    agent = Agent(
        name="Code Reviewer",
        instructions="You help review code changes using the review_code tool.",
        mcp_servers=[mcp_server],
    )

    async with mcp_server:
        result = await Runner.run(agent, "Review my current changes")
        print(result.final_output)

asyncio.run(main())
```

---

### Python MCP SDK 直连

最轻量的方式——直接用 MCP Python SDK 调用工具，无需 Agent 框架：

```bash
pip install mcp
```

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="mcp-agent-review",
        env={"GITHUB_TOKEN": "your-github-token"},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出可用工具
            tools = await session.list_tools()
            print("Available tools:", [t.name for t in tools.tools])

            # 调用 review_code（自动检测 git diff）
            result = await session.call_tool("review_code", arguments={})
            print(result.content[0].text)

            # 指定 base 分支做 PR review
            result = await session.call_tool(
                "review_code",
                arguments={"base": "main"},
            )
            print(result.content[0].text)

            # 带开发意图和定向审查
            result = await session.call_tool(
                "review_code",
                arguments={
                    "base": "main",
                    "task_description": "fix race condition in connection pool",
                    "review_focus": "concurrency safety",
                },
            )
            print(result.content[0].text)

asyncio.run(main())
```

---

## 环境变量参考

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `GITHUB_TOKEN` | 二选一* | — | GitHub 个人访问令牌（GitHub Models 免费） |
| `OPENAI_API_KEY` | 二选一* | — | OpenAI 或兼容服务的 API Key（优先级高于 GITHUB_TOKEN） |
| `OPENAI_BASE_URL` | 否 | `https://models.github.ai/inference` | API 地址 |
| `REVIEW_MODEL` | 否 | `gpt-4o` | 使用的模型 |
| `MAX_TOOL_ROUNDS` | 否 | `8` | 最大 agentic 工具调用轮数 |
| `MAX_FILE_LINES` | 否 | `1000` | 单文件最大读取行数 |

*`GITHUB_TOKEN` 和 `OPENAI_API_KEY` 至少提供一个。

### 工具参数

`review_code` 工具支持以下参数（均为可选）：

| 参数 | 说明 |
|------|------|
| `diff` | 自定义 diff 字符串。不传则自动读取 `git diff` |
| `base` | PR 审查的基准分支（如 `main`） |
| `task_description` | 本次变更的开发意图（如 `"修复连接池竞争条件"`）。帮助发现意图与实现不匹配的问题 |
| `review_focus` | 定向审查维度（如 `"security"`、`"performance"`、`"concurrency safety"`）。在指定维度上做更深入的分析 |

---

## 验证安装

配置完成后，在对应工具中测试：

1. **检查工具是否加载** — 询问 "What tools do you have available?" 确认 `review_code` 出现在列表中
2. **基础调用** — 在有 git 变更的仓库中输入 "Review my current changes"
3. **PR Review** — 输入 "Review changes against main"
4. **意图审查** — 输入 "Review my changes, the task is to add input validation, focus on security"

---

## 常见问题

**Q: 提示 "command not found"**
A: 使用 `which mcp-agent-review` 确认命令存在。在 Claude Desktop / VS Code 等工具中，建议使用绝对路径。如果用了虚拟环境，需要指向虚拟环境中的完整路径。

**Q: 提示 "No code changes detected"**
A: `review_code` 默认读取 `git diff HEAD`。确保当前目录是 git 仓库且有未提交的变更，或使用 `base` 参数指定比较分支。

**Q: 如何切换到 OpenAI 官方 API？**
A: 在 `env` 中设置 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 为 `https://api.openai.com/v1`。

**Q: 修改配置后不生效？**
A: 所有 IDE 都需要在修改配置后**重启**才能加载新的 MCP 服务器配置。

**Q: VS Code 中看不到 MCP 工具？**
A: MCP 工具仅在 GitHub Copilot 的 **Agent 模式**下可见，Ask 和 Edit 模式下不可用。
