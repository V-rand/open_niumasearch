from __future__ import annotations

import argparse
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Deep Research Agent harness")
    parser.add_argument("user_input", help="The user request for the agent.")
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

    sessions_dir = Path(args.sessions_dir).resolve()
    base_system_prompt = (
        Path(args.system_prompt_file).read_text(encoding="utf-8")
        if args.system_prompt_file
        else DEFAULT_SYSTEM_PROMPT
    )
    loaded_skills = load_repo_skills(args.skill) if args.skill else []
    system_prompt = compose_system_prompt(base_system_prompt, loaded_skills)
    session = create_session(
        sessions_dir,
        user_input=args.user_input,
        session_id=args.session_id,
    )

    backend = DashScopeOpenAIBackend()
    tools = build_builtin_tools(workspace_root=session.workspace_dir)
    logger = RunLogger(base_dir=session.logs_dir)
    agent = ReActAgent(
        model_backend=backend,
        tool_registry=tools,
        logger=logger,
        config=AgentConfig(max_turns=args.max_turns),
    )

    result = agent.run(
        user_input=args.user_input,
        system_prompt=system_prompt,
        skill_paths=[str(skill.path) for skill in loaded_skills],
    )
    print(f"session_id={session.session_id}")
    print(f"session_dir={session.session_dir}")
    print(f"workspace_dir={session.workspace_dir}")
    if loaded_skills:
        print(f"skills={','.join(skill.name for skill in loaded_skills)}")
    print(f"stop_reason={result.stop_reason}")
    print(f"turn_count={result.turn_count}")
    print(f"run_dir={result.run_dir}")
    if result.final_answer:
        print(result.final_answer)


if __name__ == "__main__":
    main()
