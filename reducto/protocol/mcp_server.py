"""
reducto.protocol.mcp_server
---------------------------
MCP server que expone el knowledge graph a cualquier LLM.
"""

from __future__ import annotations

import json
import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from reducto.graph.core import ReductoGraph
from reducto.protocol.tools import (
    TOOLS,
    handle_search_context,
    handle_get_dependencies,
    handle_get_callers,
    handle_save_autonomous_skill
)

server = Server("reducto")
_graph: ReductoGraph | None = None

def get_graph() -> ReductoGraph:
    global _graph
    if _graph is None:
        _graph = ReductoGraph()
        _graph.connect()
    return _graph

@server.list_tools()
async def list_tools() -> list[Tool]:
    graph = get_graph()
    dynamic_tools = []
    for skill in graph.skills_registry.values():
        dynamic_tools.append(Tool(
            name=skill.name,
            description=skill.description,
            inputSchema=skill.input_schema
        ))
    return TOOLS + dynamic_tools

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    graph = get_graph()

    if name in graph.skills_registry:
        skill = graph.skills_registry[name]
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(skill.execute, graph, arguments),
                timeout=15.0
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except asyncio.TimeoutError:
            return [TextContent(type="text", text=json.dumps({
                "error": f"TimeoutError: Skill '{name}' exceeded the 15-second execution limit and was terminated."
            }, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({
                "error": f"Error executing skill '{name}'",
                "details": str(e)
            }, indent=2))]

    if name == "search_context":
        return handle_search_context(graph, arguments)

    elif name == "get_dependencies":
        return handle_get_dependencies(graph, arguments)

    elif name == "get_callers":
        return handle_get_callers(graph, arguments)
        
    elif name == "save_autonomous_skill":
        return handle_save_autonomous_skill(graph, arguments)

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

async def run():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
