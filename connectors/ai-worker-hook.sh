#!/bin/sh
# AI Worker connector: lets Codex, Cursor and Gemini CLI show on the AI Worker board.
# Bộ nối AI Worker: cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker.
#
# Each tool runs this file as a hook:  ai-worker-hook.sh <tool> <event>
# Mỗi công cụ chạy file này như một hook:  ai-worker-hook.sh <tool> <event>
#   tool   codex | cursor | gemini
#   event  start | prompt | ask | tool | reply | stop | end
#
# It keeps one line per open session in a small file on this computer, then sends the board
# three numbers per tool: sessions open, working, waiting for the person.
# Nó giữ mỗi phiên đang mở một dòng trong một file nhỏ trên máy này, rồi gửi lên bảng
# ba con số cho mỗi công cụ: số phiên đang mở, đang làm, đang chờ người dùng.
#
# What leaves this computer: the name and email typed at install, a random device id, the time
# and those numbers. Never the prompt, the answer, a file name, a folder or a project name.
# Thứ rời khỏi máy này: tên và email gõ lúc cài, một mã máy ngẫu nhiên, thời điểm
# và các con số đó. Không bao giờ có câu hỏi, câu trả lời, tên file, thư mục hay tên dự án.
#
# The tool hands the hook its event as JSON. This file reads two things from it: the session id,
# which stays on this computer, and whether the tool's last message ends with a question mark,
# which decides between "waiting" and "idle". The message itself is not kept anywhere.
# Công cụ đưa cho hook sự kiện của nó dưới dạng JSON. File này đọc hai thứ trong đó: mã phiên,
# chỉ nằm trên máy này, và việc câu cuối của công cụ có kết thúc bằng dấu hỏi hay không,
# để chọn giữa "đang chờ" và "rảnh". Bản thân câu đó không được lưu ở đâu cả.
#
# Needs only sh, awk, sed, grep and curl (or wget): no Python, no Node.
# Chỉ cần sh, awk, sed, grep và curl (hoặc wget): không cần Python, không cần Node.

tool=$1
event=$2
DIR=${AI_WORKER_CONNECTOR_DIR:-$HOME/.local/share/ai-worker/connector}
# a session with no event for this long is no longer counted; the server keeps a report for the same time
# phiên không có sự kiện nào trong ngần này thì thôi không tính; máy chủ giữ một báo cáo cũng trong ngần đó
SESSION_SECONDS=7200
# with nothing changed, send again after this long, so the board knows the computer is still there
# không có gì đổi thì sau ngần này gửi lại, để bảng biết máy vẫn còn đó
RESEND_SECONDS=300

# Answer the tool first, so a slow network never holds it up. Codex wants nothing on stdout;
# Gemini CLI and Cursor read JSON, and Cursor sends the prompt only when told to continue.
# Trả lời công cụ trước, để mạng chậm không bao giờ giữ chân nó. Codex không muốn gì trên stdout;
# Gemini CLI và Cursor đọc JSON, và Cursor chỉ gửi câu hỏi khi được bảo tiếp tục.
case "$tool:$event" in
  *:send) ;;
  cursor:prompt) printf '{"continue":true}\n' ;;
  cursor:* | gemini:*) printf '{}\n' ;;
esac

case "$tool" in codex | cursor | gemini) ;; *) exit 0 ;; esac
case "$event" in start | prompt | ask | tool | reply | stop | end | send) ;; *) exit 0 ;; esac
[ -r "$DIR/config" ] || exit 0

# take a lock by making a folder, which only one process can do; a lock left behind by a killed process is removed after a minute
# lấy khoá bằng cách tạo một thư mục, việc chỉ một tiến trình làm được; khoá do tiến trình bị dừng để lại thì bỏ sau một phút
take_lock() {
  tries=0
  while ! mkdir "$1" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -ge "$2" ]; then
      [ -n "$(find "$1" -maxdepth 0 -mmin +1 2>/dev/null)" ] || return 1
      rmdir "$1" 2>/dev/null
      tries=0
    fi
    sleep 0.1 2>/dev/null || sleep 1
  done
}

# the number of sessions per tool that are still counted, as "tool open working waiting" lines
# số phiên còn được tính của từng công cụ, thành các dòng "tool open working waiting"
count_sessions() {
  awk -v now="$1" -v keep="$SESSION_SECONDS" '
    now - $4 < keep { open[$1]++; if ($3 == "working") working[$1]++; if ($3 == "waiting") waiting[$1]++ }
    END { for (t in open) print t, open[t], working[t] + 0, waiting[t] + 0 }' "$DIR/sessions" 2>/dev/null | sort
}

send_report() {
  url='' key='' name='' account=''
  while IFS='=' read -r k v; do
    case "$k" in url) url=$v ;; key) key=$v ;; name) name=$v ;; account) account=$v ;; esac
  done < "$DIR/config"
  [ -n "$url" ] && [ -n "$key" ] || return 0
  device=$(cat "$DIR/device" 2>/dev/null)
  case "$device" in
    device-*) ;;
    *)
      device=device-$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 16)
      printf '%s\n' "$device" > "$DIR/device"
      ;;
  esac
  take_lock "$DIR/send.lock" 100 || return 0
  round=0
  while [ "$round" -lt 3 ]; do
    round=$((round + 1))
    now=$(date +%s)
    counts=$(count_sessions "$now")
    signature=$(printf '%s' "$counts" | tr '\n' ';')
    sent_at=0 sent_signature=''
    [ -r "$DIR/sent" ] && IFS=' ' read -r sent_at sent_signature < "$DIR/sent"
    [ "$signature" = "$sent_signature" ] && [ $((now - sent_at)) -lt "$RESEND_SECONDS" ] && break
    tools=$(printf '%s\n' "$counts" | awk 'NF == 4 { printf "%s\"%s\":{\"openSessions\":%d,\"working\":%d,\"waiting\":%d}", sep, $1, $2, $3, $4; sep = "," }')
    totals=$(printf '%s\n' "$counts" | awk 'NF == 4 { o += $2; w += $3; q += $4 } END { printf "\"openSessions\":%d,\"working\":%d,\"waiting\":%d", o, w, q }')
    printf '{"v":1,"device":"%s","name":"%s","account":"%s","updatedAt":%s000,%s,"tools":{%s}}' \
      "$device" "$(printf '%s' "$name" | tr -d '"\\\000-\037')" "$(printf '%s' "$account" | tr -d '"\\\000-\037')" "$now" "$totals" "$tools" > "$DIR/report.json"
    code=''
    # this computer's own key once the server has given it one, else the key of the install package
    # khoá riêng của máy này khi máy chủ đã cấp, nếu không thì khoá của gói cài
    send_key=$key
    own=$(cat "$DIR/device-key" 2> /dev/null)
    case "$own" in awd1.*) send_key=$own ;; esac
    rm -f "$DIR/answer"
    if command -v curl > /dev/null 2>&1; then
      # the key goes in through stdin, so it never shows in the list of running programs
      # khoá đi vào qua stdin, nên không bao giờ hiện trong danh sách chương trình đang chạy
      code=$( (umask 077 && printf 'header = "Authorization: Bearer %s"\n' "$send_key" | curl -K - -sS -m 8 -o "$DIR/answer" -w '%{http_code}' \
        -H 'Content-Type: application/json' --data-binary "@$DIR/report.json" "$url/ingest" 2> /dev/null))
    elif command -v wget > /dev/null 2>&1; then
      (umask 077 && printf 'header = Authorization: Bearer %s\n' "$send_key" > "$DIR/wgetrc")
      (umask 077 && wget --config="$DIR/wgetrc" -q -O "$DIR/answer" --timeout=8 --tries=1 --header='Content-Type: application/json' \
        --post-file="$DIR/report.json" "$url/ingest" 2> /dev/null) && code=200
      # wget gives no status on a refusal: an answer that names a key problem counts as 401
      # wget không cho mã khi bị từ chối: câu trả lời nói về lỗi khoá được coi là 401
      [ -z "$code" ] && grep -q 'key\|signature' "$DIR/answer" 2> /dev/null && code=401
      rm -f "$DIR/wgetrc"
    fi
    # a key of its own in the answer: kept where only this user can read it, used from the next send on
    # khoá riêng trong câu trả lời: cất nơi chỉ người dùng này đọc được, dùng từ lần gửi sau
    given=$(sed -n 's/.*"deviceKey": *"\(awd1\.[A-Za-z0-9._-]*\)".*/\1/p' "$DIR/answer" 2> /dev/null | head -n 1)
    [ -n "$given" ] && (umask 077 && printf '%s\n' "$given" > "$DIR/device-key")
    # its own key refused (too old, or the server was set up again): drop it, so the next send asks for a new one
    # khoá riêng bị từ chối (quá cũ, hoặc máy chủ được cài lại): bỏ nó, để lần gửi sau xin khoá mới
    [ "$code" = 401 ] && [ "$send_key" != "$key" ] && rm -f "$DIR/device-key"
    rm -f "$DIR/answer"
    if [ "$code" = 200 ]; then
      printf '%s %s\n' "$now" "$signature" > "$DIR/sent"
      rm -f "$DIR/last-error"
    else
      # kept for the person looking into a board that stays empty: the time and the server's answer, nothing else
      # giữ lại cho người tìm hiểu vì sao bảng vẫn trống: thời điểm và câu trả lời của máy chủ, không gì khác
      printf '%s http=%s\n' "$now" "${code:-none}" > "$DIR/last-error"
      break
    fi
  done
  rmdir "$DIR/send.lock" 2> /dev/null
}

if [ "$event" = send ]; then
  send_report
  exit 0
fi

input=''
[ -t 0 ] || input=$(cat)
exec > /dev/null 2>&1

# the first value of a text field in the event; an id is cut down to plain characters before it is used
# giá trị đầu tiên của một trường chữ trong sự kiện; mã được lược còn ký tự thường trước khi dùng
text_field() {
  printf '%s' "$input" | tr '\n' ' ' | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"\\\\]*\"" | head -n 1 |
    sed 's/^[^:]*:[[:space:]]*"//; s/"$//' | LC_ALL=C tr -cd 'A-Za-z0-9_.-' | cut -c 1-64
}

# whether a text field ends with a question mark, allowing for the line breaks and marks that may follow it
# một trường chữ có kết thúc bằng dấu hỏi hay không, tính cả các dấu xuống dòng và ký hiệu có thể đứng sau
ends_with_question() {
  printf '%s' "$input" | tr '\n' ' ' | LC_ALL=C grep -Eq "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*(\\?|？)([[:space:]*_\`)]|\\\\[nrt\"])*\""
}

case "$tool" in
  codex) session=$(text_field session_id) reply_field=last_assistant_message ;;
  gemini) session=$(printf '%s' "${GEMINI_SESSION_ID:-}" | LC_ALL=C tr -cd 'A-Za-z0-9_.-' | cut -c 1-64) reply_field=prompt_response
    [ -n "$session" ] || session=$(text_field session_id) ;;
  cursor) session=$(text_field conversation_id) reply_field=text ;;
esac
[ -n "$session" ] || session=unknown
asked=0
case "$event" in reply | stop) ends_with_question "$reply_field" && asked=1 ;; esac

take_lock "$DIR/state.lock" 30 || exit 0
touch "$DIR/sessions"
# One line per session: tool, session id, state, time of the last event, and a mark: 1 when its last message asked
# something, 2 when it is waiting for an approval.
# start opens a session; prompt means working; ask means the tool wants an approval; tool means the approved step ran;
# reply notes a question; stop ends the turn: waiting when a question is open, idle when not; end closes the session.
# Mỗi phiên một dòng: công cụ, mã phiên, trạng thái, thời điểm sự kiện cuối, và một dấu: 1 khi câu cuối của nó có hỏi,
# 2 khi nó đang chờ duyệt.
# start mở một phiên; prompt là đang làm; ask là công cụ xin duyệt; tool là bước được duyệt đã chạy;
# reply ghi nhận một câu hỏi; stop kết thúc lượt: đang chờ khi còn câu hỏi, rảnh khi không; end đóng phiên.
awk -v tool="$tool" -v session="$session" -v event="$event" -v asked="$asked" -v now="$(date +%s)" -v keep="$SESSION_SECONDS" '
  function next_state(state, mark) {
    if (event == "prompt") { state = "working"; mark = 0 }
    else if (event == "ask") { state = "waiting"; mark = 2 }
    else if (event == "tool") { if (state == "waiting" && mark == 2) { state = "working"; mark = 0 } }
    else if (event == "reply") { mark = asked }
    else if (event == "stop") { state = (asked == 1 || mark == 1) ? "waiting" : "idle"; mark = 0 }
    print tool, session, state, now, mark
  }
  now - $4 >= keep { next }
  $1 == tool && $2 == session { seen = 1; if (event != "end") next_state($3, $5); next }
  { print }
  END { if (!seen && event != "end") next_state("idle", 0) }' "$DIR/sessions" > "$DIR/sessions.new" && mv "$DIR/sessions.new" "$DIR/sessions"
rmdir "$DIR/state.lock" 2> /dev/null

# send in the background, cut off from the tool, so the hook returns at once
# gửi ở nền, tách hẳn khỏi công cụ, để hook trả về ngay
"$0" "$tool" send < /dev/null > /dev/null 2>&1 &
exit 0
