from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from deep_research_agent.models import AssistantResponse, ToolCall


class DashScopeOpenAIBackend:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ) -> None:
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not resolved_api_key:
            raise RuntimeError("OPENAI_API_KEY or DASHSCOPE_API_KEY is not set")

        self.model = model or os.getenv("AGENT_OS_MODEL") or "qwen-plus"
        self.client = OpenAI(api_key=resolved_api_key, base_url=base_url)

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
            "model": self.model,
            "messages": messages,
            "extra_body": {"enable_thinking": enable_thinking},
        }
        if tools:
            request_kwargs["tools"] = tools
            request_kwargs["parallel_tool_calls"] = parallel_tool_calls
            if tool_choice is not None:
                request_kwargs["tool_choice"] = tool_choice

        response = self.client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for item in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=item.id,
                        name=item.function.name,
                        arguments=_parse_tool_arguments(item.function.arguments),
                    )
                )

        reasoning = getattr(message, "reasoning_content", None)
        content = message.content if isinstance(message.content, str) else None
        return AssistantResponse(reasoning=reasoning, content=content, tool_calls=tool_calls)


def _parse_tool_arguments(raw_arguments: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments

    import json

    return json.loads(raw_arguments)
