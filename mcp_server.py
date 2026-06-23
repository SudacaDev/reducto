"""
reducto.mcp_server
------------------
MCP server que expone el knowledge graph a cualquier LLM.
Tools: search_context, get_dependencies, get_callers
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from reducto.graph import ReductoGraph

# ---------------------------------------------------------------------------
# Estimación de tokens (aproximación: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def estimate_raw_file_tokens(file_path: str) -> int:
    try:
        from pathlib import Path
        size = len(Path(file_path).read_text(errors="replace"))
        return size // 4
    except Exception:
        return 4000  # fallback conservador

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

server = Server("reducto")
_graph: ReductoGraph | None = None

def get_graph() -> ReductoGraph:
    global _graph
    if _graph is None:
        _graph = ReductoGraph()
        _graph.connect()
    return _graph


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="search_context",
        description=(
            "Search the knowledge graph for code nodes by name or concept. "
            "IMPORTANT: Always search using English technical terms from the codebase "
            "(e.g. 'auth', 'user', 'payment') NOT the user's natural language query. "
            "For example, if the user asks about 'autenticación', search 'auth'. "
            "Returns only relevant nodes — NOT the entire file. "
            "Use 'resolve' + 'view' to load code only when needed:\n"
            "  - view='signature' (cheap, ~20 tokens) — just function signature\n"
            "  - view='summary'   (medium, ~100 tokens) — signature + docstring\n"
            "  - view='full'      (expensive, full source) — only when you need the actual code\n"
            "Try multiple short queries if the first returns nothing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name or concept to search (e.g. 'auth', 'process_payment')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10)",
                    "default": 10,
                },
                "resolve": {
                    "type": "boolean",
                    "description": "If true, load content of matching nodes (per 'view')",
                    "default": False,
                },
                "view": {
                    "type": "string",
                    "enum": ["signature", "summary", "full"],
                    "description": "Level of detail to return when resolve=true",
                    "default": "summary",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_dependencies",
        description=(
            "Get everything a file or function imports or calls. "
            "Use this to understand what a node depends on without reading all files."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Node ID from search_context results (e.g. 'src/auth.py::login')",
                },
            },
            "required": ["node_id"],
        },
    ),
    Tool(
        name="get_callers",
        description=(
            "Find what depends on a file/function/class — what imports it, "
            "or (once call-graph extraction is added) what calls it. "
            "Useful for impact analysis: 'what breaks if I change this?'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Node ID of the file/function/class to analyze",
                },
            },
            "required": ["node_id"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    graph = get_graph()

    if name == "search_context":
        query   = arguments["query"]
        limit   = arguments.get("limit", 10)
        resolve = arguments.get("resolve", False)
        view    = arguments.get("view", "summary")

        nodes = graph.search_by_name(query, limit=limit)

        if resolve:
            resolved = []
            tokens_used  = 0
            tokens_saved = 0
            for n in nodes:
                full = graph.resolve_node(n["id"], view=view)
                if full:
                    content = full.get("content") or full.get("raw_source", "")
                    tokens_used  += estimate_tokens(content)
                    tokens_saved += estimate_raw_file_tokens(full.get("file_path", ""))
                    resolved.append(full)
            graph.update_session_stats(tokens_used, tokens_saved - tokens_used)
            payload = {"nodes": resolved, "view": view, "tokens_used": tokens_used, "tokens_saved": tokens_saved}
        else:
            # Sin resolve: solo metadata, prácticamente 0 tokens
            tokens_used  = estimate_tokens(json.dumps(nodes))
            tokens_saved = sum(
                estimate_raw_file_tokens(n.get("file_path", ""))
                for n in nodes
            )
            graph.update_session_stats(tokens_used, tokens_saved - tokens_used)
            payload = {"nodes": nodes, "tokens_used": tokens_used, "tokens_saved": tokens_saved}

        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    elif name == "get_dependencies":
        node_id = arguments["node_id"]
        deps    = graph.get_dependencies(node_id)
        tokens_used  = estimate_tokens(json.dumps(deps))
        graph.update_session_stats(tokens_used, 0)
        return [TextContent(type="text", text=json.dumps({"dependencies": deps}, indent=2))]

    elif name == "get_callers":
        node_id = arguments["node_id"]
        callers = graph.get_callers(node_id)
        tokens_used = estimate_tokens(json.dumps(callers))
        graph.update_session_stats(tokens_used, 0)
        return [TextContent(type="text", text=json.dumps({"callers": callers}, indent=2))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
