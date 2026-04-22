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

    research_dir = tmp_path / "research"
    notes_dir = research_dir / "notes"
    evidence_dir = research_dir / "evidence"
    checkpoints_dir = research_dir / "checkpoints"
    notes_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    (research_dir / "todo.md").write_text(
        "# Demo TODO\n\n## 任务列表\n\n- [ ] in_progress: 校验 2024 数据口径差异\n- [ ] open: 补充官方来源\n",
        encoding="utf-8",
    )
    (research_dir / "source_index.md").write_text(
        "# Source Index\n\n- source_1 | official report | in_progress\n",
        encoding="utf-8",
    )
    (notes_dir / "note_1.md").write_text("# Note\n\n关键结论 A", encoding="utf-8")
    (evidence_dir / "evidence_1.md").write_text("# Evidence\n\nclaim: A", encoding="utf-8")
    (checkpoints_dir / "cp_1.md").write_text("# Checkpoint\n\n未解决项：口径统一", encoding="utf-8")

    manager = ContextManager(workspace_root=tmp_path)
    manager.record_tool_observation("web_search", '{"query":"A","results":[{"title":"t"}]}', is_error=False)
    payload = manager.build_context_payload(user_input="请继续研究")

    assert "当前阶段" in payload
    assert "in_progress: 校验 2024 数据口径差异" in payload
    assert "source_1" in payload
    assert "关键结论 A" in payload
    assert "未解决项" in payload
    assert "web_search" in payload


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
    assert "上下文包" in str(first_call[1]["content"])

    # second call still has compact messages and should not replay full raw tool payload history.
    assert len(second_call) <= 4
    assert second_call[0]["role"] == "system"
    assert second_call[1]["role"] == "user"

    events = [json.loads(line) for line in (logger.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    event_types = [event["event_type"] for event in events]
    assert "context_pack_built" in event_types

