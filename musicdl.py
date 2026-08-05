import argparse
import sys

from core.metadata import fetch_album
from core.downloader import install_album
from core.cache import load_cache, save_cache


def get_metadata(artist: str, album: str) -> dict:
    """Devuelve los metadatos del álbum, usando la caché si está vigente."""
    data = load_cache(artist, album)

    if data is None:
        print(f"Fetching metadata for '{artist} - {album}' from MusicBrainz...")
        data = fetch_album(artist, album)
        save_cache(artist, album, data)
    else:
        print(f"Using cached metadata for '{artist} - {album}'.")

    return data


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
        "--force",
        action="store_true",
        help="Vuelve a descargar aunque el mp3 ya exista.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="No descarga: muestra qué se buscaría y elegiría.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.from_file:
        albums = read_album_list(args.from_file)
        if not albums:
            print("No hay álbumes válidos en el archivo.")
            sys.exit(1)
    else:
        if not args.artist or not args.album:
            parser.error("se requieren 'artist' y 'album' (o --from-file)")
        albums = [(args.artist, args.album)]

    total_failed = 0

    for artist, album in albums:
        try:
            data = get_metadata(artist, album)
        except Exception as e:
            print(f"Metadata error for '{artist} - {album}': {e}")
            total_failed += 1
            continue

        summary = install_album(
            data,
            outdir_base=args.outdir,
            force=args.force,
            dry_run=args.dry_run,
        )
        total_failed += len(summary["failed"])

    # Salida distinta de cero si algo falló, útil para scripts.
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
