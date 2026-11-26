"""Huecos restaurables (tokens ⟦hNNN⟧ no usados) y campos usados solo por fórmulas."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from docx import Document

from conftest import campo
from docai_kit.build import build
from docai_kit.errors import KitError
from docai_kit.render import textos
from docai_kit.validate import validar

H1, H2, H3 = "⟦h001⟧", "⟦h002⟧", "⟦h003⟧"
HUECOS = [
    {"token": H1, "original": ""},
    {"token": H2, "original": "☐"},
    {"token": H3, "original": "☐"},
]


def _origen(kit) -> None:
    doc = Document()
    tabla = doc.add_table(rows=1, cols=2)
    tabla.cell(0, 0).text = "Nombre"
    tabla.cell(0, 1).text = H1
    doc.add_paragraph(f"{H2} Sí {H3} No")
    doc.save(kit.fuente / "origen.docx")


def _xml_plantilla(kit) -> str:
    datos = (kit.componentes / "plantilla.docx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def _celda_vacia(kit) -> bool:
    doc = Document(io.BytesIO((kit.componentes / "plantilla.docx").read_bytes()))
    return doc.tables[0].cell(0, 1).text == ""


def test_token_no_usado_se_restaura(kit):
    _origen(kit)
    kit.inventario([campo("nombre", H1)], huecos=HUECOS)
    build(kit.raiz, kit.slug)
    xml = _xml_plantilla(kit)
    assert "{{ nombre }}" in xml
    assert "☐ Sí ☐ No" in "".join(textos((kit.componentes / "plantilla.docx").read_bytes()))
    assert "⟦" not in xml and "⟧" not in xml


def test_celda_descartada_queda_vacia(kit):
    _origen(kit)
    kit.inventario([campo("otro", H2)], huecos=HUECOS)
    build(kit.raiz, kit.slug)
    assert _celda_vacia(kit)
    assert "⟦" not in _xml_plantilla(kit)


CAMPOS_FORMULA = [
    {
        "nombre": "linea_vida",
        "tipo": "select",
        "opciones": [{"value": "Sí"}, {"value": "No"}],
        "ocurrencias": [],
    },
    campo("linea_vida__1", H2, origen_valor="formula"),
]


def test_campo_solo_en_formula_es_valido(kit):
    _origen(kit)
    campos = [dict(c) for c in CAMPOS_FORMULA]
    campos[1]["formula"] = "'☒' if linea_vida == 'Sí' else '☐'"
    kit.inventario(campos, huecos=HUECOS)
    build(kit.raiz, kit.slug)


def test_campo_sin_ocurrencias_ni_formula_sigue_fallando(kit):
    _origen(kit)
    kit.inventario(CAMPOS_FORMULA, huecos=HUECOS)
    with pytest.raises(KitError) as exc:
        build(kit.raiz, kit.slug)
    assert any(f.codigo == "E002" and "sin ocurrencias" in f.mensaje for f in exc.value.fallos)


def _campos_formula() -> list[dict]:
    campos = [dict(c) for c in CAMPOS_FORMULA]
    campos[1]["formula"] = "'☒' if linea_vida == 'Sí' else '☐'"
    return campos


def test_validate_admite_campo_solo_en_formula(kit):
    _origen(kit)
    kit.inventario(_campos_formula(), huecos=HUECOS)
    build(kit.raiz, kit.slug)
    informe = validar(kit.raiz, kit.slug)
    v02 = next(c for c in informe.comprobaciones if c.codigo == "V02")
    assert v02.estado == "passed", informe.como_dict()["fallos"]


def test_validate_campo_sin_variable_ni_formula_falla_v02(kit):
    _origen(kit)
    kit.inventario(_campos_formula(), huecos=HUECOS)
    build(kit.raiz, kit.slug)
    ruta = kit.componentes / "fields.json"
    campos = json.loads(ruta.read_text())
    campos[1]["formula"] = None
    ruta.write_text(json.dumps(campos))
    informe = validar(kit.raiz, kit.slug)
    v02 = next(c for c in informe.comprobaciones if c.codigo == "V02")
    assert v02.estado == "failed"
    assert any("linea_vida" in f.mensaje for f in v02.fallos)
