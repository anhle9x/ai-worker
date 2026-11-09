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

rm -f /tmp/server-first.txt /tmp/server-second.txt
if [ "$errors" != 0 ]; then
  echo "$errors checks FAILED"
  journalctl -u "$SERVICE" -n 20 --no-pager | sed -E 's/(Bearer )[^ ]+/\1***/'
  exit 1
fi
echo 'All server checks passed'
