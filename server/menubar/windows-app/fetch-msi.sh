#!/bin/bash
# Fetches AI Worker.msi built by GitHub (job windows-app, latest successful run of the current branch) into server/menubar/AI-Worker.msi,
# which the server then hands out with its own address filled in. Needs gh, logged in. Checks the address placeholder is there exactly once.
# Lấy AI Worker.msi do GitHub dựng (job windows-app, lượt chạy đạt mới nhất của nhánh đang đứng) về server/menubar/AI-Worker.msi,
# để máy chủ phát kèm địa chỉ của nó. Cần lệnh gh đã đăng nhập. Kiểm chỗ giữ chỗ địa chỉ có đúng một lần.
set -euo pipefail
cd "$(dirname "$0")"
branch=$(git rev-parse --abbrev-ref HEAD)
run=$(gh run list --branch "$branch" --status success --limit 1 --json databaseId -q '.[0].databaseId')
[ -n "$run" ] || { echo "No successful GitHub run on branch $branch yet"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
gh run download "$run" -n ai-worker-msi -D "$tmp"
count=$(LC_ALL=C grep -c -a -o "AIWORKER-SERVER-0123456789abcdef" "$tmp/AI Worker.msi" || true)
[ "$count" = "1" ] || { echo "The .msi does not hold the address placeholder exactly once ($count)"; exit 1; }
cp "$tmp/AI Worker.msi" ../AI-Worker.msi
echo "Fetched AI-Worker.msi from run $run of branch $branch ($(wc -c < ../AI-Worker.msi | tr -d ' ') bytes)"
