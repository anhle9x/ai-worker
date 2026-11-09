#!/bin/bash
# Install the AI Worker technical pack on macOS. Double-click this file to run it.
# Cài gói kỹ thuật AI Worker trên macOS. Bấm đúp file này để chạy.
set -e
cd "$(dirname "$0")"
[ -f ./lang.sh ] || { echo "lang.sh is missing next to this file: unzip the whole pack and run again. / Thiếu lang.sh cạnh file này: giải nén cả gói rồi chạy lại."; read -r -p "Press Enter / Nhấn Enter..." _; exit 1; } # i18n-allow
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

[ -d ai-worker-dev ] && [ -d .claude-plugin ] || {
  say "Cannot find the ai-worker-dev folder next to the installer: unzip the whole pack and run again." "Không thấy thư mục ai-worker-dev cạnh file cài: giải nén cả gói rồi chạy lại."
  pause_close; exit 1
}
INSTALL_DIR="$HOME/claude-plugins-ai-worker-dev"
export PATH="$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
say "== Installing the AI Worker technical pack ==" "== Cài gói kỹ thuật AI Worker =="
find_claude() {
  if command -v claude >/dev/null 2>&1; then echo claude; return 0; fi
  ls -td "$HOME/Library/Application Support/Claude/claude-code/"*/*/claude.app/Contents/MacOS/claude 2>/dev/null | head -1
}
CLAUDE=$(find_claude)
if [ -z "$CLAUDE" ]; then
  say "Claude Code was not found. Open the Claude app, sign in, click the Code tab once, then run this file again." "Chưa tìm thấy Claude Code. Mở app Claude, đăng nhập, bấm sang tab Code một lần rồi chạy lại file này."
  pause_close
  exit 1
fi
say "Copying the plugin to $INSTALL_DIR ..." "Chép plugin vào $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -R .claude-plugin ai-worker-dev "$INSTALL_DIR/"
"$CLAUDE" plugin marketplace add "$INSTALL_DIR" || "$CLAUDE" plugin marketplace update ai-worker-dev
if ! "$CLAUDE" plugin install ai-worker-dev@ai-worker-dev; then
  say "The install did not succeed. Take a screenshot of this window and send it to your admin." "Cài chưa thành công. Chụp màn hình cửa sổ này gửi người quản trị."
  pause_close
  exit 1
fi
CLAUDE="$CLAUDE" bash install-deps.sh "$INSTALL_DIR/ai-worker-dev" || true
echo
say "Done. Quit the Claude app completely (Cmd+Q) and open it again to use it." "Xong. Thoát hẳn app Claude (Cmd+Q) rồi mở lại để dùng."
pause_close
