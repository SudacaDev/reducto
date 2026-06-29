import sys
import asyncio
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from reducto.protocol.mcp_server import list_tools, call_tool, get_graph
import json

async def main():
    graph = get_graph()
    
    print("\n--- 1. Testing Infinite Loop Timeout ---")
    bad_skill_code = """
from reducto.skills.blueprint import ReductoSkill
import time

class InfiniteSkill(ReductoSkill):
    name = "infinite_loop"
    def execute(self, graph, args):
        while True:
            time.sleep(1)
"""
    res = await call_tool("save_autonomous_skill", {
        "skill_name": "infinite_loop",
        "python_code": bad_skill_code
    })
    print(json.loads(res[0].text))
    
    print("\nExecuting infinite_loop skill (this should timeout after ~15s)...")
    res = await call_tool("infinite_loop", {})
    print(json.loads(res[0].text))

if __name__ == "__main__":
    asyncio.run(main())
