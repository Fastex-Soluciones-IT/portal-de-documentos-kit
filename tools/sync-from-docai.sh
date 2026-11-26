#!/usr/bin/env bash
#
# sync-from-docai.sh — mantiene el kit sincronizado con DocAI.
#
# Las guías de docs/ y las muestras de ejemplos/ son COPIAS de las fuentes canónicas de DocAI
# (backend/app/samples/). Cuando cambia el motor de cálculos, el generador de la plantilla o
# cualquiera de esas guías, hay que volver a copiarlas aquí para que el kit no quede desfasado.
#
# Los esquemas de schemas/{fields,datasets,calculations,prompts}.schema.json se GENERAN desde los
# modelos Pydantic de DocAI (backend/app/models.py y validadores) con tools/gen_schemas.py, en un
# entorno efímero de uv (no toca ni este repo ni el de DocAI). Si uv no está, ese paso se omite.
#
# Uso:
#   tools/sync-from-docai.sh [--check] [--src <ruta a backend/app/samples>]
#
#   (sin args)   Copia las fuentes canónicas → docs/ y ejemplos/. Idempotente.
#   --check      No copia: solo informa si hay desfase (exit 1 si lo hay). Útil en gates/CI.
#   --src PATH   Origen alternativo (por defecto: la ruta de abajo o $DOCAI_SAMPLES).
#
set -euo pipefail

# Raíz del kit = carpeta padre de este script.
KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Origen canónico (orden de prioridad): --src > $DOCAI_SAMPLES > default WSL > sibling repo.
DEFAULT_SRC="/mnt/c/codigo/factoria-proyectos/backend/app/samples"
SRC="${DOCAI_SAMPLES:-$DEFAULT_SRC}"
CHECK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift ;;
    --src)   SRC="$2"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$SRC" ]; then
  # Fallback: repo hermano en el mismo directorio padre que el kit.
  ALT="$(cd "$KIT_ROOT/.." && pwd)/factoria-proyectos/backend/app/samples"
  if [ -d "$ALT" ]; then SRC="$ALT"; else
    echo "ERROR: no encuentro las fuentes canónicas de DocAI." >&2
    echo "       Probé: '$SRC' y '$ALT'." >&2
    echo "       Pasa --src <ruta a backend/app/samples> o exporta DOCAI_SAMPLES." >&2
    exit 2
  fi
fi

# Mapa fuente -> destino dentro del kit.
#   guías      -> docs/
#   muestras   -> ejemplos/
GUIDES="TEMPLATE_AUTHORING_GUIDE.md DATASETS_FILE_GUIDE.md CALCULATIONS_FILE_GUIDE.md AI_PROMPTS_FILE_GUIDE.md FIELDS_FILE_GUIDE.md"
SAMPLES="sample_template.docx sample_dataset.json sample_calculations.json sample_prompts.json sample_fields.json sample_data.json sample_section.docx sample_section_fields.json sample_section_datasets.json sample_section_calculations.json sample_section_prompts.json sample_section_data.json"

drift=0
copied=0

sync_one() {  # $1=archivo  $2=subcarpeta destino
  local f="$1" dst_dir="$2"
  local src="$SRC/$f" dst="$KIT_ROOT/$dst_dir/$f"
  if [ ! -f "$src" ]; then
    echo "  ! FALTA en origen: $f (se omite)"; return 0
  fi
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    return 0  # igual, nada que hacer
  fi
  drift=1
  if [ "$CHECK" -eq 1 ]; then
    echo "  ~ DESFASE: $dst_dir/$f difiere del canónico"
  else
    cp "$src" "$dst"
    echo "  + actualizado: $dst_dir/$f"
    copied=$((copied+1))
  fi
}

echo "Origen canónico: $SRC"
echo "Kit:             $KIT_ROOT"
echo "Guías → docs/:"
for f in $GUIDES; do sync_one "$f" "docs"; done
echo "Muestras → ejemplos/:"
for f in $SAMPLES; do sync_one "$f" "ejemplos"; done

echo "Esquemas → schemas/ (generados desde los modelos de DocAI):"
BACKEND="$(cd "$SRC/../.." && pwd)"
# uv suele vivir en ~/.local/bin, que no siempre está en el PATH de shells no interactivas.
UV="${UV:-$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")}"
if [ -x "$UV" ] && [ -f "$BACKEND/app/models.py" ]; then
  GEN="$(mktemp -d)"
  trap 'rm -rf "$GEN"' EXIT
  "$UV" run --quiet --no-project --python 3.12 \
    --with 'sqlmodel>=0.0.21,<1' --with 'email-validator>=2.1.0.post1,<3' \
    python "$KIT_ROOT/tools/gen_schemas.py" --backend "$BACKEND" --out "$GEN" >/dev/null
  for f in fields datasets calculations prompts; do
    src="$GEN/$f.schema.json" dst="$KIT_ROOT/schemas/$f.schema.json"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then continue; fi
    drift=1
    if [ "$CHECK" -eq 1 ]; then
      echo "  ~ DESFASE: schemas/$f.schema.json difiere del generado"
    else
      cp "$src" "$dst"; echo "  + actualizado: schemas/$f.schema.json"; copied=$((copied+1))
    fi
  done
else
  echo "  ! se omiten: hace falta uv y $BACKEND/app/models.py"
fi

if [ "$CHECK" -eq 1 ]; then
  if [ "$drift" -eq 1 ]; then
    echo "RESULTADO: el kit está DESFASADO. Ejecuta 'tools/sync-from-docai.sh' (sin --check) y commitea." >&2
    exit 1
  fi
  echo "RESULTADO: el kit está al día. ✔"
  exit 0
fi

if [ "$copied" -eq 0 ]; then
  echo "RESULTADO: ya estaba todo al día. ✔"
else
  echo "RESULTADO: $copied fichero(s) actualizado(s). Revisa y commitea los cambios en el kit."
fi
