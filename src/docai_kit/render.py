"""Render local con docxtpl (revisión humana y validaciones V08–V10, V12).

El ``.docx`` resultante se empaqueta con el escritor byte-estable de ``docx_io`` (python-docx, al
guardar, sellaría cada entrada del ZIP con la hora actual).
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from docxtpl import DocxTemplate

from . import serialize
from .docx_io import MC_FALLBACK, W_P, Paquete, calcular_tramos, partes_texto, tiene_ancestro
from .errors import KitError


def render_bytes(plantilla: bytes, contexto: dict) -> bytes:
    tpl = DocxTemplate(io.BytesIO(plantilla))
    tpl.render(contexto, autoescape=True)
    paquete = Paquete.abrir(plantilla)
    nombres = set(paquete.nombres())
    blobs: dict[str, bytes] = {}
    for parte in tpl.docx.part.package.iter_parts():
        nombre = str(parte.partname).lstrip("/")
        if nombre not in nombres:
            raise KitError.de("E012", f"el render ha añadido la parte {nombre}; no soportado")
        blobs[nombre] = parte.blob
    # Solo se sustituyen las partes que docxtpl reescribe; el resto queda byte a byte.
    reescritas = {nombre for _, nombre in partes_texto(paquete)} | {"docProps/core.xml"}
    for nombre in paquete.nombres():
        if nombre in reescritas and nombre in blobs:
            paquete.reemplazar(nombre, blobs[nombre])
    return paquete.a_bytes()


def textos(docx: bytes, incluir_fallback: bool = True) -> list[str]:
    """Texto de cada párrafo de todas las partes (por defecto, también las copias mc:Fallback)."""
    paquete = Paquete.abrir(docx)
    salida = []
    for _, nombre in partes_texto(paquete):
        raiz = paquete.xml(nombre)
        for p in raiz.iter(W_P):
            if not incluir_fallback and tiene_ancestro(p, raiz, {MC_FALLBACK}):
                continue
            salida.append("".join(t.t.text or "" for t in calcular_tramos(p)))
    return salida


def a_pdf(docx: Path, destino: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise KitError.de("E050", "no se encuentra `soffice` en el PATH")
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(docx)],
            capture_output=True,
            text=True,
            check=False,
        )
        pdf = Path(tmp) / (docx.stem + ".pdf")
        if proc.returncode != 0 or not pdf.is_file():
            raise KitError.de(
                "E050", f"soffice salió con {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        serialize.escribir_bytes(destino, pdf.read_bytes())
    return destino


def soffice_disponible() -> bool:
    return (shutil.which("soffice") or shutil.which("libreoffice")) is not None
