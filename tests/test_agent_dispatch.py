import pytest
from deep_research_agent.agent import ReActAgent
from deep_research_agent.models import ToolCall, AgentConfig

def test_agent_tool_dispatch_deduplication():
    """Verify parallel tool calls are deduplicated but results are mapped back."""
    class MockRegistry:
        def __init__(self):
            self.call_count = 0
            self._tools = {}
        def invoke(self, name, arguments, call_id):
            self.call_count += 1
            return type('Obj', (object,), {'content': f"Result for {arguments['url']}", 'is_error': False, 'call_id': call_id, 'name': name})()
            
    registry = MockRegistry()
    agent = ReActAgent(model_backend=None, tool_registry=registry)
    
    # Simulate 3 tool calls, 2 to the same URL
    calls = [
        ToolCall(id="c1", name="jina_reader", arguments={"url": "siteA"}),
        ToolCall(id="c2", name="jina_reader", arguments={"url": "siteA"}),
        ToolCall(id="c3", name="jina_reader", arguments={"url": "siteB"}),
    ]
    
    results = agent._dispatch_tool_calls(calls)
    
    # 1. Check mapping: each call must have its result
    assert len(results) == 3
    assert results[0].call_id == "c1"
    assert results[1].call_id == "c2"
    assert results[2].call_id == "c3"
    
    # 2. Check deduplication: only 2 actual calls should have reached the registry
    assert registry.call_count == 2
    
    # 3. Check content: deduplicated result should mention it was deduped
    assert "Result for siteA" in results[0].content
    assert "(Deduplicated)" in results[1].content
    assert "Result for siteB" in results[2].content
