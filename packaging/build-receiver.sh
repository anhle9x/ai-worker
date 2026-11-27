#!/bin/sh
# Builds the Go receiver for the server, so the server needs no Go: sh packaging/build-receiver.sh (needs Go 1.22 or later here).
# Dựng bộ nhận Go cho máy chủ, để máy chủ không cần Go: sh packaging/build-receiver.sh (cần Go 1.22 trở lên ở máy này).
# The programs land in server/receiver-bin/ with their SHA256SUMS, so the rsync of server/ carries them and install-receiver.sh takes them.
# Các file chạy nằm trong server/receiver-bin/ cùng SHA256SUMS, nên lần rsync server/ mang chúng theo và install-receiver.sh dùng chúng.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/packaging/lang.sh" ] || { echo "packaging/lang.sh is missing. / Thiếu packaging/lang.sh." >&2; exit 1; } # i18n-allow
. "$ROOT/packaging/lang.sh"
if ! command -v go >/dev/null 2>&1; then
  say "Go 1.22 or later is needed on this computer: https://go.dev/dl/" "Máy này cần Go 1.22 trở lên: https://go.dev/dl/" >&2
  exit 1
fi
OUT="${OUT_DIR:-$ROOT/server/receiver-bin}"
mkdir -p "$OUT"
rm -f "$OUT"/ai-worker-receiver-* "$OUT/SHA256SUMS" "$OUT/BUILD"
# the server runs Linux (install.sh needs systemd): the two processors servers mostly have
# máy chủ chạy Linux (install.sh cần systemd): hai loại bộ xử lý máy chủ hay dùng nhất
for arch in amd64 arm64; do
  os=linux
  name="ai-worker-receiver-$os-$arch"
  # no C, no paths of this computer inside, no debug symbols: the same source gives the same bytes on any computer
  # không C, không đường dẫn của máy này bên trong, không ký hiệu gỡ lỗi: cùng mã nguồn cho cùng byte trên mọi máy
  (cd "$ROOT/receiver" && CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build -trimpath -buildvcs=false -ldflags='-s -w' -o "$OUT/$name" .)
done
COMMIT=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)
VERSION=$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' "$ROOT/.claude-plugin/plugin.json" | head -n 1)
printf 'version=%s\ncommit=%s\ngo=%s\n' "$VERSION" "$COMMIT" "$(go env GOVERSION)" > "$OUT/BUILD"
(cd "$OUT" && { if command -v sha256sum >/dev/null 2>&1; then sha256sum ai-worker-receiver-*; else shasum -a 256 ai-worker-receiver-*; fi; } > SHA256SUMS)
echo "$OUT"
