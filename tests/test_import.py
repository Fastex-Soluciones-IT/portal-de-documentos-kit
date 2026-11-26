"""import: dry-run por defecto, orden fijo y credenciales solo desde el entorno."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import campo
from docai_kit.build import build
from docai_kit.importer import importar


@pytest.fixture
def kit_listo(kit):
    kit.inventario([campo("empresa", "ACME", esperadas=9)], nombre_plantilla="Demo")
    kit.yaml("datos_ejemplo.yaml", {"empresa": "Fastex"})
    kit.yaml("datasets.yaml", [{"key": "d", "name": "D", "rows": [{"value": "a"}]}])
    kit.yaml(
        "calculations.yaml",
        [{"key": "c", "name": "C", "calc_type": "formula", "spec": {"expression": "1"}}],
    )
    build(kit.raiz, kit.slug)
    return kit


class _Servidor(BaseHTTPRequestHandler):
    peticiones: list = []

    def _responder(self, cuerpo: dict):
        datos = json.dumps(cuerpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _registrar(self):
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(largo)
        self.peticiones.append((self.command, self.path, self.headers.get("Authorization"), cuerpo))

    def do_POST(self):  # noqa: N802
        self._registrar()
        if self.path.endswith("/login/access-token"):
            return self._responder({"access_token": "tok"})
        if self.path == "/api/v1/templates/":
            return self._responder({"id": "T-1"})
        return self._responder({"created": 1, "updated": 0})

    def do_PUT(self):  # noqa: N802
        self._registrar()
        return self._responder({"created": 1, "updated": 0})

    def log_message(self, *args):
        pass


def test_dry_run_no_envia_nada_ni_necesita_credenciales(kit_listo):
    registro = importar(kit_listo.raiz, kit_listo.slug, "test", False, False, None, {})
    texto = "\n".join(registro)
    assert "dry-run" in texto and "$DOCAI_HOST/api/v1/datasets/import" in texto
    assert "prompts.json está vacío" in texto
    pasos = [linea.split("]")[0].lstrip("[") for linea in registro[1:-1]]
    assert pasos == ["login", "datasets", "plantilla", "calculos", "prompts", "campos"]


def test_ejecucion_completa_en_orden(kit_listo):
    _Servidor.peticiones = []
    servidor = HTTPServer(("127.0.0.1", 0), _Servidor)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        env = {
            "DOCAI_HOST": f"http://127.0.0.1:{servidor.server_port}",
            "DOCAI_USER": "u",
            "DOCAI_PASS": "s3cr3t",
        }
        registro = importar(kit_listo.raiz, kit_listo.slug, "test", True, False, None, env)
    finally:
        servidor.shutdown()
    rutas = [(m, p) for m, p, _, _ in _Servidor.peticiones]
    assert rutas == [
        ("POST", "/api/v1/login/access-token"),
        ("POST", "/api/v1/datasets/import"),
        ("POST", "/api/v1/templates/"),
        ("POST", "/api/v1/templates/T-1/calculations/import"),
        ("PUT", "/api/v1/templates/T-1/fields/import"),
    ]
    assert all(auth == "Bearer tok" for _, _, auth, _ in _Servidor.peticiones[1:])
    subida = _Servidor.peticiones[2][3]
    assert b'name="name"\r\n\r\nDemo' in subida and b'filename="plantilla.docx"' in subida
    assert not any("s3cr3t" in linea for linea in registro)


def test_template_id_existente_omite_la_subida(kit_listo):
    registro = importar(kit_listo.raiz, kit_listo.slug, "prod", False, False, "T-9", {})
    texto = "\n".join(registro)
    assert "/templates/T-9/fields/import" in texto and "plantilla existente" in texto
    assert "--confirm-prod" in texto
