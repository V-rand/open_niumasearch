from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from typing import Any
import httpx

from deep_research_agent.tools.base import ToolDefinition, ToolRegistry
from deep_research_agent.tools.archiver import ResearchArchiver
from deep_research_agent.tools.distiller import distill_evidence
from deep_research_agent.dashscope_backend import ModelBackend

logger = logging.getLogger(__name__)

# Standalone core logic - can be imported and used anywhere
def fetch_and_distill_web(
    url: str,
    archiver: ResearchArchiver,
    model_backend: ModelBackend,
    http_client: httpx.Client,
    focus_query: str | None = None,
) -> dict[str, Any]:
    """Pure logic for fetching, archiving, and distilling web content with error handling."""
    
    # 1. Fetch
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Authorization": f"Bearer {os.getenv('JINA_API_KEY')}"} if os.getenv("JINA_API_KEY") else {}
        resp = http_client.get(jina_url, headers=headers, timeout=30)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        error_msg = str(e)
        system_advice = "Unknown network error."
        
        # Specific advice for common research blockers
        if "101" in error_msg or "unreachable" in error_msg.lower() or "timeout" in error_msg.lower():
            if ".gov.cn" in url:
                system_advice = f"CRITICAL: The domain '{url}' is blocked or unreachable from current node. DO NOT RETRY. Immediately switch to research_search to find mirrors or third-party reports (e.g., legal blogs, news) to cross-validate this document."
            else:
                system_advice = "Connection failed. Avoid redundant retries. Check URL or try another source."
                
        return {
            "status": "error",
            "message": error_msg,
            "system_note": system_advice
        }
    
    # 2. Archive Raw
    # Use title from the content if possible, else URL
    title_match = re.search(r"title: (.*)", content)
    title = title_match.group(1).strip() if title_match else url.split("/")[-1] or "web_page"
    archived = archiver.archive_raw(title, url, content, "web")
    
    # 3. Distill
    evidence = distill_evidence(model_backend, content, focus_query) if focus_query else content[:2000]
    
    # 4. Archive Extract & Update Index
    note_path = ""
    if focus_query:
        note_path = archiver.archive_extract(archived["filename"], focus_query, evidence)
        
    archiver.update_index({
        "title": title,
        "url": url,
        "raw_path": archived["raw_path"],
        "note_paths": [note_path] if note_path else [],
        "summary": evidence[:300]
    })
    
    return {
        "status": "success",
        "url": url,
        "evidence": evidence,
        "raw_path": archived["raw_path"],
        "note_path": note_path,
        "system_note": archived.get("system_note")
    }

def register_web_tools(
    registry: ToolRegistry,
    workspace_root: Path,
    http_client: httpx.Client,
    model_backend: ModelBackend,
) -> None:
    archiver = ResearchArchiver(workspace_root)

    def jina_reader(arguments: dict[str, Any]) -> dict[str, Any]:
        return fetch_and_distill_web(
            url=arguments["url"],
            archiver=archiver,
            model_backend=model_backend,
            http_client=http_client,
            focus_query=arguments.get("focus_query")
        )

    registry.register(
        ToolDefinition(
            name="jina_reader",
            description="Smart web reader. Archives content automatically. Returns error advice on failure.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "focus_query": {"type": "string"},
                },
                "required": ["url"],
            },
            handler=jina_reader,
        )
    )
