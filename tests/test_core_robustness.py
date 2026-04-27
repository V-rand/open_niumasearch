import pytest
import threading
import json
from pathlib import Path
from deep_research_agent.tools.archiver import ResearchArchiver
from deep_research_agent.tools.distiller import distill_evidence
from deep_research_agent.tools.plan import ResearchPlan

def test_archiver_concurrency(tmp_path):
    """Industrial Stress Test: Verify thread-safety of the index updater."""
    archiver = ResearchArchiver(tmp_path)
    num_threads = 10
    entries_per_thread = 5
    
    def worker(t_idx):
        for i in range(entries_per_thread):
            url = f"https://example.com/{t_idx}_{i}"
            archiver.update_index({
                "title": f"Thread {t_idx} Item {i}",
                "url": url,
                "summary": "Some summary content"
            })
            
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Verify: 10 * 5 = 50 unique entries should exist
    content = archiver.index_path.read_text()
    matches = content.count("### ")
    assert matches == 50, f"Expected 50 entries, found {matches}. Concurrency bug detected!"

def test_index_parsing_resilience(tmp_path):
    """Boundary Test: Verify parsing doesn't break with internal '###' markers."""
    archiver = ResearchArchiver(tmp_path)
    # Inject an entry where the summary contains markdown headers
    malicious_summary = "This is a summary\n### False Header\nMore content"
    archiver.update_index({
        "title": "Real Title",
        "url": "https://ok.com",
        "summary": malicious_summary
    })
    
    # Parse back
    entries = archiver._parse_index(archiver.index_path.read_text())
    assert len(entries) == 1
    assert entries[0]["title"] == "Real Title"
    assert "False Header" in entries[0]["summary"]

def test_distiller_truncation():
    """Boundary Test: Ensure the distiller doesn't send too much data."""
    class MockBackend:
        def complete_lite(self, messages, max_tokens=2000):
            # Check length of the last message (source_text)
            text_sent = messages[1]["content"]
            return f"Received length: {len(text_sent)}"

    backend = MockBackend()
    huge_text = "A" * 100000 # 100k chars
    res = distill_evidence(backend, huge_text, "test query")
    
    # Based on our logic: max_chars = 60000, half = 24000. 
    # Expected length roughly 48000 + some overhead
    assert len(huge_text) > 60000
    # The result from our mock should confirm that it didn't receive the full 100k
    assert "Received length" in res
    # Extract the length from mock response
    received_len = int(res.split(": ")[1])
    assert received_len < 60000

def test_plan_json_sync(tmp_path):
    """Integration Test: Plan state machine and Markdown mirroring."""
    plan = ResearchPlan(tmp_path)
    plan.data["sub_problems"] = [
        {"title": "Task 1", "status": "todo", "finding": "", "evidence_ref": ""}
    ]
    plan.save()
    
    # Check JSON
    assert (tmp_path / "research" / "plan.json").exists()
    
    # Check Markdown mirroring
    todo_md = (tmp_path / "todo.md").read_text()
    assert "### 1. Task 1" in todo_md
    assert "⏳" in todo_md
