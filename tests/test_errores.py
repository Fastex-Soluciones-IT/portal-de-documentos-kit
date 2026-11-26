"""Cada código de error del catálogo tiene un test que lo provoca."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import FIXTURES, Kit, campo
from docai_kit import cli
from docai_kit.build import build
from docai_kit.errors import CATALOGO, KitError
from docai_kit.extract import extract
from docai_kit.importer import importar
from docai_kit.infer import inferir
from docai_kit.render import a_pdf


def _codigos(exc: pytest.ExceptionInfo) -> list[str]:
    return sorted({f.codigo for f in exc.value.fallos})


def _falla(kit: Kit, codigo: str) -> KitError:
    with pytest.raises(KitError) as exc:
        build(kit.raiz, kit.slug)
    assert codigo in _codigos(exc), exc.value.fallos
    return exc.value


def test_E001_origen_cambiado(kit):
    kit.inventario([campo("x", "ACME", esperadas=9)])
    kit.origen("marcadores.docx")
    err = _falla(kit, "E001")
    assert err.exit_code == 2


def test_E002_esquema(kit):
    kit.inventario([{"nombre": "x", "tipo": "texto", "ocurrencias": []}])
    err = _falla(kit, "E002")
    assert "texto" in err.fallos[0].mensaje and err.exit_code == 1


def test_E002_coherencia(kit):
    kit.inventario(
        [
            campo("x", "Opcional A"),
            campo("x", "Opcional B"),
            {"nombre": "y", "tipo": "number", "origen_valor": "endpoint", "ocurrencias": []},
        ]
    )
    err = _falla(kit, "E002")
    mensajes = " ".join(f.mensaje for f in err.fallos)
    assert (
        "duplicado" in mensajes and "exige `calculo`" in mensajes and "sin ocurrencias" in mensajes
    )


def test_E003_numero_de_coincidencias(kit):
    kit.inventario([campo("x", "ACME", esperadas=2)])
    err = _falla(kit, "E003")
    assert "aparece 9" in err.fallos[0].mensaje and "header1/p/0000" in err.fallos[0].mensaje


def test_E003_regex(kit):
    kit.inventario([campo("x", r"Opcional [AB]", esperadas=1, regex=True)])
    _falla(kit, "E003")


def test_E004_solape(kit):
    kit.inventario([campo("a", "ACME S.L.", esperadas=2), campo("b", "S.L.", esperadas=2)])
    _falla(kit, "E004")


def test_E005_ambito_inexistente(kit):
    kit.inventario([campo("x", "ACME", en="document/p/9999")])
    _falla(kit, "E005")


def test_E006_lock(kit):
    kit.inventario([campo("nuevo", "Opcional A", renombrado_de="viejo")])
    _falla(kit, "E006")


def test_E007_tabla_no_resoluble(kit):
    kit.inventario(
        [{"nombre": "items", "tipo": "list", "ocurrencias": []}],
        bloques=[
            {
                "tipo": "tabla_repetible",
                "lista": "items",
                "tabla": {"ancla": "no existe"},
                "fila_plantilla": 1,
                "columnas": [{"buscar": "Huawei", "atributo": "fab"}],
            }
        ],
    )
    _falla(kit, "E007")


def test_E008_contenido_no_textual(kit):
    kit.inventario([campo("x", "HolaMundo")])
    _falla(kit, "E008")


def test_E009_falta_entrada(tmp_path):
    with pytest.raises(KitError) as exc:
        build(tmp_path, "no_existe")
    assert _codigos(exc) == ["E009"] and exc.value.exit_code == 2


def test_E010_control_de_cambios(tmp_path):
    k = Kit(tmp_path)
    k.origen("revisiones.docx")
    with pytest.raises(KitError) as exc:
        extract(k.raiz, k.slug)
    assert _codigos(exc) == ["E010"]


def test_E011_fallback_distinto(tmp_path):
    k = Kit(tmp_path)
    k.origen("fallback_distinto.docx")
    k.inventario([campo("x", "ACME")])
    _falla(k, "E011")


def test_E012_estructura_no_soportada(tmp_path):
    k = Kit(tmp_path)
    k.origen("no_soportado.docx")
    with pytest.raises(KitError) as exc:
        extract(k.raiz, k.slug)
    assert _codigos(exc) == ["E012"]


def test_E013_yaml_de_dominio(kit):
    kit.inventario([campo("x", "Opcional A")])
    kit.yaml("datasets.yaml", [{"key": "d", "rows": []}])
    _falla(kit, "E013")


def test_E013_fecha_sin_comillas(kit):
    kit.inventario([campo("x", "Opcional A")])
    (kit.fuente / "prompts.yaml").write_text("- key: p\n  name: 2026-01-01\n  instruction: x\n")
    _falla(kit, "E013")


def test_E020_estructura_distinta():
    with pytest.raises(KitError) as exc:
        inferir(FIXTURES / "basico.docx", FIXTURES / "marcadores.docx", "x")
    assert _codigos(exc) == ["E020"]


def test_E021_diferencias_no_explicables(tmp_path, capsys):
    plantilla = tmp_path / "p.docx"
    shutil.copyfile(FIXTURES / "basico.docx", plantilla)
    from docai_kit.docx_io import Paquete

    paquete = Paquete.abrir(plantilla)
    xml = paquete.datos("word/document.xml").replace(b"Opcional A", b"Opcional Z")
    paquete.reemplazar("word/document.xml", xml)
    plantilla.write_bytes(paquete.a_bytes())
    code = cli.main(
        [
            "infer",
            "--origen",
            str(FIXTURES / "basico.docx"),
            "--plantilla",
            str(plantilla),
            "-o",
            str(tmp_path / "x" / "inventario.yaml"),
            "--json",
        ]
    )
    informe = json.loads(capsys.readouterr().out)
    assert code == 1 and informe["fallos"][0]["codigo"] == "E021"


def test_E030_condicional(kit):
    kit.inventario(
        [{"nombre": "incluir", "tipo": "boolean", "ocurrencias": []}],
        bloques=[
            {
                "tipo": "condicional",
                "variable": "incluir",
                "desde": "document/p/0009",
                "hasta": "document/tbl/01/r/00/c/00/p/00",
            }
        ],
    )
    _falla(kit, "E030")


def test_E030_rango_invertido(kit):
    kit.inventario(
        [{"nombre": "incluir", "tipo": "boolean", "ocurrencias": []}],
        bloques=[
            {
                "tipo": "condicional",
                "variable": "incluir",
                "desde": "document/p/0010",
                "hasta": "document/p/0009",
            }
        ],
    )
    _falla(kit, "E030")


def _kit_valido(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    kit.yaml("datos_ejemplo.yaml", {"empresa": "Fastex"})
    build(kit.raiz, kit.slug)


def test_E040_validate_falla_antes_de_importar(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)])
    with pytest.raises(KitError) as exc:  # sin build: V11 y V01 fallan
        importar(kit.raiz, kit.slug, "test", False, False, None, {})
    assert _codigos(exc) == ["E040"]


def test_E041_faltan_variables(kit):
    _kit_valido(kit)
    with pytest.raises(KitError) as exc:
        importar(kit.raiz, kit.slug, "test", True, False, None, {"DOCAI_HOST": "http://x"})
    assert _codigos(exc) == ["E041"]


def test_E042_error_http(kit):
    _kit_valido(kit)
    env = {"DOCAI_HOST": "http://127.0.0.1:9", "DOCAI_USER": "u", "DOCAI_PASS": "p"}
    with pytest.raises(KitError) as exc:
        importar(kit.raiz, kit.slug, "test", True, False, None, env)
    assert _codigos(exc) == ["E042"]


def test_E043_prod_sin_confirmar(kit):
    _kit_valido(kit)
    with pytest.raises(KitError) as exc:
        importar(kit.raiz, kit.slug, "prod", True, False, None, {})
    assert _codigos(exc) == ["E043"]


def test_E050_sin_soffice(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(KitError) as exc:
        a_pdf(tmp_path / "x.docx", tmp_path / "x.pdf")
    assert _codigos(exc) == ["E050"]


def test_W001_marcadores_preexistentes(tmp_path):
    k = Kit(tmp_path)
    k.origen("marcadores.docx")
    _, _, avisos = extract(k.raiz, k.slug)
    assert [a.codigo for a in avisos] == ["W001"]


def test_todos_los_codigos_tienen_test():
    fuente = Path(__file__).read_text(encoding="utf-8")
    sin_test = [c for c in CATALOGO if f"test_{c}_" not in fuente]
    assert sin_test == []


def test_la_tabla_de_errores_de_la_documentacion_esta_al_dia():
    docs = (Path(__file__).resolve().parents[1] / "docs" / "02-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    for c in CATALOGO.values():
        assert f"| `{c.codigo}` | {c.exit} | {c.titulo} | {c.accion} |" in docs, c.codigo
