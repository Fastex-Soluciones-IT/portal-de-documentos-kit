"""``docai-kit infer``: (origen.docx, plantilla.docx adaptada a mano) -> inventario.yaml.

Alinea los párrafos por localizador, deriva con un diff a nivel de carácter los pares
(texto original -> ``{{ x }}``) y elige para cada literal el ámbito más amplio en el que buscarlo
reproduce **exactamente** las sustituciones de la plantilla (todo el documento, una parte o un
párrafo). Lo que no es una sustitución limpia se devuelve como "diferencias no explicables".
"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .build import encontrar
from .docx_io import Parrafo, sha256_fichero
from .errors import KitError
from .extract import leer_origen
from .inventario import CLAVES_INVENTARIO, config_campo

RE_MARCADOR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
RE_NOMBRE_ESTRICTO = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Sustitucion:
    campo: str
    literal: str
    par: Parrafo
    inicio: int
    fin: int


@dataclass
class Informe:
    no_explicables: list[dict] = field(default_factory=list)
    campos_sin_marcador: list[str] = field(default_factory=list)
    marcadores_sin_campo: list[str] = field(default_factory=list)
    metadatos_no_reproducibles: list[dict] = field(default_factory=list)

    def vacio(self) -> bool:
        return not (
            self.no_explicables
            or self.campos_sin_marcador
            or self.marcadores_sin_campo
            or self.metadatos_no_reproducibles
        )

    def como_dict(self) -> dict:
        return {
            "diferencias_no_explicables": self.no_explicables,
            "campos_sin_marcador": self.campos_sin_marcador,
            "marcadores_sin_campo": self.marcadores_sin_campo,
            "metadatos_no_reproducibles": self.metadatos_no_reproducibles,
        }


def diferencias_parrafo(a: str, b: str) -> tuple[list[tuple[str, int, int]], list[dict]]:
    """Pares (campo, inicio, fin en ``a``) y el residuo que no explican los marcadores.

    Cada marcador de ``b`` es un único token que no coincide con ningún carácter de ``a``; así el
    diff no puede alinear letras del interior de un marcador con el texto que lo rodea. El tramo
    original de un marcador va del carácter alineado anterior al siguiente.
    """
    marcas = list(RE_MARCADOR.finditer(b))
    tokens: list = []
    pos = 0
    for m in marcas:
        tokens.extend(b[pos : m.start()])
        tokens.append(("marcador", m.start()))
        pos = m.end()
    tokens.extend(b[pos:])
    alineado: list[int | None] = [None] * len(tokens)
    sm = difflib.SequenceMatcher(None, list(a), tokens, autojunk=False)
    for etiqueta, i1, _i2, j1, j2 in sm.get_opcodes():
        if etiqueta == "equal":
            for k in range(j2 - j1):
                alineado[j1 + k] = i1 + k
    indices = [k for k, t in enumerate(tokens) if isinstance(t, tuple)]
    pares = []
    for m, k in zip(marcas, indices, strict=True):
        izq = next((alineado[t] + 1 for t in range(k - 1, -1, -1) if alineado[t] is not None), 0)
        der = next(
            (alineado[t] for t in range(k + 1, len(tokens)) if alineado[t] is not None), len(a)
        )
        pares.append((m.group(1), izq, der, m.group(0)))
    # Marcadores que compiten por el mismo tramo de origen no son sustituciones limpias.
    limpios = []
    for k, (nombre, i, j, texto) in enumerate(pares):
        solapa_previo = k > 0 and pares[k - 1][2] > i
        solapa_siguiente = k + 1 < len(pares) and pares[k + 1][1] < j
        if solapa_previo or solapa_siguiente or i >= j:
            continue
        limpios.append((nombre, i, j, texto))
    # Reconstruye b a partir de a + marcadores; lo que no coincida es residuo.
    trozos, pos = [], 0
    for nombre, i, j, texto in limpios:
        trozos.append(a[pos:i])
        trozos.append("{{ " + nombre + " }}" if texto == "{{ " + nombre + " }}" else "\0")
        pos = j
    trozos.append(a[pos:])
    reconstruido = "".join(trozos)
    residuo = []
    if reconstruido != b:
        sm = difflib.SequenceMatcher(None, reconstruido, b, autojunk=False)
        for etiqueta, i1, i2, j1, j2 in sm.get_opcodes():
            if etiqueta != "equal":
                residuo.append(
                    {"operacion": etiqueta, "esperado": reconstruido[i1:i2], "plantilla": b[j1:j2]}
                )
    return [(n, i, j) for n, i, j, _ in limpios], residuo


def _ambitos(literal: str, spans: list[Sustitucion], parrafos: list[Parrafo]) -> list[dict] | None:
    """Ocurrencias mínimas cuyo resultado == exactamente ``spans``. None si no hay ninguna."""
    reales = {(s.par.id, s.inicio, s.fin) for s in spans}
    encontrados = {p.id: encontrar(p.texto, literal, False) for p in parrafos}
    if {(pid, s, e) for pid, lst in encontrados.items() for s, e in lst} == reales:
        return [{"buscar": literal, "esperadas": len(reales)}]
    partes = sorted(
        {s.par.parte for s in spans}, key=lambda x: [s.par.parte for s in spans].index(x)
    )
    salida = []
    for parte in partes:
        en_parte = {
            r for r in reales if any(x.par.id == r[0] and x.par.parte == parte for x in spans)
        }
        hallados = {
            (p.id, s, e) for p in parrafos if p.parte == parte for s, e in encontrados[p.id]
        }
        if hallados == en_parte:
            salida.append({"buscar": literal, "esperadas": len(en_parte), "parte": parte})
            continue
        # Por párrafo.
        pids = []
        for s in spans:
            if s.par.parte == parte and s.par.id not in pids:
                pids.append(s.par.id)
        for pid in pids:
            propios = {r for r in reales if r[0] == pid}
            if {(pid, s, e) for s, e in encontrados[pid]} != propios:
                return None
            salida.append({"buscar": literal, "esperadas": len(propios), "en": pid})
    return salida


def _metadatos(
    campo: dict, real: dict, capitulo_titulo: str | None, orden: int, informe: Informe
) -> None:
    """Añade a ``campo`` solo las claves cuyo valor real difiere del default."""
    if real.get("calculation_binding"):
        campo["calculo"] = real["calculation_binding"]["calculation_key"]
        if real["calculation_binding"].get("input_map") is not None:
            campo["entradas"] = real["calculation_binding"]["input_map"]
    # Orden de dependencias: formula/dataset antes que value_origin, este antes que calculated,
    # y calculated antes que editable.
    secuencia = [
        "technical_name",
        "label",
        "required",
        "description",
        "help_text",
        "chapter",
        "visible",
        "visible_when",
        "options_source",
        "depends_on",
        "options",
        "default_value",
        "formula",
        "value_origin",
        "calculated",
        "editable",
    ]
    for clave in secuencia:
        defecto = config_campo(campo, "", capitulo_titulo, orden, {})[clave]
        if real.get(clave) != defecto:
            campo[CLAVES_INVENTARIO[clave]] = real.get(clave)
    final = config_campo(campo, real.get("field_id") or "", capitulo_titulo, orden, {})
    for clave in ("unit",):
        if real.get(clave) != final[clave]:
            informe.metadatos_no_reproducibles.append(
                {"campo": campo["nombre"], "clave": clave, "valor": real.get(clave)}
            )


def inferir(
    origen: Path, plantilla: Path, slug: str, campos_json: Path | None = None
) -> tuple[dict, dict | None, Informe]:
    _, pars_o = leer_origen(origen)
    _, pars_p = leer_origen(plantilla)
    ids_o = [p.id for p in pars_o]
    ids_p = [p.id for p in pars_p]
    if ids_o != ids_p:
        solo_o = [i for i in ids_o if i not in set(ids_p)][:10]
        solo_p = [i for i in ids_p if i not in set(ids_o)][:10]
        primero = next(
            (k for k, (x, y) in enumerate(zip(ids_o, ids_p, strict=False)) if x != y), None
        )
        raise KitError.de(
            "E020",
            f"{len(ids_o)} párrafos en el origen y {len(ids_p)} en la plantilla. Primera divergencia en "
            f"la posición {primero}. Solo en el origen: {solo_o}. Solo en la plantilla: {solo_p}",
        )
    informe = Informe()
    sustituciones: list[Sustitucion] = []
    for po, pp in zip(pars_o, pars_p, strict=True):
        if po.texto == pp.texto:
            continue
        pares, residuo = diferencias_parrafo(po.texto, pp.texto)
        for nombre, i, j in pares:
            sustituciones.append(Sustitucion(nombre, po.texto[i:j], po, i, j))
        for r in residuo:
            informe.no_explicables.append({"parrafo": po.id} | r)

    reales: dict[str, dict] = {}
    if campos_json is not None:
        for c in json.loads(campos_json.read_text(encoding="utf-8")):
            reales[c["name"]] = c

    # Agrupa por campo (orden de primera aparición) y literal.
    grupos: dict[str, dict[str, list[Sustitucion]]] = defaultdict(lambda: defaultdict(list))
    for s in sustituciones:
        grupos[s.campo][s.literal].append(s)
    campos = []
    for nombre, por_literal in grupos.items():
        ocurrencias = []
        for literal, spans in por_literal.items():
            ambitos = _ambitos(literal, spans, pars_o)
            if ambitos is None:
                for s in spans:
                    informe.no_explicables.append(
                        {
                            "parrafo": s.par.id,
                            "operacion": "sustitucion_parcial",
                            "esperado": literal,
                            "plantilla": "{{ " + nombre + " }}",
                        }
                    )
                continue
            ocurrencias.extend(ambitos)
        primera = min(
            (s for lst in por_literal.values() for s in lst), key=lambda s: (s.par.orden, s.inicio)
        )
        campo = {"nombre": nombre, "tipo": reales.get(nombre, {}).get("type") or "text"}
        campo["_pos"] = (primera.par.parte, primera.par.orden, primera.inicio)
        campo["_capitulo"] = primera.par.capitulo
        campo["ocurrencias"] = ocurrencias
        campos.append(campo)
        if reales and nombre not in reales:
            informe.marcadores_sin_campo.append(nombre)
    orden_partes = []
    for p in pars_o:
        if p.parte not in orden_partes:
            orden_partes.append(p.parte)
    campos.sort(key=lambda c: (orden_partes.index(c["_pos"][0]), c["_pos"][1], c["_pos"][2]))
    informe.campos_sin_marcador = [n for n in reales if n not in grupos]

    # Metadatos: capítulo primero (decide el field_order por capítulo), luego el resto.
    if reales:
        por_capitulo: dict[str | None, int] = defaultdict(int)
        for c in campos:
            real = reales.get(c["nombre"])
            capitulo = real["chapter"] if real else c["_capitulo"]
            orden = por_capitulo[capitulo]
            por_capitulo[capitulo] += 1
            if real is None:
                continue
            _metadatos(c, real, c["_capitulo"], orden, informe)
            if real.get("field_order") != orden:
                c["orden"] = real["field_order"]
    for c in campos:
        del c["_pos"], c["_capitulo"]
        ocurrencias = c.pop("ocurrencias")
        c["ocurrencias"] = ocurrencias

    inventario = {
        "version": 1,
        "slug": slug,
        "origen_sha256": sha256_fichero(origen),
        "nombres_heredados": [
            c["nombre"] for c in campos if not RE_NOMBRE_ESTRICTO.match(c["nombre"])
        ],
        "debe_desaparecer": [],
        "campos": campos,
    }
    lock = None
    if reales:
        ids = {n: c["field_id"] for n, c in reales.items() if c.get("field_id")}
        numeros = [int(f.split("-")[1]) for f in ids.values()]
        lock = {
            "version": 1,
            "siguiente": max(numeros, default=0) + 1,
            "campos": dict(sorted(ids.items(), key=lambda kv: int(kv[1].split("-")[1]))),
            "retirados": {},
        }
    return inventario, lock, informe
