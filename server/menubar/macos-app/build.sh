#!/bin/bash
# Builds the macOS menu bar app for one company: bash build.sh https://board.example.com [auto|vi|en] [name] [logo-folder] [en|vi route names]
# Đóng gói app thanh menu macOS cho một công ty: bash build.sh https://board.example.com [auto|vi|en] [tên] [thư-mục-logo] [en|vi tên đường dẫn]
# Runs on a Mac with Apple's Command Line Tools (xcode-select --install); people who only use the app need nothing.
# Chạy trên máy Mac có Command Line Tools của Apple (xcode-select --install); người chỉ dùng app không cần gì cả.
# The board's address is written inside the app before it is signed, so the app is never changed after signing.
# Địa chỉ bảng được ghi vào app trước khi ký, nên app không bị sửa sau khi ký.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVER="${1:-}"
LANG_CODE="${2:-auto}"
NAME="${3:-AI Worker}"
LOGO_DIR="${4:-$HERE/../icons}"
DIALECT="${5:-en}"
# http only to this very computer: the host must be exactly localhost, 127.0.0.1 or [::1], then a port or a path
# http chỉ tới chính máy này: máy chủ phải đúng là localhost, 127.0.0.1 hoặc [::1], sau đó là cổng hoặc đường dẫn
case "$SERVER" in
  https://?*|http://localhost|http://localhost[:/]*|http://127.0.0.1|http://127.0.0.1[:/]*|"http://[::1]"|"http://[::1]"[:/]*) ;;
  *) echo "Usage: bash build.sh https://your-board-address [auto|vi|en] [name] [logo-folder] [en|vi route names]"; exit 1 ;;
esac
command -v swiftc >/dev/null || { echo "Needs Apple's Command Line Tools: run xcode-select --install, then run this again."; exit 1; }

OUT="$HERE/dist"
APP="$OUT/$NAME.app"
rm -rf "$APP" && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

# one program for both Apple silicon and Intel Macs, macOS 13 or newer
# một chương trình chạy cả Mac chip Apple lẫn Intel, macOS 13 trở lên
for arch in arm64 x86_64; do
  swiftc -O -target "$arch-apple-macos13.0" -o "$BUILD/app-$arch" "$HERE/main.swift"
done
lipo -create "$BUILD/app-arm64" "$BUILD/app-x86_64" -output "$APP/Contents/MacOS/MenuBar"

# logo: black, or icon-black.png from the company's own folder
# logo: bản đen, hoặc icon-black.png trong thư mục riêng của công ty
LOGO="$LOGO_DIR/icon-black.png"
[ -f "$LOGO" ] || LOGO="$LOGO_DIR/generic-black.png"
cp "$LOGO" "$APP/Contents/Resources/icon-black.png"
# the app's own icon in Finder, Launchpad and the installer: app-icon.png from the company's folder, else the outline G
# biểu tượng của chính app trong Finder, Launchpad và ổ cài: app-icon.png trong thư mục riêng của công ty, không có thì chữ G viền
APP_ICON="$LOGO_DIR/app-icon.png"
[ -f "$APP_ICON" ] || APP_ICON="$HERE/../icons/app-icon.png"
ICONSET="$BUILD/AppIcon.iconset"
mkdir -p "$ICONSET"
for px in 16 32 128 256 512; do
  sips -z $px $px "$APP_ICON" --out "$ICONSET/icon_${px}x${px}.png" >/dev/null
  sips -z $((px * 2)) $((px * 2)) "$APP_ICON" --out "$ICONSET/icon_${px}x${px}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
cp "$HERE/../vi.json" "$APP/Contents/Resources/vi.json"
python3 -c 'import json, sys; json.dump({"server": sys.argv[1].rstrip("/"), "lang": sys.argv[2], "name": sys.argv[3], "dialect": sys.argv[5]}, open(sys.argv[4], "w"))' \
  "$SERVER" "$LANG_CODE" "$NAME" "$APP/Contents/Resources/config.json" "$DIALECT"

BUNDLE_ID="com.ai-worker.menubar.$(printf '%s' "$SERVER" | shasum -a 256 | cut -c1-8)"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
<key>CFBundleName</key><string>$NAME</string>
<key>CFBundleDisplayName</key><string>$NAME</string>
<key>CFBundleExecutable</key><string>MenuBar</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>LSUIElement</key><true/>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
EOF

# ad-hoc signature: the first launch asks "Open Anyway" once; with an Apple Developer ID, sign with it here instead
# chữ ký tạm: lần mở đầu phải bấm "Open Anyway" một lần; có Apple Developer ID thì ký bằng nó ở đây
codesign --force --sign "${SIGN_IDENTITY:--}" --options runtime --timestamp=none "$APP"
codesign --verify --strict "$APP"

ZIP="$OUT/$(printf '%s' "$NAME" | tr ' ' '-')-menu-bar-mac-app.zip"
rm -f "$ZIP"
( cd "$OUT" && ditto -c -k --keepParent "$NAME.app" "$ZIP" )

# the same app as a disk image: opening it shows the app next to Applications, to drag across
# cùng app đó dạng ổ đĩa ảo: mở ra thấy app cạnh thư mục Applications, chỉ việc kéo sang
DMG="${ZIP%.zip}.dmg"
STAGE="$BUILD/dmg"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$NAME.app"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
# the opened disk shows the app's logo: .VolumeIcon.icns at its root plus the "custom icon" flag, set on a writable copy, then compressed
# ổ đĩa mở ra hiện logo của app: .VolumeIcon.icns ở gốc ổ kèm cờ "biểu tượng riêng", đặt trên bản ghi được rồi mới nén
cp "$APP/Contents/Resources/AppIcon.icns" "$STAGE/.VolumeIcon.icns"
hdiutil create -quiet -volname "$NAME" -srcfolder "$STAGE" -fs HFS+ -format UDRW -ov "$BUILD/rw.dmg"
MNT="$BUILD/mnt"
mkdir -p "$MNT"
hdiutil attach -quiet -nobrowse -noverify -noautoopen -mountpoint "$MNT" "$BUILD/rw.dmg"
xattr -wx com.apple.FinderInfo "0000000000000000040000000000000000000000000000000000000000000000" "$MNT" || true
hdiutil detach -quiet "$MNT"
hdiutil convert -quiet "$BUILD/rw.dmg" -format UDZO -o "$DMG" -ov
echo "Built: $ZIP"
echo "Built: $DMG"
