# CHANGELOG

## 2026-04-22 (by Codex) — 上下文注意力管理改造（M1）

### 新增活跃对象上下文管理

- 新增 `src/deep_research_agent/context_manager.py`：
  - 以 `research/todo.md`、`source_index.md`、`notes/`、`evidence/`、`checkpoints/` 构建每轮上下文包
  - 明确区分当前 subgoal、TODO 切片、活跃来源/笔记/证据、前序 checkpoint 与最近 observation
  - 输出统一 Markdown 上下文载荷（`# 上下文包`），用于模型注意力聚焦
- `ReActAgent` 不再把整段历史消息无限累积发送；改为每轮：
  1) 构建 context pack  
  2) 发送 `system + context user + 紧凑 tail`
  3) 调用工具后记录 observation 并压缩 tail
- 新增上下文相关日志事件：
  - `context_pack_built`
  - `context_trim_applied`（当块被软裁剪时）

### TODO 闭合约束（程序化 guard）

- 在 `fs_write` 写入 `research/todo.md` 或 `writing/todo.md` 时新增校验：
  - 任意 `- [x] closed:` 条目必须包含 closure attempt 字段：
    - `结论`
    - `依据`
    - `未决项`
  - 缺失时写入直接报错，阻止伪闭合

### 检索查询重写（混合策略）

- `web_search` 支持新参数：
  - `intent`
  - `anchors`
  - `exact_phrases`
- 新增 query 组合函数：
  - 默认形态为“自然语言意图 + 锚点 + 精确短语”
  - 返回结果中增加：
    - `original_query`
    - `query_strategy`

### 检索策略回退（同日修正）

- 按主线收敛与性能要求，移除 `web_search` 的 runtime query 重写：
  - 删除 `intent/anchors/exact_phrases` 参数处理
  - 删除 `original_query/query_strategy` 返回字段
  - 工具层仅透传模型给出的 `query`，由模型自行选择关键词/自然语言/混合风格
- 在 `prompts/system.md` 增加查询风格指导，明确：
  - 简单实体问题优先关键词
  - 复杂约束问题优先自然语言
  - 不确定时使用混合表达
  - 工具层不会改写 query
- 新增测试：
  - `tests/test_tools.py::test_web_search_uses_raw_query_without_runtime_rewrite`
  - `tests/test_prompts.py::test_system_prompt_contains_query_style_guidance`

### 测试新增

- `tests/test_context_manager.py`
  - 验证上下文包内容构建
  - 验证 agent 使用 context manager 并产生日志事件
- `tests/test_todo_closure_guard.py`
  - 验证 todo 关闭缺少 closure attempt 被拒绝
  - 验证完整 closure attempt 可写入通过

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_context_manager.py tests/test_todo_closure_guard.py tests/test_agent_loop.py tests/test_tools.py -q`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q`：`32 passed, 6 skipped`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q`（回退后复验）：`34 passed, 6 skipped`

### 真实运行失败模式留痕（代理与网络）

- 失败现象 1（Jina 直连）：
  - `jina_reader` 报错 `SSL: CERTIFICATE_VERIFY_FAILED ... r.jina.ai`
  - 触发场景：未启用代理时执行真实 eval
- 失败现象 2（沙箱网络）：
  - `openai.APIConnectionError: Connection error` / `[Errno 1] Operation not permitted`
  - 触发场景：在受限沙箱中直接跑真实模型调用
- 已确认可行路径：
  - 使用交互 shell + 代理：`bash -ic '... && proxy_on && ...'`
  - 若仍因沙箱网络失败，需要提权网络执行（outside sandbox）
- 可复用命令模板：
  - `timeout 300s bash -ic 'cd /home/xiemingjie/dev/deep_research_agent && set -a && source .env && set +a && proxy_on && UV_CACHE_DIR=/tmp/uv-cache uv run deep-research-agent-eval \"<prompt>\" --skill research-todo --max-turns 10'`
  - `timeout 240s bash -ic 'cd /home/xiemingjie/dev/deep_research_agent && set -a && source .env && set +a && proxy_on && UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/smoke_tool.py jina_reader --url https://example.com'`

## 2026-04-22 (by Kimi Code CLI) — Real API 集成测试

### 新增 `tests/test_tools_real_api.py`

- 覆盖 6 个外部工具的端到端真实 API 测试：
  - `web_search` — Tavily 搜索，验证返回结果含标题、URL、内容摘要
  - `jina_reader` — Jina Reader 提取网页 Markdown
  - `arxiv_search` — arXiv 论文搜索
  - `arxiv_read_paper` — 下载并解析 arXiv PDF 为 Markdown
  - `pdf_read_url` — 本地 PyMuPDF4LLM 解析 PDF
  - `mineru_parse_url` — MinerU lightweight 模式解析 PDF
- 使用 `@pytest.mark.real_api` 标记，默认跳过
- 通过 `--run-real-api` 显式启用
- 测试在代理环境下运行，对 `cdn-mineru.openxlab.org.cn` 设置 `no_proxy` 直连避免 SSL 握手失败

### 配置更新

- `pyproject.toml` 注册 `real_api` pytest mark，消除 `Unknown pytest.mark.real_api` 警告

### 验证结果

- `pytest tests/ -q`（默认 fast 模式）：28 passed, 6 skipped
- `pytest tests/test_tools_real_api.py -v --run-real-api`（代理 + no_proxy）：6 passed

---

## 2026-04-22 (by Kimi Code CLI)

### System Prompt 管理重构

- **新建 `src/deep_research_agent/prompts.py`**：统一管理全局 system prompt 和工具目录生成
  - `get_system_prompt()`：支持从 `AGENT_SYSTEM_PROMPT_FILE` 环境变量或 `prompts/system.md` 文件加载
  - `build_tool_catalog()`：将 OpenAI tools 格式化为 Markdown 目录，注入 system prompt
  - `compose_system_prompt()`：组装最终 system prompt，替换 `{tool_catalog}` 占位符
- **新建 `prompts/system.md`**：全局 system prompt 模板文件，包含 `{tool_catalog}` 占位符
- **移除硬编码 prompt**：`cli.py` 和 `eval.py` 不再各自维护 `DEFAULT_SYSTEM_PROMPT`，统一从 `prompts.py` 导入
- **工具目录注入**：模型现在在 system prompt 中就能看到完整的工具清单、参数说明和使用策略

### Trace 可读性优化

- **日记风格格式**：trace.md 从"调试日志"改为"运行日记"
- **Turn 标题带摘要**：`## Turn N — 调用工具: web_search, jina_reader`
- **Emoji 区分角色**：🤔 Thinking / 💬 Output / 🛠️ Tool / 📄 Result / ❌ Error
- **压缩冗余信息**：
  - 去掉 `### Event N: type` 小标题
  - model_request 事件在 trace 中隐藏（保留在 events.jsonl）
  - 工具参数用单行内联格式
- **完整内容保留**：thinking、output、tool result 全部显示，仅超过 spillover 阈值时才截断

### Skills 重构

- **拆分 TODO skills**：将原来的 `skills/todo-list.md` 拆分为两个独立 skill：
  - `skills/research-todo.md` — 研究阶段 TODO 管理
  - `skills/write-todo.md` — 写作阶段 TODO 管理
- **简化约束**：去掉固定模板、固定章节、固定路径的过度约束，改为动态 TODO 控制面板设计
- **引入状态机**：支持 `open` / `in_progress` / `tentatively_resolved` / `closed` / `deferred` / `abandoned` 六种状态
- **引入 closure attempt 机制**：关闭任务必须附带结论、依据、未决项，防止模型过早打勾
- **增加 one-shot 示例**：每个 skill 包含完整的初始状态 → 一轮更新后的状态示例
- **增加反模式清单**：列出常见错误，用"不做什么"收窄模型行为空间
- **参考设计**：借鉴 law_agent 的极简 skill 风格和 Extra08 的 skill 编写最佳实践

### 时间格式调整

- `src/deep_research_agent/logging.py` 中的时间戳从 UTC 改为北京时间（Asia/Shanghai）
- 时间格式从 `%Y%m%dT%H%M%SZ` 改为 `%Y%m%dT%H%M%S`（去掉 Z 后缀）

### 脚本更新

- `scripts/init_todo_md.py`：支持 research/writing 两个 phase，使用北京时间
- `scripts/validate_todo_md.py`：校验任务状态是否合法，适配新的多状态设计

### 测试更新

- `tests/test_skills.py`：新增加载 research-todo 和 write-todo 的测试
- `tests/test_todo_skill_scripts.py`：新增 writing 模板测试和非法状态校验测试
- `tests/test_session.py`：将 `todo-list` 引用更新为 `research-todo`

### 验证结果

- `pytest tests/ -q --fast` 全部通过（28 tests）

---

## 2026-04-22

- Created the initial `uv` project scaffold, `src/` layout, `.gitignore`, `README.md`, and mandatory `CHANGELOG.md`.
- Added tests first, before implementation:
  - `tests/test_agent_loop.py`
  - `tests/test_tools.py`
  - `tests/test_logging.py`
  - `tests/conftest.py` with `--fast`
- Implemented the minimal runtime needed for V0:
  - `ReActAgent` while-loop runtime
  - normalized assistant/tool message objects
  - `DashScopeOpenAIBackend` using the DashScope OpenAI-compatible endpoint
  - `RunLogger` with `events.jsonl` and artifact spillover for long payloads
  - `ToolRegistry` with schema-lite validation and normalized tool results
- Implemented the first built-in tools:
  - `fs_list`
  - `fs_read`
  - `fs_write`
  - `fs_patch`
  - `web_search` via Tavily
  - `jina_reader` via Jina Reader API
  - `mineru_parse_url` for PDF/document URL parsing via MinerU
  - `arxiv_search` and `arxiv_read_paper` via `arxiv.py` + `PyMuPDF4LLM`
  - `pdf_read_url` with `mineru_first` then local `PyMuPDF4LLM` fallback
  - added repo-local `skills/todo-list.md` as the dedicated TODO List skill
- Added runnable entrypoints:
  - CLI: `deep-research-agent`
  - tool smoke script: `scripts/smoke_tool.py`
- Real validation completed:
  - confirmed `proxy_on` exists as an interactive shell alias and can be used with `bash -ic`
  - `pytest tests -q --fast` passes via `UV_CACHE_DIR=/tmp/uv-cache`
  - real DashScope smoke test passed with proxy enabled:
    - prompt forced filesystem tool usage
    - agent completed in 3 turns
    - final answer returned `hello from agent`
    - run log written under `logs/20260422T072543Z_7ccb047a`
  - real `jina_reader` smoke test passed against `https://example.com`
  - real `web_search` smoke test passed for query `OpenAI`
  - real MinerU lightweight smoke test passed against `https://cdn-mineru.openxlab.org.cn/demo/example.pdf`
    - MinerU returned parsed Markdown successfully
  - real MinerU lightweight smoke test against `https://arxiv.org/pdf/1706.03762.pdf`
    - request reached MinerU but task returned `state=failed`
    - surfaced error: `model service is temporarily unavailable, please try again later or contact technical support`
  - direct `httpx` fetch for `https://arxiv.org/pdf/1706.03762.pdf` returned `HTTP 200` and `content-type=application/pdf`
    - confirms the PDF itself is reachable; failure is not caused by the download path
  - real `arxiv_search` smoke test passed for query `transformer attention`
  - real `arxiv_read_paper` smoke test passed for `https://arxiv.org/abs/1706.03762`
    - downloaded PDF locally and parsed Markdown into `artifacts/arxiv/1706.03762.md`
  - real `pdf_read_url` smoke tests:
    - non-arXiv PDF `https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf`
      - `mineru_first` fell back to local `PyMuPDF4LLM`
      - result succeeded and produced `artifacts/pdf_cache/dummy.md`
    - arXiv PDF `https://arxiv.org/pdf/1706.03762.pdf`
      - `mineru_first` fell back to local `PyMuPDF4LLM`
      - result succeeded and produced `artifacts/pdf_cache/1706.03762.md`
    - same non-arXiv PDF under `proxy_on`
      - final result was still successful and still used local fallback
- Effective fixes during the process:
  - cleaned the repository layout after switching to session-based runtime isolation:
    - removed obsolete top-level `logs/` and `artifacts/` demo outputs
    - removed transient Python cache directories
    - removed the unused `SKILLS example.md` draft file
    - updated `.gitignore` to ignore `sessions/`
    - updated `README.md` with the current directory layout
  - added session isolation for each task run:
    - CLI now creates per-session `workspace/` and `logs/` under `sessions/<session_id>/`
    - run logs now land inside the owning session instead of the shared top-level `logs/` folder
    - added `session.json` metadata to preserve the original user input and session identity
  - unified parsed document storage under each session workspace:
    - both `arxiv_read_paper` and `pdf_read_url` now write into `sessions/<session_id>/workspace/documents/`
    - removed the old split between shared `artifacts/arxiv/` and `artifacts/pdf_cache/`
  - added a stable benchmark-facing eval interface:
    - new importable helper `deep_research_agent.eval.run_eval_case(...)`
    - new CLI entrypoint `deep-research-agent-eval` that prints one JSON object for easy benchmark integration
  - flattened the TODO skill layout:
    - replaced the nested `skills/todo-list/` directory with a single `skills/todo-list.md`
    - moved deterministic TODO helper scripts to top-level `scripts/`
  - changed TODO from a JSON-first design to a Chinese Markdown checklist design:
    - default TODO files are now `research/todo.md` and `writing/todo.md`
    - helper scripts are `scripts/init_todo_md.py` and `scripts/validate_todo_md.py`
    - TODO guidance now follows a human-readable checklist template instead of a JSON object shape
  - tightened human log output:
    - `trace.md` now shows prompt and skill paths instead of inlining the full system prompt and skill bodies
    - system-role message bodies are omitted from the trace to keep the log compact and readable
  - fixed logger artifact path handling so spilled payload files are actually reachable
  - fixed CLI entrypoint by adding `if __name__ == "__main__": main()`
  - updated logging to produce both `events.jsonl` and human-readable `trace.md`
  - changed log retention policy to keep full payloads inline instead of replacing long text with path-only stubs
  - long text is still copied into `artifacts/` for convenience, but the main logs no longer lose information
  - upgraded `trace.md` to group events by `turn_index` while still embedding the full payload for every event
  - added human-oriented trace sections for common events such as `Messages`, `Tools`, `Reasoning`, `Tool Calls`, and `Tool Content` without removing the full payload block
  - expanded trace readability further with fixed sections for `System Prompt Content`, role-grouped messages, and a normalized `Tool Catalog`
  - corrected the trace direction: `trace.md` is now a human-readable natural-language log, while raw structured detail stays in `events.jsonl`
  - made the human trace more compact by removing timestamps and tool call ids from `trace.md`
  - changed the default `pdf_read_url` strategy to local `PyMuPDF4LLM`; MinerU is now opt-in instead of the default path
  - added a dedicated MinerU document-reading tool so PDF/doc/ppt URLs no longer need to go through `jina_reader`
- Failed attempts preserved:
  - first real CLI smoke test did nothing because the CLI module lacked the `__main__` guard
  - direct shell one-liner tool smoke tests failed due quoting/escaping issues, replaced with `scripts/smoke_tool.py`
  - sandboxed network validation failed with `openai.APIConnectionError`, so real smoke tests were rerun outside the sandbox with explicit approval
  - MinerU smoke test through `proxy_on` failed with `SSL: UNEXPECTED_EOF_WHILE_READING`
    - direct network path worked for the official demo PDF, so the current issue appears specific to the proxy path rather than the MinerU tool logic
  - MinerU also returned `model service is temporarily unavailable` for both arXiv and a non-arXiv dummy PDF during later tests
    - local `PyMuPDF4LLM` fallback avoided turning this service instability into an agent failure
- Repository state:
  - initialized git repository
  - renamed branch to `main`
  - added remote `git@github.com:V-rand/open_niumasearch.git`
- Next tasks:
  - add structured prompt files instead of embedding the default system prompt in code
  - add contract tests for the DashScope backend response parsing
  - decide whether `web_search` should keep direct REST calls or switch to the Tavily SDK
  - start the next layer above the minimal loop: research task state, TODO state, and checkpoint files
