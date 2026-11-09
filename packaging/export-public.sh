#!/usr/bin/env bash
# One-way export of one git ref into a clean folder, without history, for the public repository. Never pushes or commits.
# Xuất một chiều một nhánh của git ra thư mục sạch, không kèm lịch sử, cho repo công khai. Không bao giờ đẩy hay commit.
# Usage: export-public.sh <ref> <destination folder>. The owner then reviews and commits in the destination by hand.
# Cách dùng: export-public.sh <nhánh> <thư mục đích>. Sau đó chủ dự án tự xem lại và commit ở thư mục đích.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: export-public.sh <ref> <destination folder>" >&2
  exit 2
fi
REF="$1"
DEST="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
DENY_FILE="${AI_WORKER_DENY_FILE:-$HOME/.config/ai-worker/deny-words.txt}"

# An export without the private word list could leak, so it is refused.
# Xuất mà không có danh sách từ riêng thì có thể lộ, nên bị từ chối.
if ! tr -d '\r' < "$DENY_FILE" 2>/dev/null | grep -qvE '^[[:space:]]*(#|$)'; then
  echo "No private word list at $DENY_FILE: export refused." >&2
  exit 1
fi

# Prints the real path of a folder that may not exist yet, and creates nothing.
# In đường dẫn thật của một thư mục có thể chưa tồn tại, và không tạo gì cả.
real_path() {
  local path="$1" rest=""
  while [ ! -d "$path" ]; do
    rest="/$(basename "$path")$rest"
    path="$(dirname "$path")"
  done
  case "$rest/" in
    */../*) echo "The destination must not use .. through a folder that does not exist." >&2; return 1 ;;
  esac
  printf '%s%s\n' "$(cd "$path" && pwd -P)" "$rest"
}

# This script deletes files in the destination, so it must be a separate folder and hold only an earlier export.
# Script này xoá file ở thư mục đích, nên đích phải là thư mục riêng và chỉ chứa bản xuất trước đó.
DEST="$(real_path "$DEST")"
REAL_REPO="$(cd "$REPO" && pwd -P)"
case "$DEST/" in
  "$REAL_REPO"/*) echo "The destination must be outside this repository." >&2; exit 1 ;;
esac
case "$REAL_REPO/" in
  "$DEST"/*) echo "The destination must not contain this repository." >&2; exit 1 ;;
esac
if [ "$DEST" = "/" ] || [ "$DEST" = "$(cd "$HOME" && pwd -P)" ]; then
  echo "The destination must be its own folder." >&2
  exit 1
fi
if [ -d "$DEST" ] && [ -n "$(find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -print -quit)" ] && [ ! -f "$DEST/packaging/export-public.sh" ]; then
  echo "The destination has other files and is not an earlier export: nothing was changed." >&2
  exit 1
fi

# Export and check in a temporary folder first: nothing reaches the destination unless it is clean.
# Xuất và kiểm trong thư mục tạm trước: chưa sạch thì không có gì tới thư mục đích.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$REPO" archive --format=tar "$REF" | tar -x -C "$TMP"
bash "$HERE/check-clean.sh" --all "$TMP"

# Keep the destination's own .git; files removed from the ref are removed from the destination.
# Giữ .git của thư mục đích; file đã bỏ khỏi nhánh cũng bị bỏ khỏi thư mục đích.
mkdir -p "$DEST"
rsync -a --delete --exclude .git "$TMP/" "$DEST/"
echo "Exported $REF to $DEST. Review it, then commit there yourself."
