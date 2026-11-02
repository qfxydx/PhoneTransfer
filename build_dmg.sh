#!/usr/bin/env bash
set -e

echo "=== Building PhoneTransfer.app and DMG ==="

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 1. Clean previous build artifacts
rm -rf dist/dmg_root dist/*.dmg

# 2. Prepare DMG root
mkdir -p dist/dmg_root
cp -R dist/PhoneTransfer.app dist/dmg_root/
ln -s /Applications dist/dmg_root/Applications

# 3. Create compressed DMG using native hdiutil
DMG_NAME="PhoneTransfer-v1.0.1-macOS.dmg"
hdiutil create -volname "PhoneTransfer" \
  -srcfolder dist/dmg_root \
  -ov -format UDZO \
  "dist/${DMG_NAME}"

# 4. Clean temporary dmg_root
rm -rf dist/dmg_root

echo "=== Successfully built: dist/${DMG_NAME} ==="
ls -lh "dist/${DMG_NAME}"

