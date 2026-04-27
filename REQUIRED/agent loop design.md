# 底层 Agent Loop 与工具使用设计说明（ReAct 模式，V0.2）

## 1. 文档目的

本文档定义系统最底层的 agent loop 抽象，以及工具调用的运行时设计。这里的“React 模式”按项目语境指的是 ReAct 风格的循环：Thought -> Act -> Observe -> Thought -> ... -> Final。

本文件回答三个问题：

1. 底层 agent class 应该长什么样。
2. 一次 turn 与一次 step 如何定义。
3. 百炼 API 下如何实现 thinking、tool calling、并行工具调用与交错式推理。

---

## 2. 核心抽象

### 2.1 Agent 的最底层抽象

最底层抽象定义为一个 ReAct Agent 类。它不关心具体业务是 research 还是 writing，只负责在一个受控循环中驱动模型与工具交互。

循环模式如下：

Thought -> Act(tool) -> Observe -> Thought -> ... -> Final

这里的关键不是名字，而是约束：

- 模型不能无 observation 地连续跳多个外部动作。
- 每次工具结果返回后，都允许模型再次思考，再决定下一步。
- 最终回复不是默认直接生成，而是在若干轮 observation 后满足停止条件时生成。

### 2.2 Turn 的定义

本项目约定：每调用一次模型 API，即为一个 turn。

也就是说：

输入文本/上下文 -> 模型思考 -> 模型输出自然语言或工具调用请求

这个完整过程，算一个 turn。

如果模型请求工具，工具执行完后再次调用模型，则下一次 API 调用算下一个 turn。

### 2.3 Step 的定义

在 runtime 层，一个 step 是一个更宽的概念，可以包含：

- 本轮 prompt 组装
- 一次模型调用
- 零个或多个并行工具执行
- 一次 observation 汇总
- 状态落盘

通常：

- 一个只输出 final answer 的 step，对应一个 turn。
- 一个请求并行工具的 step，仍然只对应一个 turn，但会包含多个 tool execution 子事件。

---

## 3. Thinking 设计

### 3.1 总原则：所有动作前都要有 thinking

本项目要求：模型所有动作开始前都必须有 thinking。

这里的 thinking 不是追求神秘的“隐藏推理全文”，而是要求模型在每次行动前显式形成一段短的 decision note 或 reasoning summary，用于说明它为什么要做这个动作。

因此：

- 输出 final answer 前需要 thinking。
- 发起工具调用前需要 thinking。
- 收到工具结果后继续下一步前也需要 thinking。

### 3.2 交错思考（interleaved thinking）

交错思考是底层 loop 的强约束。
模型所有动作开始前都需要thinking
工具调用时也一样
交错思考
在接收每个工具结果后进行思考，允许它在继续之前对中间结果进行推理
User: "What's the total revenue if we sold 150 units at $50 each,
       and how does this compare to our average monthly revenue?"

step 1: [thinking] "I need to calculate 150 * $50 first..."
        [tool_use: calculator] { "expression": "150 * 50" }
  ↓ tool result: "7500"

step 2: [thinking] "Got $7,500. Now I should query the database to compare..."
        [tool_use: database_query] { "query": "SELECT AVG(revenue)..." }
        ↑ thinking after receiving calculator result
  ↓ tool result: "5200"

step 3: [thinking] "$7,500 vs $5,200 average - that's a 44% increase..."
        [text] "The total revenue is $7,500, which is 44% above your
        average monthly revenue of $5,200."
        ↑ thinking before final answer

这个模式不是可选优化，而是必须支持的底层行为。否则系统只能做“先规划，再一口气全做完”的脆弱流程。

### 3.3 对百炼的实现判断

根据官方文档，阿里云百炼支持 `enable_thinking` 控制深度思考模式，也支持 Function Calling、并行工具调用与 `tool_choice`，但它展示的工具使用模式仍然是应用侧通过 while-loop 进行下一轮调用的多步骤交互。官方文档没有提供一个“自动在每次工具结果后继续内部思考并调度下一步”的完整 agent runtime。citeturn767237search1turn863050search1

因此本项目必须自己实现交错思考循环，而不能假设百炼云侧已经替我们完成该编排。

结论是：

- `enable_thinking` 可以作为单轮模型调用中的思考开关使用。
- 但“收到工具结果后再次思考再决定下一步”必须由本项目的 while-loop 实现。

---

## 4. ReAct Agent 类设计

### 4.1 类职责

ReActAgent 是底层执行类，负责：

- 接收当前任务上下文
- 组装本轮 prompt
- 调用模型
- 解析模型输出
- 若有 tool_calls，则调度工具执行
- 汇总 observation
- 判断是否进入下一轮
- 满足停止条件时返回 final

### 4.2 不负责的事情

ReActAgent 不直接负责：

- 长期文件管理策略
- source/raw/notes/evidence 的业务含义解释
- 研究与写作的高层任务分解
- UI 展示

这些由上层 orchestration 或 harness 管理。

### 4.3 核心方法建议

建议最少拆出以下方法：

- `build_turn_context()`
- `call_model()`
- `parse_model_output()`
- `dispatch_tool_calls()`
- `aggregate_observation()`
- `apply_state_updates()`
- `should_stop()`
- `run_turn()`
- `run_until_final()`

如果后续加入 planning、verification，也是在此基础上扩展，而不是另起一套循环。

---

## 5. 单轮行为规范

### 5.1 输入

单轮输入至少包括：

- phase
- 当前 subgoal
- 当前 TODO slice
- 当前上下文 blocks
- 最近 observation
- 工具清单
- 本轮策略约束（例如 tool_choice / max_parallel / thinking_mode）

### 5.2 模型输出类型

模型本轮返回必须归一化为以下几类之一：

1. Final：直接输出最终文本。
2. Tool Request：请求调用一个或多个工具。
3. Structured Update：请求更新 TODO / file intent / note intent。
4. Final + Metadata：输出最终文本，同时带关闭建议、信心、未决项等元信息。

### 5.3 工具调用后必须产生 observation

每次工具执行完成后，不允许直接把工具结果当作 final answer 返回给用户。工具结果必须先转成 observation，加入上下文，再交由模型进行下一轮思考。

---

## 6. 工具调用设计

### 6.1 工具调用使用百炼 Function Calling，但不使用其内置工具

项目当前明确要求：不使用百炼内置工具，而是使用自定义外部工具。这个选择和项目整体设计一致，因为我们需要自己管理文件、上下文、日志和工具行为。

百炼官方的 Function Calling 模式支持通过 `tools` 传入工具描述，并由模型返回 `tool_calls`；工具真正执行仍由应用侧负责。citeturn863050search1turn767237search1

### 6.2 并行工具调用

系统必须支持并行工具调用。

适用条件：

- 多个工具请求之间无依赖
- 工具执行彼此独立
- 返回结果可以在一次 observation 中统一汇总

例如：

- “北京和上海的天气如何”
- “杭州天气，以及现在几点了”

这类请求可以在 `parallel_tool_calls=true` 下由模型一次返回多个 tool_calls，再由 runtime 并行执行。官方文档明确给出了该参数和行为说明。citeturn767237search1turn863050search1

### 6.3 串行工具调用

当任务存在依赖关系时，不得并行。

例如：

- 先查某网页摘要，再决定是否读取全文
- 先查询数据库得到 ID，再用 ID 去调详情接口
- 先获取搜索结果，再根据结果决定下一步 query

这类任务必须使用 while-loop 串行推进。

### 6.4 工具选择方式

系统需要支持：

- auto
- force specific tool
- none

百炼官方 `tool_choice` 已覆盖这三类控制。第一版应在 runtime 中统一封装，不把供应商细节泄露到业务层。citeturn863050search4turn767237search1

---

## 7. 停止条件与 final 生成

### 7.1 停止条件

ReAct loop 不能无限运行。系统需要有明确停止条件。

典型停止条件包括：

- 模型明确输出 final answer
- 当前 subgoal 达到 closure 条件
- 触发最大 turn 限制
- 工具调用失败次数达到阈值
- 当前问题被判断为无法继续推进，需要 defer 或 escalate

### 7.2 final answer 前仍要 thinking

无论循环进行了多少轮，最终输出前仍必须经过一次 thinking。这个 thinking 应该完成两件事：

- 判断是否真的已经足够回答
- 对已有 observation 做最后整合

### 7.3 final 与 task close 不是同义词

某一轮生成 final answer，不等于 TODO 自动 closed。是否关闭任务，仍需走 closure attempt 和状态校验流程。

---

## 8. 错误处理与回退

### 8.1 工具执行失败

若工具执行失败，系统应：

1. 记录 tool error。
2. 将错误信息转成 observation。
3. 重新交给模型决定下一步：重试、换工具、降级、放弃或向用户说明限制。

### 8.2 模型返回非法工具参数

若模型生成的工具参数不合法，runtime 不应直接调用工具，而应将参数校验错误反馈为 observation，再让模型自修复。

### 8.3 并发结果不一致

若并行工具执行后结果结构不一致，runtime 应先做标准化，再汇总成 observation。标准化失败时应回退为多个 error/partial observations。

---

## 9. 日志与回放配合

ReAct loop 的每一步必须被完整记录，以便复盘。

每个 step 至少应落盘：

- 输入 context manifest
- 模型可见 prompt
- 模型显式输出
- 工具请求
- 工具返回
- observation 汇总
- 下一轮上下文 diff
- state diff
- 停止判断结果

这样后续才能比较：

- 同一个任务在不同 prompt 策略下的行为差异
- 同一个工具 schema 是否影响模型选工具
- thinking 开启/关闭是否影响工具使用质量

---

## 10. 百炼适配建议

### 10.1 推荐基础路径

第一版建议采用 OpenAI 兼容接口，原因是生态成熟、便于与现有工具注册和 runtime 代码整合。官方文档也将其列为迁移和集成第三方工具成本较低的路径。citeturn863050search2

### 10.2 enable_thinking 的使用建议

- 对复杂决策、query 生成、是否读取全文、是否关闭任务等环节，建议开启。
- 对纯工具结果总结、格式化输出等低复杂步骤，可根据成本策略关闭。

官方说明 `enable_thinking` 为深度思考模式开关，适用于混合思考模式模型。citeturn767237search1turn839408search4

### 10.3 不依赖供应商内置多轮 context 管理

Responses API 虽然提供内置多轮上下文管理和内置工具，但本项目需要完整掌控：

- 外部文件对象
- 自定义工具
- 运行日志
- 可重放上下文
- TODO 状态机

因此第一版不应依赖 Responses API 的内置 agent 行为，而应由本项目 loop 自行维护对话状态和工具循环。官方文档对 Responses 的定位也偏向“内置工具、无需手动维护对话历史”，这与本项目的自管理目标不一致。citeturn863050search2

---

## 11. 一个推荐的最小执行序列

对于单个 ReAct step，推荐的最小执行序列如下：

1. 从 state 中读取当前 phase、subgoal、TODO slice、active blocks。
2. 由 harness 组装 prompt。
3. 调用模型，开启或关闭 thinking 模式。
4. 解析返回：若是 final，则进入停止判断；若是 tool_calls，则继续。
5. 对无依赖 tool_calls 并行执行；有依赖则串行执行。
6. 将工具结果汇总为 observation blocks。
7. 写入日志与状态快照。
8. 重新组装下一轮 prompt。
9. 重复，直到满足停止条件。

这个序列是整个系统最底层的“心跳”。后续研究流程、写作流程、TODO 机制、checkpoint 机制，全部都建立在这个最小循环之上。

---

## 12. 结论

底层 agent loop 的设计原则可以概括为：

**模型每一跳都要先想，再做，再看，再决定下一步；工具只是 observation 的生产者，不是最终答案的直接替代；供应商 API 只提供单轮能力，真正的多轮 ReAct 编排必须由本项目 runtime 自己实现。**

这条原则一旦立住，上层的 research、writing、logging、todo 管理就都有了坚实的底层执行基础。
