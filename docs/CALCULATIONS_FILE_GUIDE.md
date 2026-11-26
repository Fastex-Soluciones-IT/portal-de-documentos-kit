# Guía del fichero de CÁLCULOS — Portal Documentos

> **Para tu agente de desarrollo.** Esta guía te enseña a **autorizar y adaptar** el fichero JSON de **cálculos**
> reutilizables y a **importarlo**. Es precisa respecto al modelo real (`CalculationCreate` en `app/models.py`) y
> a la validación de `spec` por tipo (`app/calculations/spec_validation.py`). El ejemplo embebido es **el mismo
> `sample_calculations.json`** que ya importa en producción (B15), así que es **importable verbatim**.

Cruza con la guía principal **`GET /templates/guide`** §9 (motor de cálculos: orígenes, tipos, unidades,
rendimiento, seguridad).

---

## 1. Qué es un Cálculo

Un **Cálculo** es una pieza con nombre (`key`), **versionable**, que pertenece a **UNA** plantilla (no es una
librería compartida entre plantillas). Vive en la pestaña **Cálculos** de esa plantilla, y es **reutilizable
dentro de ella**: cualquier campo de la misma plantilla puede enlazarse al mismo cálculo desde su configuración
(`calculation_binding.calculation_key` + `input_map`, ver `FIELDS_FILE_GUIDE.md`). El resultado se resuelve al
previsualizar/generar y se inserta donde el `.docx` tiene `{{ nombre }}`. Dos plantillas distintas pueden usar la
misma `key` sin colisionar — cada una es un cálculo independiente (mismo `key`, `template_id` distinto).

---

## 2. Esquema completo del fichero (`CalculationCreate`)

El cuerpo de importación es un **array** de objetos cálculo. Cada objeto:

| Campo | Tipo | ¿Obligatorio? | Reglas / valores |
|-------|------|---------------|------------------|
| `key` | string | **sí** | 1–128 caracteres. **Única por plantilla** (`(tenant_id, template_id, key)`). `snake_case`. |
| `name` | string | **sí** | 1–255 caracteres. Nombre visible. |
| `description` | string \| null | no | ≤ 1024 caracteres. |
| `calc_type` | string (Literal) | **sí** | Uno de: `formula` · `dataset_lookup` · `ai_generation` · `endpoint` · `pipeline` · `code`. |
| `output_type` | string (Literal) | no (por defecto `text`) | Uno de: `text` · `integer` · `decimal` · `number` · `date` · `boolean`. |
| `output_unit` | string \| null | no | ≤ 64 caracteres. P. ej. `EUR`, `kWp`, `EUR/kWh`. (Es la unidad **derivada** que verá un campo enlazado.) |
| `inputs` | array de objetos | no (por defecto `[]`) | Entradas declaradas: `[{name, type, required}]` (ver §3). |
| `spec` | objeto | no (por defecto `{}`) | **Específico del `calc_type`** (ver §4). Validado al importar. |
| `validation` | objeto \| null | no | Validación de salida (mín./máx.), opcional. |
| `execution_modes` | array de strings \| null | no | Cuándo se ejecuta (ver §5). Si lo omites, el backend pone un valor por defecto según el tipo. |

> `status` y `current_version` **no** se aceptan en el create/import: un cálculo importado se crea/actualiza
> siempre como **borrador (draft)** en la versión 0 (la publicación es un paso aparte, ver §6). `template_id`
> tampoco se acepta en el cuerpo: es **propiedad del servidor** y se toma siempre de la ruta (`{template_id}`);
> `CalculationPublic` lo expone en la respuesta (solo lectura).

---

## 3. Entradas declaradas (`inputs`)

Cada entrada describe un dato lógico que el cálculo consume. Forma de cada elemento:

```json
{"name": "base", "type": "number", "required": true}
```

- `name`: nombre lógico de la entrada (lo que el campo mapea en su `input_map`).
- `type`: tipo lógico (`number`, `text`, `date`…); informativo para la UI.
- `required`: si la entrada es obligatoria para ejecutar.

Un campo de plantilla enlaza estas entradas a sus propios campos vía `input_map`, p. ej.
`input_map = {"base": "importe_neto"}` (o a un literal anteponiendo `=`, p. ej. `{"base": "=1000"}`).

---

## 4. Los 5 tipos de cálculo y su `spec`

La `spec` se valida por `calc_type` al importar (`POST /templates/{template_id}/calculations/import`) — una
`spec` mal formada se rechaza con **422** antes de guardarse. (`code` es la 6.ª opción: se acepta como borrador
con `spec` libre, pero su publicación/generación está **bloqueada**.)

### 4.1 `formula` — aritmética/condicional segura

```json
{"expression": "base * 1.21"}
```
- `expression` (**obligatorio**, no vacío). Evaluador **restringido y seguro** (mismo motor que los campos
  calculados inline, `app/documents/formula.py`): operadores `+ - * / // % **`, comparaciones
  `== != < <= > >= in not in`, booleanos `and or not`, ternario `a if c else b`, y funciones de la allow-list
  exacta: `abs round min max len int float str`. Prohibido: imports, acceso a atributos, llamadas fuera de la
  allow-list, lambdas, comprehensions.
- **Rápido** (se recalcula en vivo).

### 4.2 `dataset_lookup` — busca un valor en un catálogo

```json
{"dataset_key": "irradiacion", "match_input": "municipio", "match_column": "value", "output_column": "label"}
```
- Todos **obligatorios**: `dataset_key`, `match_input`, `match_column`, `output_column`. Busca la fila del dataset
  cuya `match_column` coincide con la entrada `match_input` y devuelve su `output_column`.
- **Rápido**.

### 4.3 `ai_generation` — redacta/extrae un valor con IA

```json
{"prompt_key": "resumen_calculo", "instruction": null, "input_fields": ["potencia", "precio"], "output": null}
```
- `prompt_key` (**obligatorio**): la clave del **prompt** (kind `calculation`) que este cálculo usa/override
  (ver `AI_PROMPTS_FILE_GUIDE.md`). `instruction`, `input_fields`, `output` son opcionales.
- **Lento** (solo al generar / Recalcular).

### 4.4 `endpoint` — consulta un servicio externo (Conector)

```json
{"connector_key": "precios_energia", "method": "GET", "path": "/tarifa",
 "request_map": {"kw": "potencia"}, "response_map": {"value": "precio"}}
```
- `connector_key` (**obligatorio**): un **Conector** registrado por un administrador (URL base + credenciales
  **cifradas**; solo `https`, con guardas anti-SSRF; los secretos nunca aparecen en el documento ni en las
  trazas). `method` (por defecto `GET`), `path`, `request_map`, `response_map` son opcionales.
- **Lento**. Hay que dar de alta el conector **antes de publicar/generar** (el borrador se puede importar sin él).

### 4.5 `pipeline` — pasos en orden

```json
{"steps": [
  {"type": "dataset_lookup", "...": "..."},
  {"type": "formula", "...": "..."},
  {"type": "ai_generation", "...": "..."}
]}
```
- `steps` (**obligatorio**, **≥ 1**). Cada paso es un objeto con `type` en
  `{dataset_lookup, formula, ai_generation, endpoint}` (un paso `pipeline` o `code` **no** está permitido dentro
  de un pipeline → **422**). Los pasos se ejecutan **en orden**, sin bifurcaciones ni bucles; cada paso lee y
  escribe valores que consumen los siguientes.
- **Lento**.

### 4.6 `code` (Python/JS) — diferido

Se acepta como **borrador** (su `spec` no tiene forma obligatoria), pero su **publicación/generación está
bloqueada** (mensaje: «cálculo de código no disponible»). No lo uses para producir valores todavía.

---

## 5. `execution_modes` (cuándo se ejecuta)

- Tipos **rápidos** (`formula`, `dataset_lookup`) → por defecto `["on_change", "on_generate"]`: se recalculan en
  vivo mientras se rellena el formulario.
- Tipos **lentos** (`ai_generation`, `endpoint`, `pipeline`) → por defecto `["on_generate"]`: solo al generar el
  documento o al pulsar **«Recalcular»** (no en cada tecla, para no disparar coste de IA / llamadas externas).
- Puedes fijarlos explícitamente en el fichero; si los omites, el backend pone el valor por defecto del tipo.

---

## 6. Borrador vs publicación (lo que hace `import`)

`POST /templates/{template_id}/calculations/import` hace **upsert por `key` DENTRO de esa plantilla, sobre el
borrador (draft)**:

- `key` **nueva** (para esa plantilla) → se **crea** como borrador en `status="draft"`, `current_version=0`.
- `key` **existente** (en esa misma plantilla) → se **actualiza el borrador** (nombre/spec/inputs/…). **Nunca**
  modifica una versión publicada ni publica automáticamente ni sube `current_version`.
- Publicar es un paso aparte: `POST /templates/{template_id}/calculations/{key}/publish` (crea la versión
  inmutable N y marca como obsoletos los documentos que usan el cálculo). `code` se importa como borrador pero
  **no** se puede publicar.

---

## 7. EJEMPLO COMPLETO (importable verbatim — es `sample_calculations.json`)

```json
[
  {
    "key": "iva_total",
    "name": "Total con IVA (ejemplo)",
    "description": "Calcula el total aplicando un 21% de IVA sobre la base imponible.",
    "calc_type": "formula",
    "output_type": "number",
    "output_unit": "EUR",
    "inputs": [
      {"name": "base", "type": "number", "required": true}
    ],
    "spec": {
      "expression": "base * 1.21"
    },
    "execution_modes": ["on_change", "on_generate"]
  },
  {
    "key": "tarifa_externa",
    "name": "Tarifa desde API externa (ejemplo)",
    "description": "Consulta una tarifa a un conector HTTP. Requiere dar de alta el conector 'precios_energia' antes de publicar/generar.",
    "calc_type": "endpoint",
    "output_type": "number",
    "output_unit": "EUR/kWh",
    "inputs": [
      {"name": "potencia", "type": "number", "required": true}
    ],
    "spec": {
      "connector_key": "precios_energia",
      "method": "GET",
      "path": "/tarifa",
      "request_map": {"kw": "potencia"},
      "response_map": {"value": "precio"}
    },
    "execution_modes": ["on_generate"]
  }
]
```

---

## 8. Cómo importar

Requiere **administrador de empresa**. `AUTH="Authorization: Bearer $TOKEN"`. Un cálculo pertenece a una
plantilla, así que primero necesitas su `TEMPLATE_ID` (sube una plantilla o reutiliza una existente).

```bash
# 1. Consigue el TEMPLATE_ID (sube una plantilla, o lista las existentes con GET /templates/)
TEMPLATE_ID=$(curl -s -X POST -H "$AUTH" -F "file=@mi_plantilla.docx" -F "name=Mi plantilla" \
     http://localhost/api/v1/templates/ | jq -r .id)

# 2. Descarga el ejemplo (estático — forma exacta de /calculations/sample == array de CalculationCreate;
#    NO requiere TEMPLATE_ID, es el mismo para cualquier plantilla)
curl -s -H "$AUTH" http://localhost/api/v1/calculations/sample > calculos.json

# 3. Edítalo (array de cálculos)

# 4. Impórtalo DENTRO de esa plantilla (upsert por key sobre el borrador)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
     "http://localhost/api/v1/templates/$TEMPLATE_ID/calculations/import" -d @calculos.json
```

Respuesta: `{created, updated, items}`. **UI:** detalle de la plantilla → pestaña **Cálculos** → botón
**«Descargar ejemplo»** + flujo de importación. (También `POST /templates/{template_id}/calculations/` para
crear uno suelto.)

---

## 9. Reglas de validación y errores comunes (422 / 409)

- **`key`/`name` ausentes** o `calc_type` desconocido → **422**.
- **`spec` mal formada** para el tipo → **422** (p. ej. `endpoint` sin `connector_key`; `formula` con
  `expression` vacía; `ai_generation` sin `prompt_key`; `pipeline` sin pasos o con un paso de tipo no permitido).
- **`key` duplicada dentro del array** → **422** y **no se escribe nada** (todo-o-nada).
- **Race de creación concurrente** con la misma `(empresa, plantilla, key)` → **409**.
- **No-administrador** → **403**.
- **Idempotencia:** reimportar el mismo fichero converge (actualiza el borrador, **no** crea versiones ni sube
  `current_version`).
- **Aislamiento multi-empresa y multi-plantilla:** dos empresas pueden usar la misma `key` sin colisionar; y
  dentro de la **misma** empresa, dos plantillas distintas también pueden reutilizar la misma `key` — son
  cálculos independientes (`(tenant_id, template_id, key)` es la clave única real).

### Gotchas

- Un cálculo `endpoint` se **importa** sin tener el conector dado de alta, pero **no se podrá publicar/generar**
  hasta que exista el `connector_key`.
- Un cálculo que **falla** en ejecución **no rompe** la generación: el campo queda sin resolver (o `0` en
  aritmética) y se registra la traza **EXEC**.
- En `output_unit` el formato de salida es es-ES (decimales con coma + unidad, p. ej. `120,50 kWp`). Dentro de la
  plantilla escribe los números con **punto** decimal.

---

## 10. Referencias cruzadas

- **Cómo un campo se enlaza a un cálculo** (`calculation_binding`, `input_map`, origen calculado): `FIELDS_FILE_GUIDE.md` §4.
- **Prompts IA** (para `ai_generation.prompt_key`): `AI_PROMPTS_FILE_GUIDE.md`.
- **Motor de cálculos end-to-end** (orígenes, trazabilidad, seguridad): guía principal §9.
- El `.docx` de ejemplo (`GET /templates/sample`) muestra un campo calculado/solo-lectura que referencia un
  cálculo en vivo.
