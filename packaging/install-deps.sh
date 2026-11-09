#!/bin/bash
# Install the libraries the skills in the technical pack need (macOS). It must not break the plugin install: anything missing is reported at the end.
# Cài các thư viện skill trong gói kỹ thuật cần (macOS). Không làm hỏng việc cài plugin: thiếu gì thì báo ở cuối.
# Use: bash install-deps.sh <copied plugin folder>   AI_WORKER_WITH_VIDEO=y, AI_WORKER_WITH_STAGESHOW=y answer the two optional questions in advance.
# Dùng: bash install-deps.sh <thư mục plugin đã chép>   AI_WORKER_WITH_VIDEO=y, AI_WORKER_WITH_STAGESHOW=y để trả lời sẵn hai câu hỏi tuỳ chọn.
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/lang.sh" ] || { echo "lang.sh is missing next to install-deps.sh. / Thiếu lang.sh cạnh install-deps.sh."; exit 1; } # i18n-allow
. "$HERE/lang.sh"
PLUGIN="$1"
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
export PATH="$BIN:$HOME/.local/node/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
MISSING=()
miss() { MISSING+=("$1"); }
# Reviewed commits: do not take the latest, because this is third-party code that runs on staff computers
# Commit đã rà: không lấy bản mới nhất, vì đây là mã của bên thứ ba chạy trên máy nhân viên
VIDEO_COMMIT=43bd349a136651865ecfa6ea1cf012f6e957d304
STAGESHOW_COMMIT=299140fafd08df55a9c234e610c3f64af3f45531
YN_PROMPT=$(
say "(type y = yes, Enter = no): " "(gõ y = có, Enter = không): "
)

# If the account cannot write to Homebrew, do not call it: it only shows a red error that worries the user
# Tài khoản không có quyền ghi vào Homebrew thì đừng gọi: chỉ ra lỗi đỏ làm người dùng hoang mang
brew_ok() {
  command -v brew >/dev/null 2>&1 && [ -w "$(brew --prefix)/Cellar" ]
}

node_ok() {
  command -v npm >/dev/null 2>&1 && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>20||(a===20&&b>=19)?0:1)' >/dev/null 2>&1
}

install_node() {
  # stageshow and chrome-devtools-mcp need Node 20.19 or newer: if the computer has an older one, install a new one
  # stageshow và chrome-devtools-mcp cần Node từ 20.19: máy có bản cũ hơn thì cài thêm bản mới
  node_ok && return 0
  if brew_ok; then
    say "Installing Node.js with Homebrew ..." "Cài Node.js bằng Homebrew ..."
    brew install node && hash -r && node_ok && return 0
  fi
  # No admin rights needed: the official build goes to ~/.local/node, and the checksum published by nodejs.org is verified
  # Không cần quyền quản trị: bản chính thức vào ~/.local/node, kiểm mã băm do nodejs.org công bố
  say "Installing Node.js from nodejs.org into ~/.local/node ..." "Cài Node.js từ nodejs.org vào ~/.local/node ..."
  case "$(uname -m)" in arm64) A=arm64 ;; *) A=x64 ;; esac
  DIST_URL=https://nodejs.org/dist/latest-v22.x
  T=$(mktemp -d)
  curl -fsSL -m 60 "$DIST_URL/SHASUMS256.txt" -o "$T/sum" || { rm -rf "$T"; return 1; }
  F=$(sed -n "s/.*\(node-v[0-9.]*-darwin-$A\.tar\.gz\)$/\1/p" "$T/sum" | head -1)
  [ -n "$F" ] && curl -fsSL -m 300 "$DIST_URL/$F" -o "$T/$F" || { rm -rf "$T"; return 1; }
  if [ "$(shasum -a 256 "$T/$F" | cut -d' ' -f1)" != "$(grep "  $F\$" "$T/sum" | cut -d' ' -f1)" ]; then
    say "The Node.js download does not match its checksum, skipped." "Tải Node.js không khớp mã kiểm tra, bỏ qua."; rm -rf "$T"; return 1
  fi
  rm -rf "$HOME/.local/node"; mkdir -p "$HOME/.local/node"
  tar -xzf "$T/$F" -C "$HOME/.local/node" --strip-components=1 || { rm -rf "$T"; return 1; }
  rm -rf "$T"
  for b in node npm npx; do ln -sf "$HOME/.local/node/bin/$b" "$BIN/$b"; done
  grep -qs '\.local/bin' "$HOME/.zprofile" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zprofile"
  hash -r
  node_ok
}

has_python() { python3 -c 'import sys; sys.exit(0 if sys.version_info[0]==3 else 1)' >/dev/null 2>&1; }

echo
say "== Libraries for the technical pack ==" "== Thư viện cho gói kỹ thuật =="
install_node || miss "$(
say "Node.js: download it from https://nodejs.org, then run the installer again" "Node.js: tải tại https://nodejs.org rồi chạy lại file cài"
)"
if ! has_python; then
  if brew_ok; then brew install python || true; fi
  has_python || miss "$(
say "Python 3 (for ui-ux-pro-max): run  xcode-select --install  and follow the dialog" "Python 3 (cho ui-ux-pro-max): chạy  xcode-select --install  rồi làm theo hộp thoại"
)"
fi
[ -d /Applications/"Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ] || miss "$(
say "Google Chrome (for the web testing skill): download it from https://www.google.com/chrome" "Google Chrome (cho skill kiểm thử web): tải tại https://www.google.com/chrome"
)"

if [ -n "$CLAUDE" ] && command -v npx >/dev/null 2>&1; then
  say "Registering the browser control tools for the testing skills ..." "Đăng ký công cụ điều khiển trình duyệt cho skill kiểm thử ..."
  NPX=$(command -v npx)
  # The app does not have the Terminal PATH: name it explicitly so npx finds the Node we just checked, not an old one on the computer
  # App không có PATH của Terminal: phải chỉ rõ để npx gặp đúng bản Node vừa kiểm, không gặp bản cũ trên máy
  PATH_DIR="$(dirname "$NPX"):/usr/bin:/bin"
  # Pinned to the versions tried (2026-11-04): @latest can change how it runs without notice
  # Ghim đúng bản đã thử (04/11/2026): @latest có thể đổi cách chạy mà không báo
  for name in playwright chrome-devtools; do "$CLAUDE" mcp remove --scope user "$name" >/dev/null 2>&1 || true; done
  "$CLAUDE" mcp add --scope user playwright -e "PATH=$PATH_DIR" -- "$NPX" -y @playwright/mcp@0.0.84 --browser chrome >/dev/null 2>&1 || miss "$(
say "Playwright: could not be registered, take a screenshot of this window and send it to your IT team" "Playwright: không đăng ký được, chụp cửa sổ này gửi phòng IT"
)"
  "$CLAUDE" mcp add --scope user chrome-devtools -e "PATH=$PATH_DIR" -- "$NPX" -y chrome-devtools-mcp@1.12.0 >/dev/null 2>&1 || miss "$(
say "Chrome DevTools: could not be registered, take a screenshot of this window and send it to your IT team" "Chrome DevTools: không đăng ký được, chụp cửa sổ này gửi phòng IT"
)"
fi

echo
say "Also install stageshow to build sample UI images and animations? It is downloaded from benjitaylor/skills and needs Node." "Cài thêm stageshow để dựng ảnh và hoạt cảnh giao diện mẫu? Tải từ benjitaylor/skills, cần Node."
say "Note: the source code is MIT, but the app icons and logos that come with it belong to their owners; see NOTICE.md." "Lưu ý: mã nguồn MIT, nhưng biểu tượng ứng dụng và logo kèm theo thuộc chủ của chúng; xem NOTICE.md."
answer="${AI_WORKER_WITH_STAGESHOW:-}"
[ -n "$answer" ] || read -r -p "$YN_PROMPT" answer || true
if [ "$answer" = y ] || [ "$answer" = Y ]; then
  D="$HOME/.claude/skills/stageshow"
  if [ -e "$D" ]; then
    say "$D already exists, left as it is." "Đã có $D, giữ nguyên."
  else
    T=$(mktemp -d)
    if curl -fsSL -m 300 "https://codeload.github.com/benjitaylor/skills/tar.gz/$STAGESHOW_COMMIT" -o "$T/s.tgz" \
      && mkdir -p "$D" && tar -xzf "$T/s.tgz" -C "$D" --strip-components=2 "skills-$STAGESHOW_COMMIT/stageshow"; then
      say "Installed stageshow into $D" "Đã cài stageshow vào $D"
      if command -v npm >/dev/null 2>&1; then
        (cd "$D" && npm ci --no-audit --no-fund --loglevel=error) || miss "$(
say "stageshow: go to $D and run  npm ci" "stageshow: vào $D chạy  npm ci"
)"
      else
        miss "$(
say "stageshow: needs Node, then go to $D and run  npm ci" "stageshow: cần Node rồi vào $D chạy  npm ci"
)"
      fi
    else
      rm -rf "$D"; miss "$(
say "stageshow: could not be downloaded, run the installer again when you have internet" "stageshow: tải không được, chạy lại file cài khi có mạng"
)"
    fi
    rm -rf "$T"
  fi
fi

echo
say "Also install video-shotcraft to make product videos? The download takes about 70 MB." "Cài thêm video-shotcraft để làm video sản phẩm? Tải và chiếm khoảng 70 MB."
say "Note: the Remotion video tool has its own license and your company may have to pay; some audio files" "Lưu ý: công cụ dựng Remotion có giấy phép riêng, công ty có thể phải trả phí; một số file âm thanh"
say "have an unclear source. Ask your IT team before using it for company videos." "chưa rõ nguồn. Hỏi phòng IT trước khi dùng cho video của công ty."
answer="${AI_WORKER_WITH_VIDEO:-}"
[ -n "$answer" ] || read -r -p "$YN_PROMPT" answer || true
if [ "$answer" = y ] || [ "$answer" = Y ]; then
  D="$HOME/.claude/skills/video-shotcraft"
  if [ -e "$D" ]; then
    say "$D already exists, left as it is." "Đã có $D, giữ nguyên."
  else
    T=$(mktemp -d)
    if curl -fsSL -m 600 "https://codeload.github.com/Vincentwei1021/video-shotcraft/tar.gz/$VIDEO_COMMIT" -o "$T/v.tgz" \
      && mkdir -p "$D" && tar -xzf "$T/v.tgz" -C "$D" --strip-components=1; then
      say "Installed video-shotcraft into $D" "Đã cài video-shotcraft vào $D"
    else
      rm -rf "$D"; miss "$(
say "video-shotcraft: could not be downloaded, run the installer again when you have internet" "video-shotcraft: tải không được, chạy lại file cài khi có mạng"
)"
    fi
    rm -rf "$T"
  fi
  if ! command -v ffmpeg >/dev/null 2>&1; then
    if brew_ok; then brew install ffmpeg || true; fi
    command -v ffmpeg >/dev/null 2>&1 || miss "$(
say "ffmpeg (for video-shotcraft): install Homebrew from https://brew.sh, then run  brew install ffmpeg" "ffmpeg (cho video-shotcraft): cài Homebrew từ https://brew.sh rồi chạy  brew install ffmpeg"
)"
  fi
fi

echo
if [ ${#MISSING[@]} -eq 0 ]; then
  say "All libraries are in place." "Đã đủ thư viện."
else
  say "Still missing, so the related skills cannot run yet:" "Còn thiếu, các skill liên quan chưa chạy được:"
  for x in "${MISSING[@]}"; do echo "  - $x"; done
fi
exit 0
