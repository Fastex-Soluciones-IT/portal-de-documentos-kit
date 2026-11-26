# 01 · MCP de Word (opcional, solo lectura)

> **El pipeline no necesita el MCP de Word.** `docai-kit extract` lee el `.docx` (párrafos, tablas,
> cuadros de texto, cabeceras, pies y notas) y `docai-kit build` coloca los marcadores. El MCP
> **`word-document-server`** ([Office-Word-MCP-Server](https://github.com/GongRzhe/Office-Word-MCP-Server))
> queda como herramienta **opcional y de solo lectura**, por ejemplo para ver comentarios o el XML crudo
> mientras se redacta el inventario.
>
> **Prohibido** usar sus herramientas de edición (`search_and_replace`, `insert_*`, `add_*`, `format_*`,
> `delete_*`, `copy_document`…) sobre `plantillas/` o `componentes/`: el `.docx` de la plantilla lo
> genera `build` de forma determinista y `validate` (V11) detecta cualquier edición a mano.

## A. Requisitos

- **Python ≥ 3.11** y `pip` (o [`uv`/`uvx`](https://github.com/astral-sh/uv)).
- El servidor usa `python-docx`, `fastmcp`, `msoffcrypto-tool`, `docx2pdf`, `python-dotenv`.

## B. Configuración (elige UNA)

### Opción 1 — `uvx`, sin instalar (recomendada, ya en `.mcp.json`)

No requiere clonar nada; `uvx` descarga el paquete publicado. La config del repo lanza `uvx` a través de un
**shell de login** (`bash -lc`) para que `~/.local/bin` (donde el instalador de `uv` deja `uvx`) esté en el
`PATH` aunque el cliente MCP arranque sin cargar tu perfil:

```json
{
  "mcpServers": {
    "word-document-server": {
      "command": "bash",
      "args": ["-lc", "exec uvx --from office-word-mcp-server word_mcp_server"]
    }
  }
}
```

> Si `uvx` ya está en el `PATH` de tu cliente (o en Windows sin `bash`), puedes usar la forma directa
> `"command": "uvx", "args": ["--from", "office-word-mcp-server", "word_mcp_server"]`. Requisito: `uv`
> instalado (`curl -LsSf https://astral.sh/uv/install.sh | sh`) y **Python ≥ 3.11**.

### Opción 2 — Clon local (tienes el repo en `C:\codigo\Office-Word-MCP-Server`)

```bash
cd C:\codigo\Office-Word-MCP-Server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt      # Linux/WSL/macOS
```

Config (Windows, usando el Python del venv):

```json
{
  "mcpServers": {
    "word-document-server": {
      "command": "C:\\codigo\\Office-Word-MCP-Server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\codigo\\Office-Word-MCP-Server\\word_mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:\\codigo\\Office-Word-MCP-Server",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

En Linux/WSL/macOS, cambia a `.venv/bin/python` y rutas con `/`. El repo incluye `setup_mcp.py`, que
prepara el venv y **genera esta configuración** automáticamente: `python setup_mcp.py`.

### Dónde va la configuración

- **Claude Code (este repo):** ya está en `.mcp.json` (raíz del kit). Acepta el servidor al abrir el repo.
- **Claude Desktop:** `claude_desktop_config.json`
  - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
  - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Cursor / otros:** su panel de MCP servers, con los mismos `command`/`args`.

Reinicia el cliente tras editar la config.

## C. Rutas de archivo

El MCP opera sobre rutas de archivo del sistema. Úsalo solo para **leer** `plantillas/<slug>/origen.docx`
(o la `componentes/<slug>/plantilla.docx` generada). Si el cliente MCP arranca con otro directorio de
trabajo, pasa rutas absolutas.

## D. Comprobación rápida

Pide al agente: *«dame el outline de `plantillas/<slug>/origen.docx`»*. Debe responder usando
`get_document_outline`. Si falla, revisa la config.

---

## Herramientas que sí se pueden usar (solo lectura)

- `get_document_text`, `get_document_outline`, `get_document_info` — texto, títulos y metadatos.
- `get_document_xml` — XML crudo (estructura fina de tablas, campos de Word).
- `get_paragraph_text_from_document`, `find_text_in_document` — localizar un texto.
- `list_available_documents` — listar `.docx` de un directorio.
- `get_all_comments`, `get_comments_by_author`, `get_comments_for_paragraph` — comentarios del autor del
  Word (útiles para entender qué es cada hueco).

> Para todo lo demás usa `documento.json` (los mismos párrafos, con el localizador `id` que espera el
> inventario en `en:`, `desde:` y `hasta:`).
