import click
import asyncio
import sys

@click.command()
def serve():
    """Start the MCP server (connects to any LLM that supports MCP)."""
    print("Reducto MCP server starting...", file=sys.stderr)
    from reducto.protocol.mcp_server import run
    asyncio.run(run())
