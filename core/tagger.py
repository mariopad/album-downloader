from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TPE2,
    TRCK, TPOS, TDRC, TCON, APIC, USLT
)


def tag_mp3(mp3, title, artist, album, album_artist,
            year, genre, track, total, cover=None,
            disc=1, disc_total=1, lyrics=None):

    tags = ID3()

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TPE2(encoding=3, text=album_artist))
    tags.add(TRCK(encoding=3, text=f"{track}/{total}"))
    tags.add(TPOS(encoding=3, text=f"{disc}/{disc_total}"))
    tags.add(TDRC(encoding=3, text=year))
    tags.add(TCON(encoding=3, text=genre))

    # Letra sin sincronizar: es lo que muestra la pantalla del iPod. La
    # descripción vacía y lang="eng" es la combinación que iTunes/iPod leen.
    if lyrics:
        tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))

    if cover:
        tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=cover
        ))

    tags.save(mp3, v2_version=3)