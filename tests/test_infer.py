"""infer sobre fixtures: pares limpios, ámbitos mínimos y diferencias no explicables."""

from __future__ import annotations

from conftest import FIXTURES, Kit, campo
from docai_kit.build import build
from docai_kit.docx_io import Paquete
from docai_kit.infer import diferencias_parrafo, inferir


def test_pares_contiguos_y_residuo():
    pares, residuo = diferencias_parrafo("Plazo [n] [uds], fin", "Plazo {{ n }} {{ uds }}, fin")
    assert pares == [("n", 6, 9), ("uds", 10, 15)] and residuo == []
    pares, residuo = diferencias_parrafo("Hola Pepe, adiós", "Hola {{ nombre }}, ADIÓS")
    assert pares == [("nombre", 5, 9)]
    assert residuo and residuo[0]["plantilla"] == "ADIÓS"


def test_ida_y_vuelta_build_infer(tmp_path):
    """build(inventario) -> plantilla; infer(origen, plantilla) -> inventario equivalente."""
    k = Kit(tmp_path)
    k.origen()
    k.inventario(
        [
            campo("empresa", "ACME", esperadas=9),
            campo("nif", "B12345678"),
            # "Opcional" aparece dos veces; solo se sustituye la de p/0009 -> infer debe acotar.
            campo("opcion", "Opcional", en="document/p/0009"),
        ]
    )
    build(k.raiz, k.slug)
    inventario, lock, informe = inferir(
        k.fuente / "origen.docx", k.componentes / "plantilla.docx", k.slug
    )
    assert informe.vacio() and lock is None
    por_nombre = {c["nombre"]: c["ocurrencias"] for c in inventario["campos"]}
    assert por_nombre["empresa"] == [{"buscar": "ACME", "esperadas": 9}]
    assert por_nombre["opcion"] == [{"buscar": "Opcional", "esperadas": 1, "en": "document/p/0009"}]


def test_texto_reformateado_se_informa(tmp_path):
    plantilla = tmp_path / "p.docx"
    paquete = Paquete.abrir(FIXTURES / "basico.docx")
    xml = paquete.datos("word/document.xml").replace(
        b"Cierre ACME", b"Cierre {{ empresa }} (nuevo)"
    )
    paquete.reemplazar("word/document.xml", xml)
    plantilla.write_bytes(paquete.a_bytes())
    _, _, informe = inferir(FIXTURES / "basico.docx", plantilla, "x")
    assert [d["plantilla"] for d in informe.no_explicables] == [" (nuevo)"]
