#!/bin/bash
# Double-click me in Finder to start Playlist Downloader.
#
# Finder runs this in Terminal; the window stays open so you can read any error
# message instead of it vanishing instantly.
cd "$(dirname "$0")" || exit 1

./run.sh "$@"
status=$?

if [ $status -ne 0 ]; then
  echo
  read -r -p "Something went wrong (exit $status). Press Enter to close …"
fi
