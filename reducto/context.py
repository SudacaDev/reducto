import click
from rich.panel import Panel

@click.command()
def context():
    """Show token savings and graph health stats."""
    from reducto.graph.core import ReductoGraph
    from reducto.__main__ import console, LOGO

    graph = ReductoGraph()
    graph.connect()

    stats   = graph.get_stats()
    session = graph.get_session_stats()
    graph.close()

    total   = stats["total_nodes"]
    known   = stats["known"]
    partial = stats["partial"]
    unknown = stats["unknown"]

    tokens_used  = session.get("tokens_used",  0)
    tokens_saved = session.get("tokens_saved", 0)
    queries      = session.get("queries", 0)

    total_would_be = tokens_used + tokens_saved
    pct_saved = (tokens_saved / total_would_be * 100) if total_would_be > 0 else 0

    cost_saved = tokens_saved * 10 / 1_000_000

    console.print(LOGO)

    console.print(Panel(
        f"[bold]Tokens used[/bold]    : [cyan]{tokens_used:,}[/cyan]\n"
        f"[bold]Without Reducto[/bold]: [dim]{total_would_be:,}[/dim]\n"
        f"[bold]Tokens saved[/bold]   : [green]{tokens_saved:,}[/green]  "
        f"([green bold]{pct_saved:.1f}%[/green bold] 🔥)\n"
        f"[bold]Cost saved[/bold]     : [green]~${cost_saved:.4f}[/green] [dim](GPT-4o rate)[/dim]\n"
        f"[bold]Queries[/bold]        : [cyan]{queries}[/cyan]",
        title="[bold cyan]Session Stats[/bold cyan]",
        border_style="cyan",
    ))

    console.print(Panel(
        f"🔴 Unknown  (never read) : [red]{unknown}[/red] / {total}\n"
        f"🟡 Partial  (seen once)  : [yellow]{partial}[/yellow] / {total}\n"
        f"🟢 Known    (cached)     : [green]{known}[/green] / {total}\n"
        f"\n[bold]Total edges[/bold]: [cyan]{stats['total_edges']}[/cyan]",
        title="[bold cyan]Schrödinger Graph 🐱[/bold cyan]",
        border_style="dim",
    ))

    if known == 0:
        console.print("[dim]No nodes resolved yet. Start querying to warm up the cache.[/dim]\n")
