from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_research_agent.logging import RunLogger


@dataclass(slots=True)
class ContextPack:
    phase: str
    subgoal: str
    todo_slice: str
    sources_summary: str
    notes_summary: str
    evidence_summary: str
    checkpoint_summary: str
    observations_summary: str
    rendered_prompt: str
    block_char_counts: dict[str, int]
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
        self._soft_context_target_chars = 180_000
        self._stale_todo_turns = 0

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
        del turn_index, max_turns

        memory_text = self._read_text("Memory.md") or self._default_memory_overview()
        observations_summary = "\n".join(self._recent_observations) if self._recent_observations else "- 暂无最近工具观察"
        todo_reminder = self._build_todo_reminder()

        sections = {
            "input_task": user_input.strip(),
            "phase": "agent_managed",
            "subgoal": "",
            "todo_slice": self._render_text_block(memory_text, default="- 暂无 Memory.md"),
            "sources_summary": todo_reminder,
            "notes_summary": "",
            "evidence_summary": "",
            "checkpoint_summary": "",
            "observations_summary": observations_summary,
            "raw_sources": "",
        }
        block_char_counts = {key: len(value) for key, value in sections.items()}
        trimmed_blocks: list[str] = []

        total_chars = sum(block_char_counts.values())
        if total_chars > self._soft_context_target_chars:
            for key in (
                "sources_summary",
                "notes_summary",
                "evidence_summary",
                "checkpoint_summary",
                "raw_sources",
            ):
                original = sections[key]
                compact = self._compact_text(original, max_chars=6_000)
                if compact != original:
                    sections[key] = compact
                    trimmed_blocks.append(key)
            block_char_counts = {key: len(value) for key, value in sections.items()}

        rendered = (
            "# 工作上下文\n\n"
            f"## 当前任务\n{sections['input_task']}\n\n"
            f"## Workspace Memory\n{sections['todo_slice']}\n\n"
            f"## TODO Reminder\n{sections['sources_summary']}\n\n"
            f"## 最近工具观察\n{sections['observations_summary']}\n\n"
            "请先读取并推进真实文件，再决定是否继续搜索、深读、写作或补证。"
            " 优先使用 `todo_manage` 或文件工具维护 `todo.md`，并通过 `fs_read` 动态读取 Memory 中列出的路径。"
        )
        return ContextPack(
            phase=sections["phase"],
            subgoal=sections["subgoal"],
            todo_slice=sections["todo_slice"],
            sources_summary=sections["sources_summary"],
            notes_summary=sections["notes_summary"],
            evidence_summary=sections["evidence_summary"],
            checkpoint_summary=sections["checkpoint_summary"],
            observations_summary=sections["observations_summary"],
            rendered_prompt=rendered,
            block_char_counts=block_char_counts,
            trimmed_blocks=trimmed_blocks,
        )

    def _read_text(self, relative_path: str) -> str:
        path = self.workspace_root / relative_path
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def _render_todo_block(self, text: str, *, default: str) -> str:
        if not text.strip():
            return default
        return text.strip()

    def _render_text_block(self, text: str, *, default: str) -> str:
        if not text.strip():
            return default
        return text.strip()

    def _collect_file_manifest(self, relative_dir: str, *, title: str) -> str:
        directory = self.workspace_root / relative_dir
        if not directory.exists() or not directory.is_dir():
            return f"- 暂无 {title}"
        files = sorted(path for path in directory.rglob("*.md") if path.is_file())
        if not files:
            return f"- 暂无 {title}"

        items: list[str] = []
        for path in files:
            rel = path.relative_to(self.workspace_root)
            title_line = self._extract_first_heading(path)
            if title_line:
                items.append(f"- {rel} | {title_line}")
            else:
                items.append(f"- {rel}")
        return "\n".join(items)

    def _extract_first_heading(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return ""

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

    def _default_memory_overview(self) -> str:
        return (
            "- `Memory.md` 缺失，请创建它并记录工作区入口。\n"
            "- 关键入口通常包括 `todo.md`、`research/source_index.md`、`research/raw/`、"
            "`research/notes/`、`research/evidence/`、`writing/drafts/`、`research/report.md`。"
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
