from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from deep_research_agent.tools.base import ToolDefinition, ToolRegistry
from deep_research_agent.tools.file_system import register_file_system_tools
from deep_research_agent.tools.web import register_web_tools
from deep_research_agent.tools.search import register_unified_search_tools
from deep_research_agent.tools.pdf import register_pdf_tools
from deep_research_agent.tools.mineru import register_mineru_tools
from deep_research_agent.tools.plan import register_plan_tools
from deep_research_agent.tools.law_expert import register_law_expert_tools
from deep_research_agent.dashscope_backend import ModelBackend


class _FallbackModelBackend:
    """Safe fallback backend for tool-level distillation when no model is wired."""

    def complete_lite(self, messages: list[dict[str, Any]], max_tokens: int = 2000) -> str:
        if not messages:
            return ""
        last_content = str(messages[-1].get("content") or "")
        return last_content[: min(len(last_content), max_tokens)]


def build_builtin_tools(
    workspace_root: Path,
    model_backend: ModelBackend | None = None,
    http_client: httpx.Client | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    workspace_root = Path(workspace_root).resolve()
    http_client = http_client or httpx.Client(timeout=60.0, trust_env=True)
    effective_model_backend = model_backend or _FallbackModelBackend()

    # 1. Strategy & State Management
    register_plan_tools(registry, workspace_root)
    
    # 2. Discovery & Retrieval
    register_unified_search_tools(registry, workspace_root, http_client)
    register_web_tools(registry, workspace_root, http_client, effective_model_backend)
    register_law_expert_tools(registry, workspace_root)
    
    # 2. Document & Image OCR
    register_pdf_tools(registry, workspace_root, http_client, effective_model_backend)
    register_mineru_tools(registry, http_client, effective_model_backend, workspace_root)
    
    # 3. Working Memory Management
    register_file_system_tools(registry, workspace_root)

    return registry


__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "build_builtin_tools",
]
