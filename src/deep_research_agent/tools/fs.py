from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from deep_research_agent.tools.core import ToolDefinition, ToolRegistry

def register_fs_tools(
    registry: ToolRegistry,
    workspace_root: Path,
) -> None:
    def fs_status(arguments: dict[str, Any]) -> dict[str, Any]:
        """Returns a comprehensive dashboard of the evidence library with tactical advice."""
        raw_dir = workspace_root / "research" / "raw"
        notes_dir = workspace_root / "research" / "notes"
        index_path = workspace_root / "research" / "source_index.md"
        
        raw_files = list(raw_dir.glob("*.md")) if raw_dir.exists() else []
        note_files = list(notes_dir.glob("*.md")) if notes_dir.exists() else []
        
        # Analyze index quality
        index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        has_summaries = "Automatically archived" not in index_content and len(index_content) > 100
        
        stats = {
            "total_raw_evidence": len(raw_files),
            "processed_notes": len(note_files),
            "index_status": "Rich" if has_summaries else "Thin/Automatic",
        }
        
        # TACTICAL ADVICE (System Steering)
        advice = []
        if len(raw_files) >= 30:
            advice.append("STOP COLLECTION: You already have 30+ raw files. Any further downloads are likely redundant and expensive.")
        
        if not has_summaries and len(raw_files) > 5:
            advice.append("ACTION REQUIRED: Your source_index is thin. You MUST read the source_index.md to see the automatically extracted summaries and update your PLAN with specific Source IDs.")
            
        if len(raw_files) > 0 and len(note_files) < (len(raw_files) / 3):
            advice.append("STRATEGY: Focus on 'evidence distillation' from existing raw files. Do not download more until you have processed current ones.")

        return {
            "evidence_dashboard": stats,
            "system_note": " ".join(advice) if advice else "Evidence library is growing. Stay focused on your research goals."
        }

    def fs_list(arguments: dict[str, Any]) -> dict[str, Any]:
        path = workspace_root / arguments.get("path", ".")
        if not path.exists(): return {"error": "Path not found"}
        
        items = []
        for entry in path.iterdir():
            items.append({
                "name": entry.name,
                "kind": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0
            })
        return {"items": items[:100], "total": len(items)}

    registry.register(
        ToolDefinition(
            name="fs_status",
            description="Crucial for progress awareness. Get a dashboard of evidence counts and tactical advice.",
            parameters={"type": "object", "properties": {}},
            handler=fs_status,
        )
    )
    
    registry.register(
        ToolDefinition(
            name="fs_list",
            description="List directory contents. Use this to verify physical files.",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=fs_list,
        )
    )
