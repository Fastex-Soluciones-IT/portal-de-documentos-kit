"""``docai-kit import``: sube componentes/<slug>/ a DocAI. Por defecto solo imprime (dry-run).

Orden (el de las guías: cálculos y prompts pertenecen a la plantilla y necesitan su id):
datasets -> plantilla (.docx) -> cálculos -> prompts -> campos.

Host y credenciales: SOLO de ``DOCAI_HOST``, ``DOCAI_USER`` y ``DOCAI_PASS``.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .errors import KitError
from .inventario import RutasPlantilla
from .serialize import cargar_yaml
from .validate import validar

TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Peticion:
    paso: str
    metodo: str
    ruta: str  # relativa a {host}/api/v1; puede contener {TEMPLATE_ID}
    fichero: Path | None
    tipo: str  # json | multipart | form
    omitida: str | None = None  # motivo si no se envía

    def describir(self, host: str, template_id: str | None) -> str:
        url = host + "/api/v1" + self.ruta.replace("{TEMPLATE_ID}", template_id or "$TEMPLATE_ID")
        if self.omitida:
            return f"[{self.paso}] (se omite: {self.omitida})"
        cuerpo = ""
        if self.fichero is not None:
            datos = self.fichero.read_bytes()
            cuerpo = f" <- {self.fichero.name} ({len(datos)} bytes, sha256 {hashlib.sha256(datos).hexdigest()[:12]})"
        return f"[{self.paso}] {self.metodo} {url} ({self.tipo}){cuerpo}"


def _vacio(ruta: Path) -> bool:
    valor = json.loads(ruta.read_text(encoding="utf-8"))
    return valor in ([], {})


def plan(rutas: RutasPlantilla, template_id: str | None) -> list[Peticion]:
    c = rutas.componentes
    pasos = [
        Peticion("login", "POST", "/login/access-token", None, "form"),
        Peticion("datasets", "POST", "/datasets/import", c / "datasets.json", "json"),
        Peticion("plantilla", "POST", "/templates/", c / "plantilla.docx", "multipart"),
        Peticion(
            "calculos",
            "POST",
            "/templates/{TEMPLATE_ID}/calculations/import",
            c / "calculations.json",
            "json",
        ),
        Peticion(
            "prompts", "POST", "/templates/{TEMPLATE_ID}/prompts/import", c / "prompts.json", "json"
        ),
        Peticion(
            "campos", "PUT", "/templates/{TEMPLATE_ID}/fields/import", c / "fields.json", "json"
        ),
    ]
    for p in pasos:
        if p.tipo == "json" and _vacio(p.fichero):
            p.omitida = f"{p.fichero.name} está vacío"
    if template_id is not None:
        pasos[2].omitida = f"se usa la plantilla existente --template-id {template_id}"
    return pasos


def _multipart(fichero: Path, nombre: str) -> tuple[bytes, str]:
    datos = fichero.read_bytes()
    limite = "docai-kit-" + hashlib.sha256(datos).hexdigest()[:24]
    partes = [
        f'--{limite}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{nombre}\r\n'.encode(),
        (
            f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{fichero.name}"\r\n'
            f"Content-Type: {TIPO_DOCX}\r\n\r\n"
        ).encode()
        + datos
        + b"\r\n",
        f"--{limite}--\r\n".encode(),
    ]
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def _enviar(metodo: str, url: str, cuerpo: bytes, tipo: str, token: str | None) -> dict:
    cabeceras = {"Content-Type": tipo, "Accept": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=120) as resp:
            texto = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", "replace")[:1000]
        raise KitError.de("E042", f"{metodo} {url} -> HTTP {exc.code}: {detalle}") from exc
    except urllib.error.URLError as exc:
        raise KitError.de("E042", f"{metodo} {url} -> {exc.reason}") from exc
    return json.loads(texto) if texto else {}


def importar(
    raiz: Path,
    slug: str,
    entorno: str,
    ejecutar: bool,
    confirmar_prod: bool,
    template_id: str | None,
    entorno_vars: dict[str, str],
) -> list[str]:
    """Devuelve las líneas del registro. Lanza KitError si algo impide seguir."""
    rutas = RutasPlantilla(raiz, slug)
    informe = validar(raiz, slug)
    if not informe.ok:
        fallidas = [c.codigo for c in informe.comprobaciones if c.estado == "failed"]
        raise KitError.de("E040", f"validate {slug} falla en {', '.join(fallidas)}")
    pasos = plan(rutas, template_id)
    host = entorno_vars.get("DOCAI_HOST", "$DOCAI_HOST").rstrip("/")
    registro = [f"entorno: {entorno} — {'EJECUCIÓN' if ejecutar else 'dry-run (no se envía nada)'}"]
    if not ejecutar:
        registro.extend(p.describir(host, template_id) for p in pasos)
        registro.append("Para ejecutar: --yes" + (" --confirm-prod" if entorno == "prod" else ""))
        return registro
    if entorno == "prod" and not confirmar_prod:
        raise KitError.de("E043", "import a prod sin --confirm-prod")
    faltan = [v for v in ("DOCAI_HOST", "DOCAI_USER", "DOCAI_PASS") if not entorno_vars.get(v)]
    if faltan:
        raise KitError.de("E041", f"faltan {', '.join(faltan)}")
    inventario = cargar_yaml(rutas.inventario, "E002")
    nombre_plantilla = inventario.get("nombre_plantilla", slug)
    base = host + "/api/v1"
    token = None
    for p in pasos:
        if p.omitida:
            registro.append(p.describir(host, template_id))
            continue
        url = base + p.ruta.replace("{TEMPLATE_ID}", template_id or "")
        if p.paso == "login":
            cuerpo = urllib.parse.urlencode(
                {"username": entorno_vars["DOCAI_USER"], "password": entorno_vars["DOCAI_PASS"]}
            ).encode()
            respuesta = _enviar("POST", url, cuerpo, "application/x-www-form-urlencoded", None)
            token = respuesta.get("access_token")
            if not token:
                raise KitError.de("E042", "login sin access_token en la respuesta")
            registro.append("[login] ok")
            continue
        if p.tipo == "multipart":
            cuerpo, tipo = _multipart(p.fichero, nombre_plantilla)
        else:
            cuerpo, tipo = p.fichero.read_bytes(), "application/json"
        respuesta = _enviar(p.metodo, url, cuerpo, tipo, token)
        if p.paso == "plantilla":
            template_id = str(respuesta.get("id") or "")
            if not template_id:
                raise KitError.de("E042", "la subida de la plantilla no devolvió `id`")
            registro.append(f"[plantilla] ok — TEMPLATE_ID={template_id}")
        else:
            resumen = {k: respuesta[k] for k in ("created", "updated") if k in respuesta}
            registro.append(f"[{p.paso}] ok {json.dumps(resumen, ensure_ascii=False)}")
    return registro
