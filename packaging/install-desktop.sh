#!/bin/bash
# Installs the Claude Desktop app on a Mac after asking once. Exit 0 installed, 1 not installed. --verify-only downloads and checks without installing.
# Cài app Claude Desktop trên Mac sau khi hỏi một lần. Thoát 0 là đã cài, 1 là chưa cài. --verify-only tải và kiểm chứ không cài.
# The general download link blocks scripts, so this uses the versioned file and checksum published in the Homebrew catalog,
# Link tải chung chặn script, nên file này dùng bản theo phiên bản và mã kiểm tra công bố trong danh mục Homebrew,
# then checks the app is notarized and signed by Anthropic before it is copied.
# rồi kiểm app đã được Apple xác thực và do Anthropic ký trước khi chép.
set -u
cd "$(dirname "$0")" || exit 1
[ -f ./lang.sh ] || { echo "lang.sh is missing next to this file: unzip the whole zip file and run again." >&2; exit 1; }
. ./lang.sh

CATALOG="https://formulae.brew.sh/api/cask/claude.json"
ANTHROPIC_TEAM="Q6L2SF6YDW"
VERIFY_ONLY=""
[ "${1:-}" = "--verify-only" ] && VERIFY_ONLY=1

not_installed() {
  say "Claude is not installed on this computer." "Máy chưa cài Claude."
  say "Download Claude Desktop at https://claude.com/download, sign in, open the Code tab once, then run this file again." "Tải Claude Desktop tại https://claude.com/download, đăng nhập, mở tab Code một lần, rồi chạy lại file này."
  exit 1
}

if [ -z "$VERIFY_ONLY" ]; then
  say "Claude Desktop is not on this computer. It is needed to use this plugin." "Máy chưa có Claude Desktop. Plugin này cần app đó."
  QUESTION=$(
    say "Install it now from Anthropic? Installing means you accept Anthropic's terms. [Y/n] " "Cài ngay từ Anthropic? Cài nghĩa là bạn đồng ý điều khoản của Anthropic. [Y/n] "
  )
  answer=""; read -r -p "$QUESTION" answer || true
  case "$answer" in n*|N*|k*|K*) not_installed ;; esac
fi

TMP=$(mktemp -d) || not_installed
trap 'rm -rf "$TMP"' EXIT

say "Downloading Claude Desktop..." "Đang tải Claude Desktop..."
if ! curl -fsSL -m 60 -o "$TMP/catalog.json" "$CATALOG"; then
  say "Cannot read the download catalog." "Không đọc được danh mục tải."
  not_installed
fi
URL=$(plutil -extract url raw -o - "$TMP/catalog.json" 2>/dev/null)
SHA=$(plutil -extract sha256 raw -o - "$TMP/catalog.json" 2>/dev/null)
# Only Anthropic's own download host is accepted, whatever the catalog says.
# Chỉ nhận máy chủ tải của chính Anthropic, dù danh mục ghi gì.
case "$URL" in
  https://downloads.claude.ai/*) ;;
  *)
    say "The download address is not from Anthropic: stopped." "Địa chỉ tải không phải của Anthropic: đã dừng."
    not_installed
    ;;
esac
case "$SHA" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *)
    say "The catalog has no checksum: stopped." "Danh mục không có mã kiểm tra: đã dừng."
    not_installed
    ;;
esac
if ! curl -fL --progress-bar -m 1800 -o "$TMP/claude.zip" "$URL"; then
  say "The download failed." "Tải về thất bại."
  not_installed
fi
if ! [ "$(shasum -a 256 "$TMP/claude.zip" | cut -d' ' -f1)" = "$SHA" ]; then
  say "The downloaded file does not match its checksum: stopped." "File tải về không khớp mã kiểm tra: đã dừng."
  not_installed
fi
if ! ditto -x -k "$TMP/claude.zip" "$TMP/app"; then
  say "Cannot unpack the download." "Không giải nén được file tải về."
  not_installed
fi
APP="$TMP/app/Claude.app"
if ! [ -d "$APP" ]; then
  say "The download does not contain the app." "File tải về không có app."
  not_installed
fi
if ! codesign --verify --deep --strict "$APP" 2>/dev/null; then
  say "The app's signature is not valid: stopped." "Chữ ký của app không hợp lệ: đã dừng."
  not_installed
fi
TEAM=$(codesign -dv "$APP" 2>&1 | sed -n 's/^TeamIdentifier=//p')
if ! [ "$TEAM" = "$ANTHROPIC_TEAM" ]; then
  say "The app is not signed by Anthropic: stopped." "App không do Anthropic ký: đã dừng."
  not_installed
fi
if ! spctl -a -t exec "$APP" 2>/dev/null; then
  say "macOS does not accept this app: stopped." "macOS không chấp nhận app này: đã dừng."
  not_installed
fi

if [ -n "$VERIFY_ONLY" ]; then
  say "Checked: checksum, signature and Anthropic's team all match. Nothing was installed." "Đã kiểm: mã kiểm tra, chữ ký và nhóm của Anthropic đều khớp. Chưa cài gì."
  exit 0
fi

DEST=/Applications
[ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
if ! ditto "$APP" "$DEST/Claude.app"; then
  say "Cannot copy the app to $DEST." "Không chép được app vào $DEST."
  not_installed
fi
open "$DEST/Claude.app" 2>/dev/null || true
say "Claude Desktop is installed and opening. Sign in, open the Code tab once, then run this file again." "Đã cài và đang mở Claude Desktop. Hãy đăng nhập, mở tab Code một lần, rồi chạy lại file này."
exit 0
