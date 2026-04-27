from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from deep_research_agent.dashscope_backend import ModelBackend
from deep_research_agent.logging import RunLogger
from deep_research_agent.models import (
    AgentConfig,
    AgentRunResult,
    AssistantResponse,
    ToolCall,
    ToolExecutionResult,
)


class ReActAgent:
    def __init__(
        self,
        model_backend: ModelBackend,
        tool_registry: Any = None,
        logger: RunLogger | None = None,
        workspace_root: Path | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.model_backend = model_backend
        self.tool_registry = tool_registry
        self.logger = logger
        self.workspace_root = workspace_root
        self.config = config or AgentConfig()
        
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def run(
        self,
        user_input: str,
        system_prompt: str,
        skill_paths: list[str] | None = None,
    ) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        
        system_prompt_path = "dynamic"
        normalized_skill_paths = [str(p) for p in skill_paths] if skill_paths else []
        config_snapshot = {
            "max_turns": self.config.max_turns,
            "enable_thinking": self.config.enable_thinking,
            "parallel_tool_calls": self.config.parallel_tool_calls,
            "tool_choice": self.config.tool_choice,
        }

        if self.logger:
            self.logger.log_event(
                event_type="run_start",
                payload={
                    "system_prompt_path": system_prompt_path,
                    "skill_paths": normalized_skill_paths,
                    "user_input": user_input,
                    "config": config_snapshot,
                },
            )

        for turn_index in range(1, self.config.max_turns + 1):
            effective_tool_choice: str | dict[str, Any] = self.config.tool_choice

            print(f"\n--- [Turn {turn_index}/{self.config.max_turns}] Thinking... ---")

            # Tools for current turn
            openai_tools = None
            tool_names = []
            if self.tool_registry and hasattr(self.tool_registry, "to_openai_tools"):
                openai_tools = self.tool_registry.to_openai_tools()
                tool_names = [t.name for t in self.tool_registry._tools.values()]

            if self.logger:
                self.logger.log_event(
                    event_type="model_request",
                    payload={
                        "turn_index": turn_index,
                        "system_prompt_path": system_prompt_path,
                        "skill_paths": normalized_skill_paths,
                        "message_count": len(messages),
                        "messages": messages,
                        "tool_names": tool_names,
                        "effective_tool_choice": effective_tool_choice if openai_tools else None,
                    },
                )

            response = self.model_backend.complete(
                messages,
                tools=openai_tools,
                tool_choice=effective_tool_choice if openai_tools else None,
                enable_thinking=self.config.enable_thinking,
                parallel_tool_calls=self.config.parallel_tool_calls,
            )

            # Update Token Usage
            self.total_prompt_tokens += response.prompt_tokens or 0
            self.total_completion_tokens += response.completion_tokens or 0
            
            print(f"📊 [Tokens] Prompt: {response.prompt_tokens or 0} | Completion: {response.completion_tokens or 0} | Total: {self.total_prompt_tokens + self.total_completion_tokens}")

            if response.reasoning:
                print(f"🤔 [Thought]: {response.reasoning.strip()}")
            
            if response.content:
                preview = response.content.strip()
                if len(preview) > 300:
                    preview = preview[:300] + "..."
                print(f"💬 [Assistant]: {preview}")

            if self.logger:
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

            messages.append(_assistant_message_from_response(response))

            if response.tool_calls and self.tool_registry:
                for tc in response.tool_calls:
                    print(f"🛠️ [Action]: Calling `{tc.name}` with {json.dumps(tc.arguments, ensure_ascii=False)}")
                
                tool_results = self._dispatch_tool_calls(response.tool_calls)
                tool_arguments_by_id = {tool_call.id: tool_call.arguments for tool_call in response.tool_calls}
                for result in tool_results:
                    preview = result.content.strip()
                    if len(preview) > 200:
                        preview = preview[:200] + "..."
                    print(f"✅ [Observation]: {result.name} -> {preview}")
                    if self.logger:
                        self.logger.log_event(
                            event_type="tool_result",
                            payload={
                                "turn_index": turn_index,
                                "tool_name": result.name,
                                "call_id": result.call_id,
                                "is_error": result.is_error,
                                "tool_arguments": tool_arguments_by_id.get(result.call_id, {}),
                                "content": result.content,
                                "metadata": result.metadata,
                            },
                        )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": f"<observation>\n{result.content}\n</observation>",
                    })
                messages.append({"role": "user", "content": self.config.followup_user_message})
                continue

            if response.content:
                print(f"\n🏁 [Mission Completed] Reason: final_answer")
                if self.logger:
                    self.logger.log_event(
                        event_type="run_stop",
                        payload={
                            "stop_reason": "final_answer",
                            "turn_index": turn_index,
                        },
                    )
                return AgentRunResult(
                    final_answer=response.content,
                    stop_reason="final_answer",
                    turn_count=turn_index,
                    run_dir=self.logger.run_dir if self.logger else None,
                )

        print(f"\n🏁 [Mission Completed] Reason: max_turns_exceeded")
        if self.logger:
            self.logger.log_event(
                event_type="run_stop",
                payload={
                    "stop_reason": "max_turns_exceeded",
                    "turn_index": self.config.max_turns,
                },
            )
        return AgentRunResult(
            final_answer=None,
            stop_reason="max_turns_exceeded",
            turn_count=self.config.max_turns,
            run_dir=self.logger.run_dir if self.logger else None,
        )

    def _dispatch_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolExecutionResult]:
        if not self.tool_registry:
            return [ToolExecutionResult(name=tc.name, call_id=tc.id, content="No tool registry.", is_error=True) for tc in tool_calls]

        # 1. Prepare dedup and results placeholder
        results_map: dict[str, ToolExecutionResult] = {}
        dedup_urls: dict[str, str] = {} # url -> original_call_id
        calls_to_execute: list[ToolCall] = []

        for tc in tool_calls:
            url = str(tc.arguments.get("url") or "")
            if url and tc.name in ("jina_reader", "pdf_read_url", "ocr_parse"):
                if url in dedup_urls:
                    orig_id = dedup_urls[url]
                    # We will fill this result later once the original call finishes
                    results_map[tc.id] = None # Placeholder
                    continue
                else:
                    dedup_urls[url] = tc.id
            calls_to_execute.append(tc)

        # 2. Execute parallel calls
        if calls_to_execute:
            max_workers = min(len(calls_to_execute), self.config.max_parallel_tools)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._run_single_tool_call, tc): tc.id for tc in calls_to_execute}
                for future in futures:
                    res = future.result()
                    results_map[res.call_id] = res

        # 3. Fill in deduplicated results
        for tc in tool_calls:
            if tc.id in results_map and results_map[tc.id] is None:
                url = str(tc.arguments.get("url"))
                orig_id = dedup_urls[url]
                orig_res = results_map[orig_id]
                results_map[tc.id] = ToolExecutionResult(
                    name=tc.name,
                    call_id=tc.id,
                    content=f"(Deduplicated) {orig_res.content}",
                    is_error=orig_res.is_error,
                    metadata={"dedup_from": orig_id}
                )

        return [results_map[tc.id] for tc in tool_calls]

    def _run_single_tool_call(self, tool_call: ToolCall) -> ToolExecutionResult:
        if not self.tool_registry:
            return ToolExecutionResult(name=tool_call.name, call_id=tool_call.id, content="No tool registry.", is_error=True)
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
                "arguments": json.dumps(item.arguments, ensure_ascii=False),
            },
        }
        for item in response.tool_calls
    ]
    message: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message
