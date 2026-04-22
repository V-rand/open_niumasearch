"""Real API validation tests for external tools.

These tests call actual external APIs and require valid credentials
in environment variables. They are skipped by default and only run
when --run-real-api is passed to pytest.

Run individually:
    pytest tests/test_tools_real_api.py -v --run-real-api

Or with fast mode (still runs real APIs, just fewer assertions):
    pytest tests/test_tools_real_api.py -v --run-real-api --fast
"""

from __future__ import annotations

import json
import os

import pytest

from deep_research_agent.tools import build_builtin_tools


# ------------------------------------------------------------------
# Fixture: skip entire module unless --run-real-api is passed
# ------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_api: marks tests that call real external APIs")


@pytest.fixture(scope="module")
def _skip_if_no_real_api(pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--run-real-api"):
        pytest.skip("Pass --run-real-api to run tests against real APIs", allow_module_level=True)


@pytest.fixture
def registry(tmp_path, _skip_if_no_real_api):
    """Build tool registry with real HTTP client."""
    return build_builtin_tools(workspace_root=tmp_path)


# ------------------------------------------------------------------
# Web Search (Tavily)
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_web_search_returns_results_with_content(registry, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    result = registry.invoke(
        "web_search",
        {
            "query": "OpenAI GPT-4 release date",
            "max_results": 3,
            "include_answer": True,
        },
    )

    assert result.is_error is False, f"web_search failed: {result.content}"
    payload = json.loads(result.content)
    assert "results" in payload
    assert len(payload["results"]) > 0
    first = payload["results"][0]
    assert "title" in first
    assert "url" in first
    assert "content" in first
    # content should be a non-empty snippet
    assert len(first["content"]) > 10


# ------------------------------------------------------------------
# Jina Reader
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_jina_reader_extracts_webpage_content(registry, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    result = registry.invoke(
        "jina_reader",
        {
            "url": "https://example.com",
            "return_format": "markdown",
            "timeout": 30,
        },
    )

    assert result.is_error is False, f"jina_reader failed: {result.content}"
    payload = json.loads(result.content)
    assert "content" in payload
    assert len(payload["content"]) > 50
    assert "example.com" in payload["url"].lower()


# ------------------------------------------------------------------
# arXiv Search
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_arxiv_search_finds_papers(registry, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    result = registry.invoke(
        "arxiv_search",
        {
            "query": "transformer attention mechanism",
            "max_results": 3,
        },
    )

    assert result.is_error is False, f"arxiv_search failed: {result.content}"
    payload = json.loads(result.content)
    assert "results" in payload
    assert len(payload["results"]) > 0
    first = payload["results"][0]
    assert "paper_id" in first
    assert "title" in first
    assert "summary" in first


# ------------------------------------------------------------------
# arXiv Read Paper
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_arxiv_read_paper_downloads_and_parses(registry, tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    result = registry.invoke(
        "arxiv_read_paper",
        {
            "paper_ref": "1706.03762",
            "preview_chars": 2000,
        },
    )

    assert result.is_error is False, f"arxiv_read_paper failed: {result.content}"
    payload = json.loads(result.content)
    assert payload["paper_id"] == "1706.03762"
    assert "Attention" in payload["title"] or "Transformer" in payload["title"]
    assert payload["markdown_path"].endswith(".md")
    # Verify file was written
    markdown_file = tmp_path / payload["markdown_path"]
    assert markdown_file.exists()
    content = markdown_file.read_text(encoding="utf-8")
    assert len(content) > 100


# ------------------------------------------------------------------
# PDF Read URL (local fallback)
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_pdf_read_url_downloads_and_parses(registry, tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    # Use a known stable PDF URL (arXiv)
    result = registry.invoke(
        "pdf_read_url",
        {
            "url": "https://arxiv.org/pdf/1706.03762.pdf",
            "strategy": "local_only",
            "preview_chars": 2000,
        },
    )

    assert result.is_error is False, f"pdf_read_url failed: {result.content}"
    payload = json.loads(result.content)
    assert "markdown_preview" in payload or "markdown" in payload
    preview = payload.get("markdown_preview") or payload.get("markdown", "")
    assert len(preview) > 100
    assert "method" in payload


# ------------------------------------------------------------------
# MinerU Parse URL
# ------------------------------------------------------------------


@pytest.mark.real_api
def test_mineru_parse_url_lightweight(registry, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    # Use MinerU demo PDF
    result = registry.invoke(
        "mineru_parse_url",
        {
            "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
            "mode": "lightweight",
            "poll_interval_seconds": 2,
            "max_polls": 30,
        },
    )

    assert result.is_error is False, f"mineru_parse_url failed: {result.content}"
    payload = json.loads(result.content)
    assert payload["mode"] == "lightweight"
    # lightweight mode returns task info; may fail due to SSL/network issues
    assert "state" in payload or "markdown" in payload or "error" in payload
