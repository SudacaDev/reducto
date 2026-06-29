"""
reducto.cache.schrodinger
-------------------------
Maneja el estado Schrödinger de cada nodo (unknown → partial → known)
y computa las vistas ("signature", "summary", "full").
"""

import hashlib
from pathlib import Path
from typing import Any
import networkx as nx

from reducto.models import STATE_UNKNOWN, STATE_PARTIAL, STATE_KNOWN

def compute_view(node: dict, view: str, file_path: str) -> str:
    """Computa la representación pedida del nodo leyendo el archivo."""
    if not file_path or not Path(file_path).exists():
        return ""

    try:
        lines = Path(file_path).read_text(errors="replace").splitlines()
    except Exception:
        return ""

    start = max(0, node.get("start_line", 1) - 1)
    end   = node.get("end_line") or len(lines)

    if view == "signature":
        for i in range(start, min(end, len(lines))):
            if lines[i].strip():
                return lines[i].strip()
        return ""

    if view == "summary":
        collected = []
        in_doc = False
        for i in range(start, min(end, len(lines))):
            line = lines[i]
            if not line.strip() and not in_doc and len(collected) >= 2:
                break
            collected.append(line)
            stripped = line.strip()
            if stripped.startswith(('"""', "'''")):
                in_doc = not in_doc if stripped.count('"""') + stripped.count("'''") == 1 else False
            if len(collected) >= 8:
                break
        return "\n".join(collected).rstrip()

    return "\n".join(lines[start:end])

def resolve_node_state(g: nx.MultiDiGraph, node_id: str, view: str = "full") -> dict[str, Any] | None:
    """
    Resuelve un nodo con la vista pedida. Muta el grafo en memoria.
    Retorna el nodo modificado con su "content".
    """
    if node_id not in g:
        return None

    if view not in ("signature", "summary", "full"):
        view = "full"

    node = dict(g.nodes[node_id])
    node["id"] = node_id
    file_path = node.get("file_path", "")

    current_hash = None
    if file_path and Path(file_path).exists():
        try:
            content = Path(file_path).read_bytes()
            current_hash = hashlib.sha256(content).hexdigest()
        except Exception:
            pass

    cached_hash = node.get("file_hash")
    if cached_hash and cached_hash != current_hash:
        g.nodes[node_id]["state"]      = STATE_UNKNOWN
        g.nodes[node_id]["raw_source"] = ""
        g.nodes[node_id]["views"]      = {}
        g.nodes[node_id]["file_hash"]  = None

    views = g.nodes[node_id].get("views") or {}
    if (current_hash and cached_hash == current_hash
            and view in views and views[view]):
        node["view"]    = view
        node["content"] = views[view]
        node["state"]   = STATE_KNOWN
        return node

    content = compute_view(node, view, file_path)

    if "views" not in g.nodes[node_id] or not isinstance(g.nodes[node_id].get("views"), dict):
        g.nodes[node_id]["views"] = {}
    g.nodes[node_id]["views"][view] = content
    g.nodes[node_id]["file_hash"]   = current_hash
    
    if view == "full" and content:
        g.nodes[node_id]["raw_source"] = content
        g.nodes[node_id]["state"]      = STATE_KNOWN
    elif content:
        if g.nodes[node_id].get("state") != STATE_KNOWN:
            g.nodes[node_id]["state"] = STATE_PARTIAL

    node["view"]    = view
    node["content"] = content
    node["state"]   = g.nodes[node_id]["state"]
    return node
