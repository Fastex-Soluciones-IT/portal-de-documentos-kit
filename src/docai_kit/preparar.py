"""``docai-kit preparar``: Word del cliente -> ``origen.docx`` con huecos ``⟦hNNN⟧``.

El kit solo sustituye texto que ya existe. Un formulario tiene respuestas sin texto (celdas
vacías, casillas ☐, controles que muestran «Escribir aquí»), así que ``preparar`` escribe en
cada una un token propio, en su propio ``w:t``, y devuelve qué es cada token:

1. quita las marcas de ortografía (``w:proofErr``);
2. desenvuelve los controles de contenido (``w:sdt``); el marcador de un control que lo muestra
   (``w:showingPlcHdr``) pasa a ser un token ``control``;
3. cada carácter ☐/☒ pasa a ser un token ``casilla`` con el formato de su run;
4. cada celda sin texto (y que no continúa una combinación vertical) recibe un token ``celda``
   con el formato de su marca de párrafo.

La copia ``mc:Fallback`` de un cuadro de texto recibe la misma transformación y, al numerar, los
mismos tokens que su párrafo principal, así ``build`` sigue viendo los dos textos iguales.

Los tokens se numeran en el orden de recorrido del documento (el mismo de ``extract``), así que
el resultado es determinista. Las partes que no cambian se copian byte a byte.
"""

from __future__ import annotations

import copy
import itertools
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lxml import etree

from . import serialize
from .docx_io import (
    MC_FALLBACK,
    W_P,
    W_PPR,
    W_R,
    W_RPR,
    W_SDT,
    W_SDTCONTENT,
    W_T,
    W_TBL,
    W_TC,
    W_TR,
    W_TXBX,
    W_VAL,
    Paquete,
    Parrafo,
    calcular_tramos,
    escribir_texto,
    partes_texto,
    qn,
    recorrer,
    tiene_ancestro,
)
from .errors import KitError

TOKEN = re.compile(r"⟦h\d{3,}⟧")
CASILLAS = "☐☒"
_RE_CASILLA = re.compile(f"([{CASILLAS}])")
_PROVISIONAL = "⟦h⟧"  # texto del token hasta que se numera

W_SDTPR, W_SHOWING, W_PROOFERR = qn("w:sdtPr"), qn("w:showingPlcHdr"), qn("w:proofErr")
W_TCPR, W_TRPR, W_RSTYLE = qn("w:tcPr"), qn("w:trPr"), qn("w:rStyle")
W_GRIDSPAN, W_GRIDBEFORE, W_VMERGE = qn("w:gridSpan"), qn("w:gridBefore"), qn("w:vMerge")

# Contenido que hace que una celda sin texto no sea un hueco (logo, firma, símbolo, tabla).
_CELDA_OCUPADA = {qn(f"w:{x}") for x in ("drawing", "pict", "object", "sym", "tbl")}
# Hijos de la marca de párrafo (w:pPr/w:rPr) que un run no admite.
_SOLO_MARCA = {qn(f"w:{x}") for x in ("ins", "del", "moveFrom", "moveTo")}


@dataclass(frozen=True)
class Hueco:
    token: str
    original: str  # "" (celda/control) o el carácter de la casilla
    tipo: str  # "celda" | "casilla" | "control"
    parrafo: str  # id del párrafo en el docx preparado (el mismo que da extract)
    etiqueta: str | None  # texto antes del hueco o, si no hay, celda a la izquierda
    cabecera: str | None  # fila 0 en la misma columna de rejilla, si la fila 0 no tiene huecos
    grupo: str | None  # "G001"… para las casillas de un mismo párrafo
    opcion: str | None  # texto tras la casilla hasta el siguiente hueco

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Preparado:
    docx: bytes
    huecos: list[Hueco]


# --------------------------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------------------------


def _run_vacio(rpr: etree._Element | None) -> etree._Element:
    run = etree.Element(W_R)
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    return run


def _run(texto: str, rpr: etree._Element | None) -> etree._Element:
    run = _run_vacio(rpr)
    escribir_texto(etree.SubElement(run, W_T), texto)
    return run


def _sin_contenido(run: etree._Element) -> bool:
    return all(hijo.tag == W_RPR for hijo in run)


def _quitar_si_vacio(run: etree._Element) -> None:
    if _sin_contenido(run):
        run.getparent().remove(run)


# --------------------------------------------------------------------------------------------
# 1–2. Marcas de ortografía y controles de contenido
# --------------------------------------------------------------------------------------------


def _quitar_proof_err(raiz: etree._Element) -> int:
    marcas = list(raiz.iter(W_PROOFERR))
    for marca in marcas:
        marca.getparent().remove(marca)
    return len(marcas)


def _rpr_control(sdt: etree._Element, run: etree._Element) -> etree._Element | None:
    """Formato del contenido del control; si no lo declara, el del marcador sin su estilo."""
    propio = sdt.find(f"{W_SDTPR}/{W_RPR}")
    if propio is not None:
        return propio
    rpr = run.find(W_RPR)
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for estilo in rpr.findall(W_RSTYLE):
        rpr.remove(estilo)
    return rpr


def _marcador_a_token(sdt: etree._Element, tipos: dict) -> None:
    contenido = sdt.find(W_SDTCONTENT)
    textos = [t for t in contenido.iter(W_T) if t.getparent().tag == W_R]
    if not textos:
        return
    primero = textos[0].getparent()
    token = _run(_PROVISIONAL, _rpr_control(sdt, primero))
    primero.addprevious(token)
    tipos[token.find(W_T)] = ("control", "")
    for t in textos:
        run = t.getparent()
        run.remove(t)
        _quitar_si_vacio(run)


def _desenvolver(sdt: etree._Element) -> None:
    contenido = sdt.find(W_SDTCONTENT)
    if contenido is not None:
        for hijo in list(contenido):
            sdt.addprevious(hijo)
    sdt.getparent().remove(sdt)


def _desenvolver_controles(raiz: etree._Element, tipos: dict) -> int:
    controles = list(raiz.iter(W_SDT))
    for sdt in controles:
        marcador = sdt.find(f"{W_SDTPR}/{W_SHOWING}") is not None
        if marcador and sdt.find(W_SDTCONTENT) is not None:
            _marcador_a_token(sdt, tipos)
        _desenvolver(sdt)
    return len(controles)


# --------------------------------------------------------------------------------------------
# 3. Casillas
# --------------------------------------------------------------------------------------------


def _partir_casillas_de(t: etree._Element, tipos: dict) -> None:
    """Parte el run de ``t``: un run por casilla (token) y por tramo de texto entre ellas."""
    run = t.getparent()
    rpr = run.find(W_RPR)
    resto = list(t.itersiblings())
    anterior = run
    for trozo in (x for x in _RE_CASILLA.split(t.text) if x):
        nuevo = _run(_PROVISIONAL if trozo in CASILLAS else trozo, rpr)
        if trozo in CASILLAS:
            tipos[nuevo.find(W_T)] = ("casilla", trozo)
        anterior.addnext(nuevo)
        anterior = nuevo
    if resto:
        cola = _run_vacio(rpr)
        cola.extend(resto)
        anterior.addnext(cola)
    run.remove(t)
    _quitar_si_vacio(run)


def _partir_casillas(raiz: etree._Element, tipos: dict) -> None:
    for t in list(raiz.iter(W_T)):
        con_casilla = t.text is not None and _RE_CASILLA.search(t.text)
        if con_casilla and t.getparent().tag == W_R:
            _partir_casillas_de(t, tipos)


# --------------------------------------------------------------------------------------------
# 4. Celdas vacías
# --------------------------------------------------------------------------------------------


def _continua_combinada(tc: etree._Element) -> bool:
    vmerge = tc.find(f"{W_TCPR}/{W_VMERGE}")
    return vmerge is not None and vmerge.get(W_VAL, "continue") == "continue"


def _celda_vacia(tc: etree._Element, tipos: dict) -> bool:
    for el in tc.iter():
        if el.tag in _CELDA_OCUPADA or el in tipos:
            return False
        if el.tag == W_T and (el.text or "").strip():
            return False
    return True


def _rpr_marca(p: etree._Element) -> etree._Element | None:
    rpr = p.find(f"{W_PPR}/{W_RPR}")
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for hijo in [h for h in rpr if h.tag in _SOLO_MARCA]:
        rpr.remove(hijo)
    return rpr


def _marcar_celdas_vacias(raiz: etree._Element, tipos: dict) -> None:
    for tc in list(raiz.iter(W_TC)):
        p = tc.find(W_P)
        if p is None or _continua_combinada(tc):
            continue
        if _celda_vacia(tc, tipos):
            token = _run(_PROVISIONAL, _rpr_marca(p))
            p.append(token)
            tipos[token.find(W_T)] = ("celda", "")


def _preparar_parte(raiz: etree._Element, tipos: dict) -> bool:
    """Escribe los tokens provisionales de una parte. Devuelve si la parte ha cambiado."""
    antes = len(tipos)
    cambios = _quitar_proof_err(raiz) + _desenvolver_controles(raiz, tipos)
    _partir_casillas(raiz, tipos)
    _marcar_celdas_vacias(raiz, tipos)
    return cambios > 0 or len(tipos) > antes


# --------------------------------------------------------------------------------------------
# Etiquetas: texto alrededor del hueco y rejilla de la tabla
# --------------------------------------------------------------------------------------------


def _limpio(texto: str) -> str | None:
    """Sin tokens, con los espacios colapsados y sin «:» ni espacios en los extremos."""
    limpio = " ".join(TOKEN.sub(" ", texto).split()).strip(" :")
    return limpio or None


def _texto_celda(tc: etree._Element) -> str | None:
    trozos = [
        " " if el.tag == W_P else el.text or ""
        for el in tc.iter(W_P, W_T)
        if not tiene_ancestro(el, tc, {MC_FALLBACK})
    ]
    return _limpio("".join(trozos))


def _con_huecos(el: etree._Element, tipos: dict) -> bool:
    return any(t in tipos for t in el.iter(W_T))


def _entero(el: etree._Element | None, defecto: int) -> int:
    valor = el.get(W_VAL, "") if el is not None else ""
    return int(valor) if valor.isdigit() else defecto


def _rejilla(tr: etree._Element) -> list[tuple[int, int, etree._Element]]:
    """``[(columna_inicial, columna_final, tc)]`` de una fila según ``gridBefore``/``gridSpan``."""
    columna = _entero(tr.find(f"{W_TRPR}/{W_GRIDBEFORE}"), 0)
    celdas = []
    for tc in tr.findall(W_TC):
        fin = columna + _entero(tc.find(f"{W_TCPR}/{W_GRIDSPAN}"), 1)
        celdas.append((columna, fin, tc))
        columna = fin
    return celdas


@dataclass
class _Celda:
    tc: etree._Element
    tr: etree._Element
    tbl: etree._Element

    @classmethod
    def de(cls, p: etree._Element) -> _Celda | None:
        actual = p.getparent()
        while actual is not None and actual.tag not in (W_TC, W_TXBX):
            actual = actual.getparent()
        if actual is None or actual.tag != W_TC:
            return None
        tr = actual.getparent()
        tbl = tr.getparent() if tr is not None else None
        if tbl is None or tr.tag != W_TR or tbl.tag != W_TBL:
            return None
        return cls(actual, tr, tbl)

    def _columna(self) -> int:
        return next(inicio for inicio, _, tc in _rejilla(self.tr) if tc is self.tc)

    def etiqueta(self, tipos: dict) -> str | None:
        """Texto de la celda más cercana a la izquierda que tiene texto y ningún hueco."""
        columna = self._columna()
        izquierda = [
            tc
            for inicio, _, tc in _rejilla(self.tr)
            if inicio < columna and not _con_huecos(tc, tipos)
        ]
        return next((t for t in map(_texto_celda, reversed(izquierda)) if t), None)

    def cabecera(self, tipos: dict) -> str | None:
        fila0 = self.tbl.find(W_TR)
        if fila0 is self.tr or _con_huecos(fila0, tipos):
            return None
        columna = self._columna()
        return next(
            (_texto_celda(tc) for inicio, fin, tc in _rejilla(fila0) if inicio <= columna < fin),
            None,
        )


# --------------------------------------------------------------------------------------------
# Huecos
# --------------------------------------------------------------------------------------------


def _tokens_de(p: etree._Element | None, tipos: dict) -> list[etree._Element]:
    if p is None or p is False:
        return []
    return [tr.t for tr in calcular_tramos(p) if tr.t in tipos]


def _numerar(parrafos: list[Parrafo], tipos: dict) -> None:
    """Numera los tokens en orden de recorrido; la copia ``mc:Fallback`` lleva los mismos."""
    n = 0
    for par in parrafos:
        gemelos = _tokens_de(par.gemelo, tipos)
        for i, tr in enumerate(tr for tr in par.tramos if tr.t in tipos):
            n += 1
            tr.t.text = f"⟦h{n:03d}⟧"
            if i < len(gemelos):
                gemelos[i].text = tr.t.text
    # Los tokens de una copia Fallback sin pareja vuelven a su texto original.
    for t, (_, original) in tipos.items():
        if t.text == _PROVISIONAL:
            escribir_texto(t, original)


def _segmentos(par: Parrafo, tipos: dict) -> list:
    """El párrafo como lista de textos (``str``) y tokens (``w:t``), con los textos unidos."""
    segmentos: list = []
    for tr in par.tramos:
        if tr.t in tipos:
            segmentos.append(tr.t)
        elif segmentos and isinstance(segmentos[-1], str):
            segmentos[-1] += tr.t.text or ""
        else:
            segmentos.append(tr.t.text or "")
    return segmentos


def _vecino(segmentos: list, i: int) -> str | None:
    if 0 <= i < len(segmentos) and isinstance(segmentos[i], str):
        return _limpio(segmentos[i])
    return None


def _huecos_de_parrafo(par: Parrafo, tipos: dict, grupos: itertools.count) -> list[Hueco]:
    segmentos = _segmentos(par, tipos)
    posiciones = [i for i, s in enumerate(segmentos) if not isinstance(s, str)]
    if not posiciones:
        return []
    casillas = [i for i in posiciones if tipos[segmentos[i]][0] == "casilla"]
    grupo = f"G{next(grupos):03d}" if casillas else None
    celda = _Celda.de(par.elem)
    izquierda = celda.etiqueta(tipos) if celda else None
    cabecera = celda.cabecera(tipos) if celda else None
    huecos = []
    for i in posiciones:
        tipo, original = tipos[segmentos[i]]
        es_casilla = tipo == "casilla"
        antes = _vecino(segmentos, (casillas[0] if es_casilla else i) - 1)
        huecos.append(
            Hueco(
                token=segmentos[i].text,
                original=original,
                tipo=tipo,
                parrafo=par.id,
                etiqueta=antes or izquierda,
                cabecera=cabecera,
                grupo=grupo if es_casilla else None,
                opcion=_vecino(segmentos, i + 1) if es_casilla else None,
            )
        )
    return huecos


def preparar(origen: bytes) -> Preparado:
    paquete = Paquete.abrir(origen)
    tipos: dict[etree._Element, tuple[str, str]] = {}  # w:t del token -> (tipo, original)
    modificadas = [n for _, n in partes_texto(paquete) if _preparar_parte(paquete.xml(n), tipos)]
    parrafos = recorrer(paquete)
    _numerar(parrafos, tipos)
    grupos = itertools.count(1)
    huecos = [h for par in parrafos for h in _huecos_de_parrafo(par, tipos, grupos)]
    for nombre in modificadas:
        paquete.marcar_modificada(nombre)
    return Preparado(paquete.a_bytes(), huecos)


def preparar_plantilla(raiz: Path, slug: str) -> tuple[Path, Path, Preparado]:
    """``plantillas/<slug>/word_original.docx`` -> ``origen.docx`` + ``trabajo/<slug>/huecos.json``."""
    fuente = raiz / "plantillas" / slug
    original = fuente / "word_original.docx"
    if not original.is_file():
        raise KitError.de("E009", "no existe el fichero", str(original))
    prep = preparar(original.read_bytes())
    origen = fuente / "origen.docx"
    huecos = raiz / "trabajo" / slug / "huecos.json"
    serialize.escribir_bytes(origen, prep.docx)
    serialize.escribir_json(huecos, [h.como_dict() for h in prep.huecos])
    return origen, huecos, prep
