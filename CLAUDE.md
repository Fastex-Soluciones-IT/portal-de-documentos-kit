# CLAUDE.md — Instrucciones para Claude Code en este repo

Este repositorio es un **kit para convertir un Word corporativo en una plantilla de DocAI** y todos sus
componentes (campos, datasets, cálculos, prompts). El trabajo lo hace la CLI determinista **`docai-kit`**;
tú solo decides qué hueco es qué campo, en `plantillas/<slug>/inventario.yaml`.

## Qué hacer cuando el usuario te lo pida

Cuando el usuario diga algo como *«adapta este Word»* / *«genera la plantilla»* / *«empieza»*:

1. **Lee `AGENTS.md`** — es tu procedimiento completo. Síguelo al pie de la letra.
2. Ejecuta `uv run docai-kit extract <slug>` y lee `trabajo/<slug>/documento.json`.
3. Redacta `plantillas/<slug>/inventario.yaml` (y los YAML de dominio si hacen falta). Es la única parte
   creativa. Usa las guías de `docs/` como referencia normativa del modelo de DocAI.
4. `uv run docai-kit build <slug>` y `uv run docai-kit validate <slug>`. Si fallan, corrige **solo** el
   inventario y repite hasta 0 errores.
5. Entrega el resumen y el comando `uv run docai-kit import <slug> --entorno test` (dry-run). **No importes
   nada sin confirmación del usuario.**

## Reglas

- **Prohibido** editar `componentes/` a mano o editar el `.docx` con el MCP de Word. El MCP de Word es
  opcional y solo de lectura (`docs/01-MCP-SETUP.md`).
- No toques `origen.docx` ni `ids.lock.json`.
- No inventes el modelo de datos: respeta las guías (`docs/*GUIDE.md`); `schemas/` lo hace cumplir.
- No toques secretos ni credenciales. `import` las lee solo de `DOCAI_HOST`, `DOCAI_USER`, `DOCAI_PASS`.
- Si `uv` no está en el `PATH`, usa `~/.local/bin/uv` o un shell de login (`bash -lc 'uv …'`).

## Mantenimiento del kit

Las guías de `docs/*GUIDE.md`, las muestras de `ejemplos/` y los esquemas de `schemas/` (salvo
`inventario`, `documento` e `ids_lock`, que son propios del kit) vienen de DocAI. Actualízalos solo con
`tools/sync-from-docai.sh` (ver `SYNC.md`); no los edites a mano.

> Arranque: si el usuario abre el repo sin contexto, dile en una línea qué es esto y pídele el `.docx`
> que quiere convertir (o que confirme cuál de `plantillas/` usar), y luego ejecuta el flujo de `AGENTS.md`.
