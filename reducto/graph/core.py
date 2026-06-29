"""
reducto.graph.core
------------------
Knowledge graph local, basado en archivo.
Maneja la ingestión, estado y queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import networkx as nx

from reducto.models import ParseResult, STATE_UNKNOWN, STATE_PARTIAL, STATE_KNOWN
from reducto.cache.store import CacheStore
from reducto.cache.schrodinger import resolve_node_state
from reducto.graph.communities import detect_communities, get_community_summary
from reducto.skills.loader import load_skills_from_directory
from reducto.skills.blueprint import ReductoSkill

class ReductoGraph:
    def __init__(self, *_legacy_args, project_root: str | Path | None = None, **_legacy_kwargs):
        if project_root:
            self.root = Path(project_root)
        else:
            self.root = self._find_project_root(Path.cwd())

        self.store = CacheStore(self.root)
        self.g = nx.MultiDiGraph()
        self._connected = False
        self.skills_registry: dict[str, ReductoSkill] = {}

    @staticmethod
    def _find_project_root(start: Path) -> Path:
        PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod"}
        current = start.resolve()
        while True:
            if (current / "reducto-out" / "graph.json").exists():
                return current
            if any((current / marker).exists() for marker in PROJECT_MARKERS):
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        return start.resolve()

    def connect(self) -> "ReductoGraph":
        self.store.ensure_dir()
        self.g = self.store.load_graph()
        self._connected = True
        self.load_skills()
        return self

    def load_skills(self):
        skills_dir = self.root / ".reducto" / "skills"
        self.skills_registry = load_skills_from_directory(skills_dir)

    def close(self):
        if self._connected:
            self.store.save_graph(self.g)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()

    @property
    def out_dir(self):
        return self.store.out_dir

    @property
    def graph_path(self):
        return self.store.graph_path

    def clear(self):
        self.g = nx.MultiDiGraph()
        self.store.save_graph(self.g)

    def invalidate_file(self, file_path: str | Path):
        """Removes all nodes associated with a file, invalidating its cache."""
        fp = str(file_path).replace("\\", "/")
        to_remove = [n for n, attrs in self.g.nodes(data=True) if attrs.get("file_path", "").replace("\\", "/") == fp]
        if to_remove:
            self.g.remove_nodes_from(to_remove)
            self.store.save_graph(self.g)

    def ingest_file(self, file_path: str | Path):
        """Parses and ingests a single file into the graph."""
        from reducto.engine.orchestrator import parse_file
        try:
            result = parse_file(Path(file_path))
            self.ingest([result])
        except Exception:
            pass

    def ingest(self, results: list[ParseResult], progress_cb=None) -> dict[str, int]:
        import hashlib
        from reducto.engine.orchestrator import resolve_call_edges
        resolve_call_edges(results)

        file_hashes: dict[str, str] = {}
        for result in results:
            fp = result.file_path.replace("\\", "/")
            if fp not in file_hashes:
                try:
                    h = hashlib.sha256(Path(result.file_path).read_bytes()).hexdigest()
                    file_hashes[fp] = h
                except Exception:
                    pass

        all_nodes = []
        all_edges = []
        for result in results:
            all_nodes.extend(result.nodes)
            all_edges.extend(result.edges)

        total_ops = len(all_nodes) + len(all_edges)
        done = 0

        for n in all_nodes:
            node_id   = n.id.replace("\\", "/")
            file_path = n.file_path.replace("\\", "/") if n.file_path else n.file_path
            new_hash  = file_hashes.get(file_path)

            existing = self.g.nodes.get(node_id, {})
            if (existing.get("state") == STATE_KNOWN
                    and existing.get("file_hash")
                    and existing.get("file_hash") == new_hash):
                done += 1
                if progress_cb: progress_cb(done, total_ops)
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
                raw_source="",
                file_hash=new_hash,
            )
            done += 1
            if progress_cb: progress_cb(done, total_ops)

        for e in all_edges:
            source = e.source_id.replace("\\", "/")
            target = e.target_id.replace("\\", "/")
            self.g.add_edge(source, target, relation=e.relation)
            done += 1
            if progress_cb: progress_cb(done, total_ops)

        self.store.save_graph(self.g)
        return {"nodes": len(all_nodes), "edges": len(all_edges)}

    def resolve_node(self, node_id: str, view: str = "full") -> dict[str, Any] | None:
        result = resolve_node_state(self.g, node_id, view)
        if result:
            self.store.save_graph(self.g)
        return result

    def search_by_name(self, name: str, limit: int = 10) -> list[dict]:
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

        STOP_WORDS = {
            "que", "hace", "como", "donde", "cuando", "cual", "cuales",
            "los", "las", "del", "una", "uno", "unos", "unas",
            "por", "para", "con", "sin", "sobre", "entre", "desde",
            "este", "esta", "estos", "estas", "ese", "esa",
            "hay", "tiene", "son", "esta", "estan", "ser", "estar",
            "todo", "todos", "toda", "todas", "otro", "otra", "otros",
            "bien", "mal", "mas", "muy", "algo", "nada", "cada",
            "pero", "porque", "sino", "tambien", "además",
            "proyecto", "archivo", "archivos", "funcion", "funciones",
            "clase", "clases", "codigo", "código",
            "the", "what", "does", "how", "this", "that", "which",
            "and", "for", "with", "from", "into", "about",
            "are", "was", "were", "been", "being",
            "have", "has", "had", "having",
            "not", "all", "any", "some", "each",
            "can", "could", "should", "would", "will",
            "file", "files", "function", "functions", "class", "classes",
            "code", "project",
        }

        raw_tokens = []
        for t in name.split():
            t_clean = t.lower().replace("-", "_").replace("\\", "/").strip("¿?¡!.,;:")
            if len(t_clean) < 2:
                continue
            if "." in t_clean and t_clean.split(".")[-1] in ("ts", "tsx", "js", "jsx", "py", "md", "json", "css"):
                raw_tokens.append(t_clean)
                raw_tokens.append(t_clean.rsplit(".", 1)[0])
                continue
            if t_clean not in STOP_WORDS:
                raw_tokens.append(t_clean)
        
        if not raw_tokens:
            return []

        tokens: set[str] = set()
        for t in raw_tokens:
            tokens.add(t)
            if t in SYNONYMS:
                tokens.update(SYNONYMS[t])

        scored: list[tuple[int, dict]] = []
        for node_id, attrs in self.g.nodes(data=True):
            nm  = (attrs.get("name") or "").lower().replace("-", "_").replace(" ", "_")
            fp  = (attrs.get("file_path") or "").lower().replace("\\", "/").replace("-", "_")
            nid = node_id.lower().replace("\\", "/").replace("-", "_")
            haystack = f"{nm} {fp} {nid}"

            matches = sum(1 for tok in tokens if tok in haystack)
            if matches == 0:
                continue

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

        scored.sort(key=lambda x: -x[0])
        return [node for _, node in scored[:limit]]

    def get_dependencies(self, node_id: str) -> list[dict]:
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

    def detect_communities(self) -> dict[str, int]:
        mapping = detect_communities(self.g)
        if mapping:
            self.store.save_graph(self.g)
        return mapping

    def get_community_summary(self) -> list[dict]:
        return get_community_summary(self.g)

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
        return self.store.load_stats()

    def update_session_stats(self, tokens_used: int, tokens_saved: int):
        stats = self.store.load_stats()
        stats["tokens_used"]  = stats.get("tokens_used", 0)  + tokens_used
        stats["tokens_saved"] = stats.get("tokens_saved", 0) + tokens_saved
        stats["queries"]      = stats.get("queries", 0) + 1
        self.store.save_stats(stats)
