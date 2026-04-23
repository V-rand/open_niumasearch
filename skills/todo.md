你将维护一个统一的 `todo.md` 文件，作为你的**核心进度表**。

## 绝对红线规则

1. **先写防火墙**：在 `todo.md` 最顶部列出所有 `IMPORTANT CONSTRAINT`（禁止项）。
2. **行动必闭合**：禁止在产出笔记或草稿时不更新 TODO。**在一个 Turn 中，如果你写入了新笔记，必须同时使用 `fs_patch` 将对应的 TODO 项标记为 `[x]`。**
3. **查重预检**：在调用任何 `jina_reader` 或 `pdf_read_url` 之前，必须先 `fs_read` `research/source_index.md`。如果 URL 已经读过，严禁重复调用，直接读取对应的 `raw/` 文件。

## 文件格式

```markdown
# 绝对约束 (FIREWALL)
- **禁止项 1**：不允许搜索 XXX

# 任务目标
（简述最终要交付什么）

## 进度看板

- [x] 已完成：完成了对 XXX 的调研，产出笔记 `research/notes/xxx.md`
- [ ] 进行中：正在深度阅读关于 YYY 的材料
- [ ] 待处理：撰写最终报告
```

## 反模式（违规表现）

1. **只搜不闭合**：开了 5 个 TODO 项，读了 10 篇文章，但 TODO 一个都没打钩。
2. **重复采集**：明明 `source_index.md` 里有了，还去调用 `jina_reader`。
3. **大词堆砌**：TODO 闭合结论里写“深度赋能”，实际上没产出任何具体事实。
