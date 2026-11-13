#!/bin/bash
# Install the tools the coding and testing skills of AI Worker need, on macOS: Node, Playwright, Chrome DevTools. For people who write code.
# The skills themselves come with the plugin: install it first with INSTALL-Mac.command. Double-click this file to run it.
# Cài các công cụ mà skill viết code và kiểm thử của AI Worker cần, trên macOS: Node, Playwright, Chrome DevTools. Dành cho người viết code.
# Bản thân các skill đi kèm plugin: cài plugin trước bằng INSTALL-Mac.command. Bấm đúp file này để chạy.
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

INSTALL_DIR="$HOME/claude-plugins-ai-worker"
export PATH="$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
say "== Installing the tools for the coding and testing skills ==" "== Cài công cụ cho các skill viết code và kiểm thử =="
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
[ -d "$INSTALL_DIR/ai-worker" ] || {
  say "The AI Worker plugin is not installed yet: run INSTALL-Mac.command first, then this file." "Chưa cài plugin AI Worker: chạy INSTALL-Mac.command trước, rồi mới chạy file này."
  pause_close; exit 1
}
CLAUDE="$CLAUDE" bash install-deps.sh "$INSTALL_DIR/ai-worker" || true
echo
say "Done. Quit the Claude app completely (Cmd+Q) and open it again to use it." "Xong. Thoát hẳn app Claude (Cmd+Q) rồi mở lại để dùng."
pause_close
