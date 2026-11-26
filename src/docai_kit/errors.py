"""Catálogo de códigos de error, aviso y validación del kit.

Todo fallo del pipeline se expresa como un :class:`Fallo` con un código de este catálogo. Las
funciones que detectan problemas los acumulan y lanzan un único :class:`KitError`; la CLI lo
convierte en informe y código de salida. No hay más tipos de excepción "esperados": cualquier otra
excepción es un bug y se propaga con su traza.
"""

from __future__ import annotations

from dataclasses import dataclass

EXIT_OK = 0
EXIT_VALIDACION = 1
EXIT_ENTRADA = 2


@dataclass(frozen=True)
class Codigo:
    codigo: str
    exit: int
    titulo: str
    accion: str


_CODIGOS = [
    # --- build / entrada ----------------------------------------------------------------------
    Codigo(
        "E001",
        EXIT_ENTRADA,
        "El origen ha cambiado: su SHA-256 no coincide con `origen_sha256` del inventario",
        "Comprueba que `origen.docx` es el Word correcto. Si lo has cambiado a propósito, ejecuta "
        "`docai-kit extract <slug>`, copia el hash que imprime en `origen_sha256` y revisa las "
        "ocurrencias del inventario.",
    ),
    Codigo(
        "E002",
        EXIT_VALIDACION,
        "`inventario.yaml` no es válido (esquema o coherencia interna)",
        "Corrige el inventario según el mensaje (ruta del error) y `schemas/inventario.schema.json`.",
    ),
    Codigo(
        "E003",
        EXIT_VALIDACION,
        "El texto buscado aparece un número de veces distinto de `esperadas`",
        "Ajusta `esperadas` o acota la búsqueda con `en:` (id de párrafo) o `parte:`. El mensaje "
        "lista dónde aparece realmente.",
    ),
    Codigo(
        "E004",
        EXIT_VALIDACION,
        "Dos coincidencias se solapan",
        "Acota una de las ocurrencias con `en:` para que no compitan por el mismo texto.",
    ),
    Codigo(
        "E005",
        EXIT_VALIDACION,
        "El ámbito indicado (`en:` / `parte:`) no existe en el documento",
        "Usa un id de párrafo o una parte que aparezcan en `trabajo/<slug>/documento.json`.",
    ),
    Codigo(
        "E006",
        EXIT_VALIDACION,
        "`ids.lock.json` es incoherente con el inventario",
        "Revisa `renombrado_de` (debe nombrar un campo que exista en el lock) y no edites el lock a "
        "mano.",
    ),
    Codigo(
        "E007",
        EXIT_VALIDACION,
        "No se puede resolver la tabla de un bloque `tabla_repetible`",
        "El `ancla` debe identificar exactamente una tabla y `fila_plantilla` debe existir en ella.",
    ),
    Codigo(
        "E008",
        EXIT_VALIDACION,
        "La coincidencia cruza contenido no textual o está dentro de un campo de Word",
        "Busca un literal que no incluya tabuladores, saltos, imágenes, campos ni límites de "
        "hipervínculo; acótalo a un solo tramo de texto.",
    ),
    Codigo(
        "E009",
        EXIT_ENTRADA,
        "Falta un fichero o directorio de entrada",
        "Comprueba el slug y que existen `plantillas/<slug>/origen.docx` e `inventario.yaml`.",
    ),
    Codigo(
        "E010",
        EXIT_ENTRADA,
        "El documento tiene control de cambios",
        "Abre el Word, acepta o rechaza todos los cambios (Revisar > Aceptar todos), desactiva el "
        "control de cambios y guarda.",
    ),
    Codigo(
        "E011",
        EXIT_ENTRADA,
        "Un cuadro de texto tiene la versión alternativa (`mc:Fallback`) distinta de la principal",
        "Edita el cuadro de texto en Word (cualquier cambio regenera ambas versiones) y vuelve a "
        "guardar.",
    ),
    Codigo(
        "E012",
        EXIT_ENTRADA,
        "El documento contiene texto en una estructura no soportada",
        "Mueve ese texto a un párrafo, celda o cuadro de texto normal, o abre una incidencia con la "
        "ruta que indica el mensaje.",
    ),
    Codigo(
        "E013",
        EXIT_VALIDACION,
        "Un YAML de dominio o de datos (`datasets`, `calculations`, `prompts`, `datos_ejemplo`) no "
        "es válido",
        "Corrige el fichero según el mensaje y su esquema en `schemas/`.",
    ),
    # --- infer ----------------------------------------------------------------------------------
    Codigo(
        "E020",
        EXIT_ENTRADA,
        "`infer`: la estructura de párrafos del origen y de la plantilla difiere",
        "La plantilla debe partir del mismo origen sin añadir ni quitar párrafos, filas o celdas. "
        "Rehaz la edición o recupera la estructura en Word.",
    ),
    Codigo(
        "E021",
        EXIT_VALIDACION,
        "`infer`: hay diferencias que no son una sustitución limpia por `{{ x }}`",
        "Revisa el informe de diferencias no explicables: o se corrigen en la plantilla, o se "
        "asumen como cambios que el pipeline no reproduce.",
    ),
    # --- bloques --------------------------------------------------------------------------------
    Codigo(
        "E030",
        EXIT_VALIDACION,
        "Rango de un bloque `condicional` no válido",
        "`desde` y `hasta` deben estar en la misma parte y el mismo contenedor (cuerpo o celda), "
        "en orden, y sin saltos de sección dentro.",
    ),
    # --- import ---------------------------------------------------------------------------------
    Codigo(
        "E040",
        EXIT_VALIDACION,
        "`import`: `validate` ha fallado; no se importa nada",
        "Ejecuta `docai-kit validate <slug>` y corrige los errores.",
    ),
    Codigo(
        "E041",
        EXIT_ENTRADA,
        "`import`: faltan variables de entorno",
        "Exporta `DOCAI_HOST`, `DOCAI_USER` y `DOCAI_PASS` (nunca en ficheros del repo).",
    ),
    Codigo(
        "E042",
        EXIT_VALIDACION,
        "`import`: DocAI ha respondido con error",
        "Lee el cuerpo de la respuesta: 422 = esquema; 409 = clave duplicada; 403 = permisos.",
    ),
    Codigo(
        "E043",
        EXIT_ENTRADA,
        "`import`: falta confirmación explícita",
        "Para ejecutar de verdad pasa `--yes`; para `prod`, además `--confirm-prod`.",
    ),
    # --- render ---------------------------------------------------------------------------------
    Codigo(
        "E050",
        EXIT_ENTRADA,
        "`render --pdf`: LibreOffice (`soffice`) no está disponible o ha fallado",
        "Instala LibreOffice o genera solo el `.docx`.",
    ),
    # --- avisos ---------------------------------------------------------------------------------
    Codigo(
        "W001",
        EXIT_OK,
        "El origen ya contiene marcadores `{{` o `{%`",
        "Revisa si el origen es realmente el Word sin adaptar.",
    ),
]

CATALOGO: dict[str, Codigo] = {c.codigo: c for c in _CODIGOS}

# Comprobaciones de `validate` (V01..V12): título de cada una.
VALIDACIONES: dict[str, str] = {
    "V01": "Los JSON de componentes validan contra su esquema",
    "V02": "Variables de la plantilla == nombres técnicos de fields.json",
    "V03": "Cada options_source apunta a un dataset existente",
    "V04": "Cada calculation_binding apunta a un cálculo y campos existentes",
    "V05": "Ningún marcador partido entre runs y todos parsean en Jinja",
    "V06": "Cada ocurrencia se aplicó y no queda ningún literal de debe_desaparecer",
    "V07": "Nombres técnicos con formato ^[a-z][a-z0-9_]*$",
    "V08": "Render con contexto vacío",
    "V09": "Render con datos_ejemplo.yaml completo",
    "V10": "Render con contexto parcial (field_order par)",
    "V11": "componentes/<slug>/ está al día con un build limpio",
    "V12": "Conversión a PDF con LibreOffice",
}


@dataclass(frozen=True)
class Fallo:
    codigo: str
    mensaje: str
    ubicacion: str | None = None
    severidad: str = "error"  # error | aviso

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "severidad": self.severidad,
            "mensaje": self.mensaje,
            "ubicacion": self.ubicacion,
        }


class KitError(Exception):
    """Uno o varios fallos que abortan el comando."""

    def __init__(self, fallos: list[Fallo]):
        if not fallos:
            raise ValueError("KitError necesita al menos un fallo")
        self.fallos = fallos
        super().__init__("; ".join(f"{f.codigo}: {f.mensaje}" for f in fallos))

    @classmethod
    def de(cls, codigo: str, mensaje: str, ubicacion: str | None = None) -> KitError:
        return cls([Fallo(codigo, mensaje, ubicacion)])

    @property
    def exit_code(self) -> int:
        return max(CATALOGO[f.codigo].exit for f in self.fallos)
