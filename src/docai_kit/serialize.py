"""Serializador canónico: el ÚNICO punto de escritura de ficheros del kit.

- JSON: UTF-8, ``ensure_ascii=False``, ``indent=2`` y ``\\n`` final.
- YAML: YAML 1.2 (ruamel, cargador *safe* puro), bloques, sin plegar líneas.
- El orden de claves de los objetos lo fija el esquema (orden de ``properties``). Las claves que el
  esquema no enumera (mapas libres como ``input_map``) conservan el orden del fichero de origen, que
  es el que escribió una persona, nunca el de un ``set``.
- Las escrituras son atómicas (fichero temporal + ``os.replace``).
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .errors import KitError

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def cargar_esquema(nombre: str) -> dict:
    """Carga ``schemas/<nombre>.schema.json``."""
    return json.loads((SCHEMAS_DIR / f"{nombre}.schema.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------
# Orden de claves dirigido por el esquema
# --------------------------------------------------------------------------------------------


def _resolver(nodo: dict, raiz: dict) -> dict:
    while "$ref" in nodo:
        ref = nodo["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"$ref no soportada: {ref}")
        destino: Any = raiz
        for trozo in ref[2:].split("/"):
            destino = destino[trozo]
        nodo = destino
    return nodo


def _candidatos(nodo: dict, raiz: dict) -> list[dict]:
    """Subesquemas (resueltos) que pueden describir el valor: el propio nodo y sus ramas."""
    nodo = _resolver(nodo, raiz)
    salida = [nodo]
    for clave in ("anyOf", "oneOf", "allOf"):
        for rama in nodo.get(clave, []):
            salida.extend(_candidatos(rama, raiz))
    return salida


def ordenar(valor: Any, esquema: dict | None, raiz: dict | None = None) -> Any:
    """Devuelve una copia de ``valor`` con las claves en el orden que marca ``esquema``."""
    if esquema is None:
        return valor
    raiz = raiz if raiz is not None else esquema
    candidatos = _candidatos(esquema, raiz)
    if isinstance(valor, dict):
        props: dict = {}
        extra: dict | None = None
        for c in candidatos:
            if "properties" in c and not props:
                props = c["properties"]
            if isinstance(c.get("additionalProperties"), dict) and extra is None:
                extra = c["additionalProperties"]
        salida = {}
        for clave in props:
            if clave in valor:
                salida[clave] = ordenar(valor[clave], props[clave], raiz)
        for clave, v in valor.items():
            if clave not in props:
                salida[clave] = ordenar(v, extra, raiz)
        return salida
    if isinstance(valor, list):
        items = next((c["items"] for c in candidatos if isinstance(c.get("items"), dict)), None)
        return [ordenar(v, items, raiz) for v in valor]
    return valor


# --------------------------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------------------------


def json_bytes(valor: Any, esquema: dict | None = None) -> bytes:
    texto = json.dumps(ordenar(valor, esquema), ensure_ascii=False, indent=2)
    return (texto + "\n").encode("utf-8")


def escribir_json(ruta: Path, valor: Any, esquema: dict | None = None) -> bytes:
    datos = json_bytes(valor, esquema)
    escribir_bytes(ruta, datos)
    return datos


# --------------------------------------------------------------------------------------------
# YAML
# --------------------------------------------------------------------------------------------


def _yaml() -> YAML:
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.sort_base_mapping_type_on_output = False
    return y


def yaml_bytes(valor: Any, esquema: dict | None = None) -> bytes:
    flujo = io.StringIO()
    _yaml().dump(ordenar(valor, esquema), flujo)
    return flujo.getvalue().encode("utf-8")


def escribir_yaml(ruta: Path, valor: Any, esquema: dict | None = None) -> bytes:
    datos = yaml_bytes(valor, esquema)
    escribir_bytes(ruta, datos)
    return datos


def _solo_json(valor: Any, ruta: str) -> list[str]:
    """Rutas de valores que no son tipos JSON (p. ej. fechas sin comillas en el YAML)."""
    if isinstance(valor, dict):
        malos = []
        for k, v in valor.items():
            if not isinstance(k, str):
                malos.append(f"{ruta}/{k!r} (clave no textual)")
            malos.extend(_solo_json(v, f"{ruta}/{k}"))
        return malos
    if isinstance(valor, list):
        return [m for i, v in enumerate(valor) for m in _solo_json(v, f"{ruta}/{i}")]
    if isinstance(valor, (_dt.date, _dt.datetime, bytes, set)):
        return [f"{ruta} ({type(valor).__name__}; ponlo entre comillas)"]
    return []


def cargar_yaml(ruta: Path, codigo: str) -> Any:
    """Carga un YAML. Cualquier problema se convierte en ``KitError(codigo)``."""
    try:
        valor = _yaml().load(ruta.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise KitError.de(codigo, f"YAML no legible: {exc}", str(ruta)) from exc
    malos = _solo_json(valor, "")
    if malos:
        raise KitError.de(
            codigo, "valores no representables en JSON: " + ", ".join(malos), str(ruta)
        )
    return valor


# --------------------------------------------------------------------------------------------
# Escritura atómica
# --------------------------------------------------------------------------------------------


def escribir_bytes(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp-docai-kit")
    temporal.write_bytes(datos)
    os.replace(temporal, ruta)
