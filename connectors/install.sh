#!/bin/bash
# Show Codex, Cursor and Gemini CLI on the AI Worker board, on macOS and Linux. Claude Code is not needed.
# Cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker, trên macOS và Linux. Không cần có Claude Code.
#
#   bash install.sh                        asks what it needs
#   bash install.sh --uninstall            takes everything out again
#   bash install.sh --status               shows what is installed and what the board last answered
#   bash install.sh                        hỏi những gì nó cần
#   bash install.sh --uninstall            gỡ sạch mọi thứ
#   bash install.sh --status               cho biết đã cài gì và lần gần nhất bảng trả lời gì
#
# Options, so it can run without asking: --server URL  --key KEY  --name NAME  --account EMAIL
#   --tools codex,cursor,gemini  --skills | --no-skills
# Tuỳ chọn, để chạy không cần hỏi: --server URL  --key KEY  --name NAME  --account EMAIL
#   --tools codex,cursor,gemini  --skills | --no-skills
#
# It adds its hooks to each tool's own settings and leaves every other line of them alone; a copy of the file
# as it was is kept next to it, ending in .ai-worker-backup.
# Nó thêm hook của mình vào cấu hình của từng công cụ và để nguyên mọi dòng khác; một bản sao của file
# như lúc trước được giữ ngay bên cạnh, tên kết thúc bằng .ai-worker-backup.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
for f in "$HERE/../../lang.sh" "$HERE/../packaging/lang.sh" "$HERE/lang.sh"; do
  [ -f "$f" ] && . "$f" && break
done
command -v say > /dev/null 2>&1 || say() { printf '%s\n' "$1"; }

DIR="${AI_WORKER_CONNECTOR_DIR:-$HOME/.local/share/ai-worker/connector}"
HOOK="$DIR/ai-worker-hook.sh"
SKILLS_DIR="$HOME/.agents/skills"
# skills that work in any of these tools; make-skill and improve-codebase-architecture lean on Claude Code and stay out
# các skill chạy được trong mọi công cụ này; make-skill và improve-codebase-architecture dựa vào Claude Code nên không chép
PORTABLE_SKILLS="browser-testing-with-devtools codebase-design diagnosing-bugs domain-modeling draw-flow grilling handoff interview-me lesson-generator meeting-notes qa-site qa-test security-audit tdd ui-ux-pro-max write-spec"
MARK="ai-worker-hook"
TOML_BEGIN="# >>> ai-worker connector: added by connectors/install.sh, removed by install.sh --uninstall >>>"
TOML_END="# <<< ai-worker connector <<<"

ACTION=install SERVER="" KEY="" NAME="" ACCOUNT="" TOOLS="" SKILLS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) ACTION=uninstall ;;
    --status) ACTION=status ;;
    --server) SERVER="${2:-}"; shift ;;
    --key) KEY="${2:-}"; shift ;;
    --name) NAME="${2:-}"; shift ;;
    --account) ACCOUNT="${2:-}"; shift ;;
    --tools) TOOLS="${2:-}"; shift ;;
    --skills) SKILLS=yes ;;
    --no-skills) SKILLS=no ;;
    *)
      say "Unknown option: $1" "Tuỳ chọn không rõ: $1"
      exit 2
      ;;
  esac
  shift
done

# one value from a small JSON file, read without a JSON program: good enough for the two files the installers write
# một giá trị trong file JSON nhỏ, đọc không cần chương trình JSON: đủ dùng cho hai file do bộ cài ghi ra
json_value() { sed -n 's/.*"'"$2"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" 2> /dev/null | head -n 1; }
config_value() { sed -n "s/^$1=//p" "$DIR/config" 2> /dev/null | head -n 1; }
clean() { printf '%s' "$1" | tr -d '"\\' | tr '[:cntrl:]' ' ' | sed 's/^ *//; s/ *$//'; }

# the JSON merge needs a program that reads JSON: macOS always has one, elsewhere Node does it
# việc gộp JSON cần một chương trình đọc được JSON: macOS luôn có sẵn, nơi khác thì dùng Node
merge_json() {
  if [ "$(uname -s)" = Darwin ] && [ -x /usr/bin/osascript ]; then
    /usr/bin/osascript -l JavaScript "$HERE/merge-hooks.js" "$@"
  elif command -v node > /dev/null 2>&1; then
    node "$HERE/merge-hooks.js" "$@"
  else
    return 3
  fi
}

# the command a tool runs for one event
# lệnh một công cụ chạy cho một sự kiện
hook_command() { printf '\\"%s\\" %s %s' "$HOOK" "$1" "$2"; }

# The events of each tool and what they mean here: "ToolEvent=ours". Ours: start, prompt, ask, tool, reply, stop, end.
# Các sự kiện của từng công cụ và nghĩa của chúng ở đây: "SựKiệnCủaCôngCụ=của ta". Của ta: start, prompt, ask, tool, reply, stop, end.
# Codex sends no Stop when the person cuts a turn short with Esc: seen in a real session, so Interrupt ends the turn here too.
# Codex không gửi Stop khi người dùng bấm Esc cắt ngang một lượt: đã thấy trong phiên thật, nên ở đây Interrupt cũng kết thúc lượt.
events_of() {
  case "$1" in
    codex) echo "SessionStart=start UserPromptSubmit=prompt PermissionRequest=ask PostToolUse=tool Stop=stop Interrupt=stop SessionEnd=end" ;;
    gemini) echo "SessionStart=start BeforeAgent=prompt Notification=ask AfterTool=tool AfterAgent=stop SessionEnd=end" ;;
    cursor) echo "sessionStart=start beforeSubmitPrompt=prompt afterAgentResponse=reply stop=stop sessionEnd=end" ;;
  esac
}

# Codex gives the hooks of these two events 3 seconds at most
# Codex cho hook của hai sự kiện này nhiều nhất 3 giây
codex_timeout() {
  case "$1" in SessionEnd | Interrupt) echo 3 ;; *) echo 5 ;; esac
}

# our hooks alone, in the shape the tool's settings file wants
# riêng các hook của ta, đúng dạng file cấu hình của công cụ đó cần
our_json() {
  local tool="$1" sep="" pair event ours
  [ "$tool" = cursor ] && printf '{\n  "version": 1,\n  "hooks": {' || printf '{\n  "hooks": {'
  for pair in $(events_of "$tool"); do
    event="${pair%%=*}" ours="${pair##*=}"
    case "$tool" in
      codex) printf '%s\n    "%s": [{ "hooks": [{ "type": "command", "command": "%s", "timeout": %s }] }]' "$sep" "$event" "$(hook_command codex "$ours")" "$(codex_timeout "$event")" ;;
      gemini) printf '%s\n    "%s": [{ "hooks": [{ "name": "ai-worker-%s", "type": "command", "command": "%s", "timeout": 5000 }] }]' "$sep" "$event" "$ours" "$(hook_command gemini "$ours")" ;;
      cursor) printf '%s\n    "%s": [{ "command": "%s", "timeout": 5 }]' "$sep" "$event" "$(hook_command cursor "$ours")" ;;
    esac
    sep=","
  done
  printf '\n  }\n}\n'
}

our_toml() {
  local pair event ours
  printf '%s\n' "$TOML_BEGIN"
  for pair in $(events_of codex); do
    event="${pair%%=*}" ours="${pair##*=}"
    printf "[[hooks.%s]]\n[[hooks.%s.hooks]]\ntype = \"command\"\ncommand = '\"%s\" codex %s'\ntimeout = %s\n" "$event" "$event" "$HOOK" "$ours" "$(codex_timeout "$event")"
  done
  printf '%s\n' "$TOML_END"
}

settings_file() {
  case "$1" in
    codex) echo "${CODEX_HOME:-$HOME/.codex}/hooks.json" ;;
    gemini) echo "$HOME/.gemini/settings.json" ;;
    cursor) echo "$HOME/.cursor/hooks.json" ;;
  esac
}

tool_name() {
  case "$1" in codex) echo "Codex" ;; gemini) echo "Gemini CLI" ;; cursor) echo "Cursor" ;; esac
}

tool_found() {
  case "$1" in
    codex) command -v codex > /dev/null 2>&1 || [ -d "${CODEX_HOME:-$HOME/.codex}" ] ;;
    gemini) command -v gemini > /dev/null 2>&1 || [ -d "$HOME/.gemini" ] ;;
    cursor) command -v cursor > /dev/null 2>&1 || command -v cursor-agent > /dev/null 2>&1 || [ -d "$HOME/.cursor" ] ;;
  esac
}

keep_backup() { [ -f "$1" ] && [ ! -f "$1.ai-worker-backup" ] && cp -p "$1" "$1.ai-worker-backup"; return 0; }

# config.toml without our block, and without the empty line the installer put in front of it
# config.toml không có khối của ta, và không có dòng trống mà bộ cài đặt trước khối đó
without_toml_block() {
  awk -v b="$TOML_BEGIN" -v e="$TOML_END" '
    $0 == b { skip = 1; held = 0 }
    !skip { if (held) print ""; held = 0; if ($0 == "") held = 1; else print }
    $0 == e { skip = 0 }
    END { if (held) print "" }' "$1"
}

# print the hooks for the person to paste in by hand, when the file cannot be changed safely
# in các hook ra để người dùng tự dán vào, khi không sửa file một cách an toàn được
by_hand() {
  say "  Could not change $2 safely. Add these hooks to it by hand, next to what is already there:" "  Không sửa $2 một cách an toàn được. Hãy tự thêm các hook này vào file, bên cạnh những gì đã có:"
  our_json "$1" | sed 's/^/    /'
}

install_tool() {
  local tool="$1" file dir toml result fresh_backup
  file=$(settings_file "$tool")
  dir=$(dirname "$file")
  mkdir -p "$dir"
  if [ "$tool" = codex ]; then
    toml="$dir/config.toml"
    # hooks already live in config.toml: ours go there too, because Codex warns when it finds hooks in both files
    # hook đã nằm sẵn trong config.toml: hook của ta cũng vào đó, vì Codex cảnh báo khi thấy hook ở cả hai file
    if [ ! -f "$file" ] && grep -Eq '^[[:space:]]*\[\[hooks\.' "$toml" 2> /dev/null; then
      case "$HOOK" in *"'"*) by_hand codex "$toml"; return 1 ;; esac
      keep_backup "$toml"
      without_toml_block "$toml" > "$toml.ai-worker-new" && { echo; our_toml; } >> "$toml.ai-worker-new" && mv "$toml.ai-worker-new" "$toml"
      say "  Codex: hooks added to $toml" "  Codex: đã thêm hook vào $toml"
      return 0
    fi
    # hooks of ours left in config.toml by an earlier install would run twice
    # hook của ta còn trong config.toml từ lần cài trước sẽ chạy hai lần
    if grep -Fqx "$TOML_BEGIN" "$toml" 2> /dev/null; then
      without_toml_block "$toml" > "$toml.ai-worker-new" && mv "$toml.ai-worker-new" "$toml"
    fi
  fi
  if [ ! -s "$file" ]; then
    our_json "$tool" > "$file"
  else
    our_json "$tool" > "$DIR/ours.json"
    fresh_backup=""
    [ -f "$file.ai-worker-backup" ] || fresh_backup=yes
    keep_backup "$file"
    result=$(merge_json add "$file" "$DIR/ours.json" 2> /dev/null) || {
      rm -f "$DIR/ours.json"
      # nothing was changed, so the copy just made has nothing to protect
      # chưa có gì thay đổi, nên bản sao vừa tạo không còn gì để giữ
      [ -n "$fresh_backup" ] && rm -f "$file.ai-worker-backup"
      by_hand "$tool" "$file"
      return 1
    }
    rm -f "$DIR/ours.json"
  fi
  say "  $(tool_name "$tool"): hooks added to $file" "  $(tool_name "$tool"): đã thêm hook vào $file"
}

remove_tool() {
  local tool="$1" file toml result
  file=$(settings_file "$tool")
  if [ "$tool" = codex ]; then
    toml="$(dirname "$file")/config.toml"
    if grep -Fqx "$TOML_BEGIN" "$toml" 2> /dev/null; then
      without_toml_block "$toml" > "$toml.ai-worker-new" && mv "$toml.ai-worker-new" "$toml"
      say "  Codex: hooks removed from $toml" "  Codex: đã gỡ hook khỏi $toml"
    fi
  fi
  grep -q "$MARK" "$file" 2> /dev/null || return 0
  # a file that holds our hooks and nothing else was made by this installer: it goes away whole
  # file chỉ chứa hook của ta thì do chính bộ cài này tạo: bỏ cả file
  if [ "$(cat "$file")" = "$(our_json "$tool")" ]; then
    rm -f "$file"
    # and the folder too when the installer made it and nothing else is in it
    # và cả thư mục khi chính bộ cài tạo ra nó và trong đó không còn gì khác
    rmdir "$(dirname "$file")" 2> /dev/null
  else
    result=$(merge_json remove "$file" 2> /dev/null) || {
      say "  Could not change $file safely. Remove by hand the hooks in it whose command holds $MARK." "  Không sửa $file một cách an toàn được. Hãy tự gỡ các hook trong đó có lệnh chứa $MARK."
      return 1
    }
    [ "$result" = empty ] && rm -f "$file"
  fi
  say "  $(tool_name "$tool"): hooks removed from $file" "  $(tool_name "$tool"): đã gỡ hook khỏi $file"
}

tool_installed() {
  grep -q "$MARK" "$(settings_file "$1")" 2> /dev/null && return 0
  [ "$1" = codex ] && grep -Fqx "$TOML_BEGIN" "$(dirname "$(settings_file codex)")/config.toml" 2> /dev/null
}

# send what the session file says right now, and tell the person what the board answered
# gửi đúng những gì file phiên đang ghi, và cho người dùng biết bảng trả lời gì
send_now() {
  rm -f "$DIR/sent" "$DIR/last-error"
  AI_WORKER_CONNECTOR_DIR="$DIR" sh "$HOOK" codex send
  if [ -f "$DIR/sent" ]; then
    say "The board answered: received." "Bảng trả lời: đã nhận."
    return 0
  fi
  local code
  code=$(sed -n 's/.*http=//p' "$DIR/last-error" 2> /dev/null)
  case "$code" in
    401)
      say "The board refused the send key (401). Check the key and run this again." "Bảng từ chối khoá gửi (401). Kiểm tra lại khoá rồi chạy lại."
      ;;
    409)
      say "The board says this computer is tied to another name (409). Ask the admin to forget this device, or use the same name and email as before." "Bảng báo máy này đã gắn với một tên khác (409). Nhờ quản trị viên xoá máy này khỏi bảng, hoặc dùng đúng tên và email như trước."
      ;;
    429 | 507)
      say "The board has reached a limit ($code). Try again tomorrow, or ask the admin." "Bảng đã chạm giới hạn ($code). Thử lại vào ngày mai, hoặc hỏi quản trị viên."
      ;;
    *)
      say "The board could not be reached (answer: ${code:-none}). The hooks are installed and will try again at the next event." "Chưa tới được bảng (trả lời: ${code:-không có}). Hook đã cài và sẽ thử lại ở sự kiện kế tiếp."
      ;;
  esac
  return 1
}

if [ "$ACTION" = status ]; then
  if [ ! -f "$DIR/config" ]; then
    say "The connector is not installed on this computer." "Bộ nối chưa được cài trên máy này."
    exit 0
  fi
  say "Board: $(config_value url) · name: $(config_value name)" "Bảng: $(config_value url) · tên: $(config_value name)"
  for tool in codex cursor gemini; do
    if tool_installed "$tool"; then
      say "  $(tool_name "$tool"): hooks installed" "  $(tool_name "$tool"): đã cài hook"
    fi
  done
  if [ -s "$DIR/sessions" ]; then
    say "Sessions counted now: $(wc -l < "$DIR/sessions" | tr -d ' ')" "Số phiên đang được tính: $(wc -l < "$DIR/sessions" | tr -d ' ')"
  fi
  if [ -f "$DIR/last-error" ]; then
    say "Last send failed: $(cat "$DIR/last-error")" "Lần gửi gần nhất hỏng: $(cat "$DIR/last-error")"
  fi
  if [ -f "$DIR/sent" ]; then
    say "Last send received by the board: $(date -r "$(cut -d' ' -f1 "$DIR/sent")" 2> /dev/null || date -d "@$(cut -d' ' -f1 "$DIR/sent")" 2> /dev/null)" "Lần gửi gần nhất bảng đã nhận: $(date -r "$(cut -d' ' -f1 "$DIR/sent")" 2> /dev/null || date -d "@$(cut -d' ' -f1 "$DIR/sent")" 2> /dev/null)"
  fi
  exit 0
fi

if [ "$ACTION" = uninstall ]; then
  say "== Removing the AI Worker connector ==" "== Gỡ bộ nối AI Worker =="
  for tool in codex cursor gemini; do remove_tool "$tool"; done
  # tell the board that no session is open here any more, so the person does not stay "waiting" for two hours
  # báo cho bảng biết ở đây không còn phiên nào mở, để người dùng không bị hiện "đang chờ" suốt hai giờ
  if [ -f "$DIR/config" ] && [ -f "$HOOK" ]; then
    : > "$DIR/sessions"
    send_now > /dev/null 2>&1
  fi
  if [ -f "$DIR/skills-installed" ]; then
    while IFS= read -r skill; do
      case "$skill" in "" | */* | .*) continue ;; esac
      rm -rf "${SKILLS_DIR:?}/$skill"
    done < "$DIR/skills-installed"
    rmdir "$SKILLS_DIR" "$HOME/.agents" 2> /dev/null
    say "  Skills removed from $SKILLS_DIR" "  Đã gỡ các skill khỏi $SKILLS_DIR"
  fi
  for f in config device sessions sessions.new sent last-error report.json ours.json wgetrc skills-installed ai-worker-hook.sh install.sh merge-hooks.js lang.sh; do rm -f "$DIR/$f"; done
  rmdir "$DIR/state.lock" "$DIR/send.lock" "$DIR" "$(dirname "$DIR")" 2> /dev/null
  say "Done. Codex, Cursor and Gemini CLI no longer send anything to the board." "Xong. Codex, Cursor và Gemini CLI không còn gửi gì lên bảng."
  for tool in codex cursor gemini; do
    for f in "$(settings_file "$tool").ai-worker-backup" "$(dirname "$(settings_file codex)")/config.toml.ai-worker-backup"; do
      if [ -f "$f" ]; then
        say "A copy of your settings from before the install is still at $f; delete it when you no longer need it." "Bản sao cấu hình của bạn từ trước khi cài vẫn còn ở $f; xoá đi khi không cần nữa."
      fi
    done
  done | sort -u
  exit 0
fi

say "== AI Worker: show Codex, Cursor and Gemini CLI on the board ==" "== AI Worker: cho Codex, Cursor và Gemini CLI hiện lên bảng =="
say "What is sent: your name and email, a random id for this computer, and for each tool how many sessions are open, working or waiting." "Thứ được gửi: tên và email của bạn, một mã ngẫu nhiên của máy này, và với mỗi công cụ là số phiên đang mở, đang làm, đang chờ."
say "Never sent: prompts, answers, file names, folders or project names." "Không bao giờ gửi: câu hỏi, câu trả lời, tên file, thư mục hay tên dự án."
echo

# the board and its send key: what was given, else what an earlier install saved, else the company package this file came in
# bảng và khoá gửi: thứ được truyền vào, không có thì lấy của lần cài trước, không có nữa thì lấy trong gói công ty chứa file này
[ -n "$SERVER" ] || SERVER="${AI_WORKER_URL:-$(config_value url)}"
[ -n "$KEY" ] || KEY="${AI_WORKER_KEY:-$(config_value key)}"
for f in "$HERE/../web/company.json" "$HOME/claude-plugins-ai-worker/ai-worker/web/company.json"; do
  [ -n "$SERVER" ] || SERVER=$(json_value "$f" webhook)
  [ -n "$KEY" ] || KEY=$(json_value "$f" ingestKey)
done
if [ -z "$SERVER" ]; then
  Q=$(
  say "Address of the board (for example https://board.example.com): " "Địa chỉ của bảng (ví dụ https://board.example.com): "
  )
  read -r -p "$Q" SERVER || exit 1
fi
SERVER=$(printf '%s' "$SERVER" | tr -d '[:space:]' | sed 's:/*$::')
case "$SERVER" in
  http://* | https://*) ;;
  *)
    say "The address must start with http:// or https://" "Địa chỉ phải bắt đầu bằng http:// hoặc https://"
    exit 1
    ;;
esac
if [ -z "$KEY" ]; then
  Q=$(
  say "Send key of the board (ask the person who runs it): " "Khoá gửi của bảng (hỏi người quản trị bảng): "
  )
  read -r -s -p "$Q" KEY || exit 1
  echo
fi
KEY=$(printf '%s' "$KEY" | tr -d '[:space:]"\\')
if ! [ -n "$KEY" ]; then
  say "A send key is needed." "Cần có khoá gửi."
  exit 1
fi

# the name and email: the same ones the Claude Code plugin uses on this computer, so one person stays one row on the board
# tên và email: đúng cặp mà plugin Claude Code dùng trên máy này, để một người vẫn là một dòng trên bảng
USER_FILE="$HOME/.local/share/ai-worker/user.json"
[ -n "$NAME" ] || NAME=$(config_value name)
[ -n "$NAME" ] || NAME=$(json_value "$USER_FILE" name)
[ -n "$ACCOUNT" ] || ACCOUNT=$(config_value account)
[ -n "$ACCOUNT" ] || ACCOUNT=$(json_value "$USER_FILE" account)
if [ -z "$NAME" ]; then
  Q=$(
  say "Your full name, as the board should show it: " "Họ tên của bạn, như bảng sẽ hiện: "
  )
  while [ -z "${NAME//[[:space:]]/}" ]; do read -r -p "$Q" NAME || exit 1; done
  if [ -z "$ACCOUNT" ]; then
    Q=$(
    say "Your work email (Enter to skip): " "Email công việc của bạn (Enter để bỏ qua): "
    )
    read -r -p "$Q" ACCOUNT || true
  fi
fi
NAME=$(clean "$NAME")
ACCOUNT=$(clean "$ACCOUNT" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
if ! [ -n "$NAME" ]; then
  say "A name is needed." "Cần có tên."
  exit 1
fi

# which tools: the ones named, else ask about each one found on this computer
# công cụ nào: những cái được nêu tên, không có thì hỏi về từng cái tìm thấy trên máy này
CHOSEN=""
if [ -n "$TOOLS" ]; then
  for tool in $(printf '%s' "$TOOLS" | tr ',' ' '); do
    case "$tool" in
      codex | cursor | gemini) CHOSEN="$CHOSEN $tool" ;;
      *)
        say "Unknown tool: $tool" "Công cụ không rõ: $tool"
        exit 2
        ;;
    esac
  done
else
  for tool in codex cursor gemini; do
    if tool_found "$tool"; then
      Q=$(
      say "Show $(tool_name "$tool") on the board? (Enter = yes, type n = no): " "Cho $(tool_name "$tool") hiện lên bảng? (Enter = có, gõ n = không): "
      )
      reply=""; read -r -p "$Q" reply || true
      [ "$reply" = n ] || [ "$reply" = N ] || CHOSEN="$CHOSEN $tool"
    else
      say "$(tool_name "$tool"): not found on this computer, skipped." "$(tool_name "$tool"): không thấy trên máy này, bỏ qua."
    fi
  done
fi
if ! [ -n "$CHOSEN" ]; then
  say "No tool chosen: nothing was changed." "Không chọn công cụ nào: không có gì thay đổi."
  exit 0
fi

mkdir -p "$DIR" || exit 1
chmod 700 "$DIR"
cp "$HERE/ai-worker-hook.sh" "$HOOK" && chmod 755 "$HOOK" || exit 1
# a copy of this installer stays with the hook, so removing still works after the package it came in is gone
# một bản sao của bộ cài này nằm cạnh hook, để việc gỡ vẫn chạy được sau khi gói chứa nó đã bị xoá
if [ "$HERE" != "$DIR" ]; then
  cp "$HERE/install.sh" "$HERE/merge-hooks.js" "$DIR/" || exit 1
  for f in "$HERE/../../lang.sh" "$HERE/../packaging/lang.sh"; do [ -f "$f" ] && cp "$f" "$DIR/lang.sh" && break; done
fi
# the send key is the only secret here: the file can be read by this account only
# khoá gửi là thứ bí mật duy nhất ở đây: chỉ tài khoản này đọc được file
(umask 077 && printf 'url=%s\nkey=%s\nname=%s\naccount=%s\n' "$SERVER" "$KEY" "$NAME" "$ACCOUNT" > "$DIR/config")
touch "$DIR/sessions"

say "Installing for:$CHOSEN" "Cài cho:$CHOSEN"
FAILED="" DONE=""
for tool in codex cursor gemini; do
  case " $CHOSEN " in
    *" $tool "*) install_tool "$tool" && DONE="$DONE $tool" || FAILED="$FAILED $tool" ;;
    *) remove_tool "$tool" ;;
  esac
done

# the skills: only when asked for, and never over a folder this installer did not put there
# các skill: chỉ khi được yêu cầu, và không bao giờ đè lên thư mục không do bộ cài này đặt vào
if [ -z "$SKILLS" ] && [ -d "$HERE/../skills" ] && [ -t 0 ]; then
  Q=$(
  say "Also copy the AI Worker skills to $SKILLS_DIR, where Codex, Cursor and Gemini CLI read skills? (type y = yes, Enter = no): " "Chép thêm các skill của AI Worker vào $SKILLS_DIR, nơi Codex, Cursor và Gemini CLI đọc skill? (gõ y = có, Enter = không): "
  )
  reply=""; read -r -p "$Q" reply || true
  { [ "$reply" = y ] || [ "$reply" = Y ]; } && SKILLS=yes
fi
if [ "$SKILLS" = yes ] && [ -d "$HERE/../skills" ]; then
  mkdir -p "$SKILLS_DIR"
  copied=0
  for skill in $PORTABLE_SKILLS; do
    [ -f "$HERE/../skills/$skill/SKILL.md" ] || continue
    if [ -e "$SKILLS_DIR/$skill" ] && ! grep -Fqx "$skill" "$DIR/skills-installed" 2> /dev/null; then
      say "  Skill $skill: a folder with this name is already there, left as it is." "  Skill $skill: đã có thư mục cùng tên, để nguyên."
      continue
    fi
    rm -rf "${SKILLS_DIR:?}/$skill"
    cp -R "$HERE/../skills/$skill" "$SKILLS_DIR/$skill" && copied=$((copied + 1))
    grep -Fqx "$skill" "$DIR/skills-installed" 2> /dev/null || printf '%s\n' "$skill" >> "$DIR/skills-installed"
  done
  say "  $copied skills copied to $SKILLS_DIR" "  Đã chép $copied skill vào $SKILLS_DIR"
fi

echo
send_now
echo
case " $DONE " in
  *" codex "*)
    say "One more step for Codex, which runs a hook only after you have looked at it:" "Còn một bước với Codex, vì Codex chỉ chạy hook sau khi bạn đã xem qua:"
    say "  1. Open Terminal and type: codex" "  1. Mở Terminal và gõ: codex"
    say "  2. In Codex type /hooks and press Enter. You see seven hooks whose command ends in ai-worker-hook.sh." "  2. Trong Codex gõ /hooks rồi nhấn Enter. Bạn thấy bảy hook có lệnh kết thúc bằng ai-worker-hook.sh."
    say "  3. Trust each of them. From then on your Codex sessions show on the board." "  3. Bấm tin cậy từng hook. Từ đó các phiên Codex của bạn hiện trên bảng."
    ;;
esac
case " $DONE " in
  *" cursor "* | *" gemini "*)
    say "Cursor and Gemini CLI pick the hooks up at their next start: close and reopen them." "Cursor và Gemini CLI nhận hook ở lần mở kế tiếp: hãy đóng rồi mở lại."
    ;;
esac
say "To remove everything later: bash \"$DIR/install.sh\" --uninstall" "Muốn gỡ sạch sau này: bash \"$DIR/install.sh\" --uninstall"
[ -z "$FAILED" ]
