# mcp-agent-review vs code-review-mcp 对比分析

## 基本信息

| 维度 | **mcp-agent-review**（本项目） | **code-review-mcp** |
|------|-----|-----|
| 语言 | Python | TypeScript |
| MCP 框架 | FastMCP (`mcp>=1.0.0`) | `@modelcontextprotocol/sdk` |
| LLM 接入 | OpenAI SDK（兼容任何 OpenAI API） | Vercel AI SDK（Google / OpenAI / Anthropic 原生） |
| 代码量 | ~600 行（6 个模块） | ~608 行（4 个模块） |
| 工具数量 | 1 个 MCP 工具 (`review_code`) | 1 个 MCP 工具 (`perform_code_review`) |

---

## 核心架构差异

### 审查方式

| | **mcp-agent-review** | **code-review-mcp** |
|---|---|---|
| **模式** | Agentic（模型可多轮调用工具） | Single-shot（一次 LLM 调用） |
| **工具调用** | 模型可调用 6 个工具（read_file、grep_code、git_blame、list_files、search_git_history、find_test_files）验证发现 | 无工具调用能力，仅分析 diff |
| **自我纠正** | 有 self-critique 阶段过滤低置信度发现 | 无 |
| **上下文收集** | 自动读取 CLAUDE.md、git log、commit messages、变更文件源码（±50 行） | 仅 diff，上下文由调用方通过参数传入（`projectContext`、`taskDescription`） |
| **最大轮次** | 默认 8 轮（`MAX_TOOL_ROUNDS`） | 1 轮 |

**结论**：本项目的 agentic 模式让审查模型可以主动探索代码库验证发现，显著降低误报率；code-review-mcp 是纯 diff-in/review-out，依赖 diff 中的上下文。

### LLM 提供商支持

| | **mcp-agent-review** | **code-review-mcp** |
|---|---|---|
| **支持的提供商** | 任何 OpenAI 兼容 API（GitHub Models 免费、OpenAI、Azure、本地 Ollama 等） | Google Gemini、OpenAI、Anthropic（三选一） |
| **切换方式** | 改 `OPENAI_BASE_URL` 环境变量 | 每次调用指定 `llmProvider` + `modelName` 参数 |
| **默认模型** | `gpt-4o`（通过 GitHub Models 免费） | 无默认，调用时必须指定 |

**结论**：本项目通过 OpenAI 兼容协议实现"一个接口接所有"，但不支持原生 Anthropic/Google SDK；code-review-mcp 原生支持三大厂商但每次调用都要指定 provider。

---

## 安全性对比

| 维度 | **mcp-agent-review** | **code-review-mcp** |
|------|-----|-----|
| 路径越界防护 | `_safe_resolve()` 阻止路径遍历和符号链接逃逸 | 不涉及（不读取任意文件） |
| 敏感文件过滤 | `_is_sensitive()` 黑名单（`.env`、`*.pem`、`*.key` 等 16 种模式） | 无（依赖 `.gitignore`） |
| 命令注入防护 | 使用 `subprocess.run` list 模式（无 shell） | `execSync` 拼接字符串命令 + 分支名白名单过滤 |
| grep 符号链接 | `--no-follow` 防止跟随 | 不涉及 |
| 数据泄露面 | 较大 — agentic 模型可主动读取仓库文件 | 较小 — 仅发送 diff 到外部 API |

**结论**：本项目因 agentic 模式暴露面更大，但有对应的安全加固措施；code-review-mcp 的攻击面天然较小（只传 diff），但 `execSync` 字符串拼接是潜在风险点，且无敏感文件过滤。

---

## 输出格式

| | **mcp-agent-review** | **code-review-mcp** |
|---|---|---|
| **格式** | 结构化 JSON（`findings[]` + `assessment`） | 自由格式 Markdown |
| **置信度** | 每个发现标注 HIGH / MEDIUM | 无 |
| **分类** | logic_error / architecture / doc_consistency / security | 无固定分类 |
| **定位** | 文件路径 + 行号 | 取决于模型输出 |

**结论**：本项目输出结构化、可程序化处理；code-review-mcp 输出更易读但不可靠地解析。

---

## 工程化对比

| 维度 | **mcp-agent-review** | **code-review-mcp** |
|------|-----|-----|
| 测试 | 69 个 pytest 用例（含安全测试） | ~12 个 vitest 用例（config + git-utils） |
| LLM 逻辑测试 | 有（mock OpenAI client） | 无（llm-service 无测试） |
| 参数校验 | Python 类型标注 | Zod schema（运行时校验） |
| 连接重试 | 无 | 3 次重试 + 2s 间隔 |
| 优雅退出 | 无 | SIGINT / SIGTERM 处理 |
| Docker 支持 | 无 | 有 Dockerfile |
| 示例模板 | 无 | 12 个 Claude 命令 + 4 个 Windsurf 工作流 |
| 进度报告 | 有（MCP progress + info） | 无 |

---

## 各自优势总结

### mcp-agent-review（本项目）的优势

1. **Agentic 审查** — 模型能主动读代码、grep 搜索、查 blame 来验证发现，这是最核心的差异化能力
2. **误报抑制** — self-critique 机制 + 强制工具验证 + 置信度评级，显著减少无效反馈
3. **自动上下文** — 自动读取 CLAUDE.md、git log、变更文件源码，零配置即可获得丰富上下文
4. **结构化输出** — JSON 格式 + 分类 + 行号定位，可被上层工具程序化消费
5. **安全加固** — 路径越界、符号链接、敏感文件过滤均有防护
6. **测试覆盖** — 69 个测试用例，包括安全边界测试
7. **免费可用** — 默认使用 GitHub Models（免费 GPT-4o）

### code-review-mcp 的优势

1. **多提供商原生支持** — 通过 Vercel AI SDK 原生支持 Google/OpenAI/Anthropic，不需要兼容层
2. **调用灵活性** — 每次调用可指定不同 provider + model + focus，适合对比不同模型的审查结果
3. **攻击面小** — 只传 diff，不读取仓库文件，数据泄露风险天然较低
4. **运维完善** — 连接重试、优雅退出、Docker、Smithery 一键部署
5. **开箱示例丰富** — 12 个预置 Claude 命令模板 + Windsurf 工作流
6. **参数校验** — Zod runtime schema 验证，类型安全且给出清晰错误
7. **可配 token 上限** — `maxTokens` 参数可控制成本

---

## 本项目可借鉴的改进方向

| 优先级 | 改进项 | 来源启发 |
|--------|--------|----------|
| 高 | 支持多 LLM 提供商原生 SDK（Anthropic、Google） | code-review-mcp 的 Vercel AI SDK 方式 |
| 高 | 添加 Zod 类似的参数运行时校验 | code-review-mcp 的 Zod schema |
| 中 | 添加连接重试和优雅退出 | code-review-mcp 的 transport retry + signal handlers |
| 中 | 提供预置 slash command 示例 | code-review-mcp 的 `examples/claude-commands/` |
| 低 | 添加 Docker 支持 | code-review-mcp 的 Dockerfile |
| 低 | 支持每次调用指定 `reviewFocus` 参数 | code-review-mcp 的 tool params |
