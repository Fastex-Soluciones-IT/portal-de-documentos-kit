"""Carga y validación del inventario, YAML de dominio e ``ids.lock.json``; generación de ``fields.json``."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from . import serialize
from .errors import Fallo, KitError

# value_origin que obtienen el valor de un cálculo (FIELDS_FILE_GUIDE §4: exigen calculation_key).
ORIGENES_CON_CALCULO = {"ai", "endpoint", "pipeline"}
# value_origin cuyo valor no teclea el usuario: el campo es calculado y no editable por defecto.
ORIGENES_CALCULADOS = {"formula", "ai", "endpoint", "pipeline", "code"}

DOMINIOS = (
    ("datasets", "datasets.yaml", "datasets.json"),
    ("calculations", "calculations.yaml", "calculations.json"),
    ("prompts", "prompts.yaml", "prompts.json"),
)


@dataclass(frozen=True)
class RutasPlantilla:
    raiz: Path
    slug: str

    @property
    def fuente(self) -> Path:
        return self.raiz / "plantillas" / self.slug

    @property
    def origen(self) -> Path:
        return self.fuente / "origen.docx"

    @property
    def inventario(self) -> Path:
        return self.fuente / "inventario.yaml"

    @property
    def lock(self) -> Path:
        return self.fuente / "ids.lock.json"

    @property
    def datos_ejemplo(self) -> Path:
        return self.fuente / "datos_ejemplo.yaml"

    @property
    def componentes(self) -> Path:
        return self.raiz / "componentes" / self.slug


def errores_esquema(valor: Any, esquema: dict, codigo: str, ubicacion: str) -> list[Fallo]:
    validador = Draft202012Validator(esquema)
    fallos = []
    for err in sorted(
        validador.iter_errors(valor), key=lambda e: [str(p) for p in e.absolute_path]
    ):
        ruta = "/" + "/".join(str(p) for p in err.absolute_path)
        fallos.append(Fallo(codigo, f"{ruta}: {err.message}", ubicacion))
    return fallos


# --------------------------------------------------------------------------------------------
# Inventario
# --------------------------------------------------------------------------------------------


def cargar_inventario(rutas: RutasPlantilla, sha_origen: str) -> dict:
    """Carga el inventario, comprueba el origen (E001) y valida esquema y coherencia (E002)."""
    if not rutas.inventario.is_file():
        raise KitError.de("E009", "no existe el inventario", str(rutas.inventario))
    inv = serialize.cargar_yaml(rutas.inventario, "E002")
    ubic = str(rutas.inventario)
    sha_inventario = inv.get("origen_sha256") if isinstance(inv, dict) else None
    if isinstance(sha_inventario, str) and sha_inventario != sha_origen:
        raise KitError.de(
            "E001",
            f"origen_sha256 del inventario = {inv['origen_sha256']}, origen.docx = {sha_origen}",
            str(rutas.origen),
        )
    fallos = errores_esquema(inv, serialize.cargar_esquema("inventario"), "E002", ubic)
    if fallos:
        raise KitError(fallos)
    if inv["slug"] != rutas.slug:
        fallos.append(Fallo("E002", f"slug {inv['slug']!r} != directorio {rutas.slug!r}", ubic))
    fallos.extend(_coherencia(inv, ubic))
    if fallos:
        raise KitError(fallos)
    return inv


def _coherencia(inv: dict, ubic: str) -> list[Fallo]:
    fallos: list[Fallo] = []

    def mal(ruta: str, msg: str) -> None:
        fallos.append(Fallo("E002", f"{ruta}: {msg}", ubic))

    campos = inv["campos"]
    por_nombre: dict[str, dict] = {}
    for i, c in enumerate(campos):
        if c["nombre"] in por_nombre:
            mal(f"/campos/{i}", f"nombre duplicado {c['nombre']!r}")
        por_nombre[c["nombre"]] = c
    referenciados = set()
    for i, b in enumerate(inv.get("bloques", [])):
        ruta = f"/bloques/{i}"
        nombre = b["lista"] if b["tipo"] == "tabla_repetible" else b["variable"]
        referenciados.add(nombre)
        if nombre not in por_nombre:
            mal(ruta, f"{nombre!r} debe declararse también en `campos` (con su `tipo`)")
        elif b["tipo"] == "condicional" and por_nombre[nombre]["tipo"] != "boolean":
            mal(ruta, f"la variable {nombre!r} de un condicional debe ser un campo `boolean`")
        if b["tipo"] == "tabla_repetible":
            atributos = [col["atributo"] for col in b["columnas"]]
            if len(set(atributos)) != len(atributos):
                mal(ruta, "atributos de columna repetidos")
            for j, col in enumerate(b["columnas"]):
                if col.get("regex"):
                    _regex_valida(col["buscar"], f"{ruta}/columnas/{j}", mal)
    en_formulas = set().union(*(nombres_en_formula(c.get("formula")) for c in campos))
    for i, c in enumerate(campos):
        ruta = f"/campos/{i} ({c['nombre']})"
        if not c["ocurrencias"] and c["nombre"] not in referenciados | en_formulas:
            mal(
                ruta,
                "sin ocurrencias: solo se admite si un bloque lo usa como lista o condición, "
                "o si la fórmula de otro campo lo usa",
            )
        for j, oc in enumerate(c["ocurrencias"]):
            if oc.get("regex"):
                _regex_valida(oc["buscar"], f"{ruta}/ocurrencias/{j}", mal)
            if "en" in oc and "parte" in oc and not oc["en"].startswith(oc["parte"] + "/"):
                mal(
                    f"{ruta}/ocurrencias/{j}",
                    f"`en` ({oc['en']}) no está en la parte {oc['parte']}",
                )
        origen = c.get("origen_valor")
        if origen in ORIGENES_CON_CALCULO and "calculo" not in c:
            mal(
                ruta,
                f"origen_valor {origen!r} exige `calculo` (calculation_binding.calculation_key)",
            )
        if "entradas" in c and "calculo" not in c:
            mal(ruta, "`entradas` sin `calculo`")
        if "depende_de" in c and c["depende_de"] not in por_nombre:
            mal(ruta, f"depende_de {c['depende_de']!r} no es un campo del inventario")
        if c.get("renombrado_de") in por_nombre:
            mal(ruta, f"renombrado_de {c['renombrado_de']!r} sigue siendo un campo del inventario")
        for nombre in (c.get("entradas") or {}).values():
            if not nombre.startswith("=") and nombre not in por_nombre:
                mal(
                    ruta, f"entradas: {nombre!r} no es un campo del inventario (ni un literal '=…')"
                )
    for nombre in inv.get("nombres_heredados", []):
        if nombre not in por_nombre:
            mal("/nombres_heredados", f"{nombre!r} no es un campo del inventario")
    return fallos


def nombres_en_formula(formula: str | None) -> set[str]:
    """Nombres (``ast.Name``) de una fórmula. Si no parsea, ninguno: lo valida otra regla."""
    try:
        arbol = ast.parse(formula or "", mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}


def _regex_valida(patron: str, ruta: str, mal) -> None:
    try:
        compilada = re.compile(patron)
    except re.error as exc:
        mal(ruta, f"regex no válida: {exc}")
        return
    if compilada.match(""):
        mal(ruta, "la regex admite la cadena vacía")


# --------------------------------------------------------------------------------------------
# YAML de dominio
# --------------------------------------------------------------------------------------------


def cargar_dominio(rutas: RutasPlantilla) -> dict[str, list]:
    """Lee datasets/calculations/prompts.yaml (opcionales) y los valida contra su esquema (E013)."""
    salida: dict[str, list] = {}
    fallos: list[Fallo] = []
    for nombre, fichero, _ in DOMINIOS:
        ruta = rutas.fuente / fichero
        if not ruta.is_file():
            salida[nombre] = []
            continue
        valor = serialize.cargar_yaml(ruta, "E013")
        fallos.extend(errores_esquema(valor, serialize.cargar_esquema(nombre), "E013", str(ruta)))
        salida[nombre] = valor
    if fallos:
        raise KitError(fallos)
    return salida


# --------------------------------------------------------------------------------------------
# ids.lock.json
# --------------------------------------------------------------------------------------------

_RE_FLD = re.compile(r"^FLD-(\d{4,})$")


def _num(fld: str) -> int:
    return int(_RE_FLD.match(fld).group(1))


def cargar_lock(ruta: Path) -> dict:
    if not ruta.is_file():
        return {"version": 1, "siguiente": 1, "campos": {}, "retirados": {}}
    try:
        lock = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KitError.de("E006", f"JSON no legible: {exc}", str(ruta)) from exc
    fallos = errores_esquema(lock, serialize.cargar_esquema("ids_lock"), "E006", str(ruta))
    if fallos:
        raise KitError(fallos)
    todos = list(lock["campos"].values()) + list(lock["retirados"])
    if len(set(todos)) != len(todos):
        raise KitError.de("E006", "un FLD aparece dos veces en el lock", str(ruta))
    if todos and max(_num(f) for f in todos) >= lock["siguiente"]:
        raise KitError.de("E006", "`siguiente` no es mayor que todos los FLD asignados", str(ruta))
    return lock


def asignar_ids(inv: dict, lock: dict, ruta_lock: Path) -> tuple[dict[str, str], dict]:
    """Devuelve ``(nombre -> FLD, lock_nuevo)``. Nunca renumera ni reutiliza."""
    activos = dict(lock["campos"])
    retirados = dict(lock["retirados"])
    siguiente = lock["siguiente"]
    nombres = [c["nombre"] for c in inv["campos"]]
    asignados: dict[str, str] = {}
    fallos = []
    # 1) Renombrados: heredan el ID del nombre anterior.
    for c in inv["campos"]:
        anterior = c.get("renombrado_de")
        if anterior is None or c["nombre"] in activos:
            continue
        if anterior not in activos:
            fallos.append(
                Fallo(
                    "E006",
                    f"{c['nombre']}: renombrado_de {anterior!r} no está en el lock",
                    str(ruta_lock),
                )
            )
            continue
        asignados[c["nombre"]] = activos.pop(anterior)
    if fallos:
        raise KitError(fallos)
    # 2) Existentes y nuevos, en el orden del inventario.
    for nombre in nombres:
        if nombre in asignados:
            continue
        if nombre in activos:
            asignados[nombre] = activos.pop(nombre)
        else:
            asignados[nombre] = f"FLD-{siguiente:04d}"
            siguiente += 1
    # 3) Lo que queda en activos ha desaparecido del inventario: se retira (su ID no se reutiliza).
    retirados.update({fld: nombre for nombre, fld in activos.items()})
    nuevo = {
        "version": 1,
        "siguiente": siguiente,
        "campos": dict(sorted(asignados.items(), key=lambda kv: _num(kv[1]))),
        "retirados": dict(sorted(retirados.items(), key=lambda kv: _num(kv[0]))),
    }
    return asignados, nuevo


# --------------------------------------------------------------------------------------------
# fields.json
# --------------------------------------------------------------------------------------------


def origen_valor(c: dict) -> str:
    if "origen_valor" in c:
        return c["origen_valor"]
    if "formula" in c:
        return "formula"
    if "dataset" in c:
        return "dataset"
    return "manual"


def config_campo(
    c: dict, field_id: str, capitulo: str | None, orden: int, unidades: dict[str, str | None]
) -> dict:
    """``FieldConfig`` completo de un campo del inventario (defaults según FIELDS_FILE_GUIDE §2)."""
    origen = origen_valor(c)
    calculado = c.get("calculado", origen in ORIGENES_CALCULADOS)
    binding = None
    if "calculo" in c:
        binding = {"calculation_key": c["calculo"], "input_map": c.get("entradas")}
    return {
        "field_id": field_id,
        "name": c["nombre"],
        "technical_name": c.get("nombre_tecnico", c["nombre"]),
        "label": c.get("etiqueta"),
        "type": c["tipo"],
        "unit": unidades.get(c["calculo"]) if "calculo" in c else None,
        "required": c.get("requerido", False),
        "description": c.get("descripcion"),
        "help_text": c.get("ayuda"),
        "chapter": c.get("capitulo", capitulo),
        "field_order": c.get("orden", orden),
        "visible": c.get("visible", True),
        "editable": c.get("editable", not calculado),
        "visible_when": c.get("visible_cuando"),
        "value_origin": origen,
        "calculation_binding": binding,
        "options_source": c.get("dataset"),
        "depends_on": c.get("depende_de"),
        "options": c.get("opciones"),
        "default_value": c.get("valor_defecto"),
        "formula": c.get("formula"),
        "calculated": calculado,
    }


# Correspondencia FieldConfig -> clave del inventario (para `infer`, que solo escribe lo que se
# sale del default).
CLAVES_INVENTARIO = {
    "technical_name": "nombre_tecnico",
    "label": "etiqueta",
    "required": "requerido",
    "description": "descripcion",
    "help_text": "ayuda",
    "chapter": "capitulo",
    "field_order": "orden",
    "visible": "visible",
    "editable": "editable",
    "visible_when": "visible_cuando",
    "value_origin": "origen_valor",
    "options_source": "dataset",
    "depends_on": "depende_de",
    "options": "opciones",
    "default_value": "valor_defecto",
    "formula": "formula",
    "calculated": "calculado",
}
