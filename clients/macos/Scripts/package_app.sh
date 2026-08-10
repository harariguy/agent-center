#!/usr/bin/env bash
# Build the SwiftPM executable and lay it out as a real .app bundle.
#
# SwiftPM cannot emit .app bundles, and the app needs one: UNUserNotificationCenter
# refuses to operate without a bundle identifier, and LSUIElement has to come
# from an Info.plist. So the bundle is assembled here and signed ad-hoc.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

CONFIGURATION=${1:-release}
APP="$ROOT/build/Agent Center.app"
VERSION="0.1.0"
BUILD_NUMBER=$(date +%Y%m%d%H%M)

case "$CONFIGURATION" in
  debug|release) ;;
  *) echo "usage: $0 [debug|release]" >&2; exit 1 ;;
esac

mkdir -p "$ROOT/build"

swift build -c "$CONFIGURATION"
BIN_DIR="$(swift build -c "$CONFIGURATION" --show-bin-path)"

if [[ ! -f "$ROOT/build/AppIcon.icns" ]]; then
  echo "rendering app icon…"
  swift Scripts/make_icon.swift >/dev/null
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_DIR/AgentCenter" "$APP/Contents/MacOS/AgentCenter"
[[ -f "$ROOT/build/AppIcon.icns" ]] && cp "$ROOT/build/AppIcon.icns" "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>AgentCenter</string>
  <key>CFBundleIdentifier</key><string>ai.tydra.agent-center</string>
  <key>CFBundleName</key><string>Agent Center</string>
  <key>CFBundleDisplayName</key><string>Agent Center</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${BUILD_NUMBER}</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHumanReadableCopyright</key><string>MIT licensed</string>
</dict>
</plist>
PLIST

# Ad-hoc signing is enough for a local build. If a caller explicitly requests a
# Developer ID, fail rather than silently producing an ad-hoc bundle that looks
# distributable but cannot be notarised and may not launch at login.
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --options runtime --sign "$CODESIGN_IDENTITY" "$APP"
else
  codesign --force --sign - "$APP"
fi

codesign --verify --strict "$APP"
echo "built $APP"
