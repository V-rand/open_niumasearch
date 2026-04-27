import asyncio
import os
import json
import shutil
from pathlib import Path
from deep_research_agent.tools.core import ToolRegistry
from deep_research_agent.tools.law_expert import register_law_expert_tools
from deep_research_agent.tools.archiver import ResearchArchiver
from dotenv import load_dotenv

load_dotenv()

async def run_validation():
    print("🚀 Starting Infrastructure Validation...")
    
    # 1. Setup temporary test workspace
    test_workspace = Path("./infra_test_workspace")
    if test_workspace.exists():
        shutil.rmtree(test_workspace)
    test_workspace.mkdir(parents=True)
    
    registry = ToolRegistry()
    register_law_expert_tools(registry, test_workspace)
    
    archiver = ResearchArchiver(test_workspace)
    
    # 2. Test Case Retrieval (The one that failed earlier)
    print("\n--- Testing Case Retrieval ---")
    case_tool = registry.get_tool("case_retrieve")
    try:
        results = case_tool.handler({"query": "外卖骑手 劳动关系认定", "top_k": 2})
        print(f"✅ API Response Received: {results.get('status')}")
        
        if results.get("status") == "success":
            count = results.get("count", 0)
            print(f"📊 Found {count} cases.")
            
            # Verify Physical Files
            raw_dir = test_workspace / "research" / "raw"
            files = list(raw_dir.glob("*.md"))
            print(f"📁 Physical Files Created: {len(files)}")
            
            if len(files) > 0:
                print(f"📄 Sample File: {files[0].name}")
                # Check source_id / raw_path consistency
                sample_res = results['results'][0]
                print(f"🔗 Tool Output 'raw_path': {sample_res.get('raw_path')}")
                if sample_res.get('raw_path') and os.path.exists(sample_res.get('raw_path')):
                    print("✨ ALL OK: Physical evidence linked successfully.")
                else:
                    print("❌ ERROR: Linked path does not exist!")
        else:
            print(f"❌ ERROR: API failed with {results.get('message')}")
            
    except Exception as e:
        print(f"💥 CRITICAL: Handler crashed: {e}")

    # 3. Test Law Retrieval
    print("\n--- Testing Law Retrieval ---")
    law_tool = registry.get_tool("law_retrieve")
    results = law_tool.handler({"query": "劳动合同法 第七条", "top_k": 1})
    if results.get("status") == "success":
        print(f"✅ Law Retrieval OK. Found: {results['results'][0]['title']}")
    else:
        print(f"❌ Law Retrieval Failed: {results.get('message')}")

    # Cleanup if needed
    # shutil.rmtree(test_workspace)

if __name__ == "__main__":
    asyncio.run(run_validation())
