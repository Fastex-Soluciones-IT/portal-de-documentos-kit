"""ids.lock.json: campos nuevos, renombrados y eliminados."""

from __future__ import annotations

import json

from conftest import campo
from docai_kit.build import build


def _lock(kit) -> dict:
    return json.loads((kit.fuente / "ids.lock.json").read_text())


def _ids(kit) -> dict:
    return {
        c["name"]: c["field_id"] for c in json.loads((kit.componentes / "fields.json").read_text())
    }


def test_nuevo_renombrado_y_eliminado(kit):
    kit.inventario([campo("a", "Opcional A"), campo("b", "Opcional B")])
    build(kit.raiz, kit.slug)
    assert _ids(kit) == {"a": "FLD-0001", "b": "FLD-0002"}

    # Campo nuevo: siguiente número libre.
    kit.inventario([campo("a", "Opcional A"), campo("b", "Opcional B"), campo("c", "Cierre ACME")])
    build(kit.raiz, kit.slug)
    assert _ids(kit) == {"a": "FLD-0001", "b": "FLD-0002", "c": "FLD-0003"}

    # Renombrado explícito: conserva el ID.
    kit.inventario(
        [
            campo("a", "Opcional A"),
            campo("b2", "Opcional B", renombrado_de="b"),
            campo("c", "Cierre ACME"),
        ]
    )
    build(kit.raiz, kit.slug)
    assert _ids(kit) == {"a": "FLD-0001", "b2": "FLD-0002", "c": "FLD-0003"}

    # Eliminado: su ID se retira y no se reutiliza, ni siquiera si vuelve el mismo nombre.
    kit.inventario([campo("a", "Opcional A"), campo("b2", "Opcional B")])
    build(kit.raiz, kit.slug)
    assert _lock(kit)["retirados"] == {"FLD-0003": "c"}
    kit.inventario([campo("a", "Opcional A"), campo("b2", "Opcional B"), campo("c", "Cierre ACME")])
    build(kit.raiz, kit.slug)
    assert _ids(kit)["c"] == "FLD-0004"
    assert _lock(kit)["siguiente"] == 5


def test_renombrar_sin_renombrado_de_da_id_nuevo(kit):
    kit.inventario([campo("a", "Opcional A")])
    build(kit.raiz, kit.slug)
    kit.inventario([campo("z", "Opcional A")])
    build(kit.raiz, kit.slug)
    assert _ids(kit) == {"z": "FLD-0002"}
    assert _lock(kit)["retirados"] == {"FLD-0001": "a"}
