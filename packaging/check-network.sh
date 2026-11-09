#!/bin/bash
# Check whether this computer can reach the company server. It sends no code or numbers; a failure does not break the install.
# Thử xem máy này có tới được máy chủ công ty không. Không gửi mã hay số liệu gì; lỗi cũng không làm hỏng việc cài.
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/lang.sh" ] || { echo "lang.sh is missing next to check-network.sh. / Thiếu lang.sh cạnh check-network.sh."; exit 1; } # i18n-allow
. "$HERE/lang.sh"
F=ai-worker/web/company.json
[ -f "$F" ] || exit 0
URL=$(sed -n 's/.*"webhook": *"\([^"]*\)".*/\1/p' "$F" | head -1)
[ -n "$URL" ] || exit 0
CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST "${URL%/}/ingest" 2>/dev/null)
case "$CODE" in
  401)
    say "Connection test done: this computer can reach the company server." "Đã thử kết nối: máy này tới được máy chủ công ty."
    ;;
  403)
    echo
    say "NOTE: the server is blocking this network, so this computer's numbers are NOT reaching the company dashboard yet." "LƯU Ý: máy chủ đang chặn mạng này, số liệu máy này CHƯA lên được bảng tổng."
    say "Take a screenshot of this line and send it to your IT team. The plugin still works normally on this computer." "Chụp dòng này gửi phòng IT. Plugin vẫn dùng bình thường trên máy."
    ;;
  *)
    echo
    say "NOTE: could not reach the company server (code ${CODE:-000}), so this computer's numbers are not on the dashboard yet." "LƯU Ý: chưa tới được máy chủ công ty (mã ${CODE:-000}), số liệu máy này chưa lên bảng tổng."
    say "This may be the network right now. If it keeps happening, take a screenshot of this line and send it to your IT team." "Có thể do mạng lúc này. Nếu kéo dài, chụp dòng này gửi phòng IT."
    ;;
esac
