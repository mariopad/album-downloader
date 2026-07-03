from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TPE2,
    TRCK, TDRC, TCON, APIC
)


def tag_mp3(mp3, title, artist, album, album_artist,
            year, genre, track, total, cover=None):

    tags = ID3()

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TPE2(encoding=3, text=album_artist))
    tags.add(TRCK(encoding=3, text=f"{track}/{total}"))
    tags.add(TDRC(encoding=3, text=year))
    tags.add(TCON(encoding=3, text=genre))

    if cover:
        tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=cover
        ))

    tags.save(mp3, v2_version=3)