from __future__ import annotations

import json
from pathlib import Path

from deep_research_agent.agent import AgentConfig, ReActAgent
from deep_research_agent.context_manager import ContextManager
from deep_research_agent.logging import RunLogger
from deep_research_agent.models import AssistantResponse, ToolCall
from deep_research_agent.tools import ToolDefinition, ToolRegistry


class _FakeBackend:
    def __init__(self, responses: list[AssistantResponse]) -> None:
        self._responses = responses
        self.calls: list[list[dict[str, object]]] = []

    def complete(self, messages: list[dict[str, object]], **_: object) -> AssistantResponse:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("No fake responses left")
        return self._responses.pop(0)


def test_context_manager_builds_xml_context_pack(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    (tmp_path / "todo.md").write_text("- [ ] open: 建立初始任务列表\n", encoding="utf-8")

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_tool_observation("web_search", '{"query":"A","results":[{"title":"t"}]}', is_error=False)
    payload = manager.build_context_payload(user_input="请继续研究")

    assert "<context>" in payload
    assert "Task: 请继续研究" in payload
    assert "web_search: query=A" in payload


def test_context_manager_summarizes_long_observation_by_path_and_url(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_tool_observation(
        "pdf_read_url",
        '{"source_url":"https://example.com/demo.pdf","markdown_path":"documents/demo.md","markdown_preview":"'
        + ("x" * 1200)
        + '"}',
        is_error=False,
    )
    pack = manager.build_context_pack(user_input="请继续推进", turn_index=2)

    assert "documents/demo.md" in pack.rendered_prompt
    assert "https://example.com/demo.pdf" in pack.rendered_prompt
    assert "markdown_preview" not in pack.rendered_prompt
    assert "<context>" in pack.rendered_prompt


def test_context_manager_reminds_when_todo_is_not_updated(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_turn_progress(used_tools=True, updated_todo=False)

    pack = manager.build_context_pack(user_input="继续")

    # While it doesn't show in rendered_prompt anymore, the pack still contains the info
    assert "未更新 todo.md" in pack.sources_summary


def test_react_agent_uses_natural_message_history(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_tool",
            description="Echo text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=lambda arguments: {"echo": arguments["text"]},
        )
    )

    backend = _FakeBackend(
        [
            AssistantResponse(
                reasoning="need tool",
                content=None,
                tool_calls=[ToolCall(id="call_1", name="echo_tool", arguments={"text": "hello"})],
            ),
            AssistantResponse(reasoning="done", content="final", tool_calls=[]),
        ]
    )
    logger = RunLogger(base_dir=tmp_path / "logs")
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=registry,
        logger=logger,
        config=AgentConfig(max_turns=4),
    )

    result = agent.run(user_input="say hello", system_prompt="system")
    assert result.final_answer == "final"

    assert len(backend.calls) == 2
    first_call = backend.calls[0]
    second_call = backend.calls[1]

    assert first_call[0]["role"] == "system"
    assert first_call[1]["role"] == "user"
    assert "<task>" in str(first_call[1]["content"])
    assert "say hello" in str(first_call[1]["content"])

    # Second call: system + first_user + assistant(tool) + tool + user(Continue) + assistant(final)
    assert len(second_call) == 6
    assert second_call[0]["role"] == "system"
    assert second_call[1]["role"] == "user"
    assert second_call[2]["role"] == "assistant"
    assert second_call[3]["role"] == "tool"
    assert "<observation>" in str(second_call[3]["content"])
    assert second_call[4]["role"] == "user"
    assert second_call[4]["content"] == "Continue."
    assert second_call[5]["role"] == "assistant"


def test_context_manager_reports_token_count(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    (tmp_path / "todo.md").write_text("- [ ] open: 写测试\n", encoding="utf-8")
    manager = ContextManager(workspace_root=tmp_path)

    pack = manager.build_context_pack(user_input="请继续")

    assert pack.token_count > 0
    assert pack.block_char_counts["input_task"] == len("请继续")
