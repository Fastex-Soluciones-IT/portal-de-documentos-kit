# 00 · El modelo de componentes de DocAI

Una **plantilla DocAI** = un `.docx` con marcadores + un conjunto de **componentes** que definen cómo se
rellena y se calcula. Esta es la foto de conjunto; el detalle de cada uno está en su guía.

## Los componentes

| Componente | Qué es | Fichero importable | Guía |
|---|---|---|---|
| **Plantilla `.docx`** | El Word con marcadores `{{ }}` (Jinja), tablas `{%tr for %}`, condicionales `{%p if %}`. Es la *forma* del documento final. | el propio `.docx` | `TEMPLATE_AUTHORING_GUIDE.md` |
| **Campos** | La definición del formulario: cada dato que el usuario rellena o que se calcula. Cada campo tiene un **ID estable `FLD-xxxx`**, un tipo, una sección y un **origen de valor** (`value_origin`). Propios de la plantilla. | `fields.json` (array `FieldConfig`) | `FIELDS_FILE_GUIDE.md` |
| **Datasets** | Catálogos de valores **reutilizables y compartibles** entre plantillas (provincias, tarifas…). Soportan **cascadas** padre→hijo. Un campo se conecta con `options_source`. | `datasets.json` (`TemplateDatasetCreate`) | `DATASETS_FILE_GUIDE.md` |
| **Cálculos** | El **motor de cálculos**: valores derivados de otros. Tipos (`calc_type`): `formula`, `dataset_lookup`, `endpoint` (API externa vía conector), `ai_generation`, `pipeline`. Versionables; pertenecen a **una** plantilla y se reutilizan dentro de ella por `calculation_key`. Código Py/JS diferido. | `calculations.json` (`CalculationCreate`) | `CALCULATIONS_FILE_GUIDE.md` |
| **Prompts IA** | Instrucciones de IA propias de la plantilla: mejorar texto (`improve`), autocompletar un campo (`field`), generar (`generate`) o alimentar un cálculo (`calculation`). | `prompts.json` (`AIPromptCreate`) | `AI_PROMPTS_FILE_GUIDE.md` |

## Cómo encajan

```
            ┌──────────────────────── Plantilla .docx ────────────────────────┐
            │  {{ cliente }}   {%tr for m in modulos %}{{ m.nombre }}{%tr endfor %}  │
            │  {%p if incluir_anexo %} …cláusula… {%p endif %}   {{ coste_anual }}  │
            └───────▲───────────────────────▲───────────────────────▲──────────┘
                    │                        │                       │
              campo manual            campo lista              campo calculado
                    │                        │                       │
   Campos (FieldConfig) ──── value_origin ───┴───────────┐           │
        │  options_source                                │           │
        ▼                                                 ▼           ▼
    Datasets (cascadas)                          Cálculos ◄── calculation_binding
                                                     │  (endpoint → Conector)
                                                     ▼
                                              Prompts IA (kind: calculation/field)
```

## El concepto clave: `value_origin`

Cada campo tiene un **origen de valor** que decide de dónde sale su contenido:

- `manual` — lo teclea el usuario.
- `dataset` — se elige de un catálogo (desplegable / cascada).
- `formula` — se calcula con una expresión segura inline (clave `formula` del campo).
- `ai` / `endpoint` / `pipeline` — lo **calcula** DocAI con un cálculo reutilizable: el campo lleva un
  `calculation_binding` que apunta a un cálculo de la misma plantilla por `calculation_key` y mapea sus
  entradas (`input_map`) a otros campos.

El **mismo marcador** `{{ x }}` en el `.docx` no sabe de dónde viene `x`: eso lo define el campo. Por eso
puedes adaptar el Word primero y afinar el origen de cada valor en los componentes después.

## Multi-tenant y seguridad (contexto)

DocAI es multi-empresa: cada componente pertenece a una organización y está aislado por fila (RLS). La
gestión de componentes (crear/importar) requiere **administrador de empresa**. Los **conectores** de los
cálculos `endpoint` guardan credenciales **cifradas** y tienen guardas anti-SSRF; se dan de alta dentro de
DocAI, **nunca** en los ficheros de este kit.

## Cómo los produce este kit

Ninguno de estos ficheros se escribe a mano. El agente redacta `plantillas/<slug>/inventario.yaml` (qué
hueco del Word es qué campo, tabla repetible o condicional) y, si aplica, los YAML de dominio
(`datasets.yaml`, `calculations.yaml`, `prompts.yaml`, con las mismas claves que los JSON de DocAI).
`docai-kit build` genera la plantilla `.docx` y los cuatro JSON en `componentes/<slug>/`, y
`docai-kit validate` comprueba que son coherentes entre sí y con los esquemas de `schemas/` (generados
desde los modelos de DocAI).

Siguiente: **`02-WORKFLOW.md`** (la receta paso a paso). El MCP de Word es opcional y solo de lectura
(**`01-MCP-SETUP.md`**).

---

## Secciones reutilizables y documentos compuestos (Epic S)

DocAI soporta también **Secciones** (`Template.kind='section'`): plantillas especializadas que se usan como
bloques de contenido reutilizables. Se pueden combinar en **plantillas compuestas** o en **documentos de
proyecto compuestos**. Toda la maquinaria de una plantilla (campos, datasets, cálculos, versiones, render)
funciona igual en una sección.

| Concepto | Qué es |
|---|---|
| **Sección** | `Template` con `kind='section'`. Diseñada igual que una plantilla: mismo `.docx`, mismos componentes. |
| **Plantilla compuesta** | `Template` con `compose_mode='sections'`. Define una lista ordenada de secciones (`TemplateComposition`) que se concatenan al renderizar. |
| **Documento compuesto** | `FormSubmission` con filas `SubmissionSection`. El autor elige y ordena secciones de la biblioteca; cada sección tiene sus propios datos y se concatena al generar. |

El flujo de autoría de componentes (campos, datasets, cálculos) es idéntico al de una plantilla ordinaria.
Para el flujo completo de composición desde el proyecto, consulta **`docs/TEMPLATE_AUTHORING_GUIDE.md` §18**.
