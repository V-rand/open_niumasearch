---
name: write-todo
description: >-
  管理写作阶段的 TODO 列表。当任务进入结构化写作、章节推进、论证表达阶段时使用。
  仅在当前 phase 为 writing 时激活。不要用于研究阶段。
---

# Write TODO

## 核心原则

- TODO 是写作控制面板，不是执行脚本。模型每轮读取后自主决定下一步。
- 条目必须写成**目标型**，不是动作型。
- 写作阶段允许局部补证，但补证结果以追加形式回流，不覆盖原有研究轨迹。

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
- 为章节 2 的 claim-3 补齐一级来源，否则将表述降级为"据部分研究显示"
- 检查段落 3 的论证链是否完整，缺失环节需补充或删除该 claim

坏例子：
- 写一下第二章
- 补充一些证据

## 更新流程

1. 读取当前 `writing/todo.md`
2. 评估本轮写作进展，更新对应条目状态
3. 发现证据缺口时追加补证条目
4. 对接近完成的条目发起 closure attempt

## Closure Attempt

模型只能发起 closure attempt，不能直接标 `closed`。

Closure attempt 必须输出：

```
结论：<一句话结论>
依据：<绑定的外部对象，如草稿段落或 claim-evidence 对齐记录路径>
未决项：<如有>
```

若写不出这三行，说明任务还不应关闭，保持 `tentatively_resolved` 或 `in_progress`。

## 补证规则

- 补证请求在 writing 域产生
- 补证动作调用研究能力
- 补证结果作为追加材料进入系统
- 不覆盖原有研究主轨迹

## One-shot 示例

### 初始状态

```markdown
#  transformer 技术综述写作

## 目标
完成一篇关于 transformer 注意力机制演化的技术综述。

## 任务列表

- [ ] open: 完成引言章节，说明注意力机制的研究背景与本文范围
- [ ] open: 完成核心设计章节，阐述原始 transformer 注意力公式与复杂度
- [ ] open: 完成改进方向章节，覆盖至少两种后续改进（如稀疏注意力、线性注意力）

## 阶段动态
- 2026-04-22: 初始化 writing TODO，基于 research/ 阶段产出开始写作
```

### 一轮写作后的更新

```markdown
# transformer 技术综述写作

## 目标
完成一篇关于 transformer 注意力机制演化的技术综述。

## 任务列表

- [x] closed: 完成引言章节，说明注意力机制的研究背景与本文范围
  - 结论：引言已覆盖 2017-2023 年注意力机制研究脉络
  - 依据：writing/drafts/section_01_intro.md
  - 未决项：是否需要补充 2024 年 Mamba 相关工作的对比
- [ ] in_progress: 完成核心设计章节，阐述原始 transformer 注意力公式与复杂度
- [ ] open: 完成改进方向章节，覆盖至少两种后续改进（如稀疏注意力、线性注意力）

## 阶段动态
- 2026-04-22: 初始化 writing TODO
- 2026-04-22: 完成引言章节草稿，已保存至 writing/drafts/section_01_intro.md
```

## 反模式

- 不要给未真正完成的事项打勾或标 `closed`
- 不要在 writing 阶段重新打开大规模研究流程
- 不要把写作 TODO 和研究 TODO 混在一起
- 不要把 TODO 当成一次性计划表，它应该随写作进展动态演化
