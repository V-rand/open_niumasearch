# Deep Research Agent — Agent Guide

> This file is written for AI coding agents. It assumes you know nothing about this project. Read this first before making any changes.

## Project Overview

**Deep Research Agent** (`deep-research-agent`) is a minimal but production-oriented harness for building a deep-research AI agent with a ReAct (Reasoning + Acting) loop. It is not a chatbot wrapper — it is a structured workflow system designed for long-horizon research tasks.

The core philosophy is **external working memory management**: the agent manages research objects (sources, notes, evidence, checkpoints, TODOs) as files, keeping only the active working set in the model context. This avoids compressing long chat history into the model context window.

The project is at V0.1/MVP stage (created 2026-04-22). It has a working ReAct loop, 9 built-in tools, session isolation, dual logging, and a Chinese Markdown TODO skill. The ambitious multi-phase research/writing system described in `REQUIRED/DESIGN main.md` is not yet implemented.

**Language**: Python 3.11+  
**Build Tool**: `uv` (modern Python package manager)  
**Build Backend**: `hatchling`  
**LLM Backend**: DashScope (Alibaba Cloud) via OpenAI-compatible API (`qwen-plus` / `qwen3.6-plus`)  
**Remote**: `git@github.com:V-rand/open_niumasearch.git`

---

## Directory Layout

```
.
├── pyproject.toml              # Package config, deps, scripts, pytest settings
├── README.md                   # Human-facing quick overview
├── CHANGELOG.md                # Mandatory work log — must be updated after every meaningful unit of work
├── AGENTS.md                   # This file
├── .env                        # API keys (gitignored — NEVER commit)
├── .gitignore                  # Ignores .venv, sessions/, logs/, artifacts/, .env, etc.
├── uv.lock                     # uv lockfile
│
├── src/deep_research_agent/    # Main source package
│   ├── __init__.py
│   ├── agent.py                # ReActAgent — core while-loop runtime
│   ├── cli.py                  # CLI entrypoint: deep-research-agent
│   ├── eval.py                 # Eval/benchmark entrypoint: deep-research-agent-eval
│   ├── dashscope_backend.py    # DashScope OpenAI-compatible backend wrapper
│   ├── logging.py              # RunLogger — events.jsonl + trace.md + artifact spillover
│   ├── models.py               # Core dataclasses: ToolCall, AssistantResponse, etc.
│   ├── session.py              # Per-task session isolation (workspace/, logs/, session.json)
│   ├── skills.py               # Skill loading from skills/ + system prompt composition
│   └── tools.py                # ToolRegistry + all 9 built-in tools (~883 lines)
│
├── tests/                      # All tests
│   ├── conftest.py             # Custom --fast pytest option + is_fast_mode fixture
│   ├── test_agent_loop.py      # ReAct loop behavior tests
│   ├── test_tools.py           # ToolRegistry, filesystem, MinerU mock, arXiv mock, PDF fallback
│   ├── test_logging.py         # Artifact spillover, trace formatting
│   ├── test_session.py         # Session directory isolation
│   ├── test_skills.py          # Skill loading, system prompt composition
│   └── test_todo_skill_scripts.py  # TODO markdown init/validate scripts
│
├── scripts/                    # Utility scripts
│   ├── smoke_tool.py           # Real API smoke tests for individual tools
│   ├── init_todo_md.py         # Generate Chinese Markdown TODO templates
│   └── validate_todo_md.py     # Validate TODO markdown structure
│
├── skills/                     # Repo-local skills (loaded by skills.py)
│   └── todo-list.md            # Chinese Markdown TODO List skill
│
├── sessions/                   # Runtime output — per-session workspace/ + logs/ (gitignored)
│
└── REQUIRED/                   # Design docs and requirements (Chinese)
    ├── CLASS.md                # Development standards — READ THIS
    ├── REQUIRED.md             # Main requirements entry
    ├── DESIGN main.md          # Full V0.1 context management & workflow design
    ├── agent loop design.md    # ReAct loop specification
    ├── 可观察.md               # Observability requirements
    ├── 百炼官方api文档.md       # BaiLian official API docs
    ├── tool design/            # Per-tool design docs
    └── skills design/          # Skill design docs
```

---

## Build and Test Commands

All commands assume `uv` is installed and available.

```bash
# Install dependencies (including dev)
uv sync

# Run the fast deterministic test subset (default dev loop)
pytest tests/ -q --fast

# Run the full test suite
pytest tests/ -q

# Run the agent CLI
deep-research-agent "your research question" --skill todo-list --max-turns 10

# Run the eval entrypoint (prints JSON)
deep-research-agent-eval "benchmark prompt" --skill todo-list

# Smoke-test a single tool against real APIs
uv run python scripts/smoke_tool.py web_search --query "OpenAI"
uv run python scripts/smoke_tool.py jina_reader --url "https://example.com"
uv run python scripts/smoke_tool.py arxiv_search --query "transformer attention"
uv run python scripts/smoke_tool.py pdf_read_url --url "https://example.com/file.pdf"
```

---

## Code Style Guidelines

The project follows the conventions defined in `REQUIRED/CLASS.md`. Key points:

- **Simple, direct, readable** — code first should be easy to read, modify, and debug. Do not chase "architecture elegance" or textbook patterns.
- **Dataclasses over dicts** for core state and cross-module objects. Avoid letting important domain objects drift as bare dicts.
- **Composition over inheritance** — no god classes. Main entry classes are assembly roots, not total-control centers.
- **Explicit over implicit** — dependencies, I/O, side effects, and state changes should be written clearly.
- **No empty `except` blocks** — errors should be exposed, not silently swallowed. Exceptions are only caught at boundary layers (tool calls, task scheduling, state persistence, external I/O).
- **Accurate naming** — avoid vague names like `data`, `obj`, `manager`, `helper`, `util`. Function names use verb phrases; boolean names should read as sentences (`is_active`, `has_pending_tasks`).
- **Modules by responsibility** — keep flat while small; layer only when complexity genuinely rises. Avoid `utils.py` / `helpers.py` / `misc.py`.
- **Comments explain "why" and "constraints"**, not literal translations of code.

### Pythonic Preferences

- `dataclass`
- Small pure functions
- Composition objects
- Explicit mapping/dispatch instead of long `if/elif` chains
- Standard library

Avoid: heavy frameworks, factory patterns, complex inheritance trees, abstract base class oceans, excessive service/repository layering.

---

## Testing Instructions

### Test-First Development (Strict)

- **All new modules must have tests before implementation.**
- **Bug fixes require a reproducing test first**, then the fix.
- **Never break existing passing tests.**
- **Never commit with failing tests.**

### Test Layers

The project expects tests at multiple layers:

- **Unit tests** — pure functions, parsers, state transforms, small data structures
- **Interface tests** — tool schemas, prompt output structures, serialization
- **Process tests** — minimal harness agent execution paths
- **Regression tests** — historical bugs, boundary conditions, previously failed cases
- **Eval tests** — task-level success rate, step count, cost/latency

### `--fast` Mode

Every test file must support `--fast` via the `is_fast_mode` fixture. `--fast` runs a deterministic ~10% subset for rapid local iteration. The default dev loop is:

```bash
pytest tests/ -q --fast
```

Only run the full suite before commits or at milestones.

### Contract Tests

Changes to the following **must** have contract tests:

- Prompt templates or output formats
- Tool input/output schemas
- State structures
- Planner / executor protocols
- Checkpoint formats or recovery logic

---

## Security Considerations

- **`.env` contains API keys** — it is gitignored and must NEVER be committed.
- **Do not commit**: local virtual environments, cache directories, build artifacts, downloaded raw materials, runtime logs, traces, checkpoints, or any other process files.
- **Default rule**: the repository only holds source code, tests, necessary docs, config templates, and explicitly versioned static assets. Anything "naturally produced at runtime" stays out of Git.
- **API keys required at runtime** (read from environment):
  - `OPENAI_API_KEY` or `DASHSCOPE_API_KEY` — for the LLM backend
  - `TAVILY_API_KEY` — for web search
  - `JINA_API_KEY` — for Jina Reader
  - `MINERU_API_KEY` — for MinerU document parsing

---

## Architecture Notes

### ReAct Loop (`agent.py`)

`ReActAgent.run()` drives a while-loop:
1. Send messages + tools to the model backend
2. Receive `AssistantResponse` (reasoning + content + optional tool_calls)
3. If tool_calls exist, dispatch them (parallel via `ThreadPoolExecutor` when configured)
4. Append tool results to messages and continue
5. If no tool_calls and content exists, return final answer
6. Stop if `max_turns` exceeded

### Session Isolation (`session.py`)

Each task run creates an isolated session under `sessions/<session_id>/`:
- `workspace/` — agent working files, documents
- `logs/` — run logs (`events.jsonl`, `trace.md`, artifacts)
- `session.json` — metadata (session_id, created_at, user_input)

Session IDs are derived from timestamp + user_input hash + uuid fragment.

### Dual Logging (`logging.py`)

`RunLogger` produces two outputs for every run:
- `events.jsonl` — structured, machine-readable, complete (with timestamps)
- `trace.md` — human-readable, grouped by turn, compact (no timestamps, no tool call IDs)

Large payloads (>4,000 chars) are spilled to `artifacts/` but remain inline in `events.jsonl`.

### Tools (`tools.py`)

9 built-in tools:

| Tool | Purpose |
|------|---------|
| `fs_list` | List files/directories in workspace |
| `fs_read` | Read text files with line/char limits |
| `fs_write` | Create/overwrite/append files |
| `fs_patch` | Text patching (replace, insert_before, insert_after) |
| `web_search` | Tavily web search |
| `jina_reader` | Jina Reader API for web page extraction |
| `mineru_parse_url` | MinerU PDF/image/Doc/PPT parsing |
| `arxiv_search` | Search arXiv papers |
| `arxiv_read_paper` | Download + parse arXiv PDF to Markdown |
| `pdf_read_url` | General PDF URL reader (default: local PyMuPDF4LLM, optional MinerU) |

Tool design patterns:
- Workspace-root path containment (no directory traversal)
- Schema-lite validation (required params only)
- Structured JSON returns normalized to `ToolExecutionResult`
- Parallel execution via `ThreadPoolExecutor`

### Skills (`skills.py`)

Skills are repo-local `.md` files under `skills/`. They are loaded and appended to the system prompt. The only current skill is `todo-list.md` (Chinese Markdown checklist design for research/writing TODOs).

### Model Backend (`dashscope_backend.py`)

Wraps DashScope's OpenAI-compatible endpoint. Supports `enable_thinking`, `tool_choice`, and `parallel_tool_calls` via `extra_body`. Default model is `qwen-plus` (overridable via `AGENT_OS_MODEL`).

---

## Development Workflow

When you receive a task, follow this order:

1. **Read** the relevant modules, existing tests, and the most recent `CHANGELOG.md` entries.
2. **Write** a minimal failing test (or a regression test that exposes the current problem).
3. **Implement** the smallest change that makes the test pass.
4. **Run** `pytest tests/ -q --fast` to check for regressions.
5. **Update** `CHANGELOG.md` with: what changed, test results, what worked, what failed, new tasks discovered.

If a larger refactor seems needed, first confirm it is driven by a current real failure. If not, do not expand. Separate pure refactors from functional changes into independent commits.

### Pre-Commit Checklist

- [ ] Change solves one clear work unit
- [ ] New modules have tests first
- [ ] New bugs have reproducing tests before fixes
- [ ] `pytest tests/ -q --fast` passes
- [ ] `CHANGELOG.md` is updated
- [ ] No secrets, environments, caches, or process files are staged
- [ ] No unnecessary large abstractions or refactors sneaked in
- [ ] If prompt/tool/state contracts changed, contract tests exist
- [ ] Behavioral changes are recorded with verification results

---

## Important Constraints

- **Chinese-first skill design** — system prompts, skills, TODOs, and requirements are in Chinese. The target model is Alibaba Cloud's Qwen via DashScope.
- **No database or vector store** — file-based external memory only, by design.
- **No CI/CD, Docker, or deployment configs** — this is a local development harness.
- **Minimal harness philosophy** — start smallest, validate, then expand. Complexity growth must be slower than demand/failure-mode growth.
- **Real API validation required** — fake/replay tests are for local iteration only. All tool integrations must be validated against real APIs before being considered working.
