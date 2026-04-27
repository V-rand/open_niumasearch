from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from deep_research_agent.tools.base import ToolDefinition, ToolRegistry


def register_file_system_tools(registry: ToolRegistry, workspace_root: Path) -> None:
    def resolve_path(raw_path: str) -> Path:
        path = (workspace_root / raw_path).resolve()
        if path != workspace_root and workspace_root not in path.parents:
            raise ValueError(f"Path escapes workspace root: {raw_path}")
        return path

    def fs_list(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        root = resolve_path(arguments.get("path", "."))
        recursive = bool(arguments.get("recursive", False))
        max_depth = arguments.get("max_depth")
        include_hidden = bool(arguments.get("include_hidden", False))
        kind = arguments.get("kind", "all")

        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {root}")

        entries: list[dict[str, Any]] = []
        iterator = root.rglob("*") if recursive else root.iterdir()
        base_depth = len(root.parts)

        for entry in iterator:
            relative = entry.relative_to(workspace_root)
            if not include_hidden and any(part.startswith(".") for part in relative.parts):
                continue

            if max_depth is not None and len(entry.parts) - base_depth > int(max_depth):
                continue

            if kind == "file" and not entry.is_file():
                continue
            if kind == "dir" and not entry.is_dir():
                continue

            entries.append(
                {
                    "path": str(relative),
                    "kind": "dir" if entry.is_dir() else "file",
                    "size": entry.stat().st_size,
                }
            )

        return entries

    def fs_read(arguments: dict[str, Any]) -> dict[str, Any]:
        path = resolve_path(arguments["path"])
        
        # Extension-based Intelligence
        suffix = path.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            return {
                "content": f"[Binary Image File: {path.name}]",
                "system_note": f"This is an image. You cannot read it as text. Please use 'ocr_parse' with the file's URL or local path to extract information."
            }
        
        if suffix == ".pdf":
            return {
                "content": f"[PDF Document: {path.name}]",
                "system_note": f"This is a PDF file. Reading it directly as text may yield garbled characters. Please use 'pdf_read_url' (if you have the URL) or 'ocr_parse' for precise extraction."
            }

        text = path.read_text(encoding="utf-8")
        total_length = len(text)

        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        lines = text.splitlines()
        total_lines = len(lines)
        
        if start_line is not None or end_line is not None:
            start = max(int(start_line or 1) - 1, 0)
            end = int(end_line) if end_line is not None else len(lines)
            text = "\n".join(lines[start:end])

        max_chars = arguments.get("max_chars")
        if max_chars is not None and len(text) > int(max_chars):
            text = text[: int(max_chars)] + "\n\n... (Content truncated due to max_chars limit) ..."

        # Dynamic guidance
        note = f"Read {len(text)} chars from {path.name}."
        if total_length > len(text):
            note += f" Total file length is {total_length} chars. Use 'start_line'/'end_line' or 'max_chars' to read more."
            
        return {
            "content": text,
            "total_lines": total_lines,
            "system_note": note
        }

    def fs_write(arguments: dict[str, Any]) -> dict[str, Any]:
        path = resolve_path(arguments["path"])
        mode = arguments.get("mode", "overwrite")
        mkdir_parents = bool(arguments.get("mkdir_parents", True))
        content = arguments["content"]

        if mkdir_parents:
            path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "create_only" and path.exists():
            raise FileExistsError(f"File already exists: {path}")

        if mode == "append":
            with path.open("a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            path.write_text(content, encoding="utf-8")

        return {
            "path": str(path.relative_to(workspace_root)),
            "bytes_written": len(content.encode("utf-8")),
        }

    def fs_patch(arguments: dict[str, Any]) -> dict[str, Any]:
        path = resolve_path(arguments["path"])
        operation = arguments["operation"]
        target = arguments["target"]
        content = arguments["content"]
        occurrence = arguments.get("occurrence", "first")

        text = path.read_text(encoding="utf-8")
        replacements = text.count(target)
        if replacements == 0:
            raise ValueError(f"Target not found: {target}")

        if operation == "replace":
            if occurrence == "first":
                updated = text.replace(target, content, 1)
                replaced_count = 1
            elif occurrence == "last":
                head, sep, tail = text.rpartition(target)
                updated = f"{head}{content}{tail}" if sep else text
                replaced_count = 1 if sep else 0
            else:
                updated = text.replace(target, content)
                replaced_count = replacements
        elif operation == "insert_before":
            replacement = f"{content}{target}"
            updated, replaced_count = _replace_by_occurrence(text, target, replacement, occurrence)
        elif operation == "insert_after":
            replacement = f"{target}{content}"
            updated, replaced_count = _replace_by_occurrence(text, target, replacement, occurrence)
        else:
            raise ValueError(f"Unsupported patch operation: {operation}")

        path.write_text(updated, encoding="utf-8")
        return {
            "path": str(path.relative_to(workspace_root)),
            "replaced_count": replaced_count,
        }

    def fs_status(arguments: dict[str, Any]) -> dict[str, Any]:
        """Provides a high-level overview of the workspace state."""
        all_files = list(workspace_root.rglob("*"))
        files_only = [f for f in all_files if f.is_file()]
        
        # Breakdown by key directories
        stats = {
            "total_files": len(files_only),
            "research_raw": len([f for f in files_only if "research/raw" in str(f)]),
            "search_history": len([f for f in files_only if "research/search_history" in str(f)]),
            "documents": len([f for f in files_only if "documents" in str(f)]),
        }
        
        # Check core files
        core_files = {}
        for name in ["todo.md", "research/source_index.md", "research/report.md"]:
            p = workspace_root / name
            if p.exists():
                core_files[name] = {
                    "size": p.stat().st_size,
                    "last_modified": time.ctime(p.stat().st_mtime)
                }
            else:
                core_files[name] = "Not Created"
                
        # Recent activity (last 5 modified files)
        recent = sorted(files_only, key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        activity = [str(f.relative_to(workspace_root)) for f in recent]
        
        return {
            "workspace_stats": stats,
            "core_files_status": core_files,
            "recent_activity": activity,
            "system_note": "Use this tool to verify your research progress and locate archived sources."
        }

    def fs_grep(arguments: dict[str, Any]) -> dict[str, Any]:
        """Search for a keyword across multiple text files in the workspace."""
        query = arguments["query"]
        path_pattern = arguments.get("path", "research/")
        root = resolve_path(path_pattern)
        
        matches = []
        # Simple recursive search
        for f in root.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".txt", ".json"):
                try:
                    content = f.read_text(encoding="utf-8")
                    if query.lower() in content.lower():
                        # Find line numbers
                        for i, line in enumerate(content.splitlines()):
                            if query.lower() in line.lower():
                                matches.append({
                                    "path": str(f.relative_to(workspace_root)),
                                    "line": i + 1,
                                    "context": line.strip()[:200]
                                })
                                if len(matches) >= 50: break # Safety limit
                except Exception: continue
            if len(matches) >= 50: break

        return {
            "query": query,
            "match_count": len(matches),
            "matches": matches,
            "system_note": "Use this to locate evidence before reading full files."
        }

    def fs_outline(arguments: dict[str, Any]) -> dict[str, Any]:
        """Extract all Markdown headers to understand document structure."""
        path = resolve_path(arguments["path"])
        if path.suffix != ".md":
            raise ValueError("Outline only supports Markdown files.")
            
        lines = path.read_text(encoding="utf-8").splitlines()
        headers = []
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                headers.append({
                    "level": line.count("#", 0, line.find(" ")),
                    "title": line.strip("# ").strip(),
                    "line": i + 1
                })
        
        return {
            "path": str(path.relative_to(workspace_root)),
            "headers": headers,
            "system_note": "Use line numbers for precise fs_patch or targeted fs_read."
        }

    def fs_metadata_query(arguments: dict[str, Any]) -> dict[str, Any]:
        """Check if a URL is already archived and where."""
        url = arguments["url"]
        from deep_research_agent.tools.utils import _find_existing_raw_source
        existing = _find_existing_raw_source(workspace_root, url)
        if existing:
            return {
                "url": url,
                "status": "found",
                "raw_path": existing["raw_path"],
                "title": existing["title"],
                "system_note": "Source already exists. Use fs_read instead of downloading again."
            }
        return {"url": url, "status": "not_found"}

    registry.register(
        ToolDefinition(
            name="fs_grep",
            description="Recursively search for text patterns in workspace files. Essential for locating evidence.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "default": "research/"},
                },
                "required": ["query"],
            },
            handler=fs_grep,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_outline",
            description="Extract the header structure of a Markdown file. Best for long reports or archives.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
            handler=fs_outline,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_metadata_query",
            description="Quickly check if a specific URL has already been processed.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
            handler=fs_metadata_query,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_status",
            description="Get a high-level status of the research workspace, including file counts and recent activity.",
            parameters={"type": "object", "properties": {}},
            handler=fs_status,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_list",
            description="List files and directories within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean"},
                    "max_depth": {"type": "integer"},
                    "include_hidden": {"type": "boolean"},
                    "kind": {"type": "string", "enum": ["all", "file", "dir"]},
                },
                "required": [],
            },
            handler=fs_list,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_read",
            description="Read a text file from the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["path"],
            },
            handler=fs_read,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_write",
            description="Write or append content to a file in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["overwrite", "append", "create_only"]},
                    "mkdir_parents": {"type": "boolean"},
                },
                "required": ["path", "content"],
            },
            handler=fs_write,
        )
    )
    registry.register(
        ToolDefinition(
            name="fs_patch",
            description="Patch a text file using search and replace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "operation": {"type": "string", "enum": ["replace", "insert_before", "insert_after"]},
                    "target": {"type": "string"},
                    "content": {"type": "string"},
                    "occurrence": {"type": "string", "enum": ["first", "last", "all"]},
                },
                "required": ["path", "operation", "target", "content"],
            },
            handler=fs_patch,
        )
    )


def _replace_by_occurrence(text: str, target: str, replacement: str, occurrence: str) -> tuple[str, int]:
    if occurrence == "first":
        return text.replace(target, replacement, 1), 1
    if occurrence == "last":
        head, sep, tail = text.rpartition(target)
        if not sep:
            raise ValueError(f"Target not found: {target}")
        return f"{head}{replacement}{tail}", 1
    replaced = text.count(target)
    return text.replace(target, replacement), replaced
