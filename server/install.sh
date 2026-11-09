#!/bin/bash
# Installs the AI Worker Office dashboard webhook on a Linux server (systemd). Run: sudo bash install.sh
# Run it again to update webhook.py: the old key and data are kept.
# Cài webhook bảng tổng Văn phòng AI Worker lên máy chủ Linux (systemd). Chạy: sudo bash install.sh
# Chạy lại để cập nhật webhook.py: giữ nguyên mã và dữ liệu cũ.
set -e
# Language of the messages: the same 8 lines as packaging/lang.sh, copied here because server/ is installed without packaging/.
# Ngôn ngữ của thông báo: đúng 8 dòng của packaging/lang.sh, chép vào đây vì server/ được cài mà không có packaging/.
case "${AI_WORKER_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
  vi*) AI_WORKER_LANG=vi ;;
  *) AI_WORKER_LANG=en ;;
esac
export AI_WORKER_LANG
say() { if [ "$AI_WORKER_LANG" = vi ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
  say "Run with sudo: sudo bash install.sh" "Cần chạy bằng sudo: sudo bash install.sh"
  exit 1
fi
if ! command -v python3 >/dev/null; then
  say "python3 is required (for example: apt install python3)" "Cần python3 (vd: apt install python3)"
  exit 1
fi

APP_DIR=/opt/ai-worker
PORT=${PORT:-8788}
ENV=/etc/ai-worker.env

id ai-worker >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin ai-worker
umask 022
mkdir -p "$APP_DIR/data"
install -m 0644 webhook.py "$APP_DIR/webhook.py"
install -m 0644 webhook_vi.py "$APP_DIR/webhook_vi.py"
# the parts of the server that webhook.py loads; files left from an older version are removed
# các phần máy chủ mà webhook.py nạp; file còn lại từ bản cũ được xoá
rm -rf "$APP_DIR/board"
install -d -m 0755 "$APP_DIR/board"
install -m 0644 board/*.py "$APP_DIR/board/"
# the 3D office page (three.js + scene + page); without it the webhook falls back to the text board
# signed plugin updates (made by packaging/release.sh): the server only keeps and serves them, the signing key is not here
# trang văn phòng 3D (three.js + cảnh + trang); thiếu thì webhook quay về bảng chữ
# bản cập nhật plugin đã ký (packaging/release.sh tạo): máy chủ chỉ giữ và phát, khoá ký không có ở đây
mkdir -p "$APP_DIR/releases"
if [ -d releases ]; then rm -f "$APP_DIR"/releases/*; install -m 0644 releases/* "$APP_DIR/releases/"; fi
mkdir -p "$APP_DIR/static"
[ -d static ] && install -m 0644 static/* "$APP_DIR/static/"
# menu bar installers the board hands to managers (no key inside; pairing happens after)
# gói cài thanh menu bảng phát cho quản lý (không chứa khoá; ghép máy làm sau)
mkdir -p "$APP_DIR/menubar/icons"
if [ -d menubar ]; then
  install -m 0644 menubar/*.* "$APP_DIR/menubar/"
  install -m 0644 menubar/icons/*.png "$APP_DIR/menubar/icons/"
  # WebView2 libraries for the small window on Windows
  # thư viện WebView2 cho khung nhỏ trên Windows
  if [ -d menubar/webview2 ]; then
    rm -rf "$APP_DIR/menubar/webview2"
    mkdir -p "$APP_DIR/menubar/webview2"
    cp -R menubar/webview2/. "$APP_DIR/menubar/webview2/"
    find "$APP_DIR/menubar/webview2" -type d -exec chmod 0755 {} + ; find "$APP_DIR/menubar/webview2" -type f -exec chmod 0644 {} +
  fi
fi
chown -R ai-worker: "$APP_DIR/data"
# data is readable only by the account running the webhook
# số liệu chỉ tài khoản chạy webhook đọc được
chmod 750 "$APP_DIR/data"
# accounts and OTP keys: readable only by the webhook, kept apart from the data so data backups hold no keys
# tài khoản và khoá OTP: chỉ webhook đọc được, tách khỏi dữ liệu để bản sao lưu số liệu không chứa khoá
mkdir -p "$APP_DIR/keys"
chown -R ai-worker: "$APP_DIR/keys"
chmod 700 "$APP_DIR/keys"
find "$APP_DIR/data" -type f -exec chmod 600 {} +

FIRST_RUN=0
if [ ! -f "$ENV" ]; then
  FIRST_RUN=1
  gen_key() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
  ( umask 077
  cat > "$ENV" <<EOF
PORT=$PORT
INGEST_KEY=$(gen_key)
DATA_DIR=$APP_DIR/data
# Language of the pages when the visitor has not chosen one: en or vi. Empty follows the browser.
# Ngôn ngữ của trang khi người xem chưa chọn: en hoặc vi. Để trống thì theo trình duyệt.
DEFAULT_LANG=
EOF
  )
fi
chmod 600 "$ENV"

# behind Caddy (TRUST_PROXY=1): the webhook listens only inside the machine, all access goes through HTTPS
# đứng sau Caddy (TRUST_PROXY=1): webhook chỉ nghe trong máy, mọi truy cập đi qua HTTPS
VIA_CADDY=0
grep -q '^TRUST_PROXY=1' "$ENV" && VIA_CADDY=1
if [ "$VIA_CADDY" = 1 ]; then
  grep -q '^BIND_ADDR=' "$ENV" && sed -i 's/^BIND_ADDR=.*/BIND_ADDR=127.0.0.1/' "$ENV" || echo 'BIND_ADDR=127.0.0.1' >> "$ENV"
  mkdir -p /etc/systemd/system/ai-worker-webhook.service.d
  cat > /etc/systemd/system/ai-worker-webhook.service.d/override.conf <<EOF
# only Caddy on this machine calls in; the list of allowed IPs is in /etc/caddy/aiworker.caddy
# chỉ Caddy trên chính máy này gọi tới; danh sách IP được vào nằm trong /etc/caddy/aiworker.caddy
[Service]
IPAddressDeny=any
IPAddressAllow=localhost
EOF
fi

cat > /etc/systemd/system/ai-worker-webhook.service <<EOF
[Unit]
Description=AI Worker Office dashboard webhook
After=network.target

[Service]
EnvironmentFile=$ENV
ExecStart=/usr/bin/env python3 $APP_DIR/webhook.py
User=ai-worker
Restart=on-failure
NoNewPrivileges=true
UMask=0077
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
MemoryMax=1G
TasksMax=512
LimitNOFILE=4096
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data $APP_DIR/keys

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ai-worker-webhook
systemctl restart ai-worker-webhook
# wait up to 10 seconds for the first answer: Python and the database take a moment to start
# chờ tối đa 10 giây cho lần trả lời đầu: Python và cơ sở dữ liệu cần chút thời gian để khởi động
PORT_NOW=$(sed -n 's/^PORT=//p' "$ENV"); PORT_NOW=${PORT_NOW:-$PORT}
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -fsS "http://127.0.0.1:$PORT_NOW/health" >/dev/null 2>&1 && break; sleep 1; done

. "$ENV"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  say "✔ The webhook is running." "✔ Webhook đang chạy."
else
  say "✘ The webhook is not running: see 'journalctl -u ai-worker-webhook'" "✘ Webhook chưa chạy: xem 'journalctl -u ai-worker-webhook'"
fi
if [ "$VIA_CADDY" = 1 ]; then
  say "  Listening only on 127.0.0.1:$PORT (reached through Caddy's HTTPS)." "  Chỉ nghe 127.0.0.1:$PORT (vào qua HTTPS của Caddy)."
fi
echo
# the key is printed only on the first install; a re-run to update does not print it (so it does not leak through the screen history)
# mã chỉ in lần cài đầu; chạy lại để cập nhật thì không in (khỏi lộ qua lịch sử màn hình)
if [ "$FIRST_RUN" = 1 ]; then
  say "Send these lines to whoever builds the AI Worker Office package:" "Gửi các dòng sau cho người đóng gói Văn phòng AI Worker:"
  say "  Webhook address : https://<your-domain> (behind Caddy/nginx; the webhook listens only inside the machine by default, port $PORT)" "  Địa chỉ webhook : https://<tên-miền-của-bạn> (đặt sau Caddy/nginx; webhook mặc định chỉ nghe trong máy, cổng $PORT)"
  say "  INGEST_KEY      : $INGEST_KEY      (put it in the install package for staff)" "  INGEST_KEY      : $INGEST_KEY      (đưa vào gói cài cho nhân viên)"
  echo
  say "If the server has a firewall, open port $PORT to the internal network, for example: ufw allow from 192.168.0.0/16 to any port $PORT" "Nếu máy chủ bật tường lửa, mở cổng $PORT cho mạng nội bộ, ví dụ: ufw allow from 192.168.0.0/16 to any port $PORT"
else
  say "Updated; INGEST_KEY is unchanged (see $ENV if you need it)." "Đã cập nhật; INGEST_KEY giữ nguyên (xem trong $ENV nếu cần)."
fi
# if there is no admin yet, create the first one; from then on manage accounts on the /admin page
# máy chưa có quản trị thì tạo người đầu tiên; từ đó quản lý tài khoản ở trang /admin
has_admin() {
  python3 - "$APP_DIR/keys" <<'PY'
import json, os, sqlite3, sys
keys = sys.argv[1]
path = os.path.join(keys, "accounts.db")
if os.path.exists(path):
    # read only: root must not create files the webhook could not write afterwards
    # chỉ đọc: root không được tạo file mà webhook sau đó không ghi được
    rows = sqlite3.connect("file:%s?mode=ro" % path, uri=True).execute("SELECT 1 FROM accounts WHERE role = 'admin' LIMIT 1").fetchall()
    sys.exit(0 if rows else 1)
# a version before SQLite: the accounts are still in accounts.json until the webhook starts
# bản trước SQLite: tài khoản còn trong accounts.json cho tới khi webhook khởi động
try:
    d = json.load(open(os.path.join(keys, "accounts.json"), encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if any(m.get("role") == "admin" for m in d.get("accounts", {}).values()) else 1)
PY
}
if [ -f manage-otp.sh ] && ! has_admin 2>/dev/null; then
  if [ -t 0 ]; then
    echo
    PROMPT=$(
say "No admin yet. Name the first admin account [it-team]: " "Chưa có quản trị. Đặt tên tài khoản quản trị đầu tiên [phong-it]: "
)
    read -r -p "$PROMPT" ADMIN_NAME
    bash manage-otp.sh --rescue "${ADMIN_NAME:-$(say it-team phong-it)}"
  else
    say "No admin yet: run sudo bash manage-otp.sh --rescue <name>" "Chưa có quản trị: chạy sudo bash manage-otp.sh --rescue <tên>"
  fi
fi
say "Manage accounts, locations, the Team plan and the log on the /admin page." "Quản lý tài khoản, địa điểm, gói Team, nhật ký ở trang /admin."
