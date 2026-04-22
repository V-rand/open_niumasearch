from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_SKILLS_ROOT = Path("skills")


@dataclass(slots=True)
class SkillDefinition:
    name: str
    path: Path
    content: str


def load_repo_skills(skill_names: list[str], *, skills_root: Path | None = None) -> list[SkillDefinition]:
    root = (skills_root or DEFAULT_SKILLS_ROOT).resolve()
    loaded: list[SkillDefinition] = []
    for name in skill_names:
        skill_path = root / f"{name}.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {name} ({skill_path})")
        loaded.append(
            SkillDefinition(
                name=name,
                path=skill_path,
                content=skill_path.read_text(encoding="utf-8"),
            )
        )
    return loaded


def compose_system_prompt(base_prompt: str, skills: list[SkillDefinition]) -> str:
    if not skills:
        return base_prompt

    sections = [base_prompt.rstrip(), "", "以下 repo-local skills 已启用。仅在任务相关时使用，并严格遵守其中规则。"]
    for skill in skills:
        sections.extend(
            [
                "",
                f"## Skill: {skill.name}",
                f"Path: {skill.path}",
                "",
                skill.content.rstrip(),
            ]
        )
    return "\n".join(sections).rstrip() + "\n"
