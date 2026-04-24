from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from deep_research_agent.models import AssistantResponse
from deep_research_agent.multi_agent import MultiAgentConfig, run_multi_agent_case
from deep_research_agent.tools import build_readonly_tools


class ScriptedBackend:
    def __init__(self, response: AssistantResponse, calls: list[list[dict[str, Any]]]) -> None:
        self._response = response
        self._calls = calls

    def complete(self, messages: list[dict[str, Any]], **kwargs: object) -> AssistantResponse:
        self._calls.append([dict(message) for message in messages])
        return self._response


class BackendFactory:
    def __init__(
        self,
        *,
        generator_responses: list[AssistantResponse],
        evaluator_responses: list[AssistantResponse],
    ) -> None:
        self.generator_responses = generator_responses
        self.evaluator_responses = evaluator_responses
        self.generator_calls: list[list[dict[str, Any]]] = []
        self.evaluator_calls: list[list[dict[str, Any]]] = []
        self.requested_models: list[str | None] = []
        self._lock = threading.Lock()

    def __call__(self, model: str | None = None) -> ScriptedBackend:
        with self._lock:
            self.requested_models.append(model)
            if model is None:
                response = self.generator_responses.pop(0)
                calls = self.generator_calls
            else:
                response = self.evaluator_responses.pop(0)
                calls = self.evaluator_calls
        return ScriptedBackend(response=response, calls=calls)


def _response(content: str) -> AssistantResponse:
    return AssistantResponse(reasoning=None, content=content, tool_calls=[])


def test_research_certification_starts_fresh_writer_then_writer_certification(
    tmp_path, is_fast_mode: bool
) -> None:
    if is_fast_mode:
        pass

    factory = BackendFactory(
        generator_responses=[
            _response("Researcher cycle complete."),
            _response("Writer final answer."),
        ],
        evaluator_responses=[
            _response("# Rubric\n\nEvidence must be quoted.\nDecision: CONTINUE"),
            _response("Research evidence ok.\nDecision: STOP"),
            _response("Research strategy ok.\nDecision: STOP"),
            _response("Research handoff ok.\nDecision: STOP"),
            _response("Citations ok.\nDecision: STOP"),
            _response("Writing ok.\nDecision: STOP"),
            _response("No gaps.\nDecision: STOP"),
        ],
    )

    result = run_multi_agent_case(
        user_input="research task",
        sessions_dir=tmp_path / "sessions",
        system_prompt="system {tool_catalog}",
        config=MultiAgentConfig(
            max_research_cycles=3,
            max_writing_cycles=2,
            evaluator_model="eval-model",
        ),
        backend_factory=factory,
    )

    assert result.stop_reason == "writer_certified"
    assert result.research_cycle_count == 1
    assert result.writing_cycle_count == 1
    assert result.final_answer == "Writer final answer."
    assert len(result.writer_run_dirs) == 1
    assert (result.workspace_dir / "research" / "evaluation_rubric.md").exists()
    assert (result.workspace_dir / "research" / "writer_packet.md").exists()
    assert (result.workspace_dir / "research" / "evaluations" / "research_cycle_001_decision.md").exists()
    assert (result.workspace_dir / "research" / "evaluations" / "writing_cycle_001_decision.md").exists()

    writer_messages = factory.generator_calls[1]
    assert writer_messages[0]["role"] == "system"
    writer_user_message = next(message for message in writer_messages if message["role"] == "user")
    assert "当前显式阶段：WRITING" in str(writer_user_message["content"])
    assert "research/writer_packet.md" in str(writer_user_message["content"])


def test_research_revise_feedback_reaches_next_researcher_cycle(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    factory = BackendFactory(
        generator_responses=[
            _response("research cycle one"),
            _response("research cycle two"),
            _response("writer done"),
        ],
        evaluator_responses=[
            _response("# Rubric\nDecision: CONTINUE"),
            _response("Need quotes.\nDecision: REVISE"),
            _response("Need lead status.\nDecision: CONTINUE"),
            _response("Need references.\nDecision: CONTINUE"),
            _response("Research ok.\nDecision: STOP"),
            _response("Research ok.\nDecision: STOP"),
            _response("Research ok.\nDecision: STOP"),
            _response("Writing ok.\nDecision: STOP"),
            _response("Writing ok.\nDecision: STOP"),
            _response("Writing ok.\nDecision: STOP"),
        ],
    )

    result = run_multi_agent_case(
        user_input="research task",
        sessions_dir=tmp_path / "sessions",
        system_prompt="system {tool_catalog}",
        config=MultiAgentConfig(max_research_cycles=2, evaluator_model="eval-model"),
        backend_factory=factory,
    )

    assert result.stop_reason == "writer_certified"
    assert result.research_cycle_count == 2
    second_researcher_messages = factory.generator_calls[1]
    second_user_message = next(message for message in second_researcher_messages if message["role"] == "user")
    assert "Decision: REVISE" in str(second_user_message["content"])
    assert "Need quotes" in str(second_user_message["content"])


def test_writing_revise_starts_another_fresh_writer_cycle(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    factory = BackendFactory(
        generator_responses=[
            _response("research done"),
            _response("draft one"),
            _response("draft two"),
        ],
        evaluator_responses=[
            _response("# Rubric\nDecision: CONTINUE"),
            _response("Research ok.\nDecision: STOP"),
            _response("Research ok.\nDecision: STOP"),
            _response("Research ok.\nDecision: STOP"),
            _response("Missing citation.\nDecision: REVISE"),
            _response("Too long for short answer.\nDecision: CONTINUE"),
            _response("Gap.\nDecision: CONTINUE"),
            _response("Ok.\nDecision: STOP"),
            _response("Ok.\nDecision: STOP"),
            _response("Ok.\nDecision: STOP"),
        ],
    )

    result = run_multi_agent_case(
        user_input="short answer benchmark task",
        sessions_dir=tmp_path / "sessions",
        system_prompt="system {tool_catalog}",
        config=MultiAgentConfig(max_writing_cycles=2, evaluator_model="eval-model"),
        backend_factory=factory,
    )

    assert result.stop_reason == "writer_certified"
    assert result.writing_cycle_count == 2
    second_writer_messages = factory.generator_calls[2]
    second_writer_user = next(message for message in second_writer_messages if message["role"] == "user")
    assert "Missing citation" in str(second_writer_user["content"])
    assert "Too long for short answer" in str(second_writer_user["content"])


def test_evaluator_model_precedence_uses_cli_config_then_env(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("AGENT_OS_EVALUATOR_MODEL", "env-evaluator")
    factory = BackendFactory(
        generator_responses=[_response("research done"), _response("writer done")],
        evaluator_responses=[
            _response("rubric\nDecision: CONTINUE"),
            _response("Decision: STOP"),
            _response("Decision: STOP"),
            _response("Decision: STOP"),
            _response("Decision: STOP"),
            _response("Decision: STOP"),
            _response("Decision: STOP"),
        ],
    )

    run_multi_agent_case(
        user_input="task",
        sessions_dir=tmp_path / "sessions",
        system_prompt="system {tool_catalog}",
        config=MultiAgentConfig(max_research_cycles=1, evaluator_model="cli-evaluator"),
        backend_factory=factory,
    )

    assert "cli-evaluator" in factory.requested_models
    assert "env-evaluator" not in factory.requested_models


def test_readonly_tools_expose_only_list_and_read(tmp_path: Path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    tools = build_readonly_tools(tmp_path)

    assert tools.tool_names() == ["fs_list", "fs_read"]
