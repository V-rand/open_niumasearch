from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_todo_md_creates_research_template(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    module = _load_module(
        Path("scripts/init_todo_md.py").resolve(),
        "todo_init_script",
    )
    content = module.create_todo_markdown(phase="research", title="测试任务")

    assert "# 测试任务 - 研究 TODO" in content
    assert "## 目标" in content
    assert "## 任务列表" in content
    assert "- [ ] open:" in content
    assert "## 阶段动态" in content


def test_init_todo_md_creates_writing_template(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    module = _load_module(
        Path("scripts/init_todo_md.py").resolve(),
        "todo_init_writing",
    )
    content = module.create_todo_markdown(phase="writing", title="写作测试")

    assert "# 写作测试 - 写作 TODO" in content
    assert "## 目标" in content
    assert "## 任务列表" in content
    assert "- [ ] open:" in content
    assert "## 阶段动态" in content


def test_validate_todo_md_rejects_missing_sections(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    module = _load_module(
        Path("scripts/validate_todo_md.py").resolve(),
        "todo_validate_script",
    )
    errors = module.validate_todo_markdown("# 只有标题\n")

    assert any("## 目标" in error for error in errors)
    assert any("task list item" in error for error in errors)


def test_validate_todo_md_accepts_complete_research_template(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    init_module = _load_module(
        Path("scripts/init_todo_md.py").resolve(),
        "todo_init_script_ok",
    )
    validate_module = _load_module(
        Path("scripts/validate_todo_md.py").resolve(),
        "todo_validate_script_ok",
    )
    content = init_module.create_todo_markdown(phase="research", title="测试任务")

    errors = validate_module.validate_todo_markdown(content)

    assert errors == []


def test_validate_todo_md_rejects_invalid_status(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    module = _load_module(
        Path("scripts/validate_todo_md.py").resolve(),
        "todo_validate_invalid",
    )
    text = """# 测试

## 目标
测试

## 任务列表
- [ ] invalid_status: 某个任务

## 阶段动态
- 2024-01-01: 测试
"""
    errors = module.validate_todo_markdown(text)

    assert any("Invalid task status" in error for error in errors)
