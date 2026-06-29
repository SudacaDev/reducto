import click
from pathlib import Path
from rich.panel import Panel

@click.command(name="export")
@click.option("--target", default="obsidian",
              type=click.Choice(["obsidian"], case_sensitive=False),
              help="Export format (default: obsidian)")
@click.option("--out", default=None, help="Output directory")
def export_graph(target, out):
    """Export the knowledge graph to other formats."""
    from reducto.graph.core import ReductoGraph
    from reducto.__main__ import console

    graph = ReductoGraph()
    graph.connect()

    if target == "obsidian":
        out_dir = Path(out) if out else graph.out_dir / "obsidian-vault"
        out_dir.mkdir(parents=True, exist_ok=True)

        node_names: dict[str, str] = {}
        for node_id, attrs in graph.g.nodes(data=True):
            name = attrs.get("name") or node_id.split("/")[-1]
            kind = attrs.get("kind", "")
            safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("<", "").replace(">", "")
            if safe_name in node_names.values():
                safe_name = f"{safe_name} ({kind})"
            node_names[node_id] = safe_name

        count = 0
        for node_id, attrs in graph.g.nodes(data=True):
            name = node_names[node_id]
            kind = attrs.get("kind", "File")
            state = attrs.get("state", "unknown")
            file_path = attrs.get("file_path", "")
            start_line = attrs.get("start_line", "")
            community = attrs.get("community", -1)

            lines = []
            lines.append(f"# {name}")
            lines.append("")
            lines.append(f"**Kind:** {kind}  ")
            lines.append(f"**State:** {state}  ")
            if file_path:
                lines.append(f"**File:** `{file_path}`  ")
            if start_line:
                lines.append(f"**Line:** {start_line}  ")
            if community >= 0:
                lines.append(f"**Community:** {community}  ")
            lines.append("")

            views = attrs.get("views")
            if isinstance(views, dict) and views.get("signature"):
                lines.append("## Signature")
                lines.append("```")
                lines.append(views["signature"])
                lines.append("```")
                lines.append("")

            outgoing = list(graph.g.out_edges(node_id, data=True))
            if outgoing:
                lines.append("## Connections")
                lines.append("")
                for _, target_id, edge_data in outgoing:
                    relation = edge_data.get("relation", "→")
                    target_name = node_names.get(target_id, target_id.split("/")[-1])
                    lines.append(f"- **{relation}** → [[{target_name}]]")
                lines.append("")

            incoming = list(graph.g.in_edges(node_id, data=True))
            if incoming:
                lines.append("## Referenced by")
                lines.append("")
                for source_id, _, edge_data in incoming:
                    relation = edge_data.get("relation", "→")
                    source_name = node_names.get(source_id, source_id.split("/")[-1])
                    lines.append(f"- **{relation}** ← [[{source_name}]]")
                lines.append("")

            md_path = out_dir / f"{name}.md"
            md_path.write_text("\n".join(lines), encoding="utf-8")
            count += 1

    graph.close()

    console.print(Panel(
        f"[green]✓ Exported![/green]\n\n"
        f"  Format : [cyan]{target}[/cyan]\n"
        f"  Notes  : [cyan]{count}[/cyan]\n"
        f"  Path   : [cyan]{out_dir.resolve()}[/cyan]\n\n"
        f"[dim]Open this folder in Obsidian as a vault (File → Open folder as vault).[/dim]",
        title="[bold cyan]Reducto Export[/bold cyan]",
        border_style="cyan",
    ))
