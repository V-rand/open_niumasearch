# Deep Research Agent — Agent Guide

> This file is written for AI coding agents. Read this first before making any changes.

## Project Overview

**Deep Research Agent** is a structured research system designed for long-horizon tasks (especially Legal Research). 

### Core Philosophy: **External Working Memory & Context Budgeting**
The agent does NOT keep long documents in its context. Instead, it follows a **"Locality First"** strategy:
1.  **High-Density Index**: All evidence is summarized in `research/source_index.md` (Source ID, Case No, Result).
2.  **Surgical Extraction**: Use `focus_query` to extract snippets into `notes/` instead of reading 100KB files.
3.  **Tactical Steering**: Tools like `fs_status` return a `system_note` to guide the agent (e.g., "Stop downloading, you have enough evidence").

---

## Directory Layout (Updated 2026-04-25)

```
.
├── src/deep_research_agent/
│   ├── agent.py                # ReActAgent runtime
│   ├── tools/
│   │   ├── __init__.py         # Unified tool registration
│   │   ├── archiver.py         # Standardized Archiver (OCR, Judicial Summary, History)
│   │   ├── fs.py               # fs_status, fs_list, fs_grep (Awareness tools)
│   │   ├── law_expert.py       # Professional legal retrieval (case_retrieve, etc.)
│   │   ├── pdf.py              # Token-budgeted PDF reader
│   │   ├── search.py           # Unified Search (auto-indexing top snippets)
│   │   └── web.py              # Web reader with pre-flight & gov.cn redirect logic
│   ├── retrieval_untils.py     # Backend for law retrieval
│   └── untils_case.py          # Judicial data structures
│
├── research/                   # The Evidence Library (Gitignored)
│   ├── raw/                    # Original MD/PDF text (Identifier: title_hash.md)
│   ├── notes/                  # Extracted evidence snippets
│   ├── search_history/         # JSON logs of all search queries
│   └── source_index.md         # The "Master Ledger" (Read this first!)
│
├── tests/
│   ├── test_core_robustness.py  # Archiver & Standardization tests
│   └── test_agent_dispatch.py  # ReAct loop & Tool routing tests
└── scripts/
    └── validate_infra.py       # Infrastructure health check
```

---

## Tool Chain (V2.1 Hardened)

| Tool | Capability | Budgeting/Resilience |
|------|------------|----------------------|
| `fs_status` | Returns evidence counts + Tactical Advice | **Awareness**: Prevents redundant downloads. |
| `case_retrieve` | Judicial case search by No./Cause | **Legal**: Auto-extracts "Result" to index. |
| `research_search` | Global discovery (Serper/Tavily) | **Auto-Index**: Top 3 snippets go to index. |
| `pdf_read_url` | PDF Text/OCR extraction | **Cap**: Max 2000 chars preview, full text archived. |
| `web_read` | Jina/Firecrawl web extraction | **Redirect**: Avoids gov.cn dead-ends. |
| `plan_*` | Atomic TODO management | **State**: Locks findings to Source IDs. |

---

## Development Workflow (Strict)

1.  **Harness First**: Before changing a tool, run `scripts/validate_infra.py`.
2.  **Source ID Protocol**: Every claim in a report MUST reference a Source ID from `source_index.md`.
3.  **Environment**: Ensure `UV_PROJECT_ENVIRONMENT` is set correctly. Currently transitioning from `agent_os4law` to `deep_research_agent` venv.

---

## Handover for Codex
- **Next Task**: The `source_index.md` is now the primary source of truth for planning.
- **Critical Fix**: PDF and Web tools now automatically call `archiver.archive_raw`. Don't implement private saving logic.
- **Risk**: The `.venv` path might need a `uv venv --clear` if you see import errors.
