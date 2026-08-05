import subprocess
import sys
from pathlib import Path

from core.cover import get_cover
from core.tagger import tag_mp3


# Cuántos resultados de YouTube pedir para elegir el mejor por duración.
SEARCH_RESULTS = 5

# Si el mejor candidato se aleja más de esto (segundos) de la duración
# esperada, avisamos: probablemente sea una versión en vivo, un remix,
# un edit acelerado o directamente la canción equivocada.
DURATION_TOLERANCE = 20


def _search_candidates(query: str, n: int):
    """
    Pide los primeros `n` resultados de YouTube para `query` y devuelve
    una lista de (duración_en_segundos | None, video_id), sin descargar.
    """
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        f"ytsearch{n}:{query}",
        "--flat-playlist",
        "--print", "%(duration)s\t%(id)s",
        "--no-warnings",
        "--extractor-args", "youtube:player_client=android",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    candidates = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if "\t" not in line:
            continue

        dur_str, vid = line.split("\t", 1)
        try:
            dur = float(dur_str)
        except ValueError:
            dur = None

        if vid:
            candidates.append((dur, vid))

    return candidates


def _pick_best(candidates, target):
    """
    Elige el video_id cuya duración más se acerca a `target` (segundos).

    Devuelve (video_id, diff) donde diff es la diferencia en segundos con
    la duración esperada, o None si no se pudo comparar. Sin candidatos,
    devuelve (None, None).
    """
    if not candidates:
        return None, None

    # Sin duración esperada no podemos verificar: primer resultado.
    if target is None:
        return candidates[0][1], None

    scored = [
        (abs(dur - target), vid)
        for dur, vid in candidates
        if dur is not None
    ]

    # Ningún candidato trae duración: primer resultado.
    if not scored:
        return candidates[0][1], None

    scored.sort()
    diff, vid = scored[0]

    return vid, diff


#CHAR_MAP = {
#    "?": "\uFF1F",   # U+FF1F FULLWIDTH QUESTION MARK
#    ":": "：",   # U+FF1A FULLWIDTH COLON
#    "/": "／",
#    "\\": "＼",
#    "*": "＊",
#    "\"": "＂",
#    "<": "＜",
#    ">": "＞",
#    "|": "｜",
#}

#def windows_safe_unicode(name: str) -> str:
#    return "".join(CHAR_MAP.get(c, c) for c in name)


def install_album(data: dict):

    artist = data["artist"]
    album = data["album"]
    album_artist = data.get("album_artist", artist)
    year = str(data["year"])
    genre = data["genre"]
    tracks = data["tracks"]

    cover = get_cover(data)

    outdir = Path("ipod") / album
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Installing {artist} - {album} ===\n")

    for i, track in enumerate(tracks, start=1):

        title = track["title"]
        track_artists = track.get("artists", [artist])
        artist_str = ", ".join(track_artists)

        print(f"[{i}/{len(tracks)}] {title}")

        #output = outdir / f"{i:02d} - {windows_safe_unicode(title)}.%(ext)s"
        output = outdir / f"{i:02d} - {title}.%(ext)s"

        query = f"{artist} - {title} audio"

        # Verificación por duración: en vez de descargar a ciegas el primer
        # resultado, pedimos varios y elegimos el más cercano a la duración
        # que MusicBrainz reporta para esta pista.
        target = track.get("duration_s")
        candidates = _search_candidates(query, SEARCH_RESULTS)
        video_id, diff = _pick_best(candidates, target)

        if video_id:
            source = f"https://www.youtube.com/watch?v={video_id}"
            if diff is not None and diff > DURATION_TOLERANCE:
                print(
                    f"   WARN: mejor resultado desviado {diff:.0f}s "
                    f"(esperado {target}s) — posible versión incorrecta"
                )
        else:
            print("   WARN: sin metadatos de búsqueda, usando primer resultado")
            source = f"ytsearch1:{query}"

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            source,
            "-f", "ba/b",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-playlist",
            "--retries", "10",
            "--fragment-retries", "10",
            # Nota: no forzamos player_client=android aquí. Ese cliente ya
            # no expone formatos "audio only" (experimento SABR de YouTube),
            # así que "ba/b" caía a un formato con vídeo. Dejando que yt-dlp
            # elija cliente sí obtenemos audio puro (opus/m4a). El runtime de
            # JS (node) es necesario para resolver el nsig del cliente web.
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "--js-runtimes", "node",
            "-o", str(output),
        ]

        result = subprocess.run(cmd)

        if result.returncode != 0:
            print("   FAILED DOWNLOAD")
            continue

        mp3 = outdir / f"{i:02d} - {title}.mp3"

        tag_mp3(
            mp3=mp3,
            title=title,
            artist=artist_str,
            album=album,
            album_artist=album_artist,
            year=year,
            genre=genre,
            track=i,
            total=len(tracks),
            cover=cover,
        )

        print("   OK")

    print(f"\nFinished installing '{album}'.")