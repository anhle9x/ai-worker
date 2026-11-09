#!/bin/bash
# Tries INSTALL-Linux.sh on a clean machine. Each case gets its own home folder and a fake claude command. Usage: test-install.sh <package folder>
# Thử INSTALL-Linux.sh trên máy sạch. Mỗi tình huống có thư mục nhà riêng và lệnh claude giả. Cách dùng: test-install.sh <thư mục gói>
set -u
PACKAGE="$(cd "$1" && pwd)"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
errors=0

# Fake claude command: auth status reads $HOME/login.json, every command is logged to $HOME/commands.log.
# Lệnh claude giả: auth status đọc $HOME/login.json, mọi lệnh ghi vào $HOME/commands.log.
mkdir -p "$ROOT/fake"
cat > "$ROOT/fake/claude" <<'FAKE'
#!/bin/bash
echo "$*" >> "$HOME/commands.log"
if [ "$1 $2" = "auth status" ]; then
  if [ -f "$HOME/login.json" ]; then cat "$HOME/login.json"; else echo '{"loggedIn": false}'; fi
fi
exit 0
FAKE
chmod +x "$ROOT/fake/claude"

# run NAME HAS_CMD LOGGED_IN LANG ANSWERS: leaves the exit code and the output in RESULT and OUT.
# run TÊN CÓ_LỆNH ĐĂNG_NHẬP NGÔN_NGỮ TRẢ_LỜI: để mã thoát và nội dung in ra trong RESULT và OUT.
run() {
  local name="$1" has_cmd="$2" logged_in="$3" lang="$4" answers="$5"
  HOME_DIR="$ROOT/$name"
  mkdir -p "$HOME_DIR"
  if [ -n "$logged_in" ]; then printf '{"loggedIn": true, "email": "%s"}' "$logged_in" > "$HOME_DIR/login.json"; fi
  local path="/usr/bin:/bin"
  if [ "$has_cmd" = 1 ]; then path="$ROOT/fake:$path"; fi
  OUT=$(printf '%b' "$answers" | env -i HOME="$HOME_DIR" PATH="$path" AI_WORKER_LANG="$lang" AI_WORKER_SKIP_HELPERS=1 bash "$PACKAGE/INSTALL-Linux.sh" 2>&1)
  RESULT=$?
  USER_JSON="$HOME_DIR/.local/share/ai-worker/user.json"
}

check() {
  if eval "$2"; then
    echo "  PASS  $1"
  else
    echo "  FAIL  $1"
    errors=$((errors + 1))
    echo "---- installer output (exit $RESULT) ----"
    echo "$OUT"
  fi
}

echo '== L1 normal package, already signed in'
run l1 1 lan@example.com en '\n'
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'says it is signed in' 'echo "$OUT" | grep -q "Claude is signed in: lan@example.com"'
check 'registers the plugin' 'grep -q "plugin install ai-worker@ai-worker" "$HOME_DIR/commands.log"'
check 'copies the plugin' '[ -d "$HOME_DIR/claude-plugins-ai-worker/ai-worker/hooks" ]'
check 'saves the language en' 'grep -q "\"language\": *\"en\"" "$USER_JSON"'

echo '== L2 Claude Code is not installed'
run l2 0 '' en '\n'
check 'exit 1' '[ "$RESULT" = 1 ]'
check 'says how to install it' 'echo "$OUT" | grep -q "claude.com/claude-code"'
check 'copies nothing' '[ ! -d "$HOME_DIR/claude-plugins-ai-worker" ]'

echo '== L3 not signed in, signs in later'
run l3 1 '' en 'n\n\n'
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'says it is not signed in' 'echo "$OUT" | grep -q "not signed in"'
check 'does not call auth login' '! grep -q "auth login" "$HOME_DIR/commands.log"'

echo '== L4 Vietnamese'
run l4 1 lan@example.com vi '\n'
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'prints Vietnamese' 'echo "$OUT" | grep -q "Claude đã đăng nhập: lan@example.com"' # i18n-allow
check 'saves the language vi' 'grep -q "\"language\": *\"vi\"" "$USER_JSON"'

echo '== L5 reinstall keeps other fields'
run l5 1 lan@example.com en '\n'
printf '{"name": "Cu", "account": "cu@example.com", "language": "en"}\n' > "$USER_JSON"
run l5 1 lan@example.com vi '\n'
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'keeps the name' 'grep -q "\"name\": *\"Cu\"" "$USER_JSON"'
check 'updates the language' 'grep -q "\"language\": *\"vi\"" "$USER_JSON"'

echo '== L6 company package asks the name, and a quote cannot break the file'
touch "$PACKAGE/setup/ASK-NAME"
run l6 1 lan@example.com en 'Nguyen "Van" A\n\n'
rm -f "$PACKAGE/setup/ASK-NAME"
check 'exit 0' '[ "$RESULT" = 0 ]'
check 'user.json stays valid JSON' 'python3 -c "import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if d[\"account\"]==\"lan@example.com\" and d[\"language\"]==\"en\" else 1)" "$USER_JSON"'

if [ "$errors" != 0 ]; then
  echo "$errors checks FAILED"
  exit 1
fi
echo 'All installer checks passed'
