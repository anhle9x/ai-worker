#!/bin/bash
# The Ubuntu .deb on a real Ubuntu: apt installs it with its libraries, the icon program runs against a fake server, apt removes it cleanly.
# Gói .deb Ubuntu trên Ubuntu thật: apt cài cùng thư viện cần thiết, chương trình biểu tượng chạy với máy chủ giả, apt gỡ sạch.
# Needs sudo (GitHub's Ubuntu runner has it). There is no screen, so only --once runs, not the icon itself.
# Cần sudo (máy Ubuntu của GitHub có sẵn). Không có màn hình nên chỉ chạy --once, không hiện biểu tượng thật.
set -u
# every step has a time limit: a slow mirror or a held apt lock fails the test instead of hanging it
# mỗi bước có giới hạn thời gian: máy chủ gói chậm hay kẹt khoá apt thì báo FAIL, không treo cả bài thử
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
fail=0
check() { if [ "$1" = ok ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }

python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from board import packages; open(sys.argv[2], "wb").write(packages.menubar_deb("http://127.0.0.1:8794/"))' \
  "$ROOT/server" "$TMP/ai-worker-menubar.deb"
dpkg-deb --info "$TMP/ai-worker-menubar.deb" > /dev/null && check ok "dpkg-deb reads the package" || check no "dpkg-deb reads the package"
timeout 300 sudo apt-get update -qq -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 -o Acquire::http::Timeout=30 > /dev/null
timeout 600 sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 -o Acquire::http::Timeout=30 --no-install-recommends "$TMP/ai-worker-menubar.deb" > "$TMP/apt.log" 2>&1 \
  && check ok "apt installs it with its libraries" || { check no "apt installs it with its libraries"; tail -20 "$TMP/apt.log"; }
[ -x /usr/bin/ai-worker-menubar ] && check ok "the program is on the PATH" || check no "the program is on the PATH"
[ -f /etc/xdg/autostart/ai-worker-menubar.desktop ] && check ok "it starts at login" || check no "it starts at login"
grep -q '^Icon=ai-worker-menubar$' /usr/share/applications/ai-worker-menubar.desktop && [ -f /usr/share/pixmaps/ai-worker-menubar.png ] \
  && check ok "the app list shows its own logo" || check no "the app list shows its own logo"
python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("AyatanaAppIndicator3", "0.1"); from gi.repository import AyatanaAppIndicator3' 2>/dev/null \
  && check ok "the AppIndicator library loads" || check no "the AppIndicator library loads"
python3 -c 'import gi; gi.require_version("WebKit2", "4.1"); from gi.repository import WebKit2' 2>/dev/null \
  && check ok "the web view library for the small window loads" || check no "the web view library for the small window loads"

python3 "$ROOT/tests/menubar/fake_server.py" 8794 > "$TMP/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 1 30); do grep -q ready "$TMP/server.log" && break; sleep 0.5; done
export HOME="$TMP/home"
mkdir -p "$HOME"
first="$(timeout 60 /usr/bin/ai-worker-menubar --once)"
echo "$first" | grep -q '"state": "pair"' && check ok "first look shows a pairing code" || check no "first look shows a pairing code: $first"
sleep 1
second="$(timeout 60 /usr/bin/ai-worker-menubar --once)"
echo "$second" | grep -q '"count": 2' && check ok "second look shows 2 waiting" || check no "second look shows 2 waiting: $second"
mode="$(stat -c %a "$HOME/.config/ai-worker/menubar-session" 2>/dev/null)"
[ "$mode" = 600 ] && check ok "the session file is private" || check no "the session file is private ($mode)"

# the round badge of a notification: the first letter of the name, drawn with the cairo the package brings in
# ô tròn của thông báo: chữ cái đầu của tên, vẽ bằng cairo mà gói kéo theo
badge="$(AI_WORKER_MENUBAR_DIR="$HOME/.config/ai-worker" python3 -c 'import importlib.util, sys; s = importlib.util.spec_from_file_location("core", "/usr/lib/ai-worker-menubar/ai-worker.1m.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.initial_of(sys.argv[1]), m.avatar_png(sys.argv[1]))' "$(printf 'Ph\303\262ng IT')" 2>&1)"
case "$badge" in "P /"*.png) check ok "a notification badge is drawn for the first letter P";; *) check no "a notification badge is drawn: $badge";; esac
[ -n "${BADGE_OUT:-}" ] && cp "${badge#P }" "$BADGE_OUT" 2>/dev/null

timeout 300 sudo apt-get remove -y -qq -o DPkg::Lock::Timeout=120 ai-worker-menubar > /dev/null 2>&1
[ ! -e /usr/bin/ai-worker-menubar ] && [ ! -e /etc/xdg/autostart/ai-worker-menubar.desktop ] && check ok "apt remove takes it away" || check no "apt remove takes it away"
exit $fail
