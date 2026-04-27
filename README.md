# Deep Research Agent

Minimal harness for a deep research agent with a ReAct loop, real tool integration, and full run observability. Specially hardened for **Legal Research** and **Large-scale Evidence Management**.

## Architecture Highlights
- **Locality-First Evidence Library**: Automatically archives all downloads to `research/raw` and maintains a high-density summary index in `research/source_index.md`.
- **Token Budgeting**: Aggressive character capping and surgical snippet extraction to prevent context window overflow.
- **Resilient Tooling**: Integrated legal expert APIs and hardened PDF/Web readers with automated fallback logic.

## Layout

- `src/deep_research_agent/`: Core runtime and pluggable tools.
- `research/`: The persistent working memory (Sources, Notes, Index).
- `tests/`: Robustness and dispatch tests.
- `scripts/`: Infrastructure validation and pre-flight tools.

## Real Run & Infrastructure Check

Before running a mission, ensure your environment is healthy:

### 1. Infrastructure Validation
Check if the archiver and tool registry are correctly configured:
```bash
uv run python scripts/validate_infra.py
```

### 2. Network Preflight (China Environment)
Always run network preflight to verify API availability and proxy settings:
```bash
timeout 120s bash -ic 'cd /home/xiemingjie/dev/deep_research_agent && set -a && source .env && set +a && proxy_on && UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/preflight_network.py'
```

### 3. Execution Patterns
To start a research session with evidence awareness:
```bash
uv run deep-research-agent "研究主播劳动关系认定的司法裁判倾向" --skill todo-list --max-turns 20
```

## Maintenance Notes
- **Source Index**: If the agent seems "blind" to existing files, check `research/source_index.md`.
- **Environment**: If imports fail, run `uv pip install -e .` in your active venv.
- **Git Discipline**: Never commit files in `research/` or `sessions/`.
