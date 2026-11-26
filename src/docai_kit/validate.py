"""``docai-kit validate``: V01–V12 sobre componentes/<slug>/, acumulando todos los fallos."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import jinja2
from docxtpl import DocxTemplate

from . import serialize
from .build import VARIABLE_BUCLE, construir, marcador
from .docx_io import W_P, Paquete, calcular_tramos, partes_texto, sha256_fichero
from .errors import VALIDACIONES, Fallo, KitError
from .inventario import (
    DOMINIOS,
    RutasPlantilla,
    cargar_inventario,
    errores_esquema,
    nombres_en_formula,
)
from .render import a_pdf, render_bytes, soffice_disponible, textos

RE_NOMBRE = re.compile(r"^[a-z][a-z0-9_]*$")
RE_MARCA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")
RE_DELIMITADOR = re.compile(r"\{\{|\}\}|\{%|%\}")


@dataclass
class Comprobacion:
    codigo: str
    estado: str = "passed"  # passed | failed | warning | skipped
    fallos: list[Fallo] = field(default_factory=list)
    motivo: str | None = None

    def fallo(self, mensaje: str, ubicacion: str | None = None, severidad: str = "error") -> None:
        self.fallos.append(Fallo(self.codigo, mensaje, ubicacion, severidad))

    def cerrar(self) -> Comprobacion:
        if self.estado == "skipped":
            return self
        if any(f.severidad == "error" for f in self.fallos):
            self.estado = "failed"
        elif self.fallos:
            self.estado = "warning"
        return self

    def omitir(self, motivo: str) -> Comprobacion:
        self.estado, self.motivo = "skipped", motivo
        return self


@dataclass
class Informe:
    slug: str
    comprobaciones: list[Comprobacion]

    @property
    def ok(self) -> bool:
        return all(c.estado != "failed" for c in self.comprobaciones)

    def como_dict(self) -> dict:
        return {
            "slug": self.slug,
            "ok": self.ok,
            "comprobaciones": [
                {
                    "codigo": c.codigo,
                    "titulo": VALIDACIONES[c.codigo],
                    "estado": c.estado,
                    "motivo": c.motivo,
                }
                for c in self.comprobaciones
            ],
            "fallos": [f.como_dict() for c in self.comprobaciones for f in c.fallos],
        }


def _leer_json(ruta: Path, chk: Comprobacion):
    if not ruta.is_file():
        chk.fallo("no existe", str(ruta))
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        chk.fallo(f"JSON no legible: {exc}", str(ruta))
        return None


def _duplicados(valores: list, que: str, chk: Comprobacion, ubic: str) -> None:
    for valor, n in sorted(Counter(valores).items(), key=lambda kv: str(kv[0])):
        if n > 1:
            chk.fallo(f"{que} duplicado: {valor!r} ({n} veces)", ubic)


def _excepcion(exc: BaseException) -> str:
    ultima = traceback.extract_tb(exc.__traceback__)[-1:] if exc.__traceback__ else []
    donde = f" ({ultima[0].filename}:{ultima[0].lineno})" if ultima else ""
    return f"{type(exc).__name__}: {exc}{donde}"


def validar(raiz: Path, slug: str, strict: bool = False) -> Informe:
    rutas = RutasPlantilla(raiz, slug)
    comp = rutas.componentes
    chks = {c: Comprobacion(c) for c in VALIDACIONES}

    # V01 — esquemas.
    v01 = chks["V01"]
    datos: dict[str, object] = {}
    for nombre, fichero in [("fields", "fields.json")] + [(n, s) for n, _, s in DOMINIOS]:
        valor = _leer_json(comp / fichero, v01)
        if valor is None:
            continue
        datos[nombre] = valor
        v01.fallos.extend(
            Fallo("V01", f.mensaje, f.ubicacion)
            for f in errores_esquema(
                valor, serialize.cargar_esquema(nombre), "V01", str(comp / fichero)
            )
        )
    campos = datos.get("fields") if isinstance(datos.get("fields"), list) else []
    datasets = datos.get("datasets", [])
    datasets = [datasets] if isinstance(datasets, dict) else (datasets or [])
    calculos = datos.get("calculations") or []
    prompts = datos.get("prompts") or []
    _duplicados(
        [c.get("field_id") for c in campos if c.get("field_id")], "field_id", v01, "fields.json"
    )
    _duplicados([c.get("name") for c in campos], "name", v01, "fields.json")
    _duplicados([d.get("key") for d in datasets], "key de dataset", v01, "datasets.json")
    _duplicados([c.get("key") for c in calculos], "key de cálculo", v01, "calculations.json")
    _duplicados([p.get("key") for p in prompts], "key de prompt", v01, "prompts.json")
    nombres = {c.get("name") for c in campos}

    # Inventario (para V06/V07); si no carga, esas comprobaciones fallan con su motivo.
    inventario = None
    try:
        inventario = cargar_inventario(
            rutas, sha256_fichero(rutas.origen) if rutas.origen.is_file() else ""
        )
    except KitError as exc:
        for f in exc.fallos:
            chks["V06"].fallo(f"inventario: {f.codigo} {f.mensaje}", f.ubicacion)

    # V03 — datasets referenciados.
    claves_ds = {d.get("key") for d in datasets}
    for c in campos:
        if c.get("options_source") and c["options_source"] not in claves_ds:
            chks["V03"].fallo(
                f"{c.get('name')}: options_source {c['options_source']!r} no existe", "fields.json"
            )

    # V04 — cálculos referenciados.
    por_clave = {c.get("key"): c for c in calculos}
    for c in campos:
        binding = c.get("calculation_binding") or {}
        clave = binding.get("calculation_key")
        if not clave:
            continue
        if clave not in por_clave:
            chks["V04"].fallo(
                f"{c.get('name')}: calculation_key {clave!r} no existe", "fields.json"
            )
            continue
        declaradas = {i.get("name") for i in por_clave[clave].get("inputs", [])}
        for entrada, destino in (binding.get("input_map") or {}).items():
            if entrada not in declaradas:
                chks["V04"].fallo(
                    f"{c.get('name')}: {clave} no declara la entrada {entrada!r}", "fields.json"
                )
            if isinstance(destino, str) and not destino.startswith("=") and destino not in nombres:
                chks["V04"].fallo(
                    f"{c.get('name')}: input_map {entrada} -> {destino!r} no es un campo",
                    "fields.json",
                )

    # Plantilla.
    ruta_docx = comp / "plantilla.docx"
    plantilla = ruta_docx.read_bytes() if ruta_docx.is_file() else None
    if plantilla is None:
        for c in ("V02", "V05", "V08", "V09", "V10", "V12"):
            chks[c].fallo("no existe componentes/<slug>/plantilla.docx", str(ruta_docx))

    # V05 — marcadores partidos y sintaxis Jinja.
    sintaxis_ok = False
    if plantilla is not None:
        paquete = Paquete.abrir(plantilla)
        for parte, nombre in partes_texto(paquete):
            for k, p in enumerate(paquete.xml(nombre).iter(W_P)):
                tramos = calcular_tramos(p)
                texto = "".join(t.t.text or "" for t in tramos)
                if "{" not in texto and "}" not in texto:
                    continue
                cubiertos = set()
                for m in RE_MARCA.finditer(texto):
                    cubiertos.update(range(m.start(), m.end()))
                    if not any(t.inicio <= m.start() and m.end() <= t.fin for t in tramos):
                        chks["V05"].fallo(
                            f"marcador partido entre runs: {m.group(0)!r}", f"{parte}:p[{k}]"
                        )
                for m in RE_DELIMITADOR.finditer(texto):
                    if m.start() not in cubiertos:
                        chks["V05"].fallo(
                            f"delimitador suelto {m.group(0)!r} en {texto[:80]!r}",
                            f"{parte}:p[{k}]",
                        )
        try:
            variables = DocxTemplate(io.BytesIO(plantilla)).get_undeclared_template_variables()
            sintaxis_ok = True
        except jinja2.TemplateSyntaxError as exc:
            chks["V05"].fallo(f"Jinja no parsea la plantilla: {exc.message} (línea {exc.lineno})")

    # V02 — variables == campos.
    if plantilla is not None and not sintaxis_ok:
        chks["V02"].omitir("V05: la plantilla no parsea")
    elif plantilla is not None:
        sobran = sorted(variables - nombres)
        en_formulas = set().union(*(nombres_en_formula(c.get("formula")) for c in campos))
        faltan = sorted(nombres - variables - en_formulas)
        if sobran:
            chks["V02"].fallo(f"variables de la plantilla sin campo: {', '.join(sobran)}")
        if faltan:
            chks["V02"].fallo(f"campos sin variable en la plantilla: {', '.join(faltan)}")

    # V06 — ocurrencias aplicadas y literales desaparecidos.
    if plantilla is not None and inventario is not None:
        todo = "\n".join(textos(plantilla, incluir_fallback=False))
        con_fallback = "\n".join(textos(plantilla))
        for c in inventario["campos"]:
            esperadas = sum(o["esperadas"] for o in c["ocurrencias"])
            reales = todo.count(marcador(c["nombre"]))
            if reales != esperadas:
                chks["V06"].fallo(
                    f"{c['nombre']}: {reales} marcadores en la plantilla, se esperaban {esperadas}"
                )
        for b in inventario.get("bloques", []):
            if b["tipo"] == "tabla_repetible":
                for col in b["columnas"]:
                    m = marcador(f"{VARIABLE_BUCLE}.{col['atributo']}")
                    if todo.count(m) != 1:
                        chks["V06"].fallo(
                            f"{b['lista']}: {m} aparece {todo.count(m)} veces (se esperaba 1)"
                        )
        for literal in inventario.get("debe_desaparecer", []):
            if literal in con_fallback:
                chks["V06"].fallo(f"el literal {literal!r} sigue en la plantilla")

    # V07 — formato de nombres. Aviso por defecto; con --strict, error salvo los heredados declarados.
    heredados = set(inventario.get("nombres_heredados", [])) if inventario else set()
    malos = sorted(x for x in nombres if isinstance(x, str) and not RE_NOMBRE.match(x))
    for n in malos:
        if n not in heredados:
            chks["V07"].fallo(
                f"{n!r} no cumple ^[a-z][a-z0-9_]*$", "fields.json", "error" if strict else "aviso"
            )
    exentos = [n for n in malos if n in heredados]
    if exentos:
        chks["V07"].fallo(
            f"{len(exentos)} nombre(s) heredado(s) declarados en nombres_heredados: {', '.join(exentos)}",
            "inventario.yaml",
            "aviso",
        )

    # V08–V10 — render.
    ejemplo = None
    if plantilla is not None and not sintaxis_ok:
        for c in ("V08", "V09", "V10"):
            chks[c].omitir("V05: la plantilla no parsea")
    elif plantilla is not None:
        try:
            render_bytes(plantilla, {})
        except Exception as exc:  # noqa: BLE001 — se informa como fallo de V08, no se oculta
            chks["V08"].fallo(f"render con {{}} lanza {_excepcion(exc)}")
        if not rutas.datos_ejemplo.is_file():
            chks["V09"].fallo("no existe datos_ejemplo.yaml", str(rutas.datos_ejemplo))
            chks["V10"].omitir("sin datos_ejemplo.yaml")
        else:
            try:
                ejemplo = serialize.cargar_yaml(rutas.datos_ejemplo, "E013")
            except KitError as exc:
                chks["V09"].fallo(exc.fallos[0].mensaje, str(rutas.datos_ejemplo))
            if ejemplo is not None and not isinstance(ejemplo, dict):
                chks["V09"].fallo("datos_ejemplo.yaml debe ser un mapa campo -> valor")
                ejemplo = None
        if ejemplo is not None:
            ajenos = sorted(k for k in ejemplo if k not in nombres)
            if ajenos:
                chks["V09"].fallo(
                    f"claves que no son campos: {', '.join(ajenos)}", str(rutas.datos_ejemplo)
                )
            try:
                salida = render_bytes(plantilla, ejemplo)
                restos = [t for t in textos(salida) if "{{" in t or "{%" in t]
                for t in restos[:10]:
                    chks["V09"].fallo(f"queda un marcador tras el render: {t[:120]!r}")
            except Exception as exc:  # noqa: BLE001
                chks["V09"].fallo(f"render con datos_ejemplo lanza {_excepcion(exc)}")
            orden = {c.get("name"): c.get("field_order", 0) for c in campos}
            parcial = {k: v for k, v in ejemplo.items() if orden.get(k, 1) % 2 == 0}
            try:
                render_bytes(plantilla, parcial)
            except Exception as exc:  # noqa: BLE001
                chks["V10"].fallo(f"render parcial lanza {_excepcion(exc)}")

    # V11 — componentes al día.
    try:
        res = construir(raiz, slug)
        for nombre, contenido in sorted(res.ficheros.items()):
            ruta = comp / nombre
            if not ruta.is_file():
                chks["V11"].fallo("falta; ejecuta `docai-kit build`", str(ruta))
            elif (
                hashlib.sha256(ruta.read_bytes()).hexdigest()
                != hashlib.sha256(contenido).hexdigest()
            ):
                chks["V11"].fallo(
                    "difiere de un build limpio; ejecuta `docai-kit build`", str(ruta)
                )
        if comp.is_dir():
            for ruta in sorted(comp.iterdir()):
                if ruta.name not in res.ficheros:
                    chks["V11"].fallo(
                        "fichero que build no genera (no edites componentes/ a mano)", str(ruta)
                    )
        if res.lock_cambia:
            chks["V11"].fallo("ids.lock.json cambiaría; ejecuta `docai-kit build`", str(rutas.lock))
    except KitError as exc:
        for f in exc.fallos:
            chks["V11"].fallo(f"build falla: {f.codigo} {f.mensaje}", f.ubicacion)

    # V12 — PDF (opcional).
    if not soffice_disponible():
        chks["V12"].omitir("soffice no disponible")
    elif plantilla is not None and sintaxis_ok:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                docx = Path(tmp) / "render.docx"
                serialize.escribir_bytes(docx, render_bytes(plantilla, ejemplo or {}))
                a_pdf(docx, Path(tmp) / "render.pdf")
        except KitError as exc:
            chks["V12"].fallo(exc.fallos[0].mensaje)

    return Informe(slug, [c.cerrar() for c in chks.values()])
