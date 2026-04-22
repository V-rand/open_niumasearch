from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from deep_research_agent.logging import RunLogger
from deep_research_agent.models import AgentRunResult, AssistantResponse, ToolCall, ToolExecutionResult
from deep_research_agent.tools import ToolRegistry


class ModelBackend(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        enable_thinking: bool = True,
        parallel_tool_calls: bool = True,
    ) -> AssistantResponse:
        ...


@dataclass(slots=True)
class AgentConfig:
    max_turns: int = 6
    enable_thinking: bool = True
    parallel_tool_calls: bool = True
    tool_choice: str | dict[str, Any] = "auto"
    max_parallel_tools: int = 4


class ReActAgent:
    def __init__(
        self,
        model_backend: ModelBackend,
        tool_registry: ToolRegistry,
        logger: RunLogger,
        config: AgentConfig | None = None,
    ) -> None:
        self.model_backend = model_backend
        self.tool_registry = tool_registry
        self.logger = logger
        self.config = config or AgentConfig()

    def run(
        self,
        user_input: str,
        system_prompt: str,
        *,
        skill_paths: list[str] | None = None,
    ) -> AgentRunResult:
        system_prompt_path = self.logger.write_text_artifact("system_prompt.txt", system_prompt)
        normalized_skill_paths = skill_paths or []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        self.logger.log_event(
            event_type="run_start",
            payload={
                "system_prompt_path": system_prompt_path,
                "skill_paths": normalized_skill_paths,
                "user_input": user_input,
                "config": {
                    "max_turns": self.config.max_turns,
                    "enable_thinking": self.config.enable_thinking,
                    "parallel_tool_calls": self.config.parallel_tool_calls,
                    "tool_choice": self.config.tool_choice,
                },
            },
        )

        for turn_index in range(1, self.config.max_turns + 1):
            self.logger.log_event(
                event_type="model_request",
                payload={
                    "turn_index": turn_index,
                    "system_prompt_path": system_prompt_path,
                    "skill_paths": normalized_skill_paths,
                    "messages": messages,
                    "tools": self.tool_registry.to_openai_tools(),
                },
            )
            response = self.model_backend.complete(
                messages,
                tools=self.tool_registry.to_openai_tools(),
                tool_choice=self.config.tool_choice,
                enable_thinking=self.config.enable_thinking,
                parallel_tool_calls=self.config.parallel_tool_calls,
            )
            self.logger.log_event(
                event_type="model_response",
                payload={
                    "turn_index": turn_index,
                    "reasoning": response.reasoning,
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                },
            )

            messages.append(_assistant_message_from_response(response))

            if response.tool_calls:
                tool_results = self._dispatch_tool_calls(response.tool_calls)
                for result in tool_results:
                    self.logger.log_event(
                        event_type="tool_result",
                        payload={
                            "turn_index": turn_index,
                            "tool_name": result.name,
                            "call_id": result.call_id,
                            "is_error": result.is_error,
                            "content": result.content,
                            "metadata": result.metadata,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": result.call_id,
                            "content": result.content,
                        }
                    )
                continue

            if response.content:
                self.logger.log_event(
                    event_type="run_stop",
                    payload={"turn_index": turn_index, "stop_reason": "final_answer"},
                )
                return AgentRunResult(
                    final_answer=response.content,
                    stop_reason="final_answer",
                    turn_count=turn_index,
                    run_dir=self.logger.run_dir,
                )

        self.logger.log_event(
            event_type="run_stop",
            payload={"turn_index": self.config.max_turns, "stop_reason": "max_turns_exceeded"},
        )
        return AgentRunResult(
            final_answer=None,
            stop_reason="max_turns_exceeded",
            turn_count=self.config.max_turns,
            run_dir=self.logger.run_dir,
        )

    def _dispatch_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolExecutionResult]:
        if len(tool_calls) == 1 or not self.config.parallel_tool_calls:
            return [self._run_single_tool_call(tool_calls[0])]

        max_workers = min(len(tool_calls), self.config.max_parallel_tools)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._run_single_tool_call, tool_call) for tool_call in tool_calls]
            return [future.result() for future in futures]

    def _run_single_tool_call(self, tool_call: ToolCall) -> ToolExecutionResult:
        return self.tool_registry.invoke(
            name=tool_call.name,
            arguments=tool_call.arguments,
            call_id=tool_call.id,
        )


def _assistant_message_from_response(response: AssistantResponse) -> dict[str, Any]:
    tool_calls = [
        {
            "id": item.id,
            "type": "function",
            "function": {
                "name": item.name,
                "arguments": _dump_json(item.arguments),
            },
        }
        for item in response.tool_calls
    ]
    message: dict[str, Any] = {
        "role": "assistant",
        "content": response.content or "",
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _dump_json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
