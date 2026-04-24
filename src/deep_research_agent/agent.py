from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from deep_research_agent.context_manager import ContextManager
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
    max_turns: int = 12
    enable_thinking: bool = True
    parallel_tool_calls: bool = True
    tool_choice: str | dict[str, Any] = "auto"
    max_parallel_tools: int = 4
    followup_user_message: str = "Continue."


class ReActAgent:
    def __init__(
        self,
        model_backend: ModelBackend,
        tool_registry: ToolRegistry,
        logger: RunLogger,
        config: AgentConfig | None = None,
        context_manager: ContextManager | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.model_backend = model_backend
        self.tool_registry = tool_registry
        self.logger = logger
        self.config = config or AgentConfig()
        resolved_workspace = (workspace_root or Path(".")).resolve()
        self.context_manager = context_manager or ContextManager(
            workspace_root=resolved_workspace,
            logger=logger,
        )

    def run(
        self,
        user_input: str,
        system_prompt: str,
        *,
        skill_paths: list[str] | None = None,
    ) -> AgentRunResult:
        system_prompt_path = self.logger.write_text_artifact("system_prompt.txt", system_prompt)
        normalized_skill_paths = skill_paths or []

        # Natural message history: system + user + assistant + tool + ...
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # First user message: task wrapped in XML
        first_user_content = self._build_first_user_message(user_input)
        messages.append({"role": "user", "content": first_user_content})

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
            effective_tool_choice: str | dict[str, Any] = self.config.tool_choice

            # Log the messages being sent (summarized)
            self.logger.log_event(
                event_type="model_request",
                payload={
                    "turn_index": turn_index,
                    "system_prompt_path": system_prompt_path,
                    "skill_paths": normalized_skill_paths,
                    "message_count": len(messages),
                    "conversation_summary": _summarize_messages_for_log(messages),
                    "messages": messages,
                    "tool_names": self.tool_registry.tool_names(),
                    "effective_tool_choice": effective_tool_choice,
                },
            )

            response = self.model_backend.complete(
                messages,
                tools=self.tool_registry.to_openai_tools(),
                tool_choice=effective_tool_choice,
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
                    "prompt_tokens_api": response.prompt_tokens,
                    "output_tokens": response.completion_tokens,
                    "total_tokens_api": response.total_tokens,
                },
            )

            assistant_message = _assistant_message_from_response(response)
            messages.append(assistant_message)

            if response.tool_calls:
                tool_results = self._dispatch_tool_calls(response.tool_calls)
                tool_arguments_by_call_id = {
                    tool_call.id: tool_call.arguments for tool_call in response.tool_calls
                }
                for result in tool_results:
                    self.logger.log_event(
                        event_type="tool_result",
                        payload={
                            "turn_index": turn_index,
                            "tool_name": result.name,
                            "call_id": result.call_id,
                            "is_error": result.is_error,
                            "tool_arguments": tool_arguments_by_call_id.get(result.call_id),
                            "content": result.content,
                            "metadata": result.metadata,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": result.call_id,
                            "content": f"<observation>\n{result.content}\n</observation>",
                        }
                    )
                # After tool results, add a light user message to prompt next thinking
                messages.append({"role": "user", "content": self.config.followup_user_message})
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

    def _build_first_user_message(self, user_input: str) -> str:
        """Build the first user message with task wrapped in XML."""
        return f"<task>\n{user_input.strip()}\n</task>"

    def _dispatch_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolExecutionResult]:
        if not self.config.parallel_tool_calls:
            return [self._run_single_tool_call(tool_calls[0])]

        # Deduplicate URLs in parallel calls to prevent redundant downloads/reads
        seen_urls: set[str] = set()
        deduplicated_calls: list[ToolCall] = []
        results: list[ToolExecutionResult] = []
        
        # Mapping to keep track of which call IDs get which results
        call_id_to_result: dict[str, ToolExecutionResult] = {}

        for tc in tool_calls:
            url = str(tc.arguments.get("url") or tc.arguments.get("paper_ref") or "")
            if url and tc.name in ("jina_reader", "pdf_read_url", "arxiv_read_paper", "mineru_parse_url"):
                if url in seen_urls:
                    # Mark as redundant
                    call_id_to_result[tc.id] = ToolExecutionResult(
                        name=tc.name,
                        call_id=tc.id,
                        content=f"Skipped redundant call to {url}. This URL is already being processed in this turn.",
                        is_error=False,
                        metadata={"status": "deduplicated"}
                    )
                    continue
                seen_urls.add(url)
            deduplicated_calls.append(tc)

        if not deduplicated_calls:
            return list(call_id_to_result.values())

        max_workers = min(len(deduplicated_calls), self.config.max_parallel_tools)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._run_single_tool_call, tc) for tc in deduplicated_calls]
            executed_results = [future.result() for future in futures]
            
        # Re-assemble the full list of results in original order if possible, 
        # or just combine them.
        final_results = executed_results + list(call_id_to_result.values())
        return final_results

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


def _summarize_messages_for_log(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize the messages array for logging (not sent to model)."""
    summary: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "unknown"))
        item: dict[str, Any] = {"role": role}
        if role == "assistant":
            content = str(message.get("content") or "")
            if content:
                item["content_preview"] = _truncate_text(content, 120)
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list):
                item["tool_calls"] = [
                    _tool_name_from_openai_message_call(tc)
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ]
        elif role == "tool":
            item["tool_call_id"] = message.get("tool_call_id")
            content = str(message.get("content") or "")
            if content:
                item["content_preview"] = _truncate_text(content, 120)
        else:
            content = str(message.get("content") or "")
            if content:
                item["content_preview"] = _truncate_text(content, 120)
        summary.append(item)
    return summary


def _tool_name_from_openai_message_call(tool_call: dict[str, Any]) -> str:
    function = tool_call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "unknown")
    return str(tool_call.get("name") or "unknown")


def _truncate_text(text: str, limit: int) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
