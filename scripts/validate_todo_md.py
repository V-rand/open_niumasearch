from __future__ import annotations

import argparse
from pathlib import Path


RESEARCH_REQUIRED_SECTIONS = [
    "# ",
    "## 目标",
    "## 任务列表",
    "## 阶段动态",
]

WRITING_REQUIRED_SECTIONS = [
    "# ",
    "## 目标",
    "## 任务列表",
    "## 阶段动态",
]

VALID_STATUSES = {"open", "in_progress", "tentatively_resolved", "closed", "deferred", "abandoned"}


def validate_todo_markdown(text: str) -> list[str]:
    errors: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ["TODO markdown is empty"]

    phase = _detect_phase(text)
    required_sections = RESEARCH_REQUIRED_SECTIONS if phase == "research" else WRITING_REQUIRED_SECTIONS

    for section in required_sections:
        if section not in text:
            errors.append(f"Missing required section: {section}")

    task_lines = _extract_task_lines(text)
    if not task_lines:
        errors.append("TODO markdown must contain at least one task list item")

    for line in task_lines:
        status = _extract_status(line)
        if status and status not in VALID_STATUSES:
            errors.append(f"Invalid task status '{status}' in line: {line.strip()}")

    if "## 阶段动态" in text and "- " not in _section_body(text, "## 阶段动态"):
        errors.append("阶段动态 should contain at least one bullet update")

    return errors


def _detect_phase(text: str) -> str:
    if "写作 TODO" in text or "## 写作" in text:
        return "writing"
    return "research"


def _extract_task_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_tasks = False
    for line in text.splitlines():
        if line.startswith("## 任务列表"):
            in_tasks = True
            continue
        if in_tasks:
            if line.startswith("## "):
                break
            if line.strip().startswith("- ["):
                lines.append(line)
    return lines


def _extract_status(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("- ["):
        return None
    after_bracket = stripped[stripped.find("]") + 1:].strip()
    if ":" in after_bracket:
        return after_bracket.split(":", 1)[0].strip()
    return None


def _section_body(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    after = text.split(heading, 1)[1]
    lines = after.splitlines()[1:]
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("## "):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Markdown TODO file.")
    parser.add_argument("path")
    args = parser.parse_args()

    text = Path(args.path).read_text(encoding="utf-8")
    errors = validate_todo_markdown(text)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()
