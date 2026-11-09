#!/bin/bash
# Package the technical pack (skills and rules for developers and the IT team). Run: bash packaging/build-dev-pack.sh
# Đóng gói gói kỹ thuật (skill và quy tắc cho lập trình viên, phòng IT). Chạy: bash packaging/build-dev-pack.sh
# It has no send code or company address; install it after the main package or on its own.
# Không có mã gửi hay địa chỉ công ty; cài thêm sau gói chính hoặc riêng cũng được.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/packaging/lang.sh" ] || { echo "packaging/lang.sh is missing. / Thiếu packaging/lang.sh." >&2; exit 1; } # i18n-allow
. "$ROOT/packaging/lang.sh"
VERSION=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$ROOT/dev-pack/.claude-plugin/plugin.json")
NAME="AI-Worker-Dev"
OUT_DIR="$ROOT/dist"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PKG="$TMP/$NAME"
mkdir -p "$PKG/.claude-plugin" "$OUT_DIR"
cat > "$PKG/.claude-plugin/marketplace.json" <<'EOF'
{
  "name": "ai-worker-dev",
  "owner": { "name": "AI Worker" },
  "plugins": [
    { "name": "ai-worker-dev", "source": "./ai-worker-dev", "description": "Skills and rules for developers and the IT team" }
  ]
}
EOF
rsync -a --exclude node_modules --exclude .DS_Store "$ROOT/dev-pack/" "$PKG/ai-worker-dev/"
cp "$ROOT/packaging/INSTALL-Dev-Mac.command" "$ROOT/packaging/INSTALL-Dev-Windows.bat" \
  "$ROOT/packaging/install-deps.sh" "$ROOT/packaging/install-deps.ps1" \
  "$ROOT/packaging/lang.sh" "$ROOT/packaging/lang.ps1" "$PKG/"
chmod +x "$PKG/INSTALL-Dev-Mac.command"
perl -pi -e 's/\r?\n/\r\n/' "$PKG/INSTALL-Dev-Windows.bat" "$PKG/install-deps.ps1" "$PKG/lang.ps1"
# A UTF-8 BOM so that PowerShell 5 reads the Vietnamese text correctly
# BOM UTF-8 để PowerShell 5 đọc đúng tiếng Việt
for f in install-deps lang; do
  printf '\357\273\277' | cat - "$PKG/$f.ps1" > "$PKG/x.tmp" && mv "$PKG/x.tmp" "$PKG/$f.ps1"
done
ZIP="$OUT_DIR/$NAME-$VERSION.zip"
rm -f "$ZIP"
(cd "$TMP" && zip -qr -X "$ZIP" "$NAME")
echo "$ZIP"
