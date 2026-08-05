import re

import requests

# LRCLIB: base de datos abierta de letras (sin API key). La búsqueda por
# nombre de pista + artista es tolerante; afinamos con la duración.
LRCLIB_API = "https://lrclib.net/api"

_HEADERS = {
    "User-Agent": "musicdl (https://github.com/mariopad/album-downloader)"
}

# Marcas de tiempo LRC, p.ej. "[01:23.45]".
_LRC_TS = re.compile(r"\[\d+:\d+(?:\.\d+)?\]")


def _strip_timestamps(synced: str) -> str:
    """Convierte letra sincronizada (.lrc) en texto plano."""
    lines = (_LRC_TS.sub("", line).strip() for line in synced.splitlines())
    return "\n".join(lines).strip()


def _best_match(results, duration):
    """
    Elige el resultado con letra cuya duración más se acerca a la nuestra
    (reutiliza el mismo criterio que la verificación de descargas).
    """
    candidates = []

    for r in results:
        if not (r.get("plainLyrics") or r.get("syncedLyrics")):
            continue

        d = r.get("duration")
        diff = abs(d - duration) if (duration and d) else float("inf")
        candidates.append((diff, r))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def get_lyrics(artist: str, title: str, album=None, duration=None):
    """
    Busca la letra en LRCLIB. Devuelve (plain, synced); cualquiera de los
    dos puede ser None. Nunca lanza: ante cualquier error o falta de
    resultados devuelve (None, None), para no interrumpir la descarga.
    """
    try:
        resp = requests.get(
            f"{LRCLIB_API}/search",
            params={"track_name": title, "artist_name": artist},
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return None, None
        results = resp.json() or []
    except Exception:
        return None, None

    best = _best_match(results, duration)
    if not best:
        return None, None

    synced = best.get("syncedLyrics") or None
    plain = best.get("plainLyrics") or None

    # Si solo hay sincronizada, derivamos la plana para incrustar en el tag.
    if not plain and synced:
        plain = _strip_timestamps(synced)

    return plain, synced
