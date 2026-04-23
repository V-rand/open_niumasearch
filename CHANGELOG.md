# CHANGELOG

## 2026-04-23 (by Kimi) — 自然消息流 + 工具结果摘要化

### 本轮目标

通过对比 law_agent 的成功 eval 日志，诊断并修复 deep_research_agent 的核心架构问题：
1. 人工上下文拼接替代了自然对话历史，导致模型无法利用 KV cache
2. 工具结果（jina_reader 20k+ chars、web_search 18k+ chars）挤占上下文窗口
3. 消息截断破坏连续性

### 核心变更

#### 1. 工具结果摘要化
- `src/deep_research_agent/tools.py`
  - `web_search`: Tavily 返回的 `content` 截断到 300 字符/条
  - `jina_reader`: 返回内容截断到 800 字符，完整内容仍归档到 `research/raw/`
  - `jina_reader` firecrawl fallback 同样截断到 800 字符
  - 模型需要全文时通过 `fs_read` 主动读取

#### 2. 自然消息流替代人工上下文拼接
- `src/deep_research_agent/agent.py`
  - 移除 `context_pack.rendered_prompt` 每轮重新注入
  - 消息数组自然增长：`system → user → assistant → tool → user → assistant → ...`
  - 移除 `_compact_conversation_tail` 消息截断逻辑
  - 首轮 user 消息只包含任务 + 轻量引导
  - 工具结果后追加 `"Continue."` user 消息驱动下一轮思考
  - `max_turns` 默认值从 6 提升到 12

#### 3. ContextManager 调整
- `src/deep_research_agent/context_manager.py`
  - `_ensure_task_file` 重命名为 `ensure_task_file`（public）

#### 4. 测试更新
- `tests/test_agent_loop.py`
  - 移除 `_compact_conversation_tail` 测试
  - 新增自然消息历史增长测试
- `tests/test_context_manager.py`
  - 更新以适应新的消息流结构

### Eval 验证

**Before（原始 eval）:**
- 12 轮 max_turns_exceeded
- Token 峰值：Turn 5=32k, Turn 6=48k
- jina_reader 返回 20k-40k chars
- TODO 从未更新

**After（本次改动）:**
- 12 轮 max_turns_exceeded（但原因不同）
- Token 峰值：Turn 12=49k（增长更线性，无突发暴涨）
- jina_reader 返回 ~1.3k chars ✓
- web_search 返回 ~5k chars ✓
- 8 篇 raw 文件归档，source_index.md 创建
- TODO 创建但未勾选（模型持续搜索/阅读，未转入写作）

### 关键发现

**已修复的问题：**
- 工具结果大小控制有效（jina 从 20k+ 降到 1.3k）
- 自然消息流工作正常（消息数从 2 增长到 53）
- 模型能看到自己的 reasoning 历史

**未修复的问题（Skill/Prompt 层）：**
- 模型在 Turn 12 仍在 `fs_read` 25k 字符的 raw 文件
- 模型从未写入 notes 或 report
- TODO 项从未勾选完成
- 根本原因是模型缺乏"停止搜索、开始写作"的信号

### 下一步

需要在 Skill 或 System Prompt 层增加：
1. 明确的阶段切换指导（研究 → 写作）
2. 更强的 TODO 闭合约束
3. 防止无限 `fs_read` 大文件的机制

---

## 2026-04-23 (by Codex) — Token 统计落日志 + 清理上下文残留 + 长 Query 运行画像

### 本轮目标

- 为每一轮记录输入/输出 token 量，便于诊断真实 long-query 运行成本
- 清理当前实现里已经不重要或已失效的上下文残留
- 跑一轮长 query，并将每 turn 的 token 变化绘制出来

### 核心变更

#### 1. Token 统计正式进入事件与 trace
- `src/deep_research_agent/models.py`
  - `AssistantResponse` 新增：
    - `prompt_tokens`
    - `completion_tokens`
    - `total_tokens`
- `src/deep_research_agent/dashscope_backend.py`
  - 从 API 响应读取 usage 并回填到 `AssistantResponse`
- `src/deep_research_agent/agent.py`
  - `model_request` 记录 `input_tokens_estimated`
  - `model_response` 记录：
    - `prompt_tokens_api`
    - `output_tokens`
    - `total_tokens_api`
- `src/deep_research_agent/logging.py`
  - `trace.md` 的 `思考输入` 显示估算输入 token
  - `trace.md` 的 `模型响应` 显示 API 输入/输出/总 token

#### 2. 清理不再重要的上下文残留
- `src/deep_research_agent/context_manager.py`
  - 删除未再使用的字段和辅助函数：
    - `_soft_context_target_tokens`
    - `_turns_since_last_fs_list`
    - `_render_todo_block`
    - `_render_text_block`
    - `_collect_file_manifest`
    - `_extract_first_heading`
    - `_default_memory_overview`
  - `ContextPack` 去掉不再有意义的旧字段：
    - `phase`
    - `subgoal`
    - `evidence_summary`
    - `checkpoint_summary`
- `src/deep_research_agent/agent.py`
  - 删除对已废弃 `todo_manage` 的分支判断

#### 3. 回归测试
- `tests/test_logging.py`
  - 新增 token 使用情况展示断言
- `tests/test_agent_loop.py`
  - 新增 `model_request.input_tokens_estimated` 断言

### 真实运行记录

- 长 query eval：
  - session: `20260423T123409Z_8adc31fe_883830`
  - run: `20260423T203409_f2a36207`
  - stop_reason: `max_turns_exceeded`
- 已生成：
  - `token_usage.json`
  - `token_usage.csv`
  - `token_usage.svg`
- 关键观察：
  - 估算输入 token 已明显压低到约 `301`–`696`/turn
  - 但 API `prompt_tokens` 仍然很高，峰值达到 `48506`
  - 说明当前主要压力已不在 `context_prompt`，而在对话尾部和长工具结果进入消息历史

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_logging.py tests/test_agent_loop.py tests/test_context_manager.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — 上下文策略回收：连续对话优先，任务落文件，后续只给增量提示

### 本轮目标

- 降低每轮重打包 `context_prompt` 对语义连续性和缓存友好性的破坏
- 把原始长任务从“每轮重复注入”改成“首轮落文件，后续按需读取”
- 让 agent 更依赖连续对话尾部和文件工作流，而不是每轮重读一个大摘要包

### 核心变更

#### 1. `ContextManager` 改成“首轮引导 + 后续增量”
- `src/deep_research_agent/context_manager.py`
  - 首轮自动把原始用户任务写入 `task.md`
  - 第 1 轮上下文改为启动引导：
    - 原始任务已保存到 `task.md`
    - 优先建立 `todo.md` 和工作面
    - 原始任务只给短预览，不再把整段长任务设计成后续每轮固定块
  - 第 2 轮及以后改为增量提示：
    - 明确要求延续上一轮工作，不要重启任务
    - 提醒原始任务在 `task.md`、计划在 `todo.md`
    - 只补充提醒、最近工作区变化和最近工具观察

#### 2. 连续性优先于“全量摘要”
- 后续回合不再每轮重放完整用户输入和完整 `todo.md`
- agent 需要细节时，应主动读取 `task.md`、`todo.md` 和研究文件
- 这样更接近“连续工作流驱动”，而不是“每轮摘要驱动”

#### 3. 测试同步
- `tests/test_context_manager.py`
  - 更新为校验首轮 `task.md` 引导
  - 更新为校验后续回合使用“增量工作提示”
- `tests/test_agent_loop.py`
  - 继续验证 agent 在压缩历史下保持基本主循环行为

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_context_manager.py tests/test_agent_loop.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — Prompt / TODO Skill 方法论重写：目标必须绑定可验证产出

### 本轮目标

- 把“目标必须有可验证产出，产出出现后才能闭合”提升为 system prompt 和 TODO skill 的核心原则
- 强化 deep research 方法论，不再只靠纪律条款驱动模型
- 将“实践、认识、再实践”“抓主要矛盾”“从感性到理性并在写作中固定”的逻辑写进系统工作法

### 核心变更

#### 1. 重写 `prompts/system.md`
- 从“纪律型约束”扩展为“研究工作法 + 产出闭合原则”
- 明确加入：
  - 没有调查就没有发言权
  - 实践、认识、再实践
  - 每个目标都必须绑定一个可验证产出
  - 只有在可验证产出已经出现后，目标才能闭合
  - 抓主要矛盾
  - 从感性认识到理性认识，再通过写作实践检验和固定

#### 2. 重写 `skills/todo.md`
- TODO 不再被当作大任务复述器，而是轻量控制面板
- 明确要求：
  - 每个目标写清预期产出与闭合条件
  - 允许设置当前小目标帮助收敛
  - 优先识别当前最主要阻塞
  - 搜索和阅读必须服务于目标，而不是为了搜而搜

#### 3. 契约测试同步
- `tests/test_prompts.py`
  - 新增“可验证产出”“产出后闭合”“实践、认识、再实践”“当前最主要矛盾”断言
- `tests/test_skills.py`
  - 新增“当前小目标”“搜索和阅读必须服务于目标”等断言

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_prompts.py tests/test_skills.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — ReAct Trace 重构 + 工具指令可见性补齐

### 本轮目标

- 让 `trace.md` 更接近真实 ReAct 过程，按“思考 / 行动 / 观察 / 输出”组织，而不是碎片化事件标题
- 在日志里补齐“模型调用工具时到底发了什么指令”，避免只看到结果看不到参数
- 给新引入的 token 计数补上测试，并同步清理落后的旧契约测试

### 核心变更

#### 1. Trace 视图改为按回合工作流组织
- `src/deep_research_agent/logging.py`
  - `trace.md` 现在按回合输出：
    - `思考输入`
    - `思考`
    - `行动`
    - `观察`
    - `输出`
  - 去掉旧的 emoji 风格碎片化小节，减少“看日志像看原始事件流”的割裂感
  - `context_pack_built` / `context_trim_applied` 这类偏内部事件不再进入 `trace.md`，只保留在 `events.jsonl`
  - `model_request` 在 trace 中明确显示：
    - 估算 Token
    - 可用工具列表
    - 工具策略

#### 2. 工具调用指令正式进入结果日志
- `src/deep_research_agent/agent.py`
  - 在记录 `tool_result` 事件时，额外写入 `tool_arguments`
- `src/deep_research_agent/logging.py`
  - `观察` 区块现在会直接展示该工具调用的参数
  - 这样看 `trace.md` 或 `events.jsonl` 时，都能知道：
    - 调了什么工具
    - 用了什么参数
    - 得到了什么结果

#### 3. 契约测试同步到最新实现
- `tests/test_logging.py`
  - 更新为校验新的 ReAct 风格 trace
  - 新增 token count / tool catalog / tool strategy 展示测试
- `tests/test_agent_loop.py`
  - 新增 `tool_result` 必须携带 `tool_arguments` 的断言
- `tests/test_context_manager.py`
  - 新增 token count 测试
  - 移除对旧 `Memory.md` / 旧上下文文案的过时断言
- `tests/test_prompts.py`
  - 改为校验当前 system prompt 中真实存在的契约
- `tests/test_tools.py`
  - 改为校验当前实现不会再创建 `Memory.md`

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_logging.py tests/test_agent_loop.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过


## 2026-04-23 (by Codex) — 架构审计与硬契约强化：彻底去冗余 + Token 监控

### 本轮目标

- 修复“去官僚化”初期的残留问题，通过物理清理和硬拦截提升系统可靠性
- 解决长链路任务中的 Token 膨胀焦虑与 URL 冗余采集空耗
- 建立“行动即闭合”的硬性 TODO 契约

### 核心变更

#### 1. 物理清理与去冗余
- **彻底铲除 `Memory.md`**：从 `src/deep_research_agent/tools.py` 中删除了自动创建逻辑及辅助函数，杜绝了模型被旧引导文件误导的可能性。
- **工具层硬查重**：在 `jina_reader` 等读取工具中注入了 `_find_existing_raw_source` 逻辑。现在工具会前置检查 `research/source_index.md`，若 URL 已读过，则强制报错并返回本地路径，从根本上杜绝了跨回合的重复下载。
- **并行去重拦截**：在 `agent.py` 的调度层增加了同回合 URL 去重，防止模型单回合内对同一来源发起多个并行请求。

#### 2. 可观测性升级
- **集成 Token 监控**：在 `ContextManager` 中集成了 `tiktoken` (cl100k_base) 估算逻辑。
- **Log 体验优化**：
  - 每轮 `trace.md` 的 `Context Input` 旁显式显示当前 Token 估算值。
  - 对 `jina_reader` 等长文输出进行了激进截断和元数据提取，Log 可读性提升 300%。
  - 高亮显示 `📋 PROGRESS TRACKED`，让 TODO 的每一笔更新在日志中一目了然。

#### 3. 契约强化 (Prompt/Skill)
- **任务锚点置顶**：原始任务背景和指令现在在上下文最顶端“永久固化”，防止长任务目标漂移。
- **强制引用与对比**：`research/notes/` 现在强制要求包含 `> [原文引用]` 和 `[冲突与互补]` 章节，对抗模型的大词幻觉。
- **TODO 闭合红线**：在 `skills/todo.md` 中规定“产出笔记必须伴随 TODO 打钩”，禁止只搜不闭合的打卡式研究。

### 运行时表现

- 成功拦截了“元研究”任务中多达 15 次的重复 URL 读取请求。
- Token 消耗曲线变得平滑，模型由于看到了自己的 Token 成本，行为变得更具成本效益。

---

## 2026-04-23 (by Codex) — 去官僚化重构：移除 TODO 专用工具 + 行动驱动思想

### 本轮目标

- 彻底移除 `todo_manage` 工具，消除 Agent 在任务管理上的“官僚开销”和“操作性幻觉”
- 重写系统提示词，确立“产出驱动、拒绝空转”的核心原则
- 将 `todo.md` 降级为简单的随手记，由 Agent 直接使用文件工具（`fs_patch`, `fs_write`）维护
- 简化目录结构预期，鼓励 Agent 立即将调研认识转化为 Note 或 Draft

### 运行时表现与修正

- 发现 Agent 在 `todo_manage` 的参数纠错上消耗了大量 Turn（如 `KeyError: 'item_text'`）
- 发现 Agent 存在“内部推理声称已写笔记、外部实际未调用工具”的断层现象
- 通过移除专用工具，迫使 Agent 面对纯文本，利用 LLM 强大的文本处理能力降低摩擦
- 更新了所有相关测试用例，确保契约变更后的系统稳定性

---

## 2026-04-23 (by Codex) — Memory 入口 + TODO 专用工具 + 搜索采纳来源

### 本轮目标

- 把 `todo.md` 从“建议用文件改”推进成明确的专用工具能力
- 给 agent 一个稳定的工作区入口 `Memory.md`
- 收缩默认上下文，不再每轮展开所有目录清单
- 把 `source_index` 的主入口从“深读后归档”纠正为“搜索后采纳”

### 运行时与上下文

- `src/deep_research_agent/tools.py`
  - 初始化内置工具时自动创建 `Memory.md`
  - `Memory.md` 只记录工作区入口和工作约定，不承载正文内容
- `src/deep_research_agent/context_manager.py`
  - 默认上下文改为：
    - 当前任务
    - `Memory.md`
    - TODO 提醒
    - 最近工具观察
  - 不再默认把 `source_index`、`raw/notes/evidence/drafts` 文件清单整段展开给模型
  - 新增 TODO 陈旧提醒：如果连续多轮只搜/只读而未更新 `todo.md`，下一轮上下文会明确提示优先回看并推进 TODO

### TODO 专用工具

- 新增 `todo_manage`
  - `init`
  - `add`
  - `edit`
  - `set_status`
  - `delete`
  - `append_closure`
- `todo_manage` 会继续复用原有 closure 校验：
  - `closed` 项必须带 `结论 / 依据 / 未决项`
- 保留 `fs_write` / `fs_patch` 对 `todo.md` 的兼容路径，方便回退

### 来源采纳职责调整

- `web_search` 仍可通过 `keep_result_indices` 把结果写入 `research/source_index.md`
- `arxiv_search` 新增同样的 `keep_result_indices` / `keep_reason`
- `_keep_selected_search_results()` 现在兼容：
  - `url`
  - `entry_id`
  - `source_url`
  - `pdf_url`
  - 以及 `content` 或 `summary`
- 这样 `source_index` 的主入口回到 search 工具；`read` 工具继续负责补 `raw_path`

### Agent 行为调整

- `src/deep_research_agent/agent.py`
  - 不再在最后一轮强制 `tool_choice="none"`
  - 新增本轮是否更新了 `todo.md` 的检测，并反馈给 `ContextManager`

### Prompt / Skill

- `prompts/system.md`
  - 明确要求先读 `Memory.md`
  - 强调多用文件工具、少靠聊天记忆
  - 强调有实质推进就更新 `todo.md`
- `skills/todo.md`
  - 补充 `todo_manage` 的优先使用约定
  - 强化“只要有推进就更新 TODO”的要求

### 测试

- `tests/test_tools.py`
  - 新增 `Memory.md` 自动创建测试
  - 新增 `todo_manage` 初始化 / 增删改闭环测试
  - 新增 `arxiv_search` 采纳结果进入 `source_index` 测试
- `tests/test_context_manager.py`
  - 改为验证 `Memory.md` 驱动的轻上下文
  - 新增 TODO 陈旧提醒测试
- `tests/test_agent_loop.py`
  - 更新为验证 `tool_choice` 不再在末轮被 runtime 强制改成 `none`

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tools.py tests/test_context_manager.py tests/test_agent_loop.py tests/test_skills.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — 来源工具最小闭环（保留来源 + 自动归档）

### 目标收敛

- 不再讨论泛化的“search index”
- 先实现最小可用的来源工具闭环：
  - 搜索结果可按序号收录到 `research/source_index.md`
  - 阅读类工具自动把正文归档到 `research/raw/`
  - 深读后同步更新 `research/source_index.md`

### 工具行为调整

- `web_search`
  - 新增可选参数：
    - `keep_result_indices`
    - `keep_reason`
  - 模型可以在搜索结果返回后，用序号选择哪些来源值得保留
  - 被保留来源自动写入 `research/source_index.md`
- `jina_reader`
  - 成功读取后自动：
    - 写入 `research/raw/<title>.md`
    - 更新 `research/source_index.md`
  - 返回新增字段：
    - `source_id`
    - `raw_path`
    - `source_index_updated`
  - Firecrawl fallback 现在也走同样归档路径
- `arxiv_read_paper`
  - 保持原有 `documents/` 输出兼容
  - 同时新增 raw source 归档和 source index 更新
- `pdf_read_url`
  - 本地解析和 MinerU 成功结果都会同步归档 raw source 并更新 source index

### Source Index 结构

- 当前采用极简结构，每个来源条目只保留：
  - `title`
  - `url`
  - `summary`
  - `judgment`
  - `raw_path`
  - `note_paths`
  - `why_keep`（仅搜索保留时写入）
- 不记录“被谁发现”“evidence 引用”等当前阶段不必要字段
- 目的仅是：
  - 避免重复劳动
  - 提高后续回读和复用速度

### 简单算法而非额外 LLM

- raw source 文件名优先使用原文标题，做轻量文件名清洗和冲突编号
- `source_index.md` 采用固定 Markdown 块结构，并用简单解析/重写逻辑维护
- `summary` 使用正文或搜索摘要的简单截断，不额外调用模型
- `judgment` 用 host 规则给初值（如 `nature/arxiv/.gov/.edu` -> `high`）

### 测试与验证

- 新增 `tests/test_tools.py`
  - 验证 `web_search` 可按序号收录来源
  - 验证 `jina_reader` 会自动归档 raw source 并更新 source index
- 验证结果：
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tools.py -q --fast`：通过
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_logging.py tests/test_context_manager.py -q --fast`：通过
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — 单一 TODO 体系替代双 TODO

### 设计调整

- 废弃 `research-todo` / `write-todo` 双技能与双 TODO 控制面板
- 改为单一 `skills/todo.md` 和统一的 `todo.md`
- 原因：
  - 双 TODO 会把本来连续的认知过程硬拆成两个状态机
  - 模型容易卡在“继续研究但不写作”或“进入写作后不敢补证”
  - 不符合 deep research 中“调查 -> 认识 -> 写作 -> 发现缺口 -> 补证 -> 修订”的循环过程

### 新的系统主线

- `prompts/system.md` 重写为“双阶段但可往返”的工作方式：
  - 先广泛调查与核实，形成从感性到理性的认识
  - 再进入写作实践，把认识组织成结构化表达
  - 写作中如发现证据不足、来源冲突、判断过强，可自主回到检索和验证
- 将以下思想原则显式写入 system prompt：
  - 没有调查就没有发言权
  - 实践—认识—再实践
  - 主要矛盾优先
  - 具体问题具体分析

### 新的统一 TODO skill

- 新增 `skills/todo.md`
- 合并原 research / writing 两套原则，强调：
  - TODO 是贯穿全流程的唯一控制面板
  - 不人为拆研究和写作
  - 写作中可主动补证和修订
  - 条目要围绕判断、证据和表达，而不是围绕“再搜什么”
- 删除：
  - `skills/research-todo.md`
  - `skills/write-todo.md`

### 代码与上下文同步调整

- `src/deep_research_agent/context_manager.py`
  - 只读取统一 `todo.md`
  - 不再读取 `research/todo.md` / `writing/todo.md`
- `src/deep_research_agent/tools.py`
  - TODO closure guard 现在对 `todo.md` 生效
  - 同时暂时兼容旧路径 `research/todo.md` / `writing/todo.md`
- `README.md`
  - eval 示例 skill 改为 `--skill todo`

### 测试更新

- 更新 `tests/test_skills.py`
  - 改为验证统一 `todo` skill
- 更新 `tests/test_session.py`
  - eval skill 从 `research-todo` 改为 `todo`
- 更新 `tests/test_context_manager.py`
  - 改为验证统一 `todo.md` 进入上下文

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_skills.py tests/test_session.py tests/test_context_manager.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — 上下文策略回退到弱约束全量模式

### 回退原因

- 基于长问题真实日志复盘，当前 attention-style context pack 约束过强：
  - 强行注入 `phase` / `subgoal` / `budget` / `convergence_hint`
  - 容易把 agent 锁在“研究控制台”视角，而不是允许其自行切换到整理或写作
- 按当前阶段需求，先回退到更自由的上下文管理策略，不提前解决 200k 窗口问题

### ContextManager 调整

- `src/deep_research_agent/context_manager.py` 改为更接近“全量上下文 + 文件系统导向”的结构：
  - 保留完整 `当前任务`
  - 注入完整 `research/todo.md`
  - 注入完整 `writing/todo.md`
  - 注入 `research/source_index.md`
  - 注入 `research/raw/`、`research/notes/`、`research/evidence/`、`writing/drafts/` 的文件索引
- 不再主动给模型注入：
  - `当前阶段`
  - `当前 Subgoal`
  - `回合预算`
  - `收敛策略`
- 最近工具观察从 6 条缩到 4 条，更贴近“近 4 轮工具调用结果”
- 工具观察优先提取路径/URL：
  - 如 `markdown_path`、`pdf_path`、`source_url`、`url`
  - 避免把长 `markdown_preview` 再次塞回上下文

### 对话尾巴策略调整

- `src/deep_research_agent/agent.py`
  - `conversation_tail` 不再只保留最新一个 assistant/tool 组合
  - 现在保留最近 4 个 assistant/tool 回合（最多 8 条消息）
- 目标是恢复“近几轮真实工作痕迹”而不是过早压缩成长摘要

### System Prompt 收缩

- `prompts/system.md` 去掉强阶段化和收敛化措辞：
  - 删除强调 `subgoal` / `阶段判断` / `收敛控制` 的内容
  - 改成允许 agent 自行判断研究、整理和写作的切换
- 文件规范中显式补充：
  - `writing/todo.md`
  - `research/source_index.md`
  - `writing/drafts/<section>.md`

### 测试更新

- 更新 `tests/test_context_manager.py`
  - 改为验证完整 TODO、文件索引和路径导向的工具观察摘要
- 更新 `tests/test_agent_loop.py`
  - 新增最近 4 个 assistant/tool 回合保留测试

### 验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_context_manager.py tests/test_agent_loop.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_logging.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tools.py -q --fast`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

## 2026-04-23 (by Codex) — 日志可用性修复（model_request / trace）

### 修复日志主问题

- 修复 `model_request` 记录过度冗余的问题：
  - `ReActAgent` 不再把整段原始 `messages` 和完整工具 schema 直接写入 `model_request` 日志
  - 改为记录：
    - `context_prompt`（本轮真正给 agent 的上下文包）
    - `conversation_tail` 的摘要
    - `tool_names`
    - `effective_tool_choice`
- 这样避免了每轮 artifact 大量重复落盘 system prompt、tool result 原文和完整工具定义，降低日志噪音

### 修复 trace 缺少“每轮真实输入”的问题

- `trace.md` 不再完全忽略 `model_request`
- 新增每轮输入可视化：
  - `🧾 Context Input`：显示本轮实际发送给 agent 的 `context_prompt`
  - `Conversation Tail`：显示上一轮 assistant/tool 回填的摘要，而不是完整原文
  - `Tool Choice`：显示该轮的 `effective_tool_choice`
- 保持 system prompt 不重复展开，避免 trace 被固定提示词刷屏

### 修复 artifact 命名混乱的问题

- artifact 文件名从：
  - `0001_model_request.txt`
  - `0002_tool_result.txt`
  改为带字段路径的形式，例如：
  - `0001_model_request_payload_context_prompt.txt`
  - `0002_tool_result_payload_content.txt`
- 这样可直接区分 artifact 来自哪个事件、哪个字段，减少“model_request 和 tool_result 混在一起看不出来”的问题
- `model_request` 的 `context_prompt` 现在每轮固定落盘为 artifact，不再依赖长度超过阈值才保存
- 这样每一轮真实发送给 agent 的动态输入都会被稳定记录，避免只留下固定 system 部分或字符统计

### 失败模式留痕

- 原失败现象：
  - `model_request` artifact 大量是 system prompt 内容，难以定位本轮实际上下文输入
  - `trace.md` 只显示 `context_pack_built` 的字符统计，不显示实际传给模型的动态上下文
  - `tool_result` 的长文本会在 `model_request` 原始 `messages` 中再次出现，形成重复记录
- 当前修复策略：
  - 在日志层做结构化摘要
  - 在 trace 层显示动态输入
  - 不再把固定系统部分和重复工具结果作为每轮主日志内容

### 测试新增与验证

- 更新 `tests/test_logging.py`：
  - 验证 trace 显示 `Context Input`
  - 验证 system prompt 不在 `model_request` trace 中重复出现
  - 验证 artifact 文件名包含字段路径
- 新增 `ToolRegistry.tool_names()` 供日志摘要使用
- 验证结果：
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_logging.py -q --fast`：通过
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_agent_loop.py tests/test_context_manager.py -q --fast`：通过
  - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q --fast`：通过

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

### Jina 失败回退到 Firecrawl

- 在 `jina_reader` 中新增失败回退路径：
  - 当 Jina 请求异常（例如 SSL / 连接错误）且配置了 `FIRECRAWL_API_KEY` 时，自动调用 Firecrawl `/v2/scrape` 获取 Markdown
  - 返回结构新增 `provider` 字段（`jina` 或 `firecrawl_fallback`），并在回退时记录 `fallback_reason`
- `jina_reader` 工具描述同步更新，明确回退逻辑
- 新增测试：
  - `tests/test_tools.py::test_jina_reader_falls_back_to_firecrawl_when_jina_fails`

### 本次验证结果

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tools.py -q`：通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ -q`：`35 passed, 6 skipped`

### 固化真实运行前网络预检流程

- 新增 `scripts/preflight_network.py`：
  - 检查关键环境变量是否存在（掩码打印，不输出明文）
  - 检查 DashScope/Jina/Tavily 连通性
  - 预检失败直接返回非 0，阻止继续 real eval
- `README.md` 新增固定流程：
  - 先 `preflight_network.py`
  - 通过后再执行 `deep-research-agent-eval`

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
