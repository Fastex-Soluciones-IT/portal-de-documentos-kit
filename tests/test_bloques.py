"""Bloques: tabla repetible y condicional."""

from __future__ import annotations

import io
import json

from docxtpl import DocxTemplate

from conftest import campo
from docai_kit.build import build
from docai_kit.render import render_bytes, textos

TABLA = {
    "tipo": "tabla_repetible",
    "lista": "inversores",
    "tabla": {"ancla": "Fabricante inversor", "parte": "document"},
    "fila_plantilla": 1,
    "columnas": [
        {"buscar": "Huawei", "atributo": "fabricante"},
        {"buscar": "SUN2000-10KTL", "atributo": "modelo"},
    ],
}
CONDICIONAL = {
    "tipo": "condicional",
    "variable": "incluir_opcionales",
    "desde": "document/p/0009",
    "hasta": "document/p/0010",
}
CAMPOS = [
    {"nombre": "inversores", "tipo": "list", "etiqueta": "Inversores", "ocurrencias": []},
    {"nombre": "incluir_opcionales", "tipo": "boolean", "ocurrencias": []},
    campo("cierre", "Cierre ACME"),
]


def _build(kit):
    kit.inventario(CAMPOS, bloques=[TABLA, CONDICIONAL])
    build(kit.raiz, kit.slug)
    return (kit.componentes / "plantilla.docx").read_bytes()


def test_variables_de_la_plantilla(kit):
    datos = _build(kit)
    variables = DocxTemplate(io.BytesIO(datos)).get_undeclared_template_variables()
    assert variables == {"inversores", "incluir_opcionales", "cierre"}


def test_tabla_repetible_renderiza_una_fila_por_item(kit):
    datos = _build(kit)
    items = [{"fabricante": "Huawei", "modelo": "A"}, {"fabricante": "SMA", "modelo": "B"}]
    salida = textos(render_bytes(datos, {"inversores": items, "incluir_opcionales": True}))
    assert salida.count("Huawei") == 1 and "SMA" in salida and "B" in salida
    assert not any("{%" in t for t in salida)
    vacia = textos(render_bytes(datos, {}))
    assert "Huawei" not in vacia and "Fabricante inversor" in vacia


def test_condicional_omite_el_rango(kit):
    datos = _build(kit)
    con = textos(render_bytes(datos, {"incluir_opcionales": True}))
    sin = textos(render_bytes(datos, {"incluir_opcionales": False}))
    assert "Opcional A" in con and "Opcional B" in con
    assert "Opcional A" not in sin and "Opcional B" not in sin and "Capítulo Dos" in sin


def test_campos_de_bloques_en_fields_json(kit):
    _build(kit)
    campos = {c["name"]: c for c in json.loads((kit.componentes / "fields.json").read_text())}
    assert campos["inversores"]["type"] == "list"
    assert campos["inversores"]["chapter"] == "Capítulo Uno"
    assert campos["incluir_opcionales"]["chapter"] == "Capítulo Dos"
    # field_order por capítulo y por posición: el condicional (p/0009) va antes que el cierre.
    assert campos["incluir_opcionales"]["field_order"] == 0 and campos["cierre"]["field_order"] == 1


def test_condicionales_anidados(kit):
    exterior = dict(CONDICIONAL, variable="ext", desde="document/p/0009", hasta="document/p/0010")
    interior = dict(CONDICIONAL, variable="int", desde="document/p/0010", hasta="document/p/0010")
    kit.inventario(
        [
            {"nombre": "ext", "tipo": "boolean", "ocurrencias": []},
            {"nombre": "int", "tipo": "boolean", "ocurrencias": []},
        ],
        bloques=[interior, exterior],
    )
    build(kit.raiz, kit.slug)
    datos = (kit.componentes / "plantilla.docx").read_bytes()
    salida = textos(render_bytes(datos, {"ext": True, "int": False}))
    assert "Opcional A" in salida and "Opcional B" not in salida
