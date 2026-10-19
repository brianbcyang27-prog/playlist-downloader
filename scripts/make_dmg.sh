#!/bin/bash
# Build "Playlist Downloader.app" as a self-contained *native* macOS app and
# package it into a .dmg for drag-to-Applications installation.
#
#   ./scripts/make_dmg.sh                 # build app + dmg, install to ~/Applications
#   ./scripts/make_dmg.sh --no-dmg        # just build/install the .app (fast iteration)
#   ./scripts/make_dmg.sh --no-install    # build only, leave ~/Applications alone
#
# The app owns a real window (WKWebView) and starts the Python backend itself,
# so it never opens a browser. Everything it needs (Python, yt-dlp, mutagen,
# the UI) is inside the bundle; ffmpeg is still required on the system.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$PROJECT_DIR/build"
APP="$BUILD/Playlist Downloader.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"
DISPLAY_NAME="Playlist Downloader"
BUNDLE_ID="com.brianyang.playlistdownloader"
EXEC_NAME="PlaylistDownloader"
VERSION="1.0.1"
DIST="$PROJECT_DIR/dist"
DMG="$DIST/$DISPLAY_NAME $VERSION.dmg"

MAKE_DMG=1
INSTALL=1
for arg in "$@"; do
  case "$arg" in
    --no-dmg) MAKE_DMG=0 ;;
    --no-install) INSTALL=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

PY="$PROJECT_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

echo "==> Cleaning $BUILD"
rm -rf "$BUILD"
mkdir -p "$CONTENTS/MacOS" "$RES"

echo "==> Compiling the native shell (Swift)"
swiftc -O -o "$CONTENTS/MacOS/$EXEC_NAME" "$PROJECT_DIR/scripts/native_app.swift" \
  -framework Cocoa -framework WebKit 2>&1 | grep -v "DVTFilePathFSEvents\|DVTDeveloperPaths" || true
[ -x "$CONTENTS/MacOS/$EXEC_NAME" ] || { echo "swiftc failed" >&2; exit 1; }
echo "    $(basename "$CONTENTS/MacOS/$EXEC_NAME"): $(du -h "$CONTENTS/MacOS/$EXEC_NAME" | cut -f1)"

echo "==> App icon"
"$PY" "$PROJECT_DIR/scripts/make_icon.py" --icns "$RES/AppIcon.icns"

echo "==> Copying backend + UI into the bundle"
rsync -a --exclude '__pycache__' "$PROJECT_DIR/app/" "$RES/app/"
rsync -a --exclude '__pycache__' "$PROJECT_DIR/web/" "$RES/web/"

echo "==> Bundling the Python runtime"
"$PY" "$PROJECT_DIR/scripts/bundle_python.py" --dest "$RES/python"

echo "==> Writing Info.plist"
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$DISPLAY_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$DISPLAY_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleExecutable</key>
    <string>$EXEC_NAME</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.music</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
    <key>NSHumanReadableCopyright</key>
    <string></string>
</dict>
</plist>
PLIST

printf 'APPL????' > "$CONTENTS/PkgInfo"

echo "==> Ad-hoc code signature"
codesign --force --deep --sign - "$APP" 2>&1 | grep -v "replacing existing signature" || true
codesign --verify --verbose=2 "$APP" 2>&1 | tail -2 || true

if [ "$MAKE_DMG" = "1" ]; then
  echo "==> Building the DMG"
  mkdir -p "$DIST"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  rm -f "$DMG"
  # Normal path: one-shot create. In a sandbox without DiskArbitration that
  # fails ("Device not configured"), so fall back to the pure-userspace route:
  # makehybrid builds an HFS+ image, convert wraps it in a compressed UDIF.
  if ! hdiutil create -volname "$DISPLAY_NAME" -srcfolder "$STAGE" -ov \
        -format UDZO "$DMG" >/dev/null 2>&1; then
    echo "    (hdiutil create unavailable; using makehybrid + convert)"
    RAW="$(mktemp -d)/raw.dmg"
    hdiutil makehybrid -hfs -hfs-volume-name "$DISPLAY_NAME" -o "$RAW" "$STAGE" >/dev/null 2>&1
    hdiutil convert "$RAW" -format UDZO -ov -o "$DMG" >/dev/null 2>&1
    rm -rf "$(dirname "$RAW")"
  fi
  rm -rf "$STAGE"
  if hdiutil verify "$DMG" >/dev/null 2>&1; then
    echo "    checksum verified OK"
  fi
  echo "    $DMG  ($(du -h "$DMG" | cut -f1))"
fi

if [ "$INSTALL" = "1" ]; then
  echo "==> Installing to ~/Applications"
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/$DISPLAY_NAME.app"
  cp -R "$APP" "$HOME/Applications/"
fi

echo "==> Done."
echo "    App: $APP"
[ "$MAKE_DMG" = "1" ] && echo "    DMG: $DMG"
echo "    Open it from Spotlight/Launchpad, or mount the DMG and drag it to Applications."
