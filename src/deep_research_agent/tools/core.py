from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

class ModelBackend(Protocol):
    """Minimal protocol for tools to call LLM (e.g., for distillation)."""
    def complete_lite(self, messages: list[dict[str, Any]], max_tokens: int = 2000) -> str:
        ...

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

@dataclass
class ToolRegistry:
    _tools: dict[str, ToolDefinition] = field(default_factory=dict)

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]
