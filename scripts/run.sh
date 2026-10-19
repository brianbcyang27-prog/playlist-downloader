#!/usr/bin/env bash
# Launch Playlist Downloader on macOS / Linux.
#
# Uses (or creates) a project-local virtual environment so nothing pollutes the
# system Python. Safe to run repeatedly; it only installs on the first run.
#
#   ./scripts/run.sh                 # normal start (auto-opens your browser)
#   ./scripts/run.sh --port 9000     # any extra flags pass through to the app
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

find_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if [ -x ".venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  if ! BASE="$(find_python)"; then
    echo "Python 3 is required. Get it from https://www.python.org/downloads/" >&2
    exit 1
  fi
  echo "First run: creating a virtual environment in .venv …"
  "$BASE" -m venv .venv
  PY="$ROOT/.venv/bin/python"
  "$PY" -m pip install --upgrade pip
fi

# Install dependencies if they are missing (or were removed).
if ! "$PY" -c "import yt_dlp, mutagen" >/dev/null 2>&1; then
  echo "Installing dependencies (one time) …"
  "$PY" -m pip install -r requirements.txt
fi

exec "$PY" -m app.server "$@"
