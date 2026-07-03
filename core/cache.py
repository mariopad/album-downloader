from __future__ import annotations

import json
import re
from pathlib import Path

CACHE_DIR = Path("cache")


def _slug(text: str) -> str:
    """
    Convierte un nombre en un slug válido para usar como nombre de carpeta.
    """

    text = text.lower().strip()

    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)

    return text


def cache_path(artist: str, album: str) -> Path:
    artist_dir = CACHE_DIR / _slug(artist)
    artist_dir.mkdir(parents=True, exist_ok=True)

    return artist_dir / f"{_slug(album)}.json"


def load_cache(artist: str, album: str):

    path = cache_path(artist, album)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf8"))


def save_cache(artist: str, album: str, data: dict):

    path = cache_path(artist, album)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf8",
    )