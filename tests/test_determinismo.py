"""build x2 produce los mismos bytes, también con PYTHONHASHSEED distinto."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile

from conftest import RAIZ, campo
from docai_kit.build import build, huellas
from docai_kit.docx_io import FECHA_ZIP, Paquete


def _sha_dir(directorio) -> dict:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directorio.iterdir())
    }


def test_build_dos_veces(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    primero = huellas(build(kit.raiz, kit.slug).ficheros)
    segundo = huellas(build(kit.raiz, kit.slug).ficheros)
    assert primero == segundo == _sha_dir(kit.componentes)


def test_build_con_pythonhashseed_distinto(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9), campo("nif", "B12345678")])
    resultados = []
    for semilla in ("1", "4242"):
        entorno = dict(os.environ, PYTHONHASHSEED=semilla)
        subprocess.run(
            [sys.executable, "-m", "docai_kit.cli", "build", kit.slug, "--raiz", str(kit.raiz)],
            check=True,
            env=entorno,
            cwd=RAIZ,
            capture_output=True,
        )
        resultados.append(_sha_dir(kit.componentes))
    assert resultados[0] == resultados[1]


def test_zip_estable(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    build(kit.raiz, kit.slug)
    destino = kit.componentes / "plantilla.docx"
    origen = kit.fuente / "origen.docx"
    with zipfile.ZipFile(destino) as zd, zipfile.ZipFile(origen) as zo:
        assert [i.filename for i in zd.infolist()] == [i.filename for i in zo.infolist()]
        assert all(i.date_time == FECHA_ZIP for i in zd.infolist())
        assert [i.compress_type for i in zd.infolist()] == [i.compress_type for i in zo.infolist()]
        # Partes no tocadas, byte a byte (core.xml conserva sus fechas).
        for nombre in ("docProps/core.xml", "word/styles.xml", "[Content_Types].xml"):
            assert zd.read(nombre) == zo.read(nombre)


def test_reempaquetar_sin_cambios_es_idempotente(kit):
    datos = (kit.fuente / "origen.docx").read_bytes()
    assert Paquete.abrir(datos).a_bytes() == datos
