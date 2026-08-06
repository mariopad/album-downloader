# Album downloader

A small CLI tool that downloads full albums for an **old iPod** (or
any music player), tagged properly and ready to sync.

It pulls the correct tracklist and metadata from **MusicBrainz**, finds each
track on **YouTube**, downloads **audio only**, converts to MP3, and writes
clean **ID3v2.3** tags (title, artist, album, track/disc numbers, year, genre,
cover art, and lyrics).

> **Personal use.** This tool downloads audio from YouTube for your own
> library.

---

## Features

- **Right track, not the first hit.** For every song it fetches several
  YouTube results and picks the one whose **duration matches MusicBrainz**, so
  you don't silently end up with a live version, a sped-up edit, or an
  hour-long loop. It warns when even the closest match is suspicious.
- **Audio only.** Downloads `bestaudio` (opus/m4a), then converts to MP3.
- **iPod-friendly tags.** ID3**v2.3**, FAT-safe filenames, per-disc track
  numbering, embedded cover art, and embedded lyrics.
- **Safe to re-run.** Already-downloaded tracks are skipped; a failed run
  resumes instead of starting over. A track counts as done only if it has the
  audio **and** its lyrics — if the MP3 is already there but has no lyrics,
  re-running fetches and embeds them **without re-downloading the audio** (handy
  for libraries pulled before lyrics existed).
- **Honest about failures.** Every run ends with an `ok / skipped / failed`
  summary and exits non-zero if anything failed.

---

## Requirements

**System tools** (install with your package manager):

| Tool | Why |
|------|-----|
| **Python 3.10+** | the app |
| **ffmpeg** | extract/convert audio to MP3 |
| **Node.js** | `yt-dlp` uses it to solve YouTube's signature challenge |

**Python packages** (`requirements.txt`): `yt-dlp`, `mutagen`, `Pillow`,
`requests`, `musicbrainzngs`.

### Quick setup

`setup.sh` checks the system tools, creates a `.venv`, and installs the
Python packages:

```bash
./setup.sh
source .venv/bin/activate
```

Or do it manually:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Usage

```bash
python musicdl.py install "Artist" "Album" [options]
```

### Examples

```bash
# One album
python musicdl.py install "Bad Bunny" "DeBÍ TiRAR MáS FOToS"

# Preview the match without downloading anything
python musicdl.py install "Daft Punk" "Discovery" --dry-run

# Choose the output folder
python musicdl.py install "Radiohead" "In Rainbows" --outdir ~/Music

# List every edition of an album (to avoid a bonus-track reissue)
python musicdl.py install "MF DOOM" "Operation: Doomsday" --list-releases

# Pin one exact edition by its MusicBrainz release ID
python musicdl.py install "MF DOOM" "Operation: Doomsday" \
    --release-id 2ed8a86a-7396-4aef-8b0f-21e6dc6ade9a

# Smaller files so more songs fit on the iPod
python musicdl.py install "Radiohead" "In Rainbows" --bitrate 192K

# Re-download even if the MP3s already exist
python musicdl.py install "Radiohead" "In Rainbows" --force

# Batch: one "Artist | Album" per line
python musicdl.py install --from-file albums.txt
```

`albums.txt`:

```
# lines starting with # are ignored
Radiohead | In Rainbows
Daft Punk | Discovery
Pink Floyd | The Wall
```

### Options

| Option | Description |
|--------|-------------|
| `artist album` | The album to download (omit when using `--from-file`). |
| `--from-file PATH` | Batch mode: `Artist \| Album` (or tab-separated) per line. |
| `--outdir DIR` | Base output folder (default: `ipod`). |
| `--list-releases` | List every MusicBrainz edition (date, track count, format, ID) and exit. The first, marked `*`, is the default choice. |
| `--release-id MBID` | Pin one exact edition by its MusicBrainz release ID — use it when the default pick is a reissue with bonus tracks instead of the original. Not valid with `--from-file`. |
| `--bitrate RATE` | Fixed audio bitrate, e.g. `192K` (default: best VBR, ~256 kbps). |
| `--force` | Re-download tracks even if the MP3 already exists. |
| `--no-lyrics` | Don't fetch/embed lyrics (on by default). |
| `--dry-run` | Show the MusicBrainz + YouTube match; download nothing. |

---

## Output

```
ipod/
└── In Rainbows/
    ├── 01 - 15 Step.mp3
    ├── 01 - 15 Step.lrc        # synced lyrics sidecar (if available)
    ├── 02 - Bodysnatchers.mp3
    └── ...
```

Multi-disc albums are prefixed by disc to keep order and avoid collisions
(`1-01 - …`, `2-01 - …`).

Each MP3 gets: **title, artist, album, album artist, track/total,
disc/total, year, genre, 500 px cover** (Cover Art Archive), and **unsynced
lyrics** (`USLT`, from [LRCLIB](https://lrclib.net)).

### Lyrics

- They will be displayed on the **iPod**
- On **Android**, they will only be displayed in players that support embedded/`.lrc` lyrics (e.g.
  Poweramp, Musicolet, Retro Music).
- They will probably not be displayed on **iPhone**

Coverage from LRCLIB is very high for mainstream music; instrumental tracks
and misses are skipped silently. Use `--no-lyrics` to turn the feature off.

---

## How it works

```
MusicBrainz  ──►  pick best release, tracklist, durations, disc layout
                       │
                       ▼
YouTube      ──►  search N results, choose the closest duration
                       │
                       ▼
yt-dlp       ──►  download bestaudio ──► ffmpeg ──► MP3
                       │
                       ▼
tag          ──►  ID3v2.3 + cover (Cover Art Archive) + lyrics (LRCLIB)
```

Album metadata is cached under `cache/<artist>/<album>.json`. The cache is
**versioned** — when the metadata format changes, stale entries are ignored
and re-fetched automatically, so you never run on outdated data.

---

## Notes & limitations

- The duration check warns but still downloads the closest match when nothing
  is within tolerance — sanity-check odd albums with `--dry-run` first.
- Releases with no date in MusicBrainz get an empty year; genre falls back to
  `Unknown`.
- Getting the files **onto** the iPod is a separate step (iTunes / Finder, or
  `gtkpod` / Rhythmbox on Linux).
