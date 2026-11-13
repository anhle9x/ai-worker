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
# Only the installers and the guides sit at the top; the plugin and helper files go into setup/
# Ngoài cùng chỉ có file cài và hướng dẫn; plugin và file phụ vào setup/
SETUP="$PKG/setup"

mkdir -p "$SETUP/.claude-plugin" "$OUT_DIR"
cat > "$SETUP/.claude-plugin/marketplace.json" <<'EOF'
{
  "name": "ai-worker",
  "owner": { "name": "AI Worker" },
  "plugins": [
    { "name": "ai-worker", "source": "./ai-worker", "description": "3D virtual office that shows Claude, Gemini, ChatGPT and Gemma at work" }
  ]
}
EOF

rsync -a --exclude assets --exclude extensions --exclude packaging --exclude dist --exclude server --exclude tests --exclude TRANG-THAI.md --exclude .git --exclude .github --exclude .gitignore \
  --exclude .DS_Store --exclude node_modules "$ROOT/" "$SETUP/ai-worker/"
# The public keys that sign updates live outside git: without them the installed plugin does not update itself
# Khoá công khai ký bản cập nhật nằm ngoài git: thiếu chúng thì plugin đã cài không tự cập nhật
SIGNERS="${SIGNERS:-$HOME/.ai-worker-keys/allowed_signers}"
[ -f "$SIGNERS" ] && cp "$SIGNERS" "$SETUP/ai-worker/keys/allowed_signers"
grep -qE '^[[:space:]]*ai-worker[[:space:]]+ssh-' "$SETUP/ai-worker/keys/allowed_signers" 2>/dev/null ||
  say "Note: no signing key in $SIGNERS, so this package will not update itself" "Lưu ý: chưa có khoá ký trong $SIGNERS, gói này sẽ không tự cập nhật" >&2
# The on-computer page and the server page share the drawing code: the two copies must be identical
# Trang trên máy và trang máy chủ dùng chung phần vẽ: hai bản phải giống nhau
for f in i18n.js ops.vi.js ops.js ops.css ops3d.js; do
  cmp -s "$ROOT/web/$f" "$ROOT/server/static/$f" || {
    say "web/$f differs from server/static/$f: copy it over and build again" "web/$f khác server/static/$f: chép lại rồi đóng gói" >&2
    exit 1
  }
done
cp "$ROOT/packaging/INSTALL-Mac.command" "$ROOT/packaging/INSTALL-Windows.bat" "$ROOT/packaging/INSTALL-Linux.sh" \
  "$ROOT/packaging/GUIDE.txt" "$ROOT/packaging/GUIDE.vi.txt" "$PKG/"
cp "$ROOT/packaging/ask-name.ps1" \
  "$ROOT/packaging/lang.sh" "$ROOT/packaging/lang.ps1" \
  "$ROOT/packaging/install-desktop.sh" "$ROOT/packaging/install-desktop.ps1" \
  "$ROOT/packaging/helpers.sh" "$ROOT/packaging/helpers.ps1" \
  "$ROOT/packaging/check-network.sh" "$ROOT/packaging/check-network.ps1" "$SETUP/"
# For people who write code: the tools the coding and testing skills need. They sit in setup/, out of the staff's way
# Cho người viết code: các công cụ mà skill viết code và kiểm thử cần. Chúng nằm trong setup/, không vướng nhân viên
cp "$ROOT/packaging/INSTALL-DevTools-Mac.command" "$ROOT/packaging/INSTALL-DevTools-Windows.bat" \
  "$ROOT/packaging/install-deps.sh" "$ROOT/packaging/install-deps.ps1" "$SETUP/"
chmod +x "$PKG/INSTALL-Mac.command" "$PKG/INSTALL-Linux.sh" "$SETUP/INSTALL-DevTools-Mac.command"

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
  cp "$1" "$SETUP/ai-worker/web/company.json"
  # When the installer sees this file it asks for the name (the email comes from the account signed in to Claude)
  # File cài thấy file này thì hỏi tên (email tự lấy từ tài khoản đang đăng nhập Claude)
  echo "Company package: the company dashboard is on." > "$SETUP/ASK-NAME"
  NAME="$NAME"; SUFFIX="-company"
fi
# Windows needs CRLF for .bat files
# Windows cần CRLF cho file .bat
perl -pi -e 's/\r?\n/\r\n/' "$PKG/INSTALL-Windows.bat" "$SETUP/INSTALL-DevTools-Windows.bat" "$SETUP/install-deps.ps1" "$SETUP/ask-name.ps1" "$SETUP/install-desktop.ps1" "$SETUP/helpers.ps1" "$SETUP/lang.ps1" "$SETUP/check-network.ps1"
# PowerShell 5 (built into Windows) reads Vietnamese in a .ps1 correctly only when the file has a UTF-8 BOM
# PowerShell 5 (có sẵn trên Windows) chỉ đọc đúng tiếng Việt trong .ps1 khi file có BOM UTF-8
for f in ask-name install-desktop helpers lang check-network install-deps; do
  printf '\357\273\277' | cat - "$SETUP/$f.ps1" > "$SETUP/$f.tmp" && mv "$SETUP/$f.tmp" "$SETUP/$f.ps1"
done

ZIP="$OUT_DIR/$NAME-$VERSION${SUFFIX:-}.zip"
rm -f "$ZIP"
(cd "$TMP" && zip -qr -X "$ZIP" "$NAME")
rm -rf "$TMP"
echo "$ZIP"
