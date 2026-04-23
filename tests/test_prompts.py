from __future__ import annotations

from deep_research_agent.prompts import get_system_prompt


def test_system_prompt_contains_core_principles(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    prompt = get_system_prompt()
    assert "核心工作原则" in prompt
    assert "调查 -> 认识 -> 写作" in prompt
    assert "外部化工作记忆" in prompt

