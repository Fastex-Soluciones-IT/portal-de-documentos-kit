# Guía del fichero de DATASETS — Portal Documentos

> **Para tu agente de desarrollo.** Esta guía te enseña a **autorizar y adaptar** el fichero JSON de un
> **dataset** (catálogo de valores compartido) y a **importarlo** en Portal Documentos. Es precisa respecto al modelo real
> (`TemplateDatasetCreate` en `app/models.py`) y a la ruta de importación real (`POST /datasets/import`).
> El ejemplo embebido es **el mismo `sample_dataset.json`** que ya importa correctamente en producción (B15),
> así que es **importable verbatim**.

Cruza con la guía principal: **`GET /templates/guide`** §7 (datasets y cascadas) y §10.4 (importación por API).

---

## 1. Qué es un dataset y cuándo usarlo

Un **dataset** es una tabla de valores reutilizable y **compartible entre varias plantillas** (provincias,
municipios, tarifas, tipos de instalación…). Se edita en un único sitio y se refleja en todas las plantillas que
lo usan (y marca los documentos afectados como *«desactualizados»* para regenerar bajo demanda). Una variable del
formulario se conecta a un dataset con `options_source` y se renderiza como **desplegable**; con `depends_on`
forma una **cascada** (provincia → municipio).

Usa un dataset cuando: el campo tiene un **conjunto cerrado de opciones**, esas opciones se **reutilizan** en
varias plantillas, o necesitas una **cascada** padre→hijo. Para opciones fijas de una sola plantilla puedes usar
en su lugar el campo `options` (lista estática) de la configuración de campo (ver `FIELDS_FILE_GUIDE.md`).

---

## 2. Esquema completo del fichero (`TemplateDatasetCreate`)

El cuerpo de importación es **un objeto** dataset **o un array** de ellos. Cada objeto tiene esta forma:

| Campo | Tipo | ¿Obligatorio? | Reglas / valores |
|-------|------|---------------|------------------|
| `key` | string | **sí** | 1–128 caracteres. **Clave estable** referenciada por `options_source`. **Única por empresa**. Usa `snake_case` sin espacios ni acentos (p. ej. `provincias_municipios`). |
| `name` | string | **sí** | 1–255 caracteres. Nombre visible del catálogo. |
| `description` | string \| null | no | ≤ 1024 caracteres. |
| `rows` | array de filas | no (por defecto `[]`) | Cada fila es `{value, label, parent}` (ver abajo). |

### 2.1 Forma de una fila (`DatasetRow`)

| Campo | Tipo | ¿Obligatorio? | Reglas |
|-------|------|---------------|--------|
| `value` | string | **sí** | Valor que se **almacena** cuando el usuario elige esta opción. Es lo que validará el backend (pertenencia). |
| `label` | string \| null | no | Texto **mostrado** en el desplegable. Si lo omites, la UI usa `value`. |
| `parent` | string \| null | no | **Cascada**: el `value` de la fila padre (de la MISMA tabla o de su nivel superior). `null` = nivel raíz (sin padre). |

> Nota: el modelo `DatasetRow` permite omitir `label` y `parent` (ambos por defecto `null`), pero el ejemplo y
> los exports siempre los incluyen explícitamente para que el round-trip sea claro.

---

## 3. Cascadas (padre → hijo)

Una cascada conecta dos campos (p. ej. `provincia` → `municipio`):

1. En el **dataset**, las filas hijas llevan `parent = "<value de la fila padre>"`; las filas padre llevan
   `parent = null`.
2. En el **campo hijo** (configuración de campo, ver `FIELDS_FILE_GUIDE.md`): `options_source = "<key del dataset>"`
   y `depends_on = "<nombre del campo padre>"`.
3. Al elegir el padre, la UI **filtra** las opciones hijas por `parent == valor_padre`.

En el ejemplo de abajo, `madrid_capital`/`alcala_de_henares`/`getafe` tienen `parent = "madrid"`, así que solo
aparecen cuando el usuario elige la provincia **Madrid**.

> Un mismo dataset puede contener **varios niveles** (padres con `parent=null` + hijos que los referencian),
> como aquí (provincias + sus municipios en una sola tabla). También puedes separar niveles en datasets distintos
> y encadenarlos por `depends_on` en los campos.

---

## 4. EJEMPLO COMPLETO (importable verbatim — es `sample_dataset.json`)

```json
{
  "key": "provincias_municipios",
  "name": "Provincias y municipios (ejemplo)",
  "description": "Catálogo de ejemplo con una cascada provincia -> municipio. Las filas de provincia tienen parent=null; cada municipio referencia su provincia en parent.",
  "rows": [
    {"value": "madrid", "label": "Madrid", "parent": null},
    {"value": "barcelona", "label": "Barcelona", "parent": null},
    {"value": "valencia", "label": "Valencia", "parent": null},
    {"value": "madrid_capital", "label": "Madrid", "parent": "madrid"},
    {"value": "alcala_de_henares", "label": "Alcalá de Henares", "parent": "madrid"},
    {"value": "getafe", "label": "Getafe", "parent": "madrid"},
    {"value": "barcelona_capital", "label": "Barcelona", "parent": "barcelona"},
    {"value": "hospitalet", "label": "L'Hospitalet de Llobregat", "parent": "barcelona"},
    {"value": "valencia_capital", "label": "València", "parent": "valencia"},
    {"value": "gandia", "label": "Gandia", "parent": "valencia"}
  ]
}
```

Para importar **varios** datasets de una vez, envía un **array** de objetos con esta misma forma.

---

## 5. Cómo importar

**Descarga el ejemplo → edítalo → impórtalo.** Todos los endpoints requieren **administrador de empresa**
(`company_admin`).

### 5.1 Por API (`curl`)

`AUTH="Authorization: Bearer $TOKEN"` (obtén el token con `POST /api/v1/login/access-token`).

```bash
# 1. Descarga el ejemplo (la forma exacta de /datasets/sample == TemplateDatasetCreate)
curl -s -H "$AUTH" http://localhost/api/v1/datasets/sample > dataset.json

# 2. Edítalo (key, name, filas {value,label,parent}, cascada…)

# 3. Impórtalo (acepta UN objeto o un ARRAY)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
     http://localhost/api/v1/datasets/import -d @dataset.json
```

La respuesta es un resumen `{created, updated, items}`.

### 5.2 Por UI

En la pestaña **Datos**: botón **«Descargar ejemplo»** (descarga `dataset.json`) y el flujo de importación de la
sección Datos. Un único punto de edición; los cambios se reflejan en todas las plantillas que usan el dataset.

### 5.3 También: `POST /datasets/` (crear uno)

`POST /datasets/import` es **upsert masivo idempotente**. Si solo quieres crear un dataset suelto puedes usar
`POST /datasets/` con el **mismo objeto** (pero `import` es el flujo recomendado para ficheros preparados).

---

## 6. Reglas de validación y errores comunes (422 / 409)

- **`key` o `name` ausentes / vacíos** → **422** (ambos son obligatorios, `min_length=1`).
- **`key` duplicada dentro del mismo fichero** (array con dos objetos de la misma `key`) → **422** y **no se
  escribe nada** (validación de todo el conjunto primero, aplicación **todo-o-nada**).
- **Fila sin `value`** → **422** (`value` es obligatorio en `DatasetRow`).
- **Race de creación concurrente** con la misma `(empresa, key)` → **409** (la restricción única lo detecta; nada
  se escribe).
- **No-administrador** (`member`) → **403**.
- **Idempotencia:** reimportar el mismo fichero **converge** (actualiza nombre/descripción/filas, no duplica). Una
  `key` existente se **actualiza** (y marca como obsoletos los documentos que dependan del dataset, igual que
  `PATCH /datasets/{key}`); una `key` nueva se **crea**.
- **Aislamiento multi-empresa:** dos empresas pueden usar la **misma `key`** sin colisionar (es única **por
  empresa**).

### Gotchas

- El **valor que se guarda** es `value`, no `label`. El backend valida la **pertenencia**: un valor que envíe el
  formulario y no esté en las filas del dataset se **rechaza (422)** al guardar/generar el documento.
- En una **cascada**, el `parent` del hijo debe coincidir **exactamente** con el `value` (no el `label`) de su
  padre. Un `parent` que no exista deja al hijo sin aparecer nunca.
- Usa `value` en `snake_case`/sin acentos para evitar problemas; el `label` es libre (acentos, mayúsculas…).

---

## 7. Referencias cruzadas

- **Cómo un campo se conecta a un dataset** (`options_source`, `depends_on`, cascada): `FIELDS_FILE_GUIDE.md` §3
  y la guía principal `GET /templates/guide` §7.
- **Importación masiva y semántica todo-o-nada**: guía principal §10.4.
- **El `.docx` de ejemplo** (`GET /templates/sample`) demuestra un campo select-from-dataset con cascada
  provincia → municipio en vivo.
