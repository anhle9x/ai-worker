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
# the Telegram bot process: only a file here; it runs only when asking from Telegram is turned on, see further down
# tiến trình bot Telegram: ở đây chỉ là một file; nó chỉ chạy khi việc hỏi qua Telegram được bật, xem phía dưới
[ -f telegram_bot.py ] && install -m 0644 telegram_bot.py "$APP_DIR/telegram_bot.py"
# the parts of the server that webhook.py loads; files left from an older version are removed
# các phần máy chủ mà webhook.py nạp; file còn lại từ bản cũ được xoá
rm -rf "$APP_DIR/board"
install -d -m 0755 "$APP_DIR/board"
install -m 0644 board/*.py "$APP_DIR/board/"
# the price file and the report's words for AI projects and applications (copies of skills/ai-cost-report)
# bảng giá và chữ của báo cáo cho dự án hay ứng dụng AI (bản sao từ skills/ai-cost-report)
install -m 0644 board/*.json "$APP_DIR/board/"
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

# Asking the board from Telegram (optional): on only with TELEGRAM_ASK=1 in $ENV. The webhook and the bot process share one key,
# made here; the bot's token is kept in a file of its own, so the webhook never holds it and the bot never holds the send key.
# Hỏi bảng qua Telegram (tuỳ chọn): chỉ bật khi có TELEGRAM_ASK=1 trong $ENV. Webhook và tiến trình bot dùng chung một khoá,
# tạo ở đây; khoá của bot nằm trong một file riêng, để webhook không bao giờ cầm nó và bot không bao giờ cầm mã gửi.
BOT_ENV=/etc/ai-worker-telegram.env
BOT_SERVICE=ai-worker-telegram
BOT_UNIT=/etc/systemd/system/$BOT_SERVICE.service
ASK=0
grep -q '^TELEGRAM_ASK=1[[:space:]]*$' "$ENV" && ASK=1
if [ "$ASK" = 1 ]; then
  ASK_KEY=$(sed -n 's/^TELEGRAM_ASK_KEY=//p' "$ENV" | tail -n 1)
  if [ "${#ASK_KEY}" -lt 32 ]; then
    ASK_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    sed -i '/^TELEGRAM_ASK_KEY=/d' "$ENV"
    echo "TELEGRAM_ASK_KEY=$ASK_KEY" >> "$ENV"
  fi
  if [ ! -f "$BOT_ENV" ]; then
    ( umask 077
    cat > "$BOT_ENV" <<EOF
# Settings of the Telegram bot process (ai-worker-telegram). Only root reads this file.
# Cấu hình của tiến trình bot Telegram (ai-worker-telegram). Chỉ root đọc được file này.

# The token of a bot made with @BotFather for asking the board. Not the bot used for logging in to the board.
# After putting it here, run install.sh again.
# Khoá của một bot tạo bằng @BotFather để hỏi bảng. Không phải bot dùng để đăng nhập bảng.
# Điền vào đây xong thì chạy lại install.sh.
TELEGRAM_ASK_TOKEN=

# Networks the bot process may reach, besides this machine and its DNS servers. Empty: Telegram's own networks, as listed on
# https://core.telegram.org/resources/cidr.txt. Your own list: addresses with commas between them. "any": no limit.
# Các mạng tiến trình bot được phép tới, ngoài chính máy này và các máy chủ DNS của nó. Để trống: các mạng của chính Telegram, theo
# https://core.telegram.org/resources/cidr.txt. Danh sách riêng: các địa chỉ cách nhau bằng dấu phẩy. "any": không giới hạn.
TELEGRAM_NETS=

# Written by install.sh at every run, from $ENV: do not change them here.
# install.sh ghi lại ở mỗi lần chạy, lấy từ $ENV: đừng sửa ở đây.
EOF
    )
  fi
  chmod 600 "$BOT_ENV"
  # the key and the port are the webhook's: the same on both sides after every run
  # khoá và cổng là của webhook: sau mỗi lần chạy thì hai bên giống nhau
  sed -i '/^TELEGRAM_ASK_KEY=/d; /^PORT=/d' "$BOT_ENV"
  BOT_PORT=$(sed -n 's/^PORT=//p' "$ENV" | tail -n 1)
  printf 'TELEGRAM_ASK_KEY=%s\nPORT=%s\n' "$ASK_KEY" "${BOT_PORT:-$PORT}" >> "$BOT_ENV"
fi

# The board's window inside Telegram (optional): on only with TELEGRAM_APP=1 as well. The webhook gets a key derived from the bot's token
# by Telegram's rule, which checks what Telegram signs for the window but cannot drive the bot; the token itself stays with the bot process.
# Khung bảng bên trong Telegram (tuỳ chọn): chỉ bật khi có thêm TELEGRAM_APP=1. Webhook nhận một khoá suy ra từ khoá bot theo quy tắc
# của Telegram, khoá này kiểm được phần Telegram ký cho khung nhưng không điều khiển được bot; bản thân khoá bot vẫn chỉ nằm ở tiến trình bot.
sed -i '/^TELEGRAM_APP_KEY=/d' "$ENV"
if [ "$ASK" = 1 ] && grep -q '^TELEGRAM_APP=1[[:space:]]*$' "$ENV"; then
  APP_TOKEN=$(sed -n 's/^TELEGRAM_ASK_TOKEN=//p' "$BOT_ENV" | tail -n 1 | tr -d '[:space:]')
  if [ -n "$APP_TOKEN" ]; then
    # the token goes in on stdin, not on the command line, where other users could read it
    # khoá bot đi vào qua stdin, không nằm trên dòng lệnh, nơi người dùng khác có thể đọc được
    APP_KEY=$(printf '%s' "$APP_TOKEN" | python3 -c 'import hashlib, hmac, sys; print(hmac.new(b"WebAppData", sys.stdin.read().encode(), hashlib.sha256).hexdigest())')
    echo "TELEGRAM_APP_KEY=$APP_KEY" >> "$ENV"
  fi
  if ! grep -Eq '^TELEGRAM_APP_URL=https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/tg/app[[:space:]]*$' "$ENV"; then
    say "  The window inside Telegram is on, but TELEGRAM_APP_URL is missing or wrong in $ENV: set it to https://<your board's address>/tg/app, then run this installer again." "  Khung bên trong Telegram đang bật, nhưng TELEGRAM_APP_URL trong $ENV thiếu hoặc sai: đặt thành https://<địa chỉ bảng của bạn>/tg/app, rồi chạy lại bộ cài này."
  fi
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

# The Telegram bot process: a service of its own, under its own user, that reaches this machine, its DNS servers and Telegram, nothing else.
# It starts only when a token is there, and it is taken away when asking from Telegram is turned off.
# Tiến trình bot Telegram: một dịch vụ riêng, chạy dưới người dùng riêng, chỉ tới được chính máy này, các máy chủ DNS của nó và Telegram.
# Nó chỉ chạy khi đã có khoá của bot, và bị gỡ khi việc hỏi qua Telegram bị tắt.
if [ "$ASK" = 1 ] && ! grep -q '^TELEGRAM_ASK_TOKEN=[^[:space:]]' "$BOT_ENV"; then
  if [ -f "$BOT_UNIT" ]; then systemctl disable --now "$BOT_SERVICE" >/dev/null 2>&1 || true; fi
  say "  Asking from Telegram is on, but there is no bot token yet: put the token of a bot made for this with @BotFather into $BOT_ENV (TELEGRAM_ASK_TOKEN=), then run this installer again." "  Hỏi bảng qua Telegram đang bật, nhưng chưa có khoá của bot: ghi khoá của một bot tạo riêng cho việc này bằng @BotFather vào $BOT_ENV (TELEGRAM_ASK_TOKEN=), rồi chạy lại bộ cài này."
elif [ "$ASK" = 1 ]; then
  id "$BOT_SERVICE" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$BOT_SERVICE"
  # Telegram's networks, read on 2026-11-16 from https://core.telegram.org/resources/cidr.txt; TELEGRAM_NETS in $BOT_ENV replaces the list
  # các mạng của Telegram, đọc ngày 2026-11-16 từ https://core.telegram.org/resources/cidr.txt; TELEGRAM_NETS trong $BOT_ENV thay cho danh sách này
  BOT_NETS="91.108.56.0/22 91.108.4.0/22 91.108.8.0/22 91.108.16.0/22 91.108.12.0/22 149.154.160.0/20 91.105.192.0/23 91.108.20.0/22 185.76.151.0/24 2001:b28:f23d::/48 2001:b28:f23f::/48 2001:67c:4e8::/48 2001:b28:f23c::/48 2a0a:f280::/32"
  OWN_NETS=$(sed -n 's/^TELEGRAM_NETS=//p' "$BOT_ENV" | tail -n 1 | tr ',' ' ' | xargs)
  BOT_FENCE=""
  if [ "$OWN_NETS" != any ]; then
    if [ -n "$OWN_NETS" ]; then
      if printf '%s' "$OWN_NETS" | grep -Eq '^[0-9a-fA-F:./ ]+$'; then
        BOT_NETS=$OWN_NETS
      else
        say "  TELEGRAM_NETS in $BOT_ENV is not a list of network addresses; Telegram's own networks are used." "  TELEGRAM_NETS trong $BOT_ENV không phải danh sách địa chỉ mạng; dùng các mạng của chính Telegram."
      fi
    fi
    # the name api.telegram.org must still be looked up: DNS servers that are not on this machine are let through too
    # vẫn phải tra tên api.telegram.org: các máy chủ DNS không nằm trên máy này cũng được cho qua
    BOT_DNS=$(awk '$1 == "nameserver" { print $2 }' /etc/resolv.conf 2>/dev/null | sed 's/%.*//' | grep -E '^[0-9a-fA-F:.]+$' | grep -Ev '^(127\.|::1$)' | tr '\n' ' ')
    BOT_FENCE="IPAddressDeny=any
IPAddressAllow=localhost $BOT_NETS $BOT_DNS"
  fi
  cat > "$BOT_UNIT" <<EOF
[Unit]
Description=AI Worker Telegram bot (asking the board from Telegram)
After=network-online.target ai-worker-webhook.service
Wants=network-online.target

[Service]
EnvironmentFile=$BOT_ENV
ExecStart=/usr/bin/env python3 $APP_DIR/telegram_bot.py
User=$BOT_SERVICE
Restart=on-failure
RestartSec=30
NoNewPrivileges=true
UMask=0077
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
MemoryMax=128M
TasksMax=16
LimitNOFILE=256
ProtectSystem=strict
ProtectHome=true
$BOT_FENCE

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$BOT_SERVICE" >/dev/null 2>&1
  systemctl restart "$BOT_SERVICE"
  sleep 2
  if [ "$(systemctl is-active "$BOT_SERVICE")" = active ]; then
    say "✔ The Telegram bot process is running. The /admin page, under TV screens, says whether Telegram takes its token." "✔ Tiến trình bot Telegram đang chạy. Trang /admin, mục Màn hình TV, cho biết Telegram có nhận khoá của nó không."
  else
    say "✘ The Telegram bot process is not running: see 'journalctl -u $BOT_SERVICE'" "✘ Tiến trình bot Telegram chưa chạy: xem 'journalctl -u $BOT_SERVICE'"
  fi
elif [ -f "$BOT_UNIT" ]; then
  systemctl disable --now "$BOT_SERVICE" >/dev/null 2>&1 || true
  rm -f "$BOT_UNIT"
  systemctl daemon-reload
  say "  Asking from Telegram is off: the bot's service is removed. Its token stays in $BOT_ENV; delete that file if you will not use it again." "  Hỏi bảng qua Telegram đang tắt: dịch vụ của bot đã bị gỡ. Khoá của nó vẫn nằm trong $BOT_ENV; hãy xoá file đó nếu bạn không dùng lại."
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
