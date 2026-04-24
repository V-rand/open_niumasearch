from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from deep_research_agent.agent import AgentConfig, ReActAgent
from deep_research_agent.dashscope_backend import DashScopeOpenAIBackend
from deep_research_agent.logging import RunLogger
from deep_research_agent.models import AgentRunResult
from deep_research_agent.prompts import compose_system_prompt, get_system_prompt
from deep_research_agent.session import create_session
from deep_research_agent.skills import load_repo_skills
from deep_research_agent.tools import ToolRegistry, build_builtin_tools, build_readonly_tools


class BackendFactory(Protocol):
    def __call__(self, model: str | None = None) -> Any:
        ...


@dataclass(slots=True)
class MultiAgentConfig:
    max_research_cycles: int = 4
    max_writing_cycles: int = 3
    researcher_max_turns: int = 6
    evaluator_max_turns: int = 3
    writer_max_turns: int = 6
    evaluator_model: str | None = None
    researcher_followup_user_message: str = (
        "基于新证据更新当前信念，判断下一步行动是否仍有高信息增益。"
    )
    writer_followup_user_message: str = (
        "围绕报告质量更新当前写作判断；如发现证据缺口，可以补充研究工具调用。"
    )


@dataclass(slots=True)
class ResearchDecision:
    cycle_index: int
    decision: str
    evaluator_outputs: dict[str, str]
    decision_path: Path


@dataclass(slots=True)
class MultiAgentRunResult:
    session_id: str
    session_dir: Path
    workspace_dir: Path
    stop_reason: str
    research_cycle_count: int
    writing_cycle_count: int
    final_answer: str | None
    decisions: list[ResearchDecision]
    writer_run_dirs: list[Path]


EVALUATOR_FACETS = ("evidence_auditor", "strategy_reviewer", "deliverable_reviewer")


def run_multi_agent_case(
    *,
    user_input: str,
    sessions_dir: Path,
    session_id: str | None = None,
    system_prompt: str | None = None,
    skill_names: list[str] | None = None,
    config: MultiAgentConfig | None = None,
    backend_factory: BackendFactory | None = None,
    researcher_tools: ToolRegistry | None = None,
    evaluator_tools: ToolRegistry | None = None,
    writer_tools: ToolRegistry | None = None,
) -> MultiAgentRunResult:
    config = config or MultiAgentConfig()
    backend_factory = backend_factory or (lambda model=None: DashScopeOpenAIBackend(model=model))
    evaluator_model = config.evaluator_model or os.getenv("AGENT_OS_EVALUATOR_MODEL")

    session = create_session(Path(sessions_dir), user_input=user_input, session_id=session_id)
    workspace_dir = session.workspace_dir
    _prepare_workspace(workspace_dir)

    loaded_skills = load_repo_skills(skill_names or []) if skill_names else []
    researcher_tools = researcher_tools or build_builtin_tools(workspace_root=workspace_dir)
    writer_tools = writer_tools or build_builtin_tools(workspace_root=workspace_dir)
    evaluator_tools = evaluator_tools or build_readonly_tools(workspace_root=workspace_dir)

    base_prompt = system_prompt if system_prompt is not None else get_system_prompt()
    researcher_prompt = _compose_researcher_prompt(
        base_prompt=base_prompt,
        tools=researcher_tools,
        loaded_skills=loaded_skills,
    )
    writer_prompt = _compose_writer_prompt(
        base_prompt=base_prompt,
        tools=writer_tools,
        loaded_skills=loaded_skills,
    )
    evaluator_prompt = _compose_evaluator_prompt(tools=evaluator_tools)

    rubric = _run_evaluator_handshake(
        user_input=user_input,
        evaluator_prompt=evaluator_prompt,
        evaluator_tools=evaluator_tools,
        evaluator_backend=backend_factory(evaluator_model),
        logs_dir=session.logs_dir,
        max_turns=config.evaluator_max_turns,
    )
    _write_text(workspace_dir / "research" / "evaluation_rubric.md", rubric)

    decisions: list[ResearchDecision] = []
    previous_feedback = "首次研究循环：请先读取 research/evaluation_rubric.md，并制定本周期研究计划。"

    for cycle_index in range(1, config.max_research_cycles + 1):
        researcher_result = _run_research_cycle(
            user_input=_build_researcher_cycle_input(
                user_input=user_input,
                cycle_index=cycle_index,
                previous_feedback=previous_feedback,
            ),
            researcher_prompt=researcher_prompt,
            researcher_tools=researcher_tools,
            researcher_backend=backend_factory(None),
            logs_dir=session.logs_dir,
            cycle_index=cycle_index,
            config=config,
        )

        evaluator_outputs = _run_research_evaluators(
            user_input=user_input,
            cycle_index=cycle_index,
            evaluator_prompt=evaluator_prompt,
            evaluator_tools=evaluator_tools,
            backend_factory=backend_factory,
            evaluator_model=evaluator_model,
            logs_dir=session.logs_dir,
            max_turns=config.evaluator_max_turns,
        )
        decision_text = _render_research_decision(cycle_index=cycle_index, evaluator_outputs=evaluator_outputs)
        decision_path = workspace_dir / "research" / "evaluations" / f"research_cycle_{cycle_index:03d}_decision.md"
        _write_text(decision_path, decision_text)
        decision = ResearchDecision(
            cycle_index=cycle_index,
            decision=_resolve_decision(evaluator_outputs.values()),
            evaluator_outputs=evaluator_outputs,
            decision_path=decision_path,
        )
        decisions.append(decision)

        if decision.decision == "STOP":
            packet_path = _write_writer_packet(
                workspace_dir=workspace_dir,
                user_input=user_input,
                cycle_index=cycle_index,
                certification=decision_text,
            )
            writer_final_answer, writing_cycle_count, writer_run_dirs, writer_certified = _run_writing_phase(
                user_input=user_input,
                packet_path=packet_path,
                workspace_dir=workspace_dir,
                writer_prompt=writer_prompt,
                writer_tools=writer_tools,
                evaluator_prompt=evaluator_prompt,
                evaluator_tools=evaluator_tools,
                backend_factory=backend_factory,
                evaluator_model=evaluator_model,
                logs_dir=session.logs_dir,
                config=config,
            )
            return MultiAgentRunResult(
                session_id=session.session_id,
                session_dir=session.session_dir,
                workspace_dir=workspace_dir,
                stop_reason="writer_certified" if writer_certified else "writing_not_certified_within_max_cycles",
                research_cycle_count=cycle_index,
                writing_cycle_count=writing_cycle_count,
                final_answer=writer_final_answer,
                decisions=decisions,
                writer_run_dirs=writer_run_dirs,
            )

        previous_feedback = decision_text
        if researcher_result.stop_reason == "max_turns_exceeded":
            previous_feedback += (
                "\n\nHarness note: 上一研究周期耗尽 researcher_max_turns，下一周期必须先收束并写清信念更新。"
            )

    return MultiAgentRunResult(
        session_id=session.session_id,
        session_dir=session.session_dir,
        workspace_dir=workspace_dir,
        stop_reason="research_not_certified_within_max_cycles",
        research_cycle_count=config.max_research_cycles,
        writing_cycle_count=0,
        final_answer=None,
        decisions=decisions,
        writer_run_dirs=[],
    )


def _compose_researcher_prompt(
    *,
    base_prompt: str,
    tools: ToolRegistry,
    loaded_skills: list[Any],
) -> str:
    prompt = compose_system_prompt(base_prompt, tools=tools.to_openai_tools())
    for skill in loaded_skills:
        prompt += f"\n\n## Skill: {skill.name}\n\n{skill.content.rstrip()}\n"
    prompt += (
        "\n\n<researcher_contract>\n"
        "你是 Researcher。当前显式阶段是 RESEARCH。\n"
        "你的任务是通过检索、阅读、摘录、notes 和 synthesis 形成可认证研究包。\n"
        "每个周期先写 research/cycles/research_cycle_NNN_plan.md，结束前写 "
        "research/cycles/research_cycle_NNN_update.md。\n"
        "不要写最终报告；研究认证通过后会启动全新的 Writer agent。\n"
        "</researcher_contract>"
    )
    return prompt


def _compose_writer_prompt(
    *,
    base_prompt: str,
    tools: ToolRegistry,
    loaded_skills: list[Any],
) -> str:
    prompt = compose_system_prompt(base_prompt, tools=tools.to_openai_tools())
    for skill in loaded_skills:
        prompt += f"\n\n## Skill: {skill.name}\n\n{skill.content.rstrip()}\n"
    prompt += (
        "\n\n<writer_contract>\n"
        "你是全新的 Writer agent。当前显式阶段是 WRITING。\n"
        "你不能继承 Researcher 的对话历史，只能读取 research/writer_packet.md 和工作区文件。\n"
        "你的主要任务是按原始任务选择合适交付形态：短答案、长报告、阅读清单、实验方案或草稿都可以。\n"
        "不要为了显得正式而强行写长文；benchmark 短答案任务应保持短、准、可核查。\n"
        "若需要落文件，优先写 research/report.md 或 writing/drafts/*.md。\n"
        "写作中如果发现证据缺口，可以使用研究工具补检索、补阅读，并同步更新 source_index/notes。\n"
        "</writer_contract>"
    )
    return prompt


def _compose_evaluator_prompt(*, tools: ToolRegistry) -> str:
    return compose_system_prompt(
        (
            "你是独立 Evaluator，只负责审查 Researcher 的 Markdown 产物和执行轨迹。\n"
            "你不能修改工作区，只能读取文件。\n"
            "审查重点：证据是否有原文锚点、leads/source/notes 是否真正服务于信念更新、"
            "研究包是否足以交给全新的 Writer agent。\n"
            "不要用固定流程或固定篇幅压制任务；验收标准必须适配原始任务，短答案任务不应被要求写长文。\n"
            "每次输出必须包含一行：Decision: CONTINUE、Decision: REVISE 或 Decision: STOP。\n"
            "STOP 表示研究已通过认证，可以结束 RESEARCH 并启动全新的 WRITING agent。\n"
            "\n<tool_catalog>\n{tool_catalog}\n</tool_catalog>\n"
        ),
        tools=tools.to_openai_tools(),
    )


def _run_evaluator_handshake(
    *,
    user_input: str,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    evaluator_backend: Any,
    logs_dir: Path,
    max_turns: int,
) -> str:
    logger = RunLogger(base_dir=logs_dir / "evaluator_handshake")
    agent = ReActAgent(
        model_backend=evaluator_backend,
        tool_registry=evaluator_tools,
        logger=logger,
        config=AgentConfig(max_turns=max_turns, tool_choice="auto"),
    )
    result = agent.run(
        user_input=(
            "为本任务制定 research certification rubric。必须说明 Researcher 的验收标准、"
            "证据锚定标准、信念更新标准、Writer handoff 标准和停止标准。\n\n"
            "Rubric 必须适配原始任务的交付形态：短答案、长答案、阅读清单、实验方案的要求不同。\n"
            f"任务：\n{user_input}"
        ),
        system_prompt=evaluator_prompt,
    )
    return result.final_answer or "Decision: CONTINUE\n\n未能生成完整 rubric，默认继续并要求下一周期补齐。"


def _run_research_cycle(
    *,
    user_input: str,
    researcher_prompt: str,
    researcher_tools: ToolRegistry,
    researcher_backend: Any,
    logs_dir: Path,
    cycle_index: int,
    config: MultiAgentConfig,
) -> AgentRunResult:
    logger = RunLogger(base_dir=logs_dir / f"research_cycle_{cycle_index:03d}")
    agent = ReActAgent(
        model_backend=researcher_backend,
        tool_registry=researcher_tools,
        logger=logger,
        config=AgentConfig(
            max_turns=config.researcher_max_turns,
            followup_user_message=config.researcher_followup_user_message,
        ),
    )
    return agent.run(user_input=user_input, system_prompt=researcher_prompt)


def _run_writing_phase(
    *,
    user_input: str,
    packet_path: Path,
    workspace_dir: Path,
    writer_prompt: str,
    writer_tools: ToolRegistry,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    backend_factory: BackendFactory,
    evaluator_model: str | None,
    logs_dir: Path,
    config: MultiAgentConfig,
) -> tuple[str | None, int, list[Path], bool]:
    previous_feedback = "首次写作循环：请先读取 research/writer_packet.md，并写出最终交付。"
    final_answer: str | None = None
    writer_run_dirs: list[Path] = []

    for writing_cycle_index in range(1, config.max_writing_cycles + 1):
        writer_result = _run_writer_cycle(
            user_input=_build_writer_input(
                user_input=user_input,
                packet_path=packet_path,
                writing_cycle_index=writing_cycle_index,
                previous_feedback=previous_feedback,
            ),
            writer_prompt=writer_prompt,
            writer_tools=writer_tools,
            writer_backend=backend_factory(None),
            logs_dir=logs_dir,
            writing_cycle_index=writing_cycle_index,
            config=config,
        )
        final_answer = writer_result.final_answer or final_answer
        writer_run_dirs.append(writer_result.run_dir)

        evaluator_outputs = _run_writing_evaluators(
            user_input=user_input,
            writing_cycle_index=writing_cycle_index,
            evaluator_prompt=evaluator_prompt,
            evaluator_tools=evaluator_tools,
            backend_factory=backend_factory,
            evaluator_model=evaluator_model,
            logs_dir=logs_dir,
            max_turns=config.evaluator_max_turns,
        )
        decision_text = _render_writing_decision(
            writing_cycle_index=writing_cycle_index,
            evaluator_outputs=evaluator_outputs,
        )
        _write_text(
            workspace_dir / "research" / "evaluations" / f"writing_cycle_{writing_cycle_index:03d}_decision.md",
            decision_text,
        )
        if _resolve_decision(evaluator_outputs.values()) == "STOP":
            return final_answer, writing_cycle_index, writer_run_dirs, True
        previous_feedback = decision_text

    return final_answer, config.max_writing_cycles, writer_run_dirs, False


def _run_writer_cycle(
    *,
    user_input: str,
    writer_prompt: str,
    writer_tools: ToolRegistry,
    writer_backend: Any,
    logs_dir: Path,
    writing_cycle_index: int,
    config: MultiAgentConfig,
) -> AgentRunResult:
    logger = RunLogger(base_dir=logs_dir / f"writing_cycle_{writing_cycle_index:03d}")
    agent = ReActAgent(
        model_backend=writer_backend,
        tool_registry=writer_tools,
        logger=logger,
        config=AgentConfig(
            max_turns=config.writer_max_turns,
            followup_user_message=config.writer_followup_user_message,
        ),
    )
    return agent.run(user_input=user_input, system_prompt=writer_prompt)


def _run_writing_evaluators(
    *,
    user_input: str,
    writing_cycle_index: int,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    backend_factory: BackendFactory,
    evaluator_model: str | None,
    logs_dir: Path,
    max_turns: int,
) -> dict[str, str]:
    outputs: dict[str, str] = {}
    facets = ("citation_auditor", "writing_reviewer", "gap_reviewer")
    with ThreadPoolExecutor(max_workers=len(facets)) as executor:
        futures = {
            facet: executor.submit(
                _run_single_writing_evaluator,
                facet=facet,
                user_input=user_input,
                writing_cycle_index=writing_cycle_index,
                evaluator_prompt=evaluator_prompt,
                evaluator_tools=evaluator_tools,
                evaluator_backend=backend_factory(evaluator_model),
                logs_dir=logs_dir,
                max_turns=max_turns,
            )
            for facet in facets
        }
        for facet, future in futures.items():
            outputs[facet] = future.result()
    return outputs


def _run_single_writing_evaluator(
    *,
    facet: str,
    user_input: str,
    writing_cycle_index: int,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    evaluator_backend: Any,
    logs_dir: Path,
    max_turns: int,
) -> str:
    logger = RunLogger(base_dir=logs_dir / f"writing_cycle_{writing_cycle_index:03d}_{facet}")
    agent = ReActAgent(
        model_backend=evaluator_backend,
        tool_registry=evaluator_tools,
        logger=logger,
        config=AgentConfig(max_turns=max_turns, tool_choice="auto"),
    )
    prompt = (
        f"你是 {facet}。请审查第 {writing_cycle_index} 个 WRITING 周期的报告和引用。\n"
        "先读取 research/writer_packet.md、research/report.md 或 writing/drafts/，"
        "必要时读取 source_index、notes、raw 摘录。\n"
        "请判断写作交付是否通过认证；按原始任务决定是否需要长文、短答案、引用或 References。"
        "如果任务不要求长文，不要因篇幅短而扣分；如果缺必要证据映射或发现研究缺口，要求修订。\n"
        "最后必须输出 Decision: CONTINUE / REVISE / STOP。\n\n"
        f"原始任务：\n{user_input}"
    )
    result = agent.run(user_input=prompt, system_prompt=evaluator_prompt)
    return result.final_answer or "Decision: REVISE\n\nWriter evaluator 未产出最终意见，默认要求修订。"


def _run_research_evaluators(
    *,
    user_input: str,
    cycle_index: int,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    backend_factory: BackendFactory,
    evaluator_model: str | None,
    logs_dir: Path,
    max_turns: int,
) -> dict[str, str]:
    outputs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(EVALUATOR_FACETS)) as executor:
        futures = {
            facet: executor.submit(
                _run_single_evaluator,
                facet=facet,
                user_input=user_input,
                cycle_index=cycle_index,
                evaluator_prompt=evaluator_prompt,
                evaluator_tools=evaluator_tools,
                evaluator_backend=backend_factory(evaluator_model),
                logs_dir=logs_dir,
                max_turns=max_turns,
            )
            for facet in EVALUATOR_FACETS
        }
        for facet, future in futures.items():
            outputs[facet] = future.result()
    return outputs


def _run_single_evaluator(
    *,
    facet: str,
    user_input: str,
    cycle_index: int,
    evaluator_prompt: str,
    evaluator_tools: ToolRegistry,
    evaluator_backend: Any,
    logs_dir: Path,
    max_turns: int,
) -> str:
    logger = RunLogger(base_dir=logs_dir / f"research_cycle_{cycle_index:03d}_{facet}")
    agent = ReActAgent(
        model_backend=evaluator_backend,
        tool_registry=evaluator_tools,
        logger=logger,
        config=AgentConfig(max_turns=max_turns, tool_choice="auto"),
    )
    prompt = (
        f"你是 {facet}。请审查第 {cycle_index} 个 RESEARCH 周期的工作区产物。\n"
        "先读取必要文件，如 research/evaluation_rubric.md、research/cycles/、research/source_index.md、"
        "research/notes/ 或 research/leads.md。\n"
        "请判断研究包是否足以认证并交给全新的 Writer agent。\n"
        "最后必须输出 Decision: CONTINUE / REVISE / STOP。\n\n"
        f"原始任务：\n{user_input}"
    )
    result = agent.run(user_input=prompt, system_prompt=evaluator_prompt)
    return result.final_answer or "Decision: CONTINUE\n\nEvaluator 未产出最终意见，默认继续。"


def _build_researcher_cycle_input(*, user_input: str, cycle_index: int, previous_feedback: str) -> str:
    return (
        f"原始任务：\n{user_input}\n\n"
        f"当前显式阶段：RESEARCH。当前是第 {cycle_index} 个研究周期。\n"
        "请遵循 Plan -> a series of research actions -> Update -> Eval handoff。\n"
        f"本周期开始时写 research/cycles/research_cycle_{cycle_index:03d}_plan.md；"
        f"结束前写 research/cycles/research_cycle_{cycle_index:03d}_update.md。\n"
        "不要写最终报告；你的目标是让研究包通过 evaluator 认证。\n\n"
        "上次 evaluator 反馈或启动说明：\n"
        f"{previous_feedback}"
    )


def _build_writer_input(
    *,
    user_input: str,
    packet_path: Path,
    writing_cycle_index: int,
    previous_feedback: str,
) -> str:
    return (
        f"原始任务：\n{user_input}\n\n"
        f"当前显式阶段：WRITING。当前是第 {writing_cycle_index} 个写作周期。"
        "你是全新的 Writer agent，不继承 Researcher 或上一轮 Writer 的对话历史。\n"
        f"请先读取 `{packet_path.as_posix()}`，再读取其中列出的研究产物，写出最终交付。\n"
        "如果写作中发现证据缺口，可以使用研究工具补检索或补阅读，但不要重新展开整个研究流程。\n\n"
        "上次 writing evaluator 反馈或启动说明：\n"
        f"{previous_feedback}"
    )


def _render_research_decision(*, cycle_index: int, evaluator_outputs: dict[str, str]) -> str:
    decision = _resolve_decision(evaluator_outputs.values())
    parts = [
        f"# Research Cycle {cycle_index:03d} Certification",
        "",
        f"Decision: {decision}",
        "",
    ]
    for facet, output in evaluator_outputs.items():
        parts.extend([f"## {facet}", "", output.strip(), ""])
    return "\n".join(parts).rstrip() + "\n"


def _render_writing_decision(*, writing_cycle_index: int, evaluator_outputs: dict[str, str]) -> str:
    decision = _resolve_decision(evaluator_outputs.values())
    parts = [
        f"# Writing Cycle {writing_cycle_index:03d} Certification",
        "",
        f"Decision: {decision}",
        "",
    ]
    for facet, output in evaluator_outputs.items():
        parts.extend([f"## {facet}", "", output.strip(), ""])
    return "\n".join(parts).rstrip() + "\n"


def _write_writer_packet(
    *,
    workspace_dir: Path,
    user_input: str,
    cycle_index: int,
    certification: str,
) -> Path:
    packet_path = workspace_dir / "research" / "writer_packet.md"
    files = _list_existing_research_files(workspace_dir)
    content = [
        "# Writer Handoff Packet",
        "",
        "## Original Task",
        user_input,
        "",
        "## Research Certification",
        certification.strip(),
        "",
        "## Required Reading Order",
        "- `research/evaluation_rubric.md`",
        f"- `research/evaluations/research_cycle_{cycle_index:03d}_decision.md`",
        "- `research/source_index.md` if present",
        "- `research/notes/*.md` if present",
        "- `research/cycles/research_cycle_*_update.md`",
        "",
        "## Available Research Files",
        *[f"- `{path}`" for path in files],
        "",
        "## Writer Instruction",
        "Start fresh. Do not rely on Researcher conversation history. Use these artifacts as external memory.",
    ]
    _write_text(packet_path, "\n".join(content))
    return packet_path.relative_to(workspace_dir)


def _list_existing_research_files(workspace_dir: Path) -> list[str]:
    research_dir = workspace_dir / "research"
    if not research_dir.exists():
        return []
    return sorted(str(path.relative_to(workspace_dir)) for path in research_dir.rglob("*.md"))


def _resolve_decision(outputs: Any) -> str:
    decisions = [_extract_decision(output) for output in outputs]
    stop_count = decisions.count("STOP")
    if stop_count > len(decisions) / 2:
        return "STOP"
    if "REVISE" in decisions:
        return "REVISE"
    return "CONTINUE"


def _extract_decision(text: str) -> str:
    normalized = text.upper()
    if "DECISION: STOP" in normalized:
        return "STOP"
    if "DECISION: REVISE" in normalized:
        return "REVISE"
    return "CONTINUE"


def _prepare_workspace(workspace_dir: Path) -> None:
    for relative in (
        "research",
        "research/cycles",
        "research/evaluations",
        "research/notes",
        "writing/drafts",
    ):
        (workspace_dir / relative).mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-phase multi-agent deep research harness")
    parser.add_argument("user_input", help="The user request for the agent.")
    parser.add_argument("--sessions-dir", default="sessions")
    parser.add_argument("--session-id")
    parser.add_argument("--system-prompt-file")
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--max-research-cycles", type=int, default=4)
    parser.add_argument("--max-writing-cycles", type=int, default=3)
    parser.add_argument("--researcher-max-turns", type=int, default=6)
    parser.add_argument("--evaluator-max-turns", type=int, default=3)
    parser.add_argument("--writer-max-turns", type=int, default=6)
    parser.add_argument("--evaluator-model")
    args = parser.parse_args()

    base_prompt = (
        Path(args.system_prompt_file).read_text(encoding="utf-8")
        if args.system_prompt_file
        else get_system_prompt()
    )
    result = run_multi_agent_case(
        user_input=args.user_input,
        sessions_dir=Path(args.sessions_dir).resolve(),
        session_id=args.session_id,
        system_prompt=base_prompt,
        skill_names=args.skill,
        config=MultiAgentConfig(
            max_research_cycles=args.max_research_cycles,
            max_writing_cycles=args.max_writing_cycles,
            researcher_max_turns=args.researcher_max_turns,
            evaluator_max_turns=args.evaluator_max_turns,
            writer_max_turns=args.writer_max_turns,
            evaluator_model=args.evaluator_model,
        ),
    )
    print(f"session_id={result.session_id}")
    print(f"session_dir={result.session_dir}")
    print(f"workspace_dir={result.workspace_dir}")
    print(f"stop_reason={result.stop_reason}")
    print(f"research_cycle_count={result.research_cycle_count}")
    print(f"writing_cycle_count={result.writing_cycle_count}")
    for index, writer_run_dir in enumerate(result.writer_run_dirs, start=1):
        print(f"writing_cycle_{index:03d}_run_dir={writer_run_dir}")
    for decision in result.decisions:
        print(f"research_cycle_{decision.cycle_index:03d}_decision={decision.decision}")
        print(f"research_cycle_{decision.cycle_index:03d}_decision_path={decision.decision_path}")
    if result.final_answer:
        print(result.final_answer)


if __name__ == "__main__":
    main()
