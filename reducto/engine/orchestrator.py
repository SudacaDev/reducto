"""
reducto.engine.orchestrator
---------------------------
Orquestador de parseo: delega a AST, Regex o Markdown parser según corresponda.
"""

from pathlib import Path
from reducto.models import ParseResult
from reducto.engine.ast_parser import detect_language, _ts_available, ASTParser, SUPPORTED_EXTENSIONS
from reducto.engine.regex_parser import RegexParser
from reducto.engine.markdown_parser import MarkdownParser

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
# Resolución de CALLS
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
            else:
                resolved.append(e)
        r.edges = resolved

# ---------------------------------------------------------------------------
# Resolución de imports
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
