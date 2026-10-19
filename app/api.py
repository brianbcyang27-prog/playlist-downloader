"""HTTP API + static file server (standard library only, no web framework).

Endpoints
---------
GET    /                              web UI
GET    /api/state                     settings, tool health, queue stats
GET    /api/events                    Server-Sent Events progress stream
POST   /api/settings                  update settings
GET    /api/playlists                 list playlists
GET    /api/playlists/<id>/items      items in a playlist
DELETE /api/playlists/<id>            remove a playlist and its queue
POST   /api/playlist/import           import a URL / file (background job)
POST   /api/download/start|pause|resume|stop
POST   /api/items/<id>/retry          re-queue one item
POST   /api/items/retry-failed        re-queue all failures
GET    /api/browse                    browse folders server-side
POST   /api/compare                   compare a folder to a playlist (bg job)
GET    /api/job/<id>                  fetch a finished job's result
POST   /api/compare/import-missing    queue the missing tracks
POST   /api/shutdown                  quit the app
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from . import APP_NAME, __version__, paths, playlist as pl
from .config import Config, DEFAULTS, tool_status
from .db import QueueDB
from .downloader import DownloadManager
from .events import EventHub, get_hub
from .matcher import compare_playlist_to_folder

MAX_BODY = 4 * 1024 * 1024


class JobStore:
    """In-memory results for background jobs (import / compare)."""

    def __init__(self, ttl: float = 3600) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._ttl = ttl

    def create(self, kind: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id, "kind": kind, "status": "running",
                "progress": 0, "message": "", "result": None,
                "error": None, "started": time.time(),
            }
        self._gc()
        return job_id

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def finish(self, job_id: str, result: Any) -> None:
        self.update(job_id, status="done", result=result, progress=100)

    def fail(self, job_id: str, error: str) -> None:
        self.update(job_id, status="error", error=error)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _gc(self) -> None:
        cutoff = time.time() - self._ttl
        with self._lock:
            self._jobs = {
                k: v for k, v in self._jobs.items() if v["started"] > cutoff
            }


class AppContext:
    """Shared singletons wired up by server.py."""

    def __init__(self) -> None:
        self.cfg = Config()
        self.db = QueueDB()
        self.hub: EventHub = get_hub()
        self.manager = DownloadManager(self.cfg, self.db, self.hub)
        self.jobs = JobStore()
        self.shutdown = threading.Event()


CTX: AppContext | None = None


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

def _run_import(ctx: AppContext, job_id: str, source: str, location: str,
                mode: str = "audio") -> None:
    hub = ctx.hub
    try:
        hub.emit("import_progress", {"job": job_id, "stage": "reading",
                                     "message": f"Reading playlist from {source}…"})
        name, kind, tracks = pl.fetch_playlist(source, location, ctx.cfg)

        if not tracks:
            raise ValueError("That playlist appears to be empty.")

        # Tracks without a URL get a YouTube search query so the worker pool can
        # resolve them in parallel at download time.
        items = []
        for t in tracks:
            url = t.url
            if not url and ctx.cfg.get("resolve_missing_to_youtube", True):
                q = t.search_query or t.title
                url = f"ytsearch1:{q}"
            if not url:
                continue
            items.append({
                "url": url,
                "source": kind,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "duration": t.duration,
                "thumbnail": t.thumbnail,
                "track_number": t.track_number,
                "mode": mode,
            })

        if not items:
            raise ValueError("Nothing importable was found in that playlist.")

        playlist_id = ctx.db.add_playlist(name, kind, location)
        ctx.db.add_items(playlist_id, items)
        total = ctx.db.count_items(playlist_id)

        hub.emit("import_progress", {
            "job": job_id, "stage": "done",
            "message": f"Imported {total} tracks from “{name}”.",
            "count": total,
        })
        ctx.jobs.finish(job_id, {
            "playlist_id": playlist_id, "name": name, "source": kind,
            "count": total,
        })
        hub.emit("playlists_changed", {})
    except Exception as exc:
        ctx.jobs.fail(job_id, f"{type(exc).__name__}: {exc}")
        hub.emit("import_progress", {"job": job_id, "stage": "error",
                                     "message": f"{type(exc).__name__}: {exc}"})


def _run_compare(ctx: AppContext, job_id: str, tracks: list[dict], folder: str,
                 threshold: float, recursive: bool, read_tags: bool,
                 label: str) -> None:
    hub = ctx.hub
    try:
        hub.emit("compare_progress", {"job": job_id, "stage": "scanning",
                                      "message": f"Scanning {folder}…"})
        result = compare_playlist_to_folder(
            tracks, folder, threshold=threshold,
            recursive=recursive, read_tags=read_tags,
        )
        hub.emit("compare_progress", {"job": job_id, "stage": "done",
                                      "message": "Comparison complete."})
        ctx.jobs.finish(job_id, {
            "label": label,
            "folder": folder,
            "threshold": threshold,
            "counts": result.counts,
            "matched": result.matched,
            "missing": result.missing,
            "extra": result.extra,
        })
    except Exception as exc:
        ctx.jobs.fail(job_id, f"{type(exc).__name__}: {exc}")
        hub.emit("compare_progress", {"job": job_id, "stage": "error",
                                      "message": f"{type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = f"PlaylistDownloader/{__version__}"
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):  # keep the console readable
        if "/api/events" in (self.path or ""):
            return
        ctx = CTX
        if ctx is not None:
            ctx.hub.emit("log", {"level": "http", "message": fmt % args})

    def _ctx(self) -> AppContext:
        assert CTX is not None
        return CTX

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("Request body too large.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Invalid JSON body.")

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        try:
            self._route("GET")
        except Exception as exc:
            self._crash(exc)

    def do_POST(self):
        try:
            self._route("POST")
        except Exception as exc:
            self._crash(exc)

    def do_DELETE(self):
        try:
            self._route("DELETE")
        except Exception as exc:
            self._crash(exc)

    def _crash(self, exc: Exception) -> None:
        traceback.print_exc()
        try:
            self._error(f"{type(exc).__name__}: {exc}", 500)
        except Exception:
            pass

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if method == "GET":
            if path == "/":
                return self._serve_static("index.html")
            if path == "/api/state":
                return self._api_state()
            if path == "/api/events":
                return self._api_events()
            if path == "/api/playlists":
                return self._json({"ok": True, "playlists": self._ctx().db.list_playlists()})
            if path.startswith("/api/playlists/") and path.endswith("/items"):
                pid = int(path.split("/")[3])
                items = self._ctx().db.get_items(pid, limit=100000)
                return self._json({"ok": True, "items": items})
            if path.startswith("/api/job/"):
                job = self._ctx().jobs.get(path.split("/")[3])
                if not job:
                    return self._error("Unknown job.", 404)
                return self._json({"ok": True, "job": job})
            if path == "/api/browse":
                return self._api_browse(query.get("path", [""])[0])
            if path == "/api/ping":
                return self._json({"ok": True, "version": __version__})
            # static assets
            return self._serve_static(path.lstrip("/"))

        if method == "POST":
            if path == "/api/settings":
                return self._api_settings()
            if path == "/api/playlist/import":
                return self._api_import()
            if path == "/api/download/start":
                return self._api_download_start()
            if path == "/api/download/pause":
                return self._json({"ok": True, **self._ctx().manager.pause()})
            if path == "/api/download/resume":
                return self._json({"ok": True, **self._ctx().manager.resume()})
            if path == "/api/download/stop":
                return self._json({"ok": True, **self._ctx().manager.stop()})
            if path == "/api/items/retry-failed":
                body = self._read_json()
                n = self._ctx().db.retry_failed(body.get("playlist_id"))
                return self._json({"ok": True, "requeued": n})
            if path.startswith("/api/items/") and path.endswith("/retry"):
                iid = int(path.split("/")[3])
                if not self._ctx().db.get_item(iid):
                    return self._error(f"No such item: {iid}", 404)
                self._ctx().db.mark_pending(iid)
                return self._json({"ok": True, "item_id": iid})
            if path == "/api/compare":
                return self._api_compare()
            if path == "/api/compare/import-missing":
                return self._api_import_missing()
            if path == "/api/reveal":
                return self._api_reveal()
            if path == "/api/shutdown":
                threading.Thread(target=self._shutdown_soon, daemon=True).start()
                return self._json({"ok": True})

        if method == "DELETE":
            if path.startswith("/api/playlists/"):
                pid = int(path.split("/")[3])
                self._ctx().db.delete_playlist(pid)
                self._ctx().hub.emit("playlists_changed", {})
                return self._json({"ok": True})
            if path.startswith("/api/items/"):
                iid = int(path.split("/")[3])
                self._ctx().db.update_item(iid, status="skipped")
                return self._json({"ok": True})

        self._error("Not found.", 404)

    # -- static files ------------------------------------------------------
    def _serve_static(self, rel: str) -> None:
        root = paths.web_dir().resolve()
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            return self._error("Not found.", 404)
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # -- API: state --------------------------------------------------------
    def _api_state(self) -> None:
        ctx = self._ctx()
        self._json({
            "ok": True,
            "version": __version__,
            "app_name": APP_NAME,
            "settings": ctx.cfg.as_dict(),
            "defaults": DEFAULTS,
            "tools": tool_status(ctx.cfg),
            "stats": ctx.db.stats(),
            "run": ctx.manager.status(),
            "download_dir": str(ctx.cfg.download_dir()),
            "data_dir": str(paths.data_dir()),
            "platform": __import__("sys").platform,
        })

    def _api_settings(self) -> None:
        ctx = self._ctx()
        changes = self._read_json()
        updated = ctx.cfg.update(changes)
        ctx.hub.emit("settings_changed", {"settings": updated})
        self._json({"ok": True, "settings": updated,
                    "tools": tool_status(ctx.cfg)})

    # -- API: SSE ----------------------------------------------------------
    def _api_events(self) -> None:
        ctx = self._ctx()
        types = frozenset({
            "item_progress", "item_started", "item_done", "item_failed",
            "item_stage", "item_retrying", "item_resolved",
            "run_started", "run_finished", "run_paused",
            "run_resumed", "run_stopping", "log", "playlists_changed",
            "import_progress", "compare_progress", "settings_changed",
            "queue_extended",
        })
        sub = ctx.hub.subscribe(types)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()

            last_ping = time.time()
            while not ctx.shutdown.is_set():
                payload = ctx.hub.pump(sub, timeout=5.0)
                if payload is None:
                    if time.time() - last_ping >= 15:
                        last_ping = time.time()
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    continue
                self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass
        finally:
            ctx.hub.unsubscribe(sub)

    # -- API: import -------------------------------------------------------
    def _api_import(self) -> None:
        ctx = self._ctx()
        body = self._read_json()
        source = (body.get("source") or "auto").lower()
        location = (body.get("location") or "").strip()
        mode = body.get("mode") or ctx.cfg.get("default_mode", "audio")
        if not location:
            return self._error("Paste a link or a file path first.")
        if not tool_status(ctx.cfg)["ytdlp_ok"]:
            return self._error("yt-dlp is not available. Install it, then reload.", 503)

        job_id = ctx.jobs.create("import")
        threading.Thread(
            target=_run_import, args=(ctx, job_id, source, location, mode),
            daemon=True, name="import",
        ).start()
        self._json({"ok": True, "job": job_id})

    # -- API: download controls -------------------------------------------
    def _api_download_start(self) -> None:
        ctx = self._ctx()
        body = self._read_json()
        if not tool_status(ctx.cfg)["ffmpeg_ok"] and ctx.cfg.get("audio_format") != "original":
            ctx.hub.emit("log", {
                "level": "warning",
                "message": "ffmpeg was not found. Audio conversion and cover art need it.",
            })
        result = ctx.manager.start(
            playlist_id=body.get("playlist_id"),
            retry_failed=bool(body.get("retry_failed")),
        )
        if not result.get("ok"):
            return self._error(result.get("error", "Could not start."), 409)
        self._json({"ok": True, **result})

    # -- API: folder browse -----------------------------------------------
    def _api_browse(self, raw_path: str) -> None:
        target = Path(raw_path).expanduser() if raw_path else Path.home()
        try:
            target = target.resolve()
        except OSError:
            return self._error("Invalid path.")
        if not target.is_dir():
            return self._error("Not a directory.")
        entries = []
        try:
            for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                if child.name.startswith("."):
                    continue
                if child.is_dir():
                    entries.append({"name": child.name, "path": str(child), "type": "dir"})
        except PermissionError:
            return self._error("Permission denied.")
        self._json({
            "ok": True,
            "path": str(target),
            "parent": str(target.parent),
            "entries": entries,
            "home": str(Path.home()),
        })

    # -- API: compare ------------------------------------------------------
    def _api_compare(self) -> None:
        ctx = self._ctx()
        body = self._read_json()
        folder = (body.get("folder") or "").strip()
        if not folder:
            return self._error("Choose the folder you want to check.")
        folder_path = Path(folder).expanduser()
        if not folder_path.is_dir():
            return self._error(f"Folder not found: {folder}")

        pid = body.get("playlist_id")
        tracks: list[dict] = []
        label = body.get("label") or ""
        if pid:
            playlist = ctx.db.get_playlist(int(pid))
            if not playlist:
                return self._error("That playlist no longer exists.", 404)
            tracks = ctx.db.all_items(int(pid))
            label = label or playlist.get("name") or f"Playlist {pid}"
        else:
            tracks = body.get("tracks") or []
            label = label or "Custom list"
        if not tracks:
            return self._error("There is nothing to compare against.")

        threshold = float(body.get("threshold") or 0.72)
        recursive = bool(body.get("recursive", True))
        read_tags = bool(body.get("read_tags", True))

        job_id = ctx.jobs.create("compare")
        threading.Thread(
            target=_run_compare,
            args=(ctx, job_id, tracks, str(folder_path), threshold, recursive,
                  read_tags, label),
            daemon=True, name="compare",
        ).start()
        self._json({"ok": True, "job": job_id})

    def _api_import_missing(self) -> None:
        """Turn the 'missing' list from a comparison into a downloadable playlist."""
        ctx = self._ctx()
        body = self._read_json()
        items = body.get("items") or []
        name = body.get("name") or "Missing tracks"
        if not items:
            return self._error("No missing tracks were supplied.")

        prepared = []
        for it in items:
            url = (it.get("url") or "").strip()
            if not url:
                q = " - ".join(p for p in [it.get("artist"), it.get("title")] if p)
                if not q:
                    continue
                url = f"ytsearch1:{q}"
            prepared.append({
                "url": url,
                "source": "compare",
                "title": it.get("title"),
                "artist": it.get("artist"),
                "album": it.get("album"),
                "duration": it.get("duration"),
                "mode": body.get("mode") or "audio",
            })
        if not prepared:
            return self._error("None of those items had a usable URL or title.")

        pid = ctx.db.add_playlist(name, "compare", None)
        added = ctx.db.add_items(pid, prepared)
        ctx.hub.emit("playlists_changed", {})
        self._json({"ok": True, "playlist_id": pid, "added": added})

    # -- API: reveal in file manager --------------------------------------
    def _api_reveal(self) -> None:
        import subprocess
        import sys

        body = self._read_json()
        target = body.get("path") or str(self._ctx().cfg.download_dir())
        path = Path(target).expanduser()
        if not path.exists():
            return self._error("Path does not exist.", 404)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            elif sys.platform.startswith("win"):
                if path.is_dir():
                    subprocess.Popen(["explorer", str(path)])
                else:
                    subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
        except Exception as exc:
            return self._error(f"Could not open: {exc}")
        self._json({"ok": True})

    def _shutdown_soon(self) -> None:
        ctx = self._ctx()
        time.sleep(0.3)
        ctx.shutdown.set()
        try:
            ctx.manager.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------

def build_server(ctx: AppContext, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    global CTX
    CTX = ctx
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server