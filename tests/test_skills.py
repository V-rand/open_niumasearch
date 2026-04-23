from __future__ import annotations

from pathlib import Path

from deep_research_agent.skills import compose_system_prompt, load_repo_skills


def test_load_repo_skills_reads_skill_content(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True)
    skill_path = skills_root / "demo-skill.md"
    skill_path.write_text("# Demo Skill\n\nUse carefully.\n", encoding="utf-8")

    loaded = load_repo_skills(["demo-skill"], skills_root=skills_root)

    assert len(loaded) == 1
    assert loaded[0].name == "demo-skill"
    assert loaded[0].path == Path(skill_path)
    assert "Demo Skill" in loaded[0].content


def test_compose_system_prompt_appends_skill_sections(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True)
    skill_path = skills_root / "demo-skill.md"
    skill_path.write_text("# Demo Skill\n\nUse carefully.\n", encoding="utf-8")

    [skill] = load_repo_skills(["demo-skill"], skills_root=skills_root)
    prompt = compose_system_prompt("Base prompt.", [skill])

    assert "Base prompt." in prompt
    assert "## Skill: demo-skill" in prompt
    assert f"Path: {skill_path}" in prompt
    assert "# Demo Skill" in prompt


def test_load_unified_todo_skill_from_repo(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    loaded = load_repo_skills(["todo"])

    assert len(loaded) == 1
    assert loaded[0].name == "todo"
    assert "FIREWALL" in loaded[0].content
    assert "fs_patch" in loaded[0].content


def test_load_same_todo_skill_multiple_times(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    loaded = load_repo_skills(["todo", "todo"])

    assert len(loaded) == 2
    names = {s.name for s in loaded}
    assert names == {"todo"}
