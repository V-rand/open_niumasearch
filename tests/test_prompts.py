from __future__ import annotations

from deep_research_agent.prompts import get_system_prompt


def test_system_prompt_contains_core_principles(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    prompt = get_system_prompt()
    assert "核心工作原则" in prompt
    assert "查重契约" in prompt
    assert "证据锚定契约" in prompt
    assert "不再维护 `Memory.md`" in prompt
