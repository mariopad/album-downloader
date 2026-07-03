import sys

from core.metadata import fetch_album
from core.downloader import install_album
from core.cache import load_cache, save_cache

def main():

    if len(sys.argv) != 4:
        print("Usage:")
        print('  python musicdl.py install "Artist" "Album"')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd != "install":
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    artist = sys.argv[2]
    album = sys.argv[3]

    try:
        data = load_cache(artist, album)

        if data is None:
            print("Fetching metadata from MusicBrainz...")

            data = fetch_album(artist, album)

            save_cache(artist, album, data)

        else:
            print("Using cached metadata.")
        
    except Exception as e:
        print(f"Metadata error: {e}")
        sys.exit(1)

    install_album(data)


if __name__ == "__main__":
    main()