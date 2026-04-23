from __future__ import annotations

import json

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


def test_context_manager_builds_markdown_context_pack(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    (tmp_path / "todo.md").write_text("- [ ] open: 建立初始任务列表\n", encoding="utf-8")

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_tool_observation("web_search", '{"query":"A","results":[{"title":"t"}]}', is_error=False)
    payload = manager.build_context_payload(user_input="请继续研究")

    assert "启动工作" in payload
    assert "`task.md`" in payload
    assert "## 当前进度 (todo.md)" in payload
    assert "建立初始任务列表" in payload
    assert (tmp_path / "task.md").exists()


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
    assert "增量工作提示" in pack.rendered_prompt


def test_context_manager_reminds_when_todo_is_not_updated(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_turn_progress(used_tools=True, updated_todo=False)

    pack = manager.build_context_pack(user_input="继续")

    assert "未更新 todo.md" in pack.rendered_prompt


def test_react_agent_uses_context_manager_instead_of_full_history(tmp_path, is_fast_mode: bool) -> None:
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
    manager = ContextManager(workspace_root=tmp_path, logger=logger)
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=registry,
        logger=logger,
        config=AgentConfig(max_turns=4),
        context_manager=manager,
    )

    result = agent.run(user_input="say hello", system_prompt="system")
    assert result.final_answer == "final"

    assert len(backend.calls) == 2
    first_call = backend.calls[0]
    second_call = backend.calls[1]
    assert len(first_call) == 2
    assert first_call[0]["role"] == "system"
    assert first_call[1]["role"] == "user"
    assert "启动工作" in str(first_call[1]["content"])
    assert "task.md" in str(first_call[1]["content"])

    # second call still has compact messages and should not replay full raw tool payload history.
    assert len(second_call) <= 4
    assert second_call[0]["role"] == "system"
    assert second_call[1]["role"] == "user"
    assert "增量工作提示" in str(second_call[1]["content"])
    assert "say hello" not in str(second_call[1]["content"])

    events = [json.loads(line) for line in (logger.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    event_types = [event["event_type"] for event in events]
    assert "context_pack_built" in event_types


def test_context_manager_reports_token_count(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    (tmp_path / "todo.md").write_text("- [ ] open: 写测试\n", encoding="utf-8")
    manager = ContextManager(workspace_root=tmp_path)

    pack = manager.build_context_pack(user_input="请继续")

    assert pack.token_count > 0
    assert pack.block_char_counts["input_task"] == len("请继续")
