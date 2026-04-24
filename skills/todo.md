<skill_identity>
你将维护一个统一的 `todo.md` 文件，作为整个研究过程的核心进度表。

它的作用不是复述大任务，也不是变成复杂的项目管理系统，而是帮助你回答四个问题：

1. 当前有哪些主要目标？
2. 当前最该推进的是哪一个？
3. 这个目标对应的可验证产出是什么？
4. 哪个目标已经因为产出落地而可以闭合？
</skill_identity>

<core_rules>
1. **先写防火墙**：在 `todo.md` 顶部列出任务中的 `IMPORTANT CONSTRAINT`、禁区或不能违反的要求。
2. **每个目标都必须绑定一个可验证产出**：没有产出的目标，不能算完成。
3. **只有在产出已经落地后才能闭合**：关闭目标时，必须能指出对应文件或结构化结果。
4. **抓当前主要矛盾**：如果同时存在很多未完成目标，优先指出当前最主要阻塞，并围绕它设定行动。
5. **允许当前小目标**：如果某个目标过大，应拆出一个更小、当前可闭合的小目标，帮助自己收敛。
6. **不要过度维护 TODO**：只有在出现真实推进、真实阻塞或新发现的必要工作块时，才更新 TODO。
7. **搜索和阅读必须服务于目标**：不能把 TODO 写成“继续搜更多”，而要写成“为了什么产出而搜”。
8. **阶段切换规则**：
   - 研究阶段：目标产出是 `research/notes/*.md` 或 `research/source_index.md`
   - 写作阶段：目标产出是 `research/report.md` 或 `writing/drafts/*.md`
   - 当研究目标已闭合时，必须转入写作，不能继续无限搜索
</core_rules>

<deliverables>
以下内容都可以作为目标产出：

- `research/source_index.md`
- `research/raw/*.md`
- `research/notes/*.md`
- `research/report.md`
- `writing/drafts/*.md`
- 一次已保存的结构化工具结果

闭合目标时，必须写清：

- 产出名称
- 产出路径
- 为什么它足以证明目标已完成
</deliverables>

<template>
统一用一个轻量结构，不要写太多层级。

```markdown
# 绝对约束 (FIREWALL)
- 不允许使用被明确禁用的论文或方法

# 最终交付
- 一份关于 XXX 的完整研究报告

## 当前目标

- [ ] 建立核心来源集合
  - 预期产出：`research/source_index.md`
  - 闭合条件：核心来源已经录入并可回查

- [ ] 提炼 Anthropic 长程 agent 设计要点
  - 预期产出：`research/notes/anthropic-long-running-agents.md`
  - 闭合条件：笔记已写出，且包含原文引用、关键判断、冲突与互补

- [ ] 当前小目标：确认 Qwen 团队关于模型"心理/人格/行为"研究的代表论文
  - 预期产出：`research/notes/qwen-model-behavior.md`
  - 闭合条件：已确定论文、记录来源，并说明为何纳入阅读清单

- [ ] 输出最终阅读清单
  - 预期产出：`research/report.md`
  - 闭合条件：覆盖主题、来源、推荐理由和分类结构
```
</template>

<usage>
1. 新一轮开始时，先读 `todo.md`。
2. 先判断当前最值得推进的一个目标，或当前最主要阻塞。
3. 如果目标过大，给自己补一个当前小目标。
4. 先通过检索和阅读形成感性认识，再通过 note、draft、report 把认识固定下来。
5. 搜索、阅读、写笔记都要围绕该目标的预期产出展开。
6. 当产出出现后，立即更新 TODO，记录闭合说明。
7. **关键：当研究目标已闭合时，停止搜索，转入写作。**
</usage>

<closure_template>
可以在闭合条目后追加一句简明说明：

```markdown
- [x] 提炼 Anthropic 长程 agent 设计要点
  - 产出：`research/notes/anthropic-long-running-agents.md`
  - 闭合说明：笔记已完成，包含原文引用、关键判断和对本项目的启发
```
</closure_template>

<anti_patterns>
1. **只搜不闭合**：读了很多来源，但没有形成任何 note、draft、report 或 source index 更新。
2. **无产出闭合**：在没有文件产出时把目标标记为完成。
3. **TODO 膨胀**：不断新增大目标，把 TODO 写成大任务复述器。
4. **没有当前焦点**：同时挂着很多并列目标，却没有一个当前小目标。
5. **写作断层**：已经有足够材料，却迟迟不写 note 或 report。
6. **无限搜索**：研究目标已闭合后仍继续搜索，不转入写作。
</anti_patterns>
