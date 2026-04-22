from __future__ import annotations

from deep_research_agent.prompts import get_system_prompt


def test_system_prompt_contains_query_style_guidance(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    prompt = get_system_prompt()
    assert "检索查询风格选择" in prompt
    assert "工具层不会改写你的 query" in prompt

