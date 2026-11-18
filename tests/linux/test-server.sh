#!/bin/bash
# Tries server/install.sh on a clean machine with systemd. Run with sudo from the repository root. The key is never printed.
# Thử server/install.sh trên máy sạch có systemd. Chạy bằng sudo ở thư mục gốc của repo. Không bao giờ in mã gửi.
set -u
errors=0
ENV_FILE=/etc/ai-worker.env
SERVICE=ai-worker-webhook
PORT=8788

check() {
  if eval "$2"; then
    echo "  PASS  $1"
  else
    echo "  FAIL  $1"
    errors=$((errors + 1))
  fi
}

echo '== S1 first install'
AI_WORKER_LANG=en bash server/install.sh > /tmp/server-first.txt 2>&1
RESULT=$?
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the service is active' '[ "$(systemctl is-active $SERVICE)" = active ]'
check 'it answers /health' 'curl -fsS http://127.0.0.1:$PORT/health | grep -q ok'
check 'says it is running' 'grep -q "The webhook is running" /tmp/server-first.txt'
check 'the env file is private' '[ "$(stat -c %a $ENV_FILE)" = 600 ]'
check 'the keys folder is private' '[ "$(stat -c %a /opt/ai-worker/keys)" = 700 ]'
check 'the code cannot be changed by the service' '[ "$(stat -c %U /opt/ai-worker/webhook.py)" = root ]'
check 'the server parts cannot be changed by the service' '[ "$(stat -c %U /opt/ai-worker/board)" = root ] && [ "$(stat -c %U /opt/ai-worker/board/views.py)" = root ]'
check 'the Vietnamese text is installed' '[ -f /opt/ai-worker/webhook_vi.py ]'
check 'it runs as its own user' '[ "$(systemctl show $SERVICE -p User --value)" = ai-worker ]'
check 'memory is limited' '[ "$(systemctl show $SERVICE -p MemoryMax --value)" = 1073741824 ]'
check 'threads are limited' '[ "$(systemctl show $SERVICE -p TasksMax --value)" = 512 ]'
check 'open files are limited' '[ "$(systemctl show $SERVICE -p LimitNOFILE --value)" = 4096 ]'

echo '== S2 pages in two languages'
check 'English by default' 'curl -fsS http://127.0.0.1:$PORT/ | grep -q "lang=\"en\""'
check 'Vietnamese by browser' 'curl -fsS -H "Accept-Language: vi" http://127.0.0.1:$PORT/ | grep -q "lang=\"vi\""'
check 'Vietnamese by cookie' 'curl -fsS -H "Cookie: lang=vi" http://127.0.0.1:$PORT/tv | grep -q "lang=\"vi\""'

echo '== S3 ingest'
KEY=$(sed -n 's/^INGEST_KEY=//p' "$ENV_FILE")
NOW=$(($(date +%s) * 1000))
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "{\"v\":1,\"device\":\"device-ci\",\"name\":\"CI\",\"updatedAt\":$NOW}" http://127.0.0.1:$PORT/ingest)
check 'a good report is accepted' '[ "$CODE" = 200 ]'
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Authorization: Bearer wrong' -d '{}' http://127.0.0.1:$PORT/ingest)
check 'a wrong key is refused' '[ "$CODE" = 401 ]'
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $KEY" -d '{"v":1,"device":"device-ci","updatedAt":NaN}' http://127.0.0.1:$PORT/ingest)
check 'NaN is refused' '[ "$CODE" = 400 ]'
DB=/opt/ai-worker/data/board.db
check 'the database is private' '[ "$(stat -c %a $DB)" = 600 ] && [ "$(stat -c %a $DB-wal)" = 600 ]'
check 'the accounts database is private and apart' '[ "$(stat -c %a /opt/ai-worker/keys/accounts.db)" = 600 ]'
check 'the report is in the database' '[ "$(python3 -c "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute(\"SELECT COUNT(*) FROM devices WHERE device = ?\", (\"device-ci\",)).fetchone()[0])" $DB)" = 1 ]'
# an old JSON file left by a version before SQLite is moved in at the next start and kept in legacy-json/
# file JSON cũ do bản trước SQLite để lại được chuyển vào ở lần khởi động sau và giữ trong legacy-json/
echo "{\"v\":1,\"device\":\"device-legacy\",\"name\":\"Old\",\"updatedAt\":$NOW}" > /opt/ai-worker/data/device-legacy.json
chown ai-worker: /opt/ai-worker/data/device-legacy.json

echo '== S4 update keeps the key and the data'
BEFORE=$(sha256sum "$ENV_FILE" | cut -d' ' -f1)
AI_WORKER_LANG=vi bash server/install.sh > /tmp/server-second.txt 2>&1
RESULT=$?
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the env file is unchanged' '[ "$(sha256sum "$ENV_FILE" | cut -d" " -f1)" = "$BEFORE" ]'
sleep 1
check 'the data is still there' '[ "$(python3 -c "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute(\"SELECT COUNT(*) FROM devices WHERE device IN (?, ?)\", (\"device-ci\", \"device-legacy\")).fetchone()[0])" $DB)" = 2 ]'
check 'the old JSON file is kept apart' '[ -f /opt/ai-worker/data/legacy-json/device-legacy.json ] && [ ! -f /opt/ai-worker/data/device-legacy.json ]'
check 'the key is not printed again' '! grep -qF "$KEY" /tmp/server-second.txt'
check 'the service is active' '[ "$(systemctl is-active $SERVICE)" = active ]'

echo '== S5 asking from Telegram: off, on without a token, on, off again'
BOT=ai-worker-telegram
BOT_ENV=/etc/ai-worker-telegram.env
BOT_UNIT=/etc/systemd/system/$BOT.service
# a made-up token: nothing here talks to Telegram
# một khoá bot bịa: ở đây không có gì nói chuyện với Telegram
FAKE_TOKEN='123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
bot_path() { curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $1" -H 'Content-Type: application/json' "${@:2}" -d '{"report":"ok","bot":"ci_bot"}' http://127.0.0.1:$PORT/bot/telegram; }
check 'off by default: no service, no settings file' '[ ! -f $BOT_UNIT ] && [ ! -f $BOT_ENV ]'
check 'off by default: the path is not there' '[ "$(bot_path anything)" = 404 ]'
check 'the bot file is installed and cannot be changed by a service' '[ "$(stat -c %U /opt/ai-worker/telegram_bot.py)" = root ]'

echo 'TELEGRAM_ASK=1' >> "$ENV_FILE"
AI_WORKER_LANG=en bash server/install.sh > /tmp/server-ask.txt 2>&1
RESULT=$?
check 'exit 0' '[ "$RESULT" = 0 ]'
ASK_KEY=$(sed -n 's/^TELEGRAM_ASK_KEY=//p' "$ENV_FILE")
check 'a key of 32 characters or more is made' '[ "${#ASK_KEY}" -ge 32 ]'
check 'the bot settings file is private' '[ "$(stat -c %a $BOT_ENV)" = 600 ] && [ "$(stat -c %U $BOT_ENV)" = root ]'
check 'it holds the same key and the port' 'grep -qx "TELEGRAM_ASK_KEY=$ASK_KEY" $BOT_ENV && grep -qx "PORT=$PORT" $BOT_ENV'
check 'without a token it says so and starts nothing' 'grep -q "no bot token yet" /tmp/server-ask.txt && [ ! -f $BOT_UNIT ]'
check 'the key is not printed' '! grep -qF "$ASK_KEY" /tmp/server-ask.txt'
check 'the path takes the key from this machine' '[ "$(bot_path "$ASK_KEY")" = 200 ]'
check 'it refuses another key' '[ "$(bot_path wrong)" = 401 ]'
check 'it refuses the send key' '[ "$(bot_path "$KEY")" = 401 ]'
check 'it is not there for a request a proxy passed on' '[ "$(bot_path "$ASK_KEY" -H "X-Forwarded-For: 203.0.113.9")" = 404 ]'

# with a token the process runs. Its Telegram is a closed port of this machine, so it keeps trying and reaches nothing outside
# có khoá bot thì tiến trình chạy. Telegram của nó là một cổng đóng trên chính máy này, nên nó cứ thử lại và không tới đâu bên ngoài
sed -i "s/^TELEGRAM_ASK_TOKEN=.*/TELEGRAM_ASK_TOKEN=$FAKE_TOKEN/" $BOT_ENV
echo 'TELEGRAM_API_URL=http://127.0.0.1:9' >> $BOT_ENV
AI_WORKER_LANG=en bash server/install.sh > /tmp/server-ask.txt 2>&1
RESULT=$?
sleep 3
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'the bot service is active' '[ "$(systemctl is-active $BOT)" = active ]'
check 'says it is running' 'grep -q "The Telegram bot process is running" /tmp/server-ask.txt'
check 'it runs as its own user' '[ "$(systemctl show $BOT -p User --value)" = ai-worker-telegram ]'
check 'it may reach this machine and Telegram only' 'grep -q "^IPAddressDeny=any" $BOT_UNIT && grep -q "^IPAddressAllow=localhost .*149.154.160.0/20" $BOT_UNIT'
check 'memory and threads are limited' '[ "$(systemctl show $BOT -p MemoryMax --value)" = 134217728 ] && [ "$(systemctl show $BOT -p TasksMax --value)" = 16 ]'
check 'the webhook took it' 'journalctl -u $BOT --no-pager | grep -q "the board takes this process"'
check 'the token is neither printed nor logged nor in the unit' '! grep -qF "$FAKE_TOKEN" /tmp/server-ask.txt && ! journalctl -u $BOT --no-pager | grep -qF "$FAKE_TOKEN" && ! grep -qF "$FAKE_TOKEN" $BOT_UNIT'
check 'the key is the same after the second run, once on each side' '[ "$(sed -n "s/^TELEGRAM_ASK_KEY=//p" "$ENV_FILE")" = "$ASK_KEY" ] && [ "$(grep -c "^TELEGRAM_ASK_KEY=" $BOT_ENV)" = 1 ]'
check 'the webhook is still active' '[ "$(systemctl is-active $SERVICE)" = active ]'

# the board's window inside Telegram: the installer derives the webhook's key from the token, and never writes the token there
# khung bảng bên trong Telegram: bộ cài suy ra khoá của webhook từ khoá bot, và không bao giờ ghi khoá bot vào đó
printf 'TELEGRAM_APP=1\nTELEGRAM_APP_URL=https://board.example.com/tg/app\n' >> "$ENV_FILE"
AI_WORKER_LANG=en bash server/install.sh > /tmp/server-ask.txt 2>&1
RESULT=$?
sleep 2
APP_KEY_WANT=$(printf '%s' "$FAKE_TOKEN" | python3 -c 'import hashlib, hmac, sys; print(hmac.new(b"WebAppData", sys.stdin.read().encode(), hashlib.sha256).hexdigest())')
check 'window: exit 0' '[ "$RESULT" = 0 ]'
check 'window: the key is derived from the token, written once' '[ "$(grep -c "^TELEGRAM_APP_KEY=" "$ENV_FILE")" = 1 ] && grep -qx "TELEGRAM_APP_KEY=$APP_KEY_WANT" "$ENV_FILE"'
check 'window: the token is not in the webhook settings' '! grep -qF "$FAKE_TOKEN" "$ENV_FILE"'
check 'window: the page is there' '[ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/tg/app")" = 200 ]'
sed -i '/^TELEGRAM_APP=1/d' "$ENV_FILE"
AI_WORKER_LANG=en bash server/install.sh > /dev/null 2>&1
sleep 2
check 'window off: the key is gone and so is the page' '! grep -q "^TELEGRAM_APP_KEY=" "$ENV_FILE" && [ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/tg/app")" = 404 ]'

# a list of the owner's own, then no limit
# danh sách riêng của chủ máy, rồi không giới hạn
sed -i 's#^TELEGRAM_NETS=.*#TELEGRAM_NETS=203.0.113.0/24, 2001:db8::/32#' $BOT_ENV
AI_WORKER_LANG=en bash server/install.sh > /dev/null 2>&1
check 'own networks replace the list' 'grep -q "^IPAddressAllow=localhost 203.0.113.0/24 2001:db8::/32" $BOT_UNIT && ! grep -q "149.154.160.0/20" $BOT_UNIT'
sed -i 's#^TELEGRAM_NETS=.*#TELEGRAM_NETS=any#' $BOT_ENV
AI_WORKER_LANG=en bash server/install.sh > /dev/null 2>&1
check '"any" takes the limit away' '! grep -q "^IPAddress" $BOT_UNIT && [ "$(systemctl is-active $BOT)" = active ]'

sed -i 's/^TELEGRAM_ASK=1/TELEGRAM_ASK=0/' "$ENV_FILE"
AI_WORKER_LANG=en bash server/install.sh > /tmp/server-ask.txt 2>&1
RESULT=$?
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'turned off: the service is gone' '[ ! -f $BOT_UNIT ] && [ "$(systemctl is-active $BOT)" != active ]'
check 'turned off: the path is gone' '[ "$(bot_path "$ASK_KEY")" = 404 ]'
check 'it says where the token still is' 'grep -q "$BOT_ENV" /tmp/server-ask.txt && [ -f $BOT_ENV ]'
check 'the webhook is still active' '[ "$(systemctl is-active $SERVICE)" = active ]'

rm -f /tmp/server-first.txt /tmp/server-second.txt /tmp/server-ask.txt
if [ "$errors" != 0 ]; then
  echo "$errors checks FAILED"
  journalctl -u "$SERVICE" -n 20 --no-pager | sed -E 's/(Bearer )[^ ]+/\1***/'
  journalctl -u "$BOT" -n 20 --no-pager | sed -E 's/[0-9]+:[A-Za-z0-9_-]{20,}/***/g'
  exit 1
fi
echo 'All server checks passed'
