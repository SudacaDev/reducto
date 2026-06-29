"""
reducto.cache.store
-------------------
Persistencia y manejo de archivos de graph.json y stats.
"""

import json
from pathlib import Path
import networkx as nx

DEFAULT_OUT_DIR = "reducto-out"
GRAPH_FILE = "graph.json"
STATS_FILE = "session_stats.json"

class CacheStore:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.out_dir = self.root / DEFAULT_OUT_DIR
        self.graph_path = self.out_dir / GRAPH_FILE
        self.stats_path = self.out_dir / STATS_FILE
        
    def ensure_dir(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def load_graph(self) -> nx.MultiDiGraph:
        if self.graph_path.exists():
            try:
                data = json.loads(self.graph_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"nodes": {}, "edges": []}
        else:
            data = {"nodes": {}, "edges": []}

        g = nx.MultiDiGraph()
        for node_id, attrs in data.get("nodes", {}).items():
            g.add_node(node_id, **attrs)
        for e in data.get("edges", []):
            g.add_edge(e["source"], e["target"], relation=e["relation"])
        return g

    def save_graph(self, g: nx.MultiDiGraph):
        data = {
            "nodes": {n: dict(attrs) for n, attrs in g.nodes(data=True)},
            "edges": [
                {"source": u, "target": v, "relation": d.get("relation", "")}
                for u, v, d in g.edges(data=True)
            ],
        }
        self.ensure_dir()
        self.graph_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_stats(self) -> dict:
        if self.stats_path.exists():
            try:
                return json.loads(self.stats_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"tokens_used": 0, "tokens_saved": 0, "queries": 0}

    def save_stats(self, stats: dict):
        self.ensure_dir()
        self.stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
