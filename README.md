# Deep Research Agent

Minimal harness for a deep research agent with a ReAct loop, real tool integration, and full run observability.

## Layout

- `src/deep_research_agent/`: runtime, tools, logging, session, eval entrypoint
- `tests/`: deterministic tests and fast smoke-oriented unit coverage
- `scripts/`: utility scripts such as tool smoke tests
- `skills/`: repo-local skills, including the TODO skill
- `REQUIRED/`: project requirements and design references
- `sessions/`: per-task runtime outputs, including isolated `workspace/`, `documents/`, and `logs/` for each session

## Real Run Notes (China network)

- If `jina_reader` fails with SSL/certificate errors, run with proxy enabled in an interactive shell:

```bash
timeout 240s bash -ic 'cd /home/xiemingjie/dev/deep_research_agent && set -a && source .env && set +a && proxy_on && UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/smoke_tool.py jina_reader --url https://example.com'
```

- For real eval runs, use the same pattern:

```bash
timeout 300s bash -ic 'cd /home/xiemingjie/dev/deep_research_agent && set -a && source .env && set +a && proxy_on && UV_CACHE_DIR=/tmp/uv-cache uv run deep-research-agent-eval "<prompt>" --skill research-todo --max-turns 10'
```

- If model/network calls still fail in sandbox with `Operation not permitted` or `APIConnectionError`, rerun outside sandbox permissions.
