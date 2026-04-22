from __future__ import annotations

import json

from deep_research_agent.agent import AgentConfig, ReActAgent
from deep_research_agent.logging import RunLogger
from deep_research_agent.models import AssistantResponse, ToolCall
from deep_research_agent.tools import ToolDefinition, ToolRegistry


class FakeModelBackend:
    def __init__(self, responses: list[AssistantResponse]) -> None:
        self._responses = responses
        self.calls: list[list[dict[str, object]]] = []

    def complete(self, messages: list[dict[str, object]], **_: object) -> AssistantResponse:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        return self._responses.pop(0)


def test_react_agent_runs_tool_then_returns_final(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    tool_calls: list[dict[str, object]] = []

    def echo_tool(arguments: dict[str, object]) -> dict[str, object]:
        tool_calls.append(arguments)
        return {"echo": arguments["text"]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_tool",
            description="Echo the provided text.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
            handler=echo_tool,
        )
    )

    backend = FakeModelBackend(
        [
            AssistantResponse(
                reasoning="Need to inspect the input with a tool.",
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="echo_tool",
                        arguments={"text": "hello"},
                    )
                ],
            ),
            AssistantResponse(
                reasoning="The tool returned the needed information.",
                content="final answer",
                tool_calls=[],
            ),
        ]
    )

    logger = RunLogger(base_dir=tmp_path / "logs")
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=registry,
        logger=logger,
        config=AgentConfig(max_turns=4),
    )

    result = agent.run(
        user_input="say hello",
        system_prompt="You are a careful research agent.",
    )

    assert result.final_answer == "final answer"
    assert result.turn_count == 2
    assert tool_calls == [{"text": "hello"}]

    events_path = logger.run_dir / "events.jsonl"
    assert events_path.exists()
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    event_types = [event["event_type"] for event in events]
    assert "model_request" in event_types
    assert "model_response" in event_types
    assert "tool_result" in event_types


def test_react_agent_stops_when_no_final_answer(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    backend = FakeModelBackend(
        [
            AssistantResponse(reasoning="Still thinking.", content=None, tool_calls=[]),
            AssistantResponse(reasoning="Still thinking.", content=None, tool_calls=[]),
        ]
    )

    logger = RunLogger(base_dir=tmp_path / "logs")
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=ToolRegistry(),
        logger=logger,
        config=AgentConfig(max_turns=2),
    )

    result = agent.run(
        user_input="stuck request",
        system_prompt="You are a careful research agent.",
    )

    assert result.stop_reason == "max_turns_exceeded"
    assert result.final_answer is None
