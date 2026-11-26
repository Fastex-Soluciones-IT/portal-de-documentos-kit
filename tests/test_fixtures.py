"""Los fixtures versionados son exactamente lo que genera su script."""

from __future__ import annotations

import importlib.util

from conftest import FIXTURES


def test_regenerar_fixtures_da_los_mismos_bytes(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("generar", FIXTURES / "generar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "AQUI", tmp_path)
    modulo.main()
    generados = sorted(p.name for p in tmp_path.glob("*.docx"))
    assert generados == sorted(p.name for p in FIXTURES.glob("*.docx"))
    for nombre in generados:
        assert (tmp_path / nombre).read_bytes() == (FIXTURES / nombre).read_bytes(), nombre
