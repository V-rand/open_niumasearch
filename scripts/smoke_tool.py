from __future__ import annotations

import argparse
import json
from pathlib import Path

from deep_research_agent.tools import build_builtin_tools


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a single built-in tool.")
    parser.add_argument("tool_name", choices=["web_search", "jina_reader", "mineru_parse_url", "arxiv_search", "arxiv_read_paper", "pdf_read_url"])
    parser.add_argument("--query", help="Query for web_search.")
    parser.add_argument("--url", help="URL for jina_reader, mineru_parse_url, or pdf_read_url.")
    parser.add_argument("--paper-ref", help="Paper id or arXiv URL for arxiv_read_paper.")
    parser.add_argument(
        "--mode",
        default="lightweight",
        choices=["lightweight", "precise"],
        help="Mode for mineru_parse_url.",
    )
    parser.add_argument(
        "--strategy",
        default="local_only",
        choices=["mineru_first", "mineru_only", "local_only"],
        help="Strategy for pdf_read_url.",
    )
    args = parser.parse_args()

    registry = build_builtin_tools(Path(".").resolve())

    if args.tool_name == "web_search":
        if not args.query:
            raise SystemExit("--query is required for web_search")
        result = registry.invoke(
            "web_search",
            {
                "query": args.query,
                "search_depth": "basic",
                "topic": "general",
                "max_results": 3,
            },
        )
    elif args.tool_name == "jina_reader":
        if not args.url:
            raise SystemExit("--url is required for jina_reader")
        result = registry.invoke(
            "jina_reader",
            {
                "url": args.url,
                "return_format": "markdown",
                "timeout": 30,
            },
        )
    elif args.tool_name == "mineru_parse_url":
        if not args.url:
            raise SystemExit("--url is required for mineru_parse_url")
        result = registry.invoke(
            "mineru_parse_url",
            {
                "url": args.url,
                "mode": args.mode,
                "poll_interval_seconds": 1,
                "max_polls": 20,
            },
        )
    elif args.tool_name == "arxiv_search":
        if not args.query:
            raise SystemExit("--query is required for arxiv_search")
        result = registry.invoke(
            "arxiv_search",
            {
                "query": args.query,
                "max_results": 3,
            },
        )
    elif args.tool_name == "pdf_read_url":
        if not args.url:
            raise SystemExit("--url is required for pdf_read_url")
        result = registry.invoke(
            "pdf_read_url",
            {
                "url": args.url,
                "strategy": args.strategy,
            },
        )
    else:
        if not args.paper_ref:
            raise SystemExit("--paper-ref is required for arxiv_read_paper")
        result = registry.invoke(
            "arxiv_read_paper",
            {
                "paper_ref": args.paper_ref,
            },
        )

    print(
        json.dumps(
            {
                "tool_name": args.tool_name,
                "is_error": result.is_error,
                "preview": result.content[:800],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
