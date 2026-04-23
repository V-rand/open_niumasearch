from __future__ import annotations

import json

from deep_research_agent.agent import AgentConfig, ReActAgent
from deep_research_agent.agent import _compact_conversation_tail
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


def test_compact_conversation_tail_keeps_last_four_assistant_tool_rounds(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    messages: list[dict[str, object]] = []
    for index in range(1, 7):
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {"name": "echo_tool", "arguments": "{}"},
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"call_{index}",
                "content": f"tool result {index}",
            }
        )

    compact = _compact_conversation_tail(messages)

    assert len(compact) == 8
    assert compact[0]["role"] == "assistant"
    assert compact[0]["tool_calls"][0]["id"] == "call_3"
    assert compact[-1]["role"] == "tool"
    assert compact[-1]["tool_call_id"] == "call_6"
