"""
reducto.engine.ast_parser
-------------------------
Parser basado en tree-sitter AST.
"""

from pathlib import Path
from reducto.models import CodeNode, CodeEdge, ParseResult

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
