from __future__ import annotations

import os
from typing import Any, Protocol

from openai import OpenAI
from deep_research_agent.models import AssistantResponse, ToolCall


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

    def complete_lite(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 2000,
    ) -> str:
        ...


class DashScopeOpenAIBackend:
    def __init__(self, model_name: str | None = None) -> None:
        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Neither DASHSCOPE_API_KEY nor OPENAI_API_KEY is set in environment.")
            
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.model_name = model_name or os.getenv("AGENT_OS_MODEL") or "qwen-plus"

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        enable_thinking: bool = True,
        parallel_tool_calls: bool = True,
    ) -> AssistantResponse:
        request_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        
        # Thinking logic
        if enable_thinking:
            request_kwargs["extra_body"] = {"enable_thinking": True}

        if tools:
            request_kwargs["tools"] = tools
            request_kwargs["tool_choice"] = tool_choice
            if not parallel_tool_calls:
                request_kwargs["parallel_tool_calls"] = False

        completion = self.client.chat.completions.create(**request_kwargs)
        choice = completion.choices[0]
        message = choice.message

        reasoning = getattr(message, "reasoning_content", None)
        content = message.content or ""
        tool_calls_raw = getattr(message, "tool_calls", None) or []
        import json
        tool_calls = []
        for tc in tool_calls_raw:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                )
            )

        return AssistantResponse(
            reasoning=reasoning,
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
            total_tokens=completion.usage.total_tokens,
        )

    def complete_lite(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 2000,
    ) -> str:
        """Lightweight completion for sub-agent tasks (distillation, OCR cleaning)."""
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
