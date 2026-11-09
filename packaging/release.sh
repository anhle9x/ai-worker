#!/bin/bash
# Release a plugin update: a zip package (without company.json, the send code or the installers), a manifest and a signature, into server/releases/.
# Phát hành bản cập nhật plugin: gói zip (không có company.json, mã gửi hay file cài), manifest và chữ ký, vào server/releases/.
# Run on the signing computer: bash packaging/release.sh   (asks for the key password), then scp server to the server and run install.sh.
# Chạy trên máy giữ khoá ký: bash packaging/release.sh   (hỏi mật khẩu khoá), rồi scp server lên máy chủ và chạy install.sh.
# Another key: KEY=/path/to/key bash packaging/release.sh. Another output folder: OUT_DIR=/path/out
# Khoá khác: KEY=/đường/khoá bash packaging/release.sh. Thư mục ra khác: OUT_DIR=/đường/ra
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/packaging/lang.sh" ] || { echo "packaging/lang.sh is missing. / Thiếu packaging/lang.sh." >&2; exit 1; } # i18n-allow
. "$ROOT/packaging/lang.sh"
KEY="${KEY:-$HOME/.ai-worker-keys/main}"
SIGNERS="${SIGNERS:-$HOME/.ai-worker-keys/allowed_signers}"
OUT_DIR="${OUT_DIR:-$ROOT/server/releases}"
VERSION=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$ROOT/.claude-plugin/plugin.json")
for f in i18n.js ops.vi.js ops.js ops.css ops3d.js; do
  cmp -s "$ROOT/web/$f" "$ROOT/server/static/$f" || {
    say "web/$f differs from server/static/$f: copy it over and release again" "web/$f khác server/static/$f: chép lại rồi phát hành" >&2
    exit 1
  }
done
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
rsync -a --exclude dev-pack --exclude packaging --exclude dist --exclude server --exclude tests --exclude TRANG-THAI.md --exclude .git --exclude .github \
  --exclude .DS_Store --exclude node_modules --exclude web/company.json --exclude .gitignore "$ROOT/" "$TMP/pkg/"
# The public keys live outside git (the public repository keeps a file of comments only): put them into the package
# Khoá công khai nằm ngoài git (repo công khai chỉ giữ file chú thích): đưa vào gói
[ -f "$SIGNERS" ] && cp "$SIGNERS" "$TMP/pkg/keys/allowed_signers"
if ! grep -qE '^[[:space:]]*ai-worker[[:space:]]+ssh-' "$TMP/pkg/keys/allowed_signers" 2>/dev/null; then
  say "No signing key: put the public keys into $SIGNERS (see docs/INSTALL.md)" "Chưa có khoá ký: ghi khoá công khai vào $SIGNERS (xem docs/INSTALL.vi.md)" >&2
  exit 1
fi
NAME="ai-worker-$VERSION.zip"
rm -rf "$OUT_DIR"; mkdir -p "$OUT_DIR"
(cd "$TMP/pkg" && zip -qr -X "$OUT_DIR/$NAME" .)
HASH=$(shasum -a 256 "$OUT_DIR/$NAME" | cut -d' ' -f1)
printf '{"version":"%s","name":"%s","sha256":"%s","date":%s}\n' "$VERSION" "$NAME" "$HASH" "$(date +%s)" > "$OUT_DIR/latest.json"
ssh-keygen -q -Y sign -f "$KEY" -n ai-worker "$OUT_DIR/latest.json"
ssh-keygen -Y verify -f "$TMP/pkg/keys/allowed_signers" -I ai-worker -n ai-worker -s "$OUT_DIR/latest.json.sig" < "$OUT_DIR/latest.json" >/dev/null
echo "$OUT_DIR: $NAME"
