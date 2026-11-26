# Guía de construcción y adaptación de plantillas — Portal Documentos

> **Para tu agente de desarrollo / de edición de Word.** Esta guía describe, con precisión y respecto al
> motor real, cómo convertir un documento Word corporativo (`.docx`) en una **plantilla de Portal Documentos** y cómo
> **adaptar plantillas existentes** gestionando los cambios correctamente, **respetando las secciones y las
> cabeceras** del documento. Acompáñala de la plantilla de ejemplo descargable (`plantilla-ejemplo-portal-documentos.docx`,
> botón **"Ejemplo"**), que demuestra en la práctica todo lo que aquí se explica.

---

## 1. Cómo funciona el motor (qué puedes y qué no puedes hacer)

- **Word es el documento maestro. No se usa LaTeX ni HTML.** Editas el `.docx` corporativo tal cual y solo
  insertas marcadores; **todo el formato se conserva al 100%**: estilos, **secciones de Word**, tablas,
  imágenes, **encabezados/pies (por sección)**, numeración automática, índices (TOC), referencias cruzadas y
  campos de Word.
- Motor de relleno: **[docxtpl](https://docxtpl.readthedocs.io)** (sintaxis Jinja2 sobre `.docx`) + `python-docx`.
- Conversión a PDF: **LibreOffice headless** (`soffice`). El PDF es la representación fiel del Word generado.
- **Regla de oro:** parte SIEMPRE del `.docx` real de la empresa. Sustituye los valores fijos por marcadores
  y **no toques** estilos, **saltos de sección**, cabeceras/pies, tablas ni imágenes que deban conservarse.

### ⚠️ El error nº 1: marcadores partidos entre "runs"
Word divide internamente el texto en *runs* (fragmentos con formato). Si escribes `{{ cliente }}` y a mitad
cambias de formato (negrita, corrector ortográfico, autocorrección…), Word puede partir el marcador en varios
runs y **docxtpl no lo reconocerá**. Para evitarlo:
- Escribe cada marcador de una sola vez, sin cambiar de formato a mitad.
- Si dudas, selecciona el marcador y aplica **"Borrar todo el formato"** y vuelve a aplicar el estilo al conjunto.
- Truco fiable: escribe primero `{{cliente}}` en un bloc de notas y pégalo como **texto sin formato**.

---

## 2. Sintaxis de marcadores (lo que insertas en el Word)

### 2.1 Variables simples
```
{{ nombre_variable }}
```
- El nombre debe ser `\w+` (letras, dígitos y `_`), **sin espacios ni acentos**: `{{ cliente }}`, `{{ potencia_kw }}`.
- Se sustituye por el valor que el usuario introduce en el formulario.

### 2.2 Tablas dinámicas (bucle de filas) — `{%tr for %}`
Para repetir una **fila de tabla** por cada elemento de una lista. Cada etiqueta `for`/`endfor` va en su
**propia fila**; la fila intermedia es la que se clona por cada iteración:

| Fila | Celda 1 | Celda 2 | Celda 3 |
|------|---------|---------|---------|
| 1 (apertura) | `{%tr for item in items %}` | | |
| 2 (datos)    | `{{ item.nombre }}` | `{{ item.cantidad }}` | `{{ item.precio }}` |
| 3 (cierre)   | `{%tr endfor %}` | | |

- `items` es la lista; `item.<campo>` accede a cada sub-campo (notación con punto).
- El analizador detecta esto como **tabla dinámica** y surface `items` como variable de tipo `list`.

### 2.3 Condicionales de párrafo — `{%p if %}`
Para mostrar/ocultar **párrafos enteros** según una condición:
```
{%p if incluir_anexo %}
Este párrafo (y su formato) solo aparece si "incluir_anexo" es verdadero.
{%p endif %}
```
También existen los inline Jinja `{% if %}…{% endif %}` y `{% for %}…{% endfor %}` para texto dentro de un párrafo.

### 2.4 Imágenes, cabeceras/pies, índices, numeración
- **Imágenes, encabezados, pies, TOC/índices, numeración automática y campos de Word se conservan tal cual** —
  no requieren sintaxis especial salvo que quieras parametrizar su texto con `{{ … }}`.
- Para texto variable en cabecera/pie usa marcadores normales: `Portal Documentos — {{ empresa }} | Página `.
- Variables cuyo nombre contiene `image`, `img`, `photo` o `logo` se interpretan como **tipo imagen**.

### 2.5 Operaciones aritméticas dentro de la plantilla
Puedes hacer cálculos en línea con Jinja: `{{ importe / unidades }}`, `{{ base * 1.21 }}`,
`{{ potencia_kw - perdidas }}`. Reglas:
- Los valores numéricos del formulario se **convierten automáticamente a número** (aunque lleguen como
  texto), así que la aritmética funciona sin más.
- La aritmética es **tolerante**: dentro de una operación, un operando **vacío o no numérico** cuenta como
  **0**, y una **división por cero** da **0** — así una plantilla con cálculos **no rompe** la generación si
  el formulario está a medias (un cálculo con entradas vacías muestra **0**).
- Usa el **punto** como separador decimal (`1234.56`), no la coma. Para cálculos complejos/encadenados,
  mejor un **campo calculado** (§8) que un cálculo enorme en la plantilla.

### 2.6 Campos vacíos: se conserva el marcador `{{ campo }}` en el render
Cuando un campo **se deja vacío** (o aún no se ha rellenado), el documento generado **conserva el marcador
del campo** —p. ej. `{{ cliente }}`— en lugar de dejar un hueco en blanco. Así el ingeniero puede
**descargar el documento a medio rellenar y seguir trabajándolo**, viendo de un vistazo qué falta (y puede
completarlo en Word o volver al formulario). Detalles:
- Solo afecta a **campos de salida** `{{ campo }}`. La **lógica** sigue siendo tolerante: un campo vacío en
  un condicional `{%p if campo %}` se evalúa como **falso** (la sección se **omite**, no se filtra el marcador),
  y un campo de **lista** vacío en `{%tr for x in lista %}` produce **cero filas**.
- En **operaciones** el campo vacío cuenta como **0** (no se ve el marcador dentro de un cálculo numérico).
- Los valores reales **`0`** y **`falso`** **no** se consideran vacíos: se renderizan como `0` / según el
  condicional, nunca como marcador.
- Las **imágenes** (`{{ image }}`, `{{ logo }}`) usan la **imagen de marcador** del servidor cuando no se
  proporciona una, no el texto `{{ … }}`.

---

## 3. Qué detecta el analizador automático (al subir la plantilla)

Al subir el `.docx`, el analizador (`app/documents/analyze.py`) cuenta y lista:

| Detecta | Cómo |
|---------|------|
| **variables** | `{{ var }}` (y con punto `{{ item.campo }}`) |
| **dynamic_tables** | bucles de fila `{%tr for … %}` |
| **conditional_sections** | bloques `{% if %}` |
| **loops** | todos los `{% for %}` (de fila y de párrafo) |
| **images** | medios incrustados en `word/media/` |
| **headers / footers** | `word/headerN.xml`, `word/footerN.xml` (uno por sección de Word) |
| **indexes** | campos `TOC` / `INDEX` |
| **fields** | campos de Word (`w:fldSimple`, `w:instrText`) |
| **comments** | comentarios `word/comments.xml` |

**Inferencia de tipo por nombre** (puedes cambiarlo luego en el diseñador):
- contiene `image`/`img`/`photo`/`logo` → **imagen**
- contiene `qty`/`num`/`count`/`amount`/`price`/`total` → **número**
- variable extraída de un `{% for … in <nombre> %}` → **lista**

---

## 4. Secciones del Word, cabeceras/pies y «datos generales» vs «datos de sección»

> Esta es la parte clave para que un **agente que edita el Word** ajuste las plantillas **respetando las
> secciones y las cabeceras**, y para que el formulario distinga bien los **datos generales** de los **datos
> específicos de cada sección** (cada uno **colapsable**).

**El motor conserva al 100% las secciones de Word** (saltos `w:sectPr`), sus **cabeceras y pies por sección**,
la configuración de página, la numeración y los índices. No tienes que hacer nada especial para que se respeten:
**no borres los saltos de sección ni las partes de cabecera/pie** y se mantienen intactos en el DOCX y el PDF.

### 4.1 Datos generales vs datos de sección
- **Datos generales del documento**: variables que aplican a todo el documento (cliente, proyecto, fecha, autor…).
- **Datos de sección**: variables que pertenecen a un apartado concreto (en una memoria: «Objeto»,
  «Antecedentes», «Cálculos», «Conclusiones»…).
- En el **formulario** esto se refleja en **grupos colapsables**: un grupo **«Datos generales»** + un grupo
  **colapsable por cada sección**.

### 4.2 Cómo se asigna una variable a una sección (convención que respeta el Word)
El campo de diseñador **`chapter`** define a qué sección del formulario pertenece una variable:
- `chapter` vacío → **«Datos generales»**.
- `chapter = "Cálculos"` → grupo colapsable «Cálculos».

**Convención recomendada (que el motor respeta automáticamente):**
1. Estructura el Word con un **Título de nivel 1 (estilo «Título 1» / `Heading 1`)** al inicio de cada sección
   (p. ej. `1. Objeto`, `2. Antecedentes`, `3. Cálculos`).
2. Coloca las variables de esa sección **debajo de su Título**.
3. Las variables que aparezcan **antes del primer Título 1** se consideran **datos generales**.
4. Al subir la plantilla, el analizador **asigna `chapter` = el Título 1 inmediatamente anterior** a cada
   variable (puedes ajustarlo después en el diseñador con `chapter` y `field_order`).

➡️ **La estructura de secciones del Word manda:** el formulario agrupa y colapsa los campos siguiendo los
Títulos/secciones del documento. Si añades, mueves o quitas una sección en el Word, el formulario lo refleja.

### 4.3 Cabeceras y pies por sección
- Cada **sección de Word** puede tener su **propia cabecera/pie** (distinta primera página, pares/impares…).
  Todo eso se conserva tal cual.
- Parametriza su texto con marcadores normales: en la cabecera, `{{ empresa }} — Proyecto {{ proyecto }}`.
- **No elimines ni fusiones** las partes de cabecera/pie de una sección si quieres conservar su diseño; edita
  solo su texto.

### 4.4 Gestión de cambios (para un agente que modifica el Word)
- **Añadir una sección:** inserta un **salto de sección** donde corresponda, su **Título 1**, su cabecera/pie
  si la necesita, y las variables debajo → aparecerá como un nuevo grupo colapsable «<Título>».
- **Renombrar una sección:** cambia el texto del Título 1 (y, si quieres, el `chapter` de sus variables).
- **Mover variables entre secciones:** muévelas físicamente bajo otro Título (o cambia su `chapter`).
- **Eliminar una sección:** borra su contenido y su Título y **mantén la coherencia de los saltos de sección**
  (no dejes un `sectPr` huérfano que altere las cabeceras/pies de las secciones vecinas).
- **Nunca** partas un `{{ marcador }}` entre runs (§1) — es la causa nº1 de que una variable «desaparezca».
- Tras cualquier cambio: **sube la plantilla**, revisa el conteo del analizador y la **agrupación por secciones**,
  y **genera una prueba** comparando con el original.

---

## 5. Diseñador de variables (configuración tras subir)

Cada variable detectada se puede afinar (API `PATCH /templates/{id}/variables/{vid}` o UI):

| Propiedad | Para qué |
|-----------|----------|
| `name` / `technical_name` / `display_name` | nombre técnico (el del marcador) y etiqueta visible |
| `var_type` | `text` · `number` · `date` · `table` · `image` · `coordinate` |
| `required` | obligatorio en el formulario |
| `default_value` | valor por defecto |
| `description` / `help_text` | ayuda al usuario |
| `visible` / `editable` | mostrar / permitir editar |
| `chapter` | **sección del formulario** (datos generales vs sección — ver §4) |
| `field_order` | orden dentro de la sección |
| `visible_when` | **lógica condicional** (mostrar/ocultar) — ver §6 |
| `depends_on` + `options_source` | **dependencias en cascada** con datasets — ver §7 |
| `calculated` + `formula` | **campo calculado** — ver §8 |

---

## 6. Lógica condicional (`visible_when`)

Predicado que decide si un campo se muestra. Mismo evaluador en backend y frontend
(`app/documents/formula.py` ↔ `frontend/src/lib/predicate.ts`).

**Operadores soportados:** `==` `!=` `<` `<=` `>` `>=` `in` `not in` `and` `or` `not`.
Los valores se coercionan a número cuando procede (p. ej. `"28001"` → `28001`).

```text
potencia_kw > 100
tipo_instalacion == 'autoconsumo'
tension in ['BT', 'MT']
incluir_anexo == true and provincia != ''
```
- Un campo **oculto por su predicado no se exige** aunque sea `required`.
- Si el predicado **no se puede evaluar**, el campo se **oculta** (mismo criterio que el backend).

---

## 7. Datasets (catálogos compartidos + cascadas)

Un **dataset** es una tabla de valores reutilizable, **compartible entre varias plantillas** y editable en un
único sitio (al editarlo, **se refleja en todas las plantillas** y marca los documentos afectados como
*"desactualizados"* para regenerar bajo demanda).

- Forma de cada fila: `{ "value": "...", "label": "...", "parent": "<value padre o null>" }`.
- Una variable se conecta a un dataset con `options_source = "<key del dataset>"` → se renderiza como **desplegable**.
- **Cascada** (provincia → municipio): el hijo declara `depends_on = "provincia"` y sus filas llevan
  `parent = "<value de la provincia>"`; al elegir la provincia se filtran los municipios.
- El backend **valida la pertenencia**: un valor que no esté en las opciones del dataset se rechaza (422).

---

## 8. Campos calculados (`calculated = true` + `formula`)

Se evalúan en el servidor (los valores enviados por el cliente para campos calculados se ignoran y se recomputan).
El motor es un evaluador **restringido y seguro** (`app/documents/formula.py`): NO ejecuta código arbitrario.

**Permitido:**
- Operadores aritméticos: `+ - * / // % **`
- Comparación / pertenencia: `== != < <= > >= in not in`
- Booleanos: `and or not`
- Literales numéricos y de texto, y **nombres = otras variables** del formulario.
- Funciones (allow-list exacta): `abs` · `round` · `min` · `max` · `len` · `int` · `float` · `str`

**Prohibido (lanza error y el campo se omite):** imports, acceso a atributos (`x.y`), llamadas a funciones fuera
de la allow-list, lambdas, comprehensions, etc.

```text
# Ejemplos de formula
round(potencia_kw * 1.21, 2)
max(seccion_min, 6)
caida_tension_pct = (longitud_m * intensidad_a) / (56 * seccion_mm2 * tension_v) * 100
```
Los campos calculados se muestran en el formulario como **solo lectura** (se recalculan en vivo).
Aparecen **dentro de su propia sección** —la del capítulo (Heading 1) donde está el marcador—, junto a los
campos de los que dependen y ordenados por su posición, con un **badge de su tipo** (Cálculo/API/IA/…) según
`value_origin` y un botón **«Calcular»** al lado (los orígenes lentos muestran «Se calcula al generar»).
Una fórmula inline es el **origen de valor más simple**. Para orígenes avanzados (IA, endpoint, pipeline) y
**cálculos reutilizables y versionables**, ver §9.

---

## 9. Motor de Cálculos (orígenes de valor y cálculos reutilizables)

Cada variable tiene un **origen de valor** (`value_origin`) que decide de dónde sale su contenido. En el Word
**no cambia nada**: sigues insertando `{{ nombre }}`. El **origen se configura en el diseñador** (o en la pestaña
**Cálculos**), **no en el documento**. Orígenes disponibles:

| Origen | Qué hace | ¿Lo rellena el usuario? |
|---|---|---|
| **Manual** | el usuario teclea el valor | sí |
| **Dataset (selección)** | el usuario elige de un catálogo, con cascada (§7) | sí |
| **Fórmula** | se calcula con una expresión segura (§8) | no (solo lectura) |
| **Prompt IA** | lo genera la IA a partir de otros campos | no |
| **Endpoint/API** | se obtiene llamando a un servicio externo registrado | no |
| **Pipeline** | encadena varios pasos (dataset → fórmula → IA → endpoint) | no |
| **Código** (Py/JS) | *próximamente* — todavía no disponible | — |

Los campos con origen **calculado** (Fórmula/IA/Endpoint/Pipeline) **no se piden al usuario**: aparecen en el
formulario como **solo lectura** dentro de su sección, y su valor se resuelve al previsualizar/generar.

### 9.1 Cálculos propios de la plantilla (pestaña «Cálculos»)

Un **Cálculo** es una pieza con nombre (`key`), **versionable**, que pertenece a **UNA** plantilla — vive en la
pestaña **Cálculos** del detalle de esa plantilla, junto con **Prompts** y **Campos**: todo lo que necesita la
plantilla se gestiona **dentro** de ella. Un cálculo **es reutilizable dentro de su plantilla**: cualquier campo
de la misma plantilla se **enlaza** a él indicando su `calculation_key` y un **mapa de entradas** (`input_map`)
que asocia las entradas declaradas del cálculo a los campos de ESTA plantilla (o a un literal anteponiendo `=`,
p. ej. `=1000`). No es una librería compartida entre plantillas — si otra plantilla necesita el mismo cálculo, se
crea (o importa) de nuevo dentro de ella, aunque comparta la misma `key`.

> Ejemplo: el cálculo `potencia_instalada_kwp`, definido en la plantilla «Contrato FV», declara las entradas
> `numero_modulos` y `potencia_modulo_wp`. El campo «Potencia instalada» de **esa misma plantilla** lo enlaza con
> `input_map = { numero_modulos: n_modulos, potencia_modulo_wp: w_modulo }`. Otra plantilla que necesite el mismo
> cálculo lo define en su propia pestaña **Cálculos** (puede reutilizar la `key` `potencia_instalada_kwp` sin
> colisionar: son cálculos independientes, uno por plantilla).
>
> **Lo único global/compartido entre plantillas son los datos:** los **datasets** (§7) y los **conectores**
> (§9.6), gestionados en el hub **«Datos y conexiones»** del menú principal — no en la plantilla.

### 9.2 Tipos de cálculo (cuándo usar cada uno)

- **Fórmula** — aritmética/condicional segura sobre otros campos (§8). **Rápido**. Para la mayoría de los cálculos.
- **Dataset-lookup** — busca un valor en un catálogo por una columna (p. ej. irradiación por municipio). **Rápido**.
- **Prompt IA** — redacta o extrae un valor con IA a partir de campos de entrada. **Lento**.
- **Endpoint/API** — consulta un servicio externo (producción FV, catastro, GIS…) a través de un **Conector**
  registrado por un administrador. **Lento**.
- **Pipeline** — pasos **en orden** (p. ej. dataset-lookup → fórmula → IA), cada paso lee y escribe valores que
  consumen los pasos siguientes. Sin bifurcaciones ni bucles.

### 9.3 Unidades y formato del resultado

Cada cálculo define `output_type` (`text` · `integer` · `decimal` · `number` · `date` · `boolean`) y `output_unit`.
El formato es **es-ES**: los decimales usan **coma** y se añade la unidad, p. ej. `120,50 kWp`. Dentro de la
plantilla escribe los números con **punto** decimal (`1.5`); para resultados de texto deja que el cálculo los formatee.

### 9.4 Cuándo se calcula (rendimiento y coste)

- **Rápidos** (Fórmula, Dataset-lookup): se recalculan **en vivo** mientras se rellena el formulario.
- **Lentos** (IA, Endpoint, Pipeline): se calculan **al generar** el documento o al pulsar **«Recalcular»** — NO en
  cada tecla, para no disparar llamadas externas ni coste de IA. Hasta entonces se muestran como pendientes.

### 9.5 Trazabilidad y gestión de cambios

- Cada ejecución deja un registro **EXEC** (origen, entradas, resultado, estado, duración) visible en **Ejecuciones**.
- Al **publicar** una nueva versión de un cálculo, los documentos que lo usan se marcan **«desactualizado»**: vuelve
  a generar o pulsa **Recalcular** para refrescarlos. Editar el cálculo una vez se refleja en todos.
- Un cálculo que falla **no rompe** la generación: el campo queda sin resolver (o `0` en aritmética) y se registra el error.

### 9.6 Seguridad (lo que el agente debe saber)

- **Endpoint/API** solo llama a **Conectores** registrados (URL base + credenciales **cifradas**, dados de alta por un
  administrador). Es solo **https**, con guardas anti-SSRF; los **secretos nunca** aparecen en el documento ni en las trazas.
- **Código (Python/JS)** **aún no está disponible**; el origen «Código» aparece deshabilitado.
- Para lógica compleja, crea un **Cálculo reutilizable** en vez de meter expresiones enrevesadas en una fórmula inline.

> **Resumen para el agente de Word:** tu trabajo con los campos calculados es **el mismo** que con cualquier otro —
> inserta `{{ nombre }}` en el sitio correcto y **dentro de su sección** (§4). **El origen del valor (fórmula, IA,
> endpoint, pipeline) se configura en Portal Documentos**, no en el `.docx`.

---

## 10. Gestión de campos como JSON (códigos `FLD-`, ver/editar, exportar/importar)

Cada campo tiene un **código estable e inmutable por empresa**, con el formato `FLD-NNNN` (p. ej. `FLD-0023`). Se
asigna automáticamente al crear el campo y **nunca cambia** (ni al renombrar la variable, ni al editar el JSON, ni al
importar). Es el `field_id` del contrato JSON del campo.

### 10.1 Ver / editar la configuración de UN campo (round-trip JSON)

- `GET /templates/{id}/variables/{vid}/config` → devuelve el **FieldConfig** (JSON) del campo: `field_id` (= el código
  `FLD-`), `name`, `technical_name`, `label`, `type`, `unit`, `required`, `description`, `help_text`, `chapter`,
  `field_order`, `visible`, `editable`, `visible_when`, `value_origin`, `calculation_binding`
  (`{calculation_key, input_map}`), `options_source`, `depends_on`, `options`, `default_value`, `formula`,
  `calculated`.
- `PUT /templates/{id}/variables/{vid}/config` → actualiza el campo **desde** ese mismo JSON. Es un **merge parcial**:
  solo se aplican las claves que **realmente envías**; una clave **omitida** deja el valor **sin tocar** (no se
  reinicia al valor por defecto), y un `null` explícito la **borra**. El `field_id` (código) y el `tenant_id` se
  **ignoran** aunque vengan en el cuerpo (son inmutables/propiedad del servidor). Se valida el tipo y la coherencia del
  `value_origin` (un origen de cálculo —`ai`/`endpoint`/`pipeline`— exige un `calculation_binding.calculation_key` que
  exista en la empresa); si algo es incoherente, **422**.

> La **`unit`** es **derivada** (solo lectura): proviene de la `output_unit` del **Cálculo** enlazado cuando el campo
> es calc-backed; en cualquier otro caso es `null`. No existe columna de unidad en el campo: al importar/guardar se
> ignora.

> La **validación a nivel de campo NO se almacena** en el campo (`TemplateVariable` no tiene columna de validación):
> el contrato JSON del campo **no** incluye una clave `validation`. La validación de resultados (mín./máx.) vive en los
> **Cálculos** (su validación de salida, §9), no en el campo.

### 10.2 Exportar / importar TODOS los campos de una plantilla

- `GET /templates/{id}/fields/export` → un **array JSON** con la configuración de todos los campos (ordenado por
  `field_order`, `name`).
- `PUT /templates/{id}/fields/import` (solo **administrador de empresa**) → da de alta/actualiza los campos desde un
  array JSON. Cada campo entrante se **empareja por `code`** (`field_id`) si viene, y si no por `name`; **nunca se
  reasigna** el código de un campo existente; los campos nuevos (sin coincidencia) se **crean** con un código `FLD-`
  nuevo. Se valida **todo el conjunto primero** y se aplica **todo-o-nada**: si algún campo es inválido, **422** y no
  se escribe nada (re-importar el export es idempotente).

### 10.3 Ejemplos descargables

- `GET /templates/fields/sample` → ejemplo de configuración de campos (un campo manual + uno enlazado a un cálculo con
  `calculation_binding`), en la forma del export → pégalo en `PUT …/fields/import`.
- `GET /datasets/sample` → ejemplo de **dataset** (`{value,label,parent}`) con cascada provincia → municipio → pégalo
  en `POST /datasets/`.
- `GET /calculations/sample` → ejemplo de **cálculo** (una fórmula + un endpoint) en la forma `CalculationCreate` →
  pégalo en `POST /templates/{template_id}/calculations/` (el cálculo se crea **dentro** de esa plantilla).
- `GET /ai/prompts/sample` → ejemplo de **prompts** (incluye un `kind=calculation`) → pégalo en
  `POST /templates/{template_id}/prompts` (el prompt se crea **dentro** de esa plantilla).

> Todos los ejemplos son **estáticos y de solo lectura** (sin datos de empresa). Cada uno es JSON válido que la ruta
> de creación/validación correspondiente acepta.

### 10.4 Importar un fichero preparado SIN la interfaz (vía API / `curl`)

Cada sección tiene un endpoint de **importación masiva** que acepta exactamente la forma de su `/sample`. El flujo es
siempre el mismo: **descarga el ejemplo → edítalo → impórtalo**. Así un agente externo puede preparar el fichero y
subirlo directamente, sin pasar por la UI. Todos requieren **administrador de empresa** (`company_admin`), validan
**todo el conjunto primero** y se aplican **todo-o-nada** (si algún elemento es inválido o hay `key` duplicada en el
mismo fichero → **422** y no se escribe nada), y son **idempotentes** (re-importar el mismo fichero converge:
actualiza, no duplica). Cada respuesta es un resumen `{created, updated, items}`.

**Solo los datasets (y conectores) son globales** — se importan una vez, por empresa (`(tenant, key)`), y quedan
disponibles para todas las plantillas. **Cálculos, prompts y campos son propios de la plantilla** — se importan
**dentro** de una plantilla concreta (`(tenant, template_id, key)`); si otra plantilla los necesita, se importan
también en ella (aunque reutilicen la misma `key`).

`AUTH="Authorization: Bearer $TOKEN"` (obtén el token con `POST /api/v1/login/access-token`).

- **Datasets** (global) — `POST /datasets/import`. El cuerpo es **un objeto o un array** en la forma
  `/datasets/sample` (`TemplateDatasetCreate`). Si la `key` ya existe se **actualiza** (nombre/descripcion/filas, y
  se **marcan como obsoletos** los documentos generados que dependan de ese dataset, igual que
  `PATCH /datasets/{key}`); si es nueva, se **crea**.

  ```bash
  curl -s -H "$AUTH" http://localhost/api/v1/datasets/sample > dataset.json
  # edita dataset.json (filas {value,label,parent}, cascada, etc.)
  curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
       http://localhost/api/v1/datasets/import -d @dataset.json
  ```

- **Cálculos** (propios de la plantilla) — `POST /templates/{template_id}/calculations/import`. El cuerpo es un
  **array** en la forma `/calculations/sample` (`CalculationCreate`, estático — no requiere `template_id`). Cada
  `spec` se valida por `calc_type` (**422** si está mal formada). Se hace *upsert* por `key` **dentro de esa
  plantilla**, sobre el **borrador (draft)**: si la `key` existe (en esa plantilla) se actualiza el borrador; **nunca**
  se modifica una versión publicada ni se publica automáticamente. Una `key` nueva (para esa plantilla) se crea como
  borrador. `calc_type=code` se acepta como borrador (su publicación/generación sigue bloqueada).

  ```bash
  # consigue TEMPLATE_ID (sube una plantilla, o lista las existentes con GET /templates/)
  TEMPLATE_ID=$(curl -s -X POST -H "$AUTH" -F "file=@mi_plantilla.docx" -F "name=Mi plantilla" \
       http://localhost/api/v1/templates/ | jq -r .id)
  curl -s -H "$AUTH" http://localhost/api/v1/calculations/sample > calculos.json
  # edita calculos.json (array de cálculos)
  curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
       "http://localhost/api/v1/templates/$TEMPLATE_ID/calculations/import" -d @calculos.json
  ```

- **Prompts IA** (propios de la plantilla) — `POST /templates/{template_id}/prompts/import`. El cuerpo es un
  **array** en la forma `/ai/prompts/sample` (`AIPromptCreate`, estático — no requiere `template_id`). *Upsert* por
  `key` **dentro de esa plantilla**: actualiza `instruction`/`name`/`description`/`kind` o crea.

  ```bash
  curl -s -H "$AUTH" http://localhost/api/v1/ai/prompts/sample > prompts.json
  # edita prompts.json (array de prompts)
  curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
       "http://localhost/api/v1/templates/$TEMPLATE_ID/prompts/import" -d @prompts.json
  ```

- **Campos** (propios de la plantilla) — usa la importación ya descrita en **§10.2**
  (`PUT /templates/{id}/fields/import`) tras `GET /templates/{id}/fields/export` (o `GET /templates/fields/sample`).

---

## 11. Seguridad y límites

- Solo se aceptan ficheros **`.docx`** (se valida la extensión y los *magic bytes* `PK\x03\x04`).
- Claves de respuesta terminadas en `*_path` se **eliminan** antes de renderizar (no se pueden inyectar rutas de
  fichero arbitrarias, p. ej. para imágenes). Usa el tipo `image` y el flujo de subida, no rutas.
- Todo es **multi-tenant con RLS**: una plantilla/documento nunca cruza entre empresas.

---

## 12. Checklist para ADAPTAR una plantilla existente (para el agente)

1. **Parte del `.docx` corporativo real.** No recrees el formato; edítalo.
2. Asegura la **estructura de secciones**: cada apartado con su **Título 1**; cabeceras/pies por sección donde
   correspondan (no borres saltos de sección) (§4).
3. Localiza cada dato variable y sustitúyelo por `{{ nombre }}` (nombres `\w+`, sin espacios/acentos), colocando
   cada variable **bajo el Título de su sección** (datos generales antes del primer Título). Escribe cada
   marcador de una vez para no partirlo entre runs (§1).
4. Convierte las tablas que crecen en **bucles de fila** `{%tr for item in items %}` (§2.2).
5. Marca con `{%p if … %}` los párrafos/secciones opcionales (§2.3).
6. Deja intactos cabeceras, pies, TOC, numeración e imágenes; parametriza solo su texto si hace falta.
7. **Sube la plantilla** → revisa el conteo del analizador **y la agrupación por secciones** (¿cada variable cae
   en su sección? ¿los datos generales quedan fuera de las secciones?).
8. En el **diseñador**, ajusta por variable: `chapter` (sección), tipo, obligatorio, orden, ayuda, `visible_when`,
   `depends_on`/`options_source` (datasets), `calculated`/`formula`, y el **origen de valor** + el enlace a un
   **Cálculo** reutilizable con su `input_map` (§5–§9).
9. **Genera una prueba** y compara el DOCX/PDF con el original: el formato y **las secciones/cabeceras** deben
   ser idénticos.
10. Itera sobre los marcadores que no se hayan sustituido (suelen ser marcadores partidos entre runs, §1).

---

## 13. Referencia rápida de sintaxis

```text
{{ variable }}                         variable simple
{{ item.campo }}                       sub-campo dentro de un bucle
{%tr for item in items %} … {%tr endfor %}   bucle de fila de tabla (cada tag en su fila)
{%p if condicion %} … {%p endif %}     párrafo condicional
{% if c %} … {% endif %}               condicional inline
{% for x in lista %} … {% endfor %}    bucle inline
```

**Secciones (respetar el Word):** un **Título 1** por sección → grupo colapsable del formulario; variables antes
del primer Título → **Datos generales**; cabeceras/pies y saltos de sección **se conservan**, no los borres (§4).

> La **plantilla de ejemplo** (`plantilla-ejemplo-portal-documentos.docx`) contiene en vivo: título con estilo, párrafo con
> `{{ }}`, una tabla `{%tr for %}`, una imagen incrustada, cabecera con número de página automático, pie con
> texto fijo + variables, y una lista numerada. Úsala como patrón de referencia.

---

## 14. Catálogo de TIPOS DE CAMPO

> Cada tipo: **cuándo usarlo**, el **marcador en el Word**, **cómo se fija el tipo/origen**, **validación**, y un
> ejemplo de 1 línea. El tipo se infiere al subir el `.docx` (por el nombre, §3) y se afina en el diseñador
> (`var_type`) o por JSON (`type` en `FieldConfig`, ver `FIELDS_FILE_GUIDE.md`). El **origen del valor**
> (`value_origin`) se configura en Portal Documentos, **no** en el `.docx`.
>
> El `.docx` de ejemplo (`GET /templates/sample`) demuestra cada tipo en vivo; se indica la sección donde aparece.

| Tipo (`type`/`var_type`) | Cuándo usarlo | Marcador en el Word | Cómo se fija | Validación | Ejemplo (1 línea) · sección del ejemplo |
|---|---|---|---|---|---|
| **text** | Texto libre (nombre, descripción). Por defecto. | `{{ cliente }}` | Default; o `type:text`. | — | `{{ cliente }}` · *Datos generales* |
| **textarea** | Texto largo multilínea. | `{{ objeto_desc }}` | `type:textarea` en el diseñador/JSON. | — | `{{ objeto_desc }}` · *1. Objeto* |
| **number** | Valor numérico (usado en aritmética). | `{{ potencia_total_kw }}` | Inferido si el nombre contiene `qty`/`num`/`count`/`amount`/`price`/`total` (p. ej. `potencia_total_kw` se infiere por `total`); o ajusta `type:number` en el diseñador. | Numérico; en plantilla, **coma→error**: usa **punto** decimal. | `{{ potencia_total_kw }}` · *2. Datos técnicos* |
| **date** | Fecha. | `{{ fecha_firma }}` | Inferido si el nombre contiene `date`/`fecha`; o `type:date`. | Formato fecha. | `{{ fecha_firma }}` · *Datos generales* |
| **boolean** | Sí/No, controla un condicional. | `{% if incluir_anexo %}…{% endif %}` | `type:boolean`. | Verdadero/falso. | `{% if incluir_anexo %}…{% endif %}` · *1. Objeto* |
| **select** (dataset) | Elegir de un **catálogo** (dataset). | `{{ provincia }}` | `options_source = "<key dataset>"` (+ `depends_on` para cascada). | **Pertenencia** al dataset (valor fuera → 422). | `{{ provincia }}` · *2. Datos técnicos* |
| **select** (estático) | Opciones fijas de una plantilla. | `{{ tipo_instalacion }}` | `options = [{value,label}, …]`. | Pertenencia a `options`. | `{{ tipo_instalacion }}` |
| **image** | Imagen/logo incrustado. | `{{ logo }}` / `{{ image }}` (+ `{{ logo_caption }}`) | Inferido si el nombre contiene `image/img/photo/logo`. | Subida de imagen (no rutas: §11). | `{{ logo }}` + `{{ image }}` · *Datos generales* |
| **coordinate** | Coordenada (UTM, lat/long). | `{{ coordenadas_utm }}` | `type:coordinate` (var_type). | Texto de coordenada. | `{{ coordenadas_utm }}` · *2. Datos técnicos* |
| **list / table** (grupo repetible) | Filas que se repiten (tabla). | `{%tr for modulo in modulos %}` … `{{ modulo.nombre }}` … `{%tr endfor %}` | Surge de un `{% for %}`/`{%tr for %}`; `var_type=list`. | Lista de objetos. | tabla `{%tr for modulo in modulos %}` · *4. Tabla de elementos* |
| **calculado / solo lectura** | Valor derivado (fórmula/IA/endpoint/pipeline). | `{{ potencia_instalada_kwp }}` (igual que cualquier marcador) | `value_origin = formula/ai/endpoint/pipeline` + (si calc-backed) `calculation_binding`; o `calculated=true`+`formula`. | El usuario no lo rellena (solo lectura); se recomputa. | `{{ potencia_instalada_kwp }}` · *2. Datos técnicos* |
| **currency / email / url** | Variantes de presentación de número/texto. | `{{ coste_anual_estimado }}` | `type:currency`/`email`/`url` en JSON. | Según el tipo. | `{{ coste_anual_estimado }}` |

> **Tipos aceptados por la validación de import de campos:** `text, textarea, number, date, boolean, select, list,
> image, currency, email, url` (un `type` fuera de este conjunto → **422**). El analizador del `.docx` emite además
> `coordinate` y `table` como `var_type`. **Orígenes de valor** (`value_origin`): `manual, dataset, formula, ai,
> endpoint, pipeline, code` (`code` aún deshabilitado). Detalle por campo en `FIELDS_FILE_GUIDE.md`.

---

## 15. Catálogo de OPERACIONES

> Hay **dos contextos** de cálculo, con la **misma** semántica de negocio pero sintaxis distinta:
>
> 1. **En el `.docx` (Jinja, inline)** — aritmética directa y **filtros** Jinja para las funciones. La aritmética
>    es **tolerante** (`app/documents/render.py`): en `/ // % - ** + *` un operando vacío/no numérico cuenta como
>    **0** y una división por cero da **0**. El `+` y el `*` conservan además la **concatenación/repetición de
>    cadenas** cuando algún operando es texto real (y un campo vacío en una concatenación deja su marcador
>    `{{ campo }}`). Así una plantilla **no rompe** con un formulario a medias.
> 2. **En un campo calculado / Cálculo (fórmula)** — evaluador AST **restringido y seguro**
>    (`app/documents/formula.py`): operadores + comparaciones + booleanos + ternario + una **allow-list de
>    funciones** en forma de **llamada** (`round(x, 2)`), NO filtros. Prohíbe imports, atributos, lambdas,
>    comprehensions, llamadas fuera de la allow-list.
>
> El `.docx` de ejemplo demuestra todas estas operaciones en la sección **«3. Cálculos»** (y el condicional en
> «1. Objeto», el bucle en «4. Tabla de elementos»).

### 15.1 Aritmética (en el `.docx`, tolerante)

| Operación | Operador | Ejemplo en el Word | Resultado / nota |
|---|---|---|---|
| Suma | `+` | `{{ (potencia_total_kw \| default(0)) + (perdidas_kw \| default(0)) }}` | Numérica (vacío→0). |
| Resta | `-` | `{{ potencia_total_kw - perdidas_kw }}` | Tolerante (vacío→0). |
| Multiplicación | `*` | `{{ (base \| default(0)) * 1.21 }}` | base × 1,21 (=+IVA). |
| División | `/` | `{{ potencia_total_kw / superficie_m2 }}` | **÷0 → 0** (no rompe). |
| División entera | `//` | `{{ num_organizacion // 10 }}` | ÷0 → 0. |
| Módulo (resto) | `%` | `{{ num_organizacion % 7 }}` | ÷0 → 0. |
| Potencia | `**` | `{{ superficie_m2 ** 2 }}` | x². |

### 15.2 Comparaciones, booleanos y ternario

| Construcción | Ejemplo |
|---|---|
| Comparación | `== != < <= > >=` — `potencia_total_kw > 100` |
| Pertenencia | `in` / `not in` — `tension in ['BT', 'MT']` |
| Booleanos | `and` / `or` / `not` — `incluir_anexo and provincia != ''` |
| Condicional inline | `{% if incluir_anexo %}Con anexo{% else %}Sin anexo{% endif %}` |
| **Ternario** (inline) | `{{ "Si" if (potencia_total_kw \| default(0)) > 100 else "No" }}` |

### 15.3 Funciones de la allow-list

La allow-list **exacta** es: `abs · round · min · max · len · int · float · str`.

| Función | En un **Cálculo/fórmula** (llamada) | En el **`.docx`** (filtro Jinja equivalente) |
|---|---|---|
| `abs` | `abs(perdidas - potencia)` | `{{ ((perdidas_kw \| default(0)) - (potencia_total_kw \| default(0))) \| abs }}` |
| `round` | `round(potencia_kw * 1.21, 2)` | `{{ (potencia_total_kw \| default(0)) \| round(2) }}` |
| `max` | `max(seccion_min, 6)` | `{{ [seccion_min \| default(0), 6] \| max }}` |
| `min` | `min(seccion_min, 16)` | `{{ [seccion_min \| default(0), 16] \| min }}` |
| `len` | `len(modulos)` | `{{ modulos \| default([]) \| length }}` |
| `int` / `float` / `str` | `int(x)` · `float(y)` · `str(z)` | `{{ x \| int }}` · `{{ y \| float }}` · `{{ z \| string }}` |

> **Prohibido en fórmulas** (lanza error y el campo se omite): imports, acceso a atributos (`x.y`), llamadas a
> funciones fuera de la allow-list, lambdas, comprehensions, argumentos por palabra clave.

### 15.4 Párrafos / bucles condicionales

| Construcción | Marcador | Sección del ejemplo |
|---|---|---|
| Párrafo condicional | `{%p if incluir_anexo %} … {%p endif %}` | (patrón) |
| Condicional inline | `{% if … %} … {% else %} … {% endif %}` | *1. Objeto* |
| **Bucle de fila de tabla** | `{%tr for modulo in modulos %}` / `{{ modulo.nombre }}` / `{%tr endfor %}` | *4. Tabla de elementos* |
| Bucle inline | `{% for modulo in modulos %}{{ modulo.nombre }}{% if not loop.last %}, {% endif %}{% endfor %}` | *4. Tabla de elementos* |

---

## 16. Cómo REFERENCIAR datasets / tablas / cálculos desde el Word

> El `.docx` solo lleva **marcadores**. La conexión a datasets/cálculos se configura en Portal Documentos (diseñador o
> ficheros JSON). El agente de Word solo decide **dónde** va cada `{{ marcador }}` y **bajo qué sección** (§4).

### 16.1 Dataset (desplegable + cascada)

- En el Word, inserta el marcador normal: `{{ provincia }}`, `{{ municipio }}`.
- En Portal Documentos (campo): `provincia.options_source = "provincias_municipios"`; el hijo
  `municipio.options_source = "provincias_municipios"` **+** `municipio.depends_on = "provincia"`. Las filas hijas
  del dataset llevan `parent = "<value de la provincia>"`.
- El backend valida la **pertenencia** del valor elegido. Detalle: `DATASETS_FILE_GUIDE.md`.
- *Ejemplo en el `.docx`*: sección **«2. Datos técnicos»** (`{{ provincia }}` select, `{{ municipio }}` en
  cascada).

### 16.2 Tabla / grupo repetible

- En el Word, una **fila de tabla** entre `{%tr for modulo in modulos %}` y `{%tr endfor %}`, con `{{ modulo.* }}`
  en la fila de datos (cada tag en su **propia fila**, §2.2).
- `modulos` se surfacea como variable **lista**; sus sub-campos (`nombre`, `potencia_wp`, `cantidad`) son los
  campos del **item** del grupo repetible.
- *Ejemplo en el `.docx`*: sección **«4. Tabla de elementos»** (`{%tr for modulo in modulos %}`).

### 16.3 Cálculo reutilizable

- En el Word, inserta el marcador del resultado: `{{ potencia_instalada_kwp }}` (igual que cualquier otro; el
  campo se mostrará **solo lectura**).
- En Portal Documentos (campo): `value_origin` calculado (`formula`/`ai`/`endpoint`/`pipeline`) + (si calc-backed)
  `calculation_binding = {calculation_key, input_map}`. El `input_map` asocia las **entradas declaradas** del
  cálculo a campos de ESTA plantilla (o literales con `=`). Detalle: `CALCULATIONS_FILE_GUIDE.md` y
  `FIELDS_FILE_GUIDE.md`.
- *Ejemplo en el `.docx`*: sección **«2. Datos técnicos»** (`{{ potencia_instalada_kwp }}`, con su nota «Demuestra:
  …»).

---

## 17. Guías de fichero relacionadas (para autorizar los importables)

Cada tipo de fichero importable tiene su guía dedicada, **descargable** como markdown (auth):

| Fichero | Qué autoriza | Guía (markdown) |
|---|---|---|
| **Datasets** | catálogos `{value,label,parent}` + cascadas | `GET /datasets/guide` → `DATASETS_FILE_GUIDE.md` |
| **Cálculos** | `CalculationCreate`, los 5 tipos + sus `spec` | `GET /calculations/guide` → `CALCULATIONS_FILE_GUIDE.md` |
| **Prompts IA** | `AIPromptCreate`, kinds + override | `GET /ai/prompts/guide` → `AI_PROMPTS_FILE_GUIDE.md` |
| **Campos** | `FieldConfig`, `FLD-` inmutable, binding | `GET /templates/fields/guide` → `FIELDS_FILE_GUIDE.md` |

Cada guía embebe un **ejemplo importable verbatim** (es el `…/sample` correspondiente, probado en B15) y explica
schema completo, importación (curl + UI), validación y errores 422.

---

## 18. Secciones reutilizables y composición de documentos (Epic S)

> **Nota de desambiguación:** el §4 de esta guía describe las **secciones del Word** — saltos `w:sectPr` dentro de
> un único `.docx` que agrupan campos del formulario en pestañas colapsables. Esta sección (§18) describe algo
> diferente: las **Secciones reutilizables de Portal Documentos** (entidad `Template` con `kind='section'`), que son bloques
> de contenido independientes que se **concatenan** para formar documentos compuestos. Son conceptos distintos.

---

### 18.1 Qué es una Sección

Una **Sección** es una `Template` con `kind='section'`. **Reutiliza toda la maquinaria de las plantillas:** el
archivo `.docx` en `storage_key`, variables (`TemplateVariable` con código `FLD-…`), tablas dinámicas,
condicionales, datasets enlazados, cálculos/`value_origin`, versiones, el motor de render, el form-schema, la
pestaña **Campos**, los campos calculados, el guard SSRF y el aislamiento por empresa (RLS).

**Lo que la diferencia de una plantilla ordinaria** es solo el discriminador `kind='section'` y que está
pensada para ser **compuesta** dentro de plantillas o documentos de proyecto — no se usa directamente como
plantilla independiente para rellenar formularios.

**Campos adicionales de Template relevantes para la composición:**

| Campo | Valores | Significado |
|---|---|---|
| `kind` | `'template'` (por defecto) · `'section'` | Discrimina plantilla normal de sección reutilizable |
| `compose_mode` | `'single'` (por defecto) · `'sections'` | `'sections'` → la plantilla/sección se renderiza componiendo su lista de secciones; `'single'` → su propio `.docx` |

---

### 18.2 Crear y editar una Sección

**Desde la interfaz:**

1. Ve a la sección **«Secciones»** del menú lateral → lista todas las plantillas con `kind=section`.
2. Botones de creación:
   - **Nueva sección (en blanco):** crea una sección vacía → sube el `.docx` desde el detalle.
   - **Subir .docx:** crea la sección con el `.docx` indicado.
   - **Desde plantilla:** duplica una plantilla existente como sección.
3. El **detalle de una sección** es idéntico al de una plantilla: pestañas Variables, Campos, Datasets,
   Analysis, Versions, formulario de generación/preview. Usa el mismo diseñador de variables, el mismo
   flujo de subida y el mismo motor de render. Edita la sección exactamente como editarías una plantilla.
4. **Exportar a Word:** botón «Exportar Word» en el detalle (o `GET /templates/{id}/download`) → devuelve
   el `.docx` desde `storage_key` (con auth y validación de tenant). Útil para seguir editando la sección
   en Word y volver a subirla.

**Via API:** el parámetro `kind=section` en `POST /templates/` (al crear) y `GET /templates/?kind=section`
(al listar). La edición (variables, campos, datasets, análisis, versiones) usa los mismos endpoints que
cualquier plantilla.

---

### 18.3 Componer una PLANTILLA a partir de secciones («Secciones» en el detalle de plantilla)

Una **plantilla compuesta** define una lista ordenada de secciones que se concatenan al renderizar. El campo
`compose_mode` de la plantilla pasa a `'sections'` cuando tiene composición configurada.

**Desde la interfaz:**

1. Abre el detalle de una plantilla → pestaña **«Secciones»**.
2. El panel muestra la lista actual de secciones (vacía si es nueva).
3. **Añadir una sección:** desplegable de selección en el panel → elige de la biblioteca de secciones del tenant.
4. **Reordenar:** arrastra las filas con el mango (icono grip) — drag-and-drop accesible (`@dnd-kit`).
5. **`title_override`:** campo de texto por fila — si se rellena, el documento renderizado inserta ese texto
   como **Heading-1** antes del contenido de esa sección (equivale a un título de capítulo).
6. **`enabled_default`:** controla si la sección está activa por defecto al crear un documento desde esta plantilla.
7. Guarda los cambios → `PUT /templates/{id}/composition` persiste la lista ordenada.

**Via API:**
- `GET /templates/{id}/composition` → devuelve la lista de `TemplateComposition` (`section_id`, `position`,
  `title_override`, `enabled_default`).
- `PUT /templates/{id}/composition` → reemplaza la lista completa (cuerpo: `{ "items": [...] }`).
  El servidor activa `compose_mode='sections'` automáticamente cuando la lista no está vacía, y vuelve a
  `'single'` al guardar una lista vacía — **no se envía `compose_mode` en el cuerpo**.

**Cómo renderiza una plantilla compuesta:** al generar, Portal Documentos renderiza cada sección por separado con el
motor habitual (mismo contexto de datos, tolerancia a vacíos, marcadores preservados) y concatena los
`.docx` resultados con `docxcompose` en el orden definido, añadiendo un salto de página entre secciones.
Las secciones con `enabled=false` se omiten. La composición es **recursiva**: si una sección tiene a su vez
`compose_mode='sections'`, su lista interna se expande antes de concatenar. Si `title_override` está definido,
se añade un párrafo `Heading-1` antes del contenido de esa sección.

> **Limitación conocida:** `docxcompose` aplana los encabezados y pies de página de las secciones individuales
> al componer — el encabezado/pie del documento resultante es el de la primera sección. Las secciones con
> encabezados/pies propios (§4.3) los pierden al componer. Para encabezados/pies por sección en documentos
> compuestos, edítalos manualmente sobre el DOCX exportado.

---

### 18.4 Componer un DOCUMENTO desde un proyecto

Un **documento compuesto** es una `FormSubmission` de proyecto que tiene filas `SubmissionSection` — la lista
ordenada de secciones instanciadas para ESE documento. Una `FormSubmission` sin filas `SubmissionSection`
renderiza exactamente como antes (comportamiento clásico, sin cambios).

#### 18.4.1 Crear el documento

Desde la vista de proyecto → **«Nuevo documento»** → dos modos:

| Modo | Qué hace |
|---|---|
| **Desde plantilla** | Elige una plantilla de la lista. Si es `compose_mode='sections'`, crea un documento compuesto (`POST /projects/{id}/documents` con `template_id`) y va al editor de composición. Si es plantilla clásica, va al formulario de generación habitual. |
| **Vacío (compuesto)** | Crea una `FormSubmission` sin `template_id` → documento compuesto en blanco listo para añadir secciones. |

El endpoint que se llama en ambos casos compuestos: `POST /projects/{id}/documents` con `{template_id, data, draft}`.
La respuesta devuelve la `FormSubmission` con el `id` del documento creado.

#### 18.4.2 Panel de secciones (añadir / quitar / reordenar)

El editor de composición (`/projects/{projectId}/compose/{submissionId}`) tiene dos pestañas:

**Pestaña «Secciones»** — `SubmissionSectionsPanel`:
- Lista las secciones del documento con su nombre, estado y posición.
- **Añadir sección:** botón «Añadir sección» → desplegable con la biblioteca de secciones del tenant.
  Puedes **añadir la misma sección más de una vez** (ej. repetir un capítulo para dos instalaciones).
  Las secciones ya presentes muestran un contador `×N`.
- **Reordenar:** drag-and-drop (mango grip) con teclado accesible (Space + ArrowUp/Down + Space).
- **Activar / desactivar** por sección: botón «Activa» / «Inactiva» — las secciones inactivas se omiten
  al renderizar.
- **Eliminar:** botón papelera por fila.
- **Guardar:** botón «Guardar secciones» → `PUT /submissions/{id}/sections` (reemplaza la lista completa;
  el orden en el array define la `position`). Se habilita solo cuando hay cambios sin guardar.

**Pestaña «Datos por sección»** — formulario por sección:
- Muestra una tarjeta por sección activa con los campos configurados en esa sección.
- Los campos se rellenan igual que en cualquier formulario de plantilla (texto, número, fecha, selects,
  imágenes, grupos repetibles).
- **Grupos repetibles:** filas editables con drag-and-drop para reordenar (`@dnd-kit`), botón «Añadir fila»,
  botón eliminar fila. Los `data-testid` de cada celda siguen el patrón `sec-{grupo}-{índice}-{campo}`.
- Cada tarjeta tiene un botón **«Guardar datos de sección»** → `PATCH /submissions/{id}/sections/{sectionRowId}`
  con `{data}`.

#### 18.4.3 Contexto de datos (cómo se fusionan los datos al renderizar)

- **Contexto global:** los datos de la `FormSubmission` (campo `data` del submission, rellenados si el
  documento se creó desde una plantilla compuesta con datos iniciales).
- **Contexto de sección:** los datos de cada `SubmissionSection.data` (rellenados en la pestaña «Datos
  por sección»).
- **Fusión:** `contexto_final = merge(datos_globales, datos_de_sección)`. Los datos de sección **toman
  precedencia** sobre los globales. Los campos calculados se resuelven sobre el contexto fusionado.
- **Preview == generate:** la misma fusión y el mismo motor de cálculos se usan en preview y en generate,
  garantizando paridad. Los orígenes rápidos (fórmula, dataset_lookup) se calculan en preview; los lentos
  (IA, endpoint, pipeline) solo en generate.

#### 18.4.4 Vista previa en vivo y exportación

- **Previsualizar:** botón «Previsualizar» (o se dispara automáticamente tras guardar datos/secciones con
  un debounce de ~700 ms) → `POST /submissions/{id}/preview` → devuelve texto plano del documento compuesto
  (párrafos y tablas). Solo orígenes rápidos (formula, dataset_lookup); nunca IA/endpoint.
- **Generar documento:** botón «Generar documento» → `POST /submissions/{id}/generate` → genera el DOCX
  completo (con todos los orígenes, incluidos IA/endpoint) en segundo plano. El estado `submission.status`
  pasa a `rendering` y luego `done` o `error`.
- **Exportar Word:** `GET /submissions/{id}/docx` (botón «Exportar Word»). Solo disponible cuando `status=done`.
  Devuelve el `.docx` generado; 425 si el render aún no ha terminado, 409 si hubo error.
- **Exportar PDF:** `GET /submissions/{id}/pdf` (botón «PDF»). Solo disponible cuando `status=done`.
  Devuelve el `.pdf` generado; 425 si el render aún no ha terminado, 409 si hubo error.

---

### 18.5 API de referencia (resumen)

| Endpoint | Método | Qué hace |
|---|---|---|
| `GET /templates/?kind=section` | GET | Lista las secciones del tenant |
| `GET /templates/?kind=template` | GET | Lista las plantillas clásicas (sin secciones) |
| `GET /templates/{id}/download` | GET | Exporta el `.docx` de una sección/plantilla |
| `GET /templates/{id}/composition` | GET | Lista las secciones que componen una plantilla |
| `PUT /templates/{id}/composition` | PUT | Reemplaza la lista de composición de una plantilla |
| `POST /projects/{id}/documents` | POST | Crea un documento compuesto (vacío o desde plantilla) |
| `GET /submissions/{id}/sections` | GET | Lista las `SubmissionSection` de un documento |
| `PUT /submissions/{id}/sections` | PUT | Reemplaza la lista de secciones de un documento |
| `PATCH /submissions/{id}/sections/{sid}` | PATCH | Actualiza los datos (`data`) de una sección del documento |
| `GET /submissions/{id}/sections/form` | GET | Devuelve el form-schema por sección para el editor |
| `POST /submissions/{id}/preview` | POST | Vista previa de texto del documento compuesto |
| `POST /submissions/{id}/generate` | POST | Genera el documento completo (async) |
| `GET /submissions/{id}/docx` | GET | Descarga el `.docx` generado (solo si `status=done`; 425 si renderizando, 409 si error) |
| `GET /submissions/{id}/pdf` | GET | Descarga el `.pdf` generado (solo si `status=done`; 425 si renderizando, 409 si error) |

---

### 18.6 Sección de ejemplo descargable (Epic T / T3) — chuleta exhaustiva

Para aprender la autoría de secciones sin partir de cero, descarga la **sección de ejemplo** oficial:

| Descarga | Qué contiene | Endpoint |
|---|---|---|
| **`.docx` de sección** | Chuleta exhaustiva: todos los tipos de campo, tabla repetible, cálculo referenciado, condicionales, imagen, cabecera/pie y aritmética | `GET /sections/sample` |
| **Bundle ZIP** | `.docx` + `INSTRUCTIONS.md` + companions importables | `GET /sections/sample/bundle` |

**Botones en la UI:** en la página **«Secciones»** hay dos botones junto a los de crear:
- **«Ejemplo»** — descarga el `.docx` de referencia.
- **«Bundle»** — descarga el ZIP con todo: `.docx`, instrucciones para el agente e importables.

#### Tipos de campo (`var_type`) vs. roles de diseñador

El motor de Portal Documentos solo conoce cuatro valores reales de `var_type`:

| `var_type` real | Cuándo se asigna |
|---|---|
| `text` | Por defecto; también para booleanos, condicionales y opciones |
| `number` | Nombre contiene qty/num/count/amount/price/total (o asignado manualmente) |
| `date` | Nombre contiene date/fecha |
| `image` | Nombre contiene image/img/photo/logo |

Lo que en la UI se llama «select», «cascada», «calculado» o «lista» **no son `var_type`** — son
**roles de diseñador** implementados sobre los tipos anteriores:

| Apariencia en UI | `var_type` real | Mecanismo |
|---|---|---|
| Select (desplegable) | `text` | `options_source` apunta a un dataset |
| Cascada | `text` | `depends_on` apunta al campo padre; filas del dataset llevan `parent` |
| Calculado | `number` (o `text`) | `value_origin=formula` + `formula` con la expresión |
| Lista / tabla repetible | `text` (iterable de bucle) | La variable es el iterable del `{%tr for x in lista %}` en el .docx |

#### Companions del bundle (importables via B15)

| Fichero | Importar via | Qué demuestra |
|---|---|---|
| `sample_section_fields.json` | `PUT /templates/{id}/fields/import` | 15 campos con los 4 var_types reales; demuestran además los roles de diseñador: select (`options_source`), cascada (`depends_on`), calculado (`value_origin=formula`), y lista (iterable de bucle) |
| `sample_section_datasets.json` | `POST /datasets/import` (global) | Dataset `servicios_disponibles` con cascada tipo→subtipo |
| `sample_section_calculations.json` | `POST /templates/{id}/calculations/import` (propio de la sección) | Cálculos `coste_seccion` (formula) y `coste_con_iva_seccion` |
| `sample_section_prompts.json` | `POST /templates/{id}/prompts/import` (propio de la sección) | Prompts de campo, cálculo e improve |

**INSTRUCTIONS.md** del bundle — contenido de ejemplo para `agent_instructions`: describe los constructos
de la sección, las reglas de edición y un `curl` de importación de cada companion.

#### Qué demuestra el `.docx` de sección

El `.docx` está organizado en 6 Heading-1 (agrupados en formulario por el analizador):

| Sección | Constructos demostrados |
|---|---|
| 1. Campos generales | text, number (num…/…total/…amount), date (fecha…), image (`{{ logo }}` → auto-resuelto a placeholder.png por render.py) |
| 2. Select + cascada + calculado | roles de diseñador: `options_source`, `depends_on`, `value_origin=formula` (todos sobre var_type=text/number) |
| 3. Operaciones aritméticas | + - * / // % **,  round/max/min/abs/len/int/float/str como filtros Jinja |
| 4. Condicionales | inline if/else/endif, ternario; `activo` e `incluir_notas` son text usados como condición truthy |
| 5. Tabla dinámica de partidas | `{%tr for partida in partidas %}` (lista = rol de bucle sobre var_type=text), loop.index, bucle inline |
| 6. Notas opcionales | `{%p if incluir_notas %}`, lista numerada, nueva sección Word con cabecera/pie propios |

> **Nota sobre TOC:** Un campo de Tabla de Contenidos (Word `TOC` field) solo tiene sentido en una
> plantilla completa multi-sección (ver `generate_template.py` §280). En una sección individual el
> analizador no genera índice propio; el TOC se añade a nivel de plantilla compuesta, no de sección.

**Tolerancia garantizada:** renderiza sin errores con datos vacíos (sandbox tolerante, `÷0 → 0`).

---

### 18.7 Checklist para el autor/integrador

**Crear una sección:**
1. Descarga el `.docx` de ejemplo (`GET /sections/sample`) y úsalo como chuleta. Diseña el `.docx`
   con las mismas reglas que cualquier plantilla (§1–§4, §12): marcadores `{{ }}`,
   tablas `{%tr for %}`, condicionales `{%p if %}`. Usa los mismos estilos corporativos.
2. Crea la sección en Portal Documentos (menú «Secciones» → nueva/sube). Sube el `.docx`.
3. Configura sus variables en el diseñador (§5–§9): tipos, obligatorios, capítulos, orígenes de valor.
4. Genera una prueba de render individual antes de componer.

**Componer una plantilla:**
1. Crea una plantilla ordinaria (o usa una existente).
2. En la pestaña «Secciones» del detalle de plantilla, añade las secciones en orden.
3. Define `title_override` en las secciones que necesiten un Heading-1 de capítulo.
4. Guarda → la plantilla pasa a `compose_mode='sections'`.

**Componer un documento:**
1. Desde un proyecto, «Nuevo documento» → «Vacío» o «Desde plantilla compuesta».
2. En el editor, pestaña «Secciones»: añade, reordena, activa/desactiva.
3. Pestaña «Datos por sección»: rellena los campos de cada sección.
4. «Previsualizar» para comprobar el texto; «Generar documento» para el DOCX/PDF final.

---

## 19. Crear una plantilla desde un Word en la propia plataforma (Fase 9)

Lo mismo que hace el kit `docai-platform-templatesManager` en local, pero desde la SPA y para
**cualquier usuario**: *Plantillas → Crear desde Word* (`/templates/new-from-word`). El backend
ejecuta **el mismo código del kit** (copiado sin cambios en `backend/app/kit/`), así que el resultado
es byte a byte el que daría `docai-kit build` con el mismo inventario.

1. **Subir el Word.** La plataforma **prepara** el Word (huecos y casillas, ver §19.1), extrae los
   párrafos y **propone el inventario con reglas fijas**: celdas vacías y controles por rellenar,
   casillas ☐, marcadores (`[Nombre]`, `<<x>>`, `{x}`, `XXXX`, `____`), texto resaltado, sombreado o
   subrayado, «Etiqueta: valor», tablas «etiqueta | valor», datos reconocibles (NIF/CIF/NIE, CUPS,
   IBAN, correo, teléfono, fechas, código postal tras «C.P.») y tablas de cabecera + una fila (→ tabla
   repetible). Importes y potencias se sugieren pero no se añaden solos. Los datos personales
   detectados van a `debe_desaparecer`. Si la empresa tiene **IA real** (no el *mock*), la IA revisa
   después esa propuesta (§19.2). La propuesta siempre construye.
2. **Revisar.** Tabla de campos editable (nombre, etiqueta, tipo, obligatorio) y lista de «otras
   detecciones» para añadir. Un `select` muestra sus **opciones** para editarlas, añadirlas o
   quitarlas; las casillas del Word van en la fila de su campo («3 casillas») y no en una fila propia.
   *Guardar y validar* vuelve a construir: lo que no construye no se guarda y se ven los errores del
   kit con su acción correctora.
3. **Asistente (opcional).** Un chat en lenguaje natural. La IA **solo** devuelve operaciones sobre el
   inventario (`upsert_campo`, `eliminar_campo`, `upsert_bloque`, `set`, `upsert_dataset|calculo|prompt`…);
   el servidor las aplica y el kit decide si valen. Si la respuesta de la IA llega cortada, el chat lo
   dice («se cortó») y no aplica nada.
4. **Validar.** V01–V12 del kit y descargas para revisar: `plantilla.docx`, ejemplo relleno en DOCX y
   PDF (con los textos originales: debe quedar igual que el Word subido) y los cuatro JSON.
5. **Importar.** Un botón crea una plantilla **nueva** con campos, cálculos y prompts propios. Los
   datasets que ya existen en la empresa **se reutilizan sin modificarlos**; los cálculos `endpoint`,
   `pipeline` y `code` (usan conectores) solo los importa un administrador. Si un paso falla, no queda
   nada creado.

### 19.1 Huecos y casillas (Fase 24)

Un formulario «para rellenar» no tiene texto que sustituir: sus respuestas son **celdas vacías**,
**controles de contenido** que muestran «Haga clic aquí…» y **casillas** ☐ (controles `w14:checkbox`
o el carácter suelto). Antes de proponer, `kit.preparar` (en la CLI, `docai-kit preparar`) deja cada
uno como un token `⟦hNNN⟧`:

- cada celda de tabla sin texto recibe su token, con el formato de la marca de párrafo;
- cada ☐/☒ pasa a ser su propio token, y los controles de casilla y de texto se desenvuelven;
- un control de texto que muestra su marcador pasa a ser un token;
- lo que está en un cuadro de texto se prepara también en su copia `mc:Fallback`.

La etiqueta de cada hueco sale de la celda de la izquierda y, si la tabla tiene fila de cabecera, de la
cabecera de su columna. No hay posiciones fijas por documento: vale para cualquier Word.

Una tabla con **varios bloques** (una fila de una celda con el título del bloque, una fila de cabeceras
y filas de datos «C1 | ☐ | ☐…») usa la cabecera **de su bloque**: la primera fila de encima sin huecos
con dos o más celdas con texto; una fila de una sola celda corta la búsqueda. Así cada celda de
«C1 | Tipo de cubierta | Orientación» se llama `c1_tipo_de_cubierta`, «C1 – Tipo de cubierta», y no
seis veces «C1». Solo en filas con dos huecos o más: en una tabla «Etiqueta | hueco» la fila de encima
es otro dato.

Con esos tokens, dos reglas nuevas:

| Regla | Qué detecta | Qué crea |
|---|---|---|
| `hueco` | celda vacía o control por rellenar | un campo (`text`, `number` si la etiqueta pide un número o una potencia, `date`…) |
| `casillas` | las ☐ de un mismo párrafo («☐ Sí ☐ No», «☐ CC ☐ CA») | de 2 a 4 opciones distintas: un `select` (opción única); 5 o más: un `boolean` por opción |

En el Word **las casillas conservan su aspecto**: cada una es un campo auxiliar calculado, invisible en
el formulario, llamado `<campo>__<n>`, con fórmula `'☒' if <campo> == '<opción>' else '☐'` (en un
`boolean`, `'☒' if <campo> else '☐'`). Por eso un campo que solo usa una fórmula es válido sin
ocurrencias en el Word (`build` y V02 lo admiten). Si quitas el campo, se van con él sus casillas; una
opción con casilla no se puede quitar suelta.

El inventario guarda la lista `huecos: [{token, original}]`. Al construir, `build` devuelve a su texto
original cada token que **ningún campo usa**: un hueco descartado vuelve a ser una celda vacía o una casilla con su carácter original (☐ o ☒),
y nunca queda un `⟦` en `plantilla.docx`.

Fuera de alcance: huecos de espacios en línea («L1-N:      L1-PE:»), casillas Wingdings (`w:sym`) y
separar tablas en condicionales («¿Incluye batería?» + detalle: sigue siendo trabajo del chat).

### 19.2 Revisión por IA de la propuesta (Fase 24)

Las reglas van primero. Después, si la empresa tiene IA real, **una sola llamada** al LLM lee los
párrafos y los grupos de las reglas y devuelve un bloque JSON con:

- **cambios** de un grupo: `nombre`, `etiqueta`, `tipo`, `descripcion` y, en unas casillas, el `modo`
  (`unica` → `select`, `multiple` → un `boolean` por opción). P. ej. «C1» × 6 columnas pasa a
  `c1_tipo_cubierta`, `c1_orientacion` (`number`)…;
- **descartar**: grupos que no son un dato variable (un título subrayado, un organismo fijo);
- **nuevos**: datos **ya escritos en la prosa** que ninguna regla ve («D./Dña. … con NIF …, en
  representación de …», «el inmueble ubicado en …»), con el literal copiado tal cual y si es personal.

Cada entrada se valida por separado: clave que existe, nombre `snake_case` válido (sin `__`, que es de
las casillas), tipo admitido (`select`, `boolean`, `list` e `image` no los elige la IA), literal presente
en su párrafo y fuera de un hueco. La que no vale se cuenta como **rechazada** y se ignora; tramos,
solapes y `build` los sigue comprobando el mismo código del kit. El primer mensaje del chat resume lo
que hizo («He revisado el documento con IA: 4 campos nuevos, 14 ajustes»). Si la IA no está o falla, la
propuesta es la de reglas y el chat lo avisa. El consumo se anota en `AIUsageRecord`
(`operation="template_builder"`, `action="propuesta"`).

### 19.3 Apartados del Word y orden del formulario

El formulario agrupa los campos por los **apartados del Word**, en el orden del documento: cada
apartado abarca desde su título hasta el siguiente y lo que va antes del primero son los «Datos
generales». Al subir el Word, unas reglas proponen qué párrafos abren un apartado:

| Regla | Cómo se marca en el Word |
|---|---|
| `titulo` | estilo **«Título 1»** (o el nivel de título más alto que use el documento). Si existe, manda. |
| `numerado` | título corto en negrita o mayúsculas que empieza por «1.», «2)», «IV -»… (no «1.1», que es un subapartado), también en una barra hecha con una tabla de una celda, o lista numerada de primer nivel en negrita |
| `fila_titulo` | fila de tabla de **una sola celda** (celdas combinadas) en negrita o mayúsculas, p. ej. «DATOS DEL TITULAR» |
| `mayusculas` | línea corta en mayúsculas, sin «etiqueta: valor» ni cifras |

La primera línea del Word en mayúsculas se toma como **título del documento**, no como apartado. Con IA,
el LLM recibe los candidatos y devuelve la lista final (`secciones`): puede quitar subapartados o el
título y añadir un párrafo que las reglas no vieron, pero el título de cada apartado tiene que salir
de su propio párrafo (se descarta un texto inventado). Sin IA, vale la regla más fiable que aparezca
(«Título 1»; si no, al menos dos numerados; si no, filas-título y mayúsculas).

Para que se detecten sin dudas, **marca cada apartado con el estilo «Título 1»** o con un título
numerado en negrita («1. Datos del titular»). En la revisión, la columna **Apartado** enseña el de cada
campo y permite cambiarlo (se guarda como `capitulo`; «Datos generales» es `null`). El apartado y la
posición en el documento (`orden`) se calculan al construir, sin escribirse en el inventario: lo que
fijas a mano manda, y la plantilla importada lleva `chapter` y `field_order` en el orden del Word.

API: `POST /template-drafts/` (multipart `file`, `nombre`), `GET|DELETE /template-drafts/{id}`,
`PUT /template-drafts/{id}/estado`, `POST /template-drafts/{id}/validate`,
`GET /template-drafts/{id}/files/{plantilla.docx|fields.json|…|ejemplo.docx|ejemplo.pdf}`,
`POST /template-drafts/{id}/messages`, `POST /template-drafts/{id}/import`.
