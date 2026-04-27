from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_SYSTEM_PROMPT = """你是一个谨慎的 research agent。

所有动作前先简短思考。
优先使用最直接、最少的工具完成当前问题。
工具结果不是最终答案，必须在观察后再决定下一步或给出 final answer。"""


def get_system_prompt(*, fallback: str = DEFAULT_SYSTEM_PROMPT) -> str:
    """Load system prompt from file or environment, with fallback."""
    prompt_file = os.getenv("AGENT_SYSTEM_PROMPT_FILE")
    if prompt_file:
        path = Path(prompt_file)
        if path.exists():
            return path.read_text(encoding="utf-8")

    default_path = Path("prompts/system.md")
    if default_path.exists():
        return default_path.read_text(encoding="utf-8")

    return fallback


def build_tool_catalog(tools: list[dict[str, Any]]) -> str:
    """Format OpenAI-style tool definitions into a compact Markdown catalog."""
    if not tools:
        return "（当前无可用工具）"

    lines: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name") or "unknown"
        description = function.get("description") or ""
        params = function.get("parameters", {})
        required = params.get("required", [])
        properties = params.get("properties", {})

        lines.append(f"- `{name}`: {description}")
        if properties:
            param_parts: list[str] = []
            for key, prop in properties.items():
                if not isinstance(prop, dict):
                    continue
                prop_type = prop.get("type", "any")
                marker = "*" if key in required else ""
                desc = prop.get("description", "")
                part = f"`{key}{marker}` ({prop_type})"
                if desc:
                    part += f" — {desc}"
                param_parts.append(part)
            if param_parts:
                lines.append("  - 参数: " + "; ".join(param_parts))

    return "\n".join(lines)


def compose_system_prompt(
    base_prompt: str,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Assemble the final system prompt, injecting tool catalog if placeholder exists."""
    tool_catalog = build_tool_catalog(tools or [])
    if "{tool_catalog}" in base_prompt:
        return base_prompt.replace("{tool_catalog}", tool_catalog)
    return base_prompt
