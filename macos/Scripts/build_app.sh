#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="Prompt Scheduler"
PRODUCT_NAME="PromptSchedulerUI"
APP_DIR="${MACOS_DIR}/.build/${APP_NAME}.app"
LOGO_PATH="${MACOS_DIR}/Sources/PromptSchedulerUI/Resources/AppLogo.png"
ICON_PATH="${MACOS_DIR}/Sources/PromptSchedulerUI/Resources/AppIcon.icns"

cd "${MACOS_DIR}"
swift build -c release --product "${PRODUCT_NAME}"

rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/Contents/MacOS" "${APP_DIR}/Contents/Resources"

cat > "${APP_DIR}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>${PRODUCT_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>local.prompt-scheduler</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
PLIST

cp "${MACOS_DIR}/.build/release/${PRODUCT_NAME}" "${APP_DIR}/Contents/MacOS/${PRODUCT_NAME}"
cp "${LOGO_PATH}" "${APP_DIR}/Contents/Resources/AppLogo.png"
cp "${ICON_PATH}" "${APP_DIR}/Contents/Resources/AppIcon.icns"

echo "${APP_DIR}"
