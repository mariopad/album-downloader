#!/usr/bin/env bash
#
# Prepara el entorno para musicdl:
#   - comprueba las herramientas de sistema (python, ffmpeg, node)
#   - crea un entorno virtual en .venv
#   - instala las dependencias de Python
#
# Uso:  ./setup.sh
#
set -euo pipefail

cd "$(dirname "$0")"

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
ok()   { echo "${GRN}✓${RST} $1"; }
warn() { echo "${YLW}!${RST} $1"; }
die()  { echo "${RED}✗ $1${RST}" >&2; exit 1; }

# --- Python (>= 3.10, hace falta el match statement) -------------------------
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "No se encontró Python. Instala Python 3.10 o superior."

"$PY" - <<'EOF' || die "Se necesita Python 3.10 o superior."
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
EOF
ok "Python: $($PY --version)"

# --- Herramientas de sistema requeridas por yt-dlp ---------------------------
command -v ffmpeg >/dev/null 2>&1 \
    && ok "ffmpeg: $(ffmpeg -version | head -1 | cut -d' ' -f1-3)" \
    || die "Falta ffmpeg (necesario para convertir a MP3). Instálalo con tu gestor de paquetes."

command -v node >/dev/null 2>&1 \
    && ok "node: $(node --version)" \
    || die "Falta Node.js (yt-dlp lo usa para resolver la firma de YouTube). Instálalo con tu gestor de paquetes."

# --- Entorno virtual + dependencias ------------------------------------------
if [ ! -d .venv ]; then
    "$PY" -m venv .venv
    ok "Entorno virtual creado en .venv"
else
    ok "Entorno virtual .venv ya existe"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
ok "Dependencias de Python instaladas"

echo
echo "${GRN}Listo.${RST} Actívalo con:  source .venv/bin/activate"
echo "Y prueba:                     python musicdl.py install \"Daft Punk\" \"Discovery\" --dry-run"
