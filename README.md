# DocAI · Templates Manager

**Un kit para convertir un Word corporativo en una plantilla de DocAI y todos sus componentes, con un
pipeline determinista: el agente de IA solo decide; el código hace el resto.**

El agente (Claude Code, Cursor…) redacta un único fichero declarativo, `inventario.yaml`, que dice qué
hueco del Word pasa a ser qué campo. La CLI `docai-kit` extrae el documento, coloca los marcadores,
genera los JSON, valida e importa. Misma entrada ⇒ mismos bytes de salida, siempre.

---

## ¿Qué es DocAI? (en una frase)

DocAI convierte **plantillas `.docx`** en **asistentes guiados de generación de documentos**: el usuario
rellena un formulario y DocAI produce el Word/PDF final. Una plantilla se compone de **campos**,
**datasets**, **cálculos** y **prompts de IA** (`docs/00-OVERVIEW.md`).

```
 plantillas/<slug>/                     docai-kit                       componentes/<slug>/
┌──────────────────────┐   extract  ┌───────────────┐   build      ┌─────────────────────┐  import   ┌────────┐
│ origen.docx (intacto)│ ─────────► │ documento.json│              │ plantilla.docx      │ ────────► │ DocAI  │
│ inventario.yaml  ◄───┼── agente ──┤ (lo lee el    │ ───────────► │ fields.json         │ (dry-run  │        │
│ datasets/calcula-    │            │  agente)      │   validate   │ datasets.json       │  por      └────────┘
│ tions/prompts.yaml   │            └───────────────┘   V01–V12    │ calculations.json   │  defecto)
│ ids.lock.json (auto) │                                           │ prompts.json        │
└──────────────────────┘                                           └─────────────────────┘
```

---

## Inicio rápido

Requisitos: [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). `uv`
instala Python 3.12 y las dependencias fijadas en `uv.lock`.

```bash
git clone https://github.com/Fastex-Soluciones-IT/portal-de-documentos-kit.git
cd portal-de-documentos-kit
uv sync

# 1. Deja tu Word como plantillas/<slug>/origen.docx
mkdir -p plantillas/contrato && cp /ruta/a/contrato.docx plantillas/contrato/origen.docx

# 2. Extrae su estructura (lo lee el agente)
uv run docai-kit extract contrato

# 3. El agente redacta plantillas/contrato/inventario.yaml (ver AGENTS.md)

# 4. Genera y valida
uv run docai-kit build contrato
uv run docai-kit validate contrato

# 5. Importa (dry-run: imprime las peticiones; --yes para ejecutar)
uv run docai-kit import contrato --entorno test
```

Con Claude Code: abre el repo (`claude`) y pide *«convierte `/ruta/a/contrato.docx` en una plantilla
DocAI siguiendo AGENTS.md»*. Claude Code carga `CLAUDE.md`, que lo dirige a `AGENTS.md`.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `docai-kit extract <slug>` | `origen.docx` → `trabajo/<slug>/documento.json` (párrafos con localizador estable) |
| `docai-kit build <slug>` | origen + inventario + YAML de dominio → `componentes/<slug>/` (byte-estable) |
| `docai-kit validate <slug> [--strict]` | Comprobaciones V01–V12, acumulando todos los fallos |
| `docai-kit infer --origen A --plantilla B -o inventario.yaml` | Recupera el inventario de una plantilla adaptada a mano |
| `docai-kit render <slug> --datos f.yaml -o salida.docx [--pdf]` | Render local para revisión |
| `docai-kit import <slug> --entorno test\|prod` | Sube a DocAI; dry-run salvo `--yes` (y `--confirm-prod`) |

Todos aceptan `--json`. Salida: `0` bien, `1` errores de validación, `2` error de uso o de entrada. La
tabla de códigos de error con su acción correctora está en `docs/02-WORKFLOW.md`.

---

## Estructura del repositorio

```
portal-de-documentos-kit/
├── README.md · CLAUDE.md · AGENTS.md · SYNC.md
├── pyproject.toml · uv.lock          ← Python 3.12, dependencias fijadas
├── src/docai_kit/                    ← la CLI (extract, build, validate, infer, render, import)
├── schemas/                          ← JSON Schema: inventario + componentes de DocAI (generados)
├── plantillas/<slug>/                ← FUENTE (lo que se edita)
│   ├── origen.docx                   ←   Word corporativo original, intocable
│   ├── inventario.yaml               ←   lo ÚNICO que redacta el agente
│   ├── ids.lock.json                 ←   nombre técnico -> FLD-xxxx (lo gestiona build)
│   ├── datasets.yaml · calculations.yaml · prompts.yaml   ← contenido de dominio, si aplica
│   └── datos_ejemplo.yaml            ←   contexto de prueba para render/validate
├── componentes/<slug>/               ← SALIDA de build (versionada, nunca editada a mano)
├── trabajo/<slug>/documento.json     ← salida de extract (no versionada)
├── docs/                             ← guías (las *GUIDE.md vienen de DocAI)
├── ejemplos/                         ← muestras canónicas de DocAI (no editar)
├── tests/                            ← pytest (fixtures generados por script)
└── tools/                            ← sync-from-docai.sh, gen_schemas.py
```

> **Mantenimiento:** las guías `docs/*GUIDE.md`, las muestras de `ejemplos/` y los esquemas de
> componentes de `schemas/` vienen de DocAI. Se actualizan con `tools/sync-from-docai.sh` (comprobación:
> `--check`). Ver **`SYNC.md`**.

## Desarrollo

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
pre-commit install          # opcional: ruff + validate en cada commit
```

CI (`.github/workflows/ci.yml`): `uv sync --frozen`, ruff, pytest, `validate` de cada plantilla y
`sync-from-docai.sh --check` cuando la fuente de DocAI está disponible.

## Licencia

© 2026 Fastex Soluciones IT. Se puede usar y compartir sin modificaciones, citando la autoría; no se puede
modificar para redistribuirlo ni vender. Condiciones completas en [`LICENSE`](LICENSE).

## Para el agente

Si eres un agente de IA: **lee `AGENTS.md` antes de hacer nada**. Solo editas `plantillas/<slug>/`;
`componentes/` lo genera `docai-kit build`.
