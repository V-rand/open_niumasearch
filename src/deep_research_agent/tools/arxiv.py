from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.tools.base import ToolDefinition, ToolRegistry
from deep_research_agent.tools.utils import (
    _archive_source_content,
    _document_store_dir,
    _import_arxiv,
    _import_pymupdf4llm,
    _keep_selected_search_results,
    _normalize_arxiv_paper_ref,
    _resolve_arxiv_order,
    _resolve_arxiv_sort,
    _serialize_arxiv_paper,
)


def register_arxiv_tools(
    registry: ToolRegistry,
    workspace_root: Path,
) -> None:
    def arxiv_search(arguments: dict[str, Any]) -> dict[str, Any]:
        arxiv = _import_arxiv()
        search = arxiv.Search(
            query=arguments["query"],
            max_results=int(arguments.get("max_results", 5)),
            sort_by=_resolve_arxiv_sort(arxiv, arguments.get("sort_by", "relevance")),
            sort_order=_resolve_arxiv_order(arxiv, arguments.get("sort_order", "descending")),
        )
        client = arxiv.Client()
        results = []
        for paper in client.results(search):
            results.append(_serialize_arxiv_paper(paper))
        kept_sources = _keep_selected_search_results(
            workspace_root=workspace_root,
            results=results,
            selected_indices=arguments.get("keep_result_indices"),
            keep_reason=arguments.get("keep_reason"),
        )
        return {
            "query": arguments["query"],
            "results": results,
            "kept_sources": kept_sources,
        }

    def arxiv_read_paper(arguments: dict[str, Any]) -> dict[str, Any]:
        arxiv = _import_arxiv()
        pymupdf4llm = _import_pymupdf4llm()

        paper_id = _normalize_arxiv_paper_ref(arguments["paper_ref"])
        search = arxiv.Search(id_list=[paper_id])
        client = arxiv.Client()
        try:
            paper = next(client.results(search))
        except StopIteration as exc:
            raise RuntimeError(f"Could not find arXiv paper: {paper_id}") from exc

        document_dir = _document_store_dir(workspace_root)
        document_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = Path(
            paper.download_pdf(
                dirpath=str(document_dir),
                filename=f"{paper_id}.pdf",
            )
        )
        markdown = pymupdf4llm.to_markdown(str(pdf_path))
        markdown_path = document_dir / f"{paper_id}.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        archived = _archive_source_content(
            workspace_root=workspace_root,
            title=getattr(paper, "title", None) or paper_id,
            url=getattr(paper, "entry_id", None) or arguments["paper_ref"],
            content=markdown,
            source_type="paper",
            summary_hint=getattr(paper, "summary", None),
        )

        return {
            **_serialize_arxiv_paper(paper),
            "pdf_path": str(pdf_path.relative_to(workspace_root)),
            "markdown_path": str(markdown_path.relative_to(workspace_root)),
            "markdown_preview": markdown[: int(arguments.get("preview_chars", 4000))],
            **archived,
        }

    registry.register(
        ToolDefinition(
            name="arxiv_search",
            description="Search for papers on arXiv.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                    "sort_by": {"type": "string", "enum": ["relevance", "lastUpdatedDate", "submittedDate"]},
                    "sort_order": {"type": "string", "enum": ["ascending", "descending"]},
                    "keep_result_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices (1-based) of search results to keep in research/leads.md.",
                    },
                    "keep_reason": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=arxiv_search,
        )
    )
    registry.register(
        ToolDefinition(
            name="arxiv_read_paper",
            description="Download and read an arXiv paper as Markdown.",
            parameters={
                "type": "object",
                "properties": {
                    "paper_ref": {"type": "string", "description": "arXiv ID or URL."},
                    "preview_chars": {"type": "integer", "default": 4000},
                },
                "required": ["paper_ref"],
            },
            handler=arxiv_read_paper,
        )
    )
