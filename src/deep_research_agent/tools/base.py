from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from deep_research_agent.models import ToolExecutionResult

ToolHandler = Callable[[dict[str, Any]], ToolExecutionResult | str | dict[str, Any] | list[Any]]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def invoke(self, name: str, arguments: dict[str, Any], call_id: str | None = None) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=f"Unknown tool: {name}",
                is_error=True,
            )

        validation_error = self._validate(tool.parameters, arguments)
        if validation_error is not None:
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=validation_error,
                is_error=True,
            )

        try:
            result = tool.handler(arguments)
        except Exception as exc:
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )

        normalized = self._normalize_result(name=name, call_id=call_id, result=result)
        return normalized

    def _validate(self, schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            return f"Missing required arguments: {', '.join(missing)}"
        return None

    def _normalize_result(
        self,
        name: str,
        call_id: str | None,
        result: ToolExecutionResult | str | dict[str, Any] | list[Any],
    ) -> ToolExecutionResult:
        if isinstance(result, ToolExecutionResult):
            result.name = name
            result.call_id = call_id
            return result

        if isinstance(result, str):
            return ToolExecutionResult(name=name, call_id=call_id, content=result)

        return ToolExecutionResult(
            name=name,
            call_id=call_id,
            content=json.dumps(result, ensure_ascii=False, indent=2),
        )
