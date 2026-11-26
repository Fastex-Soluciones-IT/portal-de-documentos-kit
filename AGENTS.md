# AGENTS.md — Cómo convertir un Word en una plantilla DocAI

> **Eres un agente de desarrollo.** Tu único trabajo creativo es redactar **`inventario.yaml`**: decidir
> qué hueco del Word pasa a ser qué campo, tabla repetible o sección condicional. Todo lo demás (leer el
> Word, colocar los marcadores, generar los JSON, validar e importar) lo hace el código determinista de
> `docai-kit`. Misma entrada ⇒ mismos bytes de salida.

## Reglas de oro

- **Solo editas `plantillas/<slug>/`**: `inventario.yaml` y, si hacen falta, `datasets.yaml`,
  `calculations.yaml`, `prompts.yaml` y `datos_ejemplo.yaml`.
- **Prohibido** editar `componentes/` a mano (lo genera `docai-kit build` y `validate` lo comprueba con
  V11) y **prohibido** editar el `.docx` con el MCP de Word. El MCP de Word es opcional y solo de lectura
  (`docs/01-MCP-SETUP.md`).
- **No toques `origen.docx`** ni **`ids.lock.json`** (lo gestiona `build`).
- **No inventes el modelo de datos.** Las guías de `docs/*GUIDE.md` son la referencia normativa y
  `schemas/*.schema.json` lo hace cumplir. Los YAML de dominio usan las mismas claves (en inglés) que los
  JSON de DocAI.
- **No importes nada sin que el usuario lo pida.** Entregas el comando de `import` en `--dry-run`.
- **No toques secretos.** Host y credenciales solo por variables de entorno (`DOCAI_HOST`, `DOCAI_USER`,
  `DOCAI_PASS`), nunca en ficheros del repo.
- **Si un comando falla, corrige solo el inventario** (o el YAML de dominio) y repite. Cada error tiene un
  código con su acción correctora (tabla en `docs/02-WORKFLOW.md`). No hay arreglos "a mano" en la salida.

## El flujo

```bash
uv sync                                   # una vez por clon
uv run docai-kit extract <slug>           # 1. lee origen.docx -> trabajo/<slug>/documento.json
#                                           2. redactas plantillas/<slug>/inventario.yaml (+ YAML de dominio)
uv run docai-kit build <slug>             # 3. genera componentes/<slug>/
uv run docai-kit validate <slug>          # 4. V01–V12; repite 2-4 hasta 0 errores
uv run docai-kit import <slug> --entorno test   # 6. dry-run: imprime las peticiones, no envía nada
```

### 0 · Preparación

1. Si el usuario trae un Word nuevo: crea `plantillas/<slug>/` (slug en `snake_case`) y copia el Word como
   `plantillas/<slug>/origen.docx`. Si hay varios candidatos, pregunta cuál.
2. Si el Word tiene **control de cambios**, `extract` falla con `E010`: pide al usuario que acepte o
   rechace los cambios en Word y vuelva a guardar.

3. **Si el Word es un formulario** (celdas vacías para rellenar, casillas ☐/☒, controles de contenido con
   texto de ayuda), ejecuta antes `uv run docai-kit preparar <slug>`: lee `plantillas/<slug>/word_original.docx`
   y escribe `origen.docx` (con un token `⟦hNNN⟧` en cada hueco) y `trabajo/<slug>/huecos.json`. Después sigue
   con `extract` y trata cada token como un literal más: `buscar: "⟦h003⟧"`.
   - Un token por celda de tabla vacía (no las continuación de `vMerge`), por casilla ☐/☒ y por control de
     contenido que muestra su marcador (`showingPlcHdr`). Las casillas de un mismo párrafo forman un grupo
     (`G001`…) y llevan `opcion` (el texto de la casilla). En cuadros de texto se refleja también la copia
     `mc:Fallback`.
   - Los tokens que ningún `buscar` use **no hay que descartarlos a mano**: `build` los restaura a su
     `original` (celda vacía; la casilla, a su carácter original: ☐ o ☒), registrado en la clave `huecos` del inventario (ver `docs/02-WORKFLOW.md`).
   - **Casillas** — grupo de elección única: un campo `select` con `ocurrencias: []` y `opciones`, más un
     auxiliar por casilla (`tipo: text`, `calculado: true`, `visible: false`, nombre `<campo>__<n>` con n desde 1,
     `formula: "'☒' if <campo> == '<opción>' else '☐'"`) cuyo `buscar` es el token de esa casilla. Elección
     múltiple: un `boolean` por casilla con `formula: "'☒' if <campo> else '☐'"`. Por defecto, 2–4 opciones =
     elección única y 5 o más = múltiple.

### 1 · `docai-kit extract <slug>`

Escribe `trabajo/<slug>/documento.json` con **cada párrafo** del documento (cuerpo, tablas —incluidas las
anidadas—, cuadros de texto, cabeceras, pies y notas), en este orden: `document`, `header*`, `footer*`,
`footnotes`, `endnotes`. Por párrafo:

| Clave | Qué es |
|---|---|
| `id` | Localizador estable: `document/p/0042`, `document/tbl/03/r/02/c/01/p/00`, `header2/p/0001`, `document/p/0007/txbx/00/p/00` |
| `style`, `heading_level` | Estilo y nivel de título (o `null`) |
| `text` | Texto del párrafo (concatenación de sus `w:t`) |
| `runs` | `{text, rPr_hash}` de cada fragmento con formato |
| `chapter` | Texto del Título 1 del cuerpo más cercano por encima (o `null` = «Datos generales») |

También imprime `origen_sha256`, que va tal cual en el inventario.

### 2 · Redactar `inventario.yaml` (la única parte creativa)

Lee `documento.json` entero e identifica los huecos: datos del cliente/proyecto, fechas, importes, valores
que cambian en cada documento, tablas que crecen, cláusulas opcionales y valores calculados. Decide el
componente de cada uno:

| Lo que ves en el Word | En el inventario | Guía |
|---|---|---|
| Dato que el usuario teclea | campo con `tipo` y `ocurrencias` | `FIELDS_FILE_GUIDE.md` |
| Elección de un catálogo reutilizable / cascada | campo con `dataset:` (+ `depende_de:`) y el catálogo en `datasets.yaml` | `DATASETS_FILE_GUIDE.md` |
| Lista fija de una sola plantilla | campo con `opciones:` | `FIELDS_FILE_GUIDE.md` §2 |
| Valor calculado inline | campo con `formula:` | `TEMPLATE_AUTHORING_GUIDE.md` §8 |
| Valor de un cálculo reutilizable | campo con `origen_valor`, `calculo`, `entradas` y el cálculo en `calculations.yaml` | `CALCULATIONS_FILE_GUIDE.md` |
| Fila de tabla que se repite | bloque `tabla_repetible` + campo `tipo: list` sin ocurrencias | `TEMPLATE_AUTHORING_GUIDE.md` §2.2 |
| Párrafos que aparecen o no | bloque `condicional` + campo `tipo: boolean` sin ocurrencias | `TEMPLATE_AUTHORING_GUIDE.md` §2.3 |
| Texto redactado por IA | prompt en `prompts.yaml` | `AI_PROMPTS_FILE_GUIDE.md` |

Forma del inventario (esquema completo: `schemas/inventario.schema.json`, `additionalProperties: false` en
todos los niveles):

```yaml
version: 1
slug: mi_plantilla
origen_sha256: "…"                     # el que imprime `extract`
nombre_plantilla: Contrato de suministro  # opcional: nombre al subirla a DocAI (por defecto, el slug)
nombres_heredados: [codigo_ID]          # nombres que no cumplen ^[a-z][a-z0-9_]*$ y se aceptan (V07)
debe_desaparecer: ["Calle Mayor 1", "B12345678"]   # datos reales que no pueden quedar en la plantilla

campos:
  - nombre: loc_calle                   # = {{ loc_calle }} en el Word
    etiqueta: Calle del emplazamiento
    tipo: text                          # text textarea number date boolean select list image currency email url
    capitulo: Emplazamiento             # opcional; si falta, el Título 1 anterior a la primera ocurrencia
    ocurrencias:
      - buscar: "Calle Mayor 1"         # literal exacto dentro de un párrafo (regex solo con `regex: true`)
        esperadas: 3                    # OBLIGATORIO: si aparece otro número de veces -> E003
        parte: document                 # opcional: document | headerN | footerN | footnotes | endnotes
        en: document/p/0042             # opcional: acota a un párrafo concreto
  - nombre: total_con_iva
    tipo: currency
    formula: "round(base * 1.21, 2)"    # campo calculado inline (value_origin = formula)
    ocurrencias: [{buscar: "12.100,00 €", esperadas: 1}]

bloques:
  - tipo: tabla_repetible
    lista: inversores                   # debe declararse en `campos` (tipo: list, ocurrencias: [])
    tabla: {ancla: "Fabricante inversor", parte: document}   # texto que identifica UNA tabla
    fila_plantilla: 1                   # índice de la fila que se repite
    columnas:
      - {buscar: "Huawei", atributo: fabricante}             # -> {{ item.fabricante }}
      - {buscar: "SUN2000-10KTL", atributo: modelo}
  - tipo: condicional
    variable: incluir_baterias          # debe declararse en `campos` (tipo: boolean, ocurrencias: [])
    desde: document/p/0120              # primer párrafo incluido
    hasta: document/p/0127              # último párrafo incluido (mismo contenedor)
```

Claves de un campo y su equivalente en `fields.json` (`FieldConfig`). Escribe **solo lo que se sale del
valor por defecto**:

| Inventario | `FieldConfig` | Por defecto |
|---|---|---|
| `nombre` | `name` | — (obligatorio) |
| `nombre_tecnico` | `technical_name` | = `nombre` |
| `etiqueta` | `label` | `null` |
| `tipo` | `type` | — (obligatorio) |
| `requerido` | `required` | `false` |
| `descripcion` / `ayuda` | `description` / `help_text` | `null` |
| `capitulo` | `chapter` | Título 1 anterior a la primera ocurrencia |
| `orden` | `field_order` | posición de la primera ocurrencia dentro de su capítulo (0, 1, 2…) |
| `visible` | `visible` | `true` |
| `editable` | `editable` | `false` si el campo es calculado; si no, `true` |
| `visible_cuando` | `visible_when` | `null` |
| `origen_valor` | `value_origin` | `formula` si hay `formula`; `dataset` si hay `dataset`; si no, `manual` |
| `calculo` + `entradas` | `calculation_binding` | `null` (`ai`/`endpoint`/`pipeline` lo exigen) |
| `dataset` / `depende_de` | `options_source` / `depends_on` | `null` |
| `opciones` | `options` | `null` |
| `valor_defecto` | `default_value` | `null` |
| `formula` | `formula` | `null` |
| `calculado` | `calculated` | `true` si `value_origin` ∈ {formula, ai, endpoint, pipeline, code} |
| `renombrado_de` | (conserva el `field_id`) | — |

Los `FLD-xxxx` los asigna `build` desde `ids.lock.json`: un nombre nuevo recibe el siguiente número
libre; los IDs no se renumeran ni se reutilizan. **Para renombrar un campo** conservando su ID, pon
`renombrado_de: <nombre_anterior>`; sin eso, el nombre nuevo es un campo nuevo.

Consejos para que `build` no falle:
- Prefiere literales largos y únicos. Si un literal aparece en sitios que no son el hueco, acótalo con
  `en:` o `parte:` (el mensaje de `E003` lista dónde aparece).
- Una coincidencia no puede cruzar párrafos, tabuladores, saltos, imágenes, campos de Word ni el límite
  de un hipervínculo (`E008`).
- `datos_ejemplo.yaml` es un mapa `nombre -> valor` con todos los campos (listas como listas de objetos).
  Lo usa `validate` (V09/V10) para renderizar.

### 3 · `docai-kit build <slug>`

Parte siempre del origen: comprueba `origen_sha256` (`E001`), valida el inventario (`E002`), calcula
**todas** las coincidencias sobre el texto original (`E003`/`E004`/`E005`/`E008`), las aplica a nivel de
runs (el marcador entero en el primer run, con su formato), aplica los bloques, asigna los `FLD-xxxx` y
escribe `componentes/<slug>/{plantilla.docx, fields.json, datasets.json, calculations.json, prompts.json}`
de forma byte-estable.

### 4 · `docai-kit validate <slug>`

Doce comprobaciones (V01–V12, detalle en `docs/02-WORKFLOW.md`), acumulando todos los fallos. Debe salir
con código `0`. V07 (formato de nombres) es aviso salvo con `--strict`; V12 (PDF) se marca `skipped` si no
hay LibreOffice.

### 5 · Corregir

Si `build` o `validate` fallan, corrige **solo** el inventario o los YAML de dominio y vuelve al paso 3.

### 6 · Entregar

Resume al usuario, de forma escaneable:
- qué campos, tablas repetibles, condicionales, datasets, cálculos y prompts has definido y por qué;
- la salida de `validate` (y los avisos que queden);
- lo que requiere acción humana (conectores de cálculos `endpoint`, revisar prompts);
- el comando de importación en dry-run:

```bash
uv run docai-kit import <slug> --entorno test            # imprime las peticiones
# Para ejecutar de verdad (solo si el usuario lo pide):
DOCAI_HOST=… DOCAI_USER=… DOCAI_PASS=… uv run docai-kit import <slug> --entorno test --yes
```

## Migrar una plantilla adaptada a mano

Si ya existe un Word adaptado (con `{{ }}`) y su `fields.json`, recupera el inventario en lugar de
redactarlo:

```bash
uv run docai-kit infer --origen plantillas/<slug>/origen.docx --plantilla <adaptada>.docx \
    --campos <fields.json> --ids-lock plantillas/<slug>/ids.lock.json -o plantillas/<slug>/inventario.yaml
```

`infer` lista las "diferencias no explicables" (lo que no es una sustitución limpia por `{{ x }}`) y sale
con `1` si las hay: revísalas con el usuario, no las ocultes.

## Desambiguación: "sección" del Word vs "Sección" de DocAI (Epic S)

Un **Título 1** del Word es una **agrupación de campos** dentro de una sola plantilla (`chapter`). Una
**Sección de DocAI** (`Template.kind = 'section'`) es una plantilla reutilizable independiente que se
compone dentro de documentos compuestos (`TEMPLATE_AUTHORING_GUIDE.md` §18). Este kit genera plantillas;
si hablas del formulario, di "agrupación (Título 1)".
