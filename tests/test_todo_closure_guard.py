from __future__ import annotations

from deep_research_agent.tools import build_builtin_tools


def test_fs_write_rejects_closed_todo_without_closure_attempt(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = build_builtin_tools(workspace_root=tmp_path)
    result = registry.invoke(
        "fs_write",
        {
            "path": "research/todo.md",
            "content": "# TODO\n\n## 任务列表\n\n- [x] closed: 完成任务\n",
            "mode": "overwrite",
            "mkdir_parents": True,
        },
    )

    assert result.is_error is True
    assert "closure attempt" in result.content.lower()


def test_fs_write_accepts_closed_todo_with_required_closure_fields(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = build_builtin_tools(workspace_root=tmp_path)
    result = registry.invoke(
        "fs_write",
        {
            "path": "research/todo.md",
            "content": (
                "# TODO\n\n## 任务列表\n\n"
                "- [x] closed: 完成任务\n"
                "  - 结论：已完成\n"
                "  - 依据：research/evidence/demo.md\n"
                "  - 未决项：无\n"
            ),
            "mode": "overwrite",
            "mkdir_parents": True,
        },
    )

    assert result.is_error is False

