from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class AssistantResponse:
    reasoning: str | None
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class ToolExecutionResult:
    name: str
    content: str
    is_error: bool = False
    call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunResult:
    final_answer: str | None
    stop_reason: str
    turn_count: int
    run_dir: Path
