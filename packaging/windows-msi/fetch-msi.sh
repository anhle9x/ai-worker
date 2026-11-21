#!/bin/bash
# Fetches AI Worker plugin.msi built by GitHub (job windows-app, latest successful run of the current branch) into server/menubar/AI-Worker-Plugin.msi,
# which the server then hands out to admins with its address, send code and update keys filled in. Needs gh, logged in.
# Lấy AI Worker plugin.msi do GitHub dựng (job windows-app, lượt chạy đạt mới nhất của nhánh đang đứng) về server/menubar/AI-Worker-Plugin.msi,
# để máy chủ phát cho quản trị kèm địa chỉ, mã gửi và khoá cập nhật của nó. Cần lệnh gh đã đăng nhập.
# The .msi carries the plugin of the version it was built from: fetch it again after each release, then copy server/ to the server as usual.
# Gói .msi mang plugin của phiên bản lúc dựng: lấy lại sau mỗi lần phát hành, rồi chép server/ lên máy chủ như thường lệ.
set -euo pipefail
cd "$(dirname "$0")"
branch=$(git rev-parse --abbrev-ref HEAD)
run=$(gh run list --branch "$branch" --status success --limit 1 --json databaseId -q '.[0].databaseId')
[ -n "$run" ] || { echo "No successful GitHub run on branch $branch yet"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
gh run download "$run" -n ai-worker-plugin-msi -D "$tmp"
# the same placeholder as build-msi.ps1 and server/board/packages.py, exactly once
# đúng chuỗi giữ chỗ của build-msi.ps1 và server/board/packages.py, đúng một lần
placeholder="AIWORKER-COMPANY-$(printf '0%.0s' $(seq 1 2031))"
count=$(LC_ALL=C grep -c -a -o -F "$placeholder" "$tmp/AI Worker plugin.msi" || true)
[ "$count" = "1" ] || { echo "The .msi does not hold the company placeholder exactly once ($count)"; exit 1; }
cp "$tmp/AI Worker plugin.msi" ../../server/menubar/AI-Worker-Plugin.msi
echo "Fetched AI-Worker-Plugin.msi from run $run of branch $branch ($(wc -c < ../../server/menubar/AI-Worker-Plugin.msi | tr -d ' ') bytes)"
