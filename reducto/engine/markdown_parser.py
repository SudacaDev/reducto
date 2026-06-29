"""
reducto.engine.markdown_parser
------------------------------
Parser para archivos markdown (.md, .mdx).
"""

import re
from pathlib import Path
from reducto.models import CodeNode, CodeEdge, ParseResult, NodeKind

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
