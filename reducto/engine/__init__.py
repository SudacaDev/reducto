"""
reducto.engine
--------------
Parsing engine to extract AST nodes, edges, and dependencies.
"""
from reducto.engine.ast_parser import ASTParser, detect_language
from reducto.engine.regex_parser import RegexParser
from reducto.engine.markdown_parser import MarkdownParser
from reducto.engine.orchestrator import parse_file, parse_directory, resolve_call_edges

__all__ = [
    "ASTParser",
    "detect_language",
    "RegexParser",
    "MarkdownParser",
    "parse_file",
    "parse_directory",
    "resolve_call_edges",
]
