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

def register_serper_tools(
    registry: ToolRegistry,
    workspace_root: Path,
    http_client: httpx.Client,
) -> None:
    def serper_search(arguments: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            raise RuntimeError("SERPER_API_KEY is not set")

        query = arguments["query"]
        url = "https://google.serper.dev/search"
        payload = {
            "q": query,
            "num": arguments.get("max_results", 10),
            "gl": arguments.get("country", "us"),
            "hl": arguments.get("language", "en"),
        }
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }

        response = http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        raw_organic = data.get("organic", [])
        results = []
        for item in raw_organic:
            results.append({
                "title": item.get("title"),
                "url": item.get("link"),
                "content": item.get("snippet"),
                "score": 1.0 - (item.get("position", 10) / 100.0)
            })

        # Automated Archiving
        history_path = _archive_search_results(
            workspace_root=workspace_root,
            query=query,
            results=results,
            provider="serper"
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
            "system_note": f"Search results archived at {history_path.relative_to(workspace_root)}. "
                           "Highly relevant results are prioritized."
        }

    registry.register(
        ToolDefinition(
            name="serper_search",
            description="High-quality Google Search via Serper API. Best for general facts and broad topics.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                    "country": {"type": "string", "default": "us"},
                    "language": {"type": "string", "default": "en"},
                    "keep_result_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices (1-based) of search results to keep in research/leads.md.",
                    },
                    "keep_reason": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=serper_search,
        )
    )
