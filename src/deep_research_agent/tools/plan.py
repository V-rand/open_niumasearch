from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import datetime

from deep_research_agent.tools.base import ToolDefinition, ToolRegistry

class ResearchPlan:
    def __init__(self, workspace_root: Path):
        self.path = workspace_root / "research" / "plan.json"
        self.workspace_root = workspace_root
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {"sub_problems": [], "updated_at": ""}
        else:
            self.data = {"sub_problems": [], "updated_at": ""}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = datetime.datetime.now().isoformat()
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Sync to Markdown for human readability
        md_path = self.workspace_root / "todo.md"
        lines = ["# Research Plan & Progress", "", f"*Last Updated: {self.data['updated_at']}*", ""]
        for i, sp in enumerate(self.data["sub_problems"]):
            status_icon = "✅" if sp["status"] == "completed" else "⏳"
            lines.append(f"### {i+1}. {sp['title']} [{status_icon}]")
            lines.append(f"- **Status**: `{sp['status']}`")
            if sp.get("finding"):
                lines.append(f"- **Finding**: {sp['finding']}")
            if sp.get("evidence_ref"):
                lines.append(f"- **Evidence**: {sp['evidence_ref']}")
            lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")

def register_plan_tools(registry: ToolRegistry, workspace_root: Path) -> None:
    
    def plan_decompose(arguments: dict[str, Any]) -> dict[str, Any]:
        """Initialize or restructure the research plan into sub-problems."""
        plan = ResearchPlan(workspace_root)
        sub_problems = arguments["sub_problems"]
        plan.data["sub_problems"] = [
            {"title": title, "status": "todo", "finding": "", "evidence_ref": ""}
            for title in sub_problems
        ]
        plan.save()
        return {
            "status": "success",
            "message": f"Decomposed into {len(sub_problems)} sub-problems.",
            "plan_summary": [sp["title"] for sp in plan.data["sub_problems"]]
        }

    def plan_mark_progress(arguments: dict[str, Any]) -> dict[str, Any]:
        """Update progress on a specific sub-problem. Use index from plan_view."""
        plan = ResearchPlan(workspace_root)
        idx = int(arguments["index"]) - 1
        if idx < 0 or idx >= len(plan.data["sub_problems"]):
            return {"error": f"Invalid index. Current plan has {len(plan.data['sub_problems'])} items."}
        
        sp = plan.data["sub_problems"][idx]
        sp["status"] = arguments.get("status", "completed")
        sp["finding"] = arguments.get("finding", sp["finding"])
        sp["evidence_ref"] = arguments.get("evidence_ref", sp["evidence_ref"])
        plan.save()
        
        return {
            "updated_item": sp["title"],
            "new_status": sp["status"],
            "system_note": "Plan updated. Remember to link to source_id for accountability."
        }

    def plan_view(arguments: dict[str, Any]) -> dict[str, Any]:
        """View the current research plan, findings, and remaining gaps."""
        plan = ResearchPlan(workspace_root)
        if not plan.data["sub_problems"]:
            return {"status": "empty", "system_note": "No plan found. Use 'plan_decompose' to start."}
        return {
            "plan": plan.data["sub_problems"],
            "system_note": "Review your progress frequently to stay focused on the mission."
        }

    registry.register(
        ToolDefinition(
            name="plan_decompose",
            description="Break down the main mission into 3-5 tactical sub-problems. Essential for complex research.",
            parameters={
                "type": "object",
                "properties": {
                    "sub_problems": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sub_problems"],
            },
            handler=plan_decompose,
        )
    )
    registry.register(
        ToolDefinition(
            name="plan_mark_progress",
            description="Update a sub-problem with findings and evidence. Marks a research step as 'completed'.",
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "1-based index from plan_view."},
                    "status": {"type": "string", "enum": ["todo", "active", "completed", "blocked"]},
                    "finding": {"type": "string", "description": "Key fact or conclusion discovered."},
                    "evidence_ref": {"type": "string", "description": "The Source ID or URL supporting this finding."},
                },
                "required": ["index"],
            },
            handler=plan_mark_progress,
        )
    )
    registry.register(
        ToolDefinition(
            name="plan_view",
            description="Get a full snapshot of the research plan, all discovered facts, and remaining work.",
            parameters={"type": "object", "properties": {}},
            handler=plan_view,
        )
    )
