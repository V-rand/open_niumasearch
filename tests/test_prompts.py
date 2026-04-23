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
    assert "每个目标都必须绑定一个可验证产出" in prompt
    assert "只有在可验证产出已经出现后，目标才能闭合" in prompt
    assert "实践、认识、再实践" in prompt
    assert "当前最主要矛盾" in prompt
