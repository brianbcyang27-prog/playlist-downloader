# How to use Playlist Downloader

A complete, start-to-finish walkthrough. If you only read one section, read
**[The 60-second version](#the-60-second-version)**.

There is also a built-in **guided tour** inside the app — press **❓ How to use**
in the top-right corner (it also plays automatically the first time you open the
app).

---

## Contents

1. [Install and open](#1-install-and-open)
2. [Add a playlist](#2-add-a-playlist)
3. [Review what was imported](#3-review-what-was-imported)
4. [Choose your format](#4-choose-your-format)
5. [Start downloading](#5-start-downloading)
6. [Watch progress and fix failures](#6-watch-progress-and-fix-failures)
7. [Find your files](#7-find-your-files)
8. [Bonus: find the songs you're missing](#8-bonus-find-the-songs-youre-missing)
9. [Bonus: huge playlists (1,000+ songs)](#9-bonus-huge-playlists-1000-songs)
10. [Settings reference](#10-settings-reference)
11. [Where your data lives](#11-where-your-data-lives)
12. [Troubleshooting](#12-troubleshooting)
13. [FAQ](#13-faq)

---

## The 60-second version

1. Open **Playlist Downloader**.
2. Paste a playlist link into **Add a playlist** → **Link or file path**.
3. Leave **Download as** on **Music (audio)**.
4. Press **＋ Import playlist**.
5. Press **▶ Start** in the top-right corner.
6. Wait. Files appear in `~/Downloads/Playlist Downloader`.

That's it. Everything below is detail.

---

## 1. Install and open

### macOS

1. Open **`Playlist Downloader 1.2.dmg`**.
2. Drag **Playlist Downloader** onto the **Applications** shortcut in the window.
3. Open it from **Launchpad** or **Spotlight** (press `⌘Space`, type
   "Playlist").

The first time you open it you may need to **right-click the app → Open** and
confirm. That's standard for apps distributed outside the App Store.

> The app is self-contained — it bundles its own Python. You do **not** need to
> install Python, and there is no terminal involved.

### Windows

Double-click **`scripts\run.bat`**. It sets up what it needs on first run and
opens the app in your browser.

### What it needs installed

Two external tools are still required, and the app tells you if they're missing:

| Tool | Why | Install (macOS) |
| --- | --- | --- |
| **ffmpeg** | Converts and tags audio/video | `brew install ffmpeg` |
| **deno** (or `node`/`bun`) | Solves YouTube's playback challenge | `brew install deno` |

After installing, restart the app. Open **Settings** and look at the status
badges at the bottom — they should read **ffmpeg ✓** and **JS challenge ✓**.

Without the JS runtime, many YouTube downloads fail with
`HTTP Error 403: Forbidden`. Without ffmpeg, conversion to MP3 fails.

---

## 2. Add a playlist

Open the **Download** tab (it's the default). In the **Add a playlist** panel on
the left:

### Pick a Source

| Source | Use it when |
| --- | --- |
| **Auto-detect** | Almost always. Just paste the link and the app figures out what it is. |
| **YouTube / YouTube Music** | You want to be explicit, e.g. a channel or a mix URL. |
| **Spotify playlist** | A `open.spotify.com/playlist/…` link. |
| **Text or CSV file** | You have a list of song names or URLs in a file. |

### Paste the link or path

Put it in **Link or file path**:

- **YouTube / YouTube Music** — `https://music.youtube.com/playlist?list=…`
- **Spotify** — `https://open.spotify.com/playlist/…`
- **Text file** — one song or URL per line, e.g.
  ```
  Daft Punk - Around the World
  https://www.youtube.com/watch?v=dQw4w9WgXcQ
  Radiohead - Weird Fishes
  ```
  (Also handles `.csv`.) A **local music folder** path works here too.
- **Local folder** — e.g. `/Users/you/Music/Albums`

> **Spotify note:** without credentials the app reads Spotify's public page, which
> caps at **100 tracks**. For longer playlists add a free Spotify Client ID/Secret
> in **Settings** first — see [Settings](#10-settings-reference).

### Choose Download as

| Option | Result |
| --- | --- |
| **Music (audio)** | Audio only, with tags and cover art. Use this for songs. |
| **Video** | The full video file. Use this for video playlists. |

### Import

Press **＋ Import playlist**.

Importing **only reads the list** — it resolves each track's title, artist and
duration. Nothing is downloaded yet. This is deliberate: you get to check the
list before committing to a big download.

---

## 3. Review what was imported

Your playlist now appears under **Your playlists** in the left sidebar, and its
tracks fill the **Queue** table:

| Column | Meaning |
| --- | --- |
| **#** | Position in the playlist |
| **Title** | Track title |
| **Artist** | Artist, when known |
| **Status** | `pending`, `downloading`, `done`, `skipped` or `failed` |
| **Progress** | Live progress bar while downloading |
| **⋯** | Per-track menu (retry / remove that one track) |

Two ways to tame a big list:

- **Filter by title or artist** — type in the search box.
- **All statuses** — show only `pending`, `failed`, etc.

Playlists are **saved between sessions**. Close the app, reopen it, click the
playlist in the sidebar, and your queue is exactly where you left it.

---

## 4. Choose your format

**This step is optional** — the defaults are good. When you want to change
something, go to the **Settings** tab. The parts that matter most:

- **Music → Format**: `mp3` (most compatible), `m4a`, `opus`, `flac` (lossless),
  `wav`, or `original` (keep whatever the source gives).
- **Music → Quality**: `320 kbps (best)` is the default.
- **Write tags / Embed cover art**: already on. Keep them on.
- **Download folder**: the base folder files go into. You can also set it each
  time you press **Start** (see [section 5](#5-start-downloading)).
- **Put a multi-track playlist in its own folder**: when on (the default), a
  playlist of many songs is saved into a sub-folder named after the playlist.
  A single video/song is written straight into the folder under its own name.

Press **💾 Save settings** at the bottom of the tab — changes apply only after
you save.

See [Settings reference](#10-settings-reference) for every option.

---

## 5. Start downloading

Press **▶ Start** in the top-right corner. The first thing it asks is **where to
save**, so nothing lands somewhere you didn't expect:

- **Save to folder** — type a path or press **Choose…** to browse for one. Your
  choice is remembered for next time.
- **Put a multi-track playlist in its own folder** — tick to save a playlist into
  a sub-folder named after the playlist (a single song or video is saved directly
  under its own name). The line underneath previews exactly where files will go.
- Press **Start download** to begin, or **Cancel** to back out.

While a download is running, the same toolbar shows:

| Button | What it does |
| --- | --- |
| **⏸ Pause** | Stops after the files in flight finish; nothing is lost. |
| **▶ Resume** | Carries on from where it paused. |
| **⏹ Stop** | Ends the run. Finished tracks stay finished. |
| **↻ Retry failed** | Re-queues every failed track. Use after a network blip. |
| **⏻ Quit** | Shuts the app and its background service down cleanly. |

The counters in the top bar update live: **total · done · skipped ·
downloading · pending · failed**.

You can close the window mid-download — the queue is crash-safe and picks up
exactly where it stopped.

---

## 6. Watch progress and fix failures

- The **Progress** column shows per-track progress.
- The **Activity** tab shows a running log of what the app is doing. If
  something looks stuck, look here first.
- A **failed** track can be retried on its own via the **⋯** button, or all at
  once with **↻ Retry failed**.

Failures are usually one of three things:

1. **`403 Forbidden`** → your JS runtime (deno/node) is missing.
2. **A private or age-restricted video** → set **Cookies from browser** (Settings
   → Access & networking) to your browser, then retry.
3. **A temporary network problem** → just press **↻ Retry failed**.

---

## 7. Find your files

By default, finished files land in:

```
~/Downloads/Playlist Downloader
```

**How they are named:** a playlist of many tracks lands in its own sub-folder
named after the playlist, e.g. `~/Downloads/Playlist Downloader/Rock Classics/`,
with each song saved as `Artist - Title.mp3` (or `Title.mp4` for video). A single
video/song — or a playlist with only one item — is written straight into the
destination folder as `Artist - Title.mp3`, with no extra folder. You choose the
destination (and whether to use the sub-folder) on the screen that appears when
you press **Start**, and it is remembered.

Open the folder instantly: **Settings → Where files go → Open folder**.

Tracks that were already downloaded are **skipped** (not downloaded twice), and
with **Never re-download finished tracks** enabled the app remembers everything
it has ever fetched.

---

## 8. Bonus: find the songs you're missing

This is the feature that makes the app more than a downloader.

Say you have a playlist of 1,500 songs and a folder of 3,000 music files, and
you're not sure what you actually own. The **Compare folder** tab tells you:

1. Open **Compare folder**.
2. **Playlist** — choose one of your imported playlists.
3. **Folder to scan** — press **Browse…** and pick your music folder.
4. **Match strictness** — leave on *balanced* unless you get bad results.
   - **Include sub-folders** — on, if your music is organised in album folders.
   - **Read ID3 tags** — on, for more accurate matching.
   - **Ignore extra files** — on, if you only care about what's missing.
5. Press **⇄ Compare**.

You get three lists:

| Tab | Meaning |
| --- | --- |
| **Missing** | Playlist tracks with no file on disk (shows the closest match, if any) |
| **Matched** | Tracks already in your folder, with a confidence score |
| **Extra files** | Files in the folder that aren't in the playlist |

Matching is fuzzy, so `Artist - Title`, ID3 tags and messy YouTube titles like
`Song Title (Official Video) [HD]` all line up correctly.

Then either:

- **⬇ Add missing tracks to queue** — sends just the missing ones to the
  download queue, or
- **⤓ Export list (.txt)** — saves the missing list for later.

This is the fastest way to fill the gaps in a big library without re-downloading
everything.

---

## 9. Bonus: huge playlists (1,000+ songs)

Downloading 1,500 songs is a long job; these settings make it reliable.

> **Spotify playlists over 100 songs:** add your free Spotify Client ID/Secret in
> **Settings** before importing. Spotify's public page only lists the first 100
> tracks, so a 1,500-song playlist would silently import just 100 songs without
> credentials. YouTube playlists have no such limit.

**Before you start — use Test mode.** In **Settings → Speed & stability**, tick
**Test mode — resolve tracks, download nothing**. Import your playlist and press
Start. The app resolves every track without downloading, so you can confirm the
whole list looks right first. Untick it when you're happy.

**While downloading:**

| Setting | Recommended | Why |
| --- | --- | --- |
| **Parallel downloads** | `3`–`4` | The sweet spot. Higher just triggers throttling. |
| **Attempts per track** | `3`–`5` | Retries transient failures automatically. |
| **Retry backoff** | `5`–`10` s | Waits between attempts so YouTube stops complaining. |
| **Auto-retry failures once after a run** | on | Cleans up stragglers at the end. |
| **Never re-download finished tracks** | on | A big download won't redo work if interrupted. |

If it stops overnight, just open the app and press **▶ Start** again — it only
picks up what's left.

---

## 10. Settings reference

### Where files go

| Setting | Notes |
| --- | --- |
| **Download folder** | Base folder where finished files are written. **Open folder** reveals it. |
| **Put a multi-track playlist in its own folder** | On by default. A playlist of many tracks gets a sub-folder named after it; a single track is written flat under its own name. |

### Music

| Setting | Notes |
| --- | --- |
| **Format** | `mp3`, `m4a`/AAC, `opus`, `flac` (lossless), `wav`, or `original`. |
| **Quality** | `320`, `256`, `192`, `128 kbps`, or `best available`. |
| **Filename pattern** | How files are named. `%(title)s` etc. from yt-dlp syntax. |
| **Write tags** | Artist / album / title written into the file. |
| **Embed cover art** | Album art inside the file. |
| **Save cover.jpg beside tracks** | Also drops a `cover.jpg` next to the audio. |
| **Rename to "Artist - Title"** | Overrides the filename pattern with a tidy name. |

### Video

| Setting | Notes |
| --- | --- |
| **Container** | `mp4` (most compatible), `mkv`, `webm`. |
| **Max quality** | `best`, `2160p` (4K), `1440p`, `1080p`, `720p`, `480p`. |
| **Filename pattern** | As above, for video files. |

### Speed & stability

| Setting | Notes |
| --- | --- |
| **Parallel downloads** | How many tracks at once. 3–4 recommended. |
| **Parallel chunks per file** | Splits a single file into parallel pieces. Leave low. |
| **Speed limit (KB/s)** | `0` = unlimited. |
| **Network retries inside one attempt** | Retries inside a single attempt. |
| **Attempts per track** | Total tries before a track is marked failed. |
| **Retry backoff (seconds)** | Wait between attempts. |
| **Socket timeout (s)** | Give up on a stalled connection after this long. |
| **Delay between requests (s)** | Politeness delay; useful if you get throttled. |
| **Never re-download finished tracks** | Skips anything already downloaded, ever. |
| **Skip items whose file already exists** | Skips if the target file is on disk. |
| **Auto-retry failures once after a run** | One automatic cleanup pass. |
| **Test mode** | Resolve tracks but download nothing. Great for big lists. |

### Access & networking

| Setting | Notes |
| --- | --- |
| **Cookies from browser** | For private / age-restricted / members-only content. |
| **Proxy** | Optional, e.g. `http://host:port`. |
| **ffmpeg path** | Only if ffmpeg isn't found automatically. |
| **Spotify Client ID / Secret** | Recommended for long playlists. Free from `developer.spotify.com`. Without them the app reads Spotify's public page, which only lists the **first 100 tracks**. With them you get the full playlist plus accurate album metadata. |
| **Search YouTube for Spotify tracks** | Turns Spotify track names into YouTube downloads. |

Most people never need the **Access & networking** card.

---

## 11. Where your data lives

Everything the app writes lives in one per-user folder:

| Platform | Location |
| --- | --- |
| macOS | `~/Library/Application Support/PlaylistDownloader` |
| Windows | `%APPDATA%\PlaylistDownloader` |
| Linux | `~/.config/PlaylistDownloader` |

It contains your settings (`config.json`), the queue (`queue.db`), the
"already downloaded" list (`download-archive.txt`) and a `cache/` folder.

**Back it up or delete it as a unit.** Deleting it resets the app completely.

---

## 12. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `HTTP Error 403: Forbidden` on YouTube | Install a JS runtime: `brew install deno`. Check the **JS challenge** badge in Settings. |
| Audio conversion fails / files look wrong | ffmpeg isn't installed or isn't found. `brew install ffmpeg`, then check the **ffmpeg** badge. |
| A specific track keeps failing | Turn on **Cookies from browser** in Settings → Access & networking. |
| Compare is very slow on a huge folder | Install `rapidfuzz` (only relevant for a source checkout, not the bundled app). |
| Downloads stall overnight | Normal. Reopen the app and press **▶ Start**; it resumes. |
| App won't open ("unidentified developer") | Right-click the app → **Open** → **Open** once. |
| Everything is stuck | Check the **Activity** tab, and the log at `~/Library/Application Support/PlaylistDownloader/app.log`. |

---

## 13. FAQ

**Does it download from Spotify directly?**
No — Spotify's audio is encrypted. The app reads the Spotify playlist to get the
track list, then finds and downloads each song from YouTube.

**My Spotify playlist only imported 100 songs — why?**
Spotify's public playlist page only exposes the first **100 tracks**, and there is
no way around that anonymously. For longer playlists, add a free Spotify Client ID
and Secret in **Settings** (from `developer.spotify.com`) and the app will page
through the whole list. Without them, anything past track 100 is unreachable.

**Where do the videos/songs come from?**
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Only download content you have the
right to download — for example your own uploads, or content that is licensed
for reuse.

**Can I move my library to another computer?**
Yes. Copy the files, and copy the folder from
[Where your data lives](#11-where-your-data-lives) to keep your queue and
settings.

**Do I have to keep the app open while it downloads?**
Yes — it downloads while running. But it's safe to close: the queue is saved and
resumes where it stopped.

**How do I start over?**
Delete the folder from
[Where your data lives](#11-where-your-data-lives).

**Can I use it on Windows?**
Yes, via `scripts\run.bat`. The native window and the `.dmg` are macOS-only.
