from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def create_todo_markdown(*, phase: str, title: str) -> str:
    date_str = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if phase == "research":
        return f"""# {title} - 研究 TODO

## 目标
一句话说明本轮研究要完成什么。

## 任务列表

- [ ] open: 明确核心研究问题与判断标准
- [ ] open: 确认第一批需要优先检索的关键词或方向
- [ ] open: 补齐当前证据缺口
- [ ] open: 核查关键来源之间是否存在冲突

## 阶段动态
- {date_str}: 初始化 research TODO
"""
    if phase == "writing":
        return f"""# {title} - 写作 TODO

## 目标
一句话说明本轮写作要完成什么。

## 任务列表

- [ ] open: 明确文章结构与段落目标
- [ ] open: 完成正文草稿并补齐关键证据
- [ ] open: 检查论证链完整性

## 阶段动态
- {date_str}: 初始化 writing TODO
"""
    raise ValueError(f"Unsupported phase: {phase}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a Markdown TODO file.")
    parser.add_argument("--phase", required=True, choices=["research", "writing"])
    parser.add_argument("--title", default="未命名任务")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        create_todo_markdown(phase=args.phase, title=args.title),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
