#!/bin/bash
# Installs the AI Worker menu bar icon for a manager on macOS: SwiftBar, the script, the logo, start at login.
# Cài biểu tượng thanh menu AI Worker cho quản lý trên macOS: SwiftBar, script, logo, tự chạy khi đăng nhập.
# The server writes its own address into BOARD_URL when it hands out this file.
# Máy chủ ghi địa chỉ của chính nó vào BOARD_URL khi phát file này.
set -u
BOARD_URL="__BOARD_URL__"
HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/ai-worker"
PLIST="$HOME/Library/LaunchAgents/com.ai-worker.menubar.plist"
# SwiftBar is signed by its developer with this team id; anything else is refused
# SwiftBar được nhà phát triển ký với mã nhóm này; khác mã thì từ chối
SWIFTBAR_TEAM="X93LWC49WV"

# Language of the messages: AI_WORKER_LANG (en or vi), else the first macOS language, else English
# Ngôn ngữ lời nhắn: AI_WORKER_LANG (en hoặc vi), không có thì ngôn ngữ đầu tiên của macOS, không có nữa thì tiếng Anh
MAC_LANG="${AI_WORKER_LANG:-$(defaults read -g AppleLanguages 2>/dev/null | sed -n 2p | tr -d ' ",')}"
case "$MAC_LANG" in vi*) LANG_CODE=vi ;; *) LANG_CODE=en ;; esac
# say "English" "Vietnamese": prints the one for this computer's language
# say "English" "Tiếng Việt": in câu theo ngôn ngữ của máy này
say() { if [ "$LANG_CODE" = vi ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
PAUSE_MSG=$(
say "Press Enter to close " "Nhấn Enter để đóng "
)
pause() { read -r -p "$PAUSE_MSG" _; }
stop() { pause; exit 1; }

say "AI Worker menu bar icon" "Biểu tượng thanh menu AI Worker"
echo
say "  1. Install, and start it every time you log in" "  1. Cài, và tự chạy mỗi lần đăng nhập"
say "  2. Remove it from this computer" "  2. Gỡ khỏi máy này"
echo
CHOOSE_MSG=$(
say "Choose 1 or 2: " "Chọn 1 hoặc 2: "
)
read -r -p "$CHOOSE_MSG" CHOICE
if [ "$CHOICE" = 2 ]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  PLUGINS="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)"
  [ -n "$PLUGINS" ] && rm -f "$PLUGINS/ai-worker.1m.py"
  rm -f "$CONFIG_DIR"/menubar.json "$CONFIG_DIR"/menubar-session "$CONFIG_DIR"/menubar-pending.json "$CONFIG_DIR"/menubar-notified.json "$CONFIG_DIR"/menubar-vi.json "$CONFIG_DIR"/icon-black.png "$CONFIG_DIR"/icon-white.png
  open -g "swiftbar://refreshallplugins" 2>/dev/null
  say "Removed. SwiftBar itself stays; drag it to the Trash if nothing else uses it." "Đã gỡ. SwiftBar vẫn còn; kéo nó vào Thùng rác nếu không còn gì khác dùng."
  say "Ask an admin to remove this computer from the Admin page too." "Nhờ quản trị gỡ máy này khỏi trang Quản trị nữa."
  pause
  exit 0
fi
if [ "$CHOICE" != 1 ]; then
  say "Nothing chosen, nothing changed." "Chưa chọn gì, không đổi gì."
  stop
fi

# 1. Python 3: macOS asks to install Apple's Command Line Tools the first time it is needed
# 1. Python 3: lần đầu cần, macOS hỏi cài Command Line Tools của Apple
if ! /usr/bin/python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
  say "This computer needs Apple's Command Line Tools (free, includes Python 3)." "Máy này cần Command Line Tools của Apple (miễn phí, có sẵn Python 3)."
  say "A window will open: click Install, wait until it finishes, then run this file again." "Một cửa sổ sẽ mở: bấm Install, chờ cài xong, rồi chạy lại file này."
  xcode-select --install >/dev/null 2>&1
  pause
  exit 1
fi

# 2. SwiftBar: from Homebrew when it is there, otherwise the official release on GitHub, checked before it is used
# 2. SwiftBar: lấy từ Homebrew nếu có, không thì bản chính thức trên GitHub, kiểm trước khi dùng
APP="/Applications/SwiftBar.app"
[ -d "$APP" ] || APP="$HOME/Applications/SwiftBar.app"
if ! [ -d "$APP" ]; then
  say "Installing SwiftBar (free, open source)..." "Đang cài SwiftBar (miễn phí, mã nguồn mở)..."
  BREW="$(command -v brew || ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1)"
  if [ -n "$BREW" ]; then
    "$BREW" install --cask swiftbar || {
      say "Could not install SwiftBar with Homebrew." "Không cài được SwiftBar bằng Homebrew."
      stop; }
    APP="/Applications/SwiftBar.app"
  else
    TMP="$(mktemp -d)"
    URL="$(/usr/bin/python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen("https://api.github.com/repos/swiftbar/SwiftBar/releases/latest", timeout=20) as r:
    rel = json.load(r)
for a in rel.get("assets", []):
    u = a.get("browser_download_url", "")
    if u.startswith("https://github.com/swiftbar/SwiftBar/releases/download/") and u.endswith(".zip"):
        print(u)
        break
PY
)"
    [ -n "$URL" ] || {
      say "Could not find SwiftBar on GitHub. Check the internet connection, then run this file again." "Không tìm thấy SwiftBar trên GitHub. Kiểm tra mạng rồi chạy lại file này."
      stop; }
    curl -fsSL --proto '=https' -o "$TMP/SwiftBar.zip" "$URL" || {
      say "Could not download SwiftBar." "Không tải được SwiftBar."
      stop; }
    ditto -x -k "$TMP/SwiftBar.zip" "$TMP/out" || {
      say "Could not unzip SwiftBar." "Không giải nén được SwiftBar."
      stop; }
    [ -d "$TMP/out/SwiftBar.app" ] || {
      say "The SwiftBar download is not what was expected." "File SwiftBar tải về không đúng như mong đợi."
      stop; }
    codesign --verify --deep --strict "$TMP/out/SwiftBar.app" 2>/dev/null || {
      say "SwiftBar's signature is not valid, so it was not installed." "Chữ ký của SwiftBar không hợp lệ nên không cài."
      stop; }
    TEAM="$(codesign -dv "$TMP/out/SwiftBar.app" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
    [ "$TEAM" = "$SWIFTBAR_TEAM" ] || {
      say "SwiftBar is signed by someone else ($TEAM), so it was not installed." "SwiftBar do người khác ký ($TEAM) nên không cài."
      stop; }
    if [ -w /Applications ]; then APP="/Applications/SwiftBar.app"; else mkdir -p "$HOME/Applications"; APP="$HOME/Applications/SwiftBar.app"; fi
    ditto "$TMP/out/SwiftBar.app" "$APP" || {
      say "Could not copy SwiftBar to $APP." "Không chép được SwiftBar vào $APP."
      stop; }
    rm -rf "$TMP"
  fi
fi

# 3. Settings, words and logo for the script; the session file is created later, readable only by this user
# 3. Cài đặt, chữ và logo cho script; file phiên tạo sau, chỉ người dùng này đọc được
mkdir -p "$CONFIG_DIR" && chmod 700 "$CONFIG_DIR"
/usr/bin/python3 -c "import json,sys; json.dump({'server': sys.argv[1], 'lang': sys.argv[2]}, open(sys.argv[3], 'w'))" "$BOARD_URL" "$LANG_CODE" "$CONFIG_DIR/menubar.json"
cp "$HERE/vi.json" "$CONFIG_DIR/menubar-vi.json"
cp "$HERE/icon-black.png" "$CONFIG_DIR/icon-black.png"
cp "$HERE/icon-white.png" "$CONFIG_DIR/icon-white.png"

# 4. The plugin goes into SwiftBar's folder; a folder already chosen by the user is kept
# 4. Plugin vào thư mục của SwiftBar; thư mục người dùng đã chọn thì giữ nguyên
PLUGINS="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)"
if [ -z "$PLUGINS" ] || ! [ -d "$PLUGINS" ]; then
  PLUGINS="$HOME/Library/Application Support/AI Worker/SwiftBar"
  mkdir -p "$PLUGINS"
  defaults write com.ameba.SwiftBar PluginDirectory "$PLUGINS"
fi
cp "$HERE/ai-worker.1m.py" "$PLUGINS/ai-worker.1m.py"
chmod 755 "$PLUGINS/ai-worker.1m.py"

# 5. Start SwiftBar now and at every login
# 5. Mở SwiftBar ngay và mỗi lần đăng nhập
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.ai-worker.menubar</string>
<key>RunAtLoad</key><true/>
<key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-a</string><string>$APP</string></array>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"
open -a "$APP"
sleep 2
open -g "swiftbar://refreshallplugins" 2>/dev/null

echo
say "Installed. Click the new icon in the menu bar to see the pairing code," "Đã cài. Bấm vào biểu tượng mới trên thanh menu để xem mã ghép,"
say "then ask an admin to approve it on the Admin page." "rồi nhờ quản trị duyệt mã ở trang Quản trị."
pause
