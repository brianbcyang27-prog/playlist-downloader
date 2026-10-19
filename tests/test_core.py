"""Self-check for the matching engine: correctness edge cases + scale.

Run it with:   python -m tests.test_core
No test framework required (keeps the install footprint at two packages).
"""

from __future__ import annotations

import random
import sys
import time

sys.path.insert(0, ".")

from app import matcher  # noqa: E402
from app.matcher import (  # noqa: E402
    FileRecord, _score, _track_key, compare_playlist_to_folder, normalize,
    parse_filename,
)

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not condition else ""))


def rec(name: str, title=None, artist=None, dur=None) -> FileRecord:
    r = FileRecord(path=f"/x/{name}", name=name, title=title, artist=artist,
                   album=None, duration=dur)
    r.finalize()
    return r


def score(title, artist, dur, record) -> float:
    return _score(_track_key({"title": title, "artist": artist}), record, dur)


def main() -> int:
    print("\n=== normalisation ===")
    check("strips brackets", normalize("Track (Official Video)") == "track")
    check("strips feat", "feat" not in normalize("Track feat. Someone"))
    check("keeps letters", normalize("Midnight — City!!!") == "midnight city")
    check("accent folding", normalize("Björk") == "bjork")
    check("ampersand", normalize("Simon & Garfunkel") == "simon garfunkel")
    check("noise words", normalize("The Track (Official Audio) HD") == "track")
    check("empty is safe", normalize("") == "" and normalize("   ") == "")

    print("\n=== filename parsing ===")
    check("dash split", parse_filename("Artist - Title") == ("Artist", "Title"))
    check("track number", parse_filename("07. Artist - Title") == ("Artist", "Title"))
    check("underscore", parse_filename("bonobo_-_kerala") == ("bonobo", "kerala"))
    check("title only", parse_filename("JustATitle")[1] == "JustATitle")

    print("\n=== playlist parsing ===")
    from app.playlist import _entries_from_info, _youtube_name, MusicTrack  # noqa: E402

    # A playlist URL yields an `entries` list.
    playlist_info = {"_type": "playlist", "title": "My List",
                     "entries": [{"id": "a1", "title": "One"},
                                 {"id": "a2", "title": "Two"}]}
    check("playlist entries preserved", len(_entries_from_info(playlist_info)) == 2)
    # A single video URL comes back as the video dict itself (no entries).
    video_info = {"id": "dQw4w9WgXcQ", "title": "A Song", "duration": 213}
    got = _entries_from_info(video_info)
    check("single video becomes one entry", len(got) == 1 and got[0]["id"] == "dQw4w9WgXcQ")
    check("empty info stays empty", _entries_from_info({}) == [])
    check("single video names the playlist",
          _youtube_name([MusicTrack(title="A Song", artist="An Artist")]) == "A Song")
    check("multi track keeps generic name",
          _youtube_name([MusicTrack(title="A"), MusicTrack(title="B")]) == "YouTube Playlist")

    print("\n=== spotify embed parsing ===")
    from app.playlist import (  # noqa: E402
        _embed_entity, _split_artists, _tracks_from_entity,
    )

    check("splits nbsp-separated artists",
          _split_artists("Olivia Rodrigo,\u00a0Chappell Roan") == ["Olivia Rodrigo", "Chappell Roan"])
    check("single artist", _split_artists("Fleetwood Mac") == ["Fleetwood Mac"])
    check("blank subtitle is safe", _split_artists("") == [] and _split_artists(None) == [])

    # Payload shape Spotify serves today (props.pageProps.state.data.entity).
    embed = {"props": {"pageProps": {"state": {"data": {"entity": {
        "type": "playlist", "name": "Road Trip",
        "trackList": [
            {"uri": "spotify:track:t1", "entityType": "track", "title": "Song One",
             "subtitle": "Artist A", "duration": 180000},
            {"uri": "spotify:track:t2", "entityType": "track", "title": "Song Two",
             "subtitle": "Artist B,\u00a0Artist C", "duration": 241500},
            {"uri": "spotify:episode:e1", "entityType": "episode", "title": "An Episode"},
            {"uri": "spotify:track:t3", "entityType": "track", "title": "   "},
        ],
    }}}}}}
    entity = _embed_entity(embed)
    check("entity located in modern payload", isinstance(entity, dict) and entity.get("name") == "Road Trip")
    name, tracks = _tracks_from_entity(entity)
    check("playlist name read", name == "Road Trip")
    check("non-track and blank items skipped", len(tracks) == 2, str(len(tracks)))
    check("titles read", [t.title for t in tracks] == ["Song One", "Song Two"])
    check("artists read", tracks[1].artist == "Artist B, Artist C", tracks[1].artist)
    check("duration converted from ms", tracks[0].duration == 180.0 and tracks[1].duration == 241.5)
    check("positions renumbered after skips", [t.track_number for t in tracks] == [1, 2])
    check("no playlist cover stamped per track", all(t.thumbnail == "" for t in tracks))
    check("source tagged", all(t.source == "spotify" for t in tracks))
    check("missing entity is handled", _embed_entity({"props": {}}) is None)

    print("\n=== spotify api path (stubbed network) ===")
    from app import playlist as _pl  # noqa: E402

    class _Ctx:
        def __init__(self, payload):
            import json as _j
            self._b = _j.dumps(payload).encode()

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _trk(i):
        return {"name": f"Song {i}", "artists": [{"name": "An Artist"}],
                "album": {"name": "An Album", "images": [{"url": "http://img"}]},
                "duration_ms": 1234, "track_number": i + 1}

    real_urlopen = _pl.urllib.request.urlopen

    def _fake(segment_pages, failing=()):
        def opener(req, *a, **k):
            url = getattr(req, "full_url", str(req))
            if "accounts.spotify.com" in url:
                return _Ctx({"access_token": "T"})
            if "fields=name" in url:
                return _Ctx({"name": "Big List"})
            for seg, pages in segment_pages.items():
                if f"/{seg}?" in url:
                    if seg in failing:
                        raise OSError("HTTP 404 Not Found")
                    offset = int(url.split("offset=")[-1])
                    return _Ctx({"items": pages[offset // 100]})
            raise OSError(f"unexpected url: {url}")
        return opener

    pages = [[{"item": _trk(i)} for i in range(100)],
             [{"item": _trk(i)} for i in range(100, 130)]]
    _pl.urllib.request.urlopen = _fake({"items": pages})
    try:
        name, api_tracks = _pl._spotify_api_tracks("cid", "sec", "pid")
    finally:
        _pl.urllib.request.urlopen = real_urlopen
    check("api pages through the whole list", len(api_tracks) == 130, str(len(api_tracks)))
    check("api reads the playlist name", name == "Big List", name)
    check("api reads track fields",
          api_tracks[0].title == "Song 0" and api_tracks[0].artist == "An Artist"
          and api_tracks[0].album == "An Album")
    check("api converts duration to seconds", api_tracks[0].duration == 1.234)
    check("api keeps album art", api_tracks[0].thumbnail == "http://img")

    # Older accounts answer /tracks, not /items — the app must fall back.
    _pl.urllib.request.urlopen = _fake(
        {"items": [[]], "tracks": [[{"track": _trk(0)}, {"track": {"is_local": True}}]]},
        failing=("items",),
    )
    try:
        _name, legacy = _pl._spotify_api_tracks("cid", "sec", "pid")
    finally:
        _pl.urllib.request.urlopen = real_urlopen
    check("api falls back to /tracks", [t.title for t in legacy] == ["Song 0"], str(legacy))

    print("\n=== output naming (playlist folders) ===")
    import os as _os
    import shutil as _shutil
    import tempfile as _tempfile
    from pathlib import Path as _Path

    from app.config import Config  # noqa: E402
    from app.db import QueueDB  # noqa: E402
    from app.downloader import DownloadManager  # noqa: E402
    from app.events import EventHub  # noqa: E402

    home = _Path(_tempfile.mkdtemp(prefix="pd-dest-"))
    prev_home = _os.environ.get("PLAYLIST_DOWNLOADER_HOME")
    _os.environ["PLAYLIST_DOWNLOADER_HOME"] = str(home)
    try:
        cfg = Config(home / "config.json")
        cfg.update({"download_dir": str(home / "out")})
        db = QueueDB(home / "queue.db")
        dm = DownloadManager(cfg, db, EventHub())

        many = db.add_playlist("Rock Classics", "spotify", "u1")
        db.add_items(many, [{"url": f"ytsearch1:s{i}", "title": f"S{i}", "artist": "A"}
                            for i in range(3)])
        solo = db.add_playlist("One Song", "youtube", "u2")
        db.add_items(solo, [{"url": "https://youtu.be/x", "title": "Solo", "artist": "B"}])

        check("multi-track playlist gets a folder named after it",
              dm._playlist_folder({"playlist_id": many}) == "Rock Classics")
        check("single-track playlist stays flat",
              dm._playlist_folder({"playlist_id": solo}) == "")

        tmpl_many = dm._build_opts(db.get_items(many)[0])["outtmpl"]["default"]
        check("multi-track outtmpl lands inside the playlist folder",
              tmpl_many.startswith("Rock Classics/"), tmpl_many)
        tmpl_solo = dm._build_opts(db.get_items(solo)[0])["outtmpl"]["default"]
        check("single-track outtmpl has no sub-folder",
              "/" not in tmpl_solo and "\\" not in tmpl_solo, tmpl_solo)

        cfg.update({"make_playlist_subfolder": False})
        dm._playlist_cache.clear()
        check("turning the setting off writes flat again",
              dm._playlist_folder({"playlist_id": many}) == "")
        check("flat mode outtmpl has no sub-folder",
              "/" not in dm._build_opts(db.get_items(many)[0])["outtmpl"]["default"])

        db.close()
    finally:
        if prev_home is None:
            _os.environ.pop("PLAYLIST_DOWNLOADER_HOME", None)
        else:
            _os.environ["PLAYLIST_DOWNLOADER_HOME"] = prev_home
        _shutil.rmtree(home, ignore_errors=True)

    print("\n=== scoring ===")
    exact = score("Get Lucky", "Daft Punk", 369, rec("x", title="Get Lucky", artist="Daft Punk", dur=369))
    check("exact match scores high", exact > 0.95, f"got {exact}")
    noisy = score("Get Lucky", "Daft Punk", 369,
                  rec("x", title="Get Lucky (feat. Pharrell Williams) [Official Video]", artist="Daft Punk", dur=370))
    check("noisy title still matches", noisy > 0.8, f"got {noisy}")
    wrong = score("Get Lucky", "Daft Punk", 369, rec("x", title="Roads", artist="Portishead", dur=300))
    check("different song scores low", wrong < 0.5, f"got {wrong}")

    # Generic words must not create a match when the artists clearly differ.
    generic = score("Hold On", "Artist One", 200, rec("x", title="Hold On", artist="Totally Different Band", dur=200))
    check("conflicting artist is not a match", generic < 0.72, f"got {generic}")
    # ...but a correct artist with extra "feat." text still matches.
    feats = score("Get Lucky", "Daft Punk", 369,
                  rec("x", title="Get Lucky", artist="Daft Punk feat. Pharrell Williams", dur=369))
    check("artist with feat. still matches", feats > 0.9, f"got {feats}")

    # A same-named album upload must not beat the real single.
    album = score("Awake", "Tycho", 284, rec("x", title="Tycho - Awake Full Album", artist="Tycho", dur=2185))
    single = score("Awake", "Tycho", 284, rec("x", title="Tycho - Awake", artist="Tycho", dur=284))
    check("single beats full album", single > album, f"single={single} album={album}")

    print("\n=== end-to-end comparison ===")
    tracks = [
        {"title": "Karma Police", "artist": "Radiohead", "duration": 261},
        {"title": "Kerala", "artist": "Bonobo", "duration": 253},
        {"title": "Get Lucky", "artist": "Daft Punk", "duration": 369},
    ]
    import os
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    touch = lambda n: open(os.path.join(tmp, n), "w").close()  # noqa: E731
    touch("03 - karma police (Official Video).mp3")
    touch("bonobo_-_kerala.mp3")
    touch("Nonexistent Track.mp3")
    res = compare_playlist_to_folder(tracks, tmp, read_tags=False)
    check("finds 2 of 3", res.counts["matched"] == 2, str(res.counts))
    check("flags 1 missing", res.counts["missing"] == 1, str(res.counts))
    check("flags 1 extra", res.counts["extra"] == 1, str(res.counts))
    check("missing is the right one", res.missing[0]["title"] == "Get Lucky")
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== scale: 1500 tracks vs 3000 files ===")
    big = tempfile.mkdtemp()
    words = ["love", "night", "dream", "fire", "rain", "ocean", "city", "light",
             "shadow", "heart", "run", "gold", "silver", "moon", "star", "echo"]
    artists = [f"Artist {i}" for i in range(400)]
    files = []
    for i in range(3000):
        a = random.choice(artists)
        t = " ".join(random.sample(words, 3))
        files.append(f"{a} - {t}.mp3")
    for f in files:
        open(os.path.join(big, f), "w").close()
    tracks_big = []
    for f in files[:1500]:
        stem = f[:-4]
        a, _, t = stem.partition(" - ")
        tracks_big.append({"title": t, "artist": a})
    random.shuffle(tracks_big)
    # Add 200 tracks that are genuinely absent, using a disjoint vocabulary so
    # this actually tests detection rather than accidental word collisions.
    absent_words = ["zephyr", "quartz", "nimbus", "vellum", "obsidian", "halcyon",
                    "pallas", "cinder", "lucent", "morrow", "solace", "verity"]
    for i in range(200):
        tracks_big.append({
            "title": " ".join(random.sample(absent_words, 3)),
            "artist": f"Absent {i}",
        })

    t0 = time.time()
    res = compare_playlist_to_folder(tracks_big, big, read_tags=False)
    elapsed = time.time() - t0
    print(f"  scanned {res.counts['folder']} files, matched {res.counts['playlist']} tracks "
          f"in {elapsed:.2f}s")
    check("completes under 20s", elapsed < 20, f"{elapsed:.2f}s")
    check("finds nearly all real tracks", res.counts["matched"] >= 1480, str(res.counts))
    check("detects the absent tracks", res.counts["missing"] >= 195, str(res.counts))
    check("does not over-report extras", res.counts["extra"] <= 1600, str(res.counts))
    shutil.rmtree(big, ignore_errors=True)

    print(f"\n{'=' * 52}")
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  failures:")
        for f in FAIL:
            print(f"    - {f}")
    print(f"{'=' * 52}\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
