from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.tools.core import ToolDefinition, ToolRegistry, ModelBackend
from deep_research_agent.tools.archiver import ResearchArchiver
from deep_research_agent.tools.distiller import distill_evidence

def fetch_and_distill_ocr(
    url: str,
    archiver: ResearchArchiver,
    model_backend: ModelBackend,
    http_client: httpx.Client,
    focus_query: str | None = None,
) -> dict[str, Any]:
    # 1. Submit MinerU task
    submit_response = http_client.post(
        "https://mineru.net/api/v1/agent/parse/url", 
        json={"url": url}
    )
    submit_response.raise_for_status()
    task_id = submit_response.json().get("data", {}).get("task_id")
    
    # 2. Polling
    markdown = ""
    for _ in range(30):
        time.sleep(2)
        poll_resp = http_client.get(f"https://mineru.net/api/v1/agent/parse/{task_id}")
        data = poll_resp.json().get("data", {})
        if data.get("state") == "done":
            markdown = data.get("markdown") or ""
            break
            
    if not markdown:
        raise RuntimeError("OCR task timed out or failed.")
        
    # 3. Archive & Distill
    title = url.split("/")[-1] or "ocr_doc"
    archived = archiver.archive_raw(title, url, markdown, "ocr")
    evidence = distill_evidence(model_backend, markdown, focus_query) if focus_query else markdown[:2000]
    
    note_path = ""
    if focus_query:
        note_path = archiver.archive_extract(archived["filename"], focus_query, evidence)
        
    archiver.update_index({
        "title": title, "url": url, "raw_path": archived["raw_path"], "note_paths": [note_path] if note_path else []
    })
    
    return {"url": url, "evidence": evidence, "raw_path": archived["raw_path"]}

def register_mineru_tools(
    registry: ToolRegistry,
    http_client: httpx.Client,
    model_backend: ModelBackend,
    workspace_root: Path,
) -> None:
    archiver = ResearchArchiver(workspace_root)
    
    def ocr_parse(arguments: dict[str, Any]) -> dict[str, Any]:
        return fetch_and_distill_ocr(
            url=arguments["url"],
            archiver=archiver,
            model_backend=model_backend,
            http_client=http_client,
            focus_query=arguments.get("focus_query")
        )

    registry.register(
        ToolDefinition(
            name="ocr_parse",
            description="High-precision OCR with evidence distillation.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "focus_query": {"type": "string"},
                },
                "required": ["url"],
            },
            handler=ocr_parse,
        )
    )
