from __future__ import annotations

import json
import re
import time
import threading
import logging
from pathlib import Path
from typing import Any
from hashlib import sha1

logger = logging.getLogger(__name__)

class ResearchArchiver:
    _lock = threading.Lock()

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root).resolve()
        self.raw_dir = self.root / "research" / "raw"
        self.notes_dir = self.root / "research" / "notes"
        self.history_dir = self.root / "research" / "search_history"
        self.index_path = self.root / "research" / "source_index.md"
        
        for d in [self.raw_dir, self.notes_dir, self.history_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _auto_summarize(self, content: str, source_type: str) -> str:
        """Heuristic extraction of a summary from raw legal/web content."""
        if not content: return "Empty source."
        
        if source_type == "judicial_case":
            case_no_match = re.search(r"（\d{4}）[\u4e00-\u9fa5]+\d+号", content)
            case_no = case_no_match.group(0) if case_no_match else "Unknown CaseNo"
            res_match = re.search(r"(判决如下|裁判结果|本院认为).*?([\u4e00-\u9fa5\w]{10,300})", content, re.S)
            res_text = res_match.group(0).replace("\n", " ").strip() if res_match else "Result details in file."
            return f"[{case_no}] {res_text[:350]}..."
            
        if source_type == "legal_regulation":
            article_match = re.search(r"(第一条|前言).*?([\u4e00-\u9fa5]{10,250})", content, re.S)
            if article_match:
                return article_match.group(0).replace("\n", " ").strip()[:250]
            
        return content[:200].replace("\n", " ").strip() + "..."

    def archive_raw(self, title: str, url: str, content: str, source_type: str, summary: str | None = None) -> dict[str, str]:
        """The standard way to persist raw evidence."""
        url_hash = sha1(url.encode()).hexdigest()[:8]
        slug = re.sub(r"[^\w\-_]", "_", title.strip())[:50]
        filename = f"{slug}_{url_hash}.md"
        file_path = self.raw_dir / filename
        
        is_new = not file_path.exists()
        if is_new:
            full_md = f"# {title}\n- **URL**: {url}\n- **Type**: {source_type}\n- **Archived**: {time.ctime()}\n\n---\n\n{content}"
            file_path.write_text(full_md, encoding="utf-8")
        
        raw_path = str(file_path.relative_to(self.root))
        final_summary = summary or self._auto_summarize(content, source_type)
        
        self.update_index({
            "title": title,
            "url": url,
            "raw_path": raw_path,
            "summary": final_summary
        })
        
        return {
            "raw_path": raw_path, 
            "filename": filename, 
            "id": filename, 
            "is_new": is_new,
            "system_note": f"Source locked as {filename}. Refer to source_index.md."
        }

    def archive_history(self, query: str, results: list[dict[str, Any]], provider: str) -> str:
        """The standard way to persist search/action history."""
        timestamp = int(time.time())
        query_hash = sha1(query.encode()).hexdigest()[:8]
        filename = f"{timestamp}_{query_hash}.json"
        file_path = self.history_dir / filename
        
        data = {
            "query": query,
            "timestamp": time.ctime(),
            "provider": provider,
            "results": results
        }
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(file_path.relative_to(self.root))

    def archive_extract(self, source_id: str, query: str, evidence: str) -> str:
        safe_id = re.sub(r"[^\w\-_]", "_", source_id)
        note_path = self.notes_dir / f"{safe_id}_extracts.md"
        entry = f"## Intent: {query}\n\n{evidence}\n\n---\n"
        
        with self._lock:
            with note_path.open("a", encoding="utf-8") as f:
                if note_path.stat().st_size == 0:
                    f.write(f"# Evidence Extracts for {source_id}\n\n")
                f.write(entry)
        return str(note_path.relative_to(self.root))

    def update_index(self, entry: dict[str, Any]):
        with self._lock:
            content = self.index_path.read_text(encoding="utf-8") if self.index_path.exists() else "# Source Index\n\n"
            entries = self._parse_index(content)
            
            replaced = False
            key = entry.get("url") or entry.get("raw_path")
            
            for i, existing in enumerate(entries):
                if existing.get("url") == key or existing.get("raw_path") == key:
                    for k, v in entry.items():
                        # Only update if the new value is informative
                        if v and v not in {"pending", "Automatically archived source."}:
                            existing[k] = v
                    entries[i] = existing
                    replaced = True
                    break
            
            if not replaced:
                entries.append(entry)
                
            self.index_path.write_text(self._render_index(entries), encoding="utf-8")

    def _parse_index(self, text: str) -> list[dict[str, Any]]:
        blocks = re.split(r"\n### ", "\n" + text.strip())
        entries = []
        for block in blocks:
            if not block.strip() or block.strip() == "# Source Index": continue
            lines = block.splitlines()
            if not lines: continue
            
            item = {"title": lines[0].strip(), "note_paths": []}
            for line in lines[1:]:
                clean_line = line.strip()
                if not clean_line.startswith("- "): continue
                k, _, v = clean_line[2:].partition(":")
                key = k.strip().replace(" ", "_")
                val = v.strip()
                if key == "note_paths":
                    item["note_paths"] = [] if val in {"", "-"} else [x.strip() for x in val.split(",")]
                else:
                    item[key] = val
            entries.append(item)
        return entries

    def _render_index(self, entries: list[dict[str, Any]]) -> str:
        lines = ["# Source Index", ""]
        sorted_entries = sorted(entries, key=lambda x: x.get("title", ""))
        for e in sorted_entries:
            notes = ", ".join(e.get("note_paths", [])) or "-"
            lines.extend([
                f"### {e.get('title', 'Untitled')}",
                f"- url: {e.get('url', '')}",
                f"- raw_path: {e.get('raw_path', 'pending')}",
                f"- note_paths: {notes}",
                f"- summary: {str(e.get('summary', ''))[:400].replace('\n', ' ')}",
                ""
            ])
        return "\n".join(lines)
