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
        self._soft_context_target_tokens = 100_000 # Aim for 100k safety buffer
        self._stale_todo_turns = 0
        self._turns_since_last_fs_list = 0

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
        
        if tool_name == "fs_list":
            self._turns_since_last_fs_list = 0
        else:
            self._turns_since_last_fs_list += 1

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
        # 1. Read the real todo.md
        todo_text = self._read_text("todo.md") or "- 暂无 todo.md，请尽快初始化它。"
        
        # 2. Optimized Workspace Map: Only show last 5 modifications
        recent_files = self._build_recent_workspace_map()

        observations_summary = "\n".join(self._recent_observations) if self._recent_observations else "- 暂无最近工具观察"
        todo_reminder = self._build_todo_reminder()

        sections = {
            "input_task": user_input.strip(),
            "phase": "agent_managed",
            "subgoal": "",
            "todo_slice": todo_text,
            "sources_summary": todo_reminder,
            "notes_summary": recent_files,
            "evidence_summary": "",
            "checkpoint_summary": "",
            "observations_summary": observations_summary,
            "raw_sources": "",
        }
        
        rendered = (
            "--- 核心任务锚点 (STRICT ADHERENCE REQUIRED) ---\n"
            f"{sections['input_task']}\n"
            "--------------------------------------------\n\n"
            f"## 当前进度 (todo.md)\n{sections['todo_slice']}\n\n"
            f"## 工作区最近动态 (Recent Changes)\n{sections['notes_summary']}\n\n"
            f"## 关键提醒\n{sections['sources_summary']}\n\n"
            f"## 最近工具观察\n{sections['observations_summary']}\n\n"
            "**行动准则**：\n"
            "1. 严禁重复阅读相同 URL。\n"
            "2. 每一条笔记必须包含 [原文引用] 和 [冲突与互补]。\n"
            "3. 任何实质进展必须立即更新 todo.md。"
        )
        
        token_count = self.estimate_tokens(rendered)
        
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
            block_char_counts={k: len(v) for k, v in sections.items()},
            token_count=token_count,
            trimmed_blocks=[],
        )

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
