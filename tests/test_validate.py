"""validate detecta y acumula fallos (no se detiene en el primero)."""

from __future__ import annotations

import json

from conftest import campo
from docai_kit import cli
from docai_kit.build import build
from docai_kit.docx_io import Paquete
from docai_kit.validate import validar


def _estados(informe):
    return {c.codigo: c.estado for c in informe.comprobaciones}


def test_kit_limpio(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)], debe_desaparecer=["ACME"])
    kit.yaml("datos_ejemplo.yaml", {"empresa": "Fastex"})
    build(kit.raiz, kit.slug)
    informe = validar(kit.raiz, kit.slug)
    assert informe.ok, informe.como_dict()["fallos"]
    assert _estados(informe)["V12"] in ("skipped", "passed")


def test_acumula_varios_fallos(kit):
    kit.inventario([campo("Empresa", "ACME", esperadas=9)], debe_desaparecer=["Opcional A"])
    build(kit.raiz, kit.slug)
    campos = json.loads((kit.componentes / "fields.json").read_text())
    campos.append(dict(campos[0], field_id="FLD-0099", name="fantasma", options_source="no_existe"))
    (kit.componentes / "fields.json").write_text(json.dumps(campos))
    informe = validar(kit.raiz, kit.slug, strict=True)
    estados = _estados(informe)
    for codigo in ("V02", "V03", "V06", "V07", "V09", "V11"):
        assert estados[codigo] == "failed", codigo
    assert estados["V10"] == "skipped"


def test_marcador_partido_V05(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    kit.yaml("datos_ejemplo.yaml", {"empresa": "x"})
    build(kit.raiz, kit.slug)
    ruta = kit.componentes / "plantilla.docx"
    paquete = Paquete.abrir(ruta)
    xml = paquete.datos("word/document.xml").replace(
        b"Cierre {{ empresa }}", b"Cierre {{ emp</w:t></w:r><w:r><w:t>resa }}"
    )
    paquete.reemplazar("word/document.xml", xml)
    ruta.write_bytes(paquete.a_bytes())
    estados = _estados(validar(kit.raiz, kit.slug))
    assert estados["V05"] == "failed" and estados["V11"] == "failed"


def test_cli_json(kit, capsys):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    build(kit.raiz, kit.slug)
    code = cli.main(["validate", kit.slug, "--raiz", str(kit.raiz), "--json"])
    informe = json.loads(capsys.readouterr().out)
    assert code == 1 and informe["comando"] == "validate"
    fallo = informe["fallos"][0]
    assert set(fallo) == {"codigo", "severidad", "mensaje", "ubicacion"}
