"""Punto de entrada ``docai-kit <comando>``.

Códigos de salida: 0 = bien, 1 = errores de validación, 2 = error de uso o de entrada.
Todos los comandos aceptan ``--json`` para emitir un informe máquina-legible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import serialize
from .errors import CATALOGO, EXIT_ENTRADA, EXIT_OK, EXIT_VALIDACION, Fallo, KitError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse sale con 2 en errores de uso: lo mantenemos
        self.print_usage(sys.stderr)
        self.exit(EXIT_ENTRADA, f"{self.prog}: error: {message}\n")


def _emitir(
    args, comando: str, exit_code: int, datos: dict, fallos: list[Fallo], lineas: list[str]
):
    if args.json:
        informe = {
            "comando": comando,
            "ok": exit_code == EXIT_OK,
            "exit": exit_code,
            "fallos": [f.como_dict() for f in fallos if f.severidad == "error"],
            "avisos": [f.como_dict() for f in fallos if f.severidad != "error"],
            "datos": datos,
        }
        sys.stdout.write(json.dumps(informe, ensure_ascii=False, indent=2) + "\n")
        return exit_code
    for linea in lineas:
        print(linea)
    sys.stdout.flush()
    for f in fallos:
        marca = "ERROR" if f.severidad == "error" else "aviso"
        donde = f" [{f.ubicacion}]" if f.ubicacion else ""
        destino = sys.stderr if f.severidad == "error" else sys.stdout
        print(f"{marca} {f.codigo}{donde}: {f.mensaje}", file=destino)
        if f.severidad == "error" and f.codigo in CATALOGO:
            print(f"      -> {CATALOGO[f.codigo].accion}", file=destino)
    return exit_code


def cmd_extract(args) -> tuple[int, dict, list[Fallo], list[str]]:
    from .extract import extract

    salida, doc, avisos = extract(args.raiz, args.slug)
    lineas = [
        f"{salida} — {len(doc['parrafos'])} párrafos",
        f"origen_sha256: {doc['origen_sha256']}",
    ]
    return EXIT_OK, {"salida": str(salida), "origen_sha256": doc["origen_sha256"]}, avisos, lineas


def cmd_preparar(args):
    from .preparar import preparar_plantilla

    origen, huecos, prep = preparar_plantilla(args.raiz, args.slug)
    por_tipo = {t: sum(h.tipo == t for h in prep.huecos) for t in ("celda", "casilla", "control")}
    resumen = ", ".join(f"{t}: {n}" for t, n in por_tipo.items())
    lineas = [f"{origen} — {len(prep.huecos)} huecos ({resumen})", str(huecos)]
    datos = {"origen": str(origen), "huecos": str(huecos), "por_tipo": por_tipo}
    return EXIT_OK, datos, [], lineas


def cmd_build(args):
    from .build import build, huellas

    res = build(args.raiz, args.slug)
    datos = {"campos": res.campos, "marcadores": res.marcadores, "sha256": huellas(res.ficheros)}
    lineas = [f"componentes/{args.slug}/: {res.campos} campos, {res.marcadores} marcadores"]
    lineas += [f"  {sha[:16]}  {nombre}" for nombre, sha in datos["sha256"].items()]
    if res.lock_cambia:
        lineas.append(f"  ids.lock.json actualizado (plantillas/{args.slug}/ids.lock.json)")
    return EXIT_OK, datos, res.avisos, lineas


def cmd_validate(args):
    from .validate import validar

    informe = validar(args.raiz, args.slug, strict=args.strict)
    lineas = [f"validate {args.slug}", f"{'código':<6} {'estado':<8} comprobación"]
    from .errors import VALIDACIONES

    for c in informe.comprobaciones:
        extra = f" — {c.motivo}" if c.motivo else ""
        lineas.append(f"{c.codigo:<6} {c.estado:<8} {VALIDACIONES[c.codigo]}{extra}")
    fallos = [f for c in informe.comprobaciones for f in c.fallos]
    code = EXIT_OK if informe.ok else EXIT_VALIDACION
    return code, informe.como_dict(), fallos, lineas


def cmd_infer(args):
    from .infer import inferir

    slug = args.slug or args.salida.parent.name
    inventario, lock, informe = inferir(args.origen, args.plantilla, slug, args.campos)
    serialize.escribir_yaml(args.salida, inventario, serialize.cargar_esquema("inventario"))
    lineas = [f"{args.salida}: {len(inventario['campos'])} campos"]
    if lock is not None and args.ids_lock is not None:
        serialize.escribir_json(args.ids_lock, lock, serialize.cargar_esquema("ids_lock"))
        lineas.append(f"{args.ids_lock}: {len(lock['campos'])} IDs")
    fallos = []
    for d in informe.no_explicables:
        fallos.append(
            Fallo(
                "E021", f"{d['operacion']}: {d['esperado']!r} -> {d['plantilla']!r}", d["parrafo"]
            )
        )
    for n in informe.campos_sin_marcador:
        fallos.append(
            Fallo("E021", f"el campo {n!r} de --campos no tiene marcador en la plantilla")
        )
    for n in informe.marcadores_sin_campo:
        fallos.append(
            Fallo("E021", f"el marcador {n!r} no está en --campos (tipo por defecto: text)")
        )
    for d in informe.metadatos_no_reproducibles:
        fallos.append(
            Fallo("E021", f"{d['campo']}.{d['clave']} = {d['valor']!r} no se puede reproducir")
        )
    code = EXIT_OK if not fallos else EXIT_VALIDACION
    return code, informe.como_dict(), fallos, lineas


def cmd_render(args):
    from .inventario import RutasPlantilla
    from .render import a_pdf, render_bytes

    rutas = RutasPlantilla(args.raiz, args.slug)
    plantilla = rutas.componentes / "plantilla.docx"
    if not plantilla.is_file():
        raise KitError.de("E009", "no existe; ejecuta `docai-kit build`", str(plantilla))
    if not args.datos.is_file():
        raise KitError.de("E009", "no existe el fichero de datos", str(args.datos))
    contexto = serialize.cargar_yaml(args.datos, "E013")
    if not isinstance(contexto, dict):
        raise KitError.de("E013", "los datos deben ser un mapa campo -> valor", str(args.datos))
    serialize.escribir_bytes(args.salida, render_bytes(plantilla.read_bytes(), contexto))
    lineas = [str(args.salida)]
    if args.pdf:
        lineas.append(str(a_pdf(args.salida, args.salida.with_suffix(".pdf"))))
    return EXIT_OK, {"salida": lineas}, [], lineas


def cmd_import(args):
    from .importer import importar

    variables = {
        k: v for k, v in os.environ.items() if k in ("DOCAI_HOST", "DOCAI_USER", "DOCAI_PASS")
    }
    ejecutar = args.yes and not args.dry_run
    lineas = importar(
        args.raiz, args.slug, args.entorno, ejecutar, args.confirm_prod, args.template_id, variables
    )
    return EXIT_OK, {"registro": lineas}, [], lineas


def construir_parser() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--json", action="store_true", help="informe máquina-legible por stdout")
    comun.add_argument("--raiz", type=Path, default=Path("."), help="raíz del kit (por defecto, .)")
    ap = _Parser(
        prog="docai-kit", description="Word corporativo + inventario.yaml -> plantilla DocAI"
    )
    sub = ap.add_subparsers(dest="comando", required=True, parser_class=_Parser)

    p = sub.add_parser(
        "extract", parents=[comun], help="origen.docx -> trabajo/<slug>/documento.json"
    )
    p.add_argument("slug")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser(
        "preparar",
        parents=[comun],
        help="word_original.docx -> origen.docx con huecos ⟦hNNN⟧ + trabajo/<slug>/huecos.json",
    )
    p.add_argument("slug")
    p.set_defaults(func=cmd_preparar)

    p = sub.add_parser("build", parents=[comun], help="genera componentes/<slug>/")
    p.add_argument("slug")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", parents=[comun], help="comprobaciones V01–V12")
    p.add_argument("slug")
    p.add_argument("--strict", action="store_true", help="V07 como error, sin nombres heredados")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser(
        "infer", parents=[comun], help="(origen, plantilla adaptada) -> inventario.yaml"
    )
    p.add_argument("--origen", type=Path, required=True)
    p.add_argument("--plantilla", type=Path, required=True)
    p.add_argument("-o", dest="salida", type=Path, required=True, help="inventario.yaml de salida")
    p.add_argument("--slug", help="por defecto, el nombre del directorio de -o")
    p.add_argument("--campos", type=Path, help="fields.json existente para rellenar metadatos")
    p.add_argument("--ids-lock", type=Path, help="escribe un ids.lock.json con los FLD de --campos")
    p.set_defaults(func=cmd_infer)

    p = sub.add_parser("render", parents=[comun], help="render local para revisión")
    p.add_argument("slug")
    p.add_argument("--datos", type=Path, required=True)
    p.add_argument("-o", dest="salida", type=Path, required=True)
    p.add_argument("--pdf", action="store_true", help="además, PDF con LibreOffice headless")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser(
        "import", parents=[comun], help="sube los componentes a DocAI (dry-run por defecto)"
    )
    p.add_argument("slug")
    p.add_argument("--entorno", choices=["test", "prod"], required=True)
    p.add_argument(
        "--dry-run", action="store_true", help="solo imprime las peticiones (por defecto)"
    )
    p.add_argument("--yes", action="store_true", help="ejecuta de verdad")
    p.add_argument("--confirm-prod", action="store_true", help="obligatorio para --entorno prod")
    p.add_argument("--template-id", help="usa una plantilla ya creada en vez de subir el .docx")
    p.set_defaults(func=cmd_import)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        code, datos, fallos, lineas = args.func(args)
    except KitError as exc:
        code, datos, fallos, lineas = exc.exit_code, {}, exc.fallos, []
    return _emitir(args, args.comando, code, datos, fallos, lineas)


if __name__ == "__main__":
    sys.exit(main())
