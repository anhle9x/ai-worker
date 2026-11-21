#!/bin/bash
# Fetches AI Worker.msi built by GitHub (job windows-app, latest successful run) into server/menubar/AI-Worker.msi,
# which the server then hands out with its own address filled in. Needs gh, logged in. Checks the address placeholder is there exactly once.
# Lấy AI Worker.msi do GitHub dựng (job windows-app, lượt chạy đạt mới nhất) về server/menubar/AI-Worker.msi,
# để máy chủ phát kèm địa chỉ của nó. Cần lệnh gh đã đăng nhập. Kiểm chỗ giữ chỗ địa chỉ có đúng một lần.
# Usage: fetch-msi.sh [owner/repository [branch]]. By default the published repository, where Actions run for free; a fork passes its own.
# Cách dùng: fetch-msi.sh [chủ/repo [nhánh]]. Mặc định là repo phát hành, nơi Actions chạy miễn phí; bản fork truyền repo của mình.
set -euo pipefail
cd "$(dirname "$0")"
repo="${1:-anhle9x/ai-worker}"
branch="${2:-main}"
run=$(gh run list -R "$repo" --workflow test-install.yml --branch "$branch" --status success --limit 1 --json databaseId -q '.[0].databaseId')
[ -n "$run" ] || { echo "No successful GitHub run on $repo, branch $branch, yet"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
# a run whose Windows jobs were skipped (nothing they test changed) has no .msi: say so instead of failing later
# lượt chạy bỏ qua các việc Windows (không đổi thứ chúng kiểm) thì không có .msi: báo rõ thay vì hỏng ở bước sau
gh run download -R "$repo" "$run" -n ai-worker-msi -D "$tmp" ||
  { echo "Run $run of $repo has no ai-worker-msi: open the run, or start the workflow by hand and fetch again"; exit 1; }
count=$(LC_ALL=C grep -c -a -o "AIWORKER-SERVER-0123456789abcdef" "$tmp/AI Worker.msi" || true)
[ "$count" = "1" ] || { echo "The .msi does not hold the address placeholder exactly once ($count)"; exit 1; }
cp "$tmp/AI Worker.msi" ../AI-Worker.msi
echo "Fetched AI-Worker.msi from run $run of $repo, branch $branch ($(wc -c < ../AI-Worker.msi | tr -d ' ') bytes)"
