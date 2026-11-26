from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from docai_kit import serialize
from docai_kit.docx_io import sha256_fichero

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Kit:
    """Raíz temporal de un kit con una plantilla ``slug``."""

    def __init__(self, raiz: Path, slug: str = "demo"):
        self.raiz = raiz
        self.slug = slug
        self.fuente = raiz / "plantillas" / slug
        self.fuente.mkdir(parents=True, exist_ok=True)

    @property
    def componentes(self) -> Path:
        return self.raiz / "componentes" / self.slug

    def origen(self, fixture: str = "basico.docx") -> str:
        shutil.copyfile(FIXTURES / fixture, self.fuente / "origen.docx")
        return sha256_fichero(self.fuente / "origen.docx")

    def inventario(self, campos: list[dict], **extra) -> dict:
        inv = {
            "version": 1,
            "slug": self.slug,
            "origen_sha256": sha256_fichero(self.fuente / "origen.docx"),
            **extra,
            "campos": campos,
        }
        serialize.escribir_yaml(self.fuente / "inventario.yaml", inv)
        return inv

    def yaml(self, nombre: str, valor) -> None:
        serialize.escribir_yaml(self.fuente / nombre, valor)


@pytest.fixture
def kit(tmp_path: Path) -> Kit:
    k = Kit(tmp_path)
    k.origen()
    return k


def campo(nombre: str, buscar: str, esperadas: int = 1, tipo: str = "text", **extra) -> dict:
    oc = {"buscar": buscar, "esperadas": esperadas}
    for clave in ("en", "parte", "regex"):
        if clave in extra:
            oc[clave] = extra.pop(clave)
    return {"nombre": nombre, "tipo": tipo, **extra, "ocurrencias": [oc]}
