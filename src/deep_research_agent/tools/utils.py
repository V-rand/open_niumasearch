from __future__ import annotations

import json
import os
import re
import time
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

# --- Internal Constants ---
def _raw_store_dir(workspace_root: Path) -> Path:
    return workspace_root / "research" / "raw"

def _document_store_dir(workspace_root: Path) -> Path:
    return workspace_root / "documents"

def _source_index_path(workspace_root: Path) -> Path:
    return workspace_root / "research" / "source_index.md"

# --- Import Helpers ---
def _import_arxiv() -> Any:
    try:
        import arxiv
        return arxiv
    except ImportError:
        raise ImportError("arxiv library is missing. Install with 'uv add arxiv' or 'pip install arxiv'.")

def _import_pymupdf4llm() -> Any:
    try:
        import pymupdf4llm
        return pymupdf4llm
    except ImportError:
        raise ImportError("pymupdf4llm library is missing. Install with 'uv add pymupdf4llm' or 'pip install pymupdf4llm'.")

# --- ArXiv Specific Helpers ---
def _resolve_arxiv_sort(arxiv: Any, value: str) -> Any:
    mapping = {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
        "last_updated": arxiv.SortCriterion.LastUpdatedDate,
        "submitted": arxiv.SortCriterion.SubmittedDate,
    }
    return mapping.get(value, arxiv.SortCriterion.Relevance)

def _resolve_arxiv_order(arxiv: Any, value: str) -> Any:
    mapping = {
        "ascending": arxiv.SortOrder.Ascending,
        "descending": arxiv.SortOrder.Descending,
    }
    return mapping.get(value, arxiv.SortOrder.Descending)

def _normalize_arxiv_paper_ref(ref: str) -> str:
    value = ref.strip()
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

# --- Shared UI/Display Helpers ---
def _render_raw_source_markdown(*, title: str, url: str, source_type: str, content: str) -> str:
    return (
        f"# {title}\n\n"
        f"- title: {title}\n"
        f"- url: {url}\n"
        f"- type: {source_type}\n\n"
        "## Raw Content\n\n"
        f"{content.strip()}\n"
    )

def _next_available_raw_path(*, raw_dir: Path, title: str) -> Path:
    stem = _sanitize_filename(title) or "source"
    candidate = raw_dir / f"{stem}.md"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = raw_dir / f"{stem}-{suffix}.md"
        if not candidate.exists():
            return candidate
        suffix += 1

def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120].rstrip(" .")

def _slugify_title(title: str) -> str:
    cleaned = _sanitize_filename(title).lower()
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", cleaned).strip("-")
    return slug or "source"

def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).stem.strip()
    return name or parsed.netloc or "source"

def _summarize_source_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return ""
    sentence = compact.split(". ", 1)[0]
    sentence = sentence.split("。", 1)[0]
    summary = sentence.strip()
    if len(summary) > 220:
        return summary[:217].rstrip() + "..."
    return summary or compact[:220]

def _judgment_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    high_markers = ("nature.com", "science.org", "arxiv.org", ".gov", ".edu", "openai.com", "mit.edu")
    if any(marker in host for marker in high_markers):
        return "high"
    medium_markers = ("wikipedia.org", "pubmed.ncbi.nlm.nih.gov", "biorxiv.org")
    if any(marker in host for marker in medium_markers):
        return "medium"
    return "medium"

def _resolve_firecrawl_api_key() -> str | None:
    return (
        os.getenv("FIRECRAWL_API_KEY")
        or os.getenv("firecraw_api_key")
    )

def _find_existing_raw_source(workspace_root: Path, url: str) -> dict[str, str] | None:
    index_path = _source_index_path(workspace_root)
    if not index_path.exists():
        return None

    content = index_path.read_text(encoding="utf-8")
    blocks = re.split(r'\n---|\n# ', content)
    for block in blocks:
        if url in block:
            path_match = re.search(r'raw_path:\s*(research/raw/[^\s\n]+)', block)
            title_match = re.search(r'title:\s*(.*)', block)
            if path_match:
                raw_path = path_match.group(1).strip()
                full_path = workspace_root / raw_path
                if full_path.exists():
                    return {
                        "raw_path": raw_path,
                        "title": title_match.group(1).strip() if title_match else "Unknown"
                    }
    return None

def _firecrawl_scrape_fallback(
    *,
    workspace_root: Path,
    url: str,
    firecrawl_api_key: str,
    http_client: httpx.Client,
    jina_error: Exception,
) -> dict[str, Any]:
    response = http_client.post(
        "https://api.firecrawl.dev/v2/scrape",
        headers={
            "Authorization": f"Bearer {firecrawl_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        },
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload)
    content = data.get("markdown") or ""
    title = data.get("metadata", {}).get("title") or data.get("title")
    archived = _archive_source_content(
        workspace_root=workspace_root,
        title=title or url,
        url=url,
        content=content,
        source_type="web",
        summary_hint=content,
    )
    return {
        "title": title,
        "url": url,
        "content": content,
        "links": data.get("links", []),
        "images": data.get("images", []),
        "provider": "firecrawl_fallback",
        "fallback_reason": f"{type(jina_error).__name__}: {jina_error}",
        **archived,
    }

def _archive_search_results(
    *,
    workspace_root: Path,
    query: str,
    results: list[dict[str, Any]],
    provider: str,
) -> Path:
    history_dir = workspace_root / "research" / "search_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    digest = sha1(query.encode("utf-8")).hexdigest()[:8]
    filename = f"{timestamp}_{provider}_{digest}.json"
    file_path = history_dir / filename
    
    payload = {
        "timestamp": timestamp,
        "query": query,
        "provider": provider,
        "results": results
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path

def _trafilatura_fallback(url: str) -> str:
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded) or ""
    except Exception:
        return ""

def _upsert_leads(*, workspace_root: Path, entry: dict[str, Any]) -> None:
    leads_path = _leads_path(workspace_root)
    leads_path.parent.mkdir(parents=True, exist_ok=True)

    content = ""
    if leads_path.exists():
        content = leads_path.read_text(encoding="utf-8")
        if entry["url"] in content:
            return

    title = entry.get("title", "Untitled")
    url = entry.get("url", "")
    summary = entry.get("summary", "")
    why_keep = entry.get("why_keep", "")

    new_entry = f"### {title}\n- **URL**: {url}\n- **Summary**: {summary}\n"
    if why_keep:
        new_entry += f"- **Reason**: {why_keep}\n"
    new_entry += "- **Status**: `[Unread]`\n\n"

    with leads_path.open("a", encoding="utf-8") as f:
        if not content:
            f.write("# Research Leads\n\n")
        f.write(new_entry)

def _keep_selected_search_results(
    *,
    workspace_root: Path,
    results: list[dict[str, Any]],
    selected_indices: Any,
    keep_reason: Any,
) -> list[dict[str, Any]]:
    if not isinstance(selected_indices, list) or not selected_indices:
        return []

    kept_sources: list[dict[str, Any]] = []
    for raw_index in selected_indices:
        try:
            index = int(raw_index) - 1
        except (ValueError, TypeError):
            continue
            
        if index < 0 or index >= len(results):
            continue
            
        item = results[index]
        url = item.get("url") or item.get("entry_id") or item.get("source_url") or item.get("pdf_url") or ""
        title = item.get("title") or _title_from_url(url)
        summary = _summarize_source_text(item.get("content") or item.get("summary") or "")
        entry = _build_source_entry(
            title=title,
            url=url,
            summary=summary,
            judgment=_judgment_for_url(url),
            raw_path="pending",
            note_paths=[],
            why_keep=str(keep_reason or ""),
        )
        _upsert_leads(workspace_root=workspace_root, entry=entry)
        kept_sources.append(
            {
                "index": index + 1,
                "title": title,
                "url": url,
                "summary": summary,
            }
        )
    return kept_sources

def _archive_distilled_evidence(
    *,
    workspace_root: Path,
    source_id: str,
    focus_query: str,
    evidence: str,
) -> str:
    notes_dir = workspace_root / "research" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    
    # Filename is linked to the source_id
    note_path = notes_dir / f"{source_id}_extracts.md"
    
    entry = f"## Intent: {focus_query}\n\n{evidence}\n\n---\n"
    
    with note_path.open("a", encoding="utf-8") as f:
        if note_path.stat().st_size == 0:
            f.write(f"# Evidence Extracts for {source_id}\n\n")
        f.write(entry)
        
    return str(note_path.relative_to(workspace_root))

def _archive_source_content(
    *,
    workspace_root: Path,
    title: str,
    url: str,
    content: str,
    source_type: str,
    summary_hint: str | None,
) -> dict[str, Any]:
    source_title = title.strip() or _title_from_url(url)
    source_id = _slugify_title(source_title)
    raw_dir = _raw_store_dir(workspace_root)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = _next_available_raw_path(raw_dir=raw_dir, title=source_title)
    raw_relative_path = str(raw_path.relative_to(workspace_root))
    raw_content = _render_raw_source_markdown(
        title=source_title,
        url=url,
        source_type=source_type,
        content=content,
    )
    raw_path.write_text(raw_content, encoding="utf-8")

    entry = _build_source_entry(
        title=source_title,
        url=url,
        summary=_summarize_source_text(summary_hint or content),
        judgment=_judgment_for_url(url),
        raw_path=raw_relative_path,
        note_paths=[], # This will be updated later by distiller
        why_keep="",
    )
    _upsert_source_index(workspace_root=workspace_root, entry=entry)
    return {
        "source_id": source_id,
        "raw_path": raw_relative_path,
        "source_index_updated": True,
    }

def _build_source_entry(
    *,
    title: str,
    url: str,
    summary: str,
    judgment: str,
    raw_path: str,
    note_paths: list[str],
    why_keep: str,
) -> dict[str, Any]:
    return {
        "source_id": _slugify_title(title),
        "title": title,
        "url": url,
        "summary": summary,
        "judgment": judgment,
        "raw_path": raw_path,
        "note_paths": note_paths,
        "why_keep": why_keep,
    }

def _upsert_source_index(*, workspace_root: Path, entry: dict[str, Any]) -> None:
    index_path = _source_index_path(workspace_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _parse_source_index(index_path.read_text(encoding="utf-8")) if index_path.exists() else []

    replaced = False
    for index, existing in enumerate(entries):
        if existing.get("url") == entry["url"]:
            merged = dict(existing)
            # Update only non-empty/non-pending fields
            for k, v in entry.items():
                is_empty = (v == "" or v == [] or v == "pending")
                if not is_empty:
                    merged[k] = v
            
            if existing.get("raw_path") and entry.get("raw_path") == "pending":
                merged["raw_path"] = existing["raw_path"]
            if existing.get("why_keep") and not entry.get("why_keep"):
                merged["why_keep"] = existing["why_keep"]
            if existing.get("note_paths"):
                # Handle potential overlaps in note_paths
                existing_notes = set(existing.get("note_paths", []))
                new_notes = entry.get("note_paths", [])
                merged["note_paths"] = sorted(list(existing_notes.union(set(new_notes))))
            
            entries[index] = merged
            replaced = True
            break

    if not replaced:
        entries.append(entry)

    index_path.write_text(_render_source_index(entries), encoding="utf-8")

def _parse_source_index(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    blocks = re.split(r"^### ", text, flags=re.MULTILINE)
    entries: list[dict[str, Any]] = []
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        entry: dict[str, Any] = {"title": title, "note_paths": []}
        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line.startswith("- "):
                continue
            key, _, value = line[2:].partition(":")
            normalized_key = key.strip().replace(" ", "_")
            normalized_value = value.strip()
            if normalized_key == "note_paths":
                entry["note_paths"] = [] if normalized_value in {"", "-"} else [item.strip() for item in normalized_value.split(",")]
            else:
                entry[normalized_key] = normalized_value
        entries.append(entry)
    return entries

def _render_source_index(entries: list[dict[str, Any]]) -> str:
    lines = ["# Source Index", ""]
    for entry in entries:
        note_paths = ", ".join(entry.get("note_paths", [])) or "-"
        lines.extend(
            [
                f"### {entry.get('title', 'Untitled Source')}",
                f"- url: {entry.get('url', '')}",
                f"- summary: {entry.get('summary', '')}",
                f"- judgment: {entry.get('judgment', 'medium')}",
                f"- raw_path: {entry.get('raw_path', 'pending')}",
                f"- note_paths: {note_paths}",
            ]
        )
        why_keep = entry.get("why_keep", "")
        if why_keep:
            lines.append(f"- why_keep: {why_keep}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

# --- MinerU Specific Helpers ---
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

# --- PDF Specific Helpers ---
def _suggest_pdf_filename(url: str) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path).name or "document.pdf"
    if not candidate.endswith(".pdf"):
        digest = sha1(url.encode("utf-8")).hexdigest()[:12]
        candidate = f"{candidate or 'document'}_{digest}.pdf"
    return candidate

def _download_pdf_to_workspace(
    *,
    url: str,
    workspace_root: Path,
    http_client: httpx.Client,
    filename_hint: str | None = None,
) -> Path:
    token_url = url.split("?")[0]
    response = http_client.get(url, follow_redirects=True)
    response.raise_for_status()
    pdf_dir = _document_store_dir(workspace_root)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_hint or _suggest_pdf_filename(token_url)
    pdf_path = pdf_dir / filename
    pdf_path.write_bytes(response.content)
    return pdf_path

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
    archived = _archive_source_content(
        workspace_root=workspace_root,
        title=_title_from_url(url),
        url=url,
        content=markdown,
        source_type="pdf",
        summary_hint=markdown,
    )
    return {
        "source_url": url,
        "method": "local_pymupdf4llm",
        "fallback_used": fallback_used,
        "pdf_path": str(pdf_path.relative_to(workspace_root)),
        "markdown_path": str(markdown_path.relative_to(workspace_root)),
        "markdown_preview": markdown[:preview_chars],
        **archived,
    }

def _normalize_pdf_tool_result_from_mineru(
    *,
    workspace_root: Path,
    url: str,
    mineru_result: dict[str, Any],
    fallback_used: bool,
) -> dict[str, Any]:
    archived = _archive_source_content(
        workspace_root=workspace_root,
        title=_title_from_url(url),
        url=url,
        content=mineru_result.get("markdown") or "",
        source_type="pdf",
        summary_hint=mineru_result.get("markdown") or "",
    )
    return {
        "source_url": url,
        "method": "mineru",
        "fallback_used": fallback_used,
        "state": mineru_result.get("state"),
        "markdown_url": mineru_result.get("markdown_url"),
        "markdown_preview": (mineru_result.get("markdown") or "")[:4000],
        **archived,
    }
