import subprocess
import sys
from pathlib import Path

from core.cover import get_cover
from core.tagger import tag_mp3


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

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            f"ytsearch1:{query}",
            "-f", "bv*+ba/b",
            "-x",
            "--audio-format", "mp3",
            "--no-playlist",
            "--retries", "10",
            "--fragment-retries", "10",
            "--extractor-args", "youtube:player_client=android",
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