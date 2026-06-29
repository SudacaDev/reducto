# 🛠️ Project Specification: Reducto v2 Core Evolution & Restructuring

## 1. Context & Purpose
Reducto is a local knowledge graph tool designed to minimize LLM token consumption without losing contextual intelligence. This document defines the architectural specification for the next major phase of the project. Every new feature, pull request, or refactoring session must align with the pillars outlined below.

The core philosophy remains strict: **100% Local (Edge), Zero-External Infrastructure, Minimal Token Footprint.**

---

## 2. Pillar 0: Core Restructuring (Decoupling & Modular Architecture)
Before implementing advanced v2 features, the existing codebase must be refactored to separate concerns, break down monolithic components, and define clean boundaries. This ensures long-term maintainability and easier agent testing.

### Technical Requirements:
- **Separation of Concerns (SoC):** Distinct boundaries must be drawn between:
  1. *The Parsing Engine:* Responsibilities dedicated strictly to `tree-sitter` and signature/syntax extraction.
  2. *The Graph Manager:* Responsible for graph state, community clustering algorithms (Louvain), and node density calculations.
  3. *The Cache Layer:* Managing SHA256 hashing, file validation (Schrödinger Cache), and persistence.
  4. *The Protocol Layer:* Managing the MCP server endpoints, tools declaration, and routing files (`CLAUDE.md`, `.cursorrules`).
- **Domain Isolation:** Move away from shared scripts. If a module handles AST extraction, it should have no inherent awareness of how the MCP server exposes that data.
- **Interface-Driven Design:** Define clear contracts (Python ABCs or strict signatures) between layers so components can be mocked or refactored independently.

---

## 3. Pillar 1: Autonomous Skill Generation (Self-Feeding Agent Architecture)
Reducto must evolve from a passive codebase indexer into an active, self-extending framework where the LLM can generate its own analysis tools dynamically via the Model Context Protocol (MCP).

### Technical Requirements:
- **`save_autonomous_skill` MCP Tool:** Implement a new write-authorized tool in the decoupled Protocol Layer. It must accept `skill_name (str)` and `python_code (str)`.
- **Target Location:** Skills must be written deterministically inside the `.reducto/skills/` directory.
- **Hot-Reloading Pipeline:** Upon writing a new skill, the server must run a lightweight syntax validation, invalidate the affected node hashes, and hot-reload the graph into the active MCP server memory without requiring a manual server restart.
- **Skill Templates (Blueprints):** Define a strict base class or decorator syntax in Python so the LLM outputs highly predictable, reliable skill structures, minimizing code generation syntax errors.

---

## 4. Pillar 2: High-Scale Codebase Engine (Edge Big Data Patterns)
To support massive monorepos (e.g., Nx, complex micro-frontends, multi-service monoliths) without degrading local performance.

### Technical Requirements:
- **Multi-Repo Cross-Referencing (Federated Graph Data Lake):** Reducto must allow cross-graph queries. If a repository depends on another local project, Reducto should fetch only the method/component contracts (`signatures`) from the external pre-cached `graph.json`, preventing huge token overhead across interconnected codebases.
- **Local MapReduce & Streaming Ingestion:** Refactor the parsing engine to chunk files and process them concurrently across multiple CPU threads using the parallel chunking model.
  - *Map Stage:* Asynchronous parsing and token metadata/signature extraction.
  - *Reduce Stage:* Graph consolidation and execution of the Louvain Clustering algorithm to group file communities.
- **On-Demand Hybrid Semantic Cache:** Introduce an embedded, zero-configuration vector database (such as *DuckDB* with vector extensions or *LanceDB*). 
  - Structural, syntax, and dependency routing must keep using the ultra-fast AST graph (JSON/Memory).
  - Semantic vector search must only be triggered when the LLM explicitly requests abstract conceptual lookups.
- **Graph Density Analytics:** Implement a graph mining metric to calculate node centrality. Reducto should proactively warn the developer or the AI agent if a file/module becomes a highly coupled bottleneck, suggesting automated refactoring to reduce future token impact.

---

## 5. Implementation Workflow for AI Agents
When tasked with creating new features or fixing bugs based on this specification:
1. **Restructure First:** When writing or modifying logic, ensure it fits into the new decoupled directory structure defined in Pillar 0. Do not pile code into monolithic files.
2. **Analyze for Skills:** Check if the requested functionality can or should be modularized as an autonomous Reducto Skill instead of embedding it directly into the core app logic.
3. **Optimize for Scale:** Ensure any parsing or indexing logic utilizes the parallel chunking (MapReduce) model to maintain high performance in multi-gigabyte repositories.
4. **Validate Hashing:** Confirm that all generated structures adhere to the SHA256 caching layer to prevent unneeded token decoherence.