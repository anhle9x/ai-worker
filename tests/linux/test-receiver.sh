#!/bin/bash
# Tries server/install-receiver.sh on a machine with systemd: first run, run again, update through install.sh, rollback, remove, and
# taking over a service written by hand. Run with sudo from the repository root, after test-server.sh or on a clean machine.
# The receiver's program comes from server/receiver-bin/ (sh packaging/build-receiver.sh, which needs Go).
# Thử server/install-receiver.sh trên máy có systemd: lần chạy đầu, chạy lại, cập nhật qua install.sh, quay lui, gỡ, và thay một
# dịch vụ viết tay. Chạy bằng sudo ở thư mục gốc của repo, sau test-server.sh hoặc trên máy sạch.
# File chạy của bộ nhận lấy từ server/receiver-bin/ (sh packaging/build-receiver.sh, cần Go).
set -u
errors=0
ENV_FILE=/etc/ai-worker.env
RENV=/etc/ai-worker-receiver.env
SERVICE=ai-worker-receiver
UNIT=/etc/systemd/system/$SERVICE.service
BIN=/opt/ai-worker/ai-worker-receiver
# an address kept for documentation (RFC 5737), put on the loopback card for the test only, and a name only this machine knows
# một địa chỉ dành cho tài liệu (RFC 5737), chỉ gắn vào card loopback trong lúc thử, và một tên chỉ máy này biết
IP=192.0.2.10
NAME=ingest.test
TLS=/etc/ai-worker-receiver-test
HAND=/etc/systemd/system/receiver-by-hand.service
OUT=$(mktemp)

check() {
  if eval "$2"; then
    echo "  PASS  $1"
  else
    echo "  FAIL  $1"
    errors=$((errors + 1))
    echo "---- output ----"; cat "$OUT"
  fi
}
run() { AI_WORKER_LANG=en sh server/install-receiver.sh "$@" > "$OUT" 2>&1 < /dev/null; RESULT=$?; }
sum() { sha256sum "$1" | cut -d' ' -f1; }
cleanup() {
  systemctl disable --now receiver-by-hand >/dev/null 2>&1
  rm -f "$HAND" "$HAND.before-install-receiver"
  sh server/install-receiver.sh --remove >/dev/null 2>&1
  ip addr del "$IP/32" dev lo 2>/dev/null
  sed -i "/ $NAME\$/d" /etc/hosts
  rm -rf "$TLS" "$OUT" /tmp/receiver-server /tmp/receiver-caddy /etc/ai-worker-receiver
  sed -i "/ aiworker.corp.test\$/d; / ingest.corp.test\$/d" /etc/hosts
  systemctl daemon-reload
}
trap cleanup EXIT

[ -f server/receiver-bin/ai-worker-receiver-linux-amd64 ] || sh packaging/build-receiver.sh >/dev/null
[ -f "$ENV_FILE" ] || AI_WORKER_LANG=en bash server/install.sh > /dev/null 2>&1 < /dev/null
# start from a webhook without the receiver, as an office has it
# bắt đầu từ một webhook không có bộ nhận, như một văn phòng đang có
rm -f "$RENV"
sed -i '/^RECEIVER=/d; /^RECEIVER_LIVE_URL=/d; /^RECEIVER_BOARD_ORIGIN=/d' "$ENV_FILE"
AI_WORKER_LANG=en bash server/install.sh > /dev/null 2>&1 < /dev/null

# a certificate of our own for the name, readable by the receiver's account
# một chứng chỉ tự ký cho tên đó, tài khoản của bộ nhận đọc được
mkdir -p "$TLS"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 30 -subj "/CN=$NAME" -addext "subjectAltName=DNS:$NAME,DNS:ingest.corp.test" \
  -keyout "$TLS/privkey.pem" -out "$TLS/fullchain.pem" > /dev/null 2>&1
chgrp -R ai-worker "$TLS"; chmod 750 "$TLS"; chmod 640 "$TLS"/*.pem
FLAGS="--listen $IP:443 --cert $TLS/fullchain.pem --key $TLS/privkey.pem --live-url https://$NAME --board https://aiworker.example.com"

echo '== R1 nothing set up yet'
run --update
check '--update: exit 0, says nothing, writes nothing' '[ "$RESULT" = 0 ] && [ ! -s "$OUT" ] && [ ! -f "$UNIT" ]'
run --check
check '--check: exit 1' '[ "$RESULT" = 1 ] && grep -q "not set up yet" "$OUT"'
run
check 'the first run without settings stops and says what it needs' '[ "$RESULT" = 1 ] && grep -q -- "--listen IP:443" "$OUT" && [ ! -f "$RENV" ]'

echo '== R2 the second IP is missing'
run $FLAGS
check 'exit 1, starts nothing' '[ "$RESULT" = 1 ] && [ ! -f "$UNIT" ]'
check 'says the IP is not on this machine' 'grep -q "1. $IP is not on this machine" "$OUT"'
check 'says the name does not point to it' 'grep -q "3. $NAME does not point to $IP" "$OUT"'
check 'keeps the settings for the next run' '[ -f "$RENV" ] && grep -qx "RECEIVER_LISTEN=$IP:443" "$RENV"'
check 'the webhook settings are not touched' '! grep -q "^RECEIVER=1" "$ENV_FILE"'

ip addr add "$IP/32" dev lo
echo "$IP $NAME" >> /etc/hosts

echo '== R2b another program holds port 443 of every address, as Caddy does without default_bind'
python3 -m http.server 443 --bind 0.0.0.0 > /dev/null 2>&1 &
HOLDER=$!
sleep 1
run
kill "$HOLDER"; wait "$HOLDER" 2>/dev/null
check 'exit 1, starts nothing' '[ "$RESULT" = 1 ] && [ ! -f "$UNIT" ]'
check 'says who holds the port' 'grep -q "2. Another program listens on port 443" "$OUT" && grep -q python3 "$OUT"'

echo '== R3 the first install'
WEBHOOK_MEM_BEFORE=$(systemctl show ai-worker-webhook -p MemoryMax --value)
run
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the checks pass' 'grep -q "1. $IP is on this machine" "$OUT" && grep -q "2. Nothing else listens" "$OUT" && grep -q "3. $NAME points to $IP" "$OUT" && grep -q "4. The certificate is valid for $NAME" "$OUT"'
check 'the service is active' '[ "$(systemctl is-active $SERVICE)" = active ]'
check 'it runs as ai-worker, never root' '[ "$(systemctl show $SERVICE -p User --value)" = ai-worker ]'
check 'it may bind port 443 and nothing more' 'systemctl show $SERVICE -p AmbientCapabilities --value | grep -qx cap_net_bind_service && systemctl show $SERVICE -p CapabilityBoundingSet --value | grep -qx cap_net_bind_service'
MB=$(sed -n 's/^RECEIVER_MEMORY_MB=//p' "$RENV")
check 'MemoryMax a little above RECEIVER_MEMORY_MB' '[ "$(systemctl show $SERVICE -p MemoryMax --value)" = $(( (MB + MB / 10 + 64) * 1048576 )) ]'
check 'the kernel kills it before Python' '[ "$(systemctl show $SERVICE -p OOMScoreAdjust --value)" = 500 ]'
check 'its settings are private' '[ "$(stat -c %a:%U $RENV)" = 600:root ]'
check 'its program cannot be changed by the service' '[ "$(stat -c %U $BIN)" = root ]'
check 'RECEIVER=1 and the two addresses in the webhook settings' 'grep -qx "RECEIVER=1" "$ENV_FILE" && grep -qx "RECEIVER_LIVE_URL=https://$NAME" "$ENV_FILE" && grep -qx "RECEIVER_BOARD_ORIGIN=https://aiworker.example.com" "$ENV_FILE"'
check 'no computer is moved to it' '! grep -q "^RECEIVER_INGEST_URLS=." "$ENV_FILE"'
check 'the webhook wrote the file of secrets' '[ -f /opt/ai-worker/keys/receiver-secrets.json ]'
check 'the webhook got the larger memory ceiling' '[ "$(systemctl show ai-worker-webhook -p MemoryMax --value)" != "$WEBHOOK_MEM_BEFORE" ] || [ "$(awk "/^MemTotal:/ {print int(\$2 / 1024 * 45 / 100)}" /proc/meminfo)" -le 1024 ]'
check 'the receiver answers over TLS on its own address' 'curl -kfsS --resolve $NAME:443:$IP https://$NAME/health > /dev/null'
check 'says the certificate is not trusted (it is our own)' 'grep -q "does not trust its certificate" "$OUT"'
check 'says how to try it with a few computers' 'grep -q "RECEIVER_INGEST_URLS=https://$NAME" "$OUT"'
check 'the webhook is still active' '[ "$(systemctl is-active ai-worker-webhook)" = active ]'

echo '== R4 run again: nothing changes'
RENV_SUM=$(sum "$RENV"); ENV_SUM=$(sum "$ENV_FILE"); UNIT_SUM=$(sum "$UNIT"); PID=$(systemctl show $SERVICE -p MainPID --value)
run
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'both settings files and the service are unchanged' '[ "$(sum "$RENV")" = "$RENV_SUM" ] && [ "$(sum "$ENV_FILE")" = "$ENV_SUM" ] && [ "$(sum "$UNIT")" = "$UNIT_SUM" ]'
check 'the receiver was not restarted' '[ "$(systemctl show $SERVICE -p MainPID --value)" = "$PID" ]'
check 'no program before is made' '[ ! -f "$BIN.prev" ]'
run --check
check '--check: exit 0 and changes nothing' '[ "$RESULT" = 0 ] && [ "$(sum "$RENV")" = "$RENV_SUM" ] && [ "$(sum "$UNIT")" = "$UNIT_SUM" ]'

echo '== R5 a new version through install.sh'
# a copy of server/ whose program differs by one byte at its end, as a new version would differ
# một bản server/ có file chạy khác một byte ở cuối, như một bản mới sẽ khác
rm -rf /tmp/receiver-server; cp -R server /tmp/receiver-server
for f in /tmp/receiver-server/receiver-bin/ai-worker-receiver-linux-*; do printf 'x' >> "$f"; done
(cd /tmp/receiver-server/receiver-bin && sha256sum ai-worker-receiver-linux-* > SHA256SUMS)
OLD_SUM=$(sum "$BIN")
AI_WORKER_LANG=en bash /tmp/receiver-server/install.sh > "$OUT" 2>&1 < /dev/null
RESULT=$?
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the new program is in place, the one before kept' '[ "$(sum "$BIN")" != "$OLD_SUM" ] && [ "$(sum "$BIN.prev")" = "$OLD_SUM" ]'
check 'the receiver runs it' '[ "$(systemctl is-active $SERVICE)" = active ] && curl -kfsS --resolve $NAME:443:$IP https://$NAME/health > /dev/null'
check 'its settings are unchanged' '[ "$(sum "$RENV")" = "$RENV_SUM" ]'
printf 'y' >> /tmp/receiver-server/receiver-bin/ai-worker-receiver-linux-amd64; printf 'y' >> /tmp/receiver-server/receiver-bin/ai-worker-receiver-linux-arm64
NEW_SUM=$(sum "$BIN")
AI_WORKER_LANG=en sh /tmp/receiver-server/install-receiver.sh --update > "$OUT" 2>&1 < /dev/null
RESULT=$?
check 'a program that does not match SHA256SUMS is refused' '[ "$RESULT" = 1 ] && grep -q "does not match" "$OUT" && [ "$(sum "$BIN")" = "$NEW_SUM" ]'

echo '== R6 back to the program before'
run --rollback
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the program before is in place' '[ "$(sum "$BIN")" = "$OLD_SUM" ] && [ "$(sum "$BIN.prev")" = "$NEW_SUM" ]'
check 'the receiver runs' '[ "$(systemctl is-active $SERVICE)" = active ]'

echo '== R7 remove'
run --remove
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the service is gone' '[ ! -f "$UNIT" ] && [ "$(systemctl is-active $SERVICE)" != active ]'
check 'nothing listens on the second IP' '! curl -kfsS --max-time 2 --resolve $NAME:443:$IP https://$NAME/health > /dev/null 2>&1'
check 'the settings are kept' '[ -f "$RENV" ] && grep -qx "RECEIVER=1" "$ENV_FILE"'
check 'the webhook is still active' '[ "$(systemctl is-active ai-worker-webhook)" = active ]'
run --update
check '--update does nothing once removed' '[ "$RESULT" = 0 ] && [ ! -f "$UNIT" ]'

echo '== R8 a service written by hand, as the trial had'
rm -f "$RENV" "$BIN.prev"
cat > "$HAND" <<EOF
[Unit]
Description=receiver by hand
[Service]
Environment=RECEIVER_LISTEN=$IP:443 RECEIVER_TLS_CERT=$TLS/fullchain.pem
Environment="RECEIVER_TLS_KEY=$TLS/privkey.pem" "RECEIVER_SECRETS_FILE=/opt/ai-worker/keys/receiver-secrets.json"
Environment=RECEIVER_BATCH_MS=2000
ExecStart=$BIN
User=ai-worker
AmbientCapabilities=CAP_NET_BIND_SERVICE
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload; systemctl start receiver-by-hand; sleep 2
check 'the service by hand runs' '[ "$(systemctl is-active receiver-by-hand)" = active ]'
run --live-url "https://$NAME" --board https://aiworker.example.com
check 'it is left alone without --take-over' '[ "$RESULT" = 1 ] && grep -q "written by hand is here: $HAND" "$OUT" && [ "$(systemctl is-active receiver-by-hand)" = active ] && [ ! -f "$UNIT" ]'
run --take-over --live-url "https://$NAME" --board https://aiworker.example.com
check '--take-over: exit 0' '[ "$RESULT" = 0 ]'
check 'its settings are taken' 'grep -qx "RECEIVER_LISTEN=$IP:443" "$RENV" && grep -qx "RECEIVER_TLS_KEY=$TLS/privkey.pem" "$RENV" && grep -qx "RECEIVER_BATCH_MS=2000" "$RENV"'
check 'the service by hand is stopped, its file kept beside' '[ ! -f "$HAND" ] && [ -f "$HAND.before-install-receiver" ] && [ "$(systemctl is-active receiver-by-hand)" != active ]'
check 'the installer'"'"'s service runs instead' '[ "$(systemctl is-active $SERVICE)" = active ] && curl -kfsS --resolve $NAME:443:$IP https://$NAME/health > /dev/null'

echo '== R9 a service by hand whose settings file has the installer'"'"'s own name, as the trial on a real server had'
run --remove
rm -f "$BIN.prev" "$HAND.before-install-receiver"
sed -i '/^RECEIVER_LIVE_URL=/d; /^RECEIVER_BOARD_ORIGIN=/d' "$ENV_FILE"
printf 'RECEIVER_LISTEN=%s:443\nRECEIVER_TLS_CERT=%s/fullchain.pem\nRECEIVER_TLS_KEY=%s/privkey.pem\nRECEIVER_SECRETS_FILE=/opt/ai-worker/keys/receiver-secrets.json\nRECEIVER_BATCH_MS=3000\n' "$IP" "$TLS" "$TLS" > "$RENV"
cat > "$HAND" <<EOF
[Service]
EnvironmentFile=$RENV
ExecStart=$BIN
User=ai-worker
AmbientCapabilities=CAP_NET_BIND_SERVICE
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload; systemctl start receiver-by-hand; sleep 2
run --take-over
check 'without the addresses it stops and says which flags to add' '[ "$RESULT" = 1 ] && grep -q "add --live-url https://ingest" "$OUT" && grep -q "not known yet: add --board" "$OUT" && [ "$(systemctl is-active receiver-by-hand)" = active ]'
run --take-over --live-url "https://$NAME" --board https://aiworker.example.com
check '--take-over with them: exit 0' '[ "$RESULT" = 0 ]'
check 'the file by hand is kept and filled in' 'grep -qx "RECEIVER_BATCH_MS=3000" "$RENV" && grep -qx "RECEIVER_NAME=$NAME" "$RENV" && grep -q "^RECEIVER_MEMORY_MB=[0-9]" "$RENV" && grep -q "^RECEIVER_WEBHOOK=http://127.0.0.1:" "$RENV"'
check 'the installer'"'"'s service runs instead' '[ ! -f "$HAND" ] && [ "$(systemctl is-active $SERVICE)" = active ] && curl -kfsS --resolve $NAME:443:$IP https://$NAME/health > /dev/null'

echo '== R10 the first run with questions: the answers are guessed from this machine, Enter takes each'
run --remove
rm -f "$RENV" "$BIN.prev" "$HAND.before-install-receiver"
# the address of the window inside Telegram, which test-server.sh leaves behind, would be taken for the board's before Caddy is read
# địa chỉ của khung trong Telegram, do test-server.sh để lại, sẽ được lấy làm địa chỉ của bảng trước khi đọc tới Caddy
sed -i '/^RECEIVER_LIVE_URL=/d; /^RECEIVER_BOARD_ORIGIN=/d; /^TELEGRAM_APP_URL=/d' "$ENV_FILE"
# the board's own address is this machine's first address; its Caddy site passes to the webhook's port; the certificate is in a usual folder
# địa chỉ của bảng là địa chỉ đầu của máy này; trang Caddy của nó chuyển tới cổng của webhook; chứng chỉ nằm ở một thư mục quen thuộc
OWN_IP=$(ip -o -4 addr show scope global | awk '$2 !~ /^(lo|docker|br-|veth)/ {print $4}' | head -n 1 | cut -d/ -f1)
echo "$OWN_IP aiworker.corp.test" >> /etc/hosts
echo "$IP ingest.corp.test" >> /etc/hosts
mkdir -p /tmp/receiver-caddy /etc/ai-worker-receiver
PORT_NOW=$(sed -n 's/^PORT=//p' "$ENV_FILE"); PORT_NOW=${PORT_NOW:-8788}
printf 'other.example.com {\n\treverse_proxy 127.0.0.1:1\n}\naiworker.corp.test {\n\t# reverse_proxy 127.0.0.1:1\n\treverse_proxy 127.0.0.1:%s\n}\n' "$PORT_NOW" > /tmp/receiver-caddy/aiworker.caddy
cp "$TLS"/fullchain.pem "$TLS"/privkey.pem /etc/ai-worker-receiver/
chgrp -R ai-worker /etc/ai-worker-receiver; chmod 750 /etc/ai-worker-receiver; chmod 640 /etc/ai-worker-receiver/*.pem
printf '\n\n\n\n\nn\n' | AI_WORKER_LANG=en AI_WORKER_ASK=1 AI_WORKER_CADDY_DIR=/tmp/receiver-caddy sh server/install-receiver.sh > "$OUT" 2>&1
RESULT=$?
check 'the guesses are shown: the board from Caddy, the other address on 443, ingest.<domain>, the certificate found' 'grep -q "dashboard people open: *https://aiworker.corp.test" "$OUT" && grep -q "receiver listens on: *$IP:443" "$OUT" && grep -q "will send to: *https://ingest.corp.test" "$OUT" && grep -q "Certificate and key: */etc/ai-worker-receiver/fullchain.pem, /etc/ai-worker-receiver/privkey.pem" "$OUT"'
check 'n at the end stops with nothing changed' '[ "$RESULT" = 0 ] && grep -q "nothing was changed" "$OUT" && [ ! -f "$RENV" ] && [ ! -f "$UNIT" ]'
printf '\n\n\n\n\n\n' | AI_WORKER_LANG=en AI_WORKER_ASK=1 AI_WORKER_CADDY_DIR=/tmp/receiver-caddy sh server/install-receiver.sh > "$OUT" 2>&1
RESULT=$?
check 'Enter six times sets it up' '[ "$RESULT" = 0 ] && [ "$(systemctl is-active $SERVICE)" = active ]'
check 'with the guessed settings' 'grep -qx "RECEIVER_LISTEN=$IP:443" "$RENV" && grep -qx "RECEIVER_NAME=ingest.corp.test" "$RENV" && grep -qx "RECEIVER_BOARD_ORIGIN=https://aiworker.corp.test" "$ENV_FILE" && grep -qx "RECEIVER_LIVE_URL=https://ingest.corp.test" "$ENV_FILE"'
check 'the receiver answers under the guessed name' 'curl -kfsS --resolve ingest.corp.test:443:$IP https://ingest.corp.test/health > /dev/null'
run --remove
rm -f "$RENV"
sed -i '/^RECEIVER_LIVE_URL=/d; /^RECEIVER_BOARD_ORIGIN=/d' "$ENV_FILE"
printf '\n\ningest.test\n\n\n\n' | AI_WORKER_LANG=en AI_WORKER_ASK=1 AI_WORKER_CADDY_DIR=/tmp/receiver-caddy sh server/install-receiver.sh > "$OUT" 2>&1
RESULT=$?
check 'a typed sub-domain wins over the guess, and gets https:// in front' '[ "$RESULT" = 0 ] && grep -qx "RECEIVER_NAME=ingest.test" "$RENV" && grep -qx "RECEIVER_LIVE_URL=https://ingest.test" "$ENV_FILE"'

if [ "$errors" != 0 ]; then
  echo "$errors checks FAILED"
  journalctl -u "$SERVICE" -n 20 --no-pager
  exit 1
fi
echo 'All receiver install checks passed'
