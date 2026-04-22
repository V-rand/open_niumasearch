from __future__ import annotations

import json
import os
import re
import time
from hashlib import sha1
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from deep_research_agent.models import ToolExecutionResult


ToolHandler = Callable[[dict[str, Any]], ToolExecutionResult | str | dict[str, Any] | list[Any]]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def invoke(self, name: str, arguments: dict[str, Any], call_id: str | None = None) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=f"Unknown tool: {name}",
                is_error=True,
            )

        validation_error = self._validate(tool.parameters, arguments)
        if validation_error is not None:
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=validation_error,
                is_error=True,
            )

        try:
            result = tool.handler(arguments)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            return ToolExecutionResult(
                name=name,
                call_id=call_id,
                content=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )

        normalized = self._normalize_result(name=name, call_id=call_id, result=result)
        return normalized

    def _validate(self, schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            return f"Missing required arguments: {', '.join(missing)}"
        return None

    def _normalize_result(
        self,
        name: str,
        call_id: str | None,
        result: ToolExecutionResult | str | dict[str, Any] | list[Any],
    ) -> ToolExecutionResult:
        if isinstance(result, ToolExecutionResult):
            result.name = name
            result.call_id = call_id
            return result

        if isinstance(result, str):
            return ToolExecutionResult(name=name, call_id=call_id, content=result)

        return ToolExecutionResult(
            name=name,
            call_id=call_id,
            content=json.dumps(result, ensure_ascii=False, indent=2),
        )


def build_builtin_tools(
    workspace_root: Path,
    http_client: httpx.Client | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    workspace_root = Path(workspace_root).resolve()
    http_client = http_client or httpx.Client(timeout=60.0, trust_env=True)

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

    def fs_read(arguments: dict[str, Any]) -> str:
        path = resolve_path(arguments["path"])
        text = path.read_text(encoding="utf-8")

        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        if start_line is not None or end_line is not None:
            lines = text.splitlines()
            start = max(int(start_line or 1) - 1, 0)
            end = int(end_line) if end_line is not None else len(lines)
            text = "\n".join(lines[start:end])

        max_chars = arguments.get("max_chars")
        if max_chars is not None:
            text = text[: int(max_chars)]

        return text

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

    def web_search(arguments: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")

        payload = {
            "api_key": api_key,
            "query": arguments["query"],
            "search_depth": arguments.get("search_depth", "basic"),
            "topic": arguments.get("topic", "general"),
            "max_results": arguments.get("max_results", 5),
            "include_answer": arguments.get("include_answer", False),
            "include_raw_content": arguments.get("include_raw_content", False),
        }
        optional_fields = [
            "time_range",
            "start_date",
            "end_date",
            "include_domains",
            "exclude_domains",
            "country",
        ]
        for field_name in optional_fields:
            if field_name in arguments and arguments[field_name] is not None:
                payload[field_name] = arguments[field_name]

        response = http_client.post("https://api.tavily.com/search", json=payload)
        response.raise_for_status()
        data = response.json()

        return {
            "query": data.get("query", arguments["query"]),
            "answer": data.get("answer"),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                }
                for item in data.get("results", [])
            ],
        }

    def jina_reader(arguments: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("JINA_API_KEY")
        if not api_key:
            raise RuntimeError("JINA_API_KEY is not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Return-Format": arguments.get("return_format", "markdown"),
        }
        optional_headers = {
            "X-Engine": arguments.get("engine"),
            "X-Timeout": arguments.get("timeout"),
            "X-With-Links-Summary": arguments.get("with_links_summary"),
            "X-With-Images-Summary": arguments.get("with_images_summary"),
            "X-No-Cache": arguments.get("no_cache"),
            "X-Respond-With": arguments.get("respond_with"),
        }
        for key, value in optional_headers.items():
            if value is not None:
                headers[key] = str(value)

        body: dict[str, Any] = {"url": arguments["url"]}
        if "viewport" in arguments and arguments["viewport"] is not None:
            body["viewport"] = arguments["viewport"]

        response = http_client.post("https://r.jina.ai/", headers=headers, json=body)
        response.raise_for_status()
        data = response.json().get("data", {})
        return {
            "title": data.get("title"),
            "url": arguments["url"],
            "content": data.get("content", ""),
            "links": data.get("links", []),
            "images": data.get("images", []),
        }

    def mineru_parse_url(arguments: dict[str, Any]) -> dict[str, Any]:
        mode = arguments.get("mode", "lightweight")
        if mode == "lightweight":
            return _mineru_parse_url_lightweight(arguments=arguments, http_client=http_client)
        if mode == "precise":
            return _mineru_parse_url_precise(arguments=arguments, http_client=http_client)
        raise ValueError(f"Unsupported MinerU mode: {mode}")

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
        return {
            "query": arguments["query"],
            "results": results,
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

        return {
            **_serialize_arxiv_paper(paper),
            "pdf_path": str(pdf_path.relative_to(workspace_root)),
            "markdown_path": str(markdown_path.relative_to(workspace_root)),
            "markdown_preview": markdown[: int(arguments.get("preview_chars", 4000))],
        }

    def pdf_read_url(arguments: dict[str, Any]) -> dict[str, Any]:
        strategy = arguments.get("strategy", "local_only")
        if strategy == "mineru_only":
            mineru_result = _mineru_parse_url_lightweight(arguments=arguments, http_client=http_client)
            return _normalize_pdf_tool_result_from_mineru(
                url=arguments["url"],
                mineru_result=mineru_result,
                fallback_used=False,
            )

        if strategy == "local_only":
            return _read_pdf_locally_from_url(
                url=arguments["url"],
                workspace_root=workspace_root,
                http_client=http_client,
                preview_chars=int(arguments.get("preview_chars", 4000)),
                fallback_used=False,
            )

        mineru_result = _mineru_parse_url_lightweight(arguments=arguments, http_client=http_client)
        if mineru_result.get("state") == "done" and mineru_result.get("markdown"):
            return _normalize_pdf_tool_result_from_mineru(
                url=arguments["url"],
                mineru_result=mineru_result,
                fallback_used=False,
            )

        local_result = _read_pdf_locally_from_url(
            url=arguments["url"],
            workspace_root=workspace_root,
            http_client=http_client,
            preview_chars=int(arguments.get("preview_chars", 4000)),
            fallback_used=True,
        )
        local_result["mineru_error"] = mineru_result.get("error") or mineru_result.get("err_msg")
        local_result["mineru_state"] = mineru_result.get("state")
        return local_result

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
            description="Create, overwrite, or append to a text file in the workspace.",
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
            description="Patch an existing text file by replacing or inserting around a target string.",
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
    registry.register(
        ToolDefinition(
            name="web_search",
            description="Search the web with Tavily. Start broad, then narrow if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"]},
                    "topic": {"type": "string", "enum": ["general", "news", "finance"]},
                    "max_results": {"type": "integer"},
                    "include_answer": {"type": "boolean"},
                    "include_raw_content": {"type": "boolean"},
                    "time_range": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "include_domains": {"type": "array"},
                    "exclude_domains": {"type": "array"},
                    "country": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=web_search,
        )
    )
    registry.register(
        ToolDefinition(
            name="jina_reader",
            description="Read and extract an HTML web page with Jina Reader. Prefer this for normal web pages, not PDF/doc/ppt/image files. Use proxy-enabled shell when the network blocks jina.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "return_format": {"type": "string", "enum": ["markdown", "html", "text", "screenshot", "pageshot"]},
                    "engine": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "with_links_summary": {"type": "string"},
                    "with_images_summary": {"type": "string"},
                    "no_cache": {"type": "boolean"},
                    "respond_with": {"type": "string"},
                    "viewport": {"type": "object"},
                },
                "required": ["url"],
            },
            handler=jina_reader,
        )
    )
    registry.register(
        ToolDefinition(
            name="mineru_parse_url",
            description="Parse PDF, image, Doc/Docx, or PPT/PPTx URLs with MinerU. Prefer this over jina_reader for arXiv PDFs and other document files. Default mode is lightweight and returns parsed Markdown.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "mode": {"type": "string", "enum": ["lightweight", "precise"]},
                    "language": {"type": "string"},
                    "enable_table": {"type": "boolean"},
                    "enable_formula": {"type": "boolean"},
                    "is_ocr": {"type": "boolean"},
                    "page_range": {"type": "string"},
                    "poll_interval_seconds": {"type": "number"},
                    "max_polls": {"type": "integer"},
                    "model_version": {"type": "string", "enum": ["pipeline", "vlm", "MinerU-HTML"]},
                },
                "required": ["url"],
            },
            handler=mineru_parse_url,
        )
    )
    registry.register(
        ToolDefinition(
            name="arxiv_search",
            description="Search arXiv papers by query using the arXiv API. Use this instead of generic web search when the target is clearly an arXiv paper or topic.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                    "sort_by": {"type": "string", "enum": ["relevance", "last_updated", "submitted"]},
                    "sort_order": {"type": "string", "enum": ["ascending", "descending"]},
                },
                "required": ["query"],
            },
            handler=arxiv_search,
        )
    )
    registry.register(
        ToolDefinition(
            name="arxiv_read_paper",
            description="Read an arXiv paper by arXiv id, abs URL, or pdf URL. Downloads the PDF with arxiv.py, parses it with PyMuPDF4LLM, and writes the full Markdown into the current session workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "paper_ref": {"type": "string"},
                    "preview_chars": {"type": "integer"},
                },
                "required": ["paper_ref"],
            },
            handler=arxiv_read_paper,
        )
    )
    registry.register(
        ToolDefinition(
            name="pdf_read_url",
            description="Read a general PDF URL. Default strategy is local download plus PyMuPDF4LLM. Parsed files are written into the current session workspace. Use MinerU only when explicitly requested.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "strategy": {"type": "string", "enum": ["mineru_first", "mineru_only", "local_only"]},
                    "preview_chars": {"type": "integer"},
                    "language": {"type": "string"},
                    "enable_table": {"type": "boolean"},
                    "enable_formula": {"type": "boolean"},
                    "is_ocr": {"type": "boolean"},
                    "page_range": {"type": "string"},
                },
                "required": ["url"],
            },
            handler=pdf_read_url,
        )
    )
    return registry


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


def _mineru_parse_url_lightweight(arguments: dict[str, Any], http_client: httpx.Client) -> dict[str, Any]:
    submit_payload: dict[str, Any] = {"url": arguments["url"]}
    optional_fields = ["language", "enable_table", "enable_formula", "is_ocr", "page_range"]
    for field_name in optional_fields:
        if field_name in arguments and arguments[field_name] is not None:
            submit_payload[field_name] = arguments[field_name]

    submit_response = http_client.post("https://mineru.net/api/v1/agent/parse/url", json=submit_payload)
    submit_response.raise_for_status()
    submit_data = submit_response.json()
    task_id = submit_data.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"MinerU lightweight submit failed: {submit_data}")

    poll_result = _poll_mineru_task(
        http_client=http_client,
        poll_url=f"https://mineru.net/api/v1/agent/parse/{task_id}",
        poll_interval_seconds=float(arguments.get("poll_interval_seconds", 2)),
        max_polls=int(arguments.get("max_polls", 30)),
    )

    state = poll_result.get("state")
    if state != "done":
        return {
            "mode": "lightweight",
            "source_url": arguments["url"],
            "task_id": task_id,
            "state": state,
            "error": poll_result.get("error") or poll_result.get("err_msg"),
        }

    markdown_url = poll_result.get("markdown_url")
    if not markdown_url:
        raise RuntimeError(f"MinerU lightweight parse completed without markdown_url: {poll_result}")

    markdown_response = http_client.get(markdown_url)
    markdown_response.raise_for_status()
    return {
        "mode": "lightweight",
        "source_url": arguments["url"],
        "task_id": task_id,
        "state": state,
        "markdown_url": markdown_url,
        "markdown": markdown_response.text,
    }


def _mineru_parse_url_precise(arguments: dict[str, Any], http_client: httpx.Client) -> dict[str, Any]:
    api_key = os.getenv("MinerU_API_KEY") or os.getenv("MINERU_API_KEY")
    if not api_key:
        raise RuntimeError("MinerU_API_KEY or MINERU_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    submit_payload: dict[str, Any] = {
        "url": arguments["url"],
        "model_version": arguments.get("model_version", "vlm"),
    }
    optional_fields = [
        "language",
        "enable_table",
        "enable_formula",
        "is_ocr",
        "page_range",
    ]
    for field_name in optional_fields:
        if field_name in arguments and arguments[field_name] is not None:
            submit_payload[field_name] = arguments[field_name]

    submit_response = http_client.post("https://mineru.net/api/v4/extract/task", json=submit_payload, headers=headers)
    submit_response.raise_for_status()
    submit_data = submit_response.json()
    task_id = submit_data.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"MinerU precise submit failed: {submit_data}")

    poll_result = _poll_mineru_task(
        http_client=http_client,
        poll_url=f"https://mineru.net/api/v4/extract/task/{task_id}",
        poll_interval_seconds=float(arguments.get("poll_interval_seconds", 2)),
        max_polls=int(arguments.get("max_polls", 30)),
        headers=headers,
    )
    return {
        "mode": "precise",
        "source_url": arguments["url"],
        "task_id": task_id,
        "state": poll_result.get("state"),
        "full_zip_url": poll_result.get("full_zip_url"),
        "error": poll_result.get("error") or poll_result.get("err_msg"),
        "note": "Precise mode currently returns the result zip URL and task state. Lightweight mode returns inline Markdown.",
    }


def _poll_mineru_task(
    *,
    http_client: httpx.Client,
    poll_url: str,
    poll_interval_seconds: float,
    max_polls: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    last_data: dict[str, Any] = {}
    for poll_index in range(max_polls):
        response = http_client.get(poll_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        last_data = data
        state = data.get("state")
        if state in {"done", "failed"}:
            return data
        if poll_index < max_polls - 1 and poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)
    return {
        **last_data,
        "state": last_data.get("state", "timeout"),
        "error": "MinerU polling exceeded max_polls",
    }


def _import_arxiv():
    try:
        import arxiv  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency path
        raise RuntimeError("arxiv is not installed. Add it to the environment before using arXiv tools.") from exc
    return arxiv


def _import_pymupdf4llm():
    try:
        import pymupdf4llm  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency path
        raise RuntimeError("pymupdf4llm is not installed. Add it to the environment before using arXiv PDF parsing.") from exc
    return pymupdf4llm


def _normalize_arxiv_paper_ref(paper_ref: str) -> str:
    value = paper_ref.strip()
    patterns = [
        r"arxiv\.org/abs/([^/?#]+)",
        r"arxiv\.org/pdf/([^/?#]+?)(?:\.pdf)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return _strip_arxiv_version(match.group(1))
    return _strip_arxiv_version(value)


def _strip_arxiv_version(paper_id: str) -> str:
    return re.sub(r"v\d+$", "", paper_id)


def _resolve_arxiv_sort(arxiv_module: Any, value: str) -> Any:
    mapping = {
        "relevance": arxiv_module.SortCriterion.Relevance,
        "last_updated": arxiv_module.SortCriterion.LastUpdatedDate,
        "submitted": arxiv_module.SortCriterion.SubmittedDate,
    }
    return mapping[value]


def _resolve_arxiv_order(arxiv_module: Any, value: str) -> Any:
    mapping = {
        "ascending": arxiv_module.SortOrder.Ascending,
        "descending": arxiv_module.SortOrder.Descending,
    }
    return mapping[value]


def _serialize_arxiv_paper(paper: Any) -> dict[str, Any]:
    authors = []
    for author in getattr(paper, "authors", []):
        name = getattr(author, "name", author)
        authors.append(str(name))

    return {
        "paper_id": _normalize_arxiv_paper_ref(getattr(paper, "entry_id", "").split("/")[-1]),
        "entry_id": getattr(paper, "entry_id", None),
        "title": getattr(paper, "title", None),
        "summary": getattr(paper, "summary", None),
        "pdf_url": getattr(paper, "pdf_url", None),
        "published": str(getattr(paper, "published", "")) if getattr(paper, "published", None) is not None else None,
        "updated": str(getattr(paper, "updated", "")) if getattr(paper, "updated", None) is not None else None,
        "authors": authors,
    }


def _normalize_pdf_tool_result_from_mineru(
    *,
    url: str,
    mineru_result: dict[str, Any],
    fallback_used: bool,
) -> dict[str, Any]:
    return {
        "source_url": url,
        "method": "mineru",
        "fallback_used": fallback_used,
        "state": mineru_result.get("state"),
        "markdown_url": mineru_result.get("markdown_url"),
        "markdown_preview": (mineru_result.get("markdown") or "")[:4000],
    }


def _read_pdf_locally_from_url(
    *,
    url: str,
    workspace_root: Path,
    http_client: httpx.Client,
    preview_chars: int,
    fallback_used: bool,
) -> dict[str, Any]:
    pdf_path = _download_pdf_to_workspace(
        url=url,
        workspace_root=workspace_root,
        http_client=http_client,
    )
    pymupdf4llm = _import_pymupdf4llm()
    markdown = pymupdf4llm.to_markdown(str(pdf_path))
    markdown_path = pdf_path.with_suffix(".md")
    markdown_path.write_text(markdown, encoding="utf-8")
    return {
        "source_url": url,
        "method": "local_pymupdf4llm",
        "fallback_used": fallback_used,
        "pdf_path": str(pdf_path.relative_to(workspace_root)),
        "markdown_path": str(markdown_path.relative_to(workspace_root)),
        "markdown_preview": markdown[:preview_chars],
    }


def _download_pdf_to_workspace(
    *,
    url: str,
    workspace_root: Path,
    http_client: httpx.Client,
    filename_hint: str | None = None,
) -> Path:
    response = http_client.get(url, follow_redirects=True)
    response.raise_for_status()
    pdf_dir = _document_store_dir(workspace_root)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_hint or _suggest_pdf_filename(url)
    pdf_path = pdf_dir / filename
    pdf_path.write_bytes(response.content)
    return pdf_path


def _document_store_dir(workspace_root: Path) -> Path:
    return workspace_root / "documents"


def _suggest_pdf_filename(url: str) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path).name or "document.pdf"
    if not candidate.endswith(".pdf"):
        digest = sha1(url.encode("utf-8")).hexdigest()[:12]
        candidate = f"{candidate or 'document'}_{digest}.pdf"
    return candidate
