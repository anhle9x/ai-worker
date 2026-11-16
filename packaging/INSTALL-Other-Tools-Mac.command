#!/bin/bash
# Show Codex, Cursor and Gemini CLI on the AI Worker board, on macOS. Claude Code is not needed. Double-click this file to run it.
# To take it out again: open Terminal and run  bash ~/.local/share/ai-worker/connector/install.sh --uninstall
# Cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker, trên macOS. Không cần có Claude Code. Bấm đúp file này để chạy.
# Muốn gỡ: mở Terminal và chạy  bash ~/.local/share/ai-worker/connector/install.sh --uninstall
cd "$(dirname "$0")" || exit 1
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
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
bash ai-worker/connectors/install.sh "$@" || true
echo
PAUSE_MSG=$(
say "Press Enter to close..." "Nhấn Enter để đóng..."
)
read -r -p "$PAUSE_MSG" _
