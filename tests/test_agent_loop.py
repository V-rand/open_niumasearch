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
        self.kwargs_history: list[dict[str, object]] = []

    def complete(self, messages: list[dict[str, object]], **kwargs: object) -> AssistantResponse:
        self.calls.append(messages)
        self.kwargs_history.append(dict(kwargs))
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
    model_request_event = next(event for event in events if event["event_type"] == "model_request")
    assert model_request_event["payload"]["message_count"] > 0
    tool_result_event = next(event for event in events if event["event_type"] == "tool_result")
    assert tool_result_event["payload"]["tool_arguments"] == {"text": "hello"}


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


def test_react_agent_keeps_tool_choice_stable_across_turns(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_tool",
            description="Echo the provided text.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=lambda arguments: {"echo": arguments["text"]},
        )
    )
    backend = FakeModelBackend(
        [
            AssistantResponse(
                reasoning="Need tool first",
                content=None,
                tool_calls=[ToolCall(id="call_1", name="echo_tool", arguments={"text": "hello"})],
            ),
            AssistantResponse(reasoning="finalize", content="done", tool_calls=[]),
        ]
    )
    logger = RunLogger(base_dir=tmp_path / "logs")
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=registry,
        logger=logger,
        config=AgentConfig(max_turns=2, tool_choice="auto"),
    )

    result = agent.run(user_input="say hello", system_prompt="system")

    assert result.final_answer == "done"
    assert len(backend.kwargs_history) == 2
    assert backend.kwargs_history[0]["tool_choice"] == "auto"
    assert backend.kwargs_history[1]["tool_choice"] == "auto"


def test_messages_grow_naturally_without_truncation(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_tool",
            description="Echo.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=lambda arguments: {"echo": arguments["text"]},
        )
    )
    backend = FakeModelBackend(
        [
            AssistantResponse(
                reasoning="t1",
                content=None,
                tool_calls=[ToolCall(id="c1", name="echo_tool", arguments={"text": "a"})],
            ),
            AssistantResponse(
                reasoning="t2",
                content=None,
                tool_calls=[ToolCall(id="c2", name="echo_tool", arguments={"text": "b"})],
            ),
            AssistantResponse(
                reasoning="t3",
                content=None,
                tool_calls=[ToolCall(id="c3", name="echo_tool", arguments={"text": "c"})],
            ),
            AssistantResponse(reasoning="done", content="final", tool_calls=[]),
        ]
    )
    logger = RunLogger(base_dir=tmp_path / "logs")
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=registry,
        logger=logger,
        config=AgentConfig(max_turns=6),
    )

    result = agent.run(user_input="test", system_prompt="system")

    assert result.final_answer == "final"
    # All messages preserved: system + user + assistant + tool + user + assistant + tool + user + assistant + tool + user + assistant
    # = 1 + 1 + (1+1+1)*3 + 1 = 12
    assert len(backend.calls[-1]) == 12
