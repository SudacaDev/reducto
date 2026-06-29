import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reducto.protocol.mcp_server import list_tools, call_tool, get_graph
import json

async def main():
    # Force initialization
    graph = get_graph()
    
    print("--- 1. Initial Tools ---")
    tools = await list_tools()
    print([t.name for t in tools])
    
    print("\n--- 2. Saving new autonomous skill ---")
    skill_code = """
from reducto.skills.blueprint import ReductoSkill

class SayHelloSkill(ReductoSkill):
    name = "say_hello"
    description = "Says hello dynamically"
    input_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
    }

    def execute(self, graph, args):
        return {"greeting": f"Hello {args['name']}! The graph has {graph.g.number_of_nodes()} nodes."}
"""
    res = await call_tool("save_autonomous_skill", {
        "skill_name": "say_hello",
        "python_code": skill_code
    })
    print(json.loads(res[0].text))
    
    print("\n--- 3. Updated Tools (Hot-Reload) ---")
    tools = await list_tools()
    print([t.name for t in tools])
    
    print("\n--- 4. Executing Dynamic Skill ---")
    res = await call_tool("say_hello", {"name": "Reducto Master"})
    print(json.loads(res[0].text))

if __name__ == "__main__":
    asyncio.run(main())
