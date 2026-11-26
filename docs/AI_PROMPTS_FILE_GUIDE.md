# Guía del fichero de PROMPTS IA — Portal Documentos

> **Para tu agente de desarrollo.** Esta guía te enseña a **autorizar y adaptar** el fichero JSON de **prompts de
> IA** (los prompts **propios de una plantilla** que **override** los prompts integrados) y a **importarlo**. Es
> precisa respecto al modelo real (`AIPromptCreate` en `app/models.py`) y a la ruta
> `POST /templates/{template_id}/prompts/import`. El ejemplo embebido es **el mismo `sample_prompts.json`** que ya
> importa en producción (B15), así que es **importable verbatim**.

---

## 1. Qué es un prompt de la plantilla

Cada fila es un prompt que pertenece a **UNA** plantilla (no es una biblioteca compartida entre plantillas) y
**override o extiende** un prompt integrado, identificado por su `key` y su `kind`. Vive en la pestaña
**Prompts** de esa plantilla. Permite personalizar el tono/instrucción de las acciones de IA (mejorar texto,
generar un campo, generar libre, o un cálculo `ai_generation`) **para esa plantilla**, sin tocar código. Cuando
la plantilla activa no define un override para una acción, el copilot **cae al prompt integrado** (built-in) —
nunca falla por falta de prompt.

---

## 2. Esquema completo del fichero (`AIPromptCreate`)

El cuerpo de importación es un **array** de objetos prompt. Cada objeto:

| Campo | Tipo | ¿Obligatorio? | Reglas / valores |
|-------|------|---------------|------------------|
| `key` | string | **sí** | 1–128 caracteres. **Única por plantilla (`(tenant, template_id, key)`)** — el `kind` NO forma parte de la clave de unicidad. Dos plantillas distintas pueden reutilizar la misma `key` sin colisionar. |
| `kind` | string (Literal) | no (por defecto `improve`) | Uno de: `improve` · `generate` · `field` · `calculation`. Validado contra el Literal — un `kind` desconocido → **422**. |
| `name` | string | **sí** | 1–255 caracteres. Nombre visible. |
| `description` | string \| null | no | ≤ 1024 caracteres. |
| `instruction` | string | **sí** | 1–8192 caracteres. La **instrucción** que se inyecta en el prompt del sistema (sustituye a la integrada). |

> `template_id` es **propiedad del servidor**: no se acepta en el cuerpo de `AIPromptCreate`/`AIPromptUpdate` — se
> toma siempre de la ruta (`{template_id}`). `AIPromptPublic` lo expone en la respuesta (solo lectura).

---

## 3. Los 4 `kind` (a qué operación de IA apuntan)

| `kind` | Qué override | `key` típica |
|--------|--------------|--------------|
| `improve` | Una **acción de mejora** de texto (la operación `POST /ai/improve`), p. ej. corregir/expandir/resumir. | el nombre de la acción, p. ej. `expandir`, `correct` |
| `generate` | La **generación libre** (`POST /ai/generate`). | una clave libre, p. ej. `generate` |
| `field` | La **generación por campo** (`POST /ai/generate-field`). | el nombre del campo (p. ej. `objeto`, o `field:objeto`) |
| `calculation` | El prompt de un **cálculo `ai_generation`** — referenciado por su `spec.prompt_key`. | la `prompt_key` del cálculo |

> La unicidad de almacenamiento es por **`(tenant_id, template_id, key)`** — dentro de la **misma** plantilla no
> puedes tener dos prompts con la misma `key` aunque tengan distinto `kind` (el segundo da **409** / actualiza al
> primero). El `kind` solo afecta a la **RESOLUCIÓN** del override (kind-aware, ver §4), **no** al namespace de la
> clave. Dos plantillas distintas SÍ pueden reutilizar la misma `key` sin colisionar — son prompts independientes.

---

## 4. Cómo resuelven los override (lo que el agente debe saber)

Los override se resuelven **dentro de la plantilla activa** (la que está usando la operación de IA en curso), de
forma **transparente** (funciona aunque la UI no envíe una `prompt_key`):

- Un `prompt_key` **explícito** en la petición siempre gana (buscado dentro de esa misma plantilla).
- Si no, se **auto-resuelve por la clave natural** de la llamada **y su `kind`**, dentro de la plantilla activa:
  el nombre de la acción para `/improve` (p. ej. `expandir`), el nombre del campo para `/generate-field` (p. ej.
  `field:objeto` y luego `objeto`), o `generate` para la generación libre.
- La resolución es **kind-aware**: cada operación pasa su `kind`, así que un prompt solo override la operación
  para la que fue escrito. Si la plantilla activa **no define** un override para esa `(key, kind)` — o si la
  llamada no lleva `template_id` (sin contexto de plantilla) — se usa el prompt **integrado** (built-in); nunca
  falla por falta de prompt.

Para un cálculo `ai_generation`, su `spec.prompt_key` se resuelve contra un prompt de `kind="calculation"` con esa
`key` **dentro de la misma plantilla que el cálculo** (ver `CALCULATIONS_FILE_GUIDE.md` §4.3).

---

## 5. EJEMPLO COMPLETO (importable verbatim — es `sample_prompts.json`)

```json
[
  {
    "key": "expandir",
    "kind": "improve",
    "name": "Expandir texto (ejemplo)",
    "description": "Override de ejemplo para la acción 'mejorar': amplía el texto manteniendo el tono.",
    "instruction": "Amplía el texto del usuario en español, manteniendo el tono formal y sin inventar datos."
  },
  {
    "key": "objeto_contrato",
    "kind": "field",
    "name": "Objeto del contrato (ejemplo)",
    "description": "Prompt de ejemplo para autocompletar el campo 'objeto'.",
    "instruction": "Redacta el objeto del contrato a partir de los datos del formulario, en una frase clara."
  },
  {
    "key": "resumen_calculo",
    "kind": "calculation",
    "name": "Resumen de cálculo (ejemplo)",
    "description": "Prompt de ejemplo de tipo 'calculation': genera un texto a partir de valores calculados, referenciable por un cálculo ai_generation.",
    "instruction": "Genera un resumen en español del coste anual estimado a partir de la potencia y el precio facilitados."
  }
]
```

---

## 6. Cómo importar

Requiere **administrador de empresa**. `AUTH="Authorization: Bearer $TOKEN"`. Un prompt pertenece a una
plantilla, así que primero necesitas su `TEMPLATE_ID` (sube una plantilla o reutiliza una existente).

```bash
# 1. Consigue el TEMPLATE_ID (sube una plantilla, o lista las existentes con GET /templates/)
TEMPLATE_ID=$(curl -s -X POST -H "$AUTH" -F "file=@mi_plantilla.docx" -F "name=Mi plantilla" \
     http://localhost/api/v1/templates/ | jq -r .id)

# 2. Descarga el ejemplo (estático — forma exacta de /ai/prompts/sample == array de AIPromptCreate;
#    NO requiere TEMPLATE_ID, es el mismo para cualquier plantilla)
curl -s -H "$AUTH" http://localhost/api/v1/ai/prompts/sample > prompts.json

# 3. Edítalo (array de prompts)

# 4. Impórtalo DENTRO de esa plantilla (upsert por key)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
     "http://localhost/api/v1/templates/$TEMPLATE_ID/prompts/import" -d @prompts.json
```

Respuesta: `{created, updated, items}`. *Upsert* por `key` **dentro de la plantilla**: actualiza
`instruction`/`name`/`description`/`kind` o crea. **UI:** detalle de la plantilla → pestaña **Prompts** → botón
**«Descargar ejemplo»** + flujo de importación. (También `POST /templates/{template_id}/prompts` para crear uno
suelto.)

---

## 7. Reglas de validación y errores comunes (422 / 409)

- **`key`, `name` o `instruction` ausentes/vacíos** → **422** (los tres son obligatorios, `min_length=1`).
- **`kind` no válido** (fuera de `improve|generate|field|calculation`) → **422**.
- **`instruction` > 8192 caracteres** → **422**.
- **`key` duplicada dentro del array** → **422** y **no se escribe nada** (todo-o-nada).
- **Race de creación concurrente** con la misma `(tenant_id, template_id, key)` → **409**.
- **No-administrador** → **403**.
- **Idempotencia:** reimportar converge (actualiza, no duplica).
- **Aislamiento multi-empresa y multi-plantilla:** dos empresas pueden usar la misma `key` sin colisionar; y
  dentro de la misma empresa, dos plantillas distintas también pueden reutilizar la misma `key` sin colisionar.

### Gotchas

- La unicidad es **por `(tenant_id, template_id, key)`** — dentro de la **misma plantilla**, dos prompts con la
  misma `key` **NO** conviven aunque tengan distinto `kind` (el segundo da **409** / actualiza al primero). Al
  reimportar, el upsert empareja por `key` dentro de esa plantilla, así que **no reutilices** una `key` para dos
  propósitos distintos dentro de la misma plantilla: el `kind` afecta solo a la resolución (§4), no al namespace
  de la clave.
- Las instrucciones **no deben inventar datos**; el patrón recomendado es «redacta a partir de los datos del
  formulario/valores calculados».

---

## 8. Referencias cruzadas

- **Cálculos `ai_generation`** que referencian un prompt `kind=calculation`: `CALCULATIONS_FILE_GUIDE.md` §4.3.
- **Motor de IA** (acciones, uso/coste): la app expone `/ai/actions`, `/ai/improve`, `/ai/generate`,
  `/ai/generate-field`, `/ai/usage`.
