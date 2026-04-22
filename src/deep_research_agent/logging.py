from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any
from uuid import uuid4


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

    def _append_trace(self, event: dict[str, Any]) -> None:
        payload = event["payload"]
        turn_index = payload.get("turn_index") if isinstance(payload, dict) else None

        trace_lines: list[str] = []
        if isinstance(turn_index, int):
            if self._current_trace_turn != turn_index:
                self._current_trace_turn = turn_index
                trace_lines.extend([f"## Turn {turn_index}", ""])
        else:
            self._current_trace_turn = None
            if not self._trace_lifecycle_started:
                self._trace_lifecycle_started = True
                trace_lines.extend(["## Lifecycle", ""])

        trace_lines.extend(
            [
                f"### Event {self._event_counter}: {event['event_type']}",
                "",
            ]
        )
        trace_lines.extend(self._build_visual_sections(event["event_type"], payload))
        if event.get("artifacts"):
            trace_lines.extend(
                [
                    "",
                    "### Full Text Copies",
                ]
            )
            for item in event["artifacts"]:
                trace_lines.append(
                    f"- `{item['field_path']}` -> `{item['artifact_path']}` ({item['char_count']} chars)"
                )
        trace_lines.append("")
        trace_lines.append("")
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(trace_lines))

    def _build_visual_sections(self, event_type: str, payload: dict[str, Any]) -> list[str]:
        if not isinstance(payload, dict):
            return []

        sections: list[str] = []

        if event_type == "run_start":
            sections.extend(self._text_section("Input", payload.get("user_input")))
            sections.extend(self._compact_config_section(payload.get("config")))
            sections.extend(self._reference_section("System Prompt Path", payload.get("system_prompt_path")))
            sections.extend(self._path_list_section("Skill Paths", payload.get("skill_paths")))
            return sections

        if event_type == "run_stop":
            sections.extend(self._inline_value("Stop", payload.get("stop_reason")))
            if payload.get("turn_index") is not None:
                sections.append(f"- finished at turn: `{payload['turn_index']}`")
                sections.append("")
            return sections

        if event_type == "model_request":
            sections.extend(self._reference_section("System Prompt Path", payload.get("system_prompt_path")))
            sections.extend(self._path_list_section("Skill Paths", payload.get("skill_paths")))
            sections.extend(self._message_sections(payload.get("messages")))
            sections.extend(self._tool_catalog_sections(payload.get("tools")))
            return sections

        if event_type == "model_response":
            sections.extend(self._text_section("Thinking", payload.get("reasoning")))
            sections.extend(self._text_section("Output", payload.get("content")))
            sections.extend(self._tool_call_sections(payload.get("tool_calls")))
            return sections

        if event_type == "tool_result":
            sections.extend(
                self._compact_tool_result_section(
                    tool_name=payload.get("tool_name"),
                    is_error=bool(payload.get("is_error")),
                    content=payload.get("content"),
                    metadata=payload.get("metadata"),
                )
            )
            metadata = payload.get("metadata")
            if metadata not in ({}, None):
                sections.extend(self._text_section("Tool Metadata", self._render_value(metadata)))
            return sections

        sections.extend(self._text_section("Details", self._render_value(payload)))
        return sections

    def _text_section(self, title: str, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        return [
            f"**{title}**",
            "```text",
            self._render_value(value),
            "```",
            "",
        ]

    def _inline_value(self, title: str, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        return [f"**{title}**", f"- {self._render_inline(value)}", ""]

    def _reference_section(self, title: str, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        return [f"**{title}**", f"- `{value}`", ""]

    def _path_list_section(self, title: str, value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            return []
        lines = [f"**{title}**"]
        for item in value:
            lines.append(f"- `{item}`")
        lines.append("")
        return lines

    def _compact_config_section(self, value: Any) -> list[str]:
        if not isinstance(value, dict) or not value:
            return []
        lines = ["**Config**"]
        for key, item in value.items():
            lines.append(f"- {key}: `{item}`")
        lines.append("")
        return lines

    def _message_sections(self, messages: Any) -> list[str]:
        if not isinstance(messages, list):
            return []

        sections: list[str] = []
        role_groups: dict[str, list[Any]] = {
            "system": [],
            "user": [],
            "assistant": [],
            "tool": [],
        }
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role", "unknown")
            role_groups.setdefault(str(role), []).append(message)

        for role in ["user", "assistant", "tool"]:
            grouped = role_groups.get(role)
            if grouped:
                label = role.replace("_", " ").title()
                sections.extend(self._role_message_section(label, grouped))
        return sections

    def _tool_catalog_sections(self, tools: Any) -> list[str]:
        if not isinstance(tools, list):
            return []

        summarized_tools: list[str] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name") or "unknown_tool"
            description = function.get("description") or ""
            summarized_tools.append(f"- `{name}`: {description}".rstrip())

        if not summarized_tools:
            return []

        return ["**Available Tools**", *summarized_tools, ""]

    def _role_message_section(self, title: str, messages: list[Any]) -> list[str]:
        lines = [f"**{title} Messages**"]
        for index, message in enumerate(messages, start=1):
            if not isinstance(message, dict):
                continue
            lines.append(f"{index}.")
            content = message.get("content")
            if content not in (None, ""):
                lines.extend(["```text", self._render_value(content), "```"])
            tool_calls = message.get("tool_calls")
            if tool_calls:
                lines.append("Requested tool calls:")
                for tool_line in self._tool_call_lines(tool_calls):
                    lines.append(tool_line)
        lines.append("")
        return lines

    def _tool_call_sections(self, tool_calls: Any) -> list[str]:
        if not tool_calls:
            return []
        lines = ["**Requested Tools**"]
        lines.extend(self._tool_call_lines(tool_calls))
        lines.append("")
        return lines

    def _tool_call_lines(self, tool_calls: Any) -> list[str]:
        if not isinstance(tool_calls, list):
            return []
        lines: list[str] = []
        for index, tool_call in enumerate(tool_calls, start=1):
            if not isinstance(tool_call, dict):
                continue
            function_payload = tool_call.get("function")
            if isinstance(function_payload, dict):
                name = function_payload.get("name") or tool_call.get("name") or "unknown_tool"
                arguments = function_payload.get("arguments", tool_call.get("arguments"))
            else:
                name = tool_call.get("name") or "unknown_tool"
                arguments = tool_call.get("arguments")
            lines.append(f"{index}. `{name}`")
            if arguments not in (None, {}, []):
                rendered = self._render_arguments(arguments)
                for line in rendered:
                    lines.append(f"   {line}")
        return lines

    def _render_arguments(self, arguments: Any) -> list[str]:
        if isinstance(arguments, dict):
            lines: list[str] = []
            for key, value in arguments.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"- {key}:")
                    for nested in self._indent_block(self._render_value(value).splitlines()):
                        lines.append(nested)
                elif isinstance(value, str) and "\n" in value:
                    lines.append(f"- {key}:")
                    lines.append("  ```text")
                    for nested in value.splitlines():
                        lines.append(f"  {nested}")
                    lines.append("  ```")
                else:
                    lines.append(f"- {key}: {self._render_inline(value)}")
            return lines
        return [f"- arguments: {self._render_inline(arguments)}"]

    def _tool_result_section(self, content: Any) -> list[str]:
        if content is None or content == "":
            return []
        parsed = self._try_parse_json_string(content)
        rendered = self._render_value(parsed if parsed is not None else content)
        return ["**Tool Result**", "```text", rendered, "```", ""]

    def _compact_tool_result_section(
        self,
        *,
        tool_name: Any,
        is_error: bool,
        content: Any,
        metadata: Any,
    ) -> list[str]:
        lines = ["**Tool**"]
        if tool_name:
            lines.append(f"- used `{tool_name}`")
        lines.append(f"- status: `{'error' if is_error else 'ok'}`")
        lines.append("")
        lines.extend(self._tool_result_section(content))
        return lines

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
