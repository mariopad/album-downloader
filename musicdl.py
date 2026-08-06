import argparse
import sys

from core.metadata import fetch_album, list_releases
from core.downloader import install_album
from core.cache import load_cache, save_cache


def get_metadata(artist: str, album: str, release_id: str = None) -> dict:
    """Devuelve los metadatos del álbum, usando la caché si está vigente."""
    data = load_cache(artist, album, release_id)

    if data is None:
        print(f"Fetching metadata for '{artist} - {album}' from MusicBrainz...")
        data = fetch_album(artist, album, release_id)
        save_cache(artist, album, data, release_id)
    else:
        print(f"Using cached metadata for '{artist} - {album}'.")

    return data


def print_releases(artist: str, album: str):
    """Lista las ediciones disponibles de un álbum para elegir con --release-id."""
    releases = list_releases(artist, album)
    if not releases:
        print(f"No se encontró '{album}' de '{artist}'.")
        return

    print(f"Releases for '{artist} - {album}' (first = default choice):\n")
    for i, r in enumerate(releases):
        mark = "* " if i == 0 else "  "
        date = r["date"] or "----"
        print(
            f"{mark}{r['tracks']:>2} tracks  {date:<10}  {r['format']:<14} "
            f"{r['country']:<3}  {r['id']}"
        )
    print("\nPin one with:  --release-id <ID>")


def read_album_list(path: str):
    """
    Lee un archivo de álbumes en lote. Una línea por álbum:

        Artista | Álbum

    También se acepta un tabulador como separador. Las líneas vacías y las
    que empiezan por '#' se ignoran.
    """
    albums = []

    with open(path, encoding="utf8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()

            if not line or line.startswith("#"):
                continue

            if "\t" in line:
                artist, _, album = line.partition("\t")
            elif "|" in line:
                artist, _, album = line.partition("|")
            else:
                print(f"  {path}:{lineno}: línea inválida (usa 'Artista | Álbum'): {line}")
                continue

            artist, album = artist.strip(), album.strip()
            if artist and album:
                albums.append((artist, album))
            else:
                print(f"  {path}:{lineno}: artista o álbum vacío: {line}")

    return albums


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="musicdl",
        description="Descarga álbumes desde YouTube con metadatos de MusicBrainz.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="Descarga un álbum (o varios en lote).")
    p.add_argument("artist", nargs="?", help="Nombre del artista.")
    p.add_argument("album", nargs="?", help="Nombre del álbum.")
    p.add_argument(
        "--from-file",
        metavar="PATH",
        help="Archivo con 'Artista | Álbum' por línea (modo lote).",
    )
    p.add_argument(
        "--outdir",
        default="ipod",
        help="Carpeta base de salida (por defecto: ipod).",
    )
    p.add_argument(
        "--release-id",
        metavar="MBID",
        help="Fija una edición concreta por su MusicBrainz release ID "
             "(evita reediciones con bonus tracks). Usa --list-releases "
             "para ver los IDs disponibles. No válido con --from-file.",
    )
    p.add_argument(
        "--list-releases",
        action="store_true",
        help="Lista las ediciones del álbum (fecha, nº pistas, formato, ID) "
             "y sale, sin descargar. Elige una con --release-id.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Vuelve a descargar aunque el mp3 ya exista.",
    )
    p.add_argument(
        "--bitrate",
        metavar="RATE",
        help="Bitrate de audio, p.ej. 192K (por defecto: mejor VBR). "
             "Baja el bitrate para que quepan más canciones en el iPod.",
    )
    p.add_argument(
        "--no-lyrics",
        dest="lyrics",
        action="store_false",
        help="No incrusta letras. Por defecto se buscan en LRCLIB y se "
             "incrustan (USLT) + se guarda un .lrc sincronizado.",
    )
    p.set_defaults(lyrics=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="No descarga: muestra qué se buscaría y elegiría.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # --release-id y --list-releases fijan/listan UNA edición: no tienen
    # sentido en modo lote, donde un solo ID no puede valer para varios álbumes.
    if args.from_file and (args.release_id or args.list_releases):
        parser.error("--release-id/--list-releases no son válidos con --from-file")

    if args.from_file:
        albums = read_album_list(args.from_file)
        if not albums:
            print("No hay álbumes válidos en el archivo.")
            sys.exit(1)
    else:
        if not args.artist or not args.album:
            parser.error("se requieren 'artist' y 'album' (o --from-file)")
        albums = [(args.artist, args.album)]

    # Solo listar ediciones y salir (no descarga nada).
    if args.list_releases:
        print_releases(args.artist, args.album)
        return

    total_failed = 0

    for artist, album in albums:
        try:
            data = get_metadata(artist, album, args.release_id)
        except Exception as e:
            print(f"Metadata error for '{artist} - {album}': {e}")
            total_failed += 1
            continue

        summary = install_album(
            data,
            outdir_base=args.outdir,
            force=args.force,
            dry_run=args.dry_run,
            bitrate=args.bitrate,
            lyrics=args.lyrics,
        )
        total_failed += len(summary["failed"])

    # Salida distinta de cero si algo falló, útil para scripts.
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
