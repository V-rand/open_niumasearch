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


def test_load_research_todo_skill_from_repo(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    loaded = load_repo_skills(["research-todo"])

    assert len(loaded) == 1
    assert loaded[0].name == "research-todo"
    assert "research-todo" in loaded[0].content
    assert "closed" in loaded[0].content
    assert "Closure Attempt" in loaded[0].content


def test_load_write_todo_skill_from_repo(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    loaded = load_repo_skills(["write-todo"])

    assert len(loaded) == 1
    assert loaded[0].name == "write-todo"
    assert "write-todo" in loaded[0].content
    assert "closed" in loaded[0].content
    assert "补证" in loaded[0].content


def test_load_both_todo_skills_together(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    loaded = load_repo_skills(["research-todo", "write-todo"])

    assert len(loaded) == 2
    names = {s.name for s in loaded}
    assert names == {"research-todo", "write-todo"}
