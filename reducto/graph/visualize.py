"""
reducto.visualize
------------------
Genera un HTML interactivo (vis-network) que muestra el knowledge graph de Reducto.
"""

from __future__ import annotations

import json
from pathlib import Path

from reducto.graph import ReductoGraph

# ---------------------------------------------------------------------------
# Paleta Reducto
# ---------------------------------------------------------------------------

PALETTE = {
    "bg":            "#1E1E2E",   # fondo principal
    "panel":         "#252434",   # panel lateral
    "text":          "#DDB6C7",   # texto principal (rosado/lila apagado)
    "muted":         "#7B7896",   # texto secundario
    "accent":        "#FECE84",   # naranja cálido (sliders, toggles)
    "edge":          "#4A4F6B",   # líneas de conexión
    "hover":         "#FFFFFF",
}

# Colores por tipo de nodo
KIND_COLORS = {
    "File":     "#A6E3E9",   # cian
    "Function": "#74C7A5",   # verde
    "Class":    "#F9CB8F",   # naranja/amarillo
    "Module":   "#DDB6C7",   # rosado/lila
    "Skill":    "#FECE84",   # naranja brillante (skills destacados)
    "Section":  "#9B8FCF",   # violeta
}

# Color de borde por estado Schrödinger
STATE_BORDER = {
    "unknown": "#4A4F6B",   # 🔴 → mismo color que edges (apagado)
    "partial": "#FECE84",   # 🟡 → naranja
    "known":   "#74C7A5",   # 🟢 → verde
}


def build_html(graph: ReductoGraph) -> str:
    """Genera el HTML completo con vis-network embebido (offline-first)."""

    # ------------------------------------------------------------------
    # Paleta de colores para comunidades (20 colores distintos)
    # ------------------------------------------------------------------
    COMMUNITY_PALETTE = [
        "#A6E3E9",  # cian
        "#74C7A5",  # verde
        "#F9CB8F",  # naranja/amarillo
        "#DDB6C7",  # rosado/lila
        "#FECE84",  # naranja brillante
        "#9B8FCF",  # violeta
        "#E87C7C",  # rojo/salmón
        "#7EC8E3",  # azul claro
        "#B5E48C",  # verde lima
        "#F4A261",  # naranja oscuro
        "#E0AFA0",  # rosa pálido
        "#81B29A",  # verde salvia
        "#FFD6A5",  # durazno
        "#C3B1E1",  # lila claro
        "#F0E68C",  # amarillo pálido
        "#89CFF0",  # celeste
        "#FFB7CE",  # rosa chicle
        "#BFCC94",  # verde oliva claro
        "#D4A373",  # marrón claro
        "#A8DADC",  # turquesa pálido
    ]

    # ------------------------------------------------------------------
    # Extraer datos del grafo
    # ------------------------------------------------------------------
    nodes_data = []
    edges_data = []

    # Calcular grado de cada nodo para tamaño
    degree = {n: 0 for n in graph.g.nodes}
    for src, tgt in graph.g.edges():
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1

    max_deg = max(degree.values()) if degree else 1

    # Extraer comunidades y armar paleta
    community_colors = {}
    for node_id, attrs in graph.g.nodes(data=True):
        cid = attrs.get("community", -1)
        if cid >= 0 and cid not in community_colors:
            community_colors[cid] = COMMUNITY_PALETTE[len(community_colors) % len(COMMUNITY_PALETTE)]

    for node_id, attrs in graph.g.nodes(data=True):
        kind  = attrs.get("kind", "File")
        state = attrs.get("state", "unknown")
        cid   = attrs.get("community", -1)
        deg   = degree.get(node_id, 0)

        # Tamaño proporcional al grado (8 a 28 px)
        size = 8 + int((deg / max(max_deg, 1)) * 20)

        # Label: mostrar solo si es un hub (top 15% por conexiones)
        show_label = deg >= max_deg * 0.15

        name = attrs.get("name") or node_id.split("/")[-1]
        if len(name) > 30:
            name = name[:27] + "..."

        # Color: por comunidad si tiene, sino por tipo
        bg_color = community_colors.get(cid, KIND_COLORS.get(kind, "#A6E3E9"))

        nodes_data.append({
            "id": node_id,
            "label": name if show_label else "",
            "title": f"{kind}: {name}",
            "value": deg,
            "size":  size,
            "color": {
                "background": bg_color,
                "border":     STATE_BORDER.get(state, "#4A4F6B"),
                "highlight":  {"background": bg_color, "border": PALETTE["hover"]},
            },
            "borderWidth": 2 if state != "unknown" else 1,
            "kind": kind,
            "state": state,
            "community": cid,
            "_name": attrs.get("name") or "",
            "_file": attrs.get("file_path") or "",
            "_line": attrs.get("start_line") or 0,
            "_signature": (attrs.get("views") or {}).get("signature", "") if isinstance(attrs.get("views"), dict) else "",
        })

    for src, tgt, data in graph.g.edges(data=True):
        relation = data.get("relation", "")
        # Color del edge: community color del source
        src_attrs = graph.g.nodes.get(src, {})
        src_cid   = src_attrs.get("community", -1)
        edge_color = community_colors.get(src_cid, PALETTE["edge"])

        edges_data.append({
            "from": src,
            "to":   tgt,
            "title": relation,
            "color": {"color": edge_color, "highlight": PALETTE["accent"], "opacity": 0.4},
            "width": 1,
            "smooth": {"type": "continuous", "roundness": 0.2},
        })

    # ------------------------------------------------------------------
    # Community summary para el panel
    # ------------------------------------------------------------------
    community_summary = graph.get_community_summary()
    for cs in community_summary:
        cs["color"] = community_colors.get(cs["id"], "#888")

    # ------------------------------------------------------------------
    # vis-network desde CDN (online)
    # ------------------------------------------------------------------
    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)
    community_json = json.dumps(community_summary)

    # ------------------------------------------------------------------
    # HTML completo
    # ------------------------------------------------------------------
    html = HTML_TEMPLATE
    html = html.replace("__NODES__", nodes_json)
    html = html.replace("__EDGES__", edges_json)
    html = html.replace("__COMMUNITIES__", community_json)
    html = html.replace("__BG__",       PALETTE["bg"])
    html = html.replace("__PANEL__",    PALETTE["panel"])
    html = html.replace("__TEXT__",     PALETTE["text"])
    html = html.replace("__MUTED__",    PALETTE["muted"])
    html = html.replace("__ACCENT__",   PALETTE["accent"])
    html = html.replace("__EDGE__",     PALETTE["edge"])
    html = html.replace("__N_NODES__",  str(len(nodes_data)))
    html = html.replace("__N_EDGES__",  str(len(edges_data)))
    html = html.replace("__N_COMMUNITIES__", str(len(community_summary)))
    html = html.replace("__KIND_COLORS__", json.dumps(KIND_COLORS))
    html = html.replace("__STATE_BORDER__", json.dumps(STATE_BORDER))

    return html


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reducto — Knowledge Graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  :root {
    --bg:     __BG__;
    --panel:  __PANEL__;
    --text:   __TEXT__;
    --muted:  __MUTED__;
    --accent: __ACCENT__;
    --edge:   __EDGE__;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    overflow: hidden;
  }
  #app {
    display: grid;
    grid-template-columns: 1fr 340px;
    height: 100vh;
  }
  #graph {
    background: var(--bg);
    position: relative;
    width: 100%;
    height: 100vh;
  }
  #sidebar {
    background: var(--panel);
    border-left: 1px solid rgba(221, 182, 199, 0.08);
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
  .brand {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 4px;
  }
  .brand h1 {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin: 0;
    color: var(--text);
    text-transform: uppercase;
  }
  .brand .tagline {
    font-size: 11px;
    color: var(--muted);
    margin-left: auto;
  }
  .section {
    background: rgba(0,0,0,0.15);
    border-radius: 8px;
    padding: 14px;
    border: 1px solid rgba(221, 182, 199, 0.06);
  }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
    margin: 0 0 12px 0;
  }
  #search {
    width: 100%;
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(221, 182, 199, 0.15);
    border-radius: 6px;
    padding: 8px 12px;
    color: var(--text);
    font-size: 13px;
    outline: none;
  }
  #search::placeholder { color: var(--muted); }
  #search:focus { border-color: var(--accent); }
  .node-info {
    font-size: 13px;
    line-height: 1.5;
  }
  .node-info .placeholder {
    color: var(--muted);
    font-style: italic;
  }
  .node-info .name {
    font-weight: 600;
    font-size: 15px;
    color: var(--text);
    margin-bottom: 4px;
  }
  .node-info .kind {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 8px;
  }
  .node-info .path {
    color: var(--muted);
    font-size: 11px;
    font-family: 'SF Mono', Menlo, monospace;
    word-break: break-all;
    margin-bottom: 8px;
  }
  .node-info .signature {
    background: rgba(0,0,0,0.4);
    border-left: 2px solid var(--accent);
    padding: 8px 10px;
    border-radius: 4px;
    font-family: 'SF Mono', Menlo, monospace;
    font-size: 12px;
    color: var(--text);
    white-space: pre-wrap;
    word-break: break-word;
    margin-top: 8px;
  }
  .filter-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    cursor: pointer;
    font-size: 13px;
  }
  .filter-row input[type=checkbox] {
    accent-color: var(--accent);
  }
  .filter-row .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .filter-row .count {
    margin-left: auto;
    color: var(--muted);
    font-size: 11px;
  }
  #footer {
    position: absolute;
    bottom: 12px;
    left: 16px;
    font-size: 12px;
    color: var(--muted);
    background: rgba(30,30,46,0.7);
    padding: 6px 12px;
    border-radius: 6px;
    backdrop-filter: blur(4px);
  }
  #footer strong {
    color: var(--text);
    font-weight: 600;
  }
</style>
</head>
<body>
<div id="app">
  <div id="graph">
    <div id="footer">
      <strong>__N_NODES__</strong> nodes · <strong>__N_EDGES__</strong> edges · <strong>__N_COMMUNITIES__</strong> communities
    </div>
  </div>

  <aside id="sidebar">
    <div class="brand">
      <h1>Reducto</h1>
      <span class="tagline">knowledge graph</span>
    </div>

    <div class="section">
      <input id="search" type="text" placeholder="Search nodes…" autocomplete="off">
    </div>

    <div class="section">
      <div class="section-title">Node Info</div>
      <div id="node-info" class="node-info">
        <div class="placeholder">Click a node to inspect it</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Communities</div>
      <div id="filters-community"></div>
    </div>

    <div class="section">
      <div class="section-title">Filter by type</div>
      <div id="filters-kind"></div>
    </div>

    <div class="section">
      <div class="section-title">Filter by state</div>
      <div id="filters-state"></div>
    </div>
  </aside>
</div>

<script>
  const KIND_COLORS  = __KIND_COLORS__;
  const STATE_BORDER = __STATE_BORDER__;
  const COMMUNITIES  = __COMMUNITIES__;
  const STATE_LABELS = {
    "unknown": "🔴 unknown",
    "partial": "🟡 partial",
    "known":   "🟢 known",
  };

  const allNodes = __NODES__;
  const allEdges = __EDGES__;

  const data = {
    nodes: new vis.DataSet(allNodes),
    edges: new vis.DataSet(allEdges),
  };

  const container = document.getElementById("graph");

  const options = {
    nodes: {
      shape: "dot",
      font: {
        color: "__TEXT__",
        size: 11,
        face: "system-ui",
      },
      borderWidth: 1,
      shadow: {
        enabled: true,
        color: "rgba(0,0,0,0.5)",
        size: 6,
        x: 0, y: 2,
      },
    },
    edges: {
      arrows: {
        to: { enabled: true, scaleFactor: 0.5, type: "arrow" },
      },
      smooth: { type: "continuous", roundness: 0.2 },
      width: 1,
      selectionWidth: 2,
    },
    physics: {
      enabled: true,
      barnesHut: {
        gravitationalConstant: -8000,
        centralGravity: 0.15,
        springLength: 110,
        springConstant: 0.03,
        damping: 0.4,
        avoidOverlap: 0.2,
      },
      stabilization: { iterations: 300 },
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
    },
  };

  const network = new vis.Network(container, data, options);

  // ----------------------------------------------------------------
  // Click en nodo → mostrar info
  // ----------------------------------------------------------------
  const infoBox = document.getElementById("node-info");

  network.on("click", function (params) {
    if (params.nodes.length === 0) {
      infoBox.innerHTML = '<div class="placeholder">Click a node to inspect it</div>';
      return;
    }
    const nodeId = params.nodes[0];
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;

    const kindColor = KIND_COLORS[node.kind] || "#888";
    const stateLabel = STATE_LABELS[node.state] || node.state;

    let html = '';
    html += '<div class="name">' + escapeHtml(node._name || node.id) + '</div>';
    html += '<span class="kind" style="background:' + kindColor + '33;color:' + kindColor + '">' + node.kind + '</span> ';
    html += '<span class="kind" style="background:rgba(0,0,0,0.3);color:var(--muted)">' + stateLabel + '</span>';
    if (node.community >= 0) {
      const comm = COMMUNITIES.find(c => c.id === node.community);
      if (comm) html += '<span class="kind" style="background:' + comm.color + '33;color:' + comm.color + '">C' + comm.id + '</span>';
    }
    if (node._file) {
      html += '<div class="path">' + escapeHtml(node._file) + (node._line ? ':' + node._line : '') + '</div>';
    }
    if (node._signature) {
      html += '<div class="signature">' + escapeHtml(node._signature) + '</div>';
    } else if (node.state === 'unknown') {
      html += '<div style="font-size:11px;color:var(--muted);margin-top:6px;font-style:italic">Not yet resolved — run `reducto query "' + escapeHtml(node._name || '') + '" --resolve` to load the signature.</div>';
    }
    infoBox.innerHTML = html;
  });

  // ----------------------------------------------------------------
  // Búsqueda
  // ----------------------------------------------------------------
  document.getElementById("search").addEventListener("input", function (e) {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      data.nodes.update(allNodes.map(n => ({ id: n.id, hidden: false })));
      return;
    }
    const updates = allNodes.map(n => ({
      id: n.id,
      hidden: !((n._name || "").toLowerCase().includes(q) || (n._file || "").toLowerCase().includes(q)),
    }));
    data.nodes.update(updates);
  });

  // ----------------------------------------------------------------
  // Filtros por tipo de nodo
  // ----------------------------------------------------------------
  function buildKindFilters() {
    const counts = {};
    allNodes.forEach(n => {
      counts[n.kind] = (counts[n.kind] || 0) + 1;
    });
    const container = document.getElementById("filters-kind");
    Object.keys(KIND_COLORS).forEach(kind => {
      if (!counts[kind]) return;
      const row = document.createElement("label");
      row.className = "filter-row";
      row.innerHTML =
        '<input type="checkbox" data-kind="' + kind + '" checked>' +
        '<span class="dot" style="background:' + KIND_COLORS[kind] + '"></span>' +
        '<span>' + kind + '</span>' +
        '<span class="count">' + counts[kind] + '</span>';
      container.appendChild(row);
    });
    container.addEventListener("change", applyFilters);
  }

  function buildStateFilters() {
    const counts = { unknown: 0, partial: 0, known: 0 };
    allNodes.forEach(n => { counts[n.state] = (counts[n.state] || 0) + 1; });
    const container = document.getElementById("filters-state");
    Object.keys(STATE_LABELS).forEach(state => {
      if (!counts[state]) return;
      const row = document.createElement("label");
      row.className = "filter-row";
      row.innerHTML =
        '<input type="checkbox" data-state="' + state + '" checked>' +
        '<span class="dot" style="background:' + STATE_BORDER[state] + '"></span>' +
        '<span>' + STATE_LABELS[state] + '</span>' +
        '<span class="count">' + counts[state] + '</span>';
      container.appendChild(row);
    });
    container.addEventListener("change", applyFilters);
  }

  function applyFilters() {
    const enabledKinds = new Set(
      Array.from(document.querySelectorAll('[data-kind]:checked')).map(el => el.dataset.kind)
    );
    const enabledStates = new Set(
      Array.from(document.querySelectorAll('[data-state]:checked')).map(el => el.dataset.state)
    );
    const enabledCommunities = new Set(
      Array.from(document.querySelectorAll('[data-community]:checked')).map(el => parseInt(el.dataset.community))
    );
    const hasCommunityFilter = document.querySelectorAll('[data-community]').length > 0;

    const updates = allNodes.map(n => ({
      id: n.id,
      hidden: !enabledKinds.has(n.kind)
           || !enabledStates.has(n.state)
           || (hasCommunityFilter && n.community >= 0 && !enabledCommunities.has(n.community)),
    }));
    data.nodes.update(updates);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  buildKindFilters();
  buildStateFilters();
  buildCommunityFilters();

  function buildCommunityFilters() {
    const container = document.getElementById("filters-community");
    if (!COMMUNITIES.length) {
      container.innerHTML = '<span style="color:var(--muted);font-size:12px">Run reducto ingest to detect</span>';
      return;
    }
    // Select All
    const allRow = document.createElement("label");
    allRow.className = "filter-row";
    allRow.innerHTML =
      '<input type="checkbox" id="community-all" checked>' +
      '<span style="font-weight:600;font-size:12px">Select All</span>' +
      '<span class="count">' + COMMUNITIES.length + '</span>';
    container.appendChild(allRow);
    document.getElementById("community-all").addEventListener("change", function(e) {
      document.querySelectorAll("[data-community]").forEach(cb => { cb.checked = e.target.checked; });
      applyFilters();
    });

    COMMUNITIES.forEach(c => {
      const row = document.createElement("label");
      row.className = "filter-row";
      row.innerHTML =
        '<input type="checkbox" data-community="' + c.id + '" checked>' +
        '<span class="dot" style="background:' + c.color + '"></span>' +
        '<span style="font-size:12px">' + escapeHtml(c.label) + '</span>' +
        '<span class="count">' + c.size + '</span>';
      container.appendChild(row);
    });
    container.addEventListener("change", applyFilters);
  }
</script>
</body>
</html>
"""


def write_visualization(graph: ReductoGraph, output_path: Path) -> Path:
    """Genera y guarda el HTML de visualización."""
    html = build_html(graph)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# Alias retrocompatible con el CLI viejo (que pasa limit=None)
def generate_graph_html(graph: ReductoGraph, output_path: Path, limit: int | None = None) -> Path:
    """Compat: el CLI llama a esta función. El parámetro limit se ignora
    porque el visualizador nuevo maneja la cantidad de nodos con filtros."""
    return write_visualization(graph, output_path)
