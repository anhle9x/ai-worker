#!/bin/bash
# Install AI Worker Office for Claude Code on Ubuntu/Linux. Run: bash INSTALL-Linux.sh
# Cài Văn phòng AI Worker cho Claude Code trên Ubuntu/Linux. Chạy: bash INSTALL-Linux.sh
set -e
cd "$(dirname "$0")"
# The helper files and the plugin sit in setup/, so only the installers show at the top of the zip
# File phụ và plugin nằm trong setup/, để ngoài cùng của zip chỉ còn các file cài
[ -d setup ] && cd setup
[ -f ./lang.sh ] || { echo "lang.sh is missing in the setup folder: unzip the whole zip file and run again. / Thiếu lang.sh trong thư mục setup: giải nén cả file zip rồi chạy lại."; exit 1; } # i18n-allow
# Language: AI_WORKER_LANG (en or vi) wins, else the system language (LANG), else English.
# Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ hệ thống (LANG), không có nữa thì tiếng Anh.
. ./lang.sh

PAUSE_MSG=$(
say "Press Enter to close..." "Nhấn Enter để đóng..."
)
pause_close() { read -r -p "$PAUSE_MSG" _ || true; }

[ -d ai-worker ] && [ -d .claude-plugin ] || {
  say "Cannot find the ai-worker folder in the setup folder: unzip the whole zip file and run again." "Không thấy thư mục ai-worker trong thư mục setup: giải nén cả file zip rồi chạy lại."
  pause_close; exit 1
}

INSTALL_DIR="$HOME/claude-plugins-ai-worker"
export PATH="$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/usr/local/bin:$PATH"

say "== Installing AI Worker Office ==" "== Cài Văn phòng AI Worker =="
if ! command -v claude >/dev/null 2>&1; then
  say "Claude Code is not installed on this computer (the 'claude' command was not found)." "Máy chưa cài Claude Code (không tìm thấy lệnh 'claude')."
  say "Install it following https://claude.com/claude-code, sign in (type claude), then run this file again." "Cài theo hướng dẫn ở https://claude.com/claude-code, đăng nhập (gõ claude), rồi chạy lại file này."
  pause_close
  exit 1
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

CLAUDE=claude
ACCOUNT=$(signed_in_email)
if [ -n "$ACCOUNT" ]; then
  say "Claude is signed in: $ACCOUNT" "Claude đã đăng nhập: $ACCOUNT"
else
  echo
  say "Claude Code is not signed in." "Claude Code chưa đăng nhập."
  LOGIN_MSG=$(
  say "Open the browser to sign in now? (Enter = yes, type n = later): " "Mở trình duyệt để đăng nhập ngay? (Enter = có, gõ n = để sau): "
  )
  answer=""; read -r -p "$LOGIN_MSG" answer || true
  if [ "$answer" != n ] && [ "$answer" != N ]; then
    if ! claude auth login --claudeai; then
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

say "Registering and installing the plugin ..." "Đăng ký và cài plugin ..."
claude plugin marketplace add "$INSTALL_DIR" || claude plugin marketplace update ai-worker
claude plugin install ai-worker@ai-worker

if ! command -v xdg-open >/dev/null 2>&1; then
  say "Note: xdg-open is missing, so /office cannot open the browser by itself." "Lưu ý: chưa có xdg-open nên /office không tự mở trình duyệt được."
  say "Install it with: sudo apt install xdg-utils" "Cài bằng: sudo apt install xdg-utils"
fi

# Helper AI assistants: Codex (default), Gemma by computer size, Gemini optional
# Nhân viên AI phụ: Codex (mặc định), Gemma theo máy, Gemini tuỳ chọn
[ -z "$AI_WORKER_SKIP_HELPERS" ] && [ -f helpers.sh ] && { bash helpers.sh || true; }

echo
say "Done. Open (or reopen) Claude Code, then type /office to see the office." "Xong. Mở (hoặc mở lại) Claude Code, rồi gõ /office để xem văn phòng."
say "If Claude Code is already open: type /reload-plugins." "Nếu Claude Code đang mở: gõ /reload-plugins."
pause_close
