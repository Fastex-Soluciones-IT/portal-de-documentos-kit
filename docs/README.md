# docs/ — Índice de la documentación

Lee en este orden:

1. **`00-OVERVIEW.md`** — el modelo de componentes de DocAI (campos, datasets, cálculos, prompts, plantilla)
   y cómo encajan. El concepto `value_origin`.
2. **`02-WORKFLOW.md`** — la receta paso a paso (con ejemplo): `extract` → `inventario.yaml` → `build` →
   `validate` → `import`, la tabla de comprobaciones V01–V12 y la de **códigos de error** con su acción
   correctora.
3. **`01-MCP-SETUP.md`** — el MCP de Word, ahora **opcional y de solo lectura**.

Guías de referencia por tipo de fichero (copias de DocAI, ver `../SYNC.md`; no se editan aquí):

- **`TEMPLATE_AUTHORING_GUIDE.md`** — autoría de la plantilla `.docx`: `{{ variables }}`, tablas
  `{%tr for %}`, condicionales `{%p if %}`, datasets/cascadas, campos calculados, catálogo de tipos y
  operaciones. (La guía maestra.)
- **`DATASETS_FILE_GUIDE.md`** — `TemplateDatasetCreate`: catálogos y cascadas.
- **`CALCULATIONS_FILE_GUIDE.md`** — `CalculationCreate`: los tipos de cálculo, `spec`, conectores.
- **`AI_PROMPTS_FILE_GUIDE.md`** — `AIPromptCreate`: kinds (improve/generate/field/calculation).
- **`FIELDS_FILE_GUIDE.md`** — `FieldConfig`: `FLD-xxxx`, `value_origin`, `calculation_binding`, export/import.

Los esquemas que hacen cumplir estas guías están en **`../schemas/`**; el procedimiento imperativo para el
agente, en **`../AGENTS.md`**.
