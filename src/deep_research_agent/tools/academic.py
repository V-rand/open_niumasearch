from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import httpx
from deep_research_agent.tools.base import ToolDefinition, ToolRegistry
from deep_research_agent.tools.utils import (
    _archive_search_results,
    _keep_selected_search_results,
    _summarize_source_text,
)

def register_academic_tools(
    registry: ToolRegistry,
    workspace_root: Path,
    http_client: httpx.Client,
) -> None:
    def crossref_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments["query"]
        url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": arguments.get("max_results", 5),
            "mailto": os.getenv("CROSSREF_MAILTO", "researcher@example.com"),
        }

        response = http_client.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        items = data.get("message", {}).get("items", [])
        results = []
        for item in items:
            title_list = item.get("title", ["Untitled"])
            title = title_list[0] if title_list else "Untitled"
            doi = item.get("DOI", "")
            results.append({
                "title": title,
                "url": f"https://doi.org/{doi}" if doi else "",
                "content": f"DOI: {doi} | Publisher: {item.get('publisher')} | Type: {item.get('type')}",
                "score": 1.0
            })

        # Automated Archiving
        history_path = _archive_search_results(
            workspace_root=workspace_root,
            query=query,
            results=results,
            provider="crossref"
        )

        kept_sources = _keep_selected_search_results(
            workspace_root=workspace_root,
            results=results,
            selected_indices=arguments.get("keep_result_indices"),
            keep_reason=arguments.get("keep_reason"),
        )

        return {
            "query": query,
            "results": results,
            "kept_sources": kept_sources,
            "system_note": f"Crossref metadata results archived at {history_path.relative_to(workspace_root)}."
        }

    registry.register(
        ToolDefinition(
            name="crossref_search",
            description="Search Crossref for scholarly metadata, DOIs, and publishers.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                    "keep_result_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices (1-based) of search results to keep in research/leads.md.",
                    },
                    "keep_reason": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=crossref_search,
        )
    )
