#!/usr/bin/env bash
set -e

echo "=== Building PhoneTransfer.app and DMG ==="

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Preserve previous releases; refuse to overwrite an existing DMG.
DMG_NAME="PhoneTransfer-v1.0.2-macOS.dmg"
if [ -e "dist/${DMG_NAME}" ]; then
  echo "Refusing to overwrite dist/${DMG_NAME}" >&2
  exit 1
fi
APP_BUNDLE="dist/v1.0.2-build/PhoneTransfer.app"
if [ ! -d "${APP_BUNDLE}" ]; then
  echo "Missing ${APP_BUNDLE}; build version 1.0.2 first" >&2
  exit 1
fi
DMG_ROOT="$(mktemp -d "${DIR}/dist/.dmg-root.XXXXXX")"
trap 'rm -rf "${DMG_ROOT}"' EXIT
cp -R "${APP_BUNDLE}" "${DMG_ROOT}/PhoneTransfer.app"
ln -s /Applications "${DMG_ROOT}/Applications"
hdiutil create -volname "PhoneTransfer"   -srcfolder "${DMG_ROOT}"   -format UDZO   "dist/${DMG_NAME}"

echo "=== Successfully built: dist/${DMG_NAME} ==="
ls -lh "dist/${DMG_NAME}"

