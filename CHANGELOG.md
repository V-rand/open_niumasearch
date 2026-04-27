# Changelog - Deep Research Agent 2.0 Upgrade

## [2.1.1] - 2026-04-27

### 🧹 Single-Agent Cleanup
- **Removed stale multi-agent test suite**: deleted `tests/test_multi_agent.py` to align with current single-agent architecture.
- **Removed read-only evaluator helper export**: dropped `build_readonly_tools` from `src/deep_research_agent/tools/__init__.py` because evaluator flow is no longer part of the runtime design.

### 🔒 Workspace Hygiene
- Updated `.gitignore` to ignore `token_cache.json` and `infra_test_workspace/` runtime artifacts.

## [2.1.0] - 2026-04-25

### 🛡️ Infrastructure Hardening (工业级加固)
- **Unified Archiving Protocol**: Heavily refactored `ResearchArchiver`. All tools now use a single entry point for data persistence, ensuring consistent hashing and Source ID naming.
- **Source Indexing 2.0**: The `source_index.md` is now a high-density summary store. It automatically captures "Case Numbers" and "Judgment Results" from judicial documents.
- **Search Auto-Indexing**: `research_search` now automatically injects the top 3 snippets into the index, reducing the need for redundant `web_read` calls.

### 🧠 Agent Awareness & Context Control
- **Evidence Dashboard**: Added `fs_status` tool. It provides a real-time radar of the evidence library and issues "Tactical Advice" via `system_note` to prevent token bloat.
- **PDF/Web Budgeting**: Hardened `pdf_read_url` and `web_read` to enforce a strict character cap on initial previews (2000 chars), pushing full-text analysis to offline extraction.
- **Principle Injection**: Updated `system.md` with "Locality First" and "Context Budgeting" mandates.

### ⚖️ Legal Specialist Suite
- **Judicial Retrieval**: Integrated `case_retrieve` and `cause_retrieve` for professional legal research.
- **Gov.cn Resilience**: Added failure redirection for government domains. The system now guides the agent to seek mirrors/news sources upon network blockage.

### ✅ Validation & Quality
- **Added `scripts/validate_infra.py`**: A health check script for the new archiver and tool registry.
- **Added `tests/test_core_robustness.py`**: Verifies that tool outputs are correctly indexed and hashed.

## [2.0.0] - 2026-04-25

### 🧠 Smart Research (战略驱动)
- **High-Fidelity Distillation**: Integrated `distiller.py`. Tools like `jina_reader`, `ocr_parse`, and `pdf_read_url` now support `focus_query`, allowing a sub-agent to extract relevant evidence snippets without overflowing the main context.
- **Strategic Planning Tools**: Replaced manual `todo.md` management with atomic tools: `plan_decompose`, `plan_view`, and `plan_mark_progress`.
- **System-Assisted Memory**: Automated the "Fact-to-Plan" loop. System prompts and `system_note` feedback now guide the agent to lock findings into the Research Plan.

### 📂 File System & Archiving (物理级归档)
- **ResearchArchiver**: A unified class for handling raw downloads, evidence notes, and source indexing.
- **Global Awareness Tools**: 
  - `fs_status`: Provides a high-level radar view of the workspace.
  - `fs_grep`: Global keyword search across local archives.
  - `fs_outline`: Structure extraction for long Markdown documents.
- **Passive Archiving**: Every search and read operation now silently saves a local copy for accountability and future re-reading.

### 🛡️ Hardening & Bug Fixes
- **JSON Robustness**: Fixed tool argument parsing for DashScope (Qwen) API.
- **Parallel Safety**: Re-implemented parallel tool execution with URL deduplication.
- **Type Safety**: Resolved `TypeError: unhashable type: 'list'` in source index merging.
- **OCR Realignment**: Renamed `mineru_parse_url` to `ocr_parse` and broadened its semantic scope to "any document or image".
- **Network Resilience**: Hardened `jina_reader` with pre-flight probes and multiple fallbacks (Firecrawl, Trafilatura).

### 🛠️ Developer Experience
- **Standalone Mode**: Core logic functions (e.g., `fetch_and_distill_web`) are exported as pure Python functions for use in other projects.
- **Smoke Tests**: Added `scripts/test_pluggable_tools.py` for component-level verification.
