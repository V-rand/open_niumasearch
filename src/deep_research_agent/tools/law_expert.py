from __future__ import annotations

import asyncio
import os
import logging
from pathlib import Path
from typing import Any
import concurrent.futures

from deep_research_agent.tools.core import ToolDefinition, ToolRegistry
from deep_research_agent.tools.archiver import ResearchArchiver

logger = logging.getLogger(__name__)

async def _safe_law_retrieve(query: str, archiver: ResearchArchiver, top_k: int = 5) -> dict[str, Any]:
    try:
        from deep_research_agent.retrieval_untils import retrieve
        results = await asyncio.to_thread(retrieve, query, 30, top_k, "Deli", 60, "Legal query", top_k)
        
        if not results:
            return {"status": "not_found", "results": []}

        normalized = []
        for item in results:
            content = item.get("article_content") or item.get("articleContent", "")
            title = f"{item.get('laws_name') or item.get('lawsName', '')} {item.get('article_tag') or item.get('articleTag', '')}".strip()
            
            # archive_raw now handles update_index automatically
            archived = archiver.archive_raw(
                title=title,
                url=f"deli://law/{query}",
                content=content,
                source_type="legal_regulation"
            )
            
            normalized.append({
                "title": title,
                "raw_path": archived.get("raw_path"),
                "source_id": archived.get("id")
            })
            
        return {"status": "success", "count": len(normalized), "results": normalized}
    except Exception as e:
        logger.error(f"Law retrieve error: {e}")
        return {"status": "error", "message": str(e)}

async def _safe_case_retrieve(query: str, archiver: ResearchArchiver, top_k: int = 5) -> dict[str, Any]:
    try:
        from deep_research_agent.untils_case import get_case_results
        results = await asyncio.to_thread(get_case_results, query, top_k, False)
        
        if not results:
            return {"status": "not_found", "results": []}

        normalized = []
        for item in results:
            content = item.get("content", "")
            title = item.get("title", "Untitled Case")
            
            archived = archiver.archive_raw(
                title=title,
                url=f"CaseNo: {item.get('caseNo', 'N/A')}",
                content=content,
                source_type="judicial_case"
            )
            
            normalized.append({
                "title": title,
                "case_no": item.get("caseNo", "N/A"),
                "court": item.get("court", "N/A"),
                "raw_path": archived.get("raw_path"),
                "source_id": archived.get("id")
            })
            
        return {"status": "success", "count": len(normalized), "results": normalized}
    except Exception as e:
        logger.error(f"Case retrieve error: {e}")
        return {"status": "error", "message": str(e)}

def _run_async_safely(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

def register_law_expert_tools(registry: ToolRegistry, workspace_root: Path) -> None:
    archiver = ResearchArchiver(workspace_root)
    
    def law_retrieve(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query", "").strip()
        top_k = int(arguments.get("top_k", 5))
        return _run_async_safely(_safe_law_retrieve(query, archiver, top_k))

    def case_retrieve(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query", "").strip()
        top_k = int(arguments.get("top_k", 5))
        return _run_async_safely(_safe_case_retrieve(query, archiver, top_k))

    registry.register(
        ToolDefinition(
            name="law_retrieve",
            description="Retrieve laws and regulations. Results are AUTOMATICALLY archived and indexed.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}, "required": ["query"]},
            handler=law_retrieve,
        )
    )

    registry.register(
        ToolDefinition(
            name="case_retrieve",
            description="Retrieve judicial cases. Results are AUTOMATICALLY archived and indexed.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}, "required": ["query"]},
            handler=case_retrieve,
        )
    )
