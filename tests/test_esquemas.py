"""Los ejemplos canónicos validan contra su esquema (si no, el esquema está mal)."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from conftest import RAIZ
from docai_kit import serialize

EJEMPLOS = {
    "fields": ["sample_fields.json", "sample_section_fields.json"],
    "datasets": ["sample_dataset.json", "sample_section_datasets.json"],
    "calculations": ["sample_calculations.json", "sample_section_calculations.json"],
    "prompts": ["sample_prompts.json", "sample_section_prompts.json"],
}


@pytest.mark.parametrize(
    "nombre", sorted(p.stem.split(".")[0] for p in (RAIZ / "schemas").glob("*.json"))
)
def test_esquema_bien_formado(nombre):
    Draft202012Validator.check_schema(serialize.cargar_esquema(nombre))


@pytest.mark.parametrize(("esquema", "fichero"), [(e, f) for e, fs in EJEMPLOS.items() for f in fs])
def test_ejemplo_valida(esquema, fichero):
    datos = json.loads((RAIZ / "ejemplos" / fichero).read_text(encoding="utf-8"))
    errores = list(Draft202012Validator(serialize.cargar_esquema(esquema)).iter_errors(datos))
    assert errores == [], [e.message for e in errores]


@pytest.mark.parametrize(("esquema", "fichero"), [(e, f) for e, fs in EJEMPLOS.items() for f in fs])
def test_canonicalizar_un_ejemplo_no_cambia_su_orden_de_claves(esquema, fichero):
    datos = json.loads((RAIZ / "ejemplos" / fichero).read_text(encoding="utf-8"))
    assert json.dumps(serialize.ordenar(datos, serialize.cargar_esquema(esquema))) == json.dumps(
        datos
    )


def test_reglas_del_servidor_en_el_esquema():
    campos = Draft202012Validator(serialize.cargar_esquema("fields"))
    assert not campos.is_valid([{"name": "x", "type": "desconocido"}])
    assert not campos.is_valid([{"name": "x", "value_origin": "endpoint"}])
    assert not campos.is_valid([{"name": "x", "clave_inventada": 1}])
    calculos = Draft202012Validator(serialize.cargar_esquema("calculations"))
    assert not calculos.is_valid(
        [{"key": "a", "name": "a", "calc_type": "formula", "spec": {"expression": " "}}]
    )
    assert not calculos.is_valid([{"key": "a", "name": "a", "calc_type": "endpoint", "spec": {}}])
    assert not calculos.is_valid(
        [{"key": "a", "name": "a", "calc_type": "pipeline", "spec": {"steps": []}}]
    )
    assert calculos.is_valid([{"key": "a", "name": "a", "calc_type": "code", "spec": {"libre": 1}}])


def test_orden_por_esquema_y_mapas_libres_en_orden_de_origen():
    esquema = serialize.cargar_esquema("fields")
    campo = {
        "calculated": False,
        "name": "x",
        "calculation_binding": {"input_map": {"z": "a", "b": "c"}, "calculation_key": "k"},
        "field_id": "FLD-0001",
    }
    ordenado = serialize.ordenar([campo], esquema)[0]
    assert list(ordenado) == ["field_id", "name", "calculation_binding", "calculated"]
    assert list(ordenado["calculation_binding"]) == ["calculation_key", "input_map"]
    assert list(ordenado["calculation_binding"]["input_map"]) == ["z", "b"]
