"""extract: localizadores, estilos, capítulos y runs."""

from __future__ import annotations

import json

from docai_kit.extract import extract


def test_documento_json(kit):
    salida, doc, avisos = extract(kit.raiz, kit.slug)
    assert salida == kit.raiz / "trabajo" / kit.slug / "documento.json"
    assert json.loads(salida.read_text()) == doc and avisos == []
    por_id = {p["id"]: p for p in doc["parrafos"]}
    assert list(por_id)[:3] == ["document/p/0000", "document/p/0001", "document/p/0002"]
    assert por_id["document/p/0001"]["heading_level"] == 1
    assert por_id["document/p/0006"]["heading_level"] == 2
    assert por_id["document/p/0000"]["chapter"] is None
    assert por_id["document/p/0006"]["chapter"] == "Capítulo Uno"
    assert por_id["document/p/0008/txbx/00/p/00"]["text"] == "Caja: ACME"
    assert por_id["document/tbl/01/r/00/c/01/tbl/00/r/00/c/00/p/00"]["text"] == "Anidada ACME"
    assert por_id["header1/p/0000"]["chapter"] is None
    runs = por_id["document/p/0002"]["runs"]
    assert [r["text"] for r in runs] == ["Cliente: AC", "ME", " S.L. y nada más"]
    assert runs[0]["rPr_hash"] == runs[2]["rPr_hash"] != runs[1]["rPr_hash"]
    assert list(doc["parrafos"][0]) == ["id", "style", "heading_level", "text", "runs", "chapter"]
