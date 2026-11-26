# ejemplos/ — Muestras importables de referencia

Estos ficheros son la **referencia canónica** y se importan **verbatim** en DocAI (verificados en
producción). Úsalos como molde: cópialos a `../componentes/<tipo>/` y adáptalos a tu plantilla.

| Fichero | Qué demuestra | Guía |
|---|---|---|
| `sample_template.docx` | Plantilla de referencia con **todos** los tipos de campo y operaciones (texto, número, fecha, dataset+cascada, imagen, coordenada, tabla repetible, booleano, calculado; aritmética, comparaciones, condicionales, bucles). | `../docs/TEMPLATE_AUTHORING_GUIDE.md` |
| `sample_dataset.json` | Dataset con **cascada** provincia→municipio (`parent`). | `../docs/DATASETS_FILE_GUIDE.md` |
| `sample_calculations.json` | Cálculo `formula` (IVA) y `endpoint` (tarifa por conector). | `../docs/CALCULATIONS_FILE_GUIDE.md` |
| `sample_prompts.json` | Prompts `improve`, `field` y `calculation`. | `../docs/AI_PROMPTS_FILE_GUIDE.md` |
| `sample_fields.json` | Dos campos: uno `manual` y uno calculado con `calculation_binding`. | `../docs/FIELDS_FILE_GUIDE.md` |
| `sample_data.json` | Valores de ejemplo para **probar el render** de `sample_template.docx` (no se importa; es entrada de formulario). | — |

## Probar la plantilla de ejemplo (opcional)

Sirve para entender cómo se ve un resultado correcto antes de adaptar el tuyo: en una instancia DocAI,
crea una plantilla a partir de `sample_template.docx`, importa los `sample_*.json` y rellena el formulario
usando `sample_data.json` como referencia. Deberías ver desplegables en cascada, tabla repetible de
módulos, cláusula condicional y campos calculados.

> Estos ficheros son estáticos y **no contienen secretos**. El de `endpoint` referencia un conector
> (`precios_energia`) que tendrías que dar de alta en DocAI para que ese cálculo resuelva.
