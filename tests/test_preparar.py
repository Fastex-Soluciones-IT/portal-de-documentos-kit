"""``preparar``: tokens ⟦hNNN⟧ en celdas vacías, casillas y controles con marcador."""

from __future__ import annotations

import io
import json
import zipfile

from fixtures import formulario

from conftest import campo
from docai_kit.build import build
from docai_kit.cli import main
from docai_kit.docx_io import Paquete, recorrer
from docai_kit.extract import leer_origen
from docai_kit.preparar import TOKEN, preparar


def _por_tipo(huecos, tipo):
    return [h for h in huecos if h.tipo == tipo]


def _xml_documento(datos: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def _textos(datos: bytes) -> list[tuple[str, str]]:
    return [(p.id, p.texto) for p in recorrer(Paquete.abrir(datos))]


def test_celdas_vacias_reciben_token_con_etiqueta():
    celdas = _por_tipo(preparar(formulario.formulario()).huecos, "celda")
    assert [(h.etiqueta, h.cabecera, h.original) for h in celdas] == [
        ("Inversores", "Modelo", ""),
        ("Inversores", "Nº", ""),
        ("Titular", None, ""),
        ("Promotor", None, ""),
    ]
    assert all(h.grupo is None and h.opcion is None for h in celdas)


def test_token_de_celda_usa_el_formato_de_la_marca_de_parrafo():
    prep = preparar(formulario.formulario())
    token = _por_tipo(prep.huecos, "celda")[0].token
    xml = _xml_documento(prep.docx)
    assert f"<w:r>{formulario.RPR_MARCA}<w:t>{token}</w:t></w:r>" in xml


def test_vmerge_de_continuacion_no_es_hueco():
    huecos = preparar(formulario.formulario()).huecos
    assert not [h for h in huecos if h.parrafo.startswith("document/tbl/02/")]


def test_casillas_forman_grupo_con_opciones():
    casillas = _por_tipo(preparar(formulario.formulario()).huecos, "casilla")
    assert len(casillas) == 2
    assert {h.grupo for h in casillas} == {"G001"}
    assert [h.opcion for h in casillas] == ["CC (inversor híbrido)", "CA"]
    assert {h.etiqueta for h in casillas} == {"Acoplamiento"}
    assert {h.original for h in casillas} == {"☐"}


def test_casilla_conserva_el_formato_de_su_run():
    prep = preparar(formulario.formulario())
    token = _por_tipo(prep.huecos, "casilla")[0].token
    assert f"{formulario.RPR_CASILLA}<w:t>{token}</w:t>" in _xml_documento(prep.docx)


def test_control_con_marcador_es_hueco():
    prep = preparar(formulario.formulario())
    (control,) = _por_tipo(prep.huecos, "control")
    assert control.original == ""
    assert control.etiqueta == "Observaciones"
    xml = _xml_documento(prep.docx)
    assert "Escribir aquí" not in xml
    assert f"<w:r><w:rPr><w:b/></w:rPr><w:t>{control.token}</w:t></w:r>" in xml


def test_quita_controles_y_marcas_de_ortografia():
    xml = _xml_documento(preparar(formulario.formulario()).docx)
    assert "w:sdt" not in xml
    assert "w:proofErr" not in xml


def test_tokens_numerados_en_orden_de_documento():
    huecos = preparar(formulario.formulario()).huecos
    assert [h.token for h in huecos] == [f"⟦h{n:03d}⟧" for n in range(1, 8)]
    assert all(TOKEN.fullmatch(h.token) for h in huecos)


def test_ids_coinciden_con_extract(tmp_path):
    prep = preparar(formulario.formulario())
    ruta = tmp_path / "origen.docx"
    ruta.write_bytes(prep.docx)
    _, parrafos = leer_origen(ruta)
    por_id = {p.id: p for p in parrafos}
    for h in prep.huecos:
        assert h.token in por_id[h.parrafo].texto
        # Cada token ocupa un w:t entero, como espera ``build`` al restaurarlo.
        assert h.token in [tr.t.text for tr in por_id[h.parrafo].tramos]


def test_determinista():
    a = preparar(formulario.formulario())
    b = preparar(formulario.formulario())
    assert a.docx == b.docx
    assert a.huecos == b.huecos


def test_sin_huecos_devuelve_documento_equivalente():
    origen = formulario.sin_huecos()
    prep = preparar(origen)
    assert prep.huecos == []
    assert _textos(prep.docx) == _textos(origen)


def test_cli_preparar_escribe_origen_y_huecos(tmp_path, capsys):
    fuente = tmp_path / "plantillas" / "demo"
    fuente.mkdir(parents=True)
    (fuente / "word_original.docx").write_bytes(formulario.formulario())
    assert main(["preparar", "demo", "--raiz", str(tmp_path)]) == 0
    prep = preparar(formulario.formulario())
    assert (fuente / "origen.docx").read_bytes() == prep.docx
    huecos = json.loads((tmp_path / "trabajo" / "demo" / "huecos.json").read_text("utf-8"))
    assert huecos == [h.como_dict() for h in prep.huecos]
    assert "7 huecos" in capsys.readouterr().out


def test_cuadro_de_texto_replica_los_tokens_en_su_copia_fallback(kit):
    prep = preparar(formulario.con_cuadro_de_texto())
    si, no = prep.huecos
    assert (si.tipo, si.opcion, no.opcion, si.etiqueta) == ("casilla", "Sí", "No", "Pregunta")
    assert si.parrafo == "document/p/0000/txbx/00/p/00"
    xml = _xml_documento(prep.docx)
    assert xml.count(si.token) == 2 and xml.count(no.token) == 2  # mc:Choice y mc:Fallback
    assert "☐" not in xml and "w:sdt" not in xml

    (kit.fuente / "origen.docx").write_bytes(prep.docx)
    kit.inventario(
        [campo("pregunta_si", si.token)],
        huecos=[{"token": h.token, "original": h.original} for h in prep.huecos],
    )
    build(kit.raiz, kit.slug)  # sin E011: principal y Fallback coinciden
    plantilla = _xml_documento((kit.componentes / "plantilla.docx").read_bytes())
    assert plantilla.count("{{ pregunta_si }}") == 2
    # La casilla sin campo vuelve a su original en ambas copias.
    assert plantilla.count("<w:t>☐</w:t>") == 2
    assert "⟦" not in plantilla
