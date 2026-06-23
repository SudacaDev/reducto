"""
reducto.parser
--------------
Parsea archivos de código y extrae nodos (File, Function, Class)
y relaciones (DEFINES, CALLS, IMPORTS) usando tree-sitter (AST real).
Fallback automático a regex si tree-sitter no está disponible.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

NodeKind = Literal["File", "Function", "Class", "Module", "Section", "Skill"]

@dataclass
class CodeNode:
    id: str
    kind: NodeKind
    name: str
    file_path: str
    start_line: int = 0
    end_line: int = 0
    docstring: str = ""
    raw_source: str = ""
    state: Literal["unknown", "partial", "known"] = "unknown"

@dataclass
class CodeEdge:
    source_id: str
    target_id: str
    relation: Literal["DEFINES", "CALLS", "IMPORTS", "BELONGS_TO"]
    metadata: dict = field(default_factory=dict)

@dataclass
class ParseResult:
    nodes: list[CodeNode]
    edges: list[CodeEdge]
    file_path: str
    language: str
    total_lines: int


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".py":  "python",
    ".js":  "javascript",
    ".ts":  "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".md":  "markdown",
    ".mdx": "markdown",
}

def detect_language(path: Path) -> str | None:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# Tree-sitter AST parser
# ---------------------------------------------------------------------------

def _ts_available() -> bool:
    try:
        import tree_sitter_python  # noqa
        import tree_sitter_typescript  # noqa
        return True
    except ImportError:
        return False


class ASTParser:
    """
    Parser basado en tree-sitter AST.
    Extrae funciones, clases, CALLS e IMPORTS con precisión real.
    """

    def __init__(self):
        from tree_sitter import Language, Parser
        import tree_sitter_python as tspython
        import tree_sitter_javascript as tsjs
        import tree_sitter_typescript as tsts
        self._parsers = {
            "python":     Parser(Language(tspython.language())),
            "javascript": Parser(Language(tsjs.language())),
            "typescript": Parser(Language(tsts.language_tsx())),
        }

    def parse(self, file_path: Path) -> ParseResult:
        lang = detect_language(file_path)
        if not lang or lang == "markdown":
            raise ValueError(f"Use MarkdownParser for {file_path}")

        source_bytes = file_path.read_bytes()
        source_str   = source_bytes.decode("utf-8", errors="replace")
        lines        = source_str.splitlines()
        file_id      = str(file_path).replace("\\", "/")

        tree = self._parsers[lang].parse(source_bytes)

        nodes: list[CodeNode] = []
        edges: list[CodeEdge] = []

        file_node = CodeNode(
            id=file_id, kind="File", name=file_path.name,
            file_path=file_id, start_line=1, end_line=len(lines), state="unknown",
        )
        nodes.append(file_node)

        if lang == "python":
            self._walk_python(tree.root_node, file_id, source_bytes, nodes, edges)
        else:
            self._walk_js(tree.root_node, file_id, source_bytes, nodes, edges)

        return ParseResult(
            nodes=nodes, edges=edges,
            file_path=file_id, language=lang, total_lines=len(lines),
        )

    # ------------------------------------------------------------------
    # Python walker
    # ------------------------------------------------------------------

    def _walk_python(self, node, file_id: str, src: bytes,
                     nodes: list, edges: list, parent_id: str | None = None):

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "?"
            node_id = f"{file_id}::{name}"
            lineno  = node.start_point[0] + 1
            endline = node.end_point[0] + 1
            nodes.append(CodeNode(
                id=node_id, kind="Function", name=name,
                file_path=file_id, start_line=lineno, end_line=endline, state="unknown",
            ))
            parent = parent_id or file_id
            edges.append(CodeEdge(parent, node_id, "DEFINES"))
            # Recursión dentro de la función para encontrar CALLS
            for child in node.children:
                self._walk_python(child, file_id, src, nodes, edges, node_id)
            return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "?"
            node_id = f"{file_id}::{name}"
            lineno  = node.start_point[0] + 1
            endline = node.end_point[0] + 1
            nodes.append(CodeNode(
                id=node_id, kind="Class", name=name,
                file_path=file_id, start_line=lineno, end_line=endline, state="unknown",
            ))
            parent = parent_id or file_id
            edges.append(CodeEdge(parent, node_id, "DEFINES"))
            for child in node.children:
                self._walk_python(child, file_id, src, nodes, edges, node_id)
            return

        if node.type == "call" and parent_id:
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = func_node.text.decode()
                # Extraer solo el nombre base (sin module prefix)
                base = callee.split(".")[-1]
                edges.append(CodeEdge(
                    parent_id, f"__call__{base}", "CALLS",
                    {"callee": callee, "line": node.start_point[0] + 1},
                ))

        if node.type == "import_statement":
            for alias in node.children:
                if alias.type == "dotted_name":
                    edges.append(CodeEdge(file_id, alias.text.decode(), "IMPORTS",
                                          {"raw_import": alias.text.decode()}))

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node:
                edges.append(CodeEdge(file_id, module_node.text.decode(), "IMPORTS",
                                      {"raw_import": module_node.text.decode()}))

        for child in node.children:
            self._walk_python(child, file_id, src, nodes, edges, parent_id)

    # ------------------------------------------------------------------
    # JS/TS walker
    # ------------------------------------------------------------------

    def _walk_js(self, node, file_id: str, src: bytes,
                 nodes: list, edges: list, parent_id: str | None = None):

        # function declaration: function Foo() {}
        if node.type in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                self._add_js_function(name_node.text.decode(), node, file_id, nodes, edges,
                                      parent_id, src)
                for child in node.children:
                    self._walk_js(child, file_id, src, nodes, edges,
                                  f"{file_id}::{name_node.text.decode()}")
                return

        # const/let Foo = () => {} or const Foo = function() {}
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            val_node  = node.child_by_field_name("value")
            if name_node and val_node and val_node.type in ("arrow_function", "function"):
                self._add_js_function(name_node.text.decode(), val_node, file_id, nodes, edges,
                                      parent_id, src)
                for child in val_node.children:
                    self._walk_js(child, file_id, src, nodes, edges,
                                  f"{file_id}::{name_node.text.decode()}")
                return

        # class Foo {}
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name    = name_node.text.decode()
                node_id = f"{file_id}::{name}"
                nodes.append(CodeNode(
                    id=node_id, kind="Class", name=name,
                    file_path=file_id,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    state="unknown",
                ))
                parent = parent_id or file_id
                edges.append(CodeEdge(parent, node_id, "DEFINES"))
                for child in node.children:
                    self._walk_js(child, file_id, src, nodes, edges, node_id)
                return

        # method_definition
        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            if name_node and parent_id:
                self._add_js_function(name_node.text.decode(), node, file_id, nodes, edges,
                                      parent_id, src)
                fn_id = f"{file_id}::{name_node.text.decode()}"
                for child in node.children:
                    self._walk_js(child, file_id, src, nodes, edges, fn_id)
                return

        # call_expression → CALLS edge
        if node.type == "call_expression" and parent_id:
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = fn_node.text.decode()
                base   = callee.split(".")[-1]
                edges.append(CodeEdge(
                    parent_id, f"__call__{base}", "CALLS",
                    {"callee": callee, "line": node.start_point[0] + 1},
                ))

        # import statement
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "string":
                    raw = child.text.decode().strip("'\"")
                    edges.append(CodeEdge(file_id, raw, "IMPORTS", {"raw_import": raw}))

        for child in node.children:
            self._walk_js(child, file_id, src, nodes, edges, parent_id)

    def _add_js_function(self, name: str, node, file_id: str,
                         nodes: list, edges: list, parent_id, src):
        node_id = f"{file_id}::{name}"
        nodes.append(CodeNode(
            id=node_id, kind="Function", name=name,
            file_path=file_id,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            state="unknown",
        ))
        parent = parent_id or file_id
        edges.append(CodeEdge(parent, node_id, "DEFINES"))


# ---------------------------------------------------------------------------
# Regex fallback parser (igual que antes)
# ---------------------------------------------------------------------------

class RegexParser:
    PY_FUNCTION  = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
    PY_CLASS     = re.compile(r"^class\s+(\w+)[\s:(]", re.MULTILINE)
    PY_IMPORT    = re.compile(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.,\t ]+))", re.MULTILINE)
    JS_FUNCTION  = re.compile(
        r"(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>|"
        r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{)", re.MULTILINE)
    JS_CLASS     = re.compile(r"class\s+(\w+)", re.MULTILINE)
    JS_IMPORT    = re.compile(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)

    def parse(self, file_path: Path) -> ParseResult:
        lang = detect_language(file_path)
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lines  = source.splitlines()
        file_id = str(file_path).replace("\\", "/")
        nodes: list[CodeNode] = []
        edges: list[CodeEdge] = []
        file_node = CodeNode(id=file_id, kind="File", name=file_path.name,
                             file_path=file_id, start_line=1, end_line=len(lines), state="unknown")
        nodes.append(file_node)
        if lang == "python":
            nodes_, edges_ = self._parse_python(source, file_id)
        else:
            nodes_, edges_ = self._parse_js(source, file_id)
        nodes.extend(nodes_); edges.extend(edges_)
        return ParseResult(nodes=nodes, edges=edges, file_path=file_id,
                           language=lang, total_lines=len(lines))

    def _parse_python(self, source, file_id):
        nodes, edges = [], []
        for m in self.PY_CLASS.finditer(source):
            name = m.group(1); lineno = source[:m.start()].count("\n") + 1
            nid = f"{file_id}::{name}"
            nodes.append(CodeNode(id=nid, kind="Class", name=name, file_path=file_id, start_line=lineno, state="unknown"))
            edges.append(CodeEdge(file_id, nid, "DEFINES"))
        for m in self.PY_FUNCTION.finditer(source):
            name = m.group(1); lineno = source[:m.start()].count("\n") + 1
            nid = f"{file_id}::{name}"
            nodes.append(CodeNode(id=nid, kind="Function", name=name, file_path=file_id, start_line=lineno, state="unknown"))
            edges.append(CodeEdge(file_id, nid, "DEFINES"))
        for m in self.PY_IMPORT.finditer(source):
            module = (m.group(1) or m.group(2) or "").strip().split(",")[0].strip()
            if module:
                edges.append(CodeEdge(file_id, module, "IMPORTS", {"raw_import": module}))
        return nodes, edges

    def _parse_js(self, source, file_id):
        nodes, edges = [], []
        for m in self.JS_CLASS.finditer(source):
            name = m.group(1); lineno = source[:m.start()].count("\n") + 1
            nid = f"{file_id}::{name}"
            nodes.append(CodeNode(id=nid, kind="Class", name=name, file_path=file_id, start_line=lineno, state="unknown"))
            edges.append(CodeEdge(file_id, nid, "DEFINES"))
        for m in self.JS_FUNCTION.finditer(source):
            name = m.group(1) or m.group(2) or m.group(3)
            if not name or name in {"if","for","while","switch","catch"}: continue
            lineno = source[:m.start()].count("\n") + 1
            nid = f"{file_id}::{name}"
            nodes.append(CodeNode(id=nid, kind="Function", name=name, file_path=file_id, start_line=lineno, state="unknown"))
            edges.append(CodeEdge(file_id, nid, "DEFINES"))
        for m in self.JS_IMPORT.finditer(source):
            edges.append(CodeEdge(file_id, m.group(1), "IMPORTS", {"raw_import": m.group(1)}))
        return nodes, edges


# ---------------------------------------------------------------------------
# Markdown parser (igual que antes)
# ---------------------------------------------------------------------------

class MarkdownParser:
    HEADING = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    def parse(self, file_path: Path) -> ParseResult:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lines  = source.splitlines()
        file_id = str(file_path).replace("\\", "/")
        name_lower = file_path.name.lower()
        is_skill   = "skill" in name_lower or name_lower == "readme.md"
        root_kind: NodeKind = "Skill" if is_skill else "File"
        h1 = re.search(r"^#\s+(.+)$", source, re.MULTILINE)
        file_title = h1.group(1).strip() if h1 else file_path.stem
        nodes: list[CodeNode] = []
        edges: list[CodeEdge] = []
        file_node = CodeNode(id=file_id, kind=root_kind, name=file_title,
                             file_path=file_id, start_line=1, end_line=len(lines), state="unknown")
        nodes.append(file_node)
        headings = list(self.HEADING.finditer(source))
        for idx, m in enumerate(headings):
            level = len(m.group(1))
            if level > 3: continue
            title  = m.group(2).strip()
            lineno = source[:m.start()].count("\n") + 1
            end_lineno = len(lines)
            for next_m in headings[idx + 1:]:
                if len(next_m.group(1)) <= level:
                    end_lineno = source[:next_m.start()].count("\n") + 1
                    break
            nid = f"{file_id}::{title.replace(' ', '_')}"
            nodes.append(CodeNode(id=nid, kind="Section", name=title,
                                  file_path=file_id, start_line=lineno, end_line=end_lineno, state="unknown"))
            edges.append(CodeEdge(file_id, nid, "DEFINES"))
        return ParseResult(nodes=nodes, edges=edges, file_path=file_id,
                           language="markdown", total_lines=len(lines))


# ---------------------------------------------------------------------------
# Exclusiones de directorios
# ---------------------------------------------------------------------------

EXCLUDED_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".git",
    "dist", "build", ".next", ".nuxt", "out", "coverage",
    ".cache", ".turbo", ".vercel", ".parcel-cache", "target",
    ".pytest_cache", ".mypy_cache", "vendor", "Pods",
}

MAX_FILE_SIZE_BYTES = 1_000_000
MAX_LINE_LENGTH = 5_000

def _looks_minified_or_huge(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES: return True
        if size > 2000:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(4000)
            if "\n" not in head[:MAX_LINE_LENGTH]: return True
    except OSError:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_ast_parser: ASTParser | None = None
_regex_parser = RegexParser()
_md_parser    = MarkdownParser()

def _get_ast_parser() -> ASTParser | None:
    global _ast_parser
    if _ast_parser is None and _ts_available():
        try:
            _ast_parser = ASTParser()
        except Exception:
            _ast_parser = None
    return _ast_parser


def parse_file(path: Path) -> ParseResult:
    """Parsea un archivo. Usa AST (tree-sitter) si está disponible, regex como fallback."""
    if path.suffix.lower() in (".md", ".mdx"):
        return _md_parser.parse(path)
    ast = _get_ast_parser()
    if ast:
        try:
            return ast.parse(path)
        except Exception:
            pass
    return _regex_parser.parse(path)


def parse_directory(
    root: Path,
    extensions: set[str] | None = None,
    known_hashes: dict[str, str] | None = None,
) -> tuple[list[ParseResult], int]:
    """
    Parsea recursivamente todos los archivos soportados en un directorio.

    Si known_hashes se pasa (dict file_path → sha256), solo parsea los archivos
    cuyo hash actual difiere del conocido (re-indexado incremental).

    Retorna (results, skipped_count) donde skipped_count es cuántos archivos
    se saltearon por no haber cambiado.
    """
    import hashlib
    exts = extensions or set(SUPPORTED_EXTENSIONS.keys())
    results = []
    skipped = 0

    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in exts and path.is_file():
            parts = path.parts
            if any(p in EXCLUDED_DIRS for p in parts): continue
            if _looks_minified_or_huge(path): continue

            # Re-indexado incremental: saltear archivos que no cambiaron
            if known_hashes is not None:
                file_id = str(path).replace("\\", "/")
                try:
                    current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                    if known_hashes.get(file_id) == current_hash:
                        skipped += 1
                        continue
                except Exception:
                    pass

            try:
                results.append(parse_file(path))
            except Exception:
                pass

    _resolve_import_edges(results, root)
    return results, skipped


# ---------------------------------------------------------------------------
# Resolución de CALLS: conectar __call__X con el nodo real del grafo
# ---------------------------------------------------------------------------

def resolve_call_edges(results: list[ParseResult]):
    """
    Los edges CALLS apuntan a nodos fantasma __call__X.
    Esta función los resuelve a nodos reales si existen.
    Se llama después de ingestar todo el grafo.
    """
    known_names: dict[str, str] = {}  # name → node_id
    for r in results:
        for n in r.nodes:
            if n.kind in ("Function", "Class"):
                known_names[n.name] = n.id

    for r in results:
        resolved = []
        for e in r.edges:
            if e.relation == "CALLS" and e.target_id.startswith("__call__"):
                callee_base = e.target_id[8:]  # strip "__call__"
                if callee_base in known_names:
                    e.target_id = known_names[callee_base]
                    resolved.append(e)
                # si no resuelve, descartamos (no queremos nodos fantasma)
            else:
                resolved.append(e)
        r.edges = resolved


# ---------------------------------------------------------------------------
# Resolución de imports (igual que antes)
# ---------------------------------------------------------------------------

_RESOLVE_EXTENSIONS = ["", ".ts", ".tsx", ".js", ".jsx", ".py",
                       "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]

def _resolve_import_edges(results: list[ParseResult], root: Path):
    known_files = {r.file_path for r in results}
    for result in results:
        resolved_edges = []
        for edge in result.edges:
            if edge.relation != "IMPORTS":
                resolved_edges.append(edge)
                continue
            raw = edge.metadata.get("raw_import", edge.target_id)
            source_path = Path(edge.source_id)
            candidate_base: Path | None = None
            if raw.startswith(".") and "/" in raw:
                candidate_base = (source_path.parent / raw).resolve()
            elif raw.startswith("."):
                i = 0
                while i < len(raw) and raw[i] == ".": i += 1
                dots, remainder = i, raw[i:]
                base_dir = source_path.parent
                for _ in range(dots - 1): base_dir = base_dir.parent
                remainder_path = remainder.replace(".", "/") if remainder else ""
                candidate_base = (base_dir / remainder_path).resolve() if remainder_path else base_dir.resolve()
            elif raw.startswith("@/"):
                candidate_base = (root / raw[2:]).resolve()
            else:
                dotted = raw.replace(".", "/")
                candidate_base = (root / dotted).resolve()

            matched = None
            if candidate_base:
                for ext in _RESOLVE_EXTENSIONS:
                    candidate = str(candidate_base) + ext if not ext.startswith("/") else str(candidate_base) + ext
                    if candidate.replace("\\", "/") in known_files or candidate in known_files:
                        matched = candidate.replace("\\", "/")
                        break
            if matched:
                edge.target_id = matched
                resolved_edges.append(edge)
        result.edges = resolved_edges
