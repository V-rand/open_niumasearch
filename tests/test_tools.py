from __future__ import annotations

import json

from deep_research_agent.tools import ToolDefinition, ToolRegistry, build_builtin_tools


def test_tool_registry_rejects_missing_required_argument(is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="needs_name",
            description="Require a name.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=lambda arguments: arguments,
        )
    )

    result = registry.invoke("needs_name", {})

    assert result.is_error is True
    assert "Missing required arguments" in result.content


def test_builtin_filesystem_tools_roundtrip(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = build_builtin_tools(workspace_root=tmp_path)

    write_result = registry.invoke(
        "fs_write",
        {
            "path": "notes/example.md",
            "content": "# Title\nhello",
            "mode": "overwrite",
            "mkdir_parents": True,
        },
    )
    assert write_result.is_error is False

    read_result = registry.invoke("fs_read", {"path": "notes/example.md"})
    assert read_result.is_error is False
    assert "# Title" in read_result.content

    patch_result = registry.invoke(
        "fs_patch",
        {
            "path": "notes/example.md",
            "operation": "replace",
            "target": "hello",
            "content": "world",
            "occurrence": "first",
        },
    )
    assert patch_result.is_error is False

    updated = registry.invoke("fs_read", {"path": "notes/example.md"})
    assert "world" in updated.content


def test_build_builtin_tools_does_not_create_memory_file(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    build_builtin_tools(workspace_root=tmp_path)

    memory_path = tmp_path / "Memory.md"
    assert not memory_path.exists()


class _FakeResponse:
    def __init__(self, data: dict | None = None, text: str | None = None, status_code: int = 200) -> None:
        self._data = data
        self.text = text or ""
        self.status_code = status_code

    def json(self) -> dict:
        if self._data is None:
            raise AssertionError("No JSON payload configured")
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    def post(self, url: str, json: dict | None = None, headers: dict | None = None) -> _FakeResponse:
        self.calls.append(("POST", url, json, headers))
        if url.endswith("/api/v1/agent/parse/url"):
            return _FakeResponse(data={"code": 0, "data": {"task_id": "task-123"}, "msg": "ok"})
        raise AssertionError(f"Unexpected POST {url}")

    def get(self, url: str, headers: dict | None = None, **kwargs) -> _FakeResponse:
        self.calls.append(("GET", url, None, headers))
        if url.endswith("/api/v1/agent/parse/task-123"):
            poll_count = sum(1 for method, target, _, _ in self.calls if method == "GET" and target.endswith("/api/v1/agent/parse/task-123"))
            if poll_count == 1:
                return _FakeResponse(data={"code": 0, "data": {"state": "running"}})
            return _FakeResponse(
                data={
                    "code": 0,
                    "data": {
                        "state": "done",
                        "markdown_url": "https://cdn-mineru.example/full.md",
                    },
                }
            )
        if url == "https://cdn-mineru.example/full.md":
            return _FakeResponse(text="# Parsed PDF\n\nhello mineru")
        raise AssertionError(f"Unexpected GET {url}")


def test_mineru_parse_url_lightweight_fetches_markdown(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("MinerU_API_KEY", "dummy-token")
    fake_client = _FakeHttpClient()
    registry = build_builtin_tools(workspace_root=tmp_path, http_client=fake_client)

    result = registry.invoke(
        "mineru_parse_url",
        {
            "url": "https://arxiv.org/pdf/1706.03762.pdf",
            "mode": "lightweight",
            "poll_interval_seconds": 0,
            "max_polls": 3,
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["mode"] == "lightweight"
    assert payload["state"] == "done"
    assert payload["markdown"] == "# Parsed PDF\n\nhello mineru"
    assert payload["source_url"] == "https://arxiv.org/pdf/1706.03762.pdf"


def test_builtin_toolset_includes_mineru_guidance(tmp_path, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = build_builtin_tools(workspace_root=tmp_path)
    tools = {tool["function"]["name"]: tool["function"] for tool in registry.to_openai_tools()}

    assert "mineru_parse_url" in tools
    assert "PDF" in tools["mineru_parse_url"]["description"]
    assert "HTML" in tools["jina_reader"]["description"]
    assert "Firecrawl" in tools["jina_reader"]["description"]


def test_jina_reader_falls_back_to_firecrawl_when_jina_fails(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("JINA_API_KEY", "dummy-jina")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "dummy-firecrawl")

    class _FallbackHttpClient:
        def post(self, url: str, json: dict | None = None, headers: dict | None = None):  # type: ignore[no-untyped-def]
            if url == "https://r.jina.ai/":
                raise RuntimeError("jina ssl failed")
            if url == "https://api.firecrawl.dev/v2/scrape":
                assert headers is not None
                assert headers["Authorization"] == "Bearer dummy-firecrawl"
                assert json is not None
                assert json["formats"] == ["markdown"]
                return _FakeResponse(
                    data={
                        "success": True,
                        "data": {
                            "markdown": "# Firecrawl Content\n\nok",
                            "metadata": {"title": "Example Domain"},
                            "links": ["https://example.com"],
                            "images": [],
                        },
                    }
                )
            raise AssertionError(f"Unexpected URL {url}")

    registry = build_builtin_tools(workspace_root=tmp_path, http_client=_FallbackHttpClient())
    result = registry.invoke(
        "jina_reader",
        {
            "url": "https://example.com",
            "return_format": "markdown",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["provider"] == "firecrawl_fallback"
    assert "Firecrawl Content" in payload["content"]
    assert payload["fallback_reason"].startswith("RuntimeError:")


def test_jina_reader_fallback_accepts_legacy_firecrawl_env_key(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("JINA_API_KEY", "dummy-jina")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("firecraw_api_key", "legacy-firecrawl-key")

    class _LegacyFallbackHttpClient:
        def post(self, url: str, json: dict | None = None, headers: dict | None = None):  # type: ignore[no-untyped-def]
            if url == "https://r.jina.ai/":
                raise RuntimeError("jina ssl failed")
            if url == "https://api.firecrawl.dev/v2/scrape":
                assert headers is not None
                assert headers["Authorization"] == "Bearer legacy-firecrawl-key"
                return _FakeResponse(
                    data={
                        "success": True,
                        "data": {"markdown": "legacy fallback content", "metadata": {"title": "t"}},
                    }
                )
            raise AssertionError(f"Unexpected URL {url}")

    registry = build_builtin_tools(workspace_root=tmp_path, http_client=_LegacyFallbackHttpClient())
    result = registry.invoke("jina_reader", {"url": "https://example.com"})

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["provider"] == "firecrawl_fallback"
    assert "legacy fallback content" in payload["content"]


def test_web_search_uses_raw_query_without_runtime_rewrite(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("TAVILY_API_KEY", "dummy-token")

    class _WebSearchFakeClient:
        def __init__(self) -> None:
            self.last_payload: dict[str, object] | None = None

        def post(self, url: str, json: dict | None = None, headers: dict | None = None):  # type: ignore[no-untyped-def]
            assert url == "https://api.tavily.com/search"
            self.last_payload = json or {}
            return _FakeResponse(
                data={
                    "query": (json or {}).get("query"),
                    "answer": None,
                    "results": [{"title": "t", "url": "u", "content": "c", "score": 0.5}],
                }
            )

    fake_client = _WebSearchFakeClient()
    registry = build_builtin_tools(workspace_root=tmp_path, http_client=fake_client)
    query = "compare model A and B with official sources after 2025"
    result = registry.invoke(
        "web_search",
        {
            "query": query,
            "max_results": 3,
        },
    )

    assert result.is_error is False
    assert fake_client.last_payload is not None
    assert fake_client.last_payload["query"] == query

    payload = json.loads(result.content)
    assert payload["query"] == query
    assert "original_query" not in payload
    assert "query_strategy" not in payload


def test_web_search_can_keep_selected_results_in_source_index(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("TAVILY_API_KEY", "dummy-token")

    class _SearchKeepClient:
        def post(self, url: str, json: dict | None = None, headers: dict | None = None):  # type: ignore[no-untyped-def]
            assert url == "https://api.tavily.com/search"
            return _FakeResponse(
                data={
                    "query": (json or {}).get("query"),
                    "answer": None,
                    "results": [
                        {"title": "Source A", "url": "https://a.example.com", "content": "summary A", "score": 0.9},
                        {"title": "Source B", "url": "https://b.example.com", "content": "summary B", "score": 0.7},
                    ],
                }
            )

    registry = build_builtin_tools(workspace_root=tmp_path, http_client=_SearchKeepClient())
    result = registry.invoke(
        "web_search",
        {
            "query": "deep research source index",
            "keep_result_indices": [2],
            "keep_reason": "用于后续深入阅读",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["kept_sources"][0]["title"] == "Source B"
    index_text = (tmp_path / "research" / "source_index.md").read_text(encoding="utf-8")
    assert "Source B" in index_text
    assert "https://b.example.com" in index_text
    assert "用于后续深入阅读" in index_text


def test_jina_reader_archives_raw_source_and_updates_source_index(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    monkeypatch.setenv("JINA_API_KEY", "dummy-jina")

    class _ArchiveJinaClient:
        def post(self, url: str, json: dict | None = None, headers: dict | None = None):  # type: ignore[no-untyped-def]
            assert url == "https://r.jina.ai/"
            return _FakeResponse(
                data={
                    "data": {
                        "title": "Example Source Title",
                        "content": "# Example Source Title\n\nFull body",
                        "links": [],
                        "images": [],
                    }
                }
            )

    registry = build_builtin_tools(workspace_root=tmp_path, http_client=_ArchiveJinaClient())
    result = registry.invoke("jina_reader", {"url": "https://example.com/page"})

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["raw_path"].startswith("research/raw/Example Source Title")
    raw_text = (tmp_path / payload["raw_path"]).read_text(encoding="utf-8")
    assert "url: https://example.com/page" in raw_text
    assert "Full body" in raw_text
    index_text = (tmp_path / "research" / "source_index.md").read_text(encoding="utf-8")
    assert "Example Source Title" in index_text
    assert payload["raw_path"] in index_text


class _FakeArxivPaper:
    def __init__(self, paper_id: str, title: str = "Attention Is All You Need") -> None:
        self.entry_id = f"http://arxiv.org/abs/{paper_id}v1"
        self.title = title
        self.summary = "Transformer paper summary"
        self.pdf_url = f"http://arxiv.org/pdf/{paper_id}.pdf"
        self.published = "2017-06-12"
        self.updated = "2017-06-12"
        self.authors = ["Ashish Vaswani", "Noam Shazeer"]
        self._paper_id = paper_id

    def download_pdf(self, dirpath: str, filename: str) -> str:
        path = tmp_path_for_fake_arxiv / dirpath / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf")
        return str(path)


class _FakeArxivClient:
    def __init__(self, paper: _FakeArxivPaper) -> None:
        self.paper = paper

    def results(self, search: object):
        return iter([self.paper])


class _FakeArxivModule:
    def __init__(self, paper: _FakeArxivPaper) -> None:
        self._paper = paper

    class SortCriterion:
        Relevance = "relevance"
        LastUpdatedDate = "lastUpdatedDate"
        SubmittedDate = "submittedDate"

    class SortOrder:
        Ascending = "ascending"
        Descending = "descending"

    def Search(self, **kwargs):
        return kwargs

    def Client(self):
        return _FakeArxivClient(self._paper)


tmp_path_for_fake_arxiv = None


def test_arxiv_read_paper_downloads_and_parses_markdown(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    global tmp_path_for_fake_arxiv
    tmp_path_for_fake_arxiv = tmp_path

    fake_paper = _FakeArxivPaper("1706.03762")
    fake_arxiv = _FakeArxivModule(fake_paper)

    def fake_parser(pdf_path: str) -> str:
        assert pdf_path.endswith(".pdf")
        return "# Parsed arXiv Paper\n\ntransformers"

    monkeypatch.setattr("deep_research_agent.tools._import_arxiv", lambda: fake_arxiv)
    monkeypatch.setattr("deep_research_agent.tools._import_pymupdf4llm", lambda: type("FakeModule", (), {"to_markdown": staticmethod(fake_parser)})())

    registry = build_builtin_tools(workspace_root=tmp_path)
    result = registry.invoke(
        "arxiv_read_paper",
        {
            "paper_ref": "https://arxiv.org/abs/1706.03762",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["paper_id"] == "1706.03762"
    assert payload["title"] == "Attention Is All You Need"
    assert payload["markdown_path"].endswith("documents/1706.03762.md")
    assert payload["pdf_path"].endswith("documents/1706.03762.pdf")
    markdown_file = tmp_path / payload["markdown_path"]
    assert markdown_file.read_text(encoding="utf-8") == "# Parsed arXiv Paper\n\ntransformers"


def test_arxiv_search_returns_metadata_list(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    fake_paper = _FakeArxivPaper("1706.03762")
    fake_arxiv = _FakeArxivModule(fake_paper)
    monkeypatch.setattr("deep_research_agent.tools._import_arxiv", lambda: fake_arxiv)

    registry = build_builtin_tools(workspace_root=tmp_path)
    result = registry.invoke(
        "arxiv_search",
        {
            "query": "transformer attention",
            "max_results": 3,
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["query"] == "transformer attention"
    assert payload["results"][0]["paper_id"] == "1706.03762"


def test_arxiv_search_can_keep_selected_results_into_source_index(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    fake_paper = _FakeArxivPaper("1706.03762", title="Attention Is All You Need")
    fake_arxiv = _FakeArxivModule(fake_paper)
    monkeypatch.setattr("deep_research_agent.tools._import_arxiv", lambda: fake_arxiv)

    registry = build_builtin_tools(workspace_root=tmp_path)
    result = registry.invoke(
        "arxiv_search",
        {
            "query": "transformer attention",
            "max_results": 3,
            "keep_result_indices": [1],
            "keep_reason": "原始论文，后续需要深读",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["kept_sources"][0]["title"] == "Attention Is All You Need"
    index_text = (tmp_path / "research" / "source_index.md").read_text(encoding="utf-8")
    assert "Attention Is All You Need" in index_text
    assert "why_keep: 原始论文，后续需要深读" in index_text


def test_pdf_read_url_falls_back_to_local_parser(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    fake_client = _FakeHttpClient()
    registry = build_builtin_tools(workspace_root=tmp_path, http_client=fake_client)

    monkeypatch.setattr(
        "deep_research_agent.tools._mineru_parse_url_lightweight",
        lambda arguments, http_client: {
            "mode": "lightweight",
            "source_url": arguments["url"],
            "state": "failed",
            "error": "temporary mineru failure",
        },
    )
    monkeypatch.setattr(
        "deep_research_agent.tools._download_pdf_to_workspace",
        lambda *, url, workspace_root, http_client, filename_hint=None: tmp_path / "documents" / "paper.pdf",
    )
    (tmp_path / "documents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "documents" / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        "deep_research_agent.tools._import_pymupdf4llm",
        lambda: type("FakeModule", (), {"to_markdown": staticmethod(lambda path: "# Local PDF\n\nfallback")})(),
    )

    result = registry.invoke(
        "pdf_read_url",
        {
            "url": "https://example.com/paper.pdf",
            "strategy": "mineru_first",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["method"] == "local_pymupdf4llm"
    assert payload["fallback_used"] is True
    assert payload["mineru_error"] == "temporary mineru failure"
    assert payload["markdown_preview"] == "# Local PDF\n\nfallback"


def test_pdf_read_url_can_return_mineru_result_without_fallback(tmp_path, monkeypatch, is_fast_mode: bool) -> None:
    if is_fast_mode:
        pass

    registry = build_builtin_tools(workspace_root=tmp_path)
    monkeypatch.setattr(
        "deep_research_agent.tools._mineru_parse_url_lightweight",
        lambda arguments, http_client: {
            "mode": "lightweight",
            "source_url": arguments["url"],
            "state": "done",
            "markdown_url": "https://cdn-mineru.example/full.md",
            "markdown": "# MinerU PDF\n\nsuccess",
        },
    )

    result = registry.invoke(
        "pdf_read_url",
        {
            "url": "https://example.com/paper.pdf",
            "strategy": "mineru_first",
        },
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["method"] == "mineru"
    assert payload["fallback_used"] is False
    assert payload["markdown_preview"] == "# MinerU PDF\n\nsuccess"
