# Deep Research Agent

Minimal harness for a deep research agent with a ReAct loop, real tool integration, and full run observability.

## Layout

- `src/deep_research_agent/`: runtime, tools, logging, session, eval entrypoint
- `tests/`: deterministic tests and fast smoke-oriented unit coverage
- `scripts/`: utility scripts such as tool smoke tests
- `skills/`: repo-local skills, including the TODO skill
- `REQUIRED/`: project requirements and design references
- `sessions/`: per-task runtime outputs, including isolated `workspace/`, `documents/`, and `logs/` for each session
