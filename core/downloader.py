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


# Caracteres reservados en FAT32/Windows (el iPod usa FAT). Sin sanear,
# un título con "/" partiría la ruta y crearía subcarpetas fantasma.
_RESERVED = {
    "/": "-",
    "\\": "-",
    ":": " -",
    "*": "",
    "?": "",
    '"': "'",
    "<": "(",
    ">": ")",
    "|": "-",
}


def _safe_filename(name: str) -> str:
    """
    Convierte un título en un nombre de archivo válido y seguro:
    reemplaza caracteres reservados, quita caracteres de control y
    recorta espacios/puntos finales (no permitidos en FAT/Windows).
    """
    name = "".join(_RESERVED.get(c, c) for c in name)
    name = "".join(c for c in name if ord(c) >= 32)
    name = name.strip().rstrip(". ")

    return name or "untitled"


def install_album(data: dict, outdir_base="ipod", force=False,
                  dry_run=False, bitrate=None):
    """
    Descarga y etiqueta un álbum. Devuelve un resumen:
        {"ok": [...], "skipped": [...], "failed": [...]}

    - outdir_base: carpeta raíz de salida (se crea outdir_base/<álbum>).
    - force:       vuelve a descargar aunque el mp3 ya exista.
    - dry_run:     no descarga; solo muestra qué se buscaría/elegiría.
    - bitrate:     bitrate de audio (p.ej. "192K"). None = mejor VBR.
    """

    artist = data["artist"]
    album = data["album"]
    album_artist = data.get("album_artist", artist)
    year = str(data["year"])
    genre = data["genre"]
    tracks = data["tracks"]

    outdir = Path(outdir_base) / _safe_filename(album)

    cover = None
    if not dry_run:
        cover = get_cover(data)
        outdir.mkdir(parents=True, exist_ok=True)

    # Con varios discos, prefijamos el nombre con el disco para ordenar
    # y evitar colisiones (disco 1 pista 1 vs disco 2 pista 1).
    multi_disc = any(t.get("disc_total", 1) > 1 for t in tracks)

    mode = " (dry-run)" if dry_run else ""
    print(f"\n=== Installing {artist} - {album}{mode} ===\n")

    ok, skipped, failed = [], [], []

    for i, track in enumerate(tracks, start=1):

        title = track["title"]
        track_artists = track.get("artists", [artist])
        artist_str = ", ".join(track_artists)

        # Numeración por disco (con fallback al índice global para cachés
        # viejas o metadatos sin estos campos).
        disc = track.get("disc", 1)
        disc_total = track.get("disc_total", 1)
        track_no = track.get("track_no", i)
        track_total = track.get("track_total", len(tracks))

        # #4: nombre de archivo saneado (evita romper rutas con "/", etc.).
        prefix = f"{disc}-{track_no:02d}" if multi_disc else f"{track_no:02d}"
        label = f"{prefix} - {_safe_filename(title)}"
        mp3 = outdir / f"{label}.mp3"

        print(f"[{i}/{len(tracks)}] {title}")

        # #3: reanudar. Si ya existe y no forzamos, saltamos.
        if not force and not dry_run and mp3.exists() and mp3.stat().st_size > 0:
            print("   SKIP (ya descargado)")
            skipped.append(label)
            continue

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

        # #5: dry-run — mostrar el candidato elegido sin descargar ni etiquetar.
        if dry_run:
            if video_id:
                d = f"{diff:.0f}s" if diff is not None else "n/a"
                print(f"   would fetch {source}  (Δdur {d})")
            else:
                print(f"   would fetch first result of: ytsearch1:{query}")
            continue

        output = outdir / f"{label}.%(ext)s"

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            source,
            "-f", "ba/b",
            "-x",
            "--audio-format", "mp3",
            # Sin bitrate: mejor VBR ("0"). Con bitrate: CBR fijo (p.ej.
            # "192K") para controlar el tamaño en el iPod.
            "--audio-quality", bitrate if bitrate else "0",
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

        # Con --force reescribimos el archivo existente.
        if force:
            cmd.append("--force-overwrites")

        result = subprocess.run(cmd)

        if result.returncode != 0 or not mp3.exists():
            print("   FAILED DOWNLOAD")
            failed.append(label)
            continue

        tag_mp3(
            mp3=mp3,
            title=title,
            artist=artist_str,
            album=album,
            album_artist=album_artist,
            year=year,
            genre=genre,
            track=track_no,
            total=track_total,
            cover=cover,
            disc=disc,
            disc_total=disc_total,
        )

        print("   OK")
        ok.append(label)

    # #4: resumen final — nunca terminar en silencio con pistas faltantes.
    if dry_run:
        print(f"\nDry-run for '{album}': {len(tracks)} tracks previewed.")
    else:
        print(
            f"\nSummary for '{album}': "
            f"{len(ok)} ok, {len(skipped)} skipped, {len(failed)} failed."
        )
        if failed:
            print("Failed tracks:")
            for t in failed:
                print(f"   - {t}")

    return {"ok": ok, "skipped": skipped, "failed": failed}