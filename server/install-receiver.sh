#!/bin/sh
# Sets up the optional Go receiver (docs/RECEIVER.md) on the Linux server where install.sh already runs the webhook. Run: sudo sh install-receiver.sh
# The first time it needs where to listen and the certificate:
#   sudo sh install-receiver.sh --listen 203.0.113.2:443 --cert /etc/ai-worker-receiver/fullchain.pem --key /etc/ai-worker-receiver/privkey.pem \
#     --live-url https://ingest.example.com --board https://board.example.com
# Run it again at any time: the settings in /etc/ai-worker-receiver.env are kept, the program and its service are written again.
# Other runs: --check (only checks, changes nothing), --update (the new program only, install.sh calls it), --rollback (the program
# before), --remove (stops the receiver and takes its service away), --take-over (replaces a receiver service written by hand).
# It never moves a computer to the receiver: that stays RECEIVER_INGEST_URLS and RECEIVER_INGEST_DEVICES in /etc/ai-worker.env.
# Cài bộ nhận Go tuỳ chọn (docs/RECEIVER.vi.md) lên máy chủ Linux nơi install.sh đã chạy webhook. Chạy: sudo sh install-receiver.sh
# Lần đầu cần nơi nghe và chứng chỉ:
#   sudo sh install-receiver.sh --listen 203.0.113.2:443 --cert /etc/ai-worker-receiver/fullchain.pem --key /etc/ai-worker-receiver/privkey.pem \
#     --live-url https://ingest.example.com --board https://board.example.com
# Chạy lại lúc nào cũng được: cấu hình trong /etc/ai-worker-receiver.env được giữ, file chạy và dịch vụ của nó được viết lại.
# Cách chạy khác: --check (chỉ kiểm, không đổi gì), --update (chỉ file chạy mới, install.sh gọi), --rollback (file chạy trước đó),
# --remove (dừng bộ nhận và gỡ dịch vụ của nó), --take-over (thay dịch vụ bộ nhận viết tay).
# Nó không bao giờ chuyển máy nào sang bộ nhận: việc đó vẫn là RECEIVER_INGEST_URLS và RECEIVER_INGEST_DEVICES trong /etc/ai-worker.env.
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
HERE=$(pwd)

APP_DIR=/opt/ai-worker
ENV=/etc/ai-worker.env
RENV=/etc/ai-worker-receiver.env
SERVICE=ai-worker-receiver
UNIT_DIR=${AI_WORKER_UNIT_DIR:-/etc/systemd/system}
UNIT=$UNIT_DIR/$SERVICE.service
BIN=$APP_DIR/ai-worker-receiver
MARK='# Written by install-receiver.sh: run it again rather than editing this file.'

MODE=install
TAKE_OVER=0
BINARY=""
A_LISTEN=""; A_CERT=""; A_KEY=""; A_LIVE=""; A_BOARD=""
need_value() {
  [ "$#" -ge 2 ] && return 0
  say "$1 needs a value" "$1 cần một giá trị"
  exit 1
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --listen) need_value "$@"; A_LISTEN=$2; shift 2 ;;
    --cert) need_value "$@"; A_CERT=$2; shift 2 ;;
    --key) need_value "$@"; A_KEY=$2; shift 2 ;;
    --live-url) need_value "$@"; A_LIVE=$2; shift 2 ;;
    --board) need_value "$@"; A_BOARD=$2; shift 2 ;;
    --binary) need_value "$@"; BINARY=$2; shift 2 ;;
    --take-over) TAKE_OVER=1; shift ;;
    --check) MODE=check; shift ;;
    --update) MODE=update; shift ;;
    --rollback) MODE=rollback; shift ;;
    --remove) MODE=remove; shift ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)
      say "Unknown option: $1 (see --help)" "Không hiểu tuỳ chọn: $1 (xem --help)"
      exit 1 ;;
  esac
done

if [ "$(id -u)" != 0 ]; then
  say "Run with sudo: sudo sh install-receiver.sh" "Cần chạy bằng sudo: sudo sh install-receiver.sh"
  exit 1
fi
if [ "$(uname -s)" != Linux ] || ! command -v systemctl >/dev/null 2>&1; then
  say "The receiver is set up on Linux with systemd only. A server on Windows is not supported yet." "Bộ nhận chỉ cài được trên Linux có systemd. Máy chủ Windows chưa được hỗ trợ."
  exit 1
fi

# envget FILE KEY: the last value of KEY in FILE, quotes taken off. envset FILE KEY VALUE: changes that line, or adds it.
# envget FILE KEY: giá trị cuối của KEY trong FILE, bỏ dấu nháy. envset FILE KEY VALUE: sửa dòng đó, hoặc thêm vào.
envget() { [ -f "$1" ] && sed -n "s/^$2=//p" "$1" | tail -n 1 | sed 's/^"\(.*\)"$/\1/; s/[[:space:]]*$//' || true; }
envset() {
  if grep -q "^$2=" "$1"; then
    tmp="$1.tmp.$$"
    awk -v k="$2" -v v="$3" 'index($0, k "=") == 1 { print k "=" v; next } { print }' "$1" > "$tmp"
    chmod 600 "$tmp"; mv "$tmp" "$1"
  else
    printf '%s=%s\n' "$2" "$3" >> "$1"
  fi
}
ours() { [ -f "$UNIT" ] && grep -qxF "$MARK" "$UNIT"; }
active() { [ "$(systemctl is-active "$SERVICE" 2>/dev/null)" = active ]; }

# The receiver's address parts from RECEIVER_LISTEN: 203.0.113.2:443 or [2001:db8::2]:443.
# Các phần địa chỉ của bộ nhận lấy từ RECEIVER_LISTEN: 203.0.113.2:443 hoặc [2001:db8::2]:443.
split_listen() {
  case "$1" in
    \[*\]:*) IP=${1#\[}; IP=${IP%%\]*}; PORT=${1##*\]:}; IP_URL="[$IP]" ;;
    *:*:*) IP=""; PORT="" ;;
    *:*) IP=${1%:*}; PORT=${1##*:}; IP_URL=$IP ;;
    *) IP=""; PORT="" ;;
  esac
  printf '%s' "$IP" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$|^[0-9a-fA-F:]+$' || IP=""
  printf '%s' "$PORT" | grep -Eq '^[0-9]{1,5}$' || PORT=""
  [ -n "$IP" ] && [ -n "$PORT" ] && [ "$IP" != 0.0.0.0 ] && [ "$IP" != :: ]
}
host_of() { printf '%s' "$1" | sed -n 's#^https://\([A-Za-z0-9.-]*\)\(:[0-9]\{1,5\}\)\{0,1\}/\{0,1\}$#\1#p'; }

# The program for this machine: --binary, else the one built for its processor in receiver-bin/ (packaging/build-receiver.sh), checked
# against SHA256SUMS.
# File chạy cho máy này: --binary, không thì bản dựng cho bộ xử lý của nó trong receiver-bin/ (packaging/build-receiver.sh), đối chiếu
# với SHA256SUMS.
pick_binary() {
  if [ -n "$BINARY" ]; then
    if [ ! -f "$BINARY" ]; then
      say "No program at $BINARY" "Không có file chạy ở $BINARY"
      exit 1
    fi
    SRC_BIN=$BINARY
    return
  fi
  case "$(uname -m)" in
    x86_64|amd64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    *)
      say "No receiver is built for the processor $(uname -m): build it with Go and pass --binary." "Không có bộ nhận dựng sẵn cho bộ xử lý $(uname -m): tự dựng bằng Go rồi đưa vào bằng --binary."
      exit 1 ;;
  esac
  SRC_BIN=$HERE/receiver-bin/ai-worker-receiver-linux-$ARCH
  if [ ! -f "$SRC_BIN" ]; then
    say "The receiver program is not here ($SRC_BIN). On the computer that copies server/ to this machine run: sh packaging/build-receiver.sh, then copy server/ again. Without Go there, take the files of your version from the project's Releases page on GitHub and put them in server/receiver-bin/ (docs/RECEIVER.md, section 5)." "Chưa có file chạy của bộ nhận ($SRC_BIN). Ở máy chép server/ lên máy này chạy: sh packaging/build-receiver.sh, rồi chép lại server/. Máy đó không có Go thì lấy các file của phiên bản bạn dùng ở trang Releases của dự án trên GitHub rồi đặt vào server/receiver-bin/ (docs/RECEIVER.vi.md, mục 5)."
    exit 1
  fi
  if [ -f "$HERE/receiver-bin/SHA256SUMS" ]; then
    if ! (cd "$HERE/receiver-bin" && grep " ai-worker-receiver-linux-$ARCH\$" SHA256SUMS | sha256sum -c - >/dev/null 2>&1); then
      say "✘ $SRC_BIN does not match receiver-bin/SHA256SUMS: build it again and copy server/ again." "✘ $SRC_BIN không khớp receiver-bin/SHA256SUMS: dựng lại rồi chép lại server/."
      exit 1
    fi
  fi
}

# Puts the program in place. The one it replaces is kept as .prev for --rollback. Sets CHANGED=1 when the program is new.
# Đặt file chạy vào chỗ. Bản bị thay được giữ thành .prev cho --rollback. Đặt CHANGED=1 khi file chạy là bản mới.
put_binary() {
  pick_binary
  if [ -f "$BIN" ] && cmp -s "$SRC_BIN" "$BIN"; then return; fi
  [ -f "$BIN" ] && cp -p "$BIN" "$BIN.prev"
  install -m 0755 -o root -g root "$SRC_BIN" "$BIN.new"
  mv -f "$BIN.new" "$BIN"
  CHANGED=1
  if [ -f "$HERE/receiver-bin/BUILD" ] && [ -z "$BINARY" ]; then
    say "  Receiver program: $(tr '\n' ' ' < "$HERE/receiver-bin/BUILD")" "  File chạy bộ nhận: $(tr '\n' ' ' < "$HERE/receiver-bin/BUILD")"
  fi
}

# The service, written again from the settings at every run. MemoryMax a little above RECEIVER_MEMORY_MB and OOMScoreAdjust=500: if
# memory still runs out, the kernel kills the receiver, which restarts in seconds, and never the Python server.
# Dịch vụ, viết lại từ cấu hình ở mỗi lần chạy. MemoryMax cao hơn RECEIVER_MEMORY_MB một chút và OOMScoreAdjust=500: nếu vẫn hết
# bộ nhớ, nhân giết bộ nhận (khởi động lại trong vài giây), không bao giờ giết máy chủ Python.
total_mb() { awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo; }
put_unit() {
  MB=$(envget "$RENV" RECEIVER_MEMORY_MB)
  case "$MB" in
    ''|*[!0-9]*) MB=$(( $(total_mb) * 40 / 100 )) ;;
    0) MB=$(( $(total_mb) * 50 / 100 )) ;;
  esac
  MAX=$(( MB + MB / 10 + 64 ))
  tmp="$UNIT.tmp.$$"
  cat > "$tmp" <<EOF
$MARK
# Bộ cài install-receiver.sh viết file này: chạy lại bộ cài thay vì sửa file này.
[Unit]
Description=AI Worker receiver (Go), takes the computers' sends for the webhook
After=network-online.target ai-worker-webhook.service
Wants=network-online.target

[Service]
EnvironmentFile=$RENV
ExecStart=$BIN
User=ai-worker
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
Restart=always
RestartSec=2
MemoryMax=${MAX}M
OOMScoreAdjust=500
LimitNOFILE=262144
TasksMax=4096
UMask=0077
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
  if [ -f "$UNIT" ] && cmp -s "$tmp" "$UNIT"; then rm -f "$tmp"; return; fi
  chmod 0644 "$tmp"; mv -f "$tmp" "$UNIT"
  systemctl daemon-reload
  CHANGED=1
}

start() {
  systemctl enable "$SERVICE" >/dev/null 2>&1
  if [ "${CHANGED:-0}" = 1 ] || ! active; then systemctl restart "$SERVICE"; fi
}

# The receiver answers /health over TLS on its own address, by its name: first as the computers would check it, then without checking
# the certificate, to tell a certificate problem from a receiver that does not answer.
# Bộ nhận trả /health qua TLS trên địa chỉ riêng, theo tên của nó: trước hết kiểm như máy nhân viên kiểm, rồi không kiểm chứng chỉ,
# để phân biệt lỗi chứng chỉ với bộ nhận không trả lời.
health() {
  split_listen "$(envget "$RENV" RECEIVER_LISTEN)" || return 1
  NAME=$(envget "$RENV" RECEIVER_NAME)
  [ -n "$NAME" ] || NAME=$IP
  URL="https://$NAME:$PORT/health"
  [ "$NAME" = "$IP" ] && URL="https://$IP_URL:$PORT/health"
  i=0
  while [ "$i" -lt "${1:-20}" ]; do
    if curl -fsS --max-time 3 --resolve "$NAME:$PORT:$IP" "$URL" >/dev/null 2>&1; then
      say "✔ The receiver answers on https://$NAME:$PORT/health" "✔ Bộ nhận trả lời ở https://$NAME:$PORT/health"
      return 0
    fi
    if curl -kfsS --max-time 3 --resolve "$NAME:$PORT:$IP" "$URL" >/dev/null 2>&1; then
      say "! The receiver answers, but this machine does not trust its certificate for $NAME: the computers will not either. Check the certificate (a public one, full chain, for $NAME)." "! Bộ nhận có trả lời, nhưng máy này không tin chứng chỉ của nó cho $NAME: máy nhân viên cũng sẽ không tin. Kiểm chứng chỉ (chứng chỉ công khai, đủ chuỗi, cho $NAME)."
      return 0
    fi
    i=$((i + 1)); sleep 1
  done
  say "✘ The receiver does not answer: see 'journalctl -u $SERVICE'" "✘ Bộ nhận chưa trả lời: xem 'journalctl -u $SERVICE'"
  return 1
}

# ---- --remove, --rollback, --update: no questions, only what is already set up --------------------------------------------------
# ---- --remove, --rollback, --update: không hỏi gì, chỉ làm trên cái đã cài ---------------------------------------------------------
if [ "$MODE" = remove ]; then
  if ! ours; then
    say "The receiver is not set up by this installer: nothing to remove." "Bộ nhận không do bộ cài này cài: không có gì để gỡ."
    exit 0
  fi
  systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
  rm -f "$UNIT"
  systemctl daemon-reload
  say "✔ The receiver is stopped and its service removed. Computers that sent to it go back to the webhook on their next send." "✔ Bộ nhận đã dừng và dịch vụ của nó đã gỡ. Các máy đang gửi tới nó quay về webhook ở lần gửi sau."
  say "  Kept: $RENV, $BIN and RECEIVER=1 in $ENV. Empty RECEIVER_INGEST_URLS in $ENV and restart the webhook so no computer is told the address again." "  Vẫn giữ: $RENV, $BIN và RECEIVER=1 trong $ENV. Để trống RECEIVER_INGEST_URLS trong $ENV rồi khởi động lại webhook để không máy nào được báo địa chỉ này nữa."
  exit 0
fi
if [ "$MODE" = rollback ]; then
  if ! ours; then
    say "The receiver is not set up by this installer." "Bộ nhận không do bộ cài này cài."
    exit 1
  fi
  if [ ! -f "$BIN.prev" ]; then
    say "There is no program before this one ($BIN.prev)." "Không có file chạy nào trước bản này ($BIN.prev)."
    exit 1
  fi
  mv -f "$BIN" "$BIN.tmp.$$"; mv -f "$BIN.prev" "$BIN"; mv -f "$BIN.tmp.$$" "$BIN.prev"
  systemctl restart "$SERVICE"
  say "✔ Back to the program before. Running --rollback again goes forward again; the next --update or install.sh puts the program of server/ back." "✔ Đã quay về file chạy trước. Chạy --rollback lần nữa thì đi tới lại; lần --update hay install.sh sau đặt lại file chạy của server/."
  health 20 || exit 1
  exit 0
fi
if [ "$MODE" = update ]; then
  # install.sh calls this at every run: nothing at all when the receiver is not set up by this installer
  # install.sh gọi ở mỗi lần chạy: không làm gì cả khi bộ nhận không do bộ cài này cài
  ours || exit 0
  CHANGED=0
  if [ -z "$BINARY" ] && [ ! -d "$HERE/receiver-bin" ]; then
    say "  The receiver keeps its program: there is no receiver-bin/ in this copy of server/ (sh packaging/build-receiver.sh)." "  Bộ nhận giữ file chạy cũ: bản server/ này không có receiver-bin/ (sh packaging/build-receiver.sh)."
  else
    put_binary
  fi
  put_unit
  start
  if [ "$CHANGED" = 1 ]; then
    health 20 || exit 1
  else
    say "✔ The receiver is unchanged." "✔ Bộ nhận không đổi."
  fi
  exit 0
fi

# ---- install and --check ----------------------------------------------------------------------------------------------------------
# ---- cài và --check -----------------------------------------------------------------------------------------------------------------
if [ ! -f "$ENV" ] || ! id ai-worker >/dev/null 2>&1; then
  say "Run install.sh first: the receiver goes beside the webhook it installs." "Chạy install.sh trước: bộ nhận nằm cạnh webhook mà nó cài."
  exit 1
fi

# the closing lines say how to try the receiver until this installer's service has run once
# các dòng cuối nói cách thử bộ nhận cho tới khi dịch vụ của bộ cài này đã chạy một lần
FIRST=1
ours && FIRST=0
# A receiver service written by hand (the trial set up before this installer): left alone unless --take-over.
# Dịch vụ bộ nhận viết tay (bản thử cài trước khi có bộ cài này): để nguyên trừ khi có --take-over.
OLD=""
for f in "$UNIT_DIR"/*.service; do
  [ -f "$f" ] || continue
  [ "$f" = "$UNIT" ] && ours && continue
  if grep -Eq '^ExecStart=.*ai-worker-receiver' "$f"; then
    if [ -n "$OLD" ]; then
      say "More than one receiver service: $OLD and $f. Keep one, then run this again." "Có hơn một dịch vụ bộ nhận: $OLD và $f. Giữ một cái rồi chạy lại."
      exit 1
    fi
    OLD=$f
  fi
done
if [ -n "$OLD" ] && [ "$MODE" = install ] && [ "$TAKE_OVER" != 1 ]; then
  say "✘ A receiver service written by hand is here: $OLD. This installer leaves it alone." "✘ Ở đây có một dịch vụ bộ nhận viết tay: $OLD. Bộ cài này không đụng tới nó."
  say "  To let this installer run the receiver from now on, run it again with --take-over: it keeps a copy of that file beside it, takes its RECEIVER_ settings, stops it and writes its own service." "  Để bộ cài này chạy bộ nhận từ nay, chạy lại với --take-over: nó giữ một bản của file đó bên cạnh, lấy các cấu hình RECEIVER_ của nó, dừng nó và viết dịch vụ của mình."
  exit 1
fi

# The settings an old service had, in its Environment= lines and its EnvironmentFile=, to fill what is not given.
# Cấu hình của dịch vụ cũ, trong các dòng Environment= và EnvironmentFile= của nó, để điền chỗ chưa được đưa.
SEED=$(mktemp)
trap 'rm -f "$SEED"' EXIT
if [ -n "$OLD" ] && [ "$TAKE_OVER" = 1 ]; then
  sed -n 's/^Environment=//p' "$OLD" | xargs -n 1 2>/dev/null | grep -E '^(RECEIVER_[A-Z_]+|GOMEMLIMIT)=' >> "$SEED" || true
  for ef in $(sed -n 's/^EnvironmentFile=-\{0,1\}//p' "$OLD"); do
    [ -f "$ef" ] && grep -E '^(RECEIVER_[A-Z_]+|GOMEMLIMIT)=' "$ef" | sed 's/="\(.*\)"$/=\1/' >> "$SEED" || true
  done
fi
seeded() { envget "$SEED" "$1"; }

PORT_WEBHOOK=$(envget "$ENV" PORT); PORT_WEBHOOK=${PORT_WEBHOOK:-8788}
SECRETS=$(envget "$ENV" RECEIVER_SECRETS_FILE)
if [ -z "$SECRETS" ]; then KEYS=$(envget "$ENV" KEYS_DIR); SECRETS=${KEYS:-$APP_DIR/keys}/receiver-secrets.json; fi
LIVE_NOW=$(envget "$ENV" RECEIVER_LIVE_URL)
BOARD_NOW=$(envget "$ENV" RECEIVER_BOARD_ORIGIN)

if [ ! -f "$RENV" ]; then
  if [ "$MODE" = check ]; then
    say "✘ The receiver is not set up yet ($RENV is missing)." "✘ Bộ nhận chưa được cài ($RENV chưa có)."
    exit 1
  fi
  # what is not given is asked when there is a terminal; otherwise the run stops and says what is missing
  # cái chưa được đưa thì hỏi khi có màn hình; không thì dừng và nói thiếu gì
  LISTEN=${A_LISTEN:-$(seeded RECEIVER_LISTEN)}
  CERT=${A_CERT:-$(seeded RECEIVER_TLS_CERT)}
  KEY=${A_KEY:-$(seeded RECEIVER_TLS_KEY)}
  LIVE=${A_LIVE:-$LIVE_NOW}
  BOARD=${A_BOARD:-$BOARD_NOW}
  if [ -z "$LISTEN" ] && [ -t 0 ]; then
    say "The second IP and port to listen on [for example 203.0.113.2:443]: " "IP thứ hai và cổng để nghe [ví dụ 203.0.113.2:443]: "
    read -r LISTEN
  fi
  if [ -z "$LIVE" ] && [ -t 0 ]; then
    say "The receiver's address [for example https://ingest.example.com]: " "Địa chỉ của bộ nhận [ví dụ https://ingest.example.com]: "
    read -r LIVE
  fi
  if [ -z "$CERT" ] && [ -t 0 ]; then
    say "The certificate file (full chain): " "File chứng chỉ (đủ chuỗi): "
    read -r CERT
  fi
  if [ -z "$KEY" ] && [ -t 0 ]; then
    say "The certificate's private key file: " "File khoá bí mật của chứng chỉ: "
    read -r KEY
  fi
  if [ -z "$BOARD" ] && [ -t 0 ]; then
    say "The board's address [for example https://board.example.com]: " "Địa chỉ của bảng [ví dụ https://board.example.com]: "
    read -r BOARD
  fi
  if [ -z "$LISTEN" ] || [ -z "$CERT" ] || [ -z "$KEY" ] || [ -z "$LIVE" ] || [ -z "$BOARD" ]; then
    say "The first run needs --listen IP:443 --cert FILE --key FILE --live-url https://ingest.<domain> --board https://<board's domain>" "Lần chạy đầu cần --listen IP:443 --cert FILE --key FILE --live-url https://ingest.<tên miền> --board https://<tên miền của bảng>"
    exit 1
  fi
  MEM=$(seeded RECEIVER_MEMORY_MB)
  if [ -z "$MEM" ]; then MEM=$(( $(total_mb) * 40 / 100 )); [ "$MEM" -lt 256 ] && MEM=256; fi
  ( umask 077
  cat > "$RENV" <<EOF
# Settings of the Go receiver (docs/RECEIVER.md, section 4). Made once by install-receiver.sh, which keeps them; after a change run it again.
# Cấu hình của bộ nhận Go (docs/RECEIVER.vi.md, mục 4). install-receiver.sh tạo một lần và giữ nguyên; sửa xong thì chạy lại nó.
RECEIVER_LISTEN=$LISTEN
RECEIVER_TLS_CERT=$CERT
RECEIVER_TLS_KEY=$KEY
RECEIVER_SECRETS_FILE=$SECRETS
RECEIVER_WEBHOOK=http://127.0.0.1:$PORT_WEBHOOK
# The receiver's name, from its address: only for the installer's checks (DNS, certificate, /health).
# Tên của bộ nhận, lấy từ địa chỉ của nó: chỉ để bộ cài kiểm (DNS, chứng chỉ, /health).
RECEIVER_NAME=$(host_of "$LIVE")
# The board's address, only for the installer: it puts it in $ENV as RECEIVER_BOARD_ORIGIN when that is empty.
# Địa chỉ của bảng, chỉ cho bộ cài: nó ghi vào $ENV thành RECEIVER_BOARD_ORIGIN khi dòng đó trống.
RECEIVER_BOARD=$BOARD
# 40% of the machine when made; the service's MemoryMax is a little above it.
# 40% bộ nhớ của máy lúc tạo; MemoryMax của dịch vụ cao hơn nó một chút.
RECEIVER_MEMORY_MB=$MEM
RECEIVER_BATCH_MS=$(seeded RECEIVER_BATCH_MS)
RECEIVER_MAX_CONNECTIONS=$(seeded RECEIVER_MAX_CONNECTIONS)
RECEIVER_SENDS_PER_SECOND=$(seeded RECEIVER_SENDS_PER_SECOND)
EOF
  )
else
  # settings given on the command line change those lines; the rest is kept
  # cấu hình đưa trên dòng lệnh sửa các dòng đó; phần còn lại giữ nguyên
  if [ "$MODE" = install ]; then
    [ -n "$A_LISTEN" ] && envset "$RENV" RECEIVER_LISTEN "$A_LISTEN"
    [ -n "$A_CERT" ] && envset "$RENV" RECEIVER_TLS_CERT "$A_CERT"
    [ -n "$A_KEY" ] && envset "$RENV" RECEIVER_TLS_KEY "$A_KEY"
    [ -n "$A_LIVE" ] && envset "$RENV" RECEIVER_NAME "$(host_of "$A_LIVE")"
    [ -n "$A_BOARD" ] && envset "$RENV" RECEIVER_BOARD "$A_BOARD"
  fi
  LIVE=$A_LIVE
  [ -n "$LIVE" ] || LIVE=$LIVE_NOW
  [ -n "$LIVE" ] || [ -z "$(envget "$RENV" RECEIVER_NAME)" ] || LIVE=https://$(envget "$RENV" RECEIVER_NAME)
  BOARD=${A_BOARD:-${BOARD_NOW:-$(envget "$RENV" RECEIVER_BOARD)}}
  # A file of settings made by hand (a trial set up before this installer used the same name): what this installer adds is asked
  # for when there is a terminal, and filled in.
  # File cấu hình viết tay (bản thử cài trước bộ cài này dùng cùng tên): phần bộ cài này thêm được hỏi khi có màn hình, rồi điền vào.
  if [ -z "$LIVE" ] && [ -t 0 ]; then
    say "The receiver's address [for example https://ingest.example.com]: " "Địa chỉ của bộ nhận [ví dụ https://ingest.example.com]: "
    read -r LIVE
  fi
  if [ -z "$BOARD" ] && [ -t 0 ]; then
    say "The board's address [for example https://board.example.com]: " "Địa chỉ của bảng [ví dụ https://board.example.com]: "
    read -r BOARD
  fi
  if [ "$MODE" = install ]; then
    [ -z "$(envget "$RENV" RECEIVER_NAME)" ] && [ -n "$(host_of "$LIVE")" ] && envset "$RENV" RECEIVER_NAME "$(host_of "$LIVE")"
    [ -z "$(envget "$RENV" RECEIVER_BOARD)" ] && [ -n "$BOARD" ] && envset "$RENV" RECEIVER_BOARD "$BOARD"
    [ -z "$(envget "$RENV" RECEIVER_SECRETS_FILE)" ] && envset "$RENV" RECEIVER_SECRETS_FILE "$SECRETS"
    [ -z "$(envget "$RENV" RECEIVER_WEBHOOK)" ] && envset "$RENV" RECEIVER_WEBHOOK "http://127.0.0.1:$PORT_WEBHOOK"
    if ! grep -q '^RECEIVER_MEMORY_MB=' "$RENV"; then
      MEM=$(( $(total_mb) * 40 / 100 )); [ "$MEM" -lt 256 ] && MEM=256
      envset "$RENV" RECEIVER_MEMORY_MB "$MEM"
    fi
  fi
fi
chown root:root "$RENV"; chmod 600 "$RENV"

LISTEN=$(envget "$RENV" RECEIVER_LISTEN); CERT=$(envget "$RENV" RECEIVER_TLS_CERT); KEY=$(envget "$RENV" RECEIVER_TLS_KEY)
NAME=$(envget "$RENV" RECEIVER_NAME)
BAD=0
if ! split_listen "$LISTEN"; then
  BAD=1
  say "✘ RECEIVER_LISTEN=$LISTEN in $RENV is not IP:port with the IP said (for example 203.0.113.2:443)." "✘ RECEIVER_LISTEN=$LISTEN trong $RENV không phải IP:cổng có nói rõ IP (ví dụ 203.0.113.2:443)."
fi
if [ -z "${LIVE:-}" ]; then
  BAD=1
  say "✘ The receiver's address is not known yet: add --live-url https://ingest.<your domain> (and --board https://<the board's domain>)." "✘ Chưa biết địa chỉ của bộ nhận: thêm --live-url https://ingest.<tên miền của bạn> (và --board https://<tên miền của bảng>)."
elif [ -z "$NAME" ] || [ -z "$(host_of "$LIVE")" ]; then
  BAD=1
  say "✘ The receiver's address must be https://<name> without a path (--live-url), not $LIVE." "✘ Địa chỉ của bộ nhận phải là https://<tên> không có đường dẫn (--live-url), không phải $LIVE."
fi
if [ -z "${BOARD:-}" ]; then
  BAD=1
  say "✘ The board's address is not known yet: add --board https://<the board's domain>." "✘ Chưa biết địa chỉ của bảng: thêm --board https://<tên miền của bảng>."
elif ! printf '%s' "$BOARD" | grep -Eq '^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$'; then
  BAD=1
  say "✘ The board's address must be https://<name> without a path (--board)." "✘ Địa chỉ của bảng phải là https://<tên> không có đường dẫn (--board)."
fi
[ "$BAD" = 1 ] && exit 1

# ---- steps 1 to 5 of docs/RECEIVER.md, section 5: checked here, never changed; what is missing is said with the line to add ----------
# ---- bước 1 tới 5 của docs/RECEIVER.vi.md, mục 5: kiểm ở đây, không bao giờ sửa; cái thiếu được nói kèm dòng cần thêm --------------
echo
say "Checking the server for the receiver on $LISTEN ($NAME):" "Kiểm máy chủ cho bộ nhận ở $LISTEN ($NAME):"
# 1. the second IP is on this machine
# 1. IP thứ hai nằm trên máy này
if ip -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -qxF "$IP"; then
  say "✔ 1. $IP is on this machine." "✔ 1. $IP nằm trên máy này."
else
  BAD=1
  say "✘ 1. $IP is not on this machine: add the second IP at the server's provider and on the network card (netplan or ip addr add), then run this again." "✘ 1. $IP không nằm trên máy này: thêm IP thứ hai ở nhà cung cấp máy chủ và trên card mạng (netplan hoặc ip addr add), rồi chạy lại."
fi
# 2. nothing else listens on that port of that IP: Caddy bound to every address takes it
# 2. không gì khác nghe cổng đó của IP đó: Caddy nghe mọi địa chỉ thì chiếm mất nó
TAKEN=$(ss -Htlnp 2>/dev/null | awk -v a="$IP:$PORT" -v b="[$IP]:$PORT" -v p=":$PORT" '{ l = $4; if (l == a || l == b || l == "0.0.0.0" p || l == "*" p || l == "[::]" p) print }' | grep -v 'ai-worker-recei' || true)
if [ -z "$TAKEN" ]; then
  say "✔ 2. Nothing else listens on $IP:$PORT." "✔ 2. Không gì khác nghe $IP:$PORT."
else
  BAD=1
  say "✘ 2. Another program listens on port $PORT of every address or of $IP:" "✘ 2. Một chương trình khác đang nghe cổng $PORT của mọi địa chỉ hoặc của $IP:"
  printf '%s\n' "$TAKEN" | sed 's/^/     /'
  FIRST_IP=$(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -vxF "$IP" | head -n 1)
  if printf '%s' "$TAKEN" | grep -q caddy; then
    say "   For Caddy: add at the top of the Caddyfile, then sudo systemctl reload caddy:" "   Với Caddy: thêm vào đầu Caddyfile, rồi sudo systemctl reload caddy:"
    printf '     {\n       default_bind %s\n     }\n     http:// {\n       bind %s\n     }\n' "${FIRST_IP:-<first IP>}" "${FIRST_IP:-<first IP>}"
  fi
fi
# 3. the name points to the second IP
# 3. tên trỏ tới IP thứ hai
if getent ahosts "$NAME" 2>/dev/null | awk '{print $1}' | grep -qxF "$IP"; then
  say "✔ 3. $NAME points to $IP." "✔ 3. $NAME trỏ tới $IP."
else
  say "! 3. $NAME does not point to $IP yet: add a DNS A record (AAAA for IPv6) $NAME → $IP. The computers cannot reach the receiver without it." "! 3. $NAME chưa trỏ tới $IP: thêm bản ghi DNS A (AAAA với IPv6) $NAME → $IP. Thiếu nó thì máy nhân viên không tới được bộ nhận."
fi
# 4. the certificate: there, readable by the receiver's account, not outside what its service may see, valid, for that name
# 4. chứng chỉ: có, tài khoản của bộ nhận đọc được, không nằm ngoài chỗ dịch vụ của nó thấy, còn hạn, đúng tên
can_read() { if command -v runuser >/dev/null 2>&1; then runuser -u ai-worker -- test -r "$1"; else su -s /bin/sh ai-worker -c "test -r '$1'"; fi; }
CERT_OK=1
for f in "$CERT" "$KEY"; do
  case "$f" in
    /home/*|/root/*|/tmp/*|/var/tmp/*|/run/user/*)
      BAD=1
      say "✘ 4. $f is in a folder the receiver's service cannot see (ProtectHome, PrivateTmp): put it under /etc, for example /etc/ai-worker-receiver/." "✘ 4. $f nằm trong thư mục dịch vụ bộ nhận không thấy (ProtectHome, PrivateTmp): đặt nó dưới /etc, ví dụ /etc/ai-worker-receiver/."; CERT_OK=0; continue ;;
    /*) ;;
    *)
      BAD=1
      say "✘ 4. $f: give the full path." "✘ 4. $f: cần đường dẫn đầy đủ."; CERT_OK=0; continue ;;
  esac
  if [ ! -f "$f" ]; then
    BAD=1
    say "✘ 4. $f is missing: get a certificate for $NAME with a tool checked over DNS (nobody answers on port 80 of $IP)." "✘ 4. Chưa có $f: lấy chứng chỉ cho $NAME bằng một công cụ kiểm qua DNS (không ai trả lời ở cổng 80 của $IP)."; CERT_OK=0
  elif ! can_read "$f"; then
    BAD=1
    say "✘ 4. The account ai-worker cannot read $f: for example chgrp ai-worker $f && chmod 640 $f (and the same after each renewal), and let it into the folders above." "✘ 4. Tài khoản ai-worker không đọc được $f: ví dụ chgrp ai-worker $f && chmod 640 $f (làm lại sau mỗi lần gia hạn), và cho nó vào được các thư mục bên trên."; CERT_OK=0
  fi
done
if [ "$CERT_OK" = 1 ]; then
  if command -v openssl >/dev/null 2>&1; then
    if ! openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null 2>&1; then
      BAD=1
      say "✘ 4. The certificate $CERT has expired or cannot be read." "✘ 4. Chứng chỉ $CERT đã hết hạn hoặc không đọc được."
    else
      if ! openssl x509 -in "$CERT" -noout -checkend 1209600 >/dev/null 2>&1; then
        say "! 4. The certificate ends within 14 days: check its renewal." "! 4. Chứng chỉ hết hạn trong vòng 14 ngày: kiểm việc gia hạn."
      fi
      if openssl x509 -in "$CERT" -noout -checkhost "$NAME" 2>/dev/null | grep -q 'does match'; then
        say "✔ 4. The certificate is valid for $NAME." "✔ 4. Chứng chỉ còn hạn và đúng tên $NAME."
      else
        BAD=1
        say "✘ 4. The certificate $CERT is not for $NAME." "✘ 4. Chứng chỉ $CERT không phải cho $NAME."
      fi
    fi
  else
    say "✔ 4. The certificate files are there (openssl is missing: expiry and name not checked)." "✔ 4. Có file chứng chỉ (thiếu openssl: chưa kiểm hạn và tên)."
  fi
fi
# 5. the firewall: said only when ufw or firewalld runs and port 443 is not open in it
# 5. tường lửa: chỉ nói khi ufw hoặc firewalld đang chạy và cổng chưa mở trong nó
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  if ufw status 2>/dev/null | awk -v p="$PORT" '/ALLOW/ { for (i = 1; i <= NF; i++) if ($i == p || $i == p "/tcp") f = 1 } END { exit !f }'; then
    say "✔ 5. ufw lets port $PORT in." "✔ 5. ufw cho cổng $PORT vào."
  else
    say "! 5. ufw is on and does not open port $PORT: sudo ufw allow proto tcp to $IP port $PORT" "! 5. ufw đang bật và chưa mở cổng $PORT: sudo ufw allow proto tcp to $IP port $PORT"
  fi
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  if firewall-cmd --list-ports 2>/dev/null | grep -qw "$PORT/tcp" || { [ "$PORT" = 443 ] && firewall-cmd --list-services 2>/dev/null | grep -qw https; }; then
    say "✔ 5. firewalld lets port $PORT in." "✔ 5. firewalld cho cổng $PORT vào."
  else
    say "! 5. firewalld is on and does not open port $PORT: sudo firewall-cmd --permanent --add-port=$PORT/tcp && sudo firewall-cmd --reload" "! 5. firewalld đang bật và chưa mở cổng $PORT: sudo firewall-cmd --permanent --add-port=$PORT/tcp && sudo firewall-cmd --reload"
  fi
else
  say "✔ 5. No ufw or firewalld runs here; open $IP:$PORT in your provider's firewall too, if it has one." "✔ 5. Không có ufw hay firewalld đang chạy; nếu nhà cung cấp có tường lửa riêng thì mở $IP:$PORT ở đó nữa."
fi
echo

if [ "$MODE" = check ]; then
  [ "$BAD" = 1 ] && exit 1
  if ours && active; then
    health 5 || exit 1
  else
    say "  The receiver's service is not running." "  Dịch vụ bộ nhận chưa chạy."
  fi
  exit 0
fi
if [ "$BAD" = 1 ]; then
  say "Nothing was started: fix what is marked ✘, then run this again. The settings are kept in $RENV." "Chưa chạy gì: sửa các mục đánh ✘, rồi chạy lại. Cấu hình đã giữ trong $RENV."
  exit 1
fi

# ---- the webhook: RECEIVER=1 and the live feed's two addresses, only where they are empty; nothing about which computers send where ---
# ---- webhook: RECEIVER=1 và hai địa chỉ của luồng trực tiếp, chỉ khi đang trống; không đụng gì tới việc máy nào gửi đi đâu -----------
WEBHOOK_CHANGED=0
if [ "$(envget "$ENV" RECEIVER)" != 1 ]; then envset "$ENV" RECEIVER 1; WEBHOOK_CHANGED=1; fi
if [ -z "$LIVE_NOW" ]; then envset "$ENV" RECEIVER_LIVE_URL "$LIVE"; WEBHOOK_CHANGED=1
elif [ -n "$A_LIVE" ] && [ "$A_LIVE" != "$LIVE_NOW" ]; then
  say "! RECEIVER_LIVE_URL in $ENV is $LIVE_NOW, not $A_LIVE: left as it is; change it there if you mean it." "! RECEIVER_LIVE_URL trong $ENV là $LIVE_NOW, không phải $A_LIVE: để nguyên; muốn đổi thì sửa ở đó."
fi
if [ -z "$BOARD_NOW" ]; then envset "$ENV" RECEIVER_BOARD_ORIGIN "$BOARD"; WEBHOOK_CHANGED=1
elif [ -n "$A_BOARD" ] && [ "$A_BOARD" != "$BOARD_NOW" ]; then
  say "! RECEIVER_BOARD_ORIGIN in $ENV is $BOARD_NOW, not $A_BOARD: left as it is; change it there if you mean it." "! RECEIVER_BOARD_ORIGIN trong $ENV là $BOARD_NOW, không phải $A_BOARD: để nguyên; muốn đổi thì sửa ở đó."
fi
chmod 600 "$ENV"
if [ "$WEBHOOK_CHANGED" = 1 ]; then
  say "Set RECEIVER=1 and the live feed's addresses in $ENV; running install.sh again (the webhook's memory ceiling grows to 45% of the machine)." "Đã đặt RECEIVER=1 và địa chỉ của luồng trực tiếp trong $ENV; chạy lại install.sh (trần bộ nhớ của webhook lên 45% bộ nhớ máy)."
  if [ -f "$HERE/install.sh" ]; then
    AI_WORKER_FROM_RECEIVER=1 bash "$HERE/install.sh" </dev/null
  else
    systemctl restart ai-worker-webhook
    say "! install.sh is not beside this file: the webhook was only restarted; run install.sh again for its memory ceiling." "! install.sh không nằm cạnh file này: webhook chỉ được khởi động lại; chạy lại install.sh để đổi trần bộ nhớ của nó."
  fi
fi
# the webhook writes the file of secrets at its start with RECEIVER=1
# webhook ghi file bí mật khi khởi động với RECEIVER=1
i=0
while [ ! -f "$SECRETS" ] && [ "$i" -lt 20 ]; do sleep 1; i=$((i + 1)); done
if [ ! -f "$SECRETS" ]; then
  say "✘ The webhook has not written $SECRETS: see 'journalctl -u ai-worker-webhook'" "✘ Webhook chưa ghi $SECRETS: xem 'journalctl -u ai-worker-webhook'"
  exit 1
fi

# ---- the program and its service -------------------------------------------------------------------------------------------------
# ---- file chạy và dịch vụ của nó ----------------------------------------------------------------------------------------------------
CHANGED=0
put_binary
if [ -n "$OLD" ]; then
  OLD_NAME=$(basename "$OLD" .service)
  systemctl disable --now "$OLD_NAME" >/dev/null 2>&1 || true
  cp -p "$OLD" "$OLD.before-install-receiver"
  [ "$OLD" != "$UNIT" ] && rm -f "$OLD"
  systemctl daemon-reload
  say "  Took over $OLD: a copy is kept as $OLD.before-install-receiver." "  Đã thay $OLD: bản cũ được giữ ở $OLD.before-install-receiver."
  CHANGED=1
fi
put_unit
start
health 30 || exit 1

echo
split_listen "$LISTEN"
HINT=https://$NAME
[ "$PORT" = 443 ] || HINT=$HINT:$PORT
if [ -n "$(envget "$ENV" RECEIVER_INGEST_URLS)" ]; then
  say "The receiver runs. RECEIVER_INGEST_URLS in $ENV is left as it was: the computers it names keep sending to the receiver." "Bộ nhận đang chạy. RECEIVER_INGEST_URLS trong $ENV được để nguyên: các máy nó chỉ định vẫn gửi tới bộ nhận."
elif [ "$FIRST" = 1 ]; then
  say "The receiver runs, and no computer sends to it yet. To try it with a few computers, add to $ENV and restart the webhook (docs/RECEIVER.md, section 5):" "Bộ nhận đang chạy, và chưa máy nào gửi tới nó. Để thử với vài máy, thêm vào $ENV rồi khởi động lại webhook (docs/RECEIVER.vi.md, mục 5):"
  printf '  RECEIVER_INGEST_URLS=%s\n  RECEIVER_INGEST_DEVICES=device-...\n  RECEIVER_CHECK_PERCENT=100\n' "$HINT"
else
  say "Updated; the settings in $RENV are unchanged." "Đã cập nhật; cấu hình trong $RENV giữ nguyên."
fi
say "Back to the program before: sudo sh install-receiver.sh --rollback. Stop it: sudo sh install-receiver.sh --remove." "Quay về file chạy trước: sudo sh install-receiver.sh --rollback. Dừng nó: sudo sh install-receiver.sh --remove."
