from __future__ import annotations

import json

from deep_research_agent.logging import RunLogger


def test_logger_spills_large_payload_to_artifact(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs", artifact_char_threshold=20)
    logger.log_event(
        event_type="tool_result",
        payload={"content": "x" * 50, "tool_name": "sample_tool"},
    )

    events_path = logger.run_dir / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    payload = events[0]["payload"]
    artifacts = events[0]["artifacts"]

    assert payload["content"] == "x" * 50
    assert artifacts[0]["artifact_path"].endswith(".txt")
    artifact_path = logger.run_dir / artifacts[0]["artifact_path"]
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "x" * 50

    trace_path = logger.run_dir / "trace.md"
    trace_content = trace_path.read_text(encoding="utf-8")
    assert "**观察**" in trace_content
    assert "`sample_tool` | `ok`" in trace_content
    assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" in trace_content
    assert "timestamp:" not in trace_content


def test_trace_groups_events_by_turn(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(event_type="run_start", payload={"user_input": "hello"})
    logger.log_event(
        event_type="model_request",
        payload={"turn_index": 1, "context_prompt": "# 上下文包\n\nhello", "conversation_tail": []},
    )
    logger.log_event(event_type="model_response", payload={"turn_index": 1, "content": "b"})
    logger.log_event(event_type="tool_result", payload={"turn_index": 2, "content": "c"})

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "## 启动" in trace_content
    assert "## Turn 1" in trace_content
    assert "## Turn 2" in trace_content
    assert "**思考输入**" in trace_content
    assert "# 上下文包" in trace_content
    assert "**输出**" in trace_content
    assert "b" in trace_content
    assert "**观察**" in trace_content
    assert "c" in trace_content


def test_trace_adds_visual_sections_for_common_events(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(
        event_type="model_request",
        payload={
            "turn_index": 1,
            "context_prompt": "# 上下文包\n\nhello",
            "conversation_tail": [],
            "tool_names": ["fs_read"],
        },
    )
    logger.log_event(
        event_type="model_response",
        payload={
            "turn_index": 1,
            "reasoning": "Need to read a file first.",
            "content": "",
            "tool_calls": [{"name": "fs_read", "arguments": {"path": "a.md"}}],
        },
    )
    logger.log_event(
        event_type="tool_result",
        payload={
            "turn_index": 1,
            "tool_name": "fs_read",
            "call_id": "call_1",
            "is_error": False,
            "content": "file body",
            "metadata": {},
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "**思考输入**" in trace_content
    assert "hello" in trace_content
    assert "**思考**" in trace_content
    assert "Need to read a file first." in trace_content
    assert "**行动**" in trace_content
    assert "`fs_read`" in trace_content
    assert '"path": "a.md"' in trace_content
    assert "**观察**" in trace_content
    assert '"path": "a.md"' in trace_content
    assert "file body" in trace_content


def test_trace_shows_run_start_summary(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    artifact_path = logger.write_text_artifact("system_prompt.txt", "system prompt body")
    logger.log_event(
        event_type="run_start",
        payload={
            "user_input": "hello",
            "config": {"max_turns": 3},
            "system_prompt_path": artifact_path,
            "skill_paths": ["skills/todo-list.md"],
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "## 启动" in trace_content
    assert "**输入**: hello" in trace_content
    assert "**配置**: max_turns=3" in trace_content
    assert "**Skills**: skills/todo-list.md" in trace_content
    assert "system prompt body" not in trace_content


def test_trace_omits_system_message_body_from_model_request(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(
        event_type="model_request",
        payload={
            "turn_index": 1,
            "system_prompt_path": "system_prompt.txt",
            "skill_paths": ["skills/todo-list.md"],
            "context_prompt": "hello",
            "conversation_tail": [],
            "tool_names": [],
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "very long system prompt body" not in trace_content
    assert "**思考输入**" in trace_content
    assert "hello" in trace_content


def test_logger_always_persists_model_request_context_prompt_and_uses_field_specific_names(
    tmp_path, is_fast_mode: bool
) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs", artifact_char_threshold=20)
    logger.log_event(
        event_type="model_request",
        payload={
            "turn_index": 1,
            "system_prompt_path": "system_prompt.txt",
            "context_prompt": "short context",
            "conversation_tail": [
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content_preview": "y" * 50,
                }
            ],
        },
    )

    events = [
        json.loads(line)
        for line in (logger.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    artifacts = events[0]["artifacts"]
    artifact_paths = [item["artifact_path"] for item in artifacts]

    assert artifact_paths == [
        "artifacts/0001_model_request_payload_context_prompt.txt",
        "artifacts/0002_model_request_payload_conversation_tail_0_content_preview.txt",
    ]
    assert all("system_prompt" not in path for path in artifact_paths)
    context_artifact = logger.run_dir / artifact_paths[0]
    assert context_artifact.read_text(encoding="utf-8") == "short context"


def test_trace_renders_openai_style_assistant_tool_calls(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(
        event_type="model_response",
        payload={
            "turn_index": 2,
            "reasoning": "",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "fs_write",
                        "arguments": '{"path":"demo.md","content":"hello"}',
                    },
                }
            ],
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")
    assert "**行动**" in trace_content
    assert "`fs_write`" in trace_content
    assert "demo.md" in trace_content


def test_trace_shows_token_count_and_tool_catalog(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(
        event_type="model_request",
        payload={
            "turn_index": 1,
            "context_prompt": "hello",
            "token_count": 321,
            "conversation_tail": [],
            "tool_names": ["fs_read", "web_search"],
            "effective_tool_choice": "auto",
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "估算 Token: `321`" in trace_content
    assert "可用工具: `fs_read`, `web_search`" in trace_content
    assert "工具策略: `auto`" in trace_content
