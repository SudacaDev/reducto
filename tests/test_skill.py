import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reducto.graph.core import ReductoGraph
from reducto.protocol.tools import handle_save_autonomous_skill
import json

graph = ReductoGraph()
graph.connect()

valid_skill = """
from reducto.skills.blueprint import ReductoSkill

class MySkill(ReductoSkill):
    name = "test_skill"
    def execute(self, graph, args):
        return "success"
"""

invalid_syntax_skill = """
from reducto.skills.blueprint import ReductoSkill
class MySkill(ReductoSkill
    def execute(self): pass
"""

missing_base_skill = """
class MySkill:
    def execute(self): pass
"""

print("--- Valid Skill ---")
res = handle_save_autonomous_skill(graph, {"skill_name": "valid_skill", "python_code": valid_skill})
print(json.loads(res[0].text))

print("\n--- Invalid Syntax Skill ---")
res = handle_save_autonomous_skill(graph, {"skill_name": "invalid", "python_code": invalid_syntax_skill})
print(json.loads(res[0].text))

print("\n--- Missing Base Class Skill ---")
res = handle_save_autonomous_skill(graph, {"skill_name": "missing", "python_code": missing_base_skill})
print(json.loads(res[0].text))

print("\nVerify file created:")
print(list((graph.root / ".reducto" / "skills").glob("*.py")))
