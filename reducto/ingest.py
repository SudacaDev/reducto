import click
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--clean", is_flag=True, default=False,
              help="Wipe the graph before ingesting (recommended after a cancelled/failed run)")
def ingest(path, clean):
    """Parse a directory and load it into the knowledge graph."""
    from reducto.engine.orchestrator import parse_directory
    from reducto.graph.core import ReductoGraph
    from reducto.__main__ import console, LOGO

    console.print(LOGO)
    root = Path(path).resolve()
    console.print(f"[bold]📂 Ingesting:[/bold] {root}\n")

    graph = ReductoGraph(project_root=root)
    graph.connect()

    if clean:
        graph.clear()
        known_hashes = None
        console.print("[dim]🧹 Graph cleared — full rebuild[/dim]\n")
    else:
        known_hashes = {
            attrs.get("file_path"): attrs.get("file_hash")
            for _, attrs in graph.g.nodes(data=True)
            if attrs.get("file_hash") and attrs.get("kind") == "File"
        }
        if known_hashes:
            console.print(f"[dim]♻️  Incremental mode — {len(known_hashes)} files cached[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing files...", total=None)
        results, skipped = parse_directory(root, known_hashes=known_hashes)
        desc = f"Parsed [cyan]{len(results)}[/cyan] files"
        if skipped:
            desc += f" ([dim]{skipped} unchanged, skipped[/dim])"
        progress.update(task, description=desc)

    total_nodes = sum(len(r.nodes) for r in results)
    total_edges = sum(len(r.edges) for r in results)

    if not results:
        console.print("[green]✓ Nothing changed — graph is up to date![/green]\n")
        graph.close()
        return

    console.print(f"\n[green]✓[/green] Found [cyan]{len(results)}[/cyan] files → "
                  f"[cyan]{total_nodes}[/cyan] nodes, [cyan]{total_edges}[/cyan] edges"
                  + (f" ([dim]{skipped} skipped[/dim])" if skipped else "") + "\n")

    console.print("[bold]💾 Loading local graph...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Loading graph (batched)...", total=total_nodes + total_edges)

        def on_progress(done, total):
            progress.update(task, completed=done)

        graph.ingest(results, progress_cb=on_progress)

    console.print("[dim]🔍 Detecting communities...[/dim]")
    communities = graph.detect_communities()
    n_communities = len(set(communities.values())) if communities else 0

    graph.close()

    console.print(Panel(
        f"[green]✓ Graph ready![/green]\n\n"
        f"  Files       : [cyan]{len(results)}[/cyan]\n"
        f"  Nodes       : [cyan]{total_nodes}[/cyan]\n"
        f"  Edges       : [cyan]{total_edges}[/cyan]\n"
        f"  Communities : [cyan]{n_communities}[/cyan]\n"
        f"  Saved to    : [cyan]{graph.graph_path.resolve()}[/cyan]\n\n"
        f"[dim]All nodes start as 🔴 unknown — they'll be resolved on demand (Schrödinger mode)[/dim]",
        title="[bold cyan]Reducto[/bold cyan]",
        border_style="cyan",
    ))

    try:
        from reducto.graph.visualize import generate_graph_html
        graph2 = ReductoGraph(project_root=root)
        graph2.connect()
        html_path = generate_graph_html(graph2, root / "reducto-out" / "graph.html")
        graph2.close()
        console.print(f"[dim]📊 Visual graph:[/dim] [cyan]{html_path.resolve()}[/cyan]\n")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not generate visualization:[/yellow] {e}")
        console.print(f"[dim]Run [cyan]reducto visualize[/cyan] manually to retry.[/dim]\n")

    console.print("\n[dim]Next:[/dim] [cyan]reducto serve[/cyan]  or  [cyan]reducto query \"your question\"[/cyan]\n")
