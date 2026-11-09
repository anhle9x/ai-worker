#!/bin/bash
# Install AI Worker Office for Claude Code on macOS. Double-click this file to run it.
# Cài Văn phòng AI Worker cho Claude Code trên macOS. Bấm đúp file này để chạy.
set -e
cd "$(dirname "$0")"
# The helper files and the plugin sit in setup/, so only the installers show at the top of the zip
# File phụ và plugin nằm trong setup/, để ngoài cùng của zip chỉ còn các file cài
[ -d setup ] && cd setup
[ -f ./lang.sh ] || { echo "lang.sh is missing in the setup folder: unzip the whole zip file and run again. / Thiếu lang.sh trong thư mục setup: giải nén cả file zip rồi chạy lại."; read -r -p "Press Enter / Nhấn Enter..." _; exit 1; } # i18n-allow
# Language: AI_WORKER_LANG (en or vi) wins, else the macOS language, else English. LANG may not show the macOS language, so ask macOS first.
# Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ macOS, không có nữa thì tiếng Anh. LANG có thể không phản ánh ngôn ngữ macOS nên hỏi macOS trước.
if [ -z "${AI_WORKER_LANG:-}" ]; then
  MAC_LANG=$(defaults read -g AppleLanguages 2>/dev/null | sed -n 2p | tr -d ' ",' || true)
  [ -z "$MAC_LANG" ] || export AI_WORKER_LANG="$MAC_LANG"
fi
. ./lang.sh

PAUSE_MSG=$(
say "Press Enter to close..." "Nhấn Enter để đóng..."
)
pause_close() { read -r -p "$PAUSE_MSG" _; }

[ -d ai-worker ] && [ -d .claude-plugin ] || {
  say "Cannot find the ai-worker folder in the setup folder: unzip the whole zip file and run again." "Không thấy thư mục ai-worker trong thư mục setup: giải nén cả file zip rồi chạy lại."
  pause_close; exit 1
}

INSTALL_DIR="$HOME/claude-plugins-ai-worker"
export PATH="$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

say "== Installing AI Worker Office ==" "== Cài Văn phòng AI Worker =="
# The claude command: installed on its own, or bundled with the Claude Desktop app (it appears after the Code tab is opened once; take the newest)
# Lệnh claude: cài riêng, hoặc bản app Claude Desktop kèm sẵn (có sau lần đầu mở tab Code; lấy bản mới nhất)
find_claude() {
  if command -v claude >/dev/null 2>&1; then echo claude; return 0; fi
  ls -td "$HOME/Library/Application Support/Claude/claude-code/"*/*/claude.app/Contents/MacOS/claude 2>/dev/null | head -1
}
CLAUDE=$(find_claude)
HAS_APP=""
[ -d /Applications/Claude.app ] || [ -d "$HOME/Applications/Claude.app" ] && HAS_APP=1
if [ -z "$CLAUDE" ] && [ -z "$HAS_APP" ]; then
  # Claude Desktop is missing: offer to install it. Either way the user signs in first, then runs this file again.
  # Thiếu Claude Desktop: đề nghị cài. Dù cách nào thì người dùng cũng đăng nhập trước, rồi chạy lại file này.
  if [ -f ./install-desktop.sh ]; then
    # "|| ..." keeps set -e from closing the window before the user can read the message.
    # "|| ..." giữ set -e không đóng cửa sổ trước khi người dùng đọc được thông báo.
    DESKTOP_RESULT=0
    bash ./install-desktop.sh || DESKTOP_RESULT=$?
  else
    say "Download Claude Desktop at https://claude.com/download, sign in, open the Code tab once, then run this file again." "Tải Claude Desktop tại https://claude.com/download, đăng nhập, mở tab Code một lần, rồi chạy lại file này."
    DESKTOP_RESULT=1
  fi
  pause_close
  exit "$DESKTOP_RESULT"
fi

# Email of the signed-in account: ask the claude command, else read Claude's config file; empty = not signed in
# Email tài khoản đang đăng nhập: hỏi lệnh claude, không được thì đọc file cấu hình của Claude; rỗng = chưa đăng nhập
signed_in_email() {
  local out=""
  if [ -n "$CLAUDE" ]; then
    out=$("$CLAUDE" auth status --json 2>/dev/null) || true
    if printf '%s' "$out" | grep -q '"loggedIn": *true'; then
      printf '%s' "$out" | sed -n 's/.*"email": *"\([^"]*@[^"]*\)".*/\1/p' | head -1 | tr '[:upper:]' '[:lower:]'
      return 0
    fi
    # The claude command says clearly it is not signed in: do not trust the old file
    # Lệnh claude nói rõ là chưa đăng nhập: không tin file cũ
    printf '%s' "$out" | grep -q '"loggedIn": *false' && return 0
  fi
  sed -n 's/.*"emailAddress": *"\([^"]*@[^"]*\)".*/\1/p' "${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json" 2>/dev/null | head -1 | tr '[:upper:]' '[:lower:]'
}

# Sign in: we cannot sign in to the Claude app for the user, so open the app, let them sign in, then wait for confirmation
# Đăng nhập: không đăng nhập hộ được app Claude, nên mở app cho nhân viên tự đăng nhập rồi chờ xác nhận
ACCOUNT=$(signed_in_email)
if [ -n "$ACCOUNT" ]; then
  say "Claude is signed in: $ACCOUNT" "Claude đã đăng nhập: $ACCOUNT"
elif [ -n "$HAS_APP" ]; then
  echo
  say "Claude does not look signed in on this computer. Opening the Claude app..." "Chưa thấy Claude đăng nhập trên máy này. Đang mở app Claude..."
  open -a Claude 2>/dev/null || open "claude://" 2>/dev/null || true
  say "In the Claude app: if you see the sign-in screen, sign in with the account your company gave you," "Trong app Claude: nếu thấy màn hình đăng nhập thì đăng nhập bằng tài khoản công ty cấp,"
  say "then click the Code tab once (so the app downloads Claude Code to this computer)." "rồi bấm sang tab Code một lần (để app tải phần Claude Code về máy)."
  CONTINUE_MSG=$(
  say "When done, press Enter here to continue installing..." "Xong thì nhấn Enter ở đây để cài tiếp..."
  )
  read -r -p "$CONTINUE_MSG" _ || true
  [ -n "$CLAUDE" ] || CLAUDE=$(find_claude)
  ACCOUNT=$(signed_in_email)
  if [ -n "$ACCOUNT" ]; then
    say "Claude is signed in: $ACCOUNT" "Claude đã đăng nhập: $ACCOUNT"
  fi
else
  echo
  say "Claude Code is not signed in." "Claude Code chưa đăng nhập."
  LOGIN_MSG=$(
  say "Open the browser to sign in now? (Enter = yes, type n = later): " "Mở trình duyệt để đăng nhập ngay? (Enter = có, gõ n = để sau): "
  )
  answer=""; read -r -p "$LOGIN_MSG" answer || true
  if [ "$answer" != n ] && [ "$answer" != N ]; then
    if ! "$CLAUDE" auth login --claudeai; then
      say "Sign-in not finished; you can sign in later." "Đăng nhập chưa xong; đăng nhập sau cũng được."
    fi
    ACCOUNT=$(signed_in_email)
    if [ -n "$ACCOUNT" ]; then
      say "Claude is signed in: $ACCOUNT" "Claude đã đăng nhập: $ACCOUNT"
    fi
  fi
fi

USER_FILE="$HOME/.local/share/ai-worker/user.json"
# Ask for a name only when user.json has no name yet (it may hold just the language from an earlier install)
# Chỉ hỏi tên khi user.json chưa có tên (file có thể chỉ có ngôn ngữ từ lần cài trước)
if [ -f ASK-NAME ] && ! grep -q '"name"' "$USER_FILE" 2>/dev/null; then
  echo
  say "This package sends usage numbers (sessions, tokens, cost; NOT chat content or file names)" "Gói này gửi số liệu sử dụng (số phiên, token, chi phí; KHÔNG có nội dung chat hay tên file)"
  say "to the company dashboard." "lên bảng tổng của công ty."
  NAME_MSG=$(
  say "Your full name: " "Họ tên của bạn: "
  )
  name=""; while [ -z "${name//[[:space:]]/}" ]; do read -r -p "$NAME_MSG" name || exit 1; done
  name=$(printf '%s' "$name" | tr '[:cntrl:]' ' ' | tr -d '"\\')
  # Email: of the signed-in account; ask only when still not signed in (sign in later, the office picks it up again)
  # Email: của tài khoản đang đăng nhập; chỉ hỏi khi vẫn chưa đăng nhập (đăng nhập sau, văn phòng tự nhận lại)
  account=$ACCOUNT
  if [ -z "$account" ]; then
    say "Could not get the email of your Claude account. Signing in later is fine: the office will pick it up." "Chưa lấy được email tài khoản Claude. Đăng nhập sau cũng được: văn phòng sẽ tự nhận."
    EMAIL_MSG=$(
    say "Claude account email (Enter to skip): " "Email tài khoản Claude (Enter để bỏ qua): "
    )
    while :; do
      read -r -p "$EMAIL_MSG" account || exit 1
      account=$(printf '%s' "$account" | tr -d '[:space:]"\\' | tr '[:upper:]' '[:lower:]')
      [ -z "$account" ] && break
      [[ "$account" =~ ^[^@]+@[^@]+\.[^@]+$ ]] && break
      say "That email does not look right (e.g. name@example.com). Type it again or press Enter to skip." "Email chưa đúng dạng (vd: ten@example.com), nhập lại hoặc Enter để bỏ qua."
    done
  fi
  mkdir -p "$(dirname "$USER_FILE")"
  printf '{"name": "%s", "account": "%s"}\n' "$name" "$account" > "$USER_FILE"
  say "Saved. You can edit it later at: $USER_FILE" "Đã lưu. Sửa sau ở: $USER_FILE"
fi

# Save the language in user.json (the plugin reads it); other fields stay as they are
# Ghi ngôn ngữ vào user.json (plugin đọc trường này); các trường khác giữ nguyên
mkdir -p "$(dirname "$USER_FILE")"
if [ -s "$USER_FILE" ]; then
  L="$AI_WORKER_LANG" perl -0pi -e 's/,\s*"language"\s*:\s*"[^"]*"//; s/"language"\s*:\s*"[^"]*"\s*,?\s*//; if (/^\s*\{\s*\}\s*$/) { $_ = "{\"language\": \"$ENV{L}\"}\n" } else { s/\s*\}\s*$/, "language": "$ENV{L}"}\n/ }' "$USER_FILE" || true
else
  printf '{"language": "%s"}\n' "$AI_WORKER_LANG" > "$USER_FILE"
fi

say "Copying the plugin to $INSTALL_DIR ..." "Chép plugin vào $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -R .claude-plugin ai-worker "$INSTALL_DIR/"

# Company package: check whether this computer can reach the server
# Gói công ty: thử xem máy này có tới được máy chủ không
[ -f ASK-NAME ] && [ -f check-network.sh ] && { bash check-network.sh || true; }

if [ -z "$CLAUDE" ]; then
  # The Claude app is here but not the claude command: install with two commands typed in the Code tab, each one copied for the user
  # Có app Claude nhưng chưa có lệnh claude: cài bằng hai lệnh gõ trong tab Code, chép sẵn từng lệnh
  echo
  say "This computer has the Claude app but the 'claude' command was not found. Install inside the app, in two steps:" "Máy có app Claude nhưng chưa tìm thấy lệnh 'claude'. Cài trong app, hai bước:"
  say "Open the Claude app > Code tab (start a new session if needed)." "Mở app Claude > tab Code (mở phiên mới nếu cần)."
  CMD="/plugin marketplace add $INSTALL_DIR"
  case "$INSTALL_DIR" in *" "*) CMD="/plugin marketplace add \"$INSTALL_DIR\"" ;; esac
  printf '%s' "$CMD" | pbcopy
  say "  1. Command copied:  $CMD" "  1. Đã chép lệnh:  $CMD"
  say "     Paste it into the chat box (Cmd+V), press Enter, and wait until it says it is done." "     Dán vào khung chat (Cmd+V) rồi Enter, chờ báo xong."
  SECOND_MSG=$(
  say "     When done, press Enter here to copy the second command..." "     Xong thì nhấn Enter ở đây để chép lệnh thứ hai..."
  )
  read -r -p "$SECOND_MSG" _
  printf '%s' "/plugin install ai-worker@ai-worker" | pbcopy
  say "  2. Command copied:  /plugin install ai-worker@ai-worker" "  2. Đã chép lệnh:  /plugin install ai-worker@ai-worker"
  say "     Paste it into the chat box and press Enter. Then type /reload-plugins, then /office." "     Dán vào khung chat rồi Enter. Sau đó gõ /reload-plugins, rồi /office."
  [ -z "$AI_WORKER_SKIP_HELPERS" ] && [ -f helpers.sh ] && { bash helpers.sh || true; }
  pause_close
  exit 0
fi

say "Registering and installing the plugin ..." "Đăng ký và cài plugin ..."
"$CLAUDE" plugin marketplace add "$INSTALL_DIR" || "$CLAUDE" plugin marketplace update ai-worker
if ! "$CLAUDE" plugin install ai-worker@ai-worker; then
  say "The install did not succeed. Take a screenshot of this window and send it to your admin." "Cài chưa thành công. Chụp màn hình cửa sổ này gửi người quản trị."
  pause_close
  exit 1
fi

# Helper AI assistants: Codex (default), Gemma by computer size, Gemini optional
# Nhân viên AI phụ: Codex (mặc định), Gemma theo máy, Gemini tuỳ chọn
[ -z "$AI_WORKER_SKIP_HELPERS" ] && [ -f helpers.sh ] && { bash helpers.sh || true; }

# Open the office page now: the plugin copies it at the first session, so put the same files there first
# Mở trang văn phòng ngay: plugin chỉ chép trang ở phiên đầu tiên, nên chép sẵn đúng các file đó trước
WEB_DIR="$HOME/.local/share/ai-worker"
if [ -z "$AI_WORKER_SKIP_HELPERS" ] && mkdir -p "$WEB_DIR" 2>/dev/null; then
  for f in index.html i18n.js index.vi.js ops.vi.js ops.js ops.css ops3d.js three.js three.LICENSE; do
    cp "$INSTALL_DIR/ai-worker/web/$f" "$WEB_DIR/" 2>/dev/null || true
  done
  [ -f "$WEB_DIR/config.js" ] || cp "$INSTALL_DIR/ai-worker/web/config.js" "$WEB_DIR/" 2>/dev/null || true
  [ -f "$WEB_DIR/index.html" ] && open "$WEB_DIR/index.html" 2>/dev/null &&
    say "The office page is open in the browser; your sessions show up there once Claude Code is running." "Đã mở trang văn phòng trên trình duyệt; các phiên sẽ hiện ở đó khi Claude Code chạy." || true
fi

echo
say "Done. Open (or reopen) Claude Code (the Code tab in the Claude app), then type /office to see the office." "Xong. Mở (hoặc mở lại) Claude Code (tab Code trong app Claude), rồi gõ /office để xem văn phòng."
say "If it is already open: type /reload-plugins." "Nếu đang mở: gõ /reload-plugins."
pause_close
