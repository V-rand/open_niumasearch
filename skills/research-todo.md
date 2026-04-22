---
name: research-todo
description: >-
  管理研究阶段的 TODO 列表。当任务处于信息收集、来源筛选、证据采集阶段时使用。
  仅在当前 phase 为 research 时激活。不要用于写作阶段。
---

# Research TODO

## 核心原则

- TODO 是研究控制面板，不是执行脚本。模型每轮读取后自主决定下一步。
- 条目必须写成**目标型**，不是动作型。
- 状态必须如实反映，禁止伪装完成。

## 状态定义

| 状态 | 含义 |
|------|------|
| `open` | 待处理 |
| `in_progress` | 正在处理 |
| `tentatively_resolved` | 看似完成，但尚未满足关闭条件 |
| `closed` | 已完成并通过 closure attempt |
| `deferred` | 推迟，当前不处理 |
| `abandoned` | 放弃，记录原因 |

## 条目写法

好例子：
- 确认 claim-2 是否至少有两条独立来源支撑，否则下调表述强度
- 核实作者机构和发表时间线，并记录是否存在来源冲突

坏例子：
- 搜一下相关文章
- 看作者背景

## 更新流程

1. 读取当前 `research/todo.md`
2. 评估本轮进展，更新对应条目状态
3. 发现新问题时追加条目
4. 对接近完成的条目发起 closure attempt

## Closure Attempt

模型只能发起 closure attempt，不能直接标 `closed`。

Closure attempt 必须输出：

```
结论：<一句话结论>
依据：<绑定的外部对象，如研究笔记或证据记录路径>
未决项：<如有>
```

若写不出这三行，说明任务还不应关闭，保持 `tentatively_resolved` 或 `in_progress`。

## One-shot 示例

### 初始状态

```markdown
#  transformer 注意力机制研究

## 目标
确认 transformer 中注意力机制的核心设计决策及其后续演化。

## 任务列表

- [ ] open: 确认原始 transformer 论文中注意力机制的核心公式与复杂度
- [ ] open: 找到至少两条独立来源说明注意力机制在后续模型中的改进方向
- [ ] open: 核查是否存在对注意力机制效率瓶颈的系统性批评

## 阶段动态
- 2026-04-22: 初始化 research TODO
```

### 一轮检索后的更新

```markdown
# transformer 注意力机制研究

## 目标
确认 transformer 中注意力机制的核心设计决策及其后续演化。

## 任务列表

- [x] closed: 确认原始 transformer 论文中注意力机制的核心公式与复杂度
  - 结论：核心公式为 scaled dot-product attention，复杂度 O(n²d)
  - 依据：research/notes/attention_basics.md
  - 未决项：无
- [ ] in_progress: 找到至少两条独立来源说明注意力机制在后续模型中的改进方向
- [ ] open: 核查是否存在对注意力机制效率瓶颈的系统性批评

## 阶段动态
- 2026-04-22: 初始化 research TODO
- 2026-04-22: 完成原始论文核心公式确认，已记录至 research/notes/attention_basics.md
```

## 反模式

- 不要给未真正完成的事项打勾或标 `closed`
- 不要把动作型条目（"搜一下"）直接执行后就认为完成
- 不要在 research 阶段维护 writing TODO
- 不要把 TODO 当成一次性计划表，它应该随研究进展动态演化
