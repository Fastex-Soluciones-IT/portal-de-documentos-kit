"""Algoritmo de sustitución a nivel de runs."""

from __future__ import annotations

import io
import json

import pytest
from docxtpl import DocxTemplate

from conftest import campo
from docai_kit.build import build
from docai_kit.docx_io import W_R, W_RPR, W_T, Paquete, qn, recorrer
from docai_kit.errors import KitError
from docai_kit.render import render_bytes, textos


def _parrafos(kit):
    paquete = Paquete.abrir(kit.componentes / "plantilla.docx")
    return paquete, {p.id: p for p in recorrer(paquete)}


def _runs(par):
    salida = []
    for run in par.elem.iter(W_R):
        rpr = run.find(W_RPR)
        salida.append(
            ("".join(t.text or "" for t in run.iter(W_T)), None if rpr is None else len(rpr))
        )
    return salida


def test_marcador_en_un_solo_run(kit):
    kit.inventario([campo("empresa", "ACME S.L.", en="document/p/0000")])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    assert pars["document/p/0000"].texto == "Portada de {{ empresa }}"
    assert len(_runs(pars["document/p/0000"])) == 1


def test_marcador_cruza_tres_runs_y_el_del_medio_tiene_otro_formato(kit):
    kit.inventario([campo("cliente", "ACME S.L.", en="document/p/0002")])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    par = pars["document/p/0002"]
    assert par.texto == "Cliente: {{ cliente }} y nada más"
    runs = _runs(par)
    # El marcador entero vive en el primer run (sin negrita); el de negrita queda vacío y se elimina.
    assert runs == [("Cliente: {{ cliente }}", None), (" y nada más", None)]


def test_marcador_cruza_n_runs(kit):
    kit.inventario([campo("nif", "B12345678")])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    assert _runs(pars["document/p/0003"]) == [("Ref: ", None), ("{{ nif }}", None)]


def test_marcador_conserva_el_rpr_del_primer_run(kit):
    kit.inventario([campo("x", "ME S.L", en="document/p/0002")])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    par = pars["document/p/0002"]
    negrita = [run for run in par.elem.iter(W_R) if run.find(W_RPR) is not None]
    assert ["".join(t.text for t in r.iter(W_T)) for r in negrita] == ["{{ x }}"]
    assert par.texto == "Cliente: AC{{ x }}. y nada más"


def test_texto_en_hipervinculo(kit):
    kit.inventario([campo("web", "ACME", en="document/p/0005")])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    par = pars["document/p/0005"]
    enlace = par.elem.find(qn("w:hyperlink"))
    assert "".join(t.text for t in enlace.iter(W_T)) == "{{ web }}"
    assert par.texto == "Web: {{ web }} fin"


def test_cruzar_limite_de_hipervinculo_es_E008(kit):
    kit.inventario([campo("web", "Web: ACME", en="document/p/0005")])
    with pytest.raises(KitError) as exc:
        build(kit.raiz, kit.slug)
    assert [f.codigo for f in exc.value.fallos] == ["E008"]


def test_cruzar_un_tabulador_es_E008(kit):
    kit.inventario([campo("saludo", "HolaMundo")])
    with pytest.raises(KitError) as exc:
        build(kit.raiz, kit.slug)
    assert exc.value.fallos[0].codigo == "E008"
    assert "tab" in exc.value.fallos[0].mensaje


def test_celda_cabecera_pie_cuadro_de_texto_y_tabla_anidada(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    build(kit.raiz, kit.slug)
    _, pars = _parrafos(kit)
    for pid in (
        "document/tbl/01/r/00/c/00/p/00",
        "document/tbl/01/r/00/c/01/tbl/00/r/00/c/00/p/00",
        "header1/p/0000",
        "footer1/p/0000",
        "document/p/0008/txbx/00/p/00",
    ):
        assert "{{ empresa }}" in pars[pid].texto, pid
    # La copia mc:Fallback del cuadro de texto recibe la misma sustitución.
    todos = textos((kit.componentes / "plantilla.docx").read_bytes())
    assert todos.count("Caja: {{ empresa }}") == 2
    assert not any("ACME" in t for t in todos)


def test_variables_y_render(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9), campo("nif", "B12345678")])
    build(kit.raiz, kit.slug)
    datos = (kit.componentes / "plantilla.docx").read_bytes()
    assert DocxTemplate(io.BytesIO(datos)).get_undeclared_template_variables() == {"empresa", "nif"}
    salida = textos(render_bytes(datos, {"empresa": "Fastex", "nif": "X1"}))
    assert "Cabecera Fastex" in salida and "Ref: X1" in salida and "Caja: Fastex" in salida
    campos = json.loads((kit.componentes / "fields.json").read_text())
    assert [c["name"] for c in campos] == ["empresa", "nif"]
