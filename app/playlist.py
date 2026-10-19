"""Playlist resolution: turn a URL or file into a list of tracks.

Supported sources:

* YouTube / YouTube Music  — read the track list directly from the playlist
* Spotify                 — via oEmbed scrape (no key) or Client Credentials
                            (key = accurate album metadata for every track)
* YouTube search          — "ytsearch:..." queries, or per-track resolution
* Plain text / CSV file   — "Artist - Title" per line

The result is a list[MusicTrack]; entries that have no direct URL yet get
queued for YouTube search resolution so yt-dlp can still download them.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict

import yt_dlp


@dataclass
class MusicTrack:
    title: str
    artist: str = ""
    album: str = ""
    duration: float | None = None
    url: str = ""                       # direct playable URL (empty = resolve)
    track_number: int | None = None
    thumbnail: str = ""
    source: str = "unknown"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def search_query(self) -> str:
        parts = [p for p in (self.artist, self.title) if p]
        return " - ".join(parts) if len(parts) == 2 else (parts[0] if parts else "")

    @property
    def display(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title


def classify_url(text: str) -> str:
    """Return the source kind: youtube | spotify | youtube-search | unknown."""
    text = text.strip()
    low = text.lower()
    if low.startswith(("ytsearch", "ytsearch1:", "ytsearch5:")):
        return "youtube-search"
    if "youtube.com" in low or "youtu.be" in low or "music.youtube.com" in low:
        return "youtube"
    if "open.spotify.com" in low or "spotify:" in low:
        return "spotify"
    return "unknown"


_YOUTUBE_FLAT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
    "playlist_items": "1:10000",
}


def _cookies_opts(cfg) -> dict:
    """Network/environment options for playlist reading (shared with downloads)."""
    from .config import network_opts
    return network_opts(cfg)


def _entries_from_info(info: dict) -> list[dict]:
    """Normalise yt-dlp output into a list of playable entry dicts.

    A playlist comes back with an ``entries`` list, but a **single video URL**
    comes back as the video dict itself — with an ``id`` but no ``entries``.
    Both cases must yield a list, otherwise a one-video link looks "empty".
    """
    entries = info.get("entries") or []
    if not entries and info.get("id"):
        return [info]
    return entries


def from_youtube(url: str, cfg, progress=None, limit: int = 100000) -> list[MusicTrack]:
    """Extract the flat (fast) track list from a YouTube playlist."""
    opts = dict(_YOUTUBE_FLAT_OPTS)
    opts.update(_cookies_opts(cfg))
    opts["playlist_items"] = f"1:{min(limit, 100000)}"

    tracks: list[MusicTrack] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            return tracks

        entries = _entries_from_info(info)
        for i, entry in enumerate(entries, start=1):
            if entry is None:
                continue
            title = entry.get("title") or entry.get("id") or ""
            artist = _youtube_artist(entry)
            tracks.append(
                MusicTrack(
                    title=title,
                    artist=artist,
                    album=info.get("title") or "",
                    duration=entry.get("duration"),
                    url=f"https://www.youtube.com/watch?v={entry.get('id')}" if entry.get("id") else (entry.get("url") or ""),
                    track_number=i,
                    thumbnail=entry.get("thumbnail") or "",
                    source="youtube",
                    extra={"channel": entry.get("channel") or entry.get("uploader") or "", "video_id": entry.get("id") or ""},
                )
            )
            if progress:
                progress(i)
    return tracks


def _youtube_artist(entry: dict) -> str:
    """Best-effort artist from YouTube metadata (uploader/channel)."""
    return entry.get("artist") or entry.get("creator") or entry.get("uploader") or entry.get("channel") or ""


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------

_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_API = "https://api.spotify.com/v1"


def _spotify_spotify_id(url: str) -> str:
    m = re.search(r"playlist[/:]([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)
    return ""


def _spotify_embed(playlist_id: str) -> dict | None:
    """Scrape the public oEmbed/embed JSON — no credentials required."""
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    req = urllib.request.Request(embed_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception:
        return None
    # The embed page embeds a JSON payload.
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_embed_tracks(data: dict) -> tuple[str, list[MusicTrack]]:
    """Walk the __NEXT_DATA__ blob looking for track items."""
    tracks: list[MusicTrack] = []
    playlist_name = "Spotify Playlist"

    def walk(node):
        nonlocal playlist_name
        if isinstance(node, dict):
            if node.get("__typename") == "Playlist":
                playlist_name = node.get("name") or playlist_name
            if node.get("__typename") == "Track":
                track = node.get("track") if isinstance(node.get("track"), dict) else node
                name = track.get("name")
                if name:
                    artists = [
                        a.get("name", "")
                        for a in (track.get("artists") or [])
                        if isinstance(a, dict)
                    ]
                    album = ""
                    al = track.get("album")
                    if isinstance(al, dict) and al.get("name"):
                        album = al["name"]
                    tracks.append(
                        MusicTrack(
                            title=name,
                            artist=", ".join(artists),
                            album=album,
                            duration=track.get("duration_ms") / 1000 if track.get("duration_ms") else None,
                            track_number=track.get("track_number"),
                            thumbnail=(
                                (al.get("images") or [{}])[0].get("url", "") if isinstance(al, dict) else ""
                            ),
                            source="spotify",
                        )
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return playlist_name, tracks


def _spotify_api_tracks(client_id: str, client_secret: str, playlist_id: str) -> tuple[str, list[MusicTrack]]:
    """Authorized fetch — gives track numbers & full album metadata."""
    import base64

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        _SPOTIFY_TOKEN_URL,
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.loads(resp.read().decode())["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    tracks: list[MusicTrack] = []
    name = "Spotify Playlist"

    with urllib.request.urlopen(
        urllib.request.Request(f"{_SPOTIFY_API}/playlists/{playlist_id}?fields=name", headers=headers), timeout=30
    ) as resp:
        name = json.loads(resp.read().decode()).get("name", name)

    offset = 0
    while True:
        url = f"{_SPOTIFY_API}/playlists/{playlist_id}/tracks?limit=100&offset={offset}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        for entry in payload.get("items", []):
            tr = entry.get("track")
            if not tr or tr.get("is_local"):
                continue
            tracks.append(
                MusicTrack(
                    title=tr.get("name", ""),
                    artist=", ".join(a["name"] for a in (tr.get("artists") or [])),
                    album=(tr.get("album") or {}).get("name", ""),
                    duration=tr.get("duration_ms") / 1000 if tr.get("duration_ms") else None,
                    track_number=tr.get("track_number"),
                    thumbnail=((tr.get("album") or {}).get("images") or [{}])[0].get("url", ""),
                    source="spotify",
                )
            )
        if len(payload.get("items", [])) < 100:
            break
        offset += 100
    return name, tracks


def from_spotify(url: str, cfg) -> tuple[str, list[MusicTrack]]:
    playlist_id = _spotify_spotify_id(url)
    if not playlist_id:
        raise ValueError("Could not find a Spotify playlist id in that URL.")

    cid = cfg.get("spotify_client_id") or ""
    secret = cfg.get("spotify_client_secret") or ""
    if cid and secret:
        try:
            return _spotify_api_tracks(cid, secret, playlist_id)
        except Exception:
            pass  # fall back to embed scrape

    data = _spotify_embed(playlist_id)
    if not data:
        raise ValueError(
            "Could not read the Spotify playlist. Add Spotify API credentials "
            "in Settings (free) for reliable access, or export to a text file."
        )
    name, tracks = _extract_embed_tracks(data)
    if not tracks:
        raise ValueError("Spotify playlist returned no tracks.")
    return name, tracks


# ---------------------------------------------------------------------------
# Text / CSV files
# ---------------------------------------------------------------------------

def from_file(path: str, cfg) -> list[MusicTrack]:
    """Parse 'Artist - Title' lines, or CSV with header title/artist/album."""
    p = __import__("pathlib").Path(path)
    raw = p.read_text("utf-8", errors="replace")
    tracks: list[MusicTrack] = []
    seen: set[str] = set()

    if p.suffix.lower() == ".csv":
        rows = csv.DictReader(raw.splitlines())
        for row in rows:
            title = (row.get("title") or row.get("Title") or "").strip()
            artist = (row.get("artist") or row.get("Artist") or "").strip()
            album = (row.get("album") or row.get("Album") or "").strip()
            url = (row.get("url") or row.get("URL") or "").strip()
            if not title and not artist:
                continue
            key = f"{artist}|{title}"
            if key in seen:
                continue
            seen.add(key)
            tracks.append(MusicTrack(title=title, artist=artist, album=album, url=url, source="file"))
        return tracks

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        # Strip line numbers like "12. Artist - Title"
        line = re.sub(r"^\d+[.)\s]+", "", line)
        parts = re.split(r"\s+-\s+", line, maxsplit=1)
        title, artist = "", ""
        if len(parts) == 2:
            title, artist = parts[1].strip(), parts[0].strip()
        else:
            title = line
        key = f"{artist}|{title}"
        if key in seen:
            continue
        seen.add(key)
        tracks.append(MusicTrack(title=title, artist=artist, source="file"))
    return tracks


# ---------------------------------------------------------------------------
# Resolution to playable URLs
# ---------------------------------------------------------------------------

def resolve_to_youtube(track: MusicTrack, cfg, index: int = 0, total: int = 0) -> MusicTrack:
    """Find the best YouTube match for a Spotify/text track using ytsearch1.

    Returns a new MusicTrack with a direct yt video URL; on failure the
    original track is returned unchanged (title kept as the query so the
    downloader can still attempt it)."""
    query = track.search_query
    if not query or not cfg.get("resolve_missing_to_youtube", True):
        return track
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "noplaylist": True,
    }
    opts.update(_cookies_opts(cfg))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            entries = (info or {}).get("entries") or []
            if entries and entries[0]:
                e = entries[0]
                resolved = MusicTrack(
                    title=track.title or e.get("title", ""),
                    artist=track.artist or _youtube_artist(e),
                    album=track.album,
                    duration=e.get("duration") or track.duration,
                    url=f"https://www.youtube.com/watch?v={e.get('id')}",
                    track_number=track.track_number,
                    thumbnail=e.get("thumbnail") or track.thumbnail,
                    source=track.source,
                    extra={**track.extra, "resolved_from": query},
                )
                return resolved
    except Exception:
        pass
    # No match: keep the query so the downloader can try it directly.
    return MusicTrack(
        title=track.title, artist=track.artist, album=track.album,
        duration=track.duration, url="ytsearch1:" + query,
        track_number=track.track_number, thumbnail=track.thumbnail,
        source=track.source, extra={**track.extra, "unresolved": True},
    )


def resolve_batch(tracks: list[MusicTrack], cfg, progress=None) -> list[MusicTrack]:
    """Resolve all tracks lacking a URL, sequentially (respects providers)."""
    out: list[MusicTrack] = []
    missing = [(i, t) for i, t in enumerate(tracks) if not t.url]
    resolved_map: dict[int, MusicTrack] = {}
    for n, (i, t) in enumerate(missing, 1):
        resolved_map[i] = resolve_to_youtube(t, cfg, n, len(missing))
        if progress:
            progress(n, len(missing), t.display)
    for i, t in enumerate(tracks):
        out.append(resolved_map.get(i, t))
    return out


def _youtube_name(tracks: list[MusicTrack]) -> str:
    """A single video keeps its own title; real playlists get a generic name."""
    if len(tracks) == 1 and tracks[0].title:
        return tracks[0].title
    return "YouTube Playlist"


def fetch_playlist(source: str, location: str, cfg, progress=None) -> tuple[str, str, list[MusicTrack]]:
    """Dispatch by source. Returns (name, source, tracks)."""
    source = source.lower()
    if source in ("youtube", "youtube-search"):
        tracks = from_youtube(location, cfg, progress=None)
        return _youtube_name(tracks), "youtube", tracks
    if source == "spotify":
        name, tracks = from_spotify(location, cfg)
        return name, "spotify", tracks
    if source in ("file", "text"):
        tracks = from_file(location, cfg)
        name = location.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return name, "file", tracks
    # Auto-detect
    kind = classify_url(location)
    if kind == "youtube":
        tracks = from_youtube(location, cfg)
        return _youtube_name(tracks), "youtube", tracks
    if kind == "spotify":
        name, tracks = from_spotify(location, cfg)
        return name, "spotify", tracks
    if kind == "unknown" and ("\n" not in location) and __import__("pathlib").Path(
        location
    ).exists():
        tracks = from_file(location, cfg)
        name = location.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return name, "file", tracks
    if kind == "youtube-search":
        return "Search", "youtube-search", [
            MusicTrack(title="YouTube search", url=location, source="youtube-search")
        ]
    raise ValueError("Could not detect the playlist source. Paste a YouTube/Spotify link, a text file path, or 'ytsearch:query'.")