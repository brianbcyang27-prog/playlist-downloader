# Playlist Downloader

A small, cross-platform desktop app (macOS + Windows) for downloading video and
music with [yt-dlp](https://github.com/yt-dlp/yt-dlp). The engine is a Python
backend behind a plain HTML/CSS/JS UI — no Electron, no heavy framework.

On macOS it ships as a **real native application**: `Playlist Downloader.app`
opens its own window (a `WKWebView`, no browser and no terminal), starts and
stops its bundled Python backend itself, and is distributed as a drag-to-
Applications **`.dmg`**. On Windows the same backend runs via `scripts\run.bat`
and opens the UI in your browser.

It is tuned for large music playlists (tested against ~1,500 tracks), keeps a
crash-safe queue, writes full tags and embedded cover art, and can **compare a
folder against a playlist to tell you exactly which tracks are missing**.

---

## ⬇️ Download (macOS)

**No build required.** Grab the ready-to-run app from the
**[latest release](https://github.com/brianbcyang27-prog/playlist-downloader/releases/latest)**:

> **[`Playlist.Downloader.1.2.dmg`](https://github.com/brianbcyang27-prog/playlist-downloader/releases/latest)**
> — ≈19 MB, macOS; no Python needed.

1. Open the `.dmg` and drag **Playlist Downloader** into **Applications**.
2. Launch it from Launchpad or Spotlight. On the first open, right-click the app
   → **Open** → **Open** — it isn't notarized, so macOS asks once.
3. Install the two helpers it uses for YouTube downloads and audio conversion:

   ```sh
   brew install ffmpeg deno
   ```

New to the app? There's a built-in **guided tour** on first launch, and a full
written walkthrough in **[docs/TUTORIAL.md](docs/TUTORIAL.md)**.

Windows users run `scripts\run.bat` from the source tree instead.

---

## Highlights

- **Music and video** downloads, with a user-selectable output format
  (Audio: `mp3` / `m4a` / `opus` / `flac` / `wav` / original ·
  Video: `mp4` / `mkv` / `webm`).
- **Playlist sources**: YouTube / YouTube Music URL, Spotify playlist (with
  optional API credentials for accurate metadata), a plain text file of songs,
  or a local folder.
- **Choose where files go**, every time. Pressing **Start** asks for a
  destination folder (remembered for next time). A multi-track playlist is saved
  into its own folder named after the playlist, while a single video/song is
  written straight to the destination under its own name.
- **Full metadata + embedded cover art** on every track (`mutagen`), including
  album art taken from the source when available.
- **Crash-safe queue** in SQLite (WAL). Close the window mid-download and it
  picks up exactly where it left off.
- **Fast folder-vs-playlist compare**: 1,500 tracks against 3,000 files in
  ~0.1 s, thanks to `rapidfuzz` plus a token/prefix index.
- **Smart search resolution**: tracks with no direct URL (Spotify / text) are
  resolved with `ytsearch1:` *in parallel*, then scored on title, artist and
  duration — so a 3-minute single never gets replaced by a 36-minute
  "Full Album" upload.
- **Resilient downloads**: in-worker retries with exponential backoff, plus one
  automatic cleanup pass over failures after a cooldown.
- **Smart archive**: finished items are never re-downloaded, but a stale archive
  entry whose file has since been deleted is detected and re-fetched.

---

## Requirements

- **Python 3.10+** (3.11–3.13 recommended).
- **ffmpeg** — required for audio conversion and muxing.
  - macOS: `brew install ffmpeg`
  - Windows: `winget install Gyan.FFmpeg` (or `choco install ffmpeg`)
- **A JavaScript runtime** for YouTube's player challenge — `deno`, `node`,
  `bun` or `quickjs`. Without one, many YouTube downloads fail with
  `HTTP Error 403: Forbidden`.
  - macOS: `brew install deno`
  - Windows: `winget install DenoLand.Deno`

Python packages (`yt-dlp`, `yt-dlp-ejs`, `mutagen`, `rapidfuzz`) are installed
automatically by the run scripts. `rapidfuzz` is optional — the compare still
works without it, just ~50× slower.

---

## Quick start

### macOS / Linux

Double-click **`scripts/run.command`** in Finder, or from a terminal:

```bash
./scripts/run.sh
```

On the first run it creates a `.venv`, installs dependencies, then opens your
browser to the app. After that it just starts.

### Windows

Double-click **`scripts\run.bat`**, or from a terminal:

```bat
scripts\run.bat
```

### Manual (any platform)

```bash
python -m venv .venv
# macOS/Linux:  source .venv/bin/activate
# Windows:      .venv\Scripts\activate
pip install -r requirements.txt
python -m app.server
```

Command-line flags (all optional):

```text
--port 8765        preferred HTTP port (falls back to a free one)
--host 127.0.0.1   bind address (localhost only by default)
--no-browser       do not auto-open a browser
```

The app is single-user and binds to `127.0.0.1` only.

---

## Native Mac app + `.dmg` (macOS)

Build a self-contained, double-clickable macOS application and a distributable
disk image:

```bash
./scripts/make_dmg.sh
```

This produces:

- **`build/Playlist Downloader.app`** — a real native app. Its window is a
  `WKWebView` (no browser, no terminal), with a normal menu bar, Dock icon and
  `⌘Q`. The app starts the Python backend itself on a free local port, waits for
  it to come up, then loads the UI into its own window.
- **`dist/Playlist Downloader 1.2.dmg`** — drag-to-Applications installer
  (contains the app plus an `Applications` shortcut).
- A copy installed to **`~/Applications`**, so it appears in Launchpad and
  Spotlight immediately.

The app is **self-contained**: a relocatable CPython 3.14, the standard library,
`yt-dlp`, `yt-dlp-ejs`, `mutagen` and `rapidfuzz` are all bundled inside
`Contents/Resources`, so it does not need Python, conda or a virtualenv on the
machine. `ffmpeg` and a JS runtime are still required (see *Requirements*).

```bash
./scripts/make_dmg.sh --no-dmg       # just build/install the .app (fast)
./scripts/make_dmg.sh --no-install   # build only, leave ~/Applications alone
```

What the launcher does, in order: locate the bundled interpreter →
pick a free port → spawn `python -m app.server --port <n> --no-browser` with
`PYTHONHOME`/`PYTHONPATH` pointed inside the bundle → poll `/api/ping` → load
the UI. Closing the window (or `⌘Q`, or the in-app **Quit** button) shuts the
backend down. Server logs go to
`~/Library/Application Support/PlaylistDownloader/app.log`.

Set `PLAYLIST_DOWNLOADER_DEBUG=1` in the environment to get startup tracing on
stderr when launching the binary directly.

> On a machine that blocks device-attaching tools, the script falls back from
> `hdiutil create` to `hdiutil makehybrid` + `hdiutil convert` (both pure
> userspace) and still writes a checksum-valid, mountable `.dmg`.

> A `.app`/`.dmg` is macOS-only. On Windows, use `scripts\run.bat`.

---

## Using it

> **New here?** The app has a built-in **step-by-step guided tour** — press
> **❓ How to use** in the top-right corner of the window (it also plays
> automatically the first time you open the app). Prefer to read? There's a full
> written walkthrough with screenshots-free instructions in
> **[docs/TUTORIAL.md](docs/TUTORIAL.md)**.

1. **Add a playlist.** Paste a YouTube / YouTube Music / Spotify URL, pick a
   text file, or point at a local music folder.
2. **Review the tracks.** Everything is listed with its resolved metadata.
3. **Pick your format** in Settings (audio or video, quality, file naming).
4. **Choose where to save, then Start.** Pressing **Start** first asks which
   folder to save into (your last choice is remembered) — multi-track playlists
   get their own sub-folder named after the playlist. Progress then streams live
   over Server-Sent Events. You can pause, resume, stop, retry individual items,
   or retry every failure at once.
5. **Compare (optional).** Point "Compare" at a folder you already have and the
   app reports **matched**, **missing** (with the closest on-disk file as a
   hint) and **extra** tracks. Missing tracks can be sent straight back into the
   download queue.

### Where things live

Everything the app writes lives under one per-user folder:

| Platform | Location |
| --- | --- |
| macOS | `~/Library/Application Support/PlaylistDownloader` |
| Windows | `%APPDATA%\PlaylistDownloader` |
| Linux | `~/.config/PlaylistDownloader` |

It contains `config.json`, `queue.db`, `download-archive.txt` and a `cache/`
folder. Back it up or delete it as a unit. Set `PLAYLIST_DOWNLOADER_HOME` to
override the location.

---

## Troubleshooting

**`HTTP Error 403: Forbidden` on YouTube.** Your JS runtime is missing. Install
`deno` / `node` / `bun` / `quickjs` (above). The Settings panel shows a
"JS challenge" health indicator so you can confirm it is detected.

**Audio conversion fails / files come out wrong.** ffmpeg is not on your PATH.
Install it and check the "ffmpeg" indicator in Settings.

**Compare on a huge folder is slow.** Install `rapidfuzz`
(`pip install rapidfuzz`); the Settings panel shows a "fast match" indicator.

**A track keeps failing.** Enable cookies in Settings (`cookies_from_browser`)
— some videos require a signed-in session.

---

## Building a standalone executable

On macOS, prefer `./scripts/make_dmg.sh` (above) — it produces a real native
`.app` + `.dmg` and needs no extra tooling.

If you want a single-file binary instead (any platform), the PyInstaller spec is
still available:

```bash
pip install pyinstaller
pyinstaller playlist_downloader.spec
# macOS/Linux -> dist/PlaylistDownloader
# Windows     -> dist\PlaylistDownloader.exe
```

Note the PyInstaller binary still opens the UI in a **browser**; the native
window comes from `make_dmg.sh` on macOS.

---

## Development

```bash
python -m tests.test_core     # correctness + 1,500x3,000 scale check
```

No test framework needed — it is a plain self-check script so the install
footprint stays small.

### Project layout

```text
app/
  __init__.py    package metadata / version
  __main__.py    `python -m app` entry point
  paths.py       per-user config/db/cache locations (macOS, Windows, Linux)
  config.py      defaults, validation, persistence, tool health
  db.py          SQLite schema + migrations (the persistent queue)
  events.py      in-process pub/sub for live progress
  playlist.py    YouTube / Spotify / text-file import + metadata
  matcher.py     folder-vs-playlist compare engine (rapidfuzz)
  tagging.py     read/write tags + embedded cover art (mutagen)
  downloader.py  worker pool, retries, ytsearch resolution, finalize
  api.py         HTTP routes, SSE, background jobs
  server.py      entry point, port picking, browser launch
web/             static UI (index.html, styles.css, app.js)
scripts/
  run.sh / run.command / run.bat   dev launchers (browser UI)
  native_app.swift                 the macOS app shell (window + backend lifecycle)
  bundle_python.py                 builds the self-contained CPython runtime
  make_dmg.sh                      builds the .app and the .dmg
  make_icon.py                     generates the app icon
docs/            TUTORIAL.md — end-user walkthrough
tests/           test_core.py self-check suite
playlist_downloader.spec   optional PyInstaller spec (single-file binary)
```
