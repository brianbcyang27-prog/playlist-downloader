# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Playlist Downloader.

    pip install pyinstaller
    pyinstaller playlist_downloader.spec

Produces a single self-contained executable in ``dist/``:

    macOS / Linux   dist/PlaylistDownloader
    Windows         dist/PlaylistDownloader.exe

It bundles the Python runtime, yt-dlp, mutagen, the optional rapidfuzz
accelerator and the ``web/`` UI, so the person running it needs no Python
install. **ffmpeg is still required on PATH** (it is a large external binary);
the app prints an install hint and still downloads when it is missing, but
audio conversion needs it.

    macOS    brew install ffmpeg
    Windows  winget install Gyan.FFmpeg
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)  # noqa: F821  - injected by PyInstaller

datas = [(str(ROOT / "web"), "web")]
binaries = []
hiddenimports = []

# yt-dlp loads extractors dynamically, so PyInstaller must be told to keep them.
for package in ("yt_dlp", "yt_dlp_ejs", "mutagen"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:  # pragma: no cover - optional / version differences
        pass

# rapidfuzz is optional; bundle it when it is installed.
try:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all("rapidfuzz")
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
except Exception:  # pragma: no cover
    pass

hiddenimports += collect_submodules("mutagen")

a = Analysis(
    [str(ROOT / "app" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "pytest", "pydoc"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PlaylistDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
