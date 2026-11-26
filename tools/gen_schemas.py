"""Genera schemas/{fields,datasets,calculations,prompts}.schema.json desde los modelos de DocAI.

Fuente de verdad (repo `factoria-proyectos`, carpeta `backend/`):

- ``app/models.py``: ``FieldConfig``, ``CalculationBinding``, ``TemplateDatasetCreate``,
  ``DatasetRow``, ``CalculationCreate``, ``AIPromptCreate`` (tipos, longitudes, Literals).
- ``app/fields/config.py``: ``_KNOWN_TYPES`` y ``_CALC_BACKED_ORIGINS`` (reglas del import de campos).
- ``app/calculations/spec_validation.py``: ``_VALIDATORS`` (forma de ``spec`` por ``calc_type``).

Sobre el JSON Schema que emite Pydantic se aplican, de forma explícita, las reglas que el servidor
valida en código y que las guías de ``docs/`` documentan: ``additionalProperties: false`` (salvo
mapas libres), tipos de campo conocidos, binding obligatorio en orígenes calc-backed, forma de
``options``/``inputs``/``input_map`` y ``spec`` por ``calc_type``. El orden de ``properties`` sigue el
de las muestras canónicas (``ejemplos/sample_*.json``), que es el orden en que el kit escribe.

No forma parte del pipeline: lo ejecuta ``tools/sync-from-docai.sh`` con un entorno efímero:

    uv run --no-project --python 3.12 --with 'sqlmodel>=0.0.21,<1' \\
        --with 'email-validator>=2.1.0.post1,<3' \\
        python tools/gen_schemas.py --backend ../factoria-proyectos/backend --out schemas
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def _cargar_modulo(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _limpiar(nodo, es_mapa_de_propiedades: bool = False):
    """Quita ``title`` (ruido de Pydantic) y cierra los objetos con propiedades."""
    if isinstance(nodo, dict):
        if not es_mapa_de_propiedades:
            nodo.pop("title", None)
        for k, v in nodo.items():
            _limpiar(v, k == "properties" and not es_mapa_de_propiedades)
        if "properties" in nodo and "additionalProperties" not in nodo:
            nodo["additionalProperties"] = False
    elif isinstance(nodo, list):
        for v in nodo:
            _limpiar(v)
    return nodo


def _ordenar_props(esquema: dict, orden: list[str]) -> None:
    props = esquema["properties"]
    faltan = [k for k in orden if k not in props]
    if faltan:
        raise SystemExit(f"la muestra usa claves que el modelo no tiene: {faltan}")
    esquema["properties"] = {k: props[k] for k in orden} | {
        k: v for k, v in props.items() if k not in orden
    }


def _orden_muestra(nombre: str) -> list[str]:
    datos = json.loads((KIT / "ejemplos" / nombre).read_text(encoding="utf-8"))
    primero = datos[0] if isinstance(datos, list) else datos
    return list(primero)


def _nullable(esquema: dict) -> dict:
    return {"anyOf": [esquema, {"type": "null"}]}


def _cabecera(id_: str, titulo: str, fuente: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": id_,
        "title": titulo,
        "$comment": f"GENERADO por tools/gen_schemas.py desde {fuente}. No editar a mano.",
    }


OPCION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["value"],
    "properties": {"value": {"type": "string"}, "label": {"type": ["string", "null"]}},
}

ENTRADA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string"},
        "required": {"type": "boolean"},
    },
}


def esquema_fields(models, config) -> dict:
    campo = _limpiar(models.FieldConfig.model_json_schema(mode="validation"))
    defs = campo.pop("$defs")
    binding = defs["CalculationBinding"]
    binding["properties"]["input_map"] = _nullable(
        {"type": "object", "additionalProperties": {"type": "string"}}
    )
    props = campo["properties"]
    props["type"] = _nullable({"enum": sorted(config._KNOWN_TYPES)})
    props["options"] = _nullable({"type": "array", "items": OPCION})
    props["calculation_binding"] = _nullable({"$ref": "#/$defs/calculation_binding"})
    _ordenar_props(campo, _orden_muestra("sample_fields.json"))
    campo["allOf"] = [
        {
            "if": {
                "required": ["value_origin"],
                "properties": {"value_origin": {"enum": sorted(config._CALC_BACKED_ORIGINS)}},
            },
            "then": {
                "required": ["calculation_binding"],
                "properties": {
                    "calculation_binding": {
                        "type": "object",
                        "required": ["calculation_key"],
                        "properties": {"calculation_key": {"type": "string", "minLength": 1}},
                    }
                },
            },
        }
    ]
    raiz = _cabecera(
        "fields.schema.json",
        "fields.json — array de FieldConfig (PUT /templates/{id}/fields/import)",
        "app/models.py:FieldConfig + app/fields/config.py",
    )
    raiz |= {"type": "array", "items": {"$ref": "#/$defs/field_config"}}
    raiz["$defs"] = {"field_config": campo, "calculation_binding": binding}
    return raiz


def esquema_datasets(models) -> dict:
    ds = _limpiar(models.TemplateDatasetCreate.model_json_schema(mode="validation"))
    defs = ds.pop("$defs")
    fila = defs["DatasetRow"]
    ds["properties"]["rows"]["items"] = {"$ref": "#/$defs/dataset_row"}
    ds["properties"]["rows"].pop("default", None)
    _ordenar_props(ds, _orden_muestra("sample_dataset.json"))
    raiz = _cabecera(
        "datasets.schema.json",
        "datasets.json — un dataset o un array de datasets (POST /datasets/import)",
        "app/models.py:TemplateDatasetCreate",
    )
    raiz |= {
        "anyOf": [
            {"$ref": "#/$defs/dataset"},
            {"type": "array", "items": {"$ref": "#/$defs/dataset"}},
        ]
    }
    raiz["$defs"] = {"dataset": ds, "dataset_row": fila}
    return raiz


def esquema_calculations(models, spec_validation) -> dict:
    calc = _limpiar(models.CalculationCreate.model_json_schema(mode="validation"))
    calc.pop("$defs", None)
    props = calc["properties"]
    props["inputs"] = {"type": "array", "items": ENTRADA}
    props["validation"] = _nullable({"type": "object"})
    # spec: unión de todas las claves conocidas (para fijar el orden) + forma estricta por tipo.
    union: dict = {}
    defs: dict = {}
    reglas = []
    for calc_type, modelo in spec_validation._VALIDATORS.items():
        sub = _limpiar(modelo.model_json_schema(mode="validation"))
        sub.pop("$defs", None)
        if calc_type == "formula":
            # _FormulaSpec._check: expression no vacía.
            sub["properties"]["expression"]["pattern"] = "\\S"
        if calc_type == "pipeline":
            # _PipelineSpec._check: >= 1 paso; cada paso con `type` permitido.
            sub["properties"]["steps"] = {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {"enum": ["dataset_lookup", "formula", "ai_generation", "endpoint"]}
                    },
                },
            }
        for k, v in sub["properties"].items():
            union.setdefault(k, copy.deepcopy(v))
        defs[f"spec_{calc_type}"] = sub
        regla = {
            "if": {"required": ["calc_type"], "properties": {"calc_type": {"const": calc_type}}},
            "then": {"properties": {"spec": {"$ref": f"#/$defs/spec_{calc_type}"}}},
        }
        if sub.get("required"):
            regla["then"]["required"] = ["spec"]
        reglas.append(regla)
    # `code`: borrador con spec libre (CALCULATIONS_FILE_GUIDE §4.6).
    props["spec"] = {"type": "object", "properties": union, "additionalProperties": True}
    props["spec"].pop("default", None)
    calc["allOf"] = reglas
    _ordenar_props(calc, _orden_muestra("sample_calculations.json"))
    raiz = _cabecera(
        "calculations.schema.json",
        "calculations.json — array de CalculationCreate (POST /templates/{id}/calculations/import)",
        "app/models.py:CalculationCreate + app/calculations/spec_validation.py",
    )
    raiz |= {"type": "array", "items": {"$ref": "#/$defs/calculation"}}
    raiz["$defs"] = {"calculation": calc} | defs
    return raiz


def esquema_prompts(models) -> dict:
    prompt = _limpiar(models.AIPromptCreate.model_json_schema(mode="validation"))
    prompt.pop("$defs", None)
    _ordenar_props(prompt, _orden_muestra("sample_prompts.json"))
    raiz = _cabecera(
        "prompts.schema.json",
        "prompts.json — array de AIPromptCreate (POST /templates/{id}/prompts/import)",
        "app/models.py:AIPromptCreate",
    )
    raiz |= {"type": "array", "items": {"$ref": "#/$defs/prompt"}}
    raiz["$defs"] = {"prompt": prompt}
    return raiz


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", required=True, type=Path, help="factoria-proyectos/backend")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    sys.path.insert(0, str(args.backend.resolve()))
    import app.models as models  # noqa: PLC0415

    config = _cargar_modulo("_docai_fields_config", args.backend / "app/fields/config.py")
    spec_validation = _cargar_modulo(
        "_docai_spec_validation", args.backend / "app/calculations/spec_validation.py"
    )
    salidas = {
        "fields": esquema_fields(models, config),
        "datasets": esquema_datasets(models),
        "calculations": esquema_calculations(models, spec_validation),
        "prompts": esquema_prompts(models),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    for nombre, esquema in salidas.items():
        texto = json.dumps(esquema, ensure_ascii=False, indent=2) + "\n"
        (args.out / f"{nombre}.schema.json").write_text(texto, encoding="utf-8")
        print(f"  + {nombre}.schema.json")


if __name__ == "__main__":
    main()
