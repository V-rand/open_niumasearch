from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.tools.core import ToolDefinition, ToolRegistry, ModelBackend
from deep_research_agent.tools.mineru import fetch_and_distill_ocr
from deep_research_agent.tools.utils import (
    _read_pdf_locally_from_url,
)
from deep_research_agent.tools.archiver import ResearchArchiver
from deep_research_agent.tools.distiller import distill_evidence


def register_pdf_tools(
    registry: ToolRegistry,
    workspace_root: Path,
    http_client: httpx.Client,
    model_backend: ModelBackend,
) -> None:
    archiver = ResearchArchiver(workspace_root)

    def pdf_read_url(arguments: dict[str, Any]) -> dict[str, Any]:
        url = arguments["url"]
        focus_query = arguments.get("focus_query")
        strategy = arguments.get("strategy", "hybrid")
        
        full_content = ""
        filename_hint = url.split("/")[-1] or "document.pdf"

        # 1. High-precision path (MinerU OCR)
        if strategy in ["ocr_only", "hybrid"]:
            try:
                ocr_result = fetch_and_distill_ocr(
                    url=url, archiver=archiver, model_backend=model_backend,
                    http_client=http_client, focus_query=focus_query
                )
                if ocr_result.get("evidence"):
                    # MinerU already calls archiver inside
                    return ocr_result
            except Exception:
                if strategy == "ocr_only":
                    return {"status": "error", "message": "OCR service failed."}

        # 2. Local fast parse fallback
        # Reduce preview_chars significantly to avoid context bloat
        local_result = _read_pdf_locally_from_url(
            url=url, workspace_root=workspace_root, http_client=http_client,
            preview_chars=10000, fallback_used=True,
        )
        full_content = local_result.get("content") or ""
        
        # 3. UNIFIED ARCHIVING
        # Force the PDF text into the standard archiver to get a consistent Source ID
        archived = archiver.archive_raw(
            title=f"PDF: {filename_hint}",
            url=url,
            content=full_content,
            source_type="pdf_document"
        )
        
        # 4. DISTILLATION
        evidence = distill_evidence(model_backend, full_content, focus_query) if focus_query else full_content[:2000]
        
        note_path = ""
        if focus_query:
            note_path = archiver.archive_extract(archived["filename"], focus_query, evidence)
        
        # Final explicit index update to ensure snippets are high quality
        archiver.update_index({
            "title": f"PDF: {filename_hint}",
            "url": url,
            "raw_path": archived["raw_path"],
            "note_paths": [note_path] if note_path else [],
            "summary": f"[PDF Extract] {evidence[:350]}"
        })

        return {
            "status": "success",
            "url": url,
            "evidence": evidence,
            "raw_path": archived["raw_path"],
            "note_path": note_path,
            "system_note": "PDF processed via unified archiver. Full text preserved in raw_path."
        }

    registry.register(
        ToolDefinition(
            name="pdf_read_url",
            description="Read a PDF. Automatically archives text and indexes snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "focus_query": {"type": "string"},
                    "strategy": {"type": "string", "enum": ["local_only", "ocr_only", "hybrid"], "default": "hybrid"},
                },
                "required": ["url"],
            },
            handler=pdf_read_url,
        )
    )
