#!/usr/bin/env python3
"""Bundle a self-contained CPython runtime into a macOS .app.

Run it with the project's venv python so it can see the base interpreter and
the installed site-packages:

    .venv/bin/python scripts/bundle_python.py --dest "App.app/Contents/Resources/python"

It copies

    <base>/bin/pythonX.Y            the interpreter
    <base>/lib/pythonX.Y            the standard library (no site-packages)
    <venv>/lib/pythonX.Y/site-packages   yt-dlp, mutagen, rapidfuzz, yt-dlp-ejs

and then resolves every @rpath / absolute C library those Mach-O files need
(OpenSSL, sqlite, zlib, ffmpeg-free helpers, …) into <dest>/lib, so the app has
no dependency on the machine's Python or conda install.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Trim things a headless backend never imports.
EXCLUDE = {
    "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo",
    "ensurepip", "lib2to3", "site-packages",
}


def log(msg: str) -> None:
    print(f"    {msg}", flush=True)


def find_site_packages() -> Path:
    for p in sys.path:
        if p.endswith("site-packages") and "python" in p:
            return Path(p)
    raise SystemExit("could not locate the venv site-packages")


def macho_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and (p.suffix in (".so", ".dylib") or p.name.startswith("python")):
            yield p


def linked_libs(path: Path) -> list[str]:
    try:
        out = subprocess.run(["otool", "-L", str(path)], capture_output=True,
                             text=True, timeout=60).stdout
    except Exception:
        return []
    return [line.strip().split(" (")[0].strip() for line in out.splitlines()[1:] if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--site-packages", default=None)
    args = ap.parse_args()

    dest = Path(args.dest).resolve()
    base = Path(sys.base_prefix)
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    site = Path(args.site_packages) if args.site_packages else find_site_packages()

    if dest.exists():
        shutil.rmtree(dest)
    (dest / "bin").mkdir(parents=True)
    (dest / "lib").mkdir(parents=True)

    # 1) interpreter ---------------------------------------------------------
    exe = base / "bin" / f"python{ver}"
    if not exe.exists():
        raise SystemExit(f"base interpreter not found: {exe}")
    shutil.copy2(exe, dest / "bin" / f"python{ver}")
    log(f"interpreter  python{ver} ({exe.stat().st_size // 1048576} MB)")

    # 2) stdlib --------------------------------------------------------------
    src_lib = base / "lib" / f"python{ver}"
    dst_lib = dest / "lib" / f"python{ver}"
    shutil.copytree(src_lib, dst_lib, ignore=shutil.ignore_patterns(*EXCLUDE),
                    symlinks=True, dirs_exist_ok=True)
    shutil.rmtree(dst_lib / "site-packages", ignore_errors=True)
    log(f"stdlib       {sum(1 for _ in dst_lib.rglob('*')):,} entries")

    # 3) site-packages -------------------------------------------------------
    #    pip/setuptools/wheel are never used at runtime (nothing installs into
    #    the bundle), and they carry the longest paths, so drop them.
    shutil.copytree(site, dst_lib / "site-packages", symlinks=True,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "pip", "pip-*", "setuptools", "setuptools-*",
                        "wheel", "wheel-*"))
    log(f"site-packages {site.name}")

    # 4) C libraries ---------------------------------------------------------
    search = [base / "lib", src_lib / "lib-dynload", dst_lib / "site-packages"]
    copied: dict[str, Path] = {}
    seen: set[str] = set()
    queue = [ref for f in macho_files(dest) for ref in linked_libs(f)]
    while queue:
        ref = queue.pop()
        if ref in seen or ref.startswith(("/usr/lib/", "/System/")):
            continue
        seen.add(ref)
        name = os.path.basename(ref)
        src = None
        for d in search:
            cand = d / name
            if cand.exists():
                src = cand
                break
        if src is None:
            continue
        target = dest / "lib" / name
        if not target.exists():
            shutil.copy2(src, target)
            copied[name] = src
            queue.extend(linked_libs(target))
    log(f"c libraries  {len(copied)} copied: {', '.join(sorted(copied))}")

    # 5) make the interpreter find its stdlib without env vars --------------
    #    A small marker file so the Swift shell knows it is valid.
    (dest / "PYTHON_BUNDLE").write_text(f"python {ver}\n", "utf-8")
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    log(f"total        {total // 1048576} MB")


if __name__ == "__main__":
    main()
