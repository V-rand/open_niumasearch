from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.agent import AgentConfig, ReActAgent
from deep_research_agent.dashscope_backend import DashScopeOpenAIBackend
from deep_research_agent.logging import RunLogger
from deep_research_agent.session import create_session
from deep_research_agent.skills import compose_system_prompt, load_repo_skills
from deep_research_agent.tools import build_builtin_tools


DEFAULT_SYSTEM_PROMPT = """你是一个谨慎的 research agent。
所有动作前先简短思考。
优先使用最直接、最少的工具完成当前问题。
工具结果不是最终答案，必须在观察后再决定下一步或给出 final answer。"""


def run_eval_case(
    *,
    user_input: str,
    sessions_dir: Path,
    session_id: str | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    skill_names: list[str] | None = None,
    max_turns: int = 6,
    model_backend: Any | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    session = create_session(
        Path(sessions_dir),
        user_input=user_input,
        session_id=session_id,
    )
    loaded_skills = load_repo_skills(skill_names or []) if skill_names else []
    full_system_prompt = compose_system_prompt(system_prompt, loaded_skills)
    backend = model_backend or DashScopeOpenAIBackend()
    tools = build_builtin_tools(workspace_root=session.workspace_dir, http_client=http_client)
    logger = RunLogger(base_dir=session.logs_dir)
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=tools,
        logger=logger,
        config=AgentConfig(max_turns=max_turns),
    )
    result = agent.run(
        user_input=user_input,
        system_prompt=full_system_prompt,
        skill_paths=[str(skill.path) for skill in loaded_skills],
    )
    return {
        "session_id": session.session_id,
        "session_dir": str(session.session_dir),
        "workspace_dir": str(session.workspace_dir),
        "logs_dir": str(session.logs_dir),
        "documents_dir": str(session.workspace_dir / "documents"),
        "run_dir": str(result.run_dir),
        "skills": [skill.name for skill in loaded_skills],
        "final_answer": result.final_answer,
        "stop_reason": result.stop_reason,
        "turn_count": result.turn_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stable JSON eval entrypoint for benchmarks.")
    parser.add_argument("user_input", help="The benchmark prompt or user input.")
    parser.add_argument(
        "--sessions-dir",
        default="sessions",
        help="Directory where isolated task sessions are created.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional existing session id to reuse.",
    )
    parser.add_argument(
        "--system-prompt-file",
        help="Optional file containing the system prompt.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Repo-local skill name under skills/<name>.md. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=6,
        help="Maximum model turns before stopping.",
    )
    args = parser.parse_args()

    system_prompt = (
        Path(args.system_prompt_file).read_text(encoding="utf-8")
        if args.system_prompt_file
        else DEFAULT_SYSTEM_PROMPT
    )
    payload = run_eval_case(
        user_input=args.user_input,
        sessions_dir=Path(args.sessions_dir).resolve(),
        session_id=args.session_id,
        system_prompt=system_prompt,
        skill_names=args.skill,
        max_turns=args.max_turns,
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
