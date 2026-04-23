from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import tiktoken
    _TOKENIZER = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _TOKENIZER = None

if TYPE_CHECKING:
    from deep_research_agent.logging import RunLogger


@dataclass(slots=True)
class ContextPack:
    todo_slice: str
    sources_summary: str
    notes_summary: str
    observations_summary: str
    rendered_prompt: str
    block_char_counts: dict[str, int]
    token_count: int
    trimmed_blocks: list[str]


class ContextManager:
    def __init__(
        self,
        workspace_root: Path,
        *,
        logger: RunLogger | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.logger = logger
        self._recent_observations: deque[str] = deque(maxlen=4)
        self._stale_todo_turns = 0

    def estimate_tokens(self, text: str) -> int:
        if _TOKENIZER:
            return len(_TOKENIZER.encode(text, disallowed_special=()))
        # Heuristic: 1 token approx 3 chars for English, 0.6 chars for Chinese
        # We'll use a conservative 1 token per 2 characters
        return len(text) // 2

    def record_tool_observation(self, tool_name: str, content: str, *, is_error: bool) -> None:
        status = "error" if is_error else "ok"
        compact = self._summarize_tool_observation(content)
        self._recent_observations.append(f"- [{status}] {tool_name}: {compact}")

    def record_turn_progress(self, *, used_tools: bool, updated_todo: bool) -> None:
        if updated_todo:
            self._stale_todo_turns = 0
            return
        if used_tools:
            self._stale_todo_turns += 1

    def build_context_payload(
        self,
        *,
        user_input: str,
        turn_index: int | None = None,
        max_turns: int | None = None,
    ) -> str:
        pack = self.build_context_pack(user_input=user_input, turn_index=turn_index, max_turns=max_turns)
        return pack.rendered_prompt

    def build_context_pack(
        self,
        *,
        user_input: str,
        turn_index: int | None = None,
        max_turns: int | None = None,
    ) -> ContextPack:
        self.ensure_task_file(user_input)
        todo_text = self._read_text("todo.md") or "- 暂无 todo.md，请尽快初始化它。"
        recent_files = self._build_recent_workspace_map()
        observations_summary = "\n".join(self._recent_observations) if self._recent_observations else "- 暂无最近工具观察"
        todo_reminder = self._build_todo_reminder()

        sections = {
            "input_task": user_input.strip(),
            "todo_slice": todo_text,
            "sources_summary": todo_reminder,
            "notes_summary": recent_files,
            "observations_summary": observations_summary,
        }

        task_preview = self._compact_text(user_input.strip(), max_chars=280)
        if turn_index in (None, 1):
            rendered = (
                "## 启动工作\n"
                "- 原始任务已保存到 `task.md`。\n"
                "- 当前回合先建立工作面：优先读取或创建 `todo.md`，需要时创建 `research/source_index.md` 与相关研究文件。\n"
                "- 如果任务复杂，不要试图一次做完；先形成一个当前可闭合的小目标。\n\n"
                "## 原始任务预览\n"
                f"{task_preview}\n\n"
                "## 当前进度 (todo.md)\n"
                f"{sections['todo_slice']}\n\n"
                "## 工作区状态\n"
                f"{sections['notes_summary']}\n\n"
                "## 提醒\n"
                f"{sections['sources_summary']}\n\n"
                "**行动准则**：\n"
                "1. 原始任务在 `task.md`，后续优先延续已有工作，不要每轮重启任务。\n"
                "2. 重要状态保存在文件里，需要时主动读取，不要依赖这条消息重复展开全部上下文。\n"
                "3. 任何实质进展必须落到可验证产出。"
            )
        else:
            rendered = (
                "## 增量工作提示\n"
                "- 延续上一轮工作，不要重启任务。\n"
                "- 原始任务全文在 `task.md`；当前计划在 `todo.md`；来源索引在 `research/source_index.md`。\n"
                "- 需要细节时主动读取文件，不要指望这一轮提示重述全部背景。\n\n"
                "## 当前提醒\n"
                f"{sections['sources_summary']}\n\n"
                "## 最近工作区变化\n"
                f"{sections['notes_summary']}\n\n"
                "## 最近工具观察\n"
                f"{sections['observations_summary']}\n\n"
                "**行动准则**：\n"
                "1. 优先围绕当前目标形成可验证产出，而不是继续泛化搜索。\n"
                "2. 如果需要计划或约束，直接读取 `todo.md` 和 `task.md`。\n"
                "3. 保持对上一轮对话和工具结果的连续延续。"
            )
        
        token_count = self.estimate_tokens(rendered)
        
        return ContextPack(
            todo_slice=sections["todo_slice"],
            sources_summary=sections["sources_summary"],
            notes_summary=sections["notes_summary"],
            observations_summary=sections["observations_summary"],
            rendered_prompt=rendered,
            block_char_counts={k: len(v) for k, v in sections.items()},
            token_count=token_count,
            trimmed_blocks=[],
        )

    def ensure_task_file(self, user_input: str) -> None:
        path = self.workspace_root / "task.md"
        if path.exists():
            return
        path.write_text(user_input.strip() + "\n", encoding="utf-8")

    def _build_recent_workspace_map(self) -> str:
        """Build a very compact list of the last 5 modified files."""
        all_md_files = list(self.workspace_root.rglob("*.md"))
        if not all_md_files:
            return "- 工作区目前为空。"
        
        # Sort by modification time
        all_md_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        lines = ["最近修改的文件："]
        for f in all_md_files[:5]:
            rel = f.relative_to(self.workspace_root)
            lines.append(f"- {rel}")
        return "\n".join(lines)

    def _read_text(self, relative_path: str) -> str:
        path = self.workspace_root / relative_path
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def _summarize_tool_observation(self, content: str) -> str:
        parsed = self._try_parse_json_string(content)
        if isinstance(parsed, dict):
            prioritized = [
                ("path", parsed.get("path")),
                ("markdown_path", parsed.get("markdown_path")),
                ("pdf_path", parsed.get("pdf_path")),
                ("markdown_url", parsed.get("markdown_url")),
                ("url", parsed.get("url")),
                ("source_url", parsed.get("source_url")),
                ("title", parsed.get("title")),
                ("query", parsed.get("query")),
            ]
            parts = [f"{key}={value}" for key, value in prioritized if value]
            if parts:
                return "; ".join(parts[:4])
        return self._compact_text(content, max_chars=240)

    def _build_todo_reminder(self) -> str:
        if self._stale_todo_turns <= 0:
            return "- 新一轮开始前先读取 todo.md，并在出现实质推进后更新它。"
        return (
            f"- 已连续 {self._stale_todo_turns} 轮未更新 todo.md。"
            " 本轮优先回看并推进 TODO，再继续发散检索。"
        )

    def _compact_text(self, text: str, *, max_chars: int) -> str:
        collapsed = re.sub(r"\n{3,}", "\n\n", text.strip())
        if len(collapsed) <= max_chars:
            return collapsed
        return collapsed[:max_chars].rstrip() + "\n...(truncated)"

    def _try_parse_json_string(self, value: str) -> Any | None:
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
