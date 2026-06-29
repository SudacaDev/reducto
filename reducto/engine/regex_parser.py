"""
reducto.engine.regex_parser
---------------------------
Fallback automático a regex si tree-sitter no está disponible.
"""

import re
from pathlib import Path
from reducto.models import CodeNode, CodeEdge, ParseResult
from reducto.engine.ast_parser import detect_language

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
