"""
reducto.graph
-------------
Knowledge graph local, basado en archivo (sin base de datos, sin cuentas).
Igual que Graphify: todo vive en `<project>/reducto-out/` como JSON plano.
Maneja el estado Schrödinger de cada nodo (unknown → partial → known).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import networkx as nx

from reducto.parser import CodeNode, CodeEdge, ParseResult

# ---------------------------------------------------------------------------
# Constantes de estado (el gato 🐱)
# ---------------------------------------------------------------------------

STATE_UNKNOWN = "unknown"    # 🔴 Existe pero nunca fue leído
STATE_PARTIAL = "partial"    # 🟡 Leído en algún contexto
STATE_KNOWN   = "known"      # 🟢 Contexto completo cacheado

DEFAULT_OUT_DIR = "reducto-out"
GRAPH_FILE = "graph.json"
STATS_FILE = "session_stats.json"


# ---------------------------------------------------------------------------
# Grafo local
# ---------------------------------------------------------------------------

class ReductoGraph:
    """
    Grafo de conocimiento 100% local. Sin servidor, sin cuenta, sin internet.
    Se guarda en `<project_root>/reducto-out/graph.json`, equivalente a como
    Graphify guarda `graphify-out/graph.json`.
    """

    def __init__(self, *_legacy_args, project_root: str | Path | None = None, **_legacy_kwargs):
        if project_root:
            self.root = Path(project_root)
        else:
            # Buscar reducto-out/graph.json subiendo por el árbol de directorios
            # (igual que git busca .git/) — así funciona sin importar el CWD
            self.root = self._find_project_root(Path.cwd())

        self.out_dir = self.root / DEFAULT_OUT_DIR
        self.graph_path = self.out_dir / GRAPH_FILE
        self.stats_path = self.out_dir / STATS_FILE
        self.g = nx.MultiDiGraph()
        self._connected = False

    @staticmethod
    def _find_project_root(start: Path) -> Path:
        """
        Sube por el árbol de directorios buscando una carpeta reducto-out/.
        Si no encuentra ninguna, devuelve el directorio de inicio (fallback).
        """
        current = start.resolve()
        while True:
            if (current / DEFAULT_OUT_DIR / GRAPH_FILE).exists():
                return current
            parent = current.parent
            if parent == current:  # llegamos a la raíz del filesystem
                break
            current = parent
        return start.resolve()  # fallback: usar el CWD

    # ------------------------------------------------------------------
    # Conexión (= cargar/crear el archivo local)
    # ------------------------------------------------------------------

    def connect(self) -> "ReductoGraph":
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self._connected = True
        return self

    def close(self):
        if self._connected:
            self._save()

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()

    @property
    def driver(self):
        raise RuntimeError(
            "ReductoGraph ya no usa Neo4j — es un grafo local en archivo. "
            "Esta propiedad existe solo por compatibilidad y no debería usarse."
        )

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _load(self):
        if self.graph_path.exists():
            try:
                data = json.loads(self.graph_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"nodes": {}, "edges": []}
        else:
            data = {"nodes": {}, "edges": []}

        self.g = nx.MultiDiGraph()
        for node_id, attrs in data.get("nodes", {}).items():
            self.g.add_node(node_id, **attrs)
        for e in data.get("edges", []):
            self.g.add_edge(e["source"], e["target"], relation=e["relation"])

    def _save(self):
        data = {
            "nodes": {n: dict(attrs) for n, attrs in self.g.nodes(data=True)},
            "edges": [
                {"source": u, "target": v, "relation": d.get("relation", "")}
                for u, v, d in self.g.edges(data=True)
            ],
        }
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear(self):
        """Borra todo el grafo. Usar con --clean."""
        self.g = nx.MultiDiGraph()
        self._save()

    # ------------------------------------------------------------------
    # Ingesta
    # ------------------------------------------------------------------

    def ingest(self, results: list[ParseResult], progress_cb=None) -> dict[str, int]:
        import hashlib
        # Resolver CALLS antes de cargar (conectar __call__X con nodos reales)
        from reducto.parser import resolve_call_edges
        resolve_call_edges(results)

        # Pre-computar hash por archivo para preservar cache si no cambió
        file_hashes: dict[str, str] = {}
        for result in results:
            fp = result.file_path.replace("\\", "/")
            if fp not in file_hashes:
                try:
                    h = hashlib.sha256(Path(result.file_path).read_bytes()).hexdigest()
                    file_hashes[fp] = h
                except Exception:
                    pass

        all_nodes: list[CodeNode] = []
        all_edges: list[CodeEdge] = []
        for result in results:
            all_nodes.extend(result.nodes)
            all_edges.extend(result.edges)

        total_ops = len(all_nodes) + len(all_edges)
        done = 0

        for n in all_nodes:
            node_id   = n.id.replace("\\", "/")
            file_path = n.file_path.replace("\\", "/") if n.file_path else n.file_path
            new_hash  = file_hashes.get(file_path)

            # Preservar cache si el nodo ya existe y el hash no cambió (decoherencia)
            existing = self.g.nodes.get(node_id, {})
            if (existing.get("state") == STATE_KNOWN
                    and existing.get("file_hash")
                    and existing.get("file_hash") == new_hash):
                # Archivo no cambió — mantener nodo 🟢 con su cache
                done += 1
                if progress_cb:
                    progress_cb(done, total_ops)
                continue

            self.g.add_node(
                node_id,
                kind=n.kind,
                name=n.name,
                file_path=file_path,
                start_line=n.start_line,
                end_line=n.end_line,
                state=n.state,
                docstring=n.docstring,
                raw_source="",  # reset — el archivo cambió
                file_hash=new_hash,
            )
            done += 1
            if progress_cb:
                progress_cb(done, total_ops)

        for e in all_edges:
            source = e.source_id.replace("\\", "/")
            target = e.target_id.replace("\\", "/")
            self.g.add_edge(source, target, relation=e.relation)
            done += 1
            if progress_cb:
                progress_cb(done, total_ops)

        self._save()
        return {"nodes": len(all_nodes), "edges": len(all_edges)}

    # ------------------------------------------------------------------
    # Schrödinger + Colapso por observador 🐱
    # ------------------------------------------------------------------

    def resolve_node(self, node_id: str, view: str = "full") -> dict[str, Any] | None:
        """
        Resuelve un nodo con la "vista" pedida (colapso por observador):
          - 'signature' → solo la primera línea (cheap, ~10-30 tokens)
          - 'summary'   → firma + docstring (medium, ~50-150 tokens)
          - 'full'      → código completo (expensive, 100-1000+ tokens)

        Cada vista se cachea independientemente. Si el archivo cambió
        (decoherencia), todas las vistas se invalidan.

        Inspirado en el patrón `resolve` de LSP: cheap first, expensive on demand.
        """
        import hashlib

        if node_id not in self.g:
            return None

        if view not in ("signature", "summary", "full"):
            view = "full"

        node = dict(self.g.nodes[node_id])
        node["id"] = node_id
        file_path = node.get("file_path", "")

        # Calcular hash actual del archivo
        current_hash = None
        if file_path and Path(file_path).exists():
            try:
                content = Path(file_path).read_bytes()
                current_hash = hashlib.sha256(content).hexdigest()
            except Exception:
                pass

        # Decoherencia: si el hash cambió, invalidar TODAS las vistas cacheadas
        cached_hash = node.get("file_hash")
        if cached_hash and cached_hash != current_hash:
            self.g.nodes[node_id]["state"]      = STATE_UNKNOWN
            self.g.nodes[node_id]["raw_source"] = ""
            self.g.nodes[node_id]["views"]      = {}
            self.g.nodes[node_id]["file_hash"]  = None

        # Buscar la vista pedida en el cache de vistas
        views = self.g.nodes[node_id].get("views") or {}
        if (current_hash and cached_hash == current_hash
                and view in views and views[view]):
            # Cache hit para esta vista específica — 0 tokens
            node["view"]    = view
            node["content"] = views[view]
            node["state"]   = STATE_KNOWN
            return node

        # No está en cache: calcular la vista
        content = self._compute_view(node, view, file_path)

        # Guardar la vista en el cache (sin pisar otras vistas ya cacheadas)
        if "views" not in self.g.nodes[node_id] or not isinstance(self.g.nodes[node_id].get("views"), dict):
            self.g.nodes[node_id]["views"] = {}
        self.g.nodes[node_id]["views"][view] = content
        self.g.nodes[node_id]["file_hash"]   = current_hash
        # Si pidieron 'full', también marcar el nodo como known con su raw_source
        if view == "full" and content:
            self.g.nodes[node_id]["raw_source"] = content
            self.g.nodes[node_id]["state"]      = STATE_KNOWN
        elif content:
            # signature/summary cuentan como partial (no tenemos el código completo aún)
            if self.g.nodes[node_id].get("state") != STATE_KNOWN:
                self.g.nodes[node_id]["state"] = STATE_PARTIAL
        self._save()

        node["view"]    = view
        node["content"] = content
        node["state"]   = self.g.nodes[node_id]["state"]
        return node

    def _compute_view(self, node: dict, view: str, file_path: str) -> str:
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
            # Primera línea no vacía a partir de start_line
            for i in range(start, min(end, len(lines))):
                if lines[i].strip():
                    return lines[i].strip()
            return ""

        if view == "summary":
            # Firma + docstring/comentario inmediato (hasta 5 líneas o hasta el primer bloque vacío)
            collected = []
            in_doc = False
            for i in range(start, min(end, len(lines))):
                line = lines[i]
                if not line.strip() and not in_doc and len(collected) >= 2:
                    break
                collected.append(line)
                # Detectar docstring de Python
                stripped = line.strip()
                if stripped.startswith(('"""', "'''")):
                    in_doc = not in_doc if stripped.count('"""') + stripped.count("'''") == 1 else False
                if len(collected) >= 8:
                    break
            return "\n".join(collected).rstrip()

        # 'full' — código completo
        return "\n".join(lines[start:end])

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_by_name(self, name: str, limit: int = 10) -> list[dict]:
        """
        Busca nodos por nombre, path o ID (case-insensitive, multi-word).

        Tokeniza la query en palabras y devuelve nodos donde matchean una o
        más, rankeados por cantidad de matches. Así 'authentication functions'
        encuentra nodos que tengan 'auth', 'sign', 'login' o 'session' en su
        nombre/path, sin requerir que aparezca la frase entera.

        Sinónimos comunes ES→EN se expanden automáticamente para que el LLM
        no tenga que adivinar la traducción exacta.
        """
        # Sinónimos ES→EN y conceptos→términos de código
        SYNONYMS = {
            "autenticacion": ["auth", "sign", "login", "session"],
            "autenticación": ["auth", "sign", "login", "session"],
            "authentication": ["auth", "sign", "login", "session"],
            "login":  ["sign_in", "signin", "auth"],
            "logout": ["sign_out", "signout"],
            "registro": ["sign_up", "signup", "register"],
            "session": ["session", "auth"],
            "sesion":  ["session", "auth"],
            "sesión":  ["session", "auth"],
            "pago":    ["payment", "checkout", "billing"],
            "pagos":   ["payment", "checkout", "billing"],
            "usuario": ["user", "account"],
            "usuarios":["user", "account"],
            "contraseña": ["password", "pwd"],
            "contrasena": ["password", "pwd"],
            "componente": ["component"],
            "componentes":["component"],
        }

        # Tokenizar la query: dividir por espacios, normalizar, expandir sinónimos
        raw_tokens = [
            t.lower().replace("-", "_").replace("\\", "/")
            for t in name.split()
            if len(t) >= 2  # ignorar palabras muy cortas
        ]
        if not raw_tokens:
            return []

        # Expandir con sinónimos
        tokens: set[str] = set()
        for t in raw_tokens:
            tokens.add(t)
            if t in SYNONYMS:
                tokens.update(SYNONYMS[t])

        # Buscar nodos que matcheen al menos un token, contar matches por nodo
        scored: list[tuple[int, dict]] = []
        for node_id, attrs in self.g.nodes(data=True):
            nm  = (attrs.get("name") or "").lower().replace("-", "_").replace(" ", "_")
            fp  = (attrs.get("file_path") or "").lower().replace("\\", "/").replace("-", "_")
            nid = node_id.lower().replace("\\", "/").replace("-", "_")
            haystack = f"{nm} {fp} {nid}"

            matches = sum(1 for tok in tokens if tok in haystack)
            if matches == 0:
                continue

            # Bonus: si el match es en el nombre del nodo, es más relevante que en el path
            name_matches = sum(1 for tok in tokens if tok in nm)
            score = matches * 10 + name_matches * 5

            scored.append((score, {
                "id": node_id,
                "name": attrs.get("name"),
                "kind": attrs.get("kind"),
                "file_path": attrs.get("file_path"),
                "start_line": attrs.get("start_line"),
                "state": attrs.get("state", STATE_UNKNOWN),
            }))

        # Ordenar por score desc, devolver top N
        scored.sort(key=lambda x: -x[0])
        return [node for _, node in scored[:limit]]

    def get_dependencies(self, node_id: str) -> list[dict]:
        """Devuelve todo lo que este nodo importa o llama."""
        out = []
        if node_id not in self.g:
            return out
        for _, target, data in self.g.out_edges(node_id, data=True):
            if data.get("relation") in ("IMPORTS", "CALLS", "DEFINES"):
                attrs = self.g.nodes.get(target, {})
                out.append({
                    "id": target,
                    "name": attrs.get("name"),
                    "kind": attrs.get("kind"),
                    "relation": data.get("relation"),
                    "state": attrs.get("state", STATE_UNKNOWN),
                })
        return out

    def get_callers(self, node_id: str) -> list[dict]:
        """
        ¿Quién depende de este nodo? Considera CALLS/IMPORTS directos, y si
        el nodo es Function/Class, también quién importa su File contenedor
        (proxy razonable mientras no exista extracción real de CALLS).
        """
        if node_id not in self.g:
            return []

        callers: dict[str, str] = {}

        for source, _, data in self.g.in_edges(node_id, data=True):
            if data.get("relation") in ("CALLS", "IMPORTS"):
                callers[source] = data.get("relation")

        attrs = self.g.nodes.get(node_id, {})
        file_path = attrs.get("file_path")
        if file_path and file_path in self.g:
            for source, _, data in self.g.in_edges(file_path, data=True):
                if data.get("relation") == "IMPORTS":
                    callers.setdefault(source, "IMPORTS")

        out = []
        for cid in callers:
            cattrs = self.g.nodes.get(cid, {})
            out.append({
                "id": cid,
                "name": cattrs.get("name"),
                "kind": cattrs.get("kind"),
                "state": cattrs.get("state", STATE_UNKNOWN),
            })
        return out

    # ------------------------------------------------------------------
    # Clustering / detección de comunidades
    # ------------------------------------------------------------------

    def detect_communities(self) -> dict[str, int]:
        """
        Detecta comunidades usando el algoritmo Louvain.
        Guarda el ID de comunidad en cada nodo y retorna un dict node_id → community_id.

        Las comunidades se detectan sobre una vista no-dirigida del grafo
        (Louvain requiere grafo no-dirigido) y se asignan como atributo
        'community' en cada nodo.
        """
        from networkx.algorithms.community import louvain_communities

        if self.g.number_of_nodes() == 0:
            return {}

        # Louvain necesita un grafo no-dirigido simple
        undirected = self.g.to_undirected()
        # Eliminar multi-edges para que Louvain funcione
        simple = nx.Graph(undirected)

        try:
            communities = louvain_communities(simple, seed=42, resolution=1.0)
        except Exception:
            return {}

        mapping: dict[str, int] = {}
        for cid, members in enumerate(communities):
            for node_id in members:
                mapping[node_id] = cid
                if node_id in self.g.nodes:
                    self.g.nodes[node_id]["community"] = cid

        self._save()
        return mapping

    def get_community_summary(self) -> list[dict]:
        """Retorna un resumen de cada comunidad con su tamaño y nodos principales."""
        communities: dict[int, list[str]] = {}
        for node_id, attrs in self.g.nodes(data=True):
            cid = attrs.get("community", -1)
            communities.setdefault(cid, []).append(node_id)

        # Calcular grado para encontrar nodos "hub" de cada comunidad
        degree = dict(self.g.degree())

        result = []
        for cid, members in sorted(communities.items()):
            if cid == -1:
                continue
            # Top 3 nodos por grado en esta comunidad
            top = sorted(members, key=lambda n: degree.get(n, 0), reverse=True)[:3]
            top_names = [self.g.nodes[n].get("name", n.split("/")[-1]) for n in top]
            result.append({
                "id": cid,
                "size": len(members),
                "top_nodes": top_names,
                "label": " / ".join(top_names[:2]),
            })
        return result

    # ------------------------------------------------------------------
    # Stats para `reducto context`
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        known = partial = unknown = 0
        for _, attrs in self.g.nodes(data=True):
            s = attrs.get("state", STATE_UNKNOWN)
            if s == STATE_KNOWN:
                known += 1
            elif s == STATE_PARTIAL:
                partial += 1
            else:
                unknown += 1
        return {
            "total_nodes": self.g.number_of_nodes(),
            "known": known,
            "partial": partial,
            "unknown": unknown,
            "total_edges": self.g.number_of_edges(),
        }

    def get_session_stats(self) -> dict[str, Any]:
        if self.stats_path.exists():
            try:
                return json.loads(self.stats_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"tokens_used": 0, "tokens_saved": 0, "queries": 0}

    def update_session_stats(self, tokens_used: int, tokens_saved: int):
        stats = self.get_session_stats()
        stats["tokens_used"]  = stats.get("tokens_used", 0)  + tokens_used
        stats["tokens_saved"] = stats.get("tokens_saved", 0) + tokens_saved
        stats["queries"]      = stats.get("queries", 0) + 1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
