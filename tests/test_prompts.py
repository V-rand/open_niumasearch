from __future__ import annotations

from deep_research_agent.prompts import get_system_prompt


def test_system_prompt_contains_core_principles(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    prompt = get_system_prompt()
    assert "核心工作原则" in prompt
    assert "查重契约" in prompt
    assert "证据锚定契约" in prompt
    assert "实践、认识、再实践" in prompt
    assert "信息增益" in prompt
    assert "当前信念" in prompt
    assert "最大不确定性" in prompt
    assert "> 原文或接近原文的关键摘录" in prompt
    assert "写作中发现缺口时可以补检索" in prompt


def test_todo_skill_describes_bayesian_research_loop(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    skill = __import__("pathlib").Path("skills/todo.md").read_text(encoding="utf-8")
    assert "周期维护，而非动作维护" in skill
    assert "信念账本" in skill
    assert "信息增益原则" in skill
    assert "[Unread]" in skill
    assert "> 原文或接近原文的关键摘录" in skill
