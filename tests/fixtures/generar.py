"""Genera los .docx de prueba de tests/fixtures/ (versionados junto a este script).

Se escriben a mano, parte a parte, para controlar exactamente los runs. El empaquetado usa el
escritor byte-estable del kit, así que volver a ejecutar el script produce los mismos bytes
(lo comprueba ``tests/test_fixtures.py``).

    uv run python tests/fixtures/generar.py
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docai_kit.docx_io import Paquete

AQUI = Path(__file__).resolve().parent

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'mc:Ignorable="wps"'
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
{extra}
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Fixture</dc:title>
<dcterms:created xsi:type="dcterms:W3CDTF">2020-01-02T03:04:05Z</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">2020-01-02T03:04:05Z</dcterms:modified>
</cp:coreProperties>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {NS}>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Ttulo1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Ttulo2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/></w:style>
</w:styles>"""


def r(texto: str, rpr: str = "") -> str:
    espacio = ' xml:space="preserve"' if texto != texto.strip() else ""
    return f"<w:r>{'<w:rPr>' + rpr + '</w:rPr>' if rpr else ''}<w:t{espacio}>{texto}</w:t></w:r>"


def p(*runs: str, estilo: str | None = None, ppr: str = "") -> str:
    pp = f'<w:pStyle w:val="{estilo}"/>' if estilo else ""
    pp += ppr
    return f"<w:p>{'<w:pPr>' + pp + '</w:pPr>' if pp else ''}{''.join(runs)}</w:p>"


def tabla(filas: list[list[str]]) -> str:
    cuerpo = "".join(
        "<w:tr>"
        + "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>{c}</w:tc>' for c in fila
        )
        + "</w:tr>"
        for fila in filas
    )
    return f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>{cuerpo}</w:tbl>'


def cuadro_de_texto(contenido: str, contenido_fallback: str | None = None) -> str:
    """Párrafo con un cuadro de texto DrawingML (mc:Choice) y su copia VML (mc:Fallback)."""
    fallback = contenido if contenido_fallback is None else contenido_fallback
    return (
        "<w:p><w:r><mc:AlternateContent>"
        '<mc:Choice Requires="wps"><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        'relativeHeight="1" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="column"><wp:posOffset>0</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        '<wp:extent cx="1000000" cy="500000"/><wp:wrapNone/><wp:docPr id="1" name="Cuadro 1"/>'
        '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
        f"<wps:wsp><wps:spPr/><wps:txbx><w:txbxContent>{contenido}</w:txbxContent></wps:txbx><wps:bodyPr/></wps:wsp>"
        "</a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>"
        f"<mc:Fallback><w:pict><v:rect><v:textbox><w:txbxContent>{fallback}</w:txbxContent></v:textbox></v:rect></w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )


def empaquetar(
    destino: Path, cuerpo: str, cabecera: str | None = None, pie: str | None = None
) -> None:
    extra = []
    rels_doc = [
        '<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ]
    sect = ""
    partes = {}
    if cabecera is not None:
        extra.append(
            '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        )
        rels_doc.append(
            '<Relationship Id="rIdH1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        )
        sect += '<w:headerReference w:type="default" r:id="rIdH1"/>'
        partes["word/header1.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:hdr {NS}>{cabecera}</w:hdr>'
        )
    if pie is not None:
        extra.append(
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        )
        rels_doc.append(
            '<Relationship Id="rIdF1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        )
        sect += '<w:footerReference w:type="default" r:id="rIdF1"/>'
        partes["word/footer1.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:ftr {NS}>{pie}</w:ftr>'
        )
    documento = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>{cuerpo}'
        f'<w:sectPr>{sect}<w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
    )
    ficheros = {
        "[Content_Types].xml": CONTENT_TYPES.format(extra="\n".join(extra)),
        "_rels/.rels": RELS,
        "docProps/core.xml": CORE,
        "word/document.xml": documento,
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels_doc)
            + '<Relationship Id="rIdL" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com" TargetMode="External"/>'
            "</Relationships>"
        ),
        "word/styles.xml": STYLES,
        **partes,
    }
    crudo = io.BytesIO()
    with zipfile.ZipFile(crudo, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, texto in ficheros.items():
            zf.writestr(nombre, texto)
    destino.write_bytes(Paquete.abrir(crudo.getvalue()).a_bytes())


NEGRITA = "<w:b/>"
CURSIVA = "<w:i/>"

# --- basico.docx: todos los casos del algoritmo de runs ---------------------------------------
BASICO = "".join(
    [
        p(r("Portada de ACME S.L."), estilo=None),  # p/0000: un run
        p(r("Capítulo Uno"), estilo="Ttulo1"),  # p/0001
        p(
            r("Cliente: AC"), r("ME", NEGRITA), r(" S.L. y nada más")
        ),  # p/0002: cruza 3 runs, el medio en negrita
        p(r("Ref: "), r("B12"), r("34"), r("56"), r("78")),  # p/0003: cruza N runs
        p(r("Tabulado: Hola"), "<w:r><w:tab/></w:r>", r("Mundo")),  # p/0004: no textual en medio
        p(
            r("Web: "),
            '<w:hyperlink r:id="rIdL">'
            + r("ACME", '<w:rStyle w:val="Hyperlink"/>')
            + "</w:hyperlink>",
            r(" fin"),
        ),  # p/0005: hipervínculo
        p(r("Sub"), estilo="Ttulo2"),  # p/0006: Heading 2 no cambia el capítulo
        tabla(
            [[p(r("Fabricante inversor")), p(r("Modelo"))], [p(r("Huawei")), p(r("SUN2000-10KTL"))]]
        ),
        p(r("Capítulo Dos"), estilo="Ttulo1"),  # p/0007
        cuadro_de_texto(p(r("Caja: ACME"))),  # p/0008 + txbx
        p(r("Opcional A")),  # p/0009
        p(r("Opcional B")),  # p/0010
        tabla([[p(r("Celda con ACME")), tabla([[p(r("Anidada ACME"))]])]]),  # tbl/02 con anidada
        p(r("Cierre ACME")),  # p/0011
    ]
)

# --- otros ---------------------------------------------------------------------------------------
REVISIONES = p(
    r("Texto "),
    '<w:ins w:id="1" w:author="x" w:date="2020-01-01T00:00:00Z">' + r("insertado") + "</w:ins>",
)
MARCADORES = p(r("Ya tiene {{ algo }} dentro"))
FALLBACK_DISTINTO = cuadro_de_texto(p(r("Caja: ACME")), p(r("Caja: OTRA")))
NO_SOPORTADO = '<w:customXml w:element="x">' + p(r("ACME escondido")) + "</w:customXml>"


def main() -> None:
    empaquetar(AQUI / "basico.docx", BASICO, cabecera=p(r("Cabecera ACME")), pie=p(r("Pie ACME")))
    empaquetar(AQUI / "revisiones.docx", REVISIONES)
    empaquetar(AQUI / "marcadores.docx", MARCADORES)
    empaquetar(AQUI / "fallback_distinto.docx", FALLBACK_DISTINTO)
    empaquetar(AQUI / "no_soportado.docx", NO_SOPORTADO)


if __name__ == "__main__":
    main()
