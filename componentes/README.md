# componentes/ — Salida de `docai-kit build` (no editar a mano)

Cada subcarpeta `componentes/<slug>/` la genera `docai-kit build <slug>` a partir de
`plantillas/<slug>/` y se versiona tal cual. **No se edita a mano**: `docai-kit validate` (V11) reconstruye
en limpio y falla si algún fichero no coincide byte a byte.

| Fichero | Contenido | Esquema / guía | Se importa con |
|---|---|---|---|
| `plantilla.docx` | El Word con marcadores `{{ }}` / `{%tr %}` / `{%p %}` | `../docs/TEMPLATE_AUTHORING_GUIDE.md` | `POST /api/v1/templates/` → `TEMPLATE_ID` |
| `datasets.json` | Catálogos y cascadas (globales a la empresa) | `../schemas/datasets.schema.json` | `POST /api/v1/datasets/import` |
| `calculations.json` | Cálculos de la plantilla | `../schemas/calculations.schema.json` | `POST /api/v1/templates/{TEMPLATE_ID}/calculations/import` |
| `prompts.json` | Prompts IA de la plantilla | `../schemas/prompts.schema.json` | `POST /api/v1/templates/{TEMPLATE_ID}/prompts/import` |
| `fields.json` | Configuración de campos (`FLD-xxxx`) | `../schemas/fields.schema.json` | `PUT /api/v1/templates/{TEMPLATE_ID}/fields/import` |

Para importar, usa `docai-kit import <slug> --entorno test` (dry-run por defecto). Orden: datasets →
plantilla → cálculos → prompts → campos.
