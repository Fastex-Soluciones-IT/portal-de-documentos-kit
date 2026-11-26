"""``docai-kit extract``: origen.docx -> trabajo/<slug>/documento.json."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lxml import etree

from . import serialize
from .docx_io import W_RPR, Paquete, Parrafo, recorrer, revisiones, sha256_fichero
from .errors import Fallo, KitError


def rpr_hash(t: etree._Element) -> str:
    """Huella del formato del run que contiene el ``w:t`` (C14N de su ``w:rPr``)."""
    run = t.getparent()
    rpr = run.find(W_RPR) if run is not None else None
    datos = b"" if rpr is None else etree.tostring(rpr, method="c14n")
    return hashlib.sha256(datos).hexdigest()[:12]


def _runs(par: Parrafo) -> list[dict]:
    salida = []
    for tr in par.tramos:
        salida.append({"text": tr.t.text or "", "rPr_hash": rpr_hash(tr.t)})
    return salida


def leer_origen(ruta: Path) -> tuple[Paquete, list[Parrafo]]:
    """Abre un .docx, rechaza el control de cambios (E010) y devuelve sus párrafos."""
    if not ruta.is_file():
        raise KitError.de("E009", "no existe el fichero", str(ruta))
    paquete = Paquete.abrir(ruta)
    marcas = revisiones(paquete)
    if marcas:
        listado = ", ".join(marcas[:5]) + (f" (+{len(marcas) - 5} más)" if len(marcas) > 5 else "")
        raise KitError.de(
            "E010", f"{len(marcas)} marca(s) de control de cambios: {listado}", str(ruta)
        )
    return paquete, recorrer(paquete)


def documento(ruta: Path, slug: str) -> tuple[dict, list[Fallo]]:
    _, parrafos = leer_origen(ruta)
    avisos = []
    con_marcadores = [p.id for p in parrafos if "{{" in p.texto or "{%" in p.texto]
    if con_marcadores:
        avisos.append(
            Fallo(
                "W001",
                f"{len(con_marcadores)} párrafo(s) ya contienen '{{{{' o '{{%'",
                ", ".join(con_marcadores[:10]),
                "aviso",
            )
        )
    doc = {
        "version": 1,
        "slug": slug,
        "origen_sha256": sha256_fichero(ruta),
        "avisos": [a.como_dict() for a in avisos],
        "parrafos": [
            {
                "id": p.id,
                "style": p.estilo,
                "heading_level": p.nivel,
                "text": p.texto,
                "runs": _runs(p),
                "chapter": p.capitulo,
            }
            for p in parrafos
        ],
    }
    return doc, avisos


def extract(raiz: Path, slug: str) -> tuple[Path, dict, list[Fallo]]:
    origen = raiz / "plantillas" / slug / "origen.docx"
    doc, avisos = documento(origen, slug)
    salida = raiz / "trabajo" / slug / "documento.json"
    serialize.escribir_json(salida, doc, serialize.cargar_esquema("documento"))
    return salida, doc, avisos
