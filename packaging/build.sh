#!/bin/bash
# Package AI Worker Office as a zip to send to another team. Run: bash packaging/build.sh
# Đóng gói Văn phòng AI Worker thành zip gửi team khác. Chạy: bash packaging/build.sh
# Company package (turns on the dashboard, with the webhook address written in): bash packaging/build.sh packaging/company.json
# Gói cho công ty (bật bảng tổng, ghi sẵn địa chỉ webhook): bash packaging/build.sh packaging/company.json
#   (template: packaging/company.example.json); the installer will ask for the user's name and email.
#   (mẫu: packaging/company.example.json); file cài sẽ hỏi tên + email của người dùng.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/packaging/lang.sh" ] || { echo "packaging/lang.sh is missing. / Thiếu packaging/lang.sh." >&2; exit 1; } # i18n-allow
. "$ROOT/packaging/lang.sh"
VERSION=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$ROOT/.claude-plugin/plugin.json")
NAME="AI-Worker"
OUT_DIR="$ROOT/dist"
TMP=$(mktemp -d)
PKG="$TMP/$NAME"

mkdir -p "$PKG/.claude-plugin" "$OUT_DIR"
cat > "$PKG/.claude-plugin/marketplace.json" <<'EOF'
{
  "name": "ai-worker",
  "owner": { "name": "AI Worker" },
  "plugins": [
    { "name": "ai-worker", "source": "./ai-worker", "description": "3D virtual office that shows Claude, Gemini, ChatGPT and Gemma at work" }
  ]
}
EOF

rsync -a --exclude dev-pack --exclude assets --exclude extensions --exclude packaging --exclude dist --exclude server --exclude tests --exclude TRANG-THAI.md --exclude .git --exclude .github --exclude .gitignore \
  --exclude .DS_Store --exclude node_modules "$ROOT/" "$PKG/ai-worker/"
# The on-computer page and the server page share the drawing code: the two copies must be identical
# Trang trên máy và trang máy chủ dùng chung phần vẽ: hai bản phải giống nhau
for f in i18n.js ops.vi.js ops.js ops.css ops3d.js; do
  cmp -s "$ROOT/web/$f" "$ROOT/server/static/$f" || {
    say "web/$f differs from server/static/$f: copy it over and build again" "web/$f khác server/static/$f: chép lại rồi đóng gói" >&2
    exit 1
  }
done
cp "$ROOT/packaging/INSTALL-Mac.command" "$ROOT/packaging/INSTALL-Windows.bat" "$ROOT/packaging/INSTALL-Linux.sh" \
  "$ROOT/packaging/GUIDE.txt" "$ROOT/packaging/GUIDE.vi.txt" "$ROOT/packaging/ask-name.ps1" \
  "$ROOT/packaging/lang.sh" "$ROOT/packaging/lang.ps1" \
  "$ROOT/packaging/install-desktop.sh" "$ROOT/packaging/install-desktop.ps1" \
  "$ROOT/packaging/helpers.sh" "$ROOT/packaging/helpers.ps1" \
  "$ROOT/packaging/check-network.sh" "$ROOT/packaging/check-network.ps1" "$PKG/"
chmod +x "$PKG/INSTALL-Mac.command" "$PKG/INSTALL-Linux.sh"

if [ -n "$1" ]; then
  python3 -c '
import json, sys
c = json.load(open(sys.argv[1]))["sharing"]
if "<" in json.dumps(c, ensure_ascii=False): sys.exit(11)
if not (c.get("webhook") or c.get("folders")): sys.exit(12)
if c.get("viewCode"): sys.exit(13)
' "$1" || {
    RC=$?
    case $RC in
      11)
        say "A <...> placeholder is still not filled in $1" "còn chỗ <...> chưa điền trong $1" >&2 ;;
      12)
        say "A webhook (or folders) is needed" "cần webhook (hoặc folders)" >&2 ;;
      13)
        say "Do not put viewCode in the staff package" "không đưa viewCode vào gói nhân viên" >&2 ;;
    esac
    exit 1
  }
  cp "$1" "$PKG/ai-worker/web/company.json"
  # When the installer sees this file it asks for the name (the email comes from the account signed in to Claude)
  # File cài thấy file này thì hỏi tên (email tự lấy từ tài khoản đang đăng nhập Claude)
  echo "Company package: the company dashboard is on." > "$PKG/ASK-NAME"
  NAME="$NAME"; SUFFIX="-company"
fi
# Windows needs CRLF for .bat files
# Windows cần CRLF cho file .bat
perl -pi -e 's/\r?\n/\r\n/' "$PKG/INSTALL-Windows.bat" "$PKG/ask-name.ps1" "$PKG/install-desktop.ps1" "$PKG/helpers.ps1" "$PKG/lang.ps1" "$PKG/check-network.ps1"
# PowerShell 5 (built into Windows) reads Vietnamese in a .ps1 correctly only when the file has a UTF-8 BOM
# PowerShell 5 (có sẵn trên Windows) chỉ đọc đúng tiếng Việt trong .ps1 khi file có BOM UTF-8
for f in ask-name install-desktop helpers lang check-network; do
  printf '\357\273\277' | cat - "$PKG/$f.ps1" > "$PKG/$f.tmp" && mv "$PKG/$f.tmp" "$PKG/$f.ps1"
done

ZIP="$OUT_DIR/$NAME-$VERSION${SUFFIX:-}.zip"
rm -f "$ZIP"
(cd "$TMP" && zip -qr -X "$ZIP" "$NAME")
rm -rf "$TMP"
echo "$ZIP"
