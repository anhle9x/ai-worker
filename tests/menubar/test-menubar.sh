#!/bin/bash
# The menu bar script against a fake server: first round shows a pairing code, the next shows 2 people waiting.
# Script thanh menu với máy chủ giả: lượt đầu hiện mã ghép, lượt sau hiện 2 người đang chờ.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
# MENUBAR_TEST_PORT picks another port when 8792 is taken
# MENUBAR_TEST_PORT chọn cổng khác khi cổng 8792 đang bận
PORT="${MENUBAR_TEST_PORT:-8792}"
export MENUBAR_TEST_HOSTILE="$TMP/hostile"
export MENUBAR_TEST_BLOCKED="$TMP/blocked"
python3 "$ROOT/tests/menubar/fake_server.py" "$PORT" > "$TMP/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 1 30); do grep -q ready "$TMP/server.log" && break; sleep 0.5; done
export AI_WORKER_MENUBAR_DIR="$TMP/cfg"
mkdir -p "$AI_WORKER_MENUBAR_DIR"
echo "{\"server\": \"http://127.0.0.1:$PORT\", \"lang\": \"en\"}" > "$AI_WORKER_MENUBAR_DIR/menubar.json"
fail=0
check() { if [ "$1" = ok ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }
first="$(python3 "$ROOT/server/menubar/ai-worker.1m.py")"
echo "$first" | grep -Eq "Pairing code: [0-9]{4}-[0-9]{4}|/mini/pair#c=[0-9]{8}" && check ok "first round shows a pairing code" || check no "first round shows a pairing code"
sleep 1
second="$(python3 "$ROOT/server/menubar/ai-worker.1m.py")"
echo "$second" | head -1 | grep -q "^2 |" && check ok "second round shows 2 waiting" || check no "second round shows 2 waiting: $(echo "$second" | head -1 | cut -c1-60)"
echo "$second" | grep -q "/mini?h=" && check ok "the window link carries a one-time code" || check no "the window link carries a one-time code"
mode="$(stat -c %a "$AI_WORKER_MENUBAR_DIR/menubar-session" 2>/dev/null || stat -f %Lp "$AI_WORKER_MENUBAR_DIR/menubar-session")"
[ "$mode" = 600 ] && check ok "the session file is private" || check no "the session file is private ($mode)"
# a hostile server's window code never reaches the menu line (SwiftBar) or the command (Argos): the window link falls back to the board
# mã mở khung của máy chủ xấu không bao giờ vào dòng menu (SwiftBar) hay câu lệnh (Argos): đường mở khung quay về bảng
touch "$MENUBAR_TEST_HOSTILE"
for platform in darwin linux; do
  out="$(python3 -c 'import runpy, sys, urllib.request; sys.platform = sys.argv[1]; sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name="__main__")' "$platform" "$ROOT/server/menubar/ai-worker.1m.py")"
  if echo "$out" | grep -q "pwned\|/usr/bin/touch\|mini?h="; then check no "hostile window code is dropped ($platform)"; else check ok "hostile window code is dropped ($platform)"; fi
  echo "$out" | grep -q "127.0.0.1:$PORT/board" && check ok "the window opens the board instead ($platform)" || check no "the window opens the board instead ($platform)"
done
[ ! -e "$MENUBAR_TEST_HOSTILE.pwned" ] && check ok "nothing ran from the hostile code" || check no "nothing ran from the hostile code"
rm -f "$MENUBAR_TEST_HOSTILE"
# a network the proxy does not allow: the plain 403 page is not the board saying the session is gone, so it is kept and the menu says why
# mạng proxy không cho phép: trang 403 chữ thường không phải bảng nói phiên đã mất, nên phiên được giữ và menu nói lý do
touch "$MENUBAR_TEST_BLOCKED"
blocked="$(python3 "$ROOT/server/menubar/ai-worker.1m.py")"
echo "$blocked" | grep -q "This network may not reach the board" && check ok "a proxy's 403 says the network may not reach the board" || check no "a proxy's 403 says the network may not reach the board"
[ -s "$AI_WORKER_MENUBAR_DIR/menubar-session" ] && check ok "a proxy's 403 keeps the session" || check no "a proxy's 403 keeps the session"
rm -f "$MENUBAR_TEST_BLOCKED"
python3 "$ROOT/server/menubar/ai-worker.1m.py" | head -1 | grep -q "^2 |" && check ok "back on an allowed network, no pairing again" || check no "back on an allowed network, no pairing again"
# http is only for this very computer: a name that merely starts with localhost is refused
# http chỉ dành cho chính máy này: tên chỉ bắt đầu bằng localhost bị từ chối
echo '{"server": "http://localhost.evil.example.com", "lang": "en"}' > "$AI_WORKER_MENUBAR_DIR/menubar.json"
python3 "$ROOT/server/menubar/ai-worker.1m.py" | grep -q "Not set up" && check ok "http to another host is refused" || check no "http to another host is refused"
exit $fail
