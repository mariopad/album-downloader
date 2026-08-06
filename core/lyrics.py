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

# Tolerancia (segundos) para aceptar un resultado de la búsqueda LIBRE (q).
# Esa búsqueda es amplia (rescata títulos que LRCLIB solo indexa con
# "(feat. X)" o que son pura puntuación como "?"), así que exigimos una
# coincidencia de duración estricta para no meter la letra de otra canción.
_Q_DURATION_TOLERANCE = 4


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


def _query(params: dict, duration, tolerance=None):
    """
    Una búsqueda en LRCLIB. Devuelve (plain, synced) del mejor resultado por
    duración, o (None, None) ante error, no-200 o sin coincidencias. Nunca
    lanza, para no interrumpir la descarga.

    Con `tolerance` (segundos), exige que el mejor resultado quede dentro de
    esa distancia de `duration`; si no, lo descarta. Se usa para verificar la
    búsqueda libre (q), que es amplia y sin este filtro podría traer otra
    canción distinta.
    """
    try:
        resp = requests.get(
            f"{LRCLIB_API}/search",
            params=params,
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

    if tolerance is not None:
        d = best.get("duration")
        if not duration or not d or abs(d - duration) > tolerance:
            return None, None

    synced = best.get("syncedLyrics") or None
    plain = best.get("plainLyrics") or None

    # Si solo hay sincronizada, derivamos la plana para incrustar en el tag.
    if not plain and synced:
        plain = _strip_timestamps(synced)

    return plain, synced


def get_lyrics(artist: str, title: str, album=None, duration=None,
               extra_artists=None):
    """
    Busca la letra en LRCLIB probando estrategias de más a menos precisa y
    devuelve la primera con resultado. (plain, synced); cualquiera puede ser
    None. Nunca lanza.

    1) título + artista — lo más preciso; resuelve la mayoría.
    2) título + álbum — rescata casos donde el artista de MusicBrainz no
       coincide con el de LRCLIB: un alias ("Ye" vs "Kanye West") o una lista
       larga de feats en la pista. El álbum desambigua canciones distintas
       con el mismo título (evita coger otra "We Don't Care" cualquiera), así
       que es un fallback seguro y no mete la letra equivocada.
    3) búsqueda libre (q) con artistas + título y verificación ESTRICTA de
       duración. Rescata títulos que LRCLIB solo indexa con "(feat. X)" o que
       son pura puntuación ("?"), donde la búsqueda por track_name falla. La
       tolerancia de duración evita colar otra canción. Solo se intenta si
       conocemos la duración (sin ella no se puede verificar).

    `extra_artists`: otros artistas acreditados en la pista (p.ej. los feats),
    que ayudan a la búsqueda libre.
    """
    strategies = [({"track_name": title, "artist_name": artist}, None)]

    if album:
        strategies.append(({"track_name": title, "album_name": album}, None))

    if duration:
        all_artists = [artist] + list(extra_artists or [])
        q = " ".join(all_artists + [title]).strip()
        strategies.append(({"q": q}, _Q_DURATION_TOLERANCE))

    for params, tolerance in strategies:
        plain, synced = _query(params, duration, tolerance)
        if plain or synced:
            return plain, synced

    return None, None
