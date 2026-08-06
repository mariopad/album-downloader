import random
import subprocess
import sys
import time
from pathlib import Path

from core.cover import get_cover
from core.tagger import tag_mp3
from core.lyrics import get_lyrics


# Cuántos resultados de YouTube pedir para elegir el mejor por duración.
SEARCH_RESULTS = 5

# Si el mejor candidato se aleja más de esto (segundos) de la duración
# esperada, avisamos: probablemente sea una versión en vivo, un remix,
# un edit acelerado o directamente la canción equivocada.
DURATION_TOLERANCE = 20

# --- Robustez frente a 403/429 de YouTube ---
#
# YouTube devuelve 403 (Forbidden), 429 (Too Many Requests) o pide
# "confirmar que no eres un bot" de forma intermitente. yt-dlp reintenta a
# nivel HTTP con --retries, pero eso repite SIEMPRE el mismo player_client,
# así que no sortea un bloqueo por cliente/firma. La estrategia robusta es:
#   1) reintentar con backoff exponencial (para 429/ratelimit), y
#   2) rotar el player_client de yt-dlp (para 403/bloqueos de firma/bot).
# Un error no transitorio (vídeo privado, borrado, etc.) falla rápido sin
# malgastar rotaciones.

# Intentos por cada cliente antes de rotar al siguiente.
MAX_ATTEMPTS_PER_CLIENT = 3

# Clientes a rotar en la DESCARGA. None = sin override: yt-dlp elige el
# cliente web (audio puro opus/m4a); ver nota en el comando de descarga.
# tv/ios/mweb/web_safari suelen esquivar bloqueos que afectan al web.
DOWNLOAD_CLIENTS = [None, "tv", "ios", "mweb", "web_safari"]

# Clientes a rotar en la BÚSQUEDA (más ligera; android suele bastar).
SEARCH_CLIENTS = ["android", "web", "ios", "tv"]

# Enfriamiento antes de la segunda pasada sobre las pistas fallidas: si
# fallaron por rate-limit, esperar da margen a que YouTube nos vuelva a servir.
RETRY_PASS_COOLDOWN = 15

# Backoff máximo (segundos) entre reintentos del mismo cliente.
MAX_BACKOFF = 30

# Señales, en la salida de yt-dlp, de un error TRANSITORIO que merece
# reintentar/rotar cliente (en minúsculas).
_TRANSIENT_SIGNS = (
    "http error 403",
    "forbidden",
    "http error 429",
    "too many requests",
    "sign in to confirm",
    "confirm you're not a bot",
    "unable to download",
    "read timed out",
    "connection reset",
    "connection aborted",
    "temporary failure",
    "timed out",
    "the read operation timed out",
    "unable to extract",
)


def _is_transient(text: str) -> bool:
    """¿La salida de yt-dlp indica un fallo transitorio (403/429/bot/red)?"""
    low = text.lower()
    return any(sign in low for sign in _TRANSIENT_SIGNS)


def _run_ytdlp(base_cmd, clients, describe="", attempts_per_client=None):
    """
    Ejecuta yt-dlp rotando `clients` y reintentando con backoff exponencial.

    - base_cmd: comando yt-dlp SIN el `--extractor-args player_client=...`
      (lo añade este helper por cada cliente).
    - clients:  lista de player_client a probar en orden. None = sin override.
    - describe: etiqueta corta para los mensajes ("search"/"download").

    Para en el primer éxito (returncode 0). Ante un error NO transitorio no
    insiste: devuelve enseguida. Devuelve (returncode, salida_combinada).
    """
    attempts = attempts_per_client or MAX_ATTEMPTS_PER_CLIENT
    last_rc, last_out = 1, ""
    label = f" [{describe}]" if describe else ""

    for client in clients:
        cmd = list(base_cmd)
        if client:
            cmd += ["--extractor-args", f"youtube:player_client={client}"]
        tag = client or "default"

        for attempt in range(1, attempts + 1):
            result = subprocess.run(cmd, capture_output=True, text=True)
            out = (result.stdout or "") + (result.stderr or "")
            last_rc, last_out = result.returncode, out

            if result.returncode == 0:
                return 0, out

            # Fallo no transitorio (privado, borrado, sin resultados...): no
            # vale la pena rotar clientes ni reintentar, falla rápido.
            if not _is_transient(out):
                return result.returncode, out

            if attempt < attempts:
                # Backoff exponencial con jitter (2^n s), acotado.
                delay = min(2 ** attempt + random.uniform(0, 1.5), MAX_BACKOFF)
                print(
                    f"   retry{label}: bloqueo transitorio (client={tag}), "
                    f"intento {attempt}/{attempts}, espera {delay:.0f}s"
                )
                time.sleep(delay)
            else:
                print(f"   retry{label}: client={tag} agotado, rotando cliente")

    return last_rc, last_out


def _search_candidates(query: str, n: int):
    """
    Pide los primeros `n` resultados de YouTube para `query` y devuelve
    una lista de (duración_en_segundos | None, video_id), sin descargar.
    """
    base = [
        sys.executable,
        "-m",
        "yt_dlp",
        f"ytsearch{n}:{query}",
        "--flat-playlist",
        "--print", "%(duration)s\t%(id)s",
        "--no-warnings",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    ]

    # Rota clientes/reintenta si YouTube devuelve 403/429 en la búsqueda.
    _rc, out = _run_ytdlp(base, SEARCH_CLIENTS, describe="search")

    candidates = []
    for line in out.splitlines():
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


# El buscador de YouTube devuelve CERO resultados para algunas queries
# cortas (p.ej. un título de una sola palabra malsonante como "Puta"): no es
# un 403/429 ni un problema de cliente —rotar player_client o reintentar no
# cambia nada—, la query en sí no da resultados. Añadir un término descriptivo
# la rescata. Probamos varias formulaciones en orden y usamos la primera que
# devuelva candidatos.
def _search_queries(artist: str, title: str):
    return [
        f"{artist} - {title} audio",
        f"{artist} {title} official audio",
        f"{artist} {title} letra",
    ]


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
                  dry_run=False, bitrate=None, lyrics=True):
    """
    Descarga y etiqueta un álbum. Devuelve un resumen:
        {"ok": [...], "skipped": [...], "failed": [...]}

    - outdir_base: carpeta raíz de salida (se crea outdir_base/<álbum>).
    - force:       vuelve a descargar aunque el mp3 ya exista.
    - dry_run:     no descarga; solo muestra qué se buscaría/elegiría.
    - bitrate:     bitrate de audio (p.ej. "192K"). None = mejor VBR.
    - lyrics:      incrusta letra (USLT) desde LRCLIB y guarda .lrc.
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

    ok, skipped = [], []
    # Pistas que fallaron la descarga, guardadas con su índice para una
    # segunda pasada al final del álbum.
    failed_tracks = []

    def process(i, track, is_retry=False):
        """
        Busca, descarga y etiqueta una pista. Devuelve (status, label) con
        status en {"ok", "skipped", "failed"}. `is_retry` solo cambia los
        mensajes (segunda pasada sobre fallidas).
        """
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

        head = "retry " if is_retry else ""
        print(f"[{head}{i}/{len(tracks)}] {title}")

        # #3: reanudar. Si ya existe y no forzamos, saltamos.
        if not force and not dry_run and mp3.exists() and mp3.stat().st_size > 0:
            print("   SKIP (ya descargado)")
            return "skipped", label

        target = track.get("duration_s")

        # Verificación por duración: en vez de descargar a ciegas el primer
        # resultado, pedimos varios y elegimos el más cercano a la duración
        # que MusicBrainz reporta para esta pista. Si una formulación no
        # devuelve nada (búsqueda de YouTube que ignora ciertos títulos
        # cortos), probamos la siguiente antes de rendirnos.
        queries = _search_queries(artist, title)
        query = queries[0]
        candidates = []
        for q in queries:
            candidates = _search_candidates(q, SEARCH_RESULTS)
            if candidates:
                query = q
                break

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
            return "skipped", label

        output = outdir / f"{label}.%(ext)s"

        base_cmd = [
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
            # Espaciado suave entre peticiones para no disparar el rate-limit
            # (429) de YouTube en álbumes largos.
            "--sleep-requests", "1",
            # Nota: el primer cliente es None (sin override). Ese cliente web
            # sí expone formatos "audio only" (opus/m4a); android ya no, por el
            # experimento SABR de YouTube. El runtime de JS (node) resuelve el
            # nsig del cliente web. _run_ytdlp rota a tv/ios/... si hay 403.
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "--js-runtimes", "node",
            "-o", str(output),
        ]

        # Con --force reescribimos el archivo existente.
        if force:
            base_cmd.append("--force-overwrites")

        # Descarga robusta: reintenta con backoff y rota player_client ante
        # 403/429/bot-check. Solo se rinde tras agotar todos los clientes.
        rc, out = _run_ytdlp(base_cmd, DOWNLOAD_CLIENTS, describe="download")

        if rc != 0 or not mp3.exists():
            print("   FAILED DOWNLOAD")
            # Última línea de error de yt-dlp, útil para diagnosticar.
            err = [ln for ln in out.splitlines() if ln.strip().lower().startswith("error")]
            if err:
                print(f"   {err[-1].strip()}")
            return "failed", label

        # Letra (opcional). Nunca hace fallar la pista: si no hay, seguimos.
        plain = None
        if lyrics:
            lyrics_artist = track_artists[0] if track_artists else artist
            plain, synced = get_lyrics(
                lyrics_artist, title, album, track.get("duration_s")
            )
            if plain:
                print("   + lyrics")
            # Sidecar .lrc sincronizado para reproductores que lo usen.
            if synced:
                (outdir / f"{label}.lrc").write_text(synced, encoding="utf8")

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
            lyrics=plain,
        )

        print("   OK")
        return "ok", label

    for i, track in enumerate(tracks, start=1):
        status, label = process(i, track)
        if status == "ok":
            ok.append(label)
        elif status == "skipped":
            skipped.append(label)
        else:
            failed_tracks.append((i, track, label))

    # Segunda pasada sobre las pistas que fallaron la descarga. Un fallo suele
    # deberse a un 403/429 puntual; tras un enfriamiento y volviendo a rotar
    # clientes, muchas se recuperan. Solo se hace una vez, en modo real.
    if failed_tracks and not dry_run:
        print(
            f"\n--- Retrying {len(failed_tracks)} failed track(s) "
            f"after {RETRY_PASS_COOLDOWN}s cooldown ---\n"
        )
        time.sleep(RETRY_PASS_COOLDOWN)

        still_failed = []
        for i, track, _label in failed_tracks:
            status, label = process(i, track, is_retry=True)
            if status == "ok":
                ok.append(label)
            else:
                still_failed.append(label)
        failed = still_failed
    else:
        failed = [label for _i, _t, label in failed_tracks]

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