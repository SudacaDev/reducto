import click
from pathlib import Path

@click.command()
@click.argument("query_str", metavar="QUERY")
@click.option("--resolve", is_flag=True, default=False, help="Load source code of results")
@click.option("--limit", default=10, help="Max results")
def query(query_str, resolve, limit):
    """Search the knowledge graph directly from the terminal."""
    import json as _json
    from reducto.graph.core import ReductoGraph
    from reducto.protocol.tools import estimate_tokens, estimate_raw_file_tokens
    from reducto.__main__ import console, state_badge
    from rich.table import Table
    from rich import box

    graph = ReductoGraph()
    graph.connect()

    nodes = graph.search_by_name(query_str, limit=limit)

    if not nodes:
        console.print(f"[yellow]No results for:[/yellow] {query_str}")
        graph.update_session_stats(estimate_tokens(query_str), 0)
        graph.close()
        return

    table = Table(
        title=f'Results for "[cyan]{query_str}[/cyan]"',
        box=box.ROUNDED,
        border_style="cyan",
    )
    table.add_column("State", width=5)
    table.add_column("Kind", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("File", style="dim")
    table.add_column("Line", justify="right", style="dim")

    tokens_used  = estimate_tokens(_json.dumps(nodes))
    tokens_saved = 0

    for n in nodes:
        if resolve:
            full = graph.resolve_node(n["id"])
            if full:
                n = full
                tokens_used  += estimate_tokens(n.get("raw_source", ""))
                tokens_saved += estimate_raw_file_tokens(n.get("file_path", ""))
        table.add_row(
            state_badge(n.get("state", "unknown")),
            n.get("kind", "?"),
            n.get("name", "?"),
            Path(n.get("file_path", "")).name,
            str(n.get("start_line", "")),
        )
        if resolve and n.get("raw_source"):
            console.print(f"\n[dim]── {n['id']} ──[/dim]")
            console.print(n["raw_source"][:500] + ("..." if len(n.get("raw_source","")) > 500 else ""))

    console.print(table)
    graph.update_session_stats(tokens_used, max(0, tokens_saved - tokens_used))
    graph.close()
