from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo


class RunLogger:
    def __init__(
        self,
        base_dir: Path,
        run_id: str | None = None,
        artifact_char_threshold: int = 4_000,
    ) -> None:
        self.base_dir = Path(base_dir)
        timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")
        self.run_id = run_id or f"{timestamp}_{uuid4().hex[:8]}"
        self.run_dir = self.base_dir / self.run_id
        self.artifacts_dir = self.run_dir / "artifacts"
        self.events_path = self.run_dir / "events.jsonl"
        self.trace_path = self.run_dir / "trace.md"
        self.artifact_char_threshold = artifact_char_threshold
        self._artifact_counter = 0
        self._event_counter = 0
        self._current_trace_turn: int | None = None
        self._trace_lifecycle_started = False

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path.write_text(
            f"# Run Trace\n\n- run_id: `{self.run_id}`\n\n",
            encoding="utf-8",
        )

    def write_text_artifact(self, name: str, content: str) -> str:
        path = self.run_dir / Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.run_dir))

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_counter += 1
        normalized_payload = self._normalize_payload(payload)
        artifacts = self._collect_artifact_copies(
            payload=normalized_payload,
            event_type=event_type,
        )
        event = {
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "event_type": event_type,
            "payload": normalized_payload,
        }
        if artifacts:
            event["artifacts"] = artifacts
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._append_trace(event=event)

    def _normalize_payload(self, payload: Any) -> Any:
        if is_dataclass(payload):
            payload = asdict(payload)

        if isinstance(payload, dict):
            return {key: self._normalize_payload(value) for key, value in payload.items()}

        if isinstance(payload, list):
            return [self._normalize_payload(value) for value in payload]

        return payload

    def _collect_artifact_copies(
        self,
        payload: Any,
        event_type: str,
    ) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        skipped_field_paths = self._collect_event_specific_artifacts(
            payload=payload,
            event_type=event_type,
            artifacts=artifacts,
        )
        self._walk_for_artifacts(
            value=payload,
            event_type=event_type,
            field_path="payload",
            artifacts=artifacts,
            skipped_field_paths=skipped_field_paths,
        )
        return artifacts

    def _walk_for_artifacts(
        self,
        value: Any,
        event_type: str,
        field_path: str,
        artifacts: list[dict[str, Any]],
        skipped_field_paths: set[str],
    ) -> None:
        if field_path in skipped_field_paths:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                self._walk_for_artifacts(
                    value=item,
                    event_type=event_type,
                    field_path=f"{field_path}.{key}",
                    artifacts=artifacts,
                    skipped_field_paths=skipped_field_paths,
                )
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                self._walk_for_artifacts(
                    value=item,
                    event_type=event_type,
                    field_path=f"{field_path}[{index}]",
                    artifacts=artifacts,
                    skipped_field_paths=skipped_field_paths,
                )
            return

        if isinstance(value, str) and len(value) > self.artifact_char_threshold:
            artifact_name = self._next_artifact_name(event_type=event_type, field_path=field_path)
            self.write_text_artifact(artifact_name, value)
            artifacts.append(
                {
                    "field_path": field_path,
                    "artifact_path": artifact_name,
                    "char_count": len(value),
                }
            )

    def _collect_event_specific_artifacts(
        self,
        payload: Any,
        event_type: str,
        artifacts: list[dict[str, Any]],
    ) -> set[str]:
        skipped_field_paths: set[str] = set()
        if event_type != "model_request" or not isinstance(payload, dict):
            return skipped_field_paths

        context_prompt = payload.get("context_prompt")
        if not isinstance(context_prompt, str) or not context_prompt:
            return skipped_field_paths

        skipped_field_paths.add("payload.context_prompt")
        artifact_name = self._next_artifact_name(
            event_type=event_type,
            field_path="payload.context_prompt",
        )
        self.write_text_artifact(artifact_name, context_prompt)
        artifacts.append(
            {
                "field_path": "payload.context_prompt",
                "artifact_path": artifact_name,
                "char_count": len(context_prompt),
            }
        )
        return skipped_field_paths

    # ------------------------------------------------------------------
    # Trace formatting — human-readable diary style
    # ------------------------------------------------------------------

    def _append_trace(self, event: dict[str, Any]) -> None:
        payload = event["payload"]
        turn_index = payload.get("turn_index") if isinstance(payload, dict) else None
        event_type = event["event_type"]

        lines: list[str] = []

        if event_type in {"context_pack_built", "context_trim_applied"}:
            return

        # Lifecycle events (run_start, run_stop, or tool_result without turn)
        if turn_index is None:
            if event_type == "run_start":
                lines.extend(self._trace_run_start(payload))
            elif event_type == "run_stop":
                lines.extend(self._trace_run_stop(payload))
            elif event_type == "tool_result":
                lines.extend(self._trace_tool_result(payload))
            else:
                lines.extend(self._trace_generic(event_type, payload))
            self._write_lines(lines)
            return

        # Turn-level events
        if self._current_trace_turn != turn_index:
            self._current_trace_turn = turn_index
            summary = self._turn_summary_from_payload(payload, event_type)
            lines.append(f"\n## Turn {turn_index}\n")
            if summary:
                lines.append(f"_概览_: {summary}\n")

        if event_type == "model_request":
            lines.extend(self._trace_model_request(payload))
        elif event_type == "model_response":
            lines.extend(self._trace_model_response(payload))
        elif event_type == "tool_result":
            lines.extend(self._trace_tool_result(payload))
        elif event_type == "run_stop":
            # run_stop is already rendered at the end of the trace; skip here.
            pass
        else:
            lines.extend(self._trace_generic(event_type, payload))

        self._write_lines(lines)

    def _write_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    # ------------------------------------------------------------------
    # Turn summary extraction
    # ------------------------------------------------------------------

    def _turn_summary_from_payload(self, payload: dict[str, Any], event_type: str) -> str:
        """Generate a one-line summary for a turn heading."""
        if event_type == "model_response":
            tool_calls = payload.get("tool_calls")
            content = payload.get("content") or ""
            reasoning = payload.get("reasoning") or ""
            if tool_calls:
                names = [self._tool_name_from_call(tc) for tc in tool_calls if isinstance(tc, dict)]
                return f"调用工具: {', '.join(names)}"
            if content:
                # Take first ~30 chars of content as hint
                hint = content.strip().replace("\n", " ")[:40]
                return f"输出回复: {hint}..." if len(content) > 40 else f"输出回复: {hint}"
            if reasoning:
                hint = reasoning.strip().replace("\n", " ")[:40]
                return f"思考中: {hint}..."
            return "模型响应"
        if event_type == "tool_result":
            name = payload.get("tool_name") or "unknown"
            return f"工具结果: {name}"
        return event_type.replace("_", " ")

    def _tool_name_from_call(self, tool_call: dict[str, Any]) -> str:
        function = tool_call.get("function")
        if isinstance(function, dict):
            return function.get("name") or "unknown"
        return tool_call.get("name") or "unknown"

    # ------------------------------------------------------------------
    # Section formatters
    # ------------------------------------------------------------------

    def _trace_run_start(self, payload: dict[str, Any]) -> list[str]:
        lines = ["## 启动\n"]
        user_input = payload.get("user_input")
        if user_input:
            lines.append(f"**输入**: {user_input}\n")
        config = payload.get("config")
        if isinstance(config, dict):
            parts = [f"{k}={v}" for k, v in config.items()]
            lines.append(f"**配置**: {', '.join(parts)}\n")
        skills = payload.get("skill_paths")
        if skills:
            lines.append(f"**Skills**: {', '.join(str(s) for s in skills)}\n")
        return lines

    def _trace_run_stop(self, payload: dict[str, Any]) -> list[str]:
        lines = ["\n## 结束\n"]
        stop_reason = payload.get("stop_reason")
        turn_index = payload.get("turn_index")
        if stop_reason:
            lines.append(f"**停止原因**: {stop_reason}")
        if turn_index is not None:
            lines.append(f"**总轮数**: {turn_index}")
        lines.append("")
        return lines

    def _trace_model_response(self, payload: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        reasoning = payload.get("reasoning")
        content = payload.get("content")
        tool_calls = payload.get("tool_calls")
        prompt_tokens_api = payload.get("prompt_tokens_api")
        output_tokens = payload.get("output_tokens")
        total_tokens_api = payload.get("total_tokens_api")

        if any(value is not None for value in (prompt_tokens_api, output_tokens, total_tokens_api)):
            lines.append("**Token 统计**")
            if prompt_tokens_api is not None:
                lines.append(f"- 输入 Token(API): `{prompt_tokens_api}`")
            if output_tokens is not None:
                lines.append(f"- 输出 Token(API): `{output_tokens}`")
            if total_tokens_api is not None:
                lines.append(f"- 总 Token(API): `{total_tokens_api}`")
            lines.append("")

        if reasoning:
            lines.append("**思考**")
            lines.append(self._compact_preview(str(reasoning), max_lines=12))
            lines.append("")

        if tool_calls:
            lines.append("**行动**")
            for index, tc in enumerate(tool_calls, start=1):
                if not isinstance(tc, dict):
                    continue
                name = self._tool_name_from_call(tc)
                function = tc.get("function")
                args = function.get("arguments") if isinstance(function, dict) else tc.get("arguments")
                lines.append(f"{index}. `{name}`")
                lines.append("   指令:")
                lines.append(self._compact_preview(self._render_arguments_block(args), max_lines=12))
            lines.append("")

        if content:
            lines.append("**输出**")
            lines.append(self._compact_preview(str(content), max_lines=16))
            lines.append("")

        return lines

    def _trace_model_request(self, payload: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        context_prompt = payload.get("context_prompt")
        input_tokens_estimated = payload.get("input_tokens_estimated")
        tool_names = payload.get("tool_names")
        effective_tool_choice = payload.get("effective_tool_choice")

        if context_prompt:
            lines.append("**思考输入**")
            if input_tokens_estimated is not None:
                lines.append(f"- 估算输入 Token: `{input_tokens_estimated}`")
            if isinstance(tool_names, list) and tool_names:
                tools_text = ", ".join(f"`{name}`" for name in tool_names)
                lines.append(f"- 可用工具: {tools_text}")
            if effective_tool_choice is not None:
                lines.append(f"- 工具策略: `{effective_tool_choice}`")
            lines.append(self._compact_preview(str(context_prompt), max_lines=18))
            lines.append("")

        conversation_tail = payload.get("conversation_tail")
        if isinstance(conversation_tail, list) and conversation_tail:
            lines.append("**最近对话尾部**")
            lines.append(self._compact_preview(self._render_value(conversation_tail), max_lines=8))
            lines.append("")

        return lines

    def _trace_tool_result(self, payload: dict[str, Any]) -> list[str]:
        tool_name = payload.get("tool_name") or "unknown"
        is_error = bool(payload.get("is_error"))
        content = payload.get("content")
        metadata = payload.get("metadata")
        tool_arguments = payload.get("tool_arguments")
        status = "error" if is_error else "ok"
        lines = ["**观察**", f"- `{tool_name}` | `{status}`"]

        if tool_arguments not in (None, {}, []):
            lines.append("  指令:")
            lines.append(self._compact_preview(self._render_arguments_block(tool_arguments), max_lines=12))

        if content:
            lines.append("  结果:")
            lines.append(self._compact_preview(self._extract_tool_result_preview(str(content)), max_lines=8))

        if metadata and metadata not in ({}, None):
            lines.append("  元数据:")
            lines.append(self._compact_preview(self._render_value(metadata), max_lines=4, aggressive=True))

        lines.append("")
        return lines

    def _trace_generic(self, event_type: str, payload: dict[str, Any]) -> list[str]:
        return [f"**{event_type}**", self._compact_preview(self._render_value(payload), max_lines=5), ""]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_arguments_block(self, args: Any) -> str:
        if isinstance(args, str):
            parsed = self._try_parse_json_string(args)
            if parsed is not None:
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            return args
        if isinstance(args, (dict, list)):
            return json.dumps(args, ensure_ascii=False, indent=2)
        return str(args)

    def _extract_tool_result_preview(self, content: str) -> str:
        parsed = self._try_parse_json_string(content)
        if not isinstance(parsed, dict):
            return content

        focus: dict[str, Any] = {}
        for key in (
            "title",
            "url",
            "path",
            "raw_path",
            "paper_id",
            "query",
            "summary",
            "preview",
            "message",
            "error",
        ):
            if key in parsed and parsed[key] not in (None, "", [], {}):
                focus[key] = parsed[key]
        if "results" in parsed and parsed["results"]:
            focus["results"] = parsed["results"]
        if "content" in parsed and parsed["content"]:
            focus["content_preview"] = str(parsed["content"])[:800]
        if "markdown" in parsed and parsed["markdown"]:
            focus["markdown_preview"] = str(parsed["markdown"])[:800]
        if not focus:
            focus = parsed
        return json.dumps(focus, ensure_ascii=False, indent=2)

    def _compact_preview(self, text: str, max_lines: int = 8, aggressive: bool = False) -> str:
        """Return full content in a code block; only truncate truly huge payloads."""
        if not text:
            return ""
        
        threshold = 500 if aggressive else self.artifact_char_threshold
        
        if len(text) > threshold:
            lines = text.strip().splitlines()
            display_lines = min(len(lines), max_lines)
            preview = "\n".join(lines[:display_lines])
            preview += f"\n... (截断显示，全文共 {len(text)} 字符，请查阅对应 Artifacts)"
            return "```text\n" + preview + "\n```"
        
        return "```text\n" + text.strip() + "\n```"

    def _render_value(self, value: Any) -> str:
        if isinstance(value, str):
            parsed = self._try_parse_json_string(value)
            if parsed is not None:
                return self._render_value(parsed)
            return value
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.append(f"{key}:")
                    lines.extend(self._indent_block(self._render_value(item).splitlines()))
                else:
                    lines.append(f"{key}: {self._render_inline(item)}")
            return "\n".join(lines)
        if isinstance(value, list):
            lines: list[str] = []
            for index, item in enumerate(value, start=1):
                if isinstance(item, (dict, list)):
                    lines.append(f"{index}.")
                    lines.extend(self._indent_block(self._render_value(item).splitlines()))
                else:
                    lines.append(f"{index}. {self._render_inline(item)}")
            return "\n".join(lines)
        return str(value)

    def _render_inline(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        return f"`{value}`" if isinstance(value, (int, float, str)) else str(value)

    def _try_parse_json_string(self, value: Any) -> Any | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    def _indent_block(self, lines: list[str]) -> list[str]:
        return [f"  {line}" if line else "" for line in lines]

    def _slugify_field_path(self, field_path: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", field_path).strip("_").lower()
        return slug or "payload"

    def _next_artifact_name(self, *, event_type: str, field_path: str) -> str:
        self._artifact_counter += 1
        return f"artifacts/{self._artifact_counter:04d}_{event_type}_{self._slugify_field_path(field_path)}.txt"
