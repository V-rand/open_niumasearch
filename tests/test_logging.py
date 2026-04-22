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
    # New diary-style trace: no "Lifecycle" heading, tool result shown inline
    assert "📄 **Result** (`sample_tool`, ok)" in trace_content
    assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" in trace_content
    assert "### Payload" not in trace_content
    assert "timestamp:" not in trace_content


def test_trace_groups_events_by_turn(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(event_type="run_start", payload={"user_input": "hello"})
    logger.log_event(event_type="model_request", payload={"turn_index": 1, "messages": ["a"]})
    logger.log_event(event_type="model_response", payload={"turn_index": 1, "content": "b"})
    logger.log_event(event_type="tool_result", payload={"turn_index": 2, "content": "c"})

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    assert "## 启动" in trace_content
    assert "## Turn 1" in trace_content
    assert "## Turn 2" in trace_content
    # model_request is suppressed in trace to reduce noise
    assert "### Event" not in trace_content
    assert "💬 **Output**" in trace_content
    assert "b" in trace_content
    assert "📄 **Result**" in trace_content
    assert "c" in trace_content


def test_trace_adds_visual_sections_for_common_events(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    logger = RunLogger(base_dir=tmp_path / "logs")
    logger.log_event(
        event_type="model_request",
        payload={
            "turn_index": 1,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"type": "function", "function": {"name": "fs_read"}}],
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

    # model_request suppressed; model_response shows thinking + tool request
    assert "🤔 **Thinking**" in trace_content
    assert "Need to read a file first." in trace_content
    assert "🛠️ **Tool**: `fs_read`" in trace_content
    assert "path=\"a.md\"" in trace_content
    assert "📄 **Result** (`fs_read`, ok)" in trace_content
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
            "messages": [
                {"role": "system", "content": "very long system prompt body"},
                {"role": "user", "content": "hello"},
            ],
            "tools": [],
        },
    )

    trace_content = (logger.run_dir / "trace.md").read_text(encoding="utf-8")

    # model_request is suppressed in trace
    assert "very long system prompt body" not in trace_content
    assert "**System Messages**" not in trace_content


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
    assert "🛠️ **Tool**: `fs_write`" in trace_content
    assert "demo.md" in trace_content
