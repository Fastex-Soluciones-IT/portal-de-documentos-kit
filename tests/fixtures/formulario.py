"""Constructor en memoria de un formulario Word de prueba para ``docai-kit preparar``.

Cada parte se escribe como XML y se valida con lxml antes de empaquetarla, para controlar
exactamente los runs, los controles de contenido y las celdas combinadas.
"""

from __future__ import annotations

import io
import zipfile

from fixtures.generar import cuadro_de_texto
from lxml import etree

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'mc:Ignorable="w14 wps"'
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

RPR_CASILLA = '<w:rPr><w:rFonts w:ascii="MS Gothic" w:hAnsi="MS Gothic"/></w:rPr>'
RPR_MARCA = '<w:rPr><w:color w:val="003263"/><w:sz w:val="17"/></w:rPr>'


def r(texto: str) -> str:
    espacio = ' xml:space="preserve"' if texto != texto.strip() else ""
    return f"<w:r><w:t{espacio}>{texto}</w:t></w:r>"


def p(*contenido: str) -> str:
    return f"<w:p>{''.join(contenido)}</w:p>"


def p_vacio() -> str:
    """Párrafo vacío cuya marca de párrafo tiene formato propio."""
    return f"<w:p><w:pPr>{RPR_MARCA}</w:pPr></w:p>"


def tc(contenido: str, tcpr: str = "") -> str:
    return f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/>{tcpr}</w:tcPr>{contenido}</w:tc>'


def tabla(columnas: int, *filas: str) -> str:
    rejilla = '<w:gridCol w:w="2000"/>' * columnas
    cuerpo = "".join(f"<w:tr>{fila}</w:tr>" for fila in filas)
    return f"<w:tbl><w:tblPr/><w:tblGrid>{rejilla}</w:tblGrid>{cuerpo}</w:tbl>"


def casilla(marca: str = "☐") -> str:
    return (
        '<w:sdt><w:sdtPr><w:id w:val="1"/><w14:checkbox><w14:checked w14:val="0"/></w14:checkbox>'
        f"</w:sdtPr><w:sdtContent><w:r>{RPR_CASILLA}<w:t>{marca}</w:t></w:r></w:sdtContent></w:sdt>"
    )


def control_con_marcador(texto: str) -> str:
    return (
        '<w:sdt><w:sdtPr><w:rPr><w:b/></w:rPr><w:id w:val="2"/><w:showingPlcHdr/><w:text/></w:sdtPr>'
        '<w:sdtContent><w:r><w:rPr><w:rStyle w:val="PlaceholderText"/></w:rPr>'
        f"<w:t>{texto}</w:t></w:r></w:sdtContent></w:sdt>"
    )


def cuerpo_formulario() -> str:
    titulo = p(
        r("Formulario"),
        '<w:proofErr w:type="spellStart"/>',
        r(" de visita"),
        '<w:proofErr w:type="spellEnd"/>',
    )
    equipos = tabla(
        3,
        tc(p(r("Equipo"))) + tc(p(r("Modelo"))) + tc(p(r("Nº"))),
        tc(p(r("Inversores"))) + tc(p_vacio()) + tc(p_vacio()),
    )
    partes = tabla(
        5,
        tc(p(r("Titular")), '<w:gridSpan w:val="2"/>')
        + tc(p_vacio())
        + tc(p(r("Promotor")))
        + tc(p_vacio()),
    )
    combinada = tabla(
        2,
        tc(p(r("Bloque")), '<w:vMerge w:val="restart"/>') + tc(p(r("Dato A"))),
        tc(p_vacio(), "<w:vMerge/>") + tc(p(r("Dato B"))),
    )
    acoplamiento = tabla(
        2,
        tc(p(r("Acoplamiento")))
        + tc(p(casilla(), r(" CC (inversor híbrido) "), casilla(), r(" CA"))),
    )
    observaciones = p(r("Observaciones: "), control_con_marcador("Escribir aquí"))
    return titulo + equipos + partes + combinada + acoplamiento + observaciones


def cuerpo_sin_huecos() -> str:
    return p(r("Informe técnico")) + tabla(2, tc(p(r("Potencia"))) + tc(p(r("10 kW"))))


def cuerpo_cuadro_de_texto() -> str:
    """Cuadro de texto DrawingML con casillas y su copia VML en ``mc:Fallback``."""
    return cuadro_de_texto(p(r("Pregunta "), casilla(), r(" Sí ☐ No")))


def docx(cuerpo: str) -> bytes:
    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document {NS}><w:body>{cuerpo}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        "</w:sectPr></w:body></w:document>"
    )
    etree.fromstring(documento.encode("utf-8"))  # bien formado
    ficheros = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": RELS,
        "word/document.xml": documento,
    }
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, texto in ficheros.items():
            zf.writestr(zipfile.ZipInfo(nombre, date_time=(1980, 1, 1, 0, 0, 0)), texto)
    return salida.getvalue()


def formulario() -> bytes:
    return docx(cuerpo_formulario())


def sin_huecos() -> bytes:
    return docx(cuerpo_sin_huecos())


def con_cuadro_de_texto() -> bytes:
    return docx(cuerpo_cuadro_de_texto())
