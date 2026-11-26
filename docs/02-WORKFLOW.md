# 02 · Receta paso a paso: Word de origen → plantilla DocAI

Versión narrada del proceso. La versión imperativa para el agente es `../AGENTS.md`; el modelo de datos
está en `00-OVERVIEW.md`. El principio: **el LLM solo decide (inventario.yaml); el código hace el resto**,
siempre igual.

```
plantillas/<slug>/origen.docx ──extract──► trabajo/<slug>/documento.json
                                                  │ (el agente lo lee)
                                                  ▼
plantillas/<slug>/inventario.yaml  ◄── lo redacta el agente (única parte creativa)
plantillas/<slug>/{datasets,calculations,prompts,datos_ejemplo}.yaml   (si aplica)
                                                  │
                     ──build──►  componentes/<slug>/{plantilla.docx, fields.json, datasets.json,
                                                     calculations.json, prompts.json}
                     ──validate──►  V01–V12
                     ──import──►  DocAI (dry-run por defecto)
```

## Antes de empezar

- [ ] `uv` instalado y `uv sync` ejecutado en el repo (Python 3.12, dependencias de `uv.lock`).
- [ ] El Word está en `plantillas/<slug>/origen.docx`, **sin control de cambios**.
- [ ] (Solo para importar) acceso a una instancia DocAI y un usuario **admin de empresa**.

## Ejemplo guía: un contrato de suministro

`plantillas/contrato/origen.docx` tiene: datos del cliente, provincia/municipio, una tabla de módulos que
se repite, una cláusula de anexo opcional y un “coste anual estimado” calculado.

### Paso 1 · `uv run docai-kit extract contrato`

Escribe `trabajo/contrato/documento.json` (un objeto por párrafo con `id`, `style`, `heading_level`,
`text`, `runs` y `chapter`) e imprime `origen_sha256`. Ejemplo de entrada:

```json
{"id": "document/p/0012", "style": "Normal", "heading_level": null,
 "text": "Cliente: ACME S.L., con NIF B12345678", "runs": [...], "chapter": "Datos generales"}
```

### Paso 1 bis · `uv run docai-kit preparar <slug>` (solo si el Word es un formulario)

Lee `plantillas/<slug>/word_original.docx` y escribe `plantillas/<slug>/origen.docx` y
`trabajo/<slug>/huecos.json` (`[{token, original, …}]`). En `origen.docx` cada hueco lleva un token
`⟦hNNN⟧`: celdas de tabla vacías (no las de continuación `vMerge`), una por casilla ☐/☒ y los controles de
contenido que muestran su marcador (`showingPlcHdr`). Las casillas de un párrafo se agrupan (`G001`…) y llevan
`opcion`. En cuadros de texto se refleja también la copia `mc:Fallback`. Después se ejecuta `extract` sobre
`origen.docx` y los tokens se usan como literales en `buscar`.

**Casillas.** Elección única: un campo `select` con `ocurrencias: []` y un auxiliar por casilla,
`tipo: text`, `calculado: true`, `visible: false`, nombre `<campo>__<n>` (n desde 1) y
`formula: "'☒' if <campo> == '<opción>' else '☐'"`, con `buscar` = token de la casilla. Elección múltiple: un
`boolean` por casilla con `formula: "'☒' if <campo> else '☐'"`. Por defecto, 2–4 opciones es elección única y
5 o más, múltiple.

### Paso 2 · Redactar `plantillas/contrato/inventario.yaml`

```yaml
version: 1
slug: contrato
origen_sha256: "…"
debe_desaparecer: ["ACME S.L.", "B12345678"]
campos:
  - nombre: cliente
    etiqueta: Nombre del cliente
    tipo: text
    requerido: true
    ocurrencias: [{buscar: "ACME S.L.", esperadas: 2}]
  - nombre: cliente_nif
    etiqueta: NIF del cliente
    tipo: text
    ocurrencias: [{buscar: "B12345678", esperadas: 1}]
  - nombre: provincia
    tipo: select
    dataset: provincias_municipios
    ocurrencias: [{buscar: "Madrid", esperadas: 1, en: document/p/0015}]
  - nombre: modulos
    tipo: list
    ocurrencias: []
  - nombre: incluir_anexo
    tipo: boolean
    ocurrencias: []
  - nombre: coste_anual_estimado
    tipo: currency
    origen_valor: endpoint
    calculo: coste_anual
    entradas: {potencia: potencia_contratada}
    ocurrencias: [{buscar: "1.234,56 €", esperadas: 1}]
bloques:
  - tipo: tabla_repetible
    lista: modulos
    tabla: {ancla: "Módulo", parte: document}
    fila_plantilla: 1
    columnas:
      - {buscar: "JA Solar 450", atributo: nombre}
      - {buscar: "450", atributo: potencia_wp}
  - tipo: condicional
    variable: incluir_anexo
    desde: document/p/0040
    hasta: document/p/0046
```

Y, si aplica, `datasets.yaml`, `calculations.yaml` y `prompts.yaml` con **la misma forma que los JSON de
DocAI** (molde: `../ejemplos/sample_*.json`; esquema: `../schemas/*.schema.json`), más un
`datos_ejemplo.yaml` con un valor para cada campo.

### Paso 3 · `uv run docai-kit build contrato`

Genera `componentes/contrato/`. Lo que hace, en orden:

1. Comprueba `origen_sha256` (`E001`) y valida el inventario y los YAML (`E002`, `E013`).
2. Calcula **todas** las coincidencias sobre el texto original, sin aplicar nada: número exacto
   (`E003`), sin solapes (`E004`), ámbito existente (`E005`), sin cruzar contenido no textual (`E008`).
3. Sustituye a nivel de runs, en orden inverso dentro de cada párrafo: el marcador completo
   `{{ nombre }}` va al primer run del tramo y conserva su `rPr`; el resto del tramo se recorta y los runs
   vacíos se eliminan. Ningún marcador puede quedar partido.
4. Bloques: filas `{%tr for item in modulos %}` / `{%tr endfor %}` alrededor de la fila plantilla (cuyas
   celdas pasan a `{{ item.<atributo> }}`), y párrafos `{%p if incluir_anexo %}` / `{%p endif %}`
   alrededor del rango.
5. Asigna los `FLD-xxxx` desde `ids.lock.json` y genera `fields.json` con todas las claves de
   `FieldConfig` en el orden del esquema.
6. Escribe todo de forma byte-estable (ZIP con orden y fechas fijos; JSON canónico).

**Clave `huecos`.** El inventario puede traer `huecos: [{token, original}]` (copia de lo que escribió
`preparar`). `build` restaura a su `original` todo token que ningún `buscar` use: la celda descartada vuelve a
quedar vacía y la casilla descartada vuelve a su carácter original (☐ o ☒). Un campo sin ocurrencias es válido si la `formula` de otro campo lo
nombra (caso del `select` de un grupo de casillas).

### Paso 4 · `uv run docai-kit validate contrato`

| Código | Comprobación |
|---|---|
| V01 | Cada JSON de `componentes/<slug>/` valida contra su esquema de `schemas/` (y sin claves duplicadas) |
| V02 | Variables de la plantilla (`get_undeclared_template_variables()`) == nombres de `fields.json` |
| V03 | Cada `options_source` apunta a una `key` de dataset existente |
| V04 | Cada `calculation_binding.calculation_key` existe; las entradas y campos de su `input_map` existen |
| V05 | Ningún `{{`, `{%`, `}}` o `%}` partido entre runs; la plantilla parsea con el Jinja de docxtpl |
| V06 | Cada ocurrencia se aplicó y no queda ningún literal de `debe_desaparecer` |
| V07 | Nombres con formato `^[a-z][a-z0-9_]*$` (aviso; error con `--strict` salvo `nombres_heredados`) |
| V08 | Render con contexto vacío `{}` sin excepción |
| V09 | Render con `datos_ejemplo.yaml` sin excepción y sin `{{`/`{%` en el resultado |
| V10 | Render con contexto parcial (solo los campos con `field_order` par) sin excepción |
| V11 | `componentes/<slug>/` está al día: un build limpio da los mismos SHA-256 (y el lock no cambia) |
| V12 | Conversión a PDF con LibreOffice; `skipped` si `soffice` no está |

Salida: tabla legible; con `--json`, un informe con `{codigo, severidad, mensaje, ubicacion}` por fallo.
Si algo falla, **corrige el inventario** y vuelve al paso 3.

### Paso 5 · Revisión humana (opcional)

```bash
uv run docai-kit render contrato --datos plantillas/contrato/datos_ejemplo.yaml -o /tmp/contrato.docx --pdf
```

### Paso 6 · `uv run docai-kit import contrato --entorno test`

Por defecto es **dry-run**: imprime las peticiones sin enviar nada. Orden fijo (el de las guías:
cálculos y prompts pertenecen a la plantilla y necesitan su id):

1. `POST /api/v1/login/access-token` (form `username`/`password`)
2. `POST /api/v1/datasets/import` ← `datasets.json`
3. `POST /api/v1/templates/` (multipart `file` + `name`) ← `plantilla.docx` → `TEMPLATE_ID`
4. `POST /api/v1/templates/{TEMPLATE_ID}/calculations/import` ← `calculations.json`
5. `POST /api/v1/templates/{TEMPLATE_ID}/prompts/import` ← `prompts.json`
6. `PUT /api/v1/templates/{TEMPLATE_ID}/fields/import` ← `fields.json`

Los ficheros vacíos (`[]`) se omiten. Con `--template-id <id>` se usa una plantilla ya creada y se omite
la subida. Para ejecutar de verdad: `--yes` (y además `--confirm-prod` para `prod`), con `DOCAI_HOST`,
`DOCAI_USER` y `DOCAI_PASS` en el entorno. `import` ejecuta `validate` antes y aborta si falla.

## Migrar una plantilla adaptada a mano: `infer`

```bash
uv run docai-kit infer --origen plantillas/<slug>/origen.docx --plantilla <adaptada>.docx \
    --campos <fields.json> --ids-lock plantillas/<slug>/ids.lock.json -o plantillas/<slug>/inventario.yaml
```

Alinea los párrafos por localizador (`E020` si la estructura difiere), deriva los pares
(texto original → `{{ x }}`) con un diff a nivel de carácter y elige para cada literal el ámbito más amplio
que reproduce **exactamente** la plantilla (todo el documento, una parte o un párrafo). Con `--campos`
rellena los metadatos (solo los que se salen del default) y con `--ids-lock` conserva los `FLD-xxxx`.
Todo lo que no es una sustitución limpia se lista como diferencia no explicable (`E021`, salida 1).

## Códigos de error

Salida `0` = bien, `1` = errores de validación, `2` = error de uso o de entrada.

| Código | Salida | Qué pasa | Acción correctora |
|---|---|---|---|
| `E001` | 2 | El origen ha cambiado: su SHA-256 no coincide con `origen_sha256` del inventario | Comprueba que `origen.docx` es el Word correcto. Si lo has cambiado a propósito, ejecuta `docai-kit extract <slug>`, copia el hash que imprime en `origen_sha256` y revisa las ocurrencias del inventario. |
| `E002` | 1 | `inventario.yaml` no es válido (esquema o coherencia interna) | Corrige el inventario según el mensaje (ruta del error) y `schemas/inventario.schema.json`. |
| `E003` | 1 | El texto buscado aparece un número de veces distinto de `esperadas` | Ajusta `esperadas` o acota la búsqueda con `en:` (id de párrafo) o `parte:`. El mensaje lista dónde aparece realmente. |
| `E004` | 1 | Dos coincidencias se solapan | Acota una de las ocurrencias con `en:` para que no compitan por el mismo texto. |
| `E005` | 1 | El ámbito indicado (`en:` / `parte:`) no existe en el documento | Usa un id de párrafo o una parte que aparezcan en `trabajo/<slug>/documento.json`. |
| `E006` | 1 | `ids.lock.json` es incoherente con el inventario | Revisa `renombrado_de` (debe nombrar un campo que exista en el lock) y no edites el lock a mano. |
| `E007` | 1 | No se puede resolver la tabla de un bloque `tabla_repetible` | El `ancla` debe identificar exactamente una tabla y `fila_plantilla` debe existir en ella. |
| `E008` | 1 | La coincidencia cruza contenido no textual o está dentro de un campo de Word | Busca un literal que no incluya tabuladores, saltos, imágenes, campos ni límites de hipervínculo; acótalo a un solo tramo de texto. |
| `E009` | 2 | Falta un fichero o directorio de entrada | Comprueba el slug y que existen `plantillas/<slug>/origen.docx` e `inventario.yaml`. |
| `E010` | 2 | El documento tiene control de cambios | Abre el Word, acepta o rechaza todos los cambios (Revisar > Aceptar todos), desactiva el control de cambios y guarda. |
| `E011` | 2 | Un cuadro de texto tiene la versión alternativa (`mc:Fallback`) distinta de la principal | Edita el cuadro de texto en Word (cualquier cambio regenera ambas versiones) y vuelve a guardar. |
| `E012` | 2 | El documento contiene texto en una estructura no soportada | Mueve ese texto a un párrafo, celda o cuadro de texto normal, o abre una incidencia con la ruta que indica el mensaje. |
| `E013` | 1 | Un YAML de dominio o de datos (`datasets`, `calculations`, `prompts`, `datos_ejemplo`) no es válido | Corrige el fichero según el mensaje y su esquema en `schemas/`. |
| `E020` | 2 | `infer`: la estructura de párrafos del origen y de la plantilla difiere | La plantilla debe partir del mismo origen sin añadir ni quitar párrafos, filas o celdas. Rehaz la edición o recupera la estructura en Word. |
| `E021` | 1 | `infer`: hay diferencias que no son una sustitución limpia por `{{ x }}` | Revisa el informe de diferencias no explicables: o se corrigen en la plantilla, o se asumen como cambios que el pipeline no reproduce. |
| `E030` | 1 | Rango de un bloque `condicional` no válido | `desde` y `hasta` deben estar en la misma parte y el mismo contenedor (cuerpo o celda), en orden, y sin saltos de sección dentro. |
| `E040` | 1 | `import`: `validate` ha fallado; no se importa nada | Ejecuta `docai-kit validate <slug>` y corrige los errores. |
| `E041` | 2 | `import`: faltan variables de entorno | Exporta `DOCAI_HOST`, `DOCAI_USER` y `DOCAI_PASS` (nunca en ficheros del repo). |
| `E042` | 1 | `import`: DocAI ha respondido con error | Lee el cuerpo de la respuesta: 422 = esquema; 409 = clave duplicada; 403 = permisos. |
| `E043` | 2 | `import`: falta confirmación explícita | Para ejecutar de verdad pasa `--yes`; para `prod`, además `--confirm-prod`. |
| `E050` | 2 | `render --pdf`: LibreOffice (`soffice`) no está disponible o ha fallado | Instala LibreOffice o genera solo el `.docx`. |
| `W001` | 0 | El origen ya contiene marcadores `{{` o `{%` | Revisa si el origen es realmente el Word sin adaptar. |

## Lista de verificación final

- [ ] `validate` sale con `0` (los avisos de V07 están justificados en `nombres_heredados`).
- [ ] `debe_desaparecer` incluye los datos reales del Word de origen.
- [ ] Conectores necesarios (cálculos `endpoint`) anotados para darlos de alta en DocAI.
- [ ] Comando de `import` entregado en dry-run; nada subido sin permiso del usuario.
- [ ] Sin secretos en ningún fichero.
