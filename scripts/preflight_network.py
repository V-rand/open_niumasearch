from __future__ import annotations

import argparse
import os
import sys

import httpx


DEFAULT_CHECKS = [
    ("dashscope_models", "https://dashscope.aliyuncs.com/compatible-mode/v1/models", {200, 401}),
    ("jina_reader", "https://r.jina.ai/http://example.com", {200}),
    ("tavily", "https://api.tavily.com", {200}),
]


def _mask(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return value[:4] + "..." + value[-4:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Network preflight checks before real eval runs.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--require-firecrawl-key", action="store_true")
    args = parser.parse_args()

    print("[preflight] key presence")
    key_map = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
        "JINA_API_KEY": os.getenv("JINA_API_KEY"),
        "FIRECRAWL_API_KEY": os.getenv("FIRECRAWL_API_KEY"),
        "HTTPS_PROXY": os.getenv("HTTPS_PROXY"),
        "HTTP_PROXY": os.getenv("HTTP_PROXY"),
    }
    for name, value in key_map.items():
        print(f"- {name}: {_mask(value)}")

    missing = [name for name in ("OPENAI_API_KEY", "TAVILY_API_KEY", "JINA_API_KEY") if not key_map[name]]
    if args.require_firecrawl_key and not key_map["FIRECRAWL_API_KEY"]:
        missing.append("FIRECRAWL_API_KEY")
    if missing:
        print(f"[preflight] FAIL missing required env: {', '.join(missing)}")
        return 2

    print("[preflight] endpoint checks")
    ok = True
    with httpx.Client(timeout=args.timeout_seconds, follow_redirects=True) as client:
        for name, url, accepted_codes in DEFAULT_CHECKS:
            try:
                response = client.get(url)
                passed = response.status_code in accepted_codes
                print(f"- {name}: status={response.status_code} {'OK' if passed else 'FAIL'}")
                if not passed:
                    ok = False
            except Exception as exc:
                print(f"- {name}: ERROR {type(exc).__name__}: {exc}")
                ok = False

    if not ok:
        print("[preflight] FAIL network preflight did not pass")
        return 3

    print("[preflight] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

