from __future__ import annotations

from typing import Dict, List
import musicbrainzngs

musicbrainzngs.set_useragent(
    "musicdl",
    "1.0",
    "https://github.com/yourname/musicdl",
)


def _release_score(release: dict, wanted_artist: str, wanted_album: str) -> int:
    score = 0

    #
    # Artista (lo más importante)
    #

    artist_credit = (
        release.get("artist-credit", [{}])[0]
        .get("artist", {})
        .get("name", "")
    ).casefold()

    wanted = wanted_artist.casefold()

    if artist_credit == wanted:
        score += 1000
    elif wanted in artist_credit:
        score += 300
    else:
        score -= 1000

    #
    # Album
    #

    title = release.get("title", "").casefold()
    wanted_title = wanted_album.casefold()

    if title == wanted_title:
        score += 500
    elif wanted_title in title:
        score += 100

    #
    # Tipo de release
    #

    primary = (
        release.get("release-group", {})
        .get("primary-type")
    )

    match primary:
        case "Album":
            score += 500
        case "EP":
            score += 200
        case "Single":
            score -= 1000

    #
    # Estado
    #

    if release.get("status") == "Official":
        score += 300

    #
    # Número de discos
    #

    media = release.get("medium-list", [])

    # if len(media) == 1:
    #     score += 100
    # else:
    #     score -= 300

    #
    # Formato preferido
    #

    formats = {
        m.get("format")
        for m in media
    }

    if "Digital Media" in formats:
        score += 50
    elif "CD" in formats:
        score += 40
    elif "Vinyl" in formats:
        score += 20

    #
    # País
    #

    country = release.get("country")

    if country == "XW":          # Worldwide
        score += 60
    elif country == "US":
        score += 50
    elif country == "GB":
        score += 40

    #
    # Fecha
    # Prefiere la edición más antigua.
    #

    # date = release.get("date")

    # if date:
    #     try:
    #         year = int(date[:4])
    #         score += (2026 - year) * 10
    #     except Exception:
    #         pass

    return score


def _choose_release(releases: List[dict], wanted_artist: str, wanted_album: str) -> dict:
    if not releases:
        raise RuntimeError("No releases reaturned by MusicBrainz.")

    releases = sorted(
        releases,
        key=lambda r: (_release_score(r, wanted_artist, wanted_album), r.get("date", "")),
        reverse=True,
    )

    return releases[0]


def _parse_artist_credit(artist_credit) -> List[str]:
    """
    Convierte MusicBrainz artist-credit en lista limpia de artistas.
    """
    artists = []

    for part in artist_credit:
        if isinstance(part, dict) and "artist" in part:
            name = part["artist"]["name"]
            if name:
                artists.append(name)

    return artists


def fetch_album(artist: str, album: str) -> Dict:
    search = musicbrainzngs.search_releases(
        artist=artist,
        release=album,
        limit=10,
    )

    releases = search.get("release-list", [])

    if not releases:
        raise RuntimeError(f"No se encontró '{album}' de '{artist}'.")

    release = _choose_release(releases, artist, album)
    mbid = release["id"]

    details = musicbrainzngs.get_release_by_id(
        mbid,
        includes=[
            "artists",
            "artist-credits",
            "recordings",
            "release-groups",
        ],
    )["release"]

    artist_credit = details.get("artist-credit", [])

    # ✅ FIX CRÍTICO: album artist correcto (NO concatenado)
    album_artist = (
        artist_credit[0]["artist"]["name"]
        if artist_credit and isinstance(artist_credit[0], dict)
        else artist
    )

    release_date = details.get("date", "")
    year = int(release_date[:4]) if release_date else None

    # Genre
    genre = "Unknown"

    rg_id = details.get("release-group", {}).get("id")
    if rg_id:
        rg = musicbrainzngs.get_release_group_by_id(
            rg_id,
            includes=["tags"]
        )["release-group"]

        tags = rg.get("tag-list", [])

        valid = [
            t for t in tags
            if t.get("name")
            and int(t.get("count", 0)) > 0
            and t["name"].lower() not in {"seen live", "favorites", "all"}
        ]

        if valid:
            genre = max(valid, key=lambda t: int(t["count"]))["name"].title()

    tracks = []

    for medium in details.get("medium-list", []):
        for track in medium.get("track-list", []):

            recording = track.get("recording", {})

            credits = recording.get(
                "artist-credit",
                artist_credit
            )

            artists = _parse_artist_credit(credits)

            tracks.append({
                "title": recording.get("title", ""),
                "artists": artists,
            })

    return {
        "artist": artist,
        "album": details.get("title", album),
        "album_artist": album_artist,
        "year": year,
        "genre": genre,
        "musicbrainz_release_id": mbid,
        "tracks": tracks,
    }