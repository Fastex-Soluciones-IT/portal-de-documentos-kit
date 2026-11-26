# Guía del fichero de CAMPOS — Portal Documentos

> **Para tu agente de desarrollo.** Esta guía te enseña a **autorizar y adaptar** la configuración JSON de los
> **campos** de una plantilla (`FieldConfig`) y a **importarla**. Es precisa respecto al modelo real
> (`FieldConfig` + `CalculationBinding` en `app/models.py`) y a las rutas reales (`GET/PUT
> /templates/{id}/variables/{vid}/config`, `GET /templates/{id}/fields/export`, `PUT
> /templates/{id}/fields/import`). El ejemplo embebido es **el mismo `sample_fields.json`** que ya importa en
> producción (B15), así que es **importable verbatim** (con la salvedad del §7 sobre el cálculo enlazado).

Cruza con la guía principal **`GET /templates/guide`** §10 (gestión de campos como JSON, códigos `FLD-`,
exportar/importar, merge).

---

## 1. Qué es un campo y su código `FLD-`

Cada campo de una plantilla tiene un **código estable e inmutable por empresa** con el formato `FLD-NNNN` (p. ej.
`FLD-0023`). Se asigna automáticamente al crear el campo y **nunca cambia** (ni al renombrar, ni al editar el
JSON, ni al importar). Es el `field_id` del contrato JSON. **Es propiedad del servidor.**

Los campos son **por plantilla**: se exportan/importan **por plantilla**. En esto no son distintos de los
**cálculos** y los **prompts IA**, que ahora también son propios de la plantilla (pestañas «Cálculos» y
«Prompts» del detalle de plantilla) — lo **único** que sigue siendo global/compartido entre plantillas son los
**datasets** y los **conectores** (hub «Datos y conexiones»).

---

## 2. Esquema completo (`FieldConfig`)

| Campo | Tipo | Estado | Reglas / valores |
|-------|------|--------|------------------|
| `field_id` | string \| null | **inmutable / servidor** | El código `FLD-NNNN`. Se acepta en el cuerpo pero se **IGNORA** al escribir; identifica el campo en el import (emparejado por `code`). |
| `tenant_id` | uuid \| null | **inmutable / servidor** | Se IGNORA al escribir. |
| `unit` | string \| null | **derivado / solo lectura** | Procede de `output_unit` del **Cálculo** enlazado (si el campo es calc-backed); en otro caso `null`. **No se almacena**; se IGNORA al importar. |
| `name` | string \| null | editable | Nombre **técnico** del campo = el del marcador `{{ name }}` del Word. Un `null` explícito es **no-op** (un campo debe conservar nombre). Para un campo **nuevo** (sin coincidencia) es **obligatorio**. |
| `technical_name` | string \| null | editable | Nombre técnico alternativo (metadato). |
| `label` | string \| null | editable | Etiqueta visible (= `display_name`). |
| `type` | string \| null | editable | Tipo del campo (= `var_type`). Conjunto conocido: ver §3. Un `null` explícito es **no-op**. |
| `required` | bool | editable | Obligatorio en el formulario (por defecto `false`). |
| `description` | string \| null | editable | ≤ 2000. **La explicación detallada de qué hay que poner** en el campo: la ven las personas en el formulario y la leen los agentes de IA (MCP) para rellenarlo bien. Escríbela como se la explicarías a alguien que no ha visto el Word (formato, unidades, de dónde sale el dato, un ejemplo). |
| `help_text` | string \| null | editable | ≤ 1024. |
| `chapter` | string \| null | editable | **Sección del formulario** (datos generales vs sección — guía §4). Vacío/`null` ⇒ «Datos generales». |
| `field_order` | int | editable | Orden dentro de la sección (por defecto `0`). |
| `visible` | bool | editable | Mostrar (por defecto `true`). |
| `editable` | bool | editable | Permitir editar (por defecto `true`). Los campos calculados van en `false`. |
| `visible_when` | string \| null | editable | **Predicado condicional** (mostrar/ocultar) — guía §6. |
| `value_origin` | string (Literal) \| null | editable | Origen del valor: `manual` · `dataset` · `formula` · `ai` · `endpoint` · `pipeline` · `code`. |
| `calculation_binding` | objeto \| null | editable | Enlace a un cálculo: `{calculation_key, input_map}` (ver §4). |
| `options_source` | string \| null | editable | **Key de un dataset** → desplegable (guía §7). |
| `depends_on` | string \| null | editable | Campo padre de una **cascada** (guía §7). |
| `options` | array de `{value,label}` \| null | editable | Opciones **estáticas** (cuando no se usa dataset). |
| `default_value` | string \| null | editable | ≤ 512. |
| `formula` | string \| null | editable | Fórmula inline (cuando `value_origin=formula`/`calculated`) — guía §8. |
| `calculated` | bool | editable | `true` para un campo calculado de solo lectura (por defecto `false`). |

> **No existe** una clave `validation` a nivel de campo: `TemplateVariable` no tiene columna de validación, así que
> un `validation` entrante se **ignora** (no se persiste). La validación de salida (mín./máx.) vive en los
> **Cálculos**, no en el campo. (Guía principal §10.1.)

### 2.1 `CalculationBinding`

```json
{"calculation_key": "coste_anual", "input_map": {"potencia": "potencia_contratada"}}
```
- `calculation_key`: la `key` de un **Cálculo** existente **en esta misma plantilla** (los cálculos son propios de
  la plantilla, ver `CALCULATIONS_FILE_GUIDE.md`).
- `input_map`: mapea cada **entrada declarada** del cálculo a un **campo de ESTA plantilla** (por su `name`) o a un
  **literal** anteponiendo `=` (p. ej. `{"base": "=1000"}`).

---

## 3. Tipos de campo (`type`) válidos

Conjunto conocido aceptado por la validación de import: `text` · `textarea` · `number` · `date` · `boolean` ·
`select` · `list` · `image` · `currency` · `email` · `url`. (El analizador del `.docx` emite además los
`VarType` `coordinate`/`table`; la inferencia por nombre se describe en la guía principal §3 y en
`TEMPLATE_AUTHORING_GUIDE.md` §3.) Un `type` fuera del conjunto conocido → **422** al importar.

Qué valor espera cada tipo al rellenar un documento (se comprueba al guardar; un valor que no encaja →
**422** que nombra el campo):

| `type` | Control en el formulario | Valor |
|---|---|---|
| `text` · `textarea` | texto de una línea · de varias | cualquier texto |
| `number` · `currency` | número · número en € | `5.5`, `"5,5"`, `"1.234,56 €"` |
| `date` | fecha | `"2026-10-20"` |
| `boolean` | casilla | `true` / `false` |
| `email` · `url` | correo · enlace | `"ana@example.com"` · `"https://…"` |
| `select` | desplegable | una de sus opciones |
| `image` | subir imagen (PNG, JPEG o GIF ≤ 10 MB) | `{"image_id": "<id>"}` — el id lo devuelve `POST /api/v1/images` al subirla; el documento lleva esa imagen (tamaño natural, como mucho 16 cm de ancho) |

---

## 4. `value_origin` y coherencia con el cálculo (regla clave)

El origen decide de dónde sale el valor (guía §9). Reglas de coherencia que aplica la validación:

- `value_origin` debe ser uno de los Literales válidos; otro valor → **422** («unknown value_origin»).
- **Orígenes calc-backed** — `ai`, `endpoint`, `pipeline` — **EXIGEN** un
  `calculation_binding.calculation_key`. Si falta → **422** («requires a calculation_binding.calculation_key»).
- **Cualquier** `calculation_key` enlazado (con cualquier origen) **debe existir** como Cálculo **en esta misma
  plantilla** (no basta con que exista en otra plantilla de la empresa). Si no → **422** («calculation_key … does
  not exist in this template»).
- `manual`/`dataset`/`formula` **no** requieren binding (aunque `formula` usa la clave `formula` inline).

---

## 5. Cómo referenciar datasets, cálculos y secciones desde el campo

- **Dataset (desplegable):** `options_source = "<key del dataset>"`. **Cascada:** además `depends_on = "<campo
  padre>"` (las filas hijas del dataset llevan `parent`). Ver `DATASETS_FILE_GUIDE.md`.
- **Cálculo:** `value_origin` calculado + `calculation_binding{calculation_key, input_map}`. Ver
  `CALCULATIONS_FILE_GUIDE.md`.
- **Sección del formulario:** `chapter` (vacío ⇒ «Datos generales»). El Word manda: el analizador asigna `chapter`
  según el Título 1 anterior; aquí puedes ajustarlo (guía §4).

---

## 6. EJEMPLO COMPLETO (importable — es `sample_fields.json`)

Array en la forma del **export**: un campo **manual** + un campo **calc-bound** (origen `endpoint` con su
binding).

```json
[
  {
    "field_id": "FLD-0001",
    "name": "potencia_contratada",
    "technical_name": "potencia_contratada",
    "label": "Potencia contratada",
    "type": "number",
    "unit": null,
    "required": true,
    "description": "Potencia contratada por el cliente en kW.",
    "help_text": "Indique la potencia que figura en el contrato de suministro.",
    "chapter": "Datos de suministro",
    "field_order": 0,
    "visible": true,
    "editable": true,
    "visible_when": null,
    "value_origin": "manual",
    "calculation_binding": null,
    "options_source": null,
    "depends_on": null,
    "options": null,
    "default_value": null,
    "formula": null,
    "calculated": false
  },
  {
    "field_id": "FLD-0002",
    "name": "coste_anual_estimado",
    "technical_name": "coste_anual_estimado",
    "label": "Coste anual estimado",
    "type": "currency",
    "unit": "EUR",
    "required": false,
    "description": "Coste anual estimado, calculado a partir de la potencia y el precio.",
    "help_text": "Valor calculado automáticamente; no editable por el usuario.",
    "chapter": "Datos de suministro",
    "field_order": 1,
    "visible": true,
    "editable": false,
    "visible_when": null,
    "value_origin": "endpoint",
    "calculation_binding": {
      "calculation_key": "coste_anual",
      "input_map": {
        "potencia": "potencia_contratada"
      }
    },
    "options_source": null,
    "depends_on": null,
    "options": null,
    "default_value": null,
    "formula": null,
    "calculated": true
  }
]
```

> El segundo campo tiene `value_origin="endpoint"`, así que su `calculation_binding.calculation_key`
> (`coste_anual`) **debe existir en esta misma plantilla** antes de importar; si no, la importación devuelve
> **422**. Crea primero ese cálculo **dentro de la plantilla** (p. ej. con
> `POST /templates/{template_id}/calculations/` o `POST /templates/{template_id}/calculations/import`). Por eso
> el campo manual, por sí solo, es importable sin dependencias.

---

## 7. Por campo vs por plantilla — endpoints

### 7.1 Un solo campo (round-trip JSON)

- `GET /templates/{id}/variables/{vid}/config` → devuelve el `FieldConfig` del campo.
- `PUT /templates/{id}/variables/{vid}/config` → lo actualiza desde el **mismo** JSON. Es un **merge parcial**:
  solo se aplican las claves que **realmente envías**; una clave **omitida** deja el valor **sin tocar**; un `null`
  explícito la **borra** (salvo `name`/`type`, donde un `null` es **no-op**). `field_id`/`tenant_id`/`unit` se
  **ignoran**. Coherencia de `value_origin` validada → **422** si es incoherente.

### 7.2 Todos los campos de una plantilla (export/import masivo)

- `GET /templates/{id}/fields/export` → un **array** de `FieldConfig` (ordenado por `field_order`, `name`).
- `PUT /templates/{id}/fields/import` (**solo administrador de empresa**) → da de alta/actualiza desde un array.
  Cada campo entrante se **empareja por `code`** (`field_id`) si viene, y si no por `name`. **Nunca** se reasigna
  el código de un campo existente; los campos **nuevos** (sin coincidencia) se **crean** con un `FLD-` nuevo (y
  por eso **deben** traer `name`). Se valida **todo el conjunto primero** y se aplica **todo-o-nada**: si algún
  campo es inválido → **422** y no se escribe nada. **Reimportar el export es idempotente.**

> El import masivo aplica el `FieldConfig` **completo** (round-trip, no merge parcial): una clave ausente en un
> objeto del array **sí** toma el valor por defecto del modelo, a diferencia del PUT por campo. Por eso el patrón
> seguro es: **exporta → edita → importa** el export íntegro.

---

## 8. Cómo importar

```bash
# Ejemplo descargable (la forma del export):
curl -s -H "$AUTH" http://localhost/api/v1/templates/fields/sample > campos.json
# Edítalo (array de FieldConfig)
# Impórtalo a una plantilla concreta {id} (admin de empresa):
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
     "http://localhost/api/v1/templates/$TEMPLATE_ID/fields/import" -d @campos.json
```

**UI:** pestaña **Campos** de una plantilla → botón **«Descargar ejemplo»** + exportar/importar.

---

## 9. Reglas de validación y errores comunes (422)

- **`type` desconocido** (fuera del conjunto §3) → **422**.
- **`value_origin` desconocido** → **422**.
- **Origen calc-backed (`ai`/`endpoint`/`pipeline`) sin `calculation_binding.calculation_key`** → **422**.
- **`calculation_key` que no existe en esta plantilla** (aunque exista en otra plantilla de la empresa) → **422**.
- **Campo nuevo (sin coincidencia por `code` ni por `name`) sin `name`** → **422** («a new field requires a
  'name'»).
- **`field_id` duplicado** en el array → **422** («duplicate field_id»).
- **Dos campos nuevos con el mismo `name`** → **422** («duplicate new field name»).
- **No-administrador** en el import masivo → **403**.

### Gotchas

- `field_id`/`tenant_id`/`unit` son **propiedad del servidor**: aunque los envíes, se ignoran. No intentes
  «cambiar» un `FLD-` editando el JSON — es imposible por diseño (inmutable).
- `unit` es **derivada**: cámbiala creando/editando el `output_unit` del **Cálculo** enlazado, no en el campo.
- No incluyas una clave `validation` en el campo: se ignora (la validación de salida vive en el Cálculo).
- Para mover un campo de sección, cambia su `chapter` (o muévelo físicamente bajo otro Título 1 en el Word y
  re-sube la plantilla).

---

## 10. Referencias cruzadas

- **Datasets** (para `options_source`/`depends_on`): `DATASETS_FILE_GUIDE.md`.
- **Cálculos** (para `calculation_binding`): `CALCULATIONS_FILE_GUIDE.md`.
- **Catálogo de tipos de campo y operaciones, secciones del Word**: `TEMPLATE_AUTHORING_GUIDE.md` (guía principal),
  §10 (gestión de campos como JSON), §4 (secciones), §14 (catálogo de tipos), §15 (catálogo de operaciones).
