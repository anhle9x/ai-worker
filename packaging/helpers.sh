#!/bin/bash
# Install the helper AI assistants for Claude on macOS / Ubuntu (called by the installer, after the plugin is installed):
# Cài nhân viên AI phụ cho Claude trên macOS / Ubuntu (file cài gọi, sau khi cài plugin):
#   ChatGPT via Codex CLI (default), Gemma via Ollama (size by computer), Gemini via Antigravity CLI (optional).
#   ChatGPT qua Codex CLI (mặc định), Gemma qua Ollama (cỡ theo máy), Gemini qua Antigravity CLI (tuỳ chọn).
# Only official installers: chatgpt.com/codex, ollama.com, antigravity.google.
# Chỉ dùng bộ cài chính thức: chatgpt.com/codex, ollama.com, antigravity.google.
# Do not stop the installer when one part fails: report it and go on.
# Không dừng file cài khi một phần hỏng: báo rồi đi tiếp.

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/lang.sh" ] || { echo "lang.sh is missing next to helpers.sh. / Thiếu lang.sh cạnh helpers.sh."; exit 1; } # i18n-allow
. "$HERE/lang.sh"

DATA_DIR="$HOME/.local/share/ai-worker"
mkdir -p "$DATA_DIR"
# $1 is the question; Enter = yes
# $1 là câu hỏi; Enter = có
ask_yes() {
  local reply="" hint
  hint=$(
  say "(Enter = yes, type n = no)" "(Enter = có, gõ n = không)"
  )
  read -r -p "$1 $hint: " reply || true
  [ "$reply" != n ] && [ "$reply" != N ]
}

echo
say "== Helper AI assistants for Claude ==" "== Nhân viên AI phụ cho Claude =="

# ---- ChatGPT (Codex CLI): installed by default ----
# ---- ChatGPT (Codex CLI): mặc định cài ----
CODEX=$(command -v codex 2>/dev/null || true)
[ -z "$CODEX" ] && [ -x "$HOME/.local/bin/codex" ] && CODEX="$HOME/.local/bin/codex"
if [ -z "$CODEX" ]; then
  say "Installing Codex CLI (ChatGPT, the official OpenAI installer)..." "Cài Codex CLI (ChatGPT, bộ cài chính thức của OpenAI)..."
  if curl -fsSL https://chatgpt.com/codex/install.sh | sh; then CODEX="$HOME/.local/bin/codex"; fi
fi
if [ -n "$CODEX" ] && "$CODEX" --version >/dev/null 2>&1; then
  if "$CODEX" login status >/dev/null 2>&1; then
    say "ChatGPT (Codex): installed and signed in." "ChatGPT (Codex): đã cài, đã đăng nhập."
  else
    say "ChatGPT (Codex): needs sign-in with the company ChatGPT account (ask your IT team if you do not have one)." "ChatGPT (Codex): cần đăng nhập bằng tài khoản ChatGPT của công ty (hỏi phòng IT nếu chưa có)."
    Q=$(
    say "Open the browser to sign in now?" "Mở trình duyệt để đăng nhập ngay?"
    )
    if ask_yes "$Q"; then
      if ! "$CODEX" login; then
        say "Codex sign-in not finished. Later, open Terminal and type: codex login" "Đăng nhập Codex chưa xong. Sau này mở Terminal gõ: codex login"
      fi
    else
      say "Later: open Terminal and type  codex login" "Để sau: mở Terminal gõ  codex login"
    fi
  fi
else
  say "ChatGPT (Codex): could not install, skipped. Take a screenshot and send it to your IT team." "ChatGPT (Codex): cài chưa được, bỏ qua. Chụp màn hình gửi phòng IT."
fi

# ---- Gemma (Ollama): size by RAM, downloaded in the background ----
# ---- Gemma (Ollama): cỡ theo RAM, tải ngầm ----
if [ "$(uname -s)" = Darwin ]; then
  RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
  # An Intel Mac runs models much slower than Apple silicon: go down one size
  # Mac chip Intel chạy mô hình chậm hơn hẳn chip Apple: hạ một cỡ
  SLOW=""
  if [ "$(uname -m)" = x86_64 ]; then
    SLOW=$(
    say "Intel chip" "chip Intel"
    )
  fi
else
  RAM_GB=$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576 ))
  # Without an NVIDIA card Ollama runs on the CPU: go down one size
  # Không có card NVIDIA thì Ollama chạy bằng CPU: hạ một cỡ
  SLOW=""
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    SLOW=$(
    say "no NVIDIA graphics card" "không có card đồ hoạ NVIDIA"
    )
  fi
fi
FREE_GB=$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2{print int($4/1048576)}')
TIER=0
[ "$RAM_GB" -ge 8 ] && TIER=1
[ "$RAM_GB" -ge 16 ] && TIER=2
[ "$RAM_GB" -ge 32 ] && TIER=3
[ -n "$SLOW" ] && [ "$TIER" -gt 0 ] && TIER=$((TIER - 1))
pick_variant() {
  case $TIER in
    3) GEMMA=gemma4:26b; SIZE_GB=17; NEED_GB=25 ;;
    2) GEMMA=gemma4:e4b; SIZE_GB=7; NEED_GB=14 ;;
    1) GEMMA=gemma4:e2b; SIZE_GB=5; NEED_GB=12 ;;
    *) GEMMA=""; NEED_GB=0 ;;
  esac
}
RAM_TIER=$TIER
pick_variant
# If the disk has no room for the size that fits the RAM, go down until one fits
# Ổ không đủ chỗ cho bản hợp RAM thì hạ dần tới bản vừa
while [ -n "$GEMMA" ] && [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt "$NEED_GB" ]; do TIER=$((TIER - 1)); pick_variant; done
DESC=$(
say "This computer has ${RAM_GB} GB RAM and ${FREE_GB:-?} GB free disk space${SLOW:+, $SLOW}" "Máy có ${RAM_GB} GB RAM, ổ còn trống ${FREE_GB:-?} GB${SLOW:+, $SLOW}"
)
GEMMA_Q=$(
say "Gemma (runs on this computer, data stays here): $DESC -> install version $GEMMA (about $SIZE_GB GB, downloaded in the background). OK?" "Gemma (chạy ngay trên máy, dữ liệu không ra ngoài): $DESC -> cài bản $GEMMA (khoảng $SIZE_GB GB, tải ngầm). Đồng ý?"
)
# Already downloaded (Ollama running and the model listed): say so and do not ask
# Đã tải sẵn (Ollama đang chạy và có mô hình trong danh sách): báo luôn, không hỏi
if [ -n "$GEMMA" ] && curl -s -m 2 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "\"name\":\"$GEMMA\""; then
  say "Gemma: $GEMMA is already there." "Gemma: đã có sẵn $GEMMA."
elif [ -z "$GEMMA" ] && [ "$RAM_TIER" -eq 0 ]; then
  say "Gemma: not installed ($DESC; needs at least 8 GB RAM)." "Gemma: không cài ($DESC; cần ít nhất 8 GB RAM)."
elif [ -z "$GEMMA" ]; then
  say "Gemma: not installed ($DESC; needs at least 12 GB free)." "Gemma: không cài ($DESC; cần trống ít nhất 12 GB)."
elif ask_yes "$GEMMA_Q"; then
  if ! command -v ollama >/dev/null 2>&1 && [ ! -d /Applications/Ollama.app ]; then
    say "Installing Ollama (the official installer; it may ask for the computer password)..." "Cài Ollama (bộ cài chính thức; có thể hỏi mật khẩu máy)..."
    if ! curl -fsSL https://ollama.com/install.sh | sh; then
      say "Could not install Ollama. Take a screenshot and send it to your IT team." "Cài Ollama chưa được. Chụp màn hình gửi phòng IT."
    fi
  fi
  if ! curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    # The Ollama app starts its background part itself; when installed from the command line (brew), start it by hand
    # App Ollama tự chạy phần nền; cài bằng lệnh (brew) thì bật phần nền bằng tay
    if [ -d /Applications/Ollama.app ]; then open -a Ollama 2>/dev/null
    elif command -v ollama >/dev/null 2>&1; then nohup ollama serve >/dev/null 2>&1 &
    fi
  fi
  # Wait for Ollama to be ready (up to 60 seconds)
  # Chờ Ollama sẵn sàng (tối đa 60 giây)
  for _ in $(seq 1 30); do curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 2; done
  if curl -s -m 5 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "\"name\":\"$GEMMA\""; then
    say "Gemma: $GEMMA is already there." "Gemma: đã có sẵn $GEMMA."
  elif curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    nohup curl -s http://127.0.0.1:11434/api/pull -d "{\"model\":\"$GEMMA\"}" > "$DATA_DIR/gemma-download.log" 2>&1 &
    say "Gemma: downloading $GEMMA in the background (about $SIZE_GB GB). You can close this window; when it finishes, reopen Claude and the Gemma desk appears." "Gemma: đang tải ngầm $GEMMA (khoảng $SIZE_GB GB). Đóng cửa sổ này không sao; tải xong, mở lại Claude là bàn Gemma hiện."
  else
    say "Gemma: Ollama could not start, so the model was not downloaded. Take a screenshot and send it to your IT team." "Gemma: Ollama chưa chạy được, chưa tải mô hình. Chụp màn hình gửi phòng IT."
  fi
else
  say "Gemma: skipped." "Gemma: bỏ qua."
fi

# ---- Gemini (Antigravity CLI): optional, personal Google account ----
# ---- Gemini (Antigravity CLI): tuỳ chọn, tài khoản Google cá nhân ----
AGY=$(command -v agy 2>/dev/null || true)
[ -z "$AGY" ] && [ -x "$HOME/.local/bin/agy" ] && AGY="$HOME/.local/bin/agy"
if [ -n "$AGY" ]; then
  say "Gemini: installed (Antigravity CLI)." "Gemini: đã cài (Antigravity CLI)."
else
  GEMINI_Q=$(
  say "Also install Gemini? Free, sign in with your own Google account, used only for web research. (type y = yes, Enter = no): " "Cài thêm Gemini? Miễn phí, đăng nhập bằng tài khoản Google của bạn, chỉ dùng tra cứu web. (gõ y = có, Enter = không): "
  )
  reply=""; read -r -p "$GEMINI_Q" reply || true
  if [ "$reply" = y ] || [ "$reply" = Y ]; then
    if curl -fsSL https://antigravity.google/cli/install.sh | bash; then
      say "Gemini: installed. First time: open Terminal, type  agy  and sign in with your Google account, then press Ctrl+C to leave." "Gemini: đã cài. Lần đầu: mở Terminal, gõ  agy  rồi đăng nhập tài khoản Google, xong nhấn Ctrl+C để thoát."
    else
      say "Gemini: could not install, skipped." "Gemini: cài chưa được, bỏ qua."
    fi
  else
    say "Gemini: not installed (the Gemini desk will be hidden)." "Gemini: không cài (bàn Gemini sẽ ẩn)."
  fi
fi
say "The helper AI assistants appear in the office after you reopen Claude." "Nhân viên AI phụ hiện lên văn phòng sau khi mở lại Claude."
