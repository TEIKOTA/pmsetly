#!/bin/sh
# Builds build/pmsetly.app from source.
set -eu
cd "$(dirname "$0")"

swift build -c release
APP=build/pmsetly.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$(swift build -c release --show-bin-path)/pmsetly" "$APP/Contents/MacOS/"
cp Info.plist "$APP/Contents/"
codesign --force --sign - "$APP"
echo "Built $APP"
