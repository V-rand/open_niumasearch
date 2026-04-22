from __future__ import annotations

import json
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
        self._walk_for_artifacts(
            value=payload,
            event_type=event_type,
            field_path="payload",
            artifacts=artifacts,
        )
        return artifacts

    def _walk_for_artifacts(
        self,
        value: Any,
        event_type: str,
        field_path: str,
        artifacts: list[dict[str, Any]],
    ) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self._walk_for_artifacts(
                    value=item,
                    event_type=event_type,
                    field_path=f"{field_path}.{key}",
                    artifacts=artifacts,
                )
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                self._walk_for_artifacts(
                    value=item,
                    event_type=event_type,
                    field_path=f"{field_path}[{index}]",
                    artifacts=artifacts,
                )
            return

        if isinstance(value, str) and len(value) > self.artifact_char_threshold:
            self._artifact_counter += 1
            artifact_name = f"artifacts/{self._artifact_counter:04d}_{event_type}.txt"
            self.write_text_artifact(artifact_name, value)
            artifacts.append(
                {
                    "field_path": field_path,
                    "artifact_path": artifact_name,
                    "char_count": len(value),
                }
            )

    # ------------------------------------------------------------------
    # Trace formatting — human-readable diary style
    # ------------------------------------------------------------------

    def _append_trace(self, event: dict[str, Any]) -> None:
        payload = event["payload"]
        turn_index = payload.get("turn_index") if isinstance(payload, dict) else None
        event_type = event["event_type"]

        lines: list[str] = []

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
            lines.append(f"\n## Turn {turn_index} — {summary}\n")

        if event_type == "model_request":
            # model_request is mostly redundant with model_response + tool_result;
            # skip it in trace to reduce noise, but keep in events.jsonl.
            pass
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

        if reasoning:
            lines.append(f"🤔 **Thinking**")
            lines.append(f"> {reasoning.strip().replace(chr(10), chr(10) + '> ')}\n")

        if content:
            lines.append(f"💬 **Output**")
            lines.append(f"{content.strip()}\n")

        if tool_calls:
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                name = self._tool_name_from_call(tc)
                function = tc.get("function")
                args = function.get("arguments") if isinstance(function, dict) else tc.get("arguments")
                args_str = self._inline_args(args)
                lines.append(f"🛠️ **Tool**: `{name}` — {args_str}\n")

        return lines

    def _trace_tool_result(self, payload: dict[str, Any]) -> list[str]:
        tool_name = payload.get("tool_name") or "unknown"
        is_error = bool(payload.get("is_error"))
        content = payload.get("content")
        metadata = payload.get("metadata")

        emoji = "❌" if is_error else "📄"
        status = "error" if is_error else "ok"

        lines = [f"{emoji} **Result** (`{tool_name}`, {status})"]

        # Compact content preview
        if content:
            preview = self._compact_preview(content, max_lines=8)
            lines.append(preview)

        # Compact metadata
        if metadata and metadata not in ({}, None):
            meta_preview = self._compact_preview(self._render_value(metadata), max_lines=3)
            lines.append(f"_metadata_: {meta_preview}")

        lines.append("")
        return lines

    def _trace_generic(self, event_type: str, payload: dict[str, Any]) -> list[str]:
        return [f"**{event_type}**", f"{self._compact_preview(self._render_value(payload), max_lines=5)}", ""]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inline_args(self, args: Any) -> str:
        """Render tool arguments as a compact inline string."""
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return args[:100]
        if isinstance(args, dict):
            parts: list[str] = []
            for k, v in args.items():
                if isinstance(v, str):
                    v_str = v if len(v) < 60 else v[:57] + "..."
                    parts.append(f'{k}="{v_str}"')
                else:
                    v_str = json.dumps(v, ensure_ascii=False)
                    if len(v_str) > 60:
                        v_str = v_str[:57] + "..."
                    parts.append(f"{k}={v_str}")
            return ", ".join(parts)
        return str(args)[:100]

    def _compact_preview(self, text: str, max_lines: int = 8) -> str:
        """Return full content in a code block; only truncate truly huge payloads."""
        if not text:
            return ""
        # Always show full text for thinking, output, and tool results.
        # Only truncate if it exceeds the artifact spillover threshold.
        if len(text) > self.artifact_char_threshold:
            lines = text.strip().splitlines()
            preview_lines = lines[:max_lines]
            preview = "\n".join(preview_lines)
            preview += f"\n... ({len(lines) - max_lines} more lines, {len(text)} chars total — see events.jsonl or artifacts for full text)"
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
