"""
reducto.graph.communities
-------------------------
Clustering y detección de comunidades usando Louvain.
"""

import networkx as nx

def detect_communities(g: nx.MultiDiGraph) -> dict[str, int]:
    """
    Detecta comunidades usando el algoritmo Louvain.
    Guarda el ID de comunidad en cada nodo y retorna un dict node_id → community_id.
    """
    from networkx.algorithms.community import louvain_communities

    if g.number_of_nodes() == 0:
        return {}

    undirected = g.to_undirected()
    simple = nx.Graph(undirected)

    try:
        communities = louvain_communities(simple, seed=42, resolution=1.0)
    except Exception:
        return {}

    mapping: dict[str, int] = {}
    for cid, members in enumerate(communities):
        for node_id in members:
            mapping[node_id] = cid
            if node_id in g.nodes:
                g.nodes[node_id]["community"] = cid

    return mapping

def get_community_summary(g: nx.MultiDiGraph) -> list[dict]:
    """Retorna un resumen de cada comunidad con su tamaño y nodos principales."""
    communities: dict[int, list[str]] = {}
    for node_id, attrs in g.nodes(data=True):
        cid = attrs.get("community", -1)
        communities.setdefault(cid, []).append(node_id)

    degree = dict(g.degree())

    result = []
    for cid, members in sorted(communities.items()):
        if cid == -1:
            continue
        top = sorted(members, key=lambda n: degree.get(n, 0), reverse=True)[:3]
        top_names = [g.nodes[n].get("name", n.split("/")[-1]) for n in top]
        result.append({
            "id": cid,
            "size": len(members),
            "top_nodes": top_names,
            "label": " / ".join(top_names[:2]),
        })
    return result
