from __future__ import annotations

import json

from deep_research_agent.eval import run_eval_case
from deep_research_agent.models import AssistantResponse
from deep_research_agent.session import create_session


class _StaticBackend:
    def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        return AssistantResponse(
            reasoning="No tools needed.",
            content="benchmark final answer",
            tool_calls=[],
        )


def test_create_session_builds_isolated_directories(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    session = create_session(tmp_path / "sessions", user_input="task A")

    assert session.session_dir.exists()
    assert session.workspace_dir.exists()
    assert session.logs_dir.exists()
    metadata = json.loads(session.metadata_path.read_text(encoding="utf-8"))
    assert metadata["session_id"] == session.session_id
    assert metadata["user_input"] == "task A"


def test_run_eval_case_returns_stable_json_payload(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    payload = run_eval_case(
        user_input="answer directly",
        sessions_dir=tmp_path / "sessions",
        model_backend=_StaticBackend(),
        skill_names=["research-todo"],
    )

    assert payload["final_answer"] == "benchmark final answer"
    assert payload["stop_reason"] == "final_answer"
    assert payload["turn_count"] == 1
    assert payload["skills"] == ["research-todo"]
    assert payload["session_id"]
    assert (tmp_path / "sessions" / payload["session_id"] / "workspace").exists()
    assert (tmp_path / "sessions" / payload["session_id"] / "logs").exists()
    assert payload["documents_dir"].endswith("/workspace/documents")
