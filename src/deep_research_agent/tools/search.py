from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.tools.core import ToolDefinition, ToolRegistry
from deep_research_agent.tools.archiver import ResearchArchiver

def register_unified_search_tools(
    registry: ToolRegistry,
    workspace_root: Path,
    http_client: httpx.Client,
) -> None:
    archiver = ResearchArchiver(workspace_root)

    def research_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments["query"]
        topic = arguments.get("topic", "general")
        max_results = int(arguments.get("max_results", 10))

        results = []
        provider_used = "none"

        # Topic-based Routing (Logic unchanged but cleaned up)
        if topic == "academic":
            results = _arxiv_search(query, max_results)
            provider_used = "arxiv"
        elif topic == "finance":
            results = _yfinance_search(query)
            provider_used = "yfinance"
        else:
            serper_key = os.getenv("SERPER_API_KEY")
            if serper_key:
                try:
                    url = "https://google.serper.dev/news" if topic == "news" else "https://google.serper.dev/search"
                    resp = http_client.post(url, headers={"X-API-KEY": serper_key}, json={"q": query, "num": max_results})
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_items = data.get("news" if topic == "news" else "organic", [])
                        results = [{"title": i.get("title"), "url": i.get("link"), "content": i.get("snippet")} for i in raw_items]
                        provider_used = "serper"
                except Exception: pass

            if not results:
                tavily_key = os.getenv("TAVILY_API_KEY")
                if tavily_key:
                    try:
                        resp = http_client.post("https://api.tavily.com/search", json={"api_key": tavily_key, "query": query, "max_results": max_results})
                        if resp.status_code == 200:
                            results = resp.json().get("results", [])
                            provider_used = "tavily"
                    except Exception: pass

        # 1. UNIFIED ARCHIVING (History)
        history_path = archiver.archive_history(query, results, provider_used)

        # 2. AUTOMATIC INDEXING of top search snippets
        # This makes the search results visible in source_index.md immediately
        for res in results[:3]:
            archiver.update_index({
                "title": f"Snippet: {res.get('title')}",
                "url": res.get("url", "N/A"),
                "summary": f"[Search Discovery] {res.get('content', '')}",
                "raw_path": f"history:{history_path}"
            })

        return {
            "topic": topic,
            "provider": provider_used,
            "results": results[:max_results],
            "history_path": history_path,
            "system_note": f"Found {len(results)} via {provider_used}. Top 3 indexed in source_index.md. Full history archived."
        }

    registry.register(
        ToolDefinition(
            name="research_search",
            description="Universal discovery tool. Automatically archives results and indexes top snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "topic": {"type": "string", "enum": ["general", "news", "finance", "academic"], "default": "general"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            handler=research_search,
        )
    )

def _arxiv_search(query: str, max_results: int) -> list[dict[str, Any]]:
    try:
        import arxiv
        client = arxiv.Client()
        search = arxiv.Search(query=query, max_results=max_results)
        return [{"title": r.title, "url": r.pdf_url, "content": r.summary} for r in client.results(search)]
    except ImportError: return []

def _yfinance_search(query: str) -> list[dict[str, Any]]:
    return [{"title": f"Market for {query}", "content": "Financial data placeholder...", "url": f"https://finance.yahoo.com/quote/{query}"}]
