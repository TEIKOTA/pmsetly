#!/bin/sh
# Usage: ./build.sh && sudo ./install.sh
# 1. Copies build/pmsetly.app to /Applications.
# 2. Lets YOU (only you) run exactly these two commands without a password:
#      /usr/bin/pmset -a disablesleep 0
#      /usr/bin/pmset -a disablesleep 1
set -eu
cd "$(dirname "$0")"

USER_NAME="${SUDO_USER:?Run with sudo: sudo ./install.sh}"
RULE=/etc/sudoers.d/pmsetly
TMP=$(mktemp)

echo "$USER_NAME ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 0, /usr/bin/pmset -a disablesleep 1" > "$TMP"
visudo -c -f "$TMP"
install -m 0440 -o root -g wheel "$TMP" "$RULE"
rm "$TMP"

rm -rf /Applications/pmsetly.app
cp -R build/pmsetly.app /Applications/
echo "Installed. Open /Applications/pmsetly.app"
