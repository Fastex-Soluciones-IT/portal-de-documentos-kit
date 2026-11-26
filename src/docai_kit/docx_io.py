"""Lectura/escritura byte-estable de ``.docx`` y recorrido estructural de párrafos.

Un ``.docx`` es un ZIP. Al guardarlo:

- las entradas se escriben en el mismo orden que en el origen;
- todas llevan ``date_time=(1980,1,1,0,0,0)``, ``create_system=0`` y ``external_attr=0``;
- cada entrada conserva su método de compresión original;
- las partes que no se han tocado se copian byte a byte (``docProps/core.xml`` incluido, así que
  las fechas del origen se conservan tal cual).

El recorrido de párrafos asigna a cada uno un localizador estable derivado de su posición:
``document/p/0042``, ``document/tbl/03/r/02/c/01/p/00``, ``header2/p/0001``,
``document/p/0007/txbx/00/p/00``.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .errors import KitError

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def qn(etiqueta: str) -> str:
    prefijo, local = etiqueta.split(":")
    ns = {"w": W_NS, "mc": MC_NS, "xml": XML_NS}[prefijo]
    return f"{{{ns}}}{local}"


W_P, W_R, W_T, W_TBL, W_TR, W_TC = (qn(f"w:{x}") for x in ("p", "r", "t", "tbl", "tr", "tc"))
W_SDT, W_SDTCONTENT, W_TXBX = qn("w:sdt"), qn("w:sdtContent"), qn("w:txbxContent")
W_PPR, W_RPR, W_PSTYLE, W_OUTLINE = qn("w:pPr"), qn("w:rPr"), qn("w:pStyle"), qn("w:outlineLvl")
W_SECTPR, W_DRAWING, W_FLDCHAR = qn("w:sectPr"), qn("w:drawing"), qn("w:fldChar")
W_VAL = qn("w:val")
MC_ALT, MC_CHOICE, MC_FALLBACK = qn("mc:AlternateContent"), qn("mc:Choice"), qn("mc:Fallback")
XML_SPACE = qn("xml:space")

# Contenido de run que no es texto: una coincidencia no puede cruzarlo.
NO_TEXTO = {
    qn(f"w:{x}")
    for x in (
        "tab",
        "br",
        "cr",
        "ptab",
        "sym",
        "drawing",
        "pict",
        "object",
        "fldChar",
        "instrText",
        "footnoteReference",
        "endnoteReference",
        "commentReference",
        "noBreakHyphen",
        "softHyphen",
    )
}

# Marcas de control de cambios (contenido y formato).
REVISIONES = {
    qn(f"w:{x}")
    for x in (
        "ins",
        "del",
        "moveFrom",
        "moveTo",
        "rPrChange",
        "pPrChange",
        "sectPrChange",
        "tblPrChange",
        "trPrChange",
        "tcPrChange",
        "tblGridChange",
        "numberingChange",
        "cellIns",
        "cellDel",
        "cellMerge",
    )
}

FECHA_ZIP = (1980, 1, 1, 0, 0, 0)

_PARSER = etree.XMLParser(remove_blank_text=False, resolve_entities=False, huge_tree=True)


def sha256_fichero(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------------
# Paquete ZIP
# --------------------------------------------------------------------------------------------


@dataclass
class _Entrada:
    nombre: str
    compresion: int
    datos: bytes


class Paquete:
    """Contenido de un ``.docx`` en memoria, con las partes XML parseadas bajo demanda."""

    def __init__(self, entradas: list[_Entrada]):
        self._entradas = entradas
        self._indice = {e.nombre: e for e in entradas}
        self._arboles: dict[str, etree._Element] = {}

    @classmethod
    def abrir(cls, origen: Path | bytes) -> Paquete:
        datos = origen if isinstance(origen, bytes) else origen.read_bytes()
        with zipfile.ZipFile(io.BytesIO(datos)) as zf:
            entradas = [_Entrada(i.filename, i.compress_type, zf.read(i)) for i in zf.infolist()]
        return cls(entradas)

    def nombres(self) -> list[str]:
        return [e.nombre for e in self._entradas]

    def tiene(self, nombre: str) -> bool:
        return nombre in self._indice

    def datos(self, nombre: str) -> bytes:
        return self._indice[nombre].datos

    def reemplazar(self, nombre: str, datos: bytes) -> None:
        self._arboles.pop(nombre, None)
        self._indice[nombre].datos = datos

    def xml(self, nombre: str) -> etree._Element:
        """Árbol XML de una parte. Las modificaciones se vuelcan al guardar."""
        if nombre not in self._arboles:
            self._arboles[nombre] = etree.fromstring(self._indice[nombre].datos, _PARSER)
        return self._arboles[nombre]

    def marcar_modificada(self, nombre: str) -> None:
        arbol = self.xml(nombre)
        self._indice[nombre].datos = etree.tostring(
            arbol, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    def a_bytes(self) -> bytes:
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w") as zf:
            for e in self._entradas:
                info = zipfile.ZipInfo(e.nombre, date_time=FECHA_ZIP)
                info.compress_type = e.compresion
                info.create_system = 0
                info.external_attr = 0
                zf.writestr(info, e.datos)
        return salida.getvalue()


# --------------------------------------------------------------------------------------------
# Partes con texto
# --------------------------------------------------------------------------------------------

_RE_HF = re.compile(r"^word/(header|footer)(\d+)\.xml$")


def partes_texto(paquete: Paquete) -> list[tuple[str, str]]:
    """``[(id_parte, nombre_zip)]`` en el orden fijo: document, header*, footer*, footnotes, endnotes."""
    if not paquete.tiene("word/document.xml"):
        raise KitError.de("E012", "el paquete no tiene word/document.xml")
    partes = [("document", "word/document.xml")]
    for tipo in ("header", "footer"):
        encontrados = []
        for nombre in paquete.nombres():
            m = _RE_HF.match(nombre)
            if m and m.group(1) == tipo:
                encontrados.append((int(m.group(2)), nombre))
        partes.extend((f"{tipo}{n}", nombre) for n, nombre in sorted(encontrados))
    for tipo in ("footnotes", "endnotes"):
        if paquete.tiene(f"word/{tipo}.xml"):
            partes.append((tipo, f"word/{tipo}.xml"))
    return partes


# --------------------------------------------------------------------------------------------
# Estilos (para heading_level)
# --------------------------------------------------------------------------------------------

_RE_TITULO = re.compile(
    r"^(heading|t[ií]tulo|titre|[uü]berschrift|titolo|rubrik|kop)\s?([1-9])$", re.IGNORECASE
)


@dataclass(frozen=True)
class _Estilo:
    nombre: str
    nivel: int | None


class Estilos:
    def __init__(self, paquete: Paquete):
        self._por_id: dict[str, _Estilo] = {}
        self.defecto: str | None = None
        if not paquete.tiene("word/styles.xml"):
            return
        for st in paquete.xml("word/styles.xml").findall(qn("w:style")):
            if st.get(qn("w:type")) != "paragraph":
                continue
            sid = st.get(qn("w:styleId"))
            nombre_el = st.find(qn("w:name"))
            nombre = nombre_el.get(W_VAL) if nombre_el is not None else sid
            nivel = None
            m = _RE_TITULO.match(nombre or "")
            if m:
                nivel = int(m.group(2))
            else:
                # Igual que el analizador de DocAI: outlineLvl del propio estilo.
                lvl = st.find(f"{W_PPR}/{W_OUTLINE}")
                if lvl is not None and lvl.get(W_VAL, "").isdigit() and int(lvl.get(W_VAL)) < 9:
                    nivel = int(lvl.get(W_VAL)) + 1
            self._por_id[sid] = _Estilo(nombre, nivel)
            if st.get(qn("w:default")) in ("1", "true"):
                self.defecto = sid

    def de_parrafo(self, p: etree._Element) -> tuple[str | None, int | None]:
        ppr = p.find(W_PPR)
        sid = None
        nivel_directo = None
        if ppr is not None:
            ps = ppr.find(W_PSTYLE)
            if ps is not None:
                sid = ps.get(W_VAL)
            lvl = ppr.find(W_OUTLINE)
            if lvl is not None and lvl.get(W_VAL, "").isdigit() and int(lvl.get(W_VAL)) < 9:
                nivel_directo = int(lvl.get(W_VAL)) + 1
        sid = sid or self.defecto
        estilo = self._por_id.get(sid) if sid else None
        nombre = estilo.nombre if estilo else sid
        nivel = nivel_directo if nivel_directo is not None else (estilo.nivel if estilo else None)
        return nombre, nivel


# --------------------------------------------------------------------------------------------
# Párrafos
# --------------------------------------------------------------------------------------------


@dataclass
class Tramo:
    """Un ``w:t`` dentro del texto del párrafo: ocupa ``[inicio, fin)``."""

    t: etree._Element
    inicio: int
    fin: int
    en_campo: bool  # dentro del resultado de un campo complejo de Word


@dataclass
class Parrafo:
    id: str
    parte: str
    contenedor: str  # localizador del contenedor (cuerpo, celda, cuadro de texto)
    orden: int  # posición del párrafo en el recorrido de su parte
    elem: etree._Element
    en_celda: bool
    gemelo: etree._Element | None = None  # copia en mc:Fallback de un cuadro de texto
    estilo: str | None = None
    nivel: int | None = None
    capitulo: str | None = None
    tramos: list[Tramo] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "".join(tr.t.text or "" for tr in self.tramos)


def _hijos_inline(el: etree._Element):
    """Recorre el contenido inline de un párrafo en orden de documento.

    Emite ``("t", w:t)`` para texto y ``("x", elem)`` para contenido no textual. No entra en
    párrafos anidados (cuadros de texto) ni en ``mc:Fallback``.
    """
    for hijo in el:
        etiqueta = hijo.tag
        if not isinstance(etiqueta, str) or etiqueta in (W_P, MC_FALLBACK, W_PPR, W_RPR):
            continue
        if etiqueta == W_T:
            yield "t", hijo
        elif etiqueta in NO_TEXTO:
            yield "x", hijo
        else:
            yield from _hijos_inline(hijo)


def calcular_tramos(p: etree._Element) -> list[Tramo]:
    tramos = []
    pos = 0
    profundidad_campo = 0
    for tipo, el in _hijos_inline(p):
        if tipo == "x":
            if el.tag == W_FLDCHAR:
                clase = el.get(qn("w:fldCharType"))
                if clase == "begin":
                    profundidad_campo += 1
                elif clase == "end":
                    profundidad_campo = max(0, profundidad_campo - 1)
            continue
        largo = len(el.text or "")
        tramos.append(Tramo(el, pos, pos + largo, profundidad_campo > 0))
        pos += largo
    return tramos


def elementos_no_texto_entre(p: etree._Element, desde: etree._Element, hasta: etree._Element):
    """Contenido no textual que hay entre dos ``w:t`` del mismo párrafo."""
    dentro = False
    encontrados = []
    for tipo, el in _hijos_inline(p):
        if el is desde:
            dentro = True
            continue
        if el is hasta:
            break
        if dentro and tipo == "x":
            encontrados.append(el)
    return encontrados


def tiene_ancestro(el: etree._Element, tope: etree._Element, etiquetas: set[str]) -> bool:
    actual = el.getparent()
    while actual is not None and actual is not tope:
        if actual.tag in etiquetas:
            return True
        actual = actual.getparent()
    return False


def _cuadros_de_texto(p: etree._Element) -> list[tuple[etree._Element, etree._Element | None]]:
    """``[(txbxContent, gemelo_fallback)]`` directos de un párrafo (no anidados, no Fallback)."""
    salida = []
    for tx in p.iter(W_TXBX):
        if tiene_ancestro(tx, p, {MC_FALLBACK, W_TXBX}):
            continue
        gemelo = None
        # ¿Está en un mc:Choice? Entonces su gemelo es el txbx con el mismo índice en el Fallback.
        actual = tx.getparent()
        while actual is not None and actual is not p and actual.tag != MC_CHOICE:
            actual = actual.getparent()
        if actual is not None and actual.tag == MC_CHOICE:
            alt = actual.getparent()
            fallback = alt.find(MC_FALLBACK) if alt is not None else None
            if fallback is not None:
                propios = [
                    t for t in actual.iter(W_TXBX) if not tiene_ancestro(t, actual, {W_TXBX})
                ]
                ajenos = [
                    t for t in fallback.iter(W_TXBX) if not tiene_ancestro(t, fallback, {W_TXBX})
                ]
                # False marca un Fallback incoherente (distinto número de cuadros).
                gemelo = ajenos[propios.index(tx)] if len(propios) == len(ajenos) else False
        salida.append((tx, gemelo))
    return salida


def _fmt(n: int, ancho: int) -> str:
    return f"{n:0{ancho}d}"


class _Recorrido:
    def __init__(self, parte: str, estilos: Estilos):
        self.parte = parte
        self.estilos = estilos
        self.parrafos: list[Parrafo] = []
        self.incoherentes: list[str] = []  # cuadros de texto con Fallback incoherente

    def contenedor(self, cont, prefijo, raiz, en_celda, gemelo_cont):
        """Recorre los bloques de ``cont``. Si ``gemelo_cont`` existe, lo recorre en paralelo."""
        cuenta = {"p": 0, "tbl": 0, "sdt": 0}
        hijos_g = list(gemelo_cont) if gemelo_cont is not None else None
        g_cuenta = {"p": 0, "tbl": 0, "sdt": 0}

        def gemelo_de(tipo):
            if hijos_g is None:
                return None
            etiqueta = {"p": W_P, "tbl": W_TBL, "sdt": W_SDT}[tipo]
            del_tipo = [h for h in hijos_g if h.tag == etiqueta]
            i = g_cuenta[tipo]
            g_cuenta[tipo] += 1
            return del_tipo[i] if i < len(del_tipo) else None

        for hijo in cont:
            if hijo.tag == W_P:
                pid = f"{prefijo}/p/{_fmt(cuenta['p'], 4 if raiz else 2)}"
                cuenta["p"] += 1
                g = gemelo_de("p")
                if hijos_g is not None and g is None:
                    self.incoherentes.append(pid)
                self.parrafo(hijo, pid, prefijo, en_celda, g)
            elif hijo.tag == W_TBL:
                tid = f"{prefijo}/tbl/{_fmt(cuenta['tbl'], 2)}"
                cuenta["tbl"] += 1
                g = gemelo_de("tbl")
                self.tabla(hijo, tid, g)
            elif hijo.tag == W_SDT:
                sid = f"{prefijo}/sdt/{_fmt(cuenta['sdt'], 2)}"
                cuenta["sdt"] += 1
                g = gemelo_de("sdt")
                contenido = hijo.find(W_SDTCONTENT)
                if contenido is not None:
                    g_contenido = g.find(W_SDTCONTENT) if g is not None else None
                    self.contenedor(contenido, sid, False, en_celda, g_contenido)

    def tabla(self, tbl, tid, g_tbl):
        g_filas = g_tbl.findall(W_TR) if g_tbl is not None else None
        for r, tr in enumerate(tbl.findall(W_TR)):
            g_tr = g_filas[r] if g_filas is not None and r < len(g_filas) else None
            g_celdas = g_tr.findall(W_TC) if g_tr is not None else None
            for c, tc in enumerate(tr.findall(W_TC)):
                g_tc = g_celdas[c] if g_celdas is not None and c < len(g_celdas) else None
                self.contenedor(tc, f"{tid}/r/{_fmt(r, 2)}/c/{_fmt(c, 2)}", False, True, g_tc)

    def parrafo(self, p, pid, contenedor, en_celda, gemelo):
        estilo, nivel = self.estilos.de_parrafo(p)
        par = Parrafo(
            id=pid,
            parte=self.parte,
            contenedor=contenedor,
            orden=len(self.parrafos),
            elem=p,
            en_celda=en_celda,
            gemelo=gemelo,
            estilo=estilo,
            nivel=nivel,
            tramos=calcular_tramos(p),
        )
        self.parrafos.append(par)
        cuadros = _cuadros_de_texto(p)
        for k, (tx, g_tx) in enumerate(cuadros):
            prefijo = f"{pid}/txbx/{_fmt(k, 2)}"
            if g_tx is False:
                self.incoherentes.append(prefijo)
                g_tx = None
            self.contenedor(tx, prefijo, False, en_celda, g_tx)


def recorrer_parte(
    paquete: Paquete, parte: str, nombre_zip: str, estilos: Estilos
) -> list[Parrafo]:
    raiz = paquete.xml(nombre_zip)
    cuerpo = raiz.find(qn("w:body")) if parte == "document" else raiz
    if cuerpo is None:
        raise KitError.de("E012", "document.xml sin w:body", parte)
    rec = _Recorrido(parte, estilos)
    if parte in ("footnotes", "endnotes"):
        # Cada nota es un contenedor propio: footnotes/n/03/p/00
        etiqueta = qn("w:footnote") if parte == "footnotes" else qn("w:endnote")
        for i, nota in enumerate(raiz.findall(etiqueta)):
            rec.contenedor(nota, f"{parte}/n/{_fmt(i, 2)}", False, False, None)
    else:
        rec.contenedor(cuerpo, parte, True, False, None)
    # Todo w:t (salvo los de mc:Fallback) debe pertenecer a algún párrafo recorrido.
    cubiertos = {id(tr.t) for par in rec.parrafos for tr in par.tramos}
    for t in raiz.iter(W_T):
        if id(t) in cubiertos or tiene_ancestro(t, raiz, {MC_FALLBACK}):
            continue
        ruta = raiz.getroottree().getpath(t)
        raise KitError.de(
            "E012", f"texto {t.text!r} fuera de los párrafos reconocidos", f"{parte}:{ruta}"
        )
    if rec.incoherentes:
        # Solo es un problema si se modifica; se informa al aplicar (E011).
        for par in rec.parrafos:
            if any(par.id.startswith(x) for x in rec.incoherentes):
                par.gemelo = False  # type: ignore[assignment]
    return rec.parrafos


def revisiones(paquete: Paquete) -> list[str]:
    """Ubicaciones de marcas de control de cambios en las partes con texto."""
    encontradas = []
    for parte, nombre in partes_texto(paquete):
        raiz = paquete.xml(nombre)
        for el in raiz.iter():
            if el.tag in REVISIONES:
                encontradas.append(f"{parte}:{raiz.getroottree().getpath(el)}")
    return encontradas


def recorrer(paquete: Paquete) -> list[Parrafo]:
    """Todos los párrafos de todas las partes, en el orden fijo, con su capítulo."""
    estilos = Estilos(paquete)
    todos: list[Parrafo] = []
    for parte, nombre in partes_texto(paquete):
        parrafos = recorrer_parte(paquete, parte, nombre, estilos)
        if parte == "document":
            capitulo = None
            for par in parrafos:
                # Como el analizador de DocAI: solo un Título 1 del cuerpo redefine el capítulo.
                if par.nivel == 1 and not par.en_celda and "/txbx/" not in par.id:
                    capitulo = par.texto.strip() or None
                par.capitulo = capitulo
        todos.extend(parrafos)
    return todos


def escribir_texto(t: etree._Element, texto: str) -> None:
    t.text = texto
    if texto != texto.strip():
        t.set(XML_SPACE, "preserve")
