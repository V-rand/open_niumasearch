from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

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
        self._recent_observations: deque[str] = deque(maxlen=6)
        self._soft_context_target_chars = 60_000

    def record_tool_observation(self, tool_name: str, content: str, *, is_error: bool) -> None:
        status = "error" if is_error else "ok"
        compact = self._compact_text(content, max_chars=480)
        self._recent_observations.append(f"- [{status}] {tool_name}: {compact}")

    def build_context_payload(self, *, user_input: str) -> str:
        pack = self.build_context_pack(user_input=user_input)
        return pack.rendered_prompt

    def build_context_pack(self, *, user_input: str) -> ContextPack:
        phase = "research"
        todo_text = self._read_text("research/todo.md")
        subgoal = self._extract_current_subgoal(todo_text)
        todo_slice = self._extract_todo_slice(todo_text)
        sources_summary = self._collect_source_summary()
        notes_summary = self._collect_recent_markdown_block("research/notes", title="活跃研究笔记")
        evidence_summary = self._collect_recent_markdown_block("research/evidence", title="活跃证据")
        checkpoint_summary = self._collect_recent_markdown_block("research/checkpoints", title="前序 Checkpoint")
        observations_summary = "\n".join(self._recent_observations) if self._recent_observations else "- 暂无工具观察"

        sections = {
            "input_task": user_input.strip(),
            "phase": phase,
            "subgoal": subgoal,
            "todo_slice": todo_slice,
            "sources_summary": sources_summary,
            "notes_summary": notes_summary,
            "evidence_summary": evidence_summary,
            "checkpoint_summary": checkpoint_summary,
            "observations_summary": observations_summary,
        }
        block_char_counts = {key: len(value) for key, value in sections.items()}
        trimmed_blocks: list[str] = []

        total_chars = sum(block_char_counts.values())
        if total_chars > self._soft_context_target_chars:
            for key in ("sources_summary", "notes_summary", "evidence_summary", "checkpoint_summary"):
                original = sections[key]
                compact = self._compact_text(original, max_chars=2_000)
                if compact != original:
                    sections[key] = compact
                    trimmed_blocks.append(key)
            block_char_counts = {key: len(value) for key, value in sections.items()}

        rendered = (
            "# 上下文包\n\n"
            f"## 当前阶段\n{sections['phase']}\n\n"
            f"## 当前任务\n{sections['input_task']}\n\n"
            f"## 当前 Subgoal\n{sections['subgoal']}\n\n"
            f"## TODO 切片\n{sections['todo_slice']}\n\n"
            f"## 活跃来源\n{sections['sources_summary']}\n\n"
            f"## 活跃研究笔记\n{sections['notes_summary']}\n\n"
            f"## 活跃证据\n{sections['evidence_summary']}\n\n"
            f"## 前序阶段沉淀\n{sections['checkpoint_summary']}\n\n"
            f"## 最近观察\n{sections['observations_summary']}\n\n"
            "请围绕当前 subgoal 推进，优先补齐关键证据链，并保持 TODO 的收敛更新。"
        )
        return ContextPack(
            phase=phase,
            subgoal=subgoal,
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

    def _extract_current_subgoal(self, todo_text: str) -> str:
        if not todo_text.strip():
            return "未定义（尚未初始化 research/todo.md）"

        task_lines = [line.strip() for line in todo_text.splitlines() if line.strip().startswith("- [")]
        for line in task_lines:
            if "in_progress:" in line:
                return line.split("in_progress:", 1)[1].strip()
        for line in task_lines:
            if "open:" in line:
                return line.split("open:", 1)[1].strip()
        if task_lines:
            return task_lines[0]
        return "未定义（TODO 中没有任务条目）"

    def _extract_todo_slice(self, todo_text: str) -> str:
        if not todo_text.strip():
            return "- 暂无 todo 文件"
        lines = todo_text.splitlines()
        in_tasks = False
        chosen: list[str] = []
        for raw in lines:
            line = raw.rstrip()
            if line.startswith("## 任务列表"):
                in_tasks = True
                continue
            if in_tasks and line.startswith("## "):
                break
            if in_tasks and line.strip().startswith("- ["):
                chosen.append(line.strip())
                if len(chosen) >= 6:
                    break
        if not chosen:
            return "- 未识别到任务条目"
        return "\n".join(chosen)

    def _collect_source_summary(self) -> str:
        source_index = self._read_text("research/source_index.md")
        if not source_index.strip():
            return "- 暂无 source_index.md"
        lines = [line.strip() for line in source_index.splitlines() if line.strip().startswith("-")]
        if not lines:
            compact = self._compact_text(source_index, max_chars=1_000)
            return compact
        return "\n".join(lines[:8])

    def _collect_recent_markdown_block(self, relative_dir: str, *, title: str) -> str:
        directory = self.workspace_root / relative_dir
        if not directory.exists() or not directory.is_dir():
            return f"- 暂无 {title}"
        files = sorted(
            [path for path in directory.glob("*.md") if path.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return f"- 暂无 {title}"

        items: list[str] = []
        for path in files[:3]:
            text = path.read_text(encoding="utf-8")
            preview = self._compact_text(text, max_chars=600)
            rel = path.relative_to(self.workspace_root)
            items.append(f"- {rel}\n{preview}")
        return "\n\n".join(items)

    def _compact_text(self, text: str, *, max_chars: int) -> str:
        collapsed = re.sub(r"\n{3,}", "\n\n", text.strip())
        if len(collapsed) <= max_chars:
            return collapsed
        return collapsed[:max_chars].rstrip() + "\n...(truncated)"
