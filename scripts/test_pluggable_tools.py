from pathlib import Path
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

from deep_research_agent.tools.archiver import ResearchArchiver
from deep_research_agent.tools.distiller import distill_evidence
from deep_research_agent.tools.web import fetch_and_distill_web
from deep_research_agent.dashscope_backend import DashScopeOpenAIBackend

def test_archiver(tmp_root: Path):
    print("Testing Archiver...")
    archiver = ResearchArchiver(tmp_root)
    res = archiver.archive_raw("Test Page", "https://example.com", "Hello World", "test")
    assert (tmp_root / res["raw_path"]).exists()
    print("✅ Archiver OK")

def test_distiller():
    print("Testing Distiller...")
    backend = DashScopeOpenAIBackend()
    text = "Apple was founded by Steve Jobs and Steve Wozniak in 1976."
    res = distill_evidence(backend, text, "Who founded Apple?")
    assert "Jobs" in res
    print("✅ Distiller OK")

def test_web_standalone(tmp_root: Path):
    print("Testing Web Standalone...")
    archiver = ResearchArchiver(tmp_root)
    backend = DashScopeOpenAIBackend()
    with httpx.Client() as client:
        res = fetch_and_distill_web(
            url="https://example.com",
            archiver=archiver,
            model_backend=backend,
            http_client=client,
            focus_query="What is the domain name?"
        )
        assert "example.com" in res["evidence"].lower()
    print("✅ Web Standalone OK")

if __name__ == "__main__":
    tmp = Path("./test_workspace")
    tmp.mkdir(exist_ok=True)
    try:
        test_archiver(tmp)
        test_distiller()
        test_web_standalone(tmp)
        print("\n🎉 ALL PLUGGABLE TESTS PASSED")
    finally:
        # Cleanup can be added here
        pass
