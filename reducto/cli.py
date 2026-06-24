"""
reducto.cli
-----------
CLI de Reducto. Comandos:
  reducto ingest <path>   — parsea y carga al grafo
  reducto serve           — levanta el MCP server
  reducto query <texto>   — query directo desde terminal
  reducto context         — muestra stats de ahorro de tokens
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import box
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Helpers visuales
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Reducto — Universal knowledge graph for LLMs."""
    pass


# ---------------------------------------------------------------------------
# reducto ingest
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--clean", is_flag=True, default=False,
              help="Wipe the graph before ingesting (recommended after a cancelled/failed run)")
def ingest(path, clean):
    """Parse a directory and load it into the knowledge graph."""
    from reducto.parser import parse_directory
    from reducto.graph import ReductoGraph

    console.print(LOGO)
    root = Path(path).resolve()
    console.print(f"[bold]📂 Ingesting:[/bold] {root}\n")

    # 1. Conectar al grafo existente para obtener hashes conocidos
    graph = ReductoGraph(project_root=root)
    graph.connect()

    if clean:
        graph.clear()
        known_hashes = None
        console.print("[dim]🧹 Graph cleared — full rebuild[/dim]\n")
    else:
        # Re-indexado incremental: extraer hashes del grafo existente
        known_hashes = {
            attrs.get("file_path"): attrs.get("file_hash")
            for _, attrs in graph.g.nodes(data=True)
            if attrs.get("file_hash") and attrs.get("kind") == "File"
        }
        if known_hashes:
            console.print(f"[dim]♻️  Incremental mode — {len(known_hashes)} files cached[/dim]\n")

    # 2. Parsear (saltea archivos sin cambios en modo incremental)
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

    # 3. Cargar al grafo local
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

    # Detectar comunidades automáticamente
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

    # Auto-generar visualización HTML (como graph.html en Graphify)
    try:
        from reducto.visualize import generate_graph_html
        graph2 = ReductoGraph(project_root=root)
        graph2.connect()
        html_path = generate_graph_html(graph2, root / "reducto-out" / "graph.html")
        graph2.close()
        console.print(f"[dim]📊 Visual graph:[/dim] [cyan]{html_path.resolve()}[/cyan]\n")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not generate visualization:[/yellow] {e}")
        console.print(f"[dim]Run [cyan]reducto visualize[/cyan] manually to retry.[/dim]\n")

    console.print("\n[dim]Next:[/dim] [cyan]reducto serve[/cyan]  or  [cyan]reducto query \"your question\"[/cyan]\n")


@cli.command()
@click.argument("url")
@click.option("--dir", "skills_dir", default=".reducto/skills",
              help="Carpeta donde guardar el skill (default: .reducto/skills)")
def skill(url, skills_dir):
    """Download and index a skill from a GitHub URL.

    Example: reducto skill https://github.com/SudacaDev/react-architecture
    """
    import urllib.request
    import urllib.error

    console.print(f"\n[cyan]📥 Fetching skill from:[/cyan] {url}\n")

    # Detectar si es un repo de GitHub — intentar bajar SKILL.md y README.md
    files_to_try = []
    if "github.com" in url:
        # Convertir URL de GitHub a raw content
        raw_base = url.replace("github.com", "raw.githubusercontent.com")
        raw_base = raw_base.rstrip("/") + "/main"
        files_to_try = [
            (f"{raw_base}/SKILL.md",  "SKILL.md"),
            (f"{raw_base}/README.md", "README.md"),
        ]
    else:
        files_to_try = [(url, Path(url).name or "skill.md")]

    skills_path = Path(skills_dir)
    skills_path.mkdir(parents=True, exist_ok=True)

    # Extraer nombre del repo para la subcarpeta
    repo_name = url.rstrip("/").split("/")[-1]
    repo_dir = skills_path / repo_name
    repo_dir.mkdir(exist_ok=True)

    downloaded = []
    for raw_url, filename in files_to_try:
        try:
            with urllib.request.urlopen(raw_url) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            dest = repo_dir / filename
            dest.write_text(content, encoding="utf-8")
            downloaded.append(dest)
            console.print(f"[green]✓[/green] Downloaded [cyan]{filename}[/cyan] → {dest}")
        except urllib.error.HTTPError:
            pass
        except Exception as e:
            console.print(f"[yellow]⚠ Could not download {filename}:[/yellow] {e}")

    if not downloaded:
        console.print(f"[red]✗ Could not download any files from {url}[/red]")
        raise SystemExit(1)

    console.print(f"\n[dim]Re-ingesting to index the new skill...[/dim]")

    # Re-ingestar solo los archivos nuevos (los skills descargados)
    from reducto.parser import parse_file
    from reducto.graph import ReductoGraph

    graph = ReductoGraph()
    graph.connect()

    new_results = []
    for path in downloaded:
        try:
            new_results.append(parse_file(path))
        except Exception as e:
            console.print(f"[yellow]⚠ Could not parse {path.name}:[/yellow] {e}")

    if new_results:
        stats = graph.ingest(new_results)
        graph.close()
        console.print(Panel(
            f"[green]✓ Skill indexed![/green]\n\n"
            f"  Source  : [cyan]{url}[/cyan]\n"
            f"  Files   : [cyan]{len(downloaded)}[/cyan]\n"
            f"  Nodes   : [cyan]{stats['nodes']}[/cyan]\n\n"
            f"[dim]Now any LLM using Reducto can find this skill with:[/dim]\n"
            f"  [cyan]search_context \"{repo_name}\"[/cyan]",
            title="[bold cyan]Reducto Skill[/bold cyan]",
            border_style="cyan",
        ))
    else:
        graph.close()
        console.print("[yellow]⚠ No files could be parsed.[/yellow]")


# ---------------------------------------------------------------------------
# reducto serve
# ---------------------------------------------------------------------------

@cli.command()
def serve():
    """Start the MCP server (connects to any LLM that supports MCP)."""
    import sys
    # Cuando corre como MCP server, stdout es el canal de comunicación —
    # no imprimir nada (ni logo ni panel) para no romper el protocolo.
    # Solo escribir a stderr si hace falta.
    print("Reducto MCP server starting...", file=sys.stderr)
    from reducto.mcp_server import run
    asyncio.run(run())


@cli.command()
@click.option("--out", default=None, help="Output HTML path (default: reducto-out/graph.html)")
@click.option("--no-open", is_flag=True, default=False, help="Don't auto-open in browser")
@click.option("--limit", default=2000, help="Max nodes to render")
def visualize(out, no_open, limit):
    """Generate an interactive HTML graph (like /graph.html in Graphify)."""
    import webbrowser
    from reducto.graph import ReductoGraph
    from reducto.visualize import generate_graph_html

    graph = ReductoGraph()
    graph.connect()

    out_path = Path(out) if out else graph.out_dir / "graph.html"

    with console.status("[cyan]Generating graph visualization...[/cyan]"):
        output_path = generate_graph_html(graph, out_path, limit=limit)

    graph.close()

    console.print(Panel(
        f"[green]✓ Graph visualization ready![/green]\n\n"
        f"  File: [cyan]{output_path.resolve()}[/cyan]\n\n"
        f"[dim]Drag nodes around, scroll to zoom, search by name.[/dim]",
        title="[bold cyan]Reducto[/bold cyan]",
        border_style="cyan",
    ))

    if not no_open:
        webbrowser.open(f"file://{output_path.resolve()}")


@cli.command()
@click.option("--target", default=None,
              type=click.Choice(["claude-code", "antigravity", "vscode", "cursor", "all"],
                                case_sensitive=False),
              help="Install for a specific IDE without the interactive prompt")
def install(target):
    """Register Reducto MCP server and routing rules for your IDE(s)."""

    routing_rules = """If the Reducto MCP server is connected (server name: "reducto"), ALWAYS prefer its tools — `search_context`, `get_dependencies`, `get_callers` — called as regular tool calls (NOT via Bash/shell) before using any file search, grep, or read to explore this codebase. These tools cost far fewer tokens than reading raw files. Only fall back to file search or grep if the MCP server is unavailable or its tools return no useful data."""

    mcp_server_entry = {"command": "reducto", "args": ["serve"]}

    # ------------------------------------------------------------------
    # Auto-detección de IDEs instalados
    # ------------------------------------------------------------------
    import shutil

    detected = []
    if shutil.which("claude"):
        detected.append("claude-code")
    if (Path.home() / ".gemini").exists() or shutil.which("antigravity"):
        detected.append("antigravity")
    if shutil.which("code"):
        detected.append("vscode")
    if shutil.which("cursor"):
        detected.append("cursor")

    # ------------------------------------------------------------------
    # Selección de targets
    # ------------------------------------------------------------------
    if target == "all":
        targets = ["claude-code", "antigravity", "vscode", "cursor"]
    elif target:
        targets = [target]
    else:
        # Checklist interactivo
        options = {
            "claude-code":  "Claude Code",
            "antigravity":  "Antigravity (Google)",
            "vscode":       "VS Code (Copilot)",
            "cursor":       "Cursor",
        }
        console.print(f"\n[bold]Select IDEs to install Reducto for:[/bold]")
        console.print("[dim](auto-detected installed tools are pre-marked with ✓)[/dim]\n")

        choices = []
        for key, label in options.items():
            mark = "[green]✓[/green] " if key in detected else "  "
            choices.append((key, label, key in detected))

        # Mostrar opciones
        for i, (key, label, pre) in enumerate(choices):
            mark = "✓" if pre else " "
            console.print(f"  [[green]{mark}[/green]] [bold]{i+1}.[/bold] {label} [dim]({key})[/dim]")

        console.print()
        default_str = ",".join(str(i+1) for i, (_, _, pre) in enumerate(choices) if pre) or "1"
        console.print(f"[bold]Enter numbers separated by commas[/bold] (e.g. 1,2) or 'all' [[dim]default: {default_str}[/dim]]: ", end="")
        try:
            raw = input().strip() or default_str
        except (EOFError, KeyboardInterrupt):
            raw = default_str

        if raw.strip().lower() == "all":
            targets = [key for key, _, _ in choices]
        else:
            selected_indices = []
            for part in raw.split(","):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(choices):
                        selected_indices.append(idx)
                except ValueError:
                    pass
            targets = [choices[i][0] for i in selected_indices]

        if not targets:
            console.print("[yellow]No IDEs selected, defaulting to Claude Code.[/yellow]")
            targets = ["claude-code"]

    installed = []

    # ------------------------------------------------------------------
    # Claude Code
    # ------------------------------------------------------------------
    if "claude-code" in targets:
        commands_dir = Path(".claude/commands")
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "reducto.md").write_text(
            "---\ndescription: Build or refresh the Reducto knowledge graph.\n---\n\n"
            "Run `reducto ingest .` in the project root to update the knowledge graph.\n\n"
            "After it finishes:\n"
            "1. Run `reducto context` and report the token-saving stats.\n"
            "2. From now on, ALWAYS use MCP tools (`search_context`, `get_dependencies`, `get_callers`) "
            "instead of Glob/Grep/Read. Only fall back to Bash/Grep if MCP returns nothing.\n",
            encoding="utf-8",
        )
        (commands_dir / "reducto-query.md").write_text(
            "---\ndescription: Query the Reducto knowledge graph.\nargument-hint: <search term>\n---\n\n"
            "Use `search_context` MCP tool with \"$ARGUMENTS\". "
            "Do NOT use Glob/Grep if the answer is available via Reducto.\n",
            encoding="utf-8",
        )

        claude_md = Path("CLAUDE.md")
        marker = "<!-- reducto:start -->"
        section = f"{marker}\n## Reducto knowledge graph\n\nThis project has a Reducto knowledge graph via MCP server \"reducto\".\n{routing_rules}\n<!-- reducto:end -->\n"
        if claude_md.exists():
            existing = claude_md.read_text(encoding="utf-8")
            if marker not in existing:
                claude_md.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
        else:
            claude_md.write_text(section, encoding="utf-8")

        mcp_path = Path(".mcp.json")
        _write_mcp_json(mcp_path, mcp_server_entry)
        installed.append("Claude Code (.mcp.json + CLAUDE.md + slash commands)")

    # ------------------------------------------------------------------
    # Antigravity
    # ------------------------------------------------------------------
    if "antigravity" in targets:
        # AGENTS.md en el proyecto
        agents_md = Path("AGENTS.md")
        agents_section = (
            "# Reducto knowledge graph\n\n"
            "This project has a Reducto knowledge graph via MCP server \"reducto\".\n\n"
            "## MANDATORY: Always use Reducto first\n\n"
            "Before reading ANY file, ALWAYS call `search_context` from the \"reducto\" MCP server.\n\n"
            "Rules:\n"
            "1. ALWAYS call `search_context` before reading files\n"
            "2. Translate queries to short English terms (\"autenticación\" → \"auth\")\n"
            "3. Try 2-3 terms if the first returns nothing before falling back to grep\n"
            "4. Only use grep if ALL Reducto queries return empty\n\n"
            f"{routing_rules}\n"
        )
        if agents_md.exists():
            existing = agents_md.read_text(encoding="utf-8")
            if "reducto" not in existing.lower():
                agents_md.write_text(existing.rstrip() + "\n\n" + agents_section, encoding="utf-8")
        else:
            agents_md.write_text(agents_section, encoding="utf-8")

        # Workflows (slash commands) para Antigravity
        wf_dir = Path(".agent/workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)

        (wf_dir / "reducto.md").write_text(
            "---\n"
            "description: Build or refresh the Reducto knowledge graph for this project.\n"
            "---\n\n"
            "1. Run `reducto ingest .` in the project root to update the knowledge graph.\n"
            "2. Run `reducto context` and report the token-saving stats.\n"
            "3. From now on, ALWAYS use the Reducto MCP tools (`search_context`, `get_dependencies`, `get_callers`) "
            "before using any file search, grep, or read.\n",
            encoding="utf-8",
        )

        (wf_dir / "reducto-query.md").write_text(
            "---\n"
            "description: Query the Reducto knowledge graph for a specific term.\n"
            "---\n\n"
            "1. Ask the user what they want to search for if not clear from context.\n"
            "2. Use the `search_context` MCP tool from the \"reducto\" server with the query.\n"
            "3. If no results, try 2-3 alternative English terms before falling back to grep.\n"
            "4. Present the results clearly.\n",
            encoding="utf-8",
        )

        (wf_dir / "reducto-visualize.md").write_text(
            "---\n"
            "description: Generate and open the visual knowledge graph.\n"
            "---\n\n"
            "// turbo\n"
            "1. Run `reducto visualize` to generate the interactive graph HTML.\n"
            "2. Tell the user to open `reducto-out/graph.html` in their browser.\n",
            encoding="utf-8",
        )

        # mcp_config.json global de Antigravity
        if os.name == "nt":  # Windows
            ag_config = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        else:  # Mac/Linux
            ag_config = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        ag_config.parent.mkdir(parents=True, exist_ok=True)
        _write_mcp_json(ag_config, mcp_server_entry)
        installed.append(f"Antigravity (AGENTS.md + workflows + {ag_config})")

    # ------------------------------------------------------------------
    # VS Code
    # ------------------------------------------------------------------
    if "vscode" in targets:
        vscode_dir = Path(".vscode")
        vscode_dir.mkdir(exist_ok=True)
        _write_mcp_json(vscode_dir / "mcp.json", mcp_server_entry)
        installed.append("VS Code (.vscode/mcp.json)")

    # ------------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------------
    if "cursor" in targets:
        cursor_dir = Path(".cursor")
        cursor_dir.mkdir(exist_ok=True)
        # Cursor usa .cursor/mcp.json
        _write_mcp_json(cursor_dir / "mcp.json", mcp_server_entry)
        # Cursor también lee .cursorrules
        rules_path = Path(".cursorrules")
        cursor_rule = f"\n# Reducto\n{routing_rules}\n"
        if rules_path.exists():
            existing = rules_path.read_text(encoding="utf-8")
            if "reducto" not in existing.lower():
                rules_path.write_text(existing + cursor_rule, encoding="utf-8")
        else:
            rules_path.write_text(cursor_rule, encoding="utf-8")
        installed.append("Cursor (.cursor/mcp.json + .cursorrules)")

    # ------------------------------------------------------------------
    # Panel de resultado
    # ------------------------------------------------------------------
    items = "\n".join(f"  [green]✓[/green] [cyan]{item}[/cyan]" for item in installed)
    console.print(Panel(
        f"[green]✓ Installed![/green]\n\n{items}\n\n"
        "[dim]Tools exposed via MCP: search_context, get_dependencies, get_callers[/dim]\n"
        "[dim]Close and reopen your IDE (or start a new session) for it to take effect.[/dim]",
        title="[bold cyan]Reducto[/bold cyan]",
        border_style="cyan",
    ))


def _write_mcp_json(path: Path, server_entry: dict):
    """Escribe o actualiza un archivo mcp.json con la entrada de Reducto."""
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    else:
        existing = {}
    existing.setdefault("mcpServers", {})["reducto"] = server_entry
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# reducto query
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--resolve", is_flag=True, default=False, help="Load source code of results")
@click.option("--limit", default=10, help="Max results")
def query(query, resolve, limit):
    """Search the knowledge graph directly from the terminal."""
    import json as _json
    from reducto.graph import ReductoGraph
    from reducto.mcp_server import estimate_tokens, estimate_raw_file_tokens

    graph = ReductoGraph()
    graph.connect()

    nodes = graph.search_by_name(query, limit=limit)

    if not nodes:
        console.print(f"[yellow]No results for:[/yellow] {query}")
        graph.update_session_stats(estimate_tokens(query), 0)
        graph.close()
        return

    table = Table(
        title=f'Results for "[cyan]{query}[/cyan]"',
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


# ---------------------------------------------------------------------------
# reducto context
# ---------------------------------------------------------------------------

@cli.command()
def context():
    """Show token savings and graph health stats."""
    from reducto.graph import ReductoGraph

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

    # Costo estimado GPT-4o ($10 / 1M input tokens)
    cost_saved = tokens_saved * 10 / 1_000_000

    console.print(LOGO)

    # Panel principal
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

    # Estado del grafo (Schrödinger dashboard)
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