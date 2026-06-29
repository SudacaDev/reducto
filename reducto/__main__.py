"""
reducto.__main__
----------------
CLI de Reducto (Entrypoint principal).
"""

import click
from rich.console import Console

console = Console()

LOGO = """
[bold cyan]
  ██████╗ ███████╗██████╗ ██╗   ██╗ ██████╗████████╗ ██████╗ 
  ██╔══██╗██╔════╝██╔══██╗██║   ██║██╔════╝╚══██╔══╝██╔═══██╗
  ██████╔╝█████╗  ██║  ██║██║   ██║██║        ██║   ██║   ██║
  ██╔══██╗██╔══╝  ██║  ██║██║   ██║██║        ██║   ██║   ██║
  ██║  ██║███████╗██████╔╝╚██████╔╝╚██████╗   ██║   ╚██████╔╝
  ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ 
[/bold cyan]
[dim]Universal knowledge graph for LLMs — reduce tokens, not intelligence.[/dim]
"""

def state_badge(state: str) -> str:
    return {"known": "🟢", "partial": "🟡", "unknown": "🔴"}.get(state, "⚪")

@click.group()
def cli():
    """Reducto — Universal knowledge graph for LLMs."""
    pass

# Register commands
from reducto.ingest import ingest
from reducto.serve import serve
from reducto.visualize_cmd import visualize
from reducto.export import export_graph
from reducto.install import install
from reducto.query import query
from reducto.context import context
from reducto.skill import skill

cli.add_command(ingest)
cli.add_command(serve)
cli.add_command(visualize)
cli.add_command(export_graph, name="export")
cli.add_command(install)
cli.add_command(query)
cli.add_command(context)
cli.add_command(skill)

if __name__ == "__main__":
    cli()
