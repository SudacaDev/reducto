# Reducto

> Reduce tokens, not intelligence.

Reducto convierte tu codebase en un **knowledge graph local** que cualquier LLM puede consultar sin leer archivos enteros. Menos tokens, mejores respuestas, mismo resultado.

## Qué hace

- **Indexa tu proyecto** — parsea `.ts`, `.tsx`, `.js`, `.py` y `.md` extrayendo funciones, clases, imports y calls reales (AST via tree-sitter)
- **Detecta comunidades** — agrupa automáticamente archivos relacionados usando Louvain clustering
- **Guarda todo localmente** — en `reducto-out/graph.json`, sin base de datos, sin cuenta, sin internet
- **Expone el grafo via MCP** — cualquier LLM que soporte MCP (Claude Code, Antigravity, VS Code Copilot, Cursor) lo puede consultar
- **Cache inteligente (Schrödinger)** — los nodos se resuelven on-demand y se cachean con hash SHA256. Si el archivo cambia, el cache se invalida automáticamente (decoherencia)
- **Vistas por observador** — pide solo la firma (`signature`), un resumen (`summary`), o el código completo (`full`) — cada vista se cachea independientemente

## Requisitos

- **Python 3.10+** (probado hasta 3.13)
- **uv** (recomendado) o pip

### Opcional (para parsing AST real)

```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript --user
```

Sin esto, Reducto usa un parser regex que funciona pero es menos preciso. Con tree-sitter se detectan CALLS reales (función→función).

## Instalación

### Opción 1: con pip (la más simple)

```bash
pip install git+https://github.com/SudacaDev/reducto.git --user
```

### Opción 2: con uv (más rápido)

```bash
uv tool install --from git+https://github.com/SudacaDev/reducto.git reducto
```

### Opción 3: clonar y instalar local

```bash
git clone https://github.com/SudacaDev/reducto.git
cd reducto
pip install . --user
# o con uv:
uv tool install --from . reducto
```

### Opcional: tree-sitter para parsing AST real

```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript --user
```

Sin esto, Reducto funciona con regex (menos preciso). Con tree-sitter detecta CALLS reales (función→función).

### Verificar

```bash
reducto --help
```

### Actualizar a la última versión

```bash
pip install git+https://github.com/SudacaDev/reducto.git --user --force-reinstall
# o con uv:
uv tool install --from git+https://github.com/SudacaDev/reducto.git reducto --force
```

## Primeros pasos

```bash
# 1. Ir a tu proyecto
cd mi-proyecto

# 2. Indexar el código (primera vez)
reducto ingest . --clean

# 3. Conectar con tu IDE
reducto install
#   → te pregunta qué IDEs querés configurar
#   → o directo: reducto install --target all

# 4. Listo — abrí tu IDE y preguntale algo sobre el proyecto
```

## Uso diario

```bash
# Re-indexar después de cambios (solo procesa archivos modificados)
reducto ingest .

# Buscar en el grafo
reducto query "auth"
reducto query "getSession" --resolve

# Ver stats de ahorro de tokens
reducto context

# Ver el grafo visualmente
reducto visualize
# → abre reducto-out/graph.html en el navegador

# Agregar un skill de arquitectura desde GitHub
reducto skill https://github.com/SudacaDev/react-architecture
```

## Comandos

| Comando | Qué hace |
|---|---|
| `reducto ingest . [--clean]` | Indexa el proyecto (`--clean` = rebuild completo) |
| `reducto install [--target X]` | Configura tu IDE (claude-code, antigravity, vscode, cursor, all) |
| `reducto query "término" [--resolve]` | Busca en el grafo (`--resolve` = carga el código fuente) |
| `reducto context` | Muestra tokens usados y ahorrados |
| `reducto visualize` | Genera un HTML interactivo del grafo |
| `reducto skill <url>` | Descarga e indexa un skill desde GitHub |
| `reducto serve` | Levanta el MCP server (el IDE lo usa automáticamente) |

## IDEs soportados

| IDE | Config generada |
|---|---|
| Claude Code | `.mcp.json` + `CLAUDE.md` + slash commands |
| Antigravity (Google) | `AGENTS.md` + `~/.gemini/antigravity/mcp_config.json` |
| VS Code (Copilot) | `.vscode/mcp.json` |
| Cursor | `.cursor/mcp.json` + `.cursorrules` |

## Cómo funciona

```
reducto ingest .      ← parsea el código, extrae nodos y edges, detecta comunidades
                        todo queda en reducto-out/graph.json

Tu IDE pregunta algo → LLM consulta Reducto via MCP (search_context, get_callers, etc.)
                     → Reducto busca en el grafo (metadata, ~10 tokens)
                     → Si necesita el código: resuelve el nodo (lee solo esas líneas)
                     → Lo cachea con hash SHA256 (próxima vez = 0 tokens)
                     → Si el archivo cambió: invalida el cache automáticamente
```

## Archivos generados

```
tu-proyecto/
  reducto-out/          ← gitignored
    graph.json          ← el grafo completo
    graph.html          ← visualización interactiva
    session_stats.json  ← stats de tokens
  .mcp.json             ← config MCP para Claude Code
  CLAUDE.md             ← routing rules para Claude Code
  AGENTS.md             ← routing rules para Antigravity
  .reducto/
    skills/             ← skills descargados con `reducto skill`
```

## Troubleshooting

**"tree-sitter no disponible"** — Reducto funciona sin tree-sitter (usa regex), pero para CALLS reales necesitás instalarlo: `pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript --user`

**"error: Failed to install entrypoint" en Windows** — Cerrá Antigravity/Claude Code (tienen `reducto.exe` bloqueado) y reintentá.

**"UnicodeEncodeError" en Windows** — Setear `$env:PYTHONUTF8 = "1"` antes de correr Reducto, o agregarlo permanente: `[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")`

**El MCP no conecta en Antigravity** — Verificá que `~/.gemini/antigravity/mcp_config.json` tenga la entrada de reducto. Corré `reducto install --target antigravity` para regenerarlo.

## Licencia

MIT
