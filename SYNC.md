# SYNC — Mantener el kit al día con DocAI

> **Requisito (anotado a petición del usuario, 2026-06-05):** este kit debe **actualizarse por defecto**
> cada vez que se modifique **la plantilla** (el generador / la guía de autoría / la `sample_template.docx`)
> o **el motor** (motor de cálculos y su guía) en DocAI. Las guías de `docs/` y las muestras de `ejemplos/`
> son **copias** de las fuentes canónicas; si las fuentes cambian y el kit no, el agente trabajará con
> documentación desfasada.

## Fuentes canónicas (la verdad vive en DocAI)

| En el kit | Fuente canónica en DocAI (`factoria-proyectos`) |
|---|---|
| `docs/TEMPLATE_AUTHORING_GUIDE.md` | `backend/app/samples/TEMPLATE_AUTHORING_GUIDE.md` |
| `docs/DATASETS_FILE_GUIDE.md` | `backend/app/samples/DATASETS_FILE_GUIDE.md` |
| `docs/CALCULATIONS_FILE_GUIDE.md` | `backend/app/samples/CALCULATIONS_FILE_GUIDE.md` |
| `docs/AI_PROMPTS_FILE_GUIDE.md` | `backend/app/samples/AI_PROMPTS_FILE_GUIDE.md` |
| `docs/FIELDS_FILE_GUIDE.md` | `backend/app/samples/FIELDS_FILE_GUIDE.md` |
| `ejemplos/sample_template.docx` | `backend/app/samples/sample_template.docx` (lo genera `generate_template.py`) |
| `ejemplos/sample_*.json` | `backend/app/samples/sample_*.json` |
| `ejemplos/sample_section.docx` | `backend/app/samples/sample_section.docx` (lo genera `generate_sample_section.py`) — chuleta de Sección con todos los constructos |
| `ejemplos/sample_section_fields.json` | `backend/app/samples/sample_section_fields.json` — 15 campos del ejemplo de sección |
| `ejemplos/sample_section_datasets.json` | `backend/app/samples/sample_section_datasets.json` — dataset `servicios_disponibles` con cascada |
| `ejemplos/sample_section_calculations.json` | `backend/app/samples/sample_section_calculations.json` — cálculos `coste_seccion` y `coste_con_iva_seccion` |
| `ejemplos/sample_section_prompts.json` | `backend/app/samples/sample_section_prompts.json` — prompts de campo, cálculo e improve |
| `ejemplos/sample_section_data.json` | `backend/app/samples/sample_section_data.json` — datos de ejemplo para renderizar la sección |

## Esquemas de componentes (generados)

`schemas/{fields,datasets,calculations,prompts}.schema.json` se **generan** desde los modelos Pydantic de
DocAI con `tools/gen_schemas.py`:

| Esquema | Fuente en DocAI (`factoria-proyectos/backend/`) |
|---|---|
| `fields.schema.json` | `app/models.py:FieldConfig` + `CalculationBinding`; `app/fields/config.py:_KNOWN_TYPES`, `_CALC_BACKED_ORIGINS` |
| `datasets.schema.json` | `app/models.py:TemplateDatasetCreate` + `DatasetRow` |
| `calculations.schema.json` | `app/models.py:CalculationCreate`; `app/calculations/spec_validation.py:_VALIDATORS` |
| `prompts.schema.json` | `app/models.py:AIPromptCreate` |

Sobre el JSON Schema de Pydantic, el generador añade explícitamente las reglas que DocAI valida en código
y documentan las guías (`additionalProperties: false` salvo mapas libres, tipos de campo conocidos,
binding obligatorio en orígenes `ai`/`endpoint`/`pipeline`, forma de `spec` por `calc_type`, `options`
como `{value,label}`, `inputs` como `{name,type,required}`). El orden de `properties` sigue el de las
muestras canónicas `ejemplos/sample_*.json`, que es el orden en que el kit escribe los JSON.

`tools/sync-from-docai.sh` lo ejecuta en un entorno efímero de `uv` (sin tocar ningún repo) y, con
`--check`, compara el resultado con lo versionado. `inventario`, `documento` e `ids_lock` son esquemas
**propios** del kit y se editan a mano.

> Los documentos **propios** del kit (`README.md`, `AGENTS.md`, `docs/00/01/02-*.md`, esta `SYNC.md`) **no**
> se copian: se mantienen a mano. Si cambia el **modelo de componentes** o las **rutas de import** de DocAI,
> revísalos también.

## Cómo actualizar (un comando)

```bash
# Desde la raíz del kit. Copia las fuentes canónicas → docs/ y ejemplos/ (idempotente).
tools/sync-from-docai.sh

# Comprobar sin tocar nada (exit 1 si hay desfase en guías, muestras o esquemas) — para gates/CI.
tools/sync-from-docai.sh --check

# Origen alternativo si el repo de DocAI no está en la ruta por defecto:
tools/sync-from-docai.sh --src /ruta/a/factoria-proyectos/backend/app/samples
# o:  DOCAI_SAMPLES=/ruta/... tools/sync-from-docai.sh
```

Tras un sync con cambios: **revisa el diff y haz commit** en el repo del kit.

## La regla "por defecto" (para agentes que tocan DocAI)

En el repo de DocAI (`factoria-proyectos`), la regla está anotada en `AGENTS.md`:

> Tras modificar `backend/app/samples/*GUIDE.md`, `generate_template.py`/`sample_template.docx`, los
> `sample_*.json`, o el comportamiento del **motor de cálculos** / **plantillas** que esas guías describen,
> **ejecuta el sync del Templates Manager kit por defecto** (`tools/sync-from-docai.sh`) y commitea el kit,
> como parte del mismo cambio. Verifica con `--check` en el gate.

Así, una modificación en plantilla/motor arrastra **por defecto** la actualización del kit, sin pasos
manuales olvidados.
