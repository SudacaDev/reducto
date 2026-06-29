import click
from pathlib import Path
import sys

@click.command()
def visualize():
    """Generar una visualización interactiva del grafo actual."""
    from reducto.graph.core import ReductoGraph
    from reducto.__main__ import console
    try:
        from reducto.graph.visualize import generate_graph_html
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import visualize module. {e}")
        sys.exit(1)

    graph = ReductoGraph()
    graph.connect()

    if graph.g.number_of_nodes() == 0:
        console.print("[yellow]Grafo vacío. Corre `reducto ingest .` primero.[/yellow]")
        return

    console.print(f"[dim]Generando HTML interactivo con {graph.g.number_of_nodes()} nodos...[/dim]")
    out_path = graph.out_dir / "graph.html"
    try:
        generate_graph_html(graph, out_path)
        console.print(f"[green]✓ Visualización guardada en:[/green] [cyan]{out_path.resolve()}[/cyan]")
    except Exception as e:
        console.print(f"[red]Error al generar HTML:[/red] {e}")
    finally:
        graph.close()
