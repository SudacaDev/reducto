import click
import sys
import json
from pathlib import Path
import shutil

@click.command()
def install():
    """Add Reducto to Cursor/Claude Code/Cline configuration."""
    from reducto.__main__ import console
    import os

    reducto_bin = shutil.which("reducto")
    if not reducto_bin:
        console.print("[yellow]⚠ 'reducto' is not in PATH. Are you in an activated virtualenv?[/yellow]")
        reducto_bin = sys.executable + " -m reducto"
    else:
        reducto_bin = str(Path(reducto_bin).resolve())

    cwd = Path.cwd()

    claude_mcp_path = Path(os.path.expanduser("~/.config/claude-code/mcp.json"))
    if not claude_mcp_path.parent.exists():
        claude_mcp_path.parent.mkdir(parents=True, exist_ok=True)
    
    mcp_config = {}
    if claude_mcp_path.exists():
        try:
            mcp_config = json.loads(claude_mcp_path.read_text())
        except Exception:
            pass
    
    mcp_servers = mcp_config.get("mcpServers", {})
    mcp_servers["reducto"] = {
        "command": "python",
        "args": ["-m", "reducto", "serve"],
        "cwd": str(cwd)
    }
    mcp_config["mcpServers"] = mcp_servers
    
    claude_mcp_path.write_text(json.dumps(mcp_config, indent=2))
    console.print(f"[green]✓ Added 'reducto' to Claude Code MCP config at {claude_mcp_path}[/green]")
    console.print("[dim]Use /mcp in Claude Code to restart servers.[/dim]")

    cline_mcp_path = Path(os.path.expanduser("~/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"))
    if not cline_mcp_path.parent.exists():
        cline_mcp_path = Path(os.path.expanduser("~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"))
        
    if cline_mcp_path.parent.exists():
        cline_config = {}
        if cline_mcp_path.exists():
            try:
                cline_config = json.loads(cline_mcp_path.read_text())
            except Exception:
                pass
        c_servers = cline_config.get("mcpServers", {})
        c_servers["reducto"] = {
            "command": "python",
            "args": ["-m", "reducto", "serve"],
            "cwd": str(cwd)
        }
        cline_config["mcpServers"] = c_servers
        cline_mcp_path.write_text(json.dumps(cline_config, indent=2))
        console.print(f"[green]✓ Added 'reducto' to Cline MCP config[/green]")
