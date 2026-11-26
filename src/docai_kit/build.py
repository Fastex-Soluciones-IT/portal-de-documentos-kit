"""``docai-kit build``: origen.docx + inventario.yaml (+ lock + dominio) -> componentes/<slug>/.

Siempre parte del origen. Primero calcula todas las coincidencias sobre el texto original y solo si
no hay ningún error las aplica, a nivel de runs. Nada se escribe en disco hasta el final.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from . import serialize
from .docx_io import (
    W_P,
    W_PPR,
    W_R,
    W_RPR,
    W_SECTPR,
    W_T,
    W_TBL,
    W_TC,
    W_TR,
    Parrafo,
    calcular_tramos,
    elementos_no_texto_entre,
    escribir_texto,
    partes_texto,
    qn,
    sha256_fichero,
)
from .errors import Fallo, KitError
from .extract import leer_origen
from .inventario import (
    DOMINIOS,
    RutasPlantilla,
    asignar_ids,
    cargar_dominio,
    cargar_inventario,
    cargar_lock,
    config_campo,
    nombres_en_formula,
)

VARIABLE_BUCLE = "item"
W_TCPR = qn("w:tcPr")


@dataclass
class Coincidencia:
    par: Parrafo
    inicio: int
    fin: int
    marcador: str
    origen: str  # descripción legible para los mensajes
    campo: str | None  # campo al que pertenece (None en columnas de tabla)


def marcador(nombre: str) -> str:
    return "{{ " + nombre + " }}"


# --------------------------------------------------------------------------------------------
# Búsqueda
# --------------------------------------------------------------------------------------------


def encontrar(texto: str, buscar: str, regex: bool) -> list[tuple[int, int]]:
    if regex:
        return [(m.start(), m.end()) for m in re.finditer(buscar, texto)]
    salida, pos = [], 0
    while True:
        i = texto.find(buscar, pos)
        if i < 0:
            return salida
        salida.append((i, i + len(buscar)))
        pos = i + len(buscar)


def _resumen(conteo: dict[str, int], limite: int = 12) -> str:
    if not conteo:
        return "ninguna"
    items = [f"{pid} ×{n}" if n > 1 else pid for pid, n in conteo.items()]
    extra = f" (+{len(items) - limite} párrafos más)" if len(items) > limite else ""
    return ", ".join(items[:limite]) + extra


def buscar_ocurrencia(
    parrafos: list[Parrafo], por_id: dict[str, Parrafo], partes: set[str], oc: dict, origen: str
) -> tuple[list[tuple[Parrafo, int, int]], list[Fallo]]:
    if "en" in oc and oc["en"] not in por_id:
        return [], [Fallo("E005", f"{origen}: el párrafo {oc['en']!r} no existe", oc["en"])]
    if "parte" in oc and oc["parte"] not in partes:
        return [], [Fallo("E005", f"{origen}: la parte {oc['parte']!r} no existe", oc["parte"])]

    def en_ambito(p: Parrafo) -> bool:
        if "en" in oc:
            return p.id == oc["en"]
        return "parte" not in oc or p.parte == oc["parte"]

    dentro: list[tuple[Parrafo, int, int]] = []
    conteo_dentro: dict[str, int] = {}
    conteo_fuera: dict[str, int] = {}
    for p in parrafos:
        hallados = encontrar(p.texto, oc["buscar"], oc.get("regex", False))
        if not hallados:
            continue
        if en_ambito(p):
            dentro.extend((p, s, e) for s, e in hallados)
            conteo_dentro[p.id] = len(hallados)
        else:
            conteo_fuera[p.id] = len(hallados)
    if any(s == e for _, s, e in dentro):
        return [], [Fallo("E002", f"{origen}: la regex produce coincidencias vacías", None)]
    if len(dentro) != oc["esperadas"]:
        msg = (
            f"{origen}: {oc['buscar']!r} aparece {len(dentro)} vez/veces en el ámbito, se esperaban "
            f"{oc['esperadas']}. En el ámbito: {_resumen(conteo_dentro)}. "
            f"Fuera del ámbito: {_resumen(conteo_fuera)}"
        )
        return [], [Fallo("E003", msg, oc.get("en") or oc.get("parte"))]
    return dentro, []


def comprobar_tramo(par: Parrafo, elem: etree._Element, s: int, e: int, origen: str) -> list[Fallo]:
    """E008 si [s,e) cruza contenido no textual, varios contenedores de run o un campo de Word."""
    tramos = [t for t in calcular_tramos(elem) if t.fin > s and t.inicio < e and t.fin > t.inicio]
    if not tramos:
        return [Fallo("E008", f"{origen}: tramo vacío", par.id)]
    if any(t.en_campo for t in tramos):
        return [Fallo("E008", f"{origen}: el texto está dentro de un campo de Word", par.id)]
    padres = {id(t.t.getparent().getparent()) for t in tramos}
    if len(padres) > 1:
        return [
            Fallo("E008", f"{origen}: cruza el límite de un hipervínculo/campo/control", par.id)
        ]
    if len(tramos) > 1:
        raros = elementos_no_texto_entre(elem, tramos[0].t, tramos[-1].t)
        if raros:
            nombres = sorted({etree.QName(x).localname for x in raros})
            return [
                Fallo(
                    "E008", f"{origen}: cruza contenido no textual ({', '.join(nombres)})", par.id
                )
            ]
    return []


# --------------------------------------------------------------------------------------------
# Sustitución a nivel de runs
# --------------------------------------------------------------------------------------------


def sustituir(p: etree._Element, s: int, e: int, texto: str) -> None:
    """Sustituye [s,e) del texto del párrafo por ``texto``.

    ``texto`` se escribe en el primer run del tramo (conserva su rPr); el resto del tramo se recorta
    de los runs siguientes y los runs que quedan vacíos se eliminan. No toca ningún pPr ni rPr.
    """
    tramos = [t for t in calcular_tramos(p) if t.fin > s and t.inicio < e and t.fin > t.inicio]
    primero, ultimo = tramos[0], tramos[-1]
    original = primero.t.text or ""
    if primero is ultimo:
        escribir_texto(
            primero.t, original[: s - primero.inicio] + texto + original[e - primero.inicio :]
        )
        return
    escribir_texto(primero.t, original[: s - primero.inicio] + texto)
    for intermedio in tramos[1:-1]:
        escribir_texto(intermedio.t, "")
    resto = (ultimo.t.text or "")[e - ultimo.inicio :]
    escribir_texto(ultimo.t, resto)
    for tramo in tramos[1:]:
        if tramo.t.text:
            continue
        run = tramo.t.getparent()
        run.remove(tramo.t)
        if run.tag == W_R and all(h.tag == W_RPR for h in run):
            run.getparent().remove(run)


def _parrafo_simple(texto: str) -> etree._Element:
    p = etree.Element(W_P)
    r = etree.SubElement(p, W_R)
    t = etree.SubElement(r, W_T)
    escribir_texto(t, texto)
    return p


def _fila_control(tr: etree._Element, texto: str) -> etree._Element:
    """Copia de la fila con todas sus celdas vacías y ``texto`` en la primera."""
    nueva = copy.deepcopy(tr)
    for i, tc in enumerate(nueva.findall(W_TC)):
        for hijo in list(tc):
            if hijo.tag != W_TCPR:
                tc.remove(hijo)
        tc.append(_parrafo_simple(texto) if i == 0 else etree.Element(W_P))
    return nueva


# --------------------------------------------------------------------------------------------
# Bloques
# --------------------------------------------------------------------------------------------


def _tabla_de(p: Parrafo) -> tuple[etree._Element, str]:
    """Tabla más interna que contiene el párrafo y su localizador."""
    el = p.elem.getparent()
    while el is not None and el.tag != W_TBL:
        el = el.getparent()
    tid = p.id[: p.id.rindex("/r/")]
    return el, tid


def resolver_tabla(bloque: dict, parrafos: list[Parrafo], partes: set[str], i: int):
    origen = f"bloques/{i} (tabla_repetible {bloque['lista']})"
    parte = bloque["tabla"].get("parte")
    if parte is not None and parte not in partes:
        raise KitError.de("E005", f"{origen}: la parte {parte!r} no existe")
    tablas: dict[str, etree._Element] = {}
    for p in parrafos:
        if "/tbl/" not in p.id or (parte and p.parte != parte) or "/txbx/" in p.id:
            continue
        if bloque["tabla"]["ancla"] in p.texto:
            tbl, tid = _tabla_de(p)
            tablas[tid] = tbl
    if len(tablas) != 1:
        raise KitError.de(
            "E007",
            f"{origen}: el ancla {bloque['tabla']['ancla']!r} identifica {len(tablas)} tablas "
            f"({', '.join(tablas) or 'ninguna'}); debe identificar exactamente una",
        )
    tid, tbl = next(iter(tablas.items()))
    filas = tbl.findall(W_TR)
    if bloque["fila_plantilla"] >= len(filas):
        raise KitError.de(
            "E007",
            f"{origen}: fila_plantilla {bloque['fila_plantilla']} fuera de rango ({len(filas)} filas)",
            tid,
        )
    prefijo = f"{tid}/r/{bloque['fila_plantilla']:02d}/"
    return tid, filas[bloque["fila_plantilla"]], [p for p in parrafos if p.id.startswith(prefijo)]


def resolver_condicional(bloque: dict, por_id: dict[str, Parrafo], i: int):
    origen = f"bloques/{i} (condicional {bloque['variable']})"
    for clave in ("desde", "hasta"):
        if bloque[clave] not in por_id:
            raise KitError.de(
                "E005", f"{origen}: {clave} {bloque[clave]!r} no existe", bloque[clave]
            )
    desde, hasta = por_id[bloque["desde"]], por_id[bloque["hasta"]]
    if desde.parte != hasta.parte or desde.contenedor != hasta.contenedor:
        raise KitError.de(
            "E030",
            f"{origen}: desde ({desde.id}) y hasta ({hasta.id}) no están en el mismo contenedor",
        )
    if "/txbx/" in desde.id:
        raise KitError.de(
            "E030", f"{origen}: no se admiten condicionales en cuadros de texto", desde.id
        )
    padre = desde.elem.getparent()
    hermanos = list(padre)
    a, b = hermanos.index(desde.elem), hermanos.index(hasta.elem)
    if a > b:
        raise KitError.de("E030", f"{origen}: desde va después de hasta", desde.id)
    rango = hermanos[a : b + 1]
    for el in rango:
        if el.tag == W_SECTPR or (el.tag == W_P and el.find(f"{W_PPR}/{W_SECTPR}") is not None):
            raise KitError.de("E030", f"{origen}: el rango contiene un salto de sección", desde.id)
    return desde, hasta, (a, b)


# --------------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------------


@dataclass
class ResultadoBuild:
    ficheros: dict[str, bytes]  # nombre relativo en componentes/<slug>/ -> contenido
    lock: bytes
    lock_cambia: bool
    campos: int
    marcadores: int
    avisos: list[Fallo]


def restaurar_huecos(paquete, inventario: dict, nombres_partes: list[tuple[str, str]]) -> set[str]:
    """Devuelve los tokens ``huecos`` que ningún ``buscar`` usa a su ``original`` (en cada ``w:t``).

    Devuelve las partes modificadas. Cada token está entero en un ``w:t`` (lo escribe `preparar`).
    """
    buscados = [oc["buscar"] for c in inventario["campos"] for oc in c["ocurrencias"]]
    buscados += [
        col["buscar"]
        for b in inventario.get("bloques", [])
        if b["tipo"] == "tabla_repetible"
        for col in b["columnas"]
    ]
    sobrantes = {
        h["token"]: h["original"]
        for h in inventario.get("huecos", [])
        if not any(h["token"] in buscar for buscar in buscados)
    }
    modificadas: set[str] = set()
    if not sobrantes:
        return modificadas
    for parte, nombre in nombres_partes:
        for t in paquete.xml(nombre).iter(W_T):
            texto = t.text or ""
            for token, original in sobrantes.items():
                texto = texto.replace(token, original)
            if texto != (t.text or ""):
                escribir_texto(t, texto)
                modificadas.add(parte)
    return modificadas


def construir(raiz: Path, slug: str) -> ResultadoBuild:
    """Calcula todas las salidas en memoria. No escribe nada."""
    rutas = RutasPlantilla(raiz, slug)
    if not rutas.origen.is_file():
        raise KitError.de("E009", "no existe el origen", str(rutas.origen))
    inv = cargar_inventario(rutas, sha256_fichero(rutas.origen))
    dominio = cargar_dominio(rutas)
    paquete, parrafos = leer_origen(rutas.origen)
    por_id = {p.id: p for p in parrafos}
    nombres_partes = partes_texto(paquete)
    indice_parte = {parte: i for i, (parte, _) in enumerate(nombres_partes)}
    partes = set(indice_parte)

    # 1) Todas las coincidencias, sobre el texto original.
    coincidencias: list[Coincidencia] = []
    fallos: list[Fallo] = []
    for c in inv["campos"]:
        for j, oc in enumerate(c["ocurrencias"]):
            origen = f"campo {c['nombre']} / ocurrencia {j}"
            hallados, err = buscar_ocurrencia(parrafos, por_id, partes, oc, origen)
            fallos.extend(err)
            coincidencias.extend(
                Coincidencia(p, s, e, marcador(c["nombre"]), origen, c["nombre"])
                for p, s, e in hallados
            )
    tablas = []
    condicionales = []
    for i, b in enumerate(inv.get("bloques", [])):
        try:
            if b["tipo"] == "tabla_repetible":
                tid, tr, fila = resolver_tabla(b, parrafos, partes, i)
                tablas.append((b, tr, fila))
                fila_ids = {p.id for p in fila}
                for col in b["columnas"]:
                    origen = f"bloques/{i} columna {col['atributo']}"
                    oc = {"buscar": col["buscar"], "esperadas": 1, "regex": col.get("regex", False)}
                    hallados, err = buscar_ocurrencia(
                        [p for p in parrafos if p.id in fila_ids], por_id, partes, oc, origen
                    )
                    fallos.extend(err)
                    coincidencias.extend(
                        Coincidencia(
                            p, s, e, marcador(f"{VARIABLE_BUCLE}.{col['atributo']}"), origen, None
                        )
                        for p, s, e in hallados
                    )
            else:
                condicionales.append((b, *resolver_condicional(b, por_id, i)))
        except KitError as exc:
            fallos.extend(exc.fallos)
    # Solapes y tramos válidos.
    por_parrafo: dict[str, list[Coincidencia]] = defaultdict(list)
    for co in coincidencias:
        por_parrafo[co.par.id].append(co)
    for pid in sorted(
        por_parrafo, key=lambda x: por_id[x].orden + 10**7 * indice_parte[por_id[x].parte]
    ):
        lista = sorted(por_parrafo[pid], key=lambda c: (c.inicio, c.fin))
        for a, b in zip(lista, lista[1:], strict=False):
            if b.inicio < a.fin:
                fallos.append(
                    Fallo(
                        "E004",
                        f"{a.origen} [{a.inicio}:{a.fin}] solapa con {b.origen} [{b.inicio}:{b.fin}] "
                        f"en {a.par.texto[min(a.inicio, b.inicio) : max(a.fin, b.fin)]!r}",
                        pid,
                    )
                )
        par = por_id[pid]
        for co in lista:
            fallos.extend(comprobar_tramo(par, par.elem, co.inicio, co.fin, co.origen))
        if par.gemelo is False:
            fallos.append(Fallo("E011", "no se puede emparejar con su versión mc:Fallback", pid))
        elif par.gemelo is not None:
            texto_gemelo = "".join(t.t.text or "" for t in calcular_tramos(par.gemelo))
            if texto_gemelo != par.texto:
                fallos.append(
                    Fallo("E011", f"Fallback = {texto_gemelo!r}, principal = {par.texto!r}", pid)
                )
            else:
                for co in lista:
                    fallos.extend(
                        comprobar_tramo(
                            par, par.gemelo, co.inicio, co.fin, co.origen + " (Fallback)"
                        )
                    )
    # Condicionales anidados correctamente.
    for i, (bx, dx, _, (ax, zx)) in enumerate(condicionales):
        for by, dy, _, (ay, zy) in condicionales[i + 1 :]:
            if dx.elem.getparent() is not dy.elem.getparent():
                continue
            disjuntos = zx < ay or zy < ax
            anidados = (ax <= ay and zy <= zx) or (ay <= ax and zx <= zy)
            if not (disjuntos or anidados):
                fallos.append(
                    Fallo(
                        "E030",
                        f"los condicionales {bx['variable']} y {by['variable']} se cruzan",
                        dx.id,
                    )
                )
    if fallos:
        raise KitError(fallos)

    # 2) Aplicar sustituciones (orden inverso dentro de cada párrafo).
    partes_modificadas = set()
    for pid, lista in por_parrafo.items():
        par = por_id[pid]
        for co in sorted(lista, key=lambda c: c.inicio, reverse=True):
            sustituir(par.elem, co.inicio, co.fin, co.marcador)
            if par.gemelo is not None:
                sustituir(par.gemelo, co.inicio, co.fin, co.marcador)
        partes_modificadas.add(par.parte)

    # Huecos que ningún campo usa: vuelven a su original (tras sustituir, para no mover offsets).
    partes_modificadas |= restaurar_huecos(paquete, inv, nombres_partes)

    # 3) Bloques.
    for b, tr, fila in tablas:
        tr.addprevious(
            _fila_control(tr, "{%tr for " + VARIABLE_BUCLE + " in " + b["lista"] + " %}")
        )
        tr.addnext(_fila_control(tr, "{%tr endfor %}"))
        partes_modificadas.add(fila[0].parte)
    # Exteriores primero: así, con el mismo `desde`/`hasta`, el anidamiento queda bien.
    for b, desde, hasta, _rango in sorted(condicionales, key=lambda x: -(x[3][1] - x[3][0])):
        desde.elem.addprevious(_parrafo_simple("{%p if " + b["variable"] + " %}"))
        hasta.elem.addnext(_parrafo_simple("{%p endif %}"))
        partes_modificadas.add(desde.parte)
    for parte, nombre in nombres_partes:
        if parte in partes_modificadas:
            paquete.marcar_modificada(nombre)
    plantilla = paquete.a_bytes()

    # 4) IDs.
    lock_actual = cargar_lock(rutas.lock)
    ids, lock_nuevo = asignar_ids(inv, lock_actual, rutas.lock)
    lock_bytes = serialize.json_bytes(lock_nuevo, serialize.cargar_esquema("ids_lock"))
    lock_previo = rutas.lock.read_bytes() if rutas.lock.is_file() else b""

    # 5) fields.json.
    posicion: dict[str, tuple] = {}
    capitulo_de: dict[str, str | None] = {}

    def anotar(nombre: str, par: Parrafo, offset: int) -> None:
        clave = (indice_parte[par.parte], par.orden, offset)
        if nombre not in posicion or clave < posicion[nombre]:
            posicion[nombre] = clave
            capitulo_de[nombre] = par.capitulo

    for co in coincidencias:
        if co.campo is not None:
            anotar(co.campo, co.par, co.inicio)
    for b, _, fila in tablas:
        anotar(b["lista"], fila[0], -1)
    for b, desde, _, _ in condicionales:
        anotar(b["variable"], desde, -1)
    # Campo sin ocurrencias, solo usado por fórmulas: va justo antes del primero que lo usa.
    for c in inv["campos"]:
        for nombre in nombres_en_formula(c.get("formula")):
            if nombre not in posicion and c["nombre"] in posicion:
                posicion[nombre] = (*posicion[c["nombre"]][:2], -2)
                capitulo_de[nombre] = capitulo_de[c["nombre"]]
    unidades = {c["key"]: c.get("output_unit") for c in dominio["calculations"]}
    campos_ordenados = sorted(inv["campos"], key=lambda c: (posicion[c["nombre"]], c["nombre"]))
    por_capitulo: dict[str | None, int] = defaultdict(int)
    configs = []
    for c in campos_ordenados:
        capitulo = c["capitulo"] if "capitulo" in c else capitulo_de[c["nombre"]]
        orden = por_capitulo[capitulo]
        por_capitulo[capitulo] += 1
        configs.append(config_campo(c, ids[c["nombre"]], capitulo_de[c["nombre"]], orden, unidades))

    # El array va por número de FLD: estable entre builds y los campos nuevos quedan al final.
    configs.sort(key=lambda c: int(c["field_id"].split("-")[1]))
    ficheros = {"plantilla.docx": plantilla}
    ficheros["fields.json"] = serialize.json_bytes(configs, serialize.cargar_esquema("fields"))
    for nombre, _, salida in DOMINIOS:
        ficheros[salida] = serialize.json_bytes(dominio[nombre], serialize.cargar_esquema(nombre))
    return ResultadoBuild(
        ficheros=ficheros,
        lock=lock_bytes,
        lock_cambia=lock_bytes != lock_previo,
        campos=len(configs),
        marcadores=len(coincidencias),
        avisos=[],
    )


def build(raiz: Path, slug: str) -> ResultadoBuild:
    """Construye y escribe ``componentes/<slug>/`` e ``ids.lock.json``."""
    res = construir(raiz, slug)
    rutas = RutasPlantilla(raiz, slug)
    destino = rutas.componentes
    for nombre, datos in sorted(res.ficheros.items()):
        serialize.escribir_bytes(destino / nombre, datos)
    if res.lock_cambia:
        serialize.escribir_bytes(rutas.lock, res.lock)
    return res


def huellas(ficheros: dict[str, bytes]) -> dict[str, str]:
    return {n: hashlib.sha256(d).hexdigest() for n, d in sorted(ficheros.items())}
