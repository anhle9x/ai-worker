#!/bin/bash
# Show Codex, Cursor and Gemini CLI on the AI Worker board, on Ubuntu/Linux. Claude Code is not needed. Run: bash INSTALL-Other-Tools-Linux.sh
# To take it out again: bash ~/.local/share/ai-worker/connector/install.sh --uninstall
# Cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker, trên Ubuntu/Linux. Không cần có Claude Code. Chạy: bash INSTALL-Other-Tools-Linux.sh
# Muốn gỡ: bash ~/.local/share/ai-worker/connector/install.sh --uninstall
cd "$(dirname "$0")" || exit 1
# The helper files and the plugin sit in setup/, so only the installers show at the top of the zip
# File phụ và plugin nằm trong setup/, để ngoài cùng của zip chỉ còn các file cài
[ -d setup ] && cd setup
[ -f ./lang.sh ] || { echo "lang.sh is missing in the setup folder: unzip the whole zip file and run again. / Thiếu lang.sh trong thư mục setup: giải nén cả file zip rồi chạy lại."; exit 1; } # i18n-allow
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:$PATH"
bash ai-worker/connectors/install.sh "$@"
