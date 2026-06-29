import click
from pathlib import Path

@click.command()
def skill():
    """Output the agent SKILL.md template to stdout."""
    import sys
    
    skill_content = """---
name: reducto-graph
description: Query the Reducto knowledge graph to navigate massive codebases without blowing up your context window.
---

# Reducto Knowledge Graph

You have access to the `reducto` MCP server, which exposes the project's knowledge graph.
**Never try to `read_file` or `grep` large swaths of the codebase blindly.** 
Use Reducto to find exactly what you need.

## Workflow

1. **Search**: Call `search_context` with a technical concept (e.g. `auth`, `login`, `payment`).
   - Leave `resolve=false` first to see what exists.
   - You will get a list of nodes (Files, Classes, Functions).
2. **Explore Dependencies**: Call `get_dependencies` on a node ID to see what it imports/calls.
3. **Explore Callers**: Call `get_callers` on a node ID to see where it is used.
4. **Resolve**: Once you identify the specific node you need, call `search_context` again with `resolve=true` and `view="summary"` (for signatures) or `view="full"` (for the actual code).
"""
    print(skill_content)
    sys.exit(0)
