"""
reducto.models
--------------
Data models for the Reducto Knowledge Graph.
"""

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Constantes de estado (el gato 🐱)
# ---------------------------------------------------------------------------

STATE_UNKNOWN = "unknown"    # 🔴 Existe pero nunca fue leído
STATE_PARTIAL = "partial"    # 🟡 Leído en algún contexto
STATE_KNOWN   = "known"      # 🟢 Contexto completo cacheado

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
    state: Literal["unknown", "partial", "known"] = STATE_UNKNOWN

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
