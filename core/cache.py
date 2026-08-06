from __future__ import annotations

import json
import re
from pathlib import Path

CACHE_DIR = Path("cache")

# Versión del esquema de metadatos guardado en caché. Súbela cada vez que
# `fetch_album` cambie qué campos produce: las entradas viejas (con otra
# versión o sin ella) se ignoran y se vuelven a pedir a MusicBrainz.
#   v2: se añadió `duration_s` por pista (verificación por duración).
#   v3: se añadió disco/pista (disc, disc_total, track_no, track_total).
CACHE_VERSION = 3


def _slug(text: str) -> str:
    """
    Convierte un nombre en un slug válido para usar como nombre de carpeta.
    """

    text = text.lower().strip()

    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)

    return text


def cache_path(artist: str, album: str, release_id: str = None) -> Path:
    artist_dir = CACHE_DIR / _slug(artist)
    artist_dir.mkdir(parents=True, exist_ok=True)

    # Al fijar una edición concreta, la cacheamos aparte para no pisar (ni
    # servir) la del álbum elegido por defecto.
    name = _slug(album)
    if release_id:
        name = f"{name}--{release_id}"

    return artist_dir / f"{name}.json"


def load_cache(artist: str, album: str, release_id: str = None):

    path = cache_path(artist, album, release_id)

    if not path.exists():
        return None

    try:
        entry = json.loads(path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError):
        return None

    # Caché con versión actual → devolvemos los metadatos.
    if isinstance(entry, dict) and entry.get("version") == CACHE_VERSION:
        return entry.get("data")

    # Cualquier otra cosa (formato viejo sin envoltorio, versión distinta)
    # se considera obsoleta: la ignoramos para forzar un re-fetch.
    return None


def save_cache(artist: str, album: str, data: dict, release_id: str = None):

    path = cache_path(artist, album, release_id)

    entry = {
        "version": CACHE_VERSION,
        "data": data,
    }

    path.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False),
        encoding="utf8",
    )