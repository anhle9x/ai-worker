#!/bin/bash
# Zips the manager browser extension (Chrome, Edge) so the Admin page can offer it: bash packaging/build-extension.sh
# Nén tiện ích trình duyệt cho quản lý (Chrome, Edge) để trang Quản trị cho tải: bash packaging/build-extension.sh
# The zip lands in server/menubar/, so install.sh copies it to the server with the other menu bar files.
# File zip nằm trong server/menubar/, nên install.sh chép lên máy chủ cùng các file thanh menu khác.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/packaging/lang.sh" ] || { echo "packaging/lang.sh is missing. / Thiếu packaging/lang.sh." >&2; exit 1; } # i18n-allow
. "$ROOT/packaging/lang.sh"
SRC="$ROOT/extensions/manager"
OUT="$ROOT/server/menubar/AI-Worker-extension.zip"
# the extension's small window runs copies of the server's files: they must be identical
# cửa sổ nhỏ của tiện ích chạy bản chép của file máy chủ: hai bản phải giống nhau
for f in mini.js mini.css; do
  cmp -s "$ROOT/server/static/$f" "$SRC/mini/$f" || {
    say "extensions/manager/mini/$f differs from server/static/$f: copy it over and build again" "extensions/manager/mini/$f khác server/static/$f: chép lại rồi đóng gói" >&2
    exit 1
  }
done
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
rsync -a --exclude .DS_Store "$SRC/" "$TMP/AI-Worker-extension/"
rm -f "$OUT"
(cd "$TMP" && zip -qr -X "$OUT" AI-Worker-extension)
echo "$OUT"
