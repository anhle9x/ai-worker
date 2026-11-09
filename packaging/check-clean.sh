#!/usr/bin/env bash
# Stops private data from reaching a public repository. Prints only file:line and the rule, never the matched text; private words in a path become ***.
# Chặn dữ liệu riêng lọt vào repo công khai. Chỉ in file:dòng và tên quy tắc, không bao giờ in chữ bị bắt; từ riêng trong đường dẫn thành ***.
# Usage: check-clean.sh [--all] [folder]  |  check-clean.sh --install-hooks  (run from the root of the repository)
# Cách dùng: check-clean.sh [--all] [thư mục]  |  check-clean.sh --install-hooks  (chạy ở thư mục gốc của repo)
# --all searches everything, for a folder about to be published. Without it, the local build folders dist, releases and node_modules are skipped, and files tracked by git inside them are refused.
# --all tìm mọi thứ, dùng cho thư mục sắp công khai. Không có nó thì bỏ qua các thư mục dựng trên máy dist, releases, node_modules, và từ chối file được git theo dõi trong đó.
# Running without a private word list is refused unless AI_WORKER_NO_DENY=1 is set.
# Chạy mà không có danh sách từ riêng sẽ bị từ chối, trừ khi đặt AI_WORKER_NO_DENY=1.
# Private words, one per line, live outside the repository: $AI_WORKER_DENY_FILE or ~/.config/ai-worker/deny-words.txt
# Từ riêng, mỗi dòng một từ, nằm ngoài repo: $AI_WORKER_DENY_FILE hoặc ~/.config/ai-worker/deny-words.txt
set -u

if [ "${1:-}" = "--install-hooks" ]; then
  hooks="$(git rev-parse --git-path hooks)" || exit 1
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  for name in pre-commit pre-push; do
    printf '#!/bin/sh\nexec bash "%s" "$(git rev-parse --show-toplevel)"\n' "$self" > "$hooks/$name"
    chmod +x "$hooks/$name"
  done
  echo "Installed pre-commit and pre-push hooks."
  exit 0
fi

SEARCH_ALL=0
if [ "${1:-}" = "--all" ]; then
  SEARCH_ALL=1
  shift
fi
ROOT="${1:-.}"
if [ ! -d "$ROOT" ]; then
  echo "NOT CLEAN: the folder to check does not exist." >&2
  exit 2
fi
DENY_FILE="${AI_WORKER_DENY_FILE:-$HOME/.config/ai-worker/deny-words.txt}"
if [ "$SEARCH_ALL" = 1 ]; then
  EXCLUDES=(--exclude-dir=.git)
else
  EXCLUDES=(--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=releases)
fi
problems=0
WORDS=()

# A list saved on Windows ends its lines with CR, and stray spaces must not hide a word.
# Danh sách lưu trên Windows có CR cuối dòng, và dấu cách thừa không được làm mất từ.
if [ -f "$DENY_FILE" ]; then
  while IFS= read -r word || [ -n "$word" ]; do
    word="$(printf '%s' "$word" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$word" in ''|'#'*) continue ;; esac
    WORDS+=("$word")
  done < "$DENY_FILE"
fi

# Upper and lower case of a non-English letter match only in a UTF-8 locale, and the environment may have none set (a git hook, for example).
# Chỉ ngôn ngữ UTF-8 mới khớp được hoa thường của chữ ngoài tiếng Anh, mà môi trường có thể chưa đặt ngôn ngữ nào (như khi git hook chạy).
# Built-in rules stay on the current locale: their patterns are English, and a UTF-8 locale would skip files with broken bytes.
# Các quy tắc có sẵn giữ nguyên ngôn ngữ hiện tại: mẫu của chúng là tiếng Anh, còn UTF-8 sẽ bỏ qua file có byte hỏng.
WORD_LOCALE=""
for candidate in C.UTF-8 en_US.UTF-8 C.utf8 en_US.utf8; do
  if printf 'đ' | LC_ALL="$candidate" grep -qiF -- 'Đ' 2>/dev/null; then # i18n-allow
    WORD_LOCALE="$candidate"
    break
  fi
done
word_grep() {
  if [ -n "$WORD_LOCALE" ]; then LC_ALL="$WORD_LOCALE" grep "$@"; else grep "$@"; fi
}

# A UTF-8 search can miss a word in a file with broken bytes, so it runs next to a byte-by-byte search that keeps the exact case.
# Tìm theo UTF-8 có thể sót từ trong file có byte hỏng, nên chạy song song với cách tìm theo từng byte, vốn vẫn bắt đúng y hoa thường.
word_search() {
  { LC_ALL=C grep "$@"; word_grep "$@"; } 2>/dev/null | sort -u
}

# Prints a path with each private word replaced by ***, because a path can hold a private word whichever rule found the file.
# In đường dẫn với mỗi từ riêng thay bằng ***, vì đường dẫn có thể chứa từ riêng dù quy tắc nào tìm ra file.
safe_path() {
  local text="$1" word
  [ "${#WORDS[@]}" -gt 0 ] || { printf '%s' "$text"; return; }
  text="$(LC_ALL="${WORD_LOCALE:-${LC_ALL:-}}" MASK_TEXT="$text" MASK_WORDS="$(printf '%s\n' "${WORDS[@]}")" awk 'BEGIN {
    s = ENVIRON["MASK_TEXT"]; n = split(ENVIRON["MASK_WORDS"], w, "\n")
    for (i = 1; i <= n; i++) {
      if (w[i] == "") continue
      out = ""; rest = s
      while ((p = index(tolower(rest), tolower(w[i]))) > 0) {
        out = out substr(rest, 1, p - 1) "***"; rest = substr(rest, p + length(w[i]))
      }
      s = out rest
    }
    printf "%s", s
  }')"
  # awk may not change the case of every letter, so anything grep still finds hides the whole path.
  # awk có thể không đổi được hoa thường của mọi chữ, nên grep còn thấy từ nào thì ẩn cả đường dẫn.
  for word in "${WORDS[@]}"; do
    if printf '%s' "$text" | LC_ALL=C grep -qiF -- "$word" || printf '%s' "$text" | word_grep -qiF -- "$word"; then
      text="(path hidden)"
      break
    fi
  done
  printf '%s' "$text"
}

# The second pass over every file, and over file names. A path holding a private word is never printed.
# Lượt thứ hai qua mọi file và tên file. Đường dẫn chứa từ riêng không bao giờ được in ra.
DEEP_SEARCH='
import os, sys, unicodedata
def norm(t): return unicodedata.normalize("NFC", t).casefold()
words = [norm(w) for w in sys.stdin.buffer.read().decode("utf-8", "replace").split("\n") if w]
root = sys.argv[1]
skip = {".git"} if os.environ.get("SEARCH_ALL") == "1" else {".git", "dist", "releases", "node_modules"}
def texts(data):
    yield data.decode("utf-8", "ignore")
    for enc in ("utf-16-le", "utf-16-be"):
        yield data.decode(enc, "ignore")
        yield data[1:].decode(enc, "ignore")
def show(rel):
    n = norm(rel)
    return "(path hidden)" if any(w in n for w in words) else rel
def report(rel, rule):
    sys.stdout.buffer.write((show(rel) + "\t" + rule + "\n").encode("utf-8", "replace"))
for folder, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in skip]
    for name in dirs + files:
        rel = os.path.relpath(os.path.join(folder, name), root)
        n = norm(rel)
        for i, w in enumerate(words, 1):
            if w in n:
                report(rel, "private word %d in a name" % i)
    for name in files:
        path = os.path.join(folder, name)
        if os.path.islink(path):
            continue
        try:
            data = open(path, "rb").read()
        except OSError:
            report(os.path.relpath(path, root), "could not be read")
            continue
        found = set()
        for t in texts(data):
            t = norm(t)
            found.update(i for i, w in enumerate(words, 1) if w in t)
        for i in sorted(found):
            report(os.path.relpath(path, root), "private word %d" % i)
'

# report RULE: reads grep output and keeps only the file and line number.
# report RULE: đọc kết quả grep và chỉ giữ tên file với số dòng.
report() {
  while IFS= read -r hit; do
    printf '%s  [%s]\n' "$(safe_path "$(printf '%s' "$hit" | cut -d: -f1,2)")" "$1"
    problems=$((problems + 1))
  done
}

scan() {
  grep -rnIE "${EXCLUDES[@]}" -- "$1" "$ROOT" 2>/dev/null
}

report "private key" < <(scan 'BEGIN [A-Z0-9 ]*PRIVATE KEY')
report "access token" < <(scan '(sk-ant-|sk-proj-|ghp_|github_pat_|xox[bp]-|AKIA)[A-Za-z0-9_-]{12,}')
report "key value" < <(scan '^[[:space:]]*(export[[:space:]]+)?(INGEST_KEY|OTP)=[A-Za-z0-9:_,+/-]{12,}')

# Files that must never be published, by name.
# Các file không bao giờ được công khai, xét theo tên.
while IFS= read -r file; do
  printf '%s  [private file]\n' "$(safe_path "$file")"
  problems=$((problems + 1))
done < <(cd "$ROOT" && find . -path ./.git -prune -o -type f \
  \( -name '.env' -o -name '.env.*' -o -name 'company.json' -o -name 'TRANG-THAI.md' -o -name '*.pem' -o -name 'id_rsa' -o -name 'id_ed25519' -o -name 'accounts.json' -o -name 'identities.json' \
     -o -name 'device-*.json' -o -name 'audit*.jsonl' -o -name 'history.jsonl' -o -name 'tv.json' -o -name 'team-csv.json' -o -name 'locations.json' -o -name 'branches.json' \
     -o -name '*.db' -o -name '*.db-wal' -o -name '*.db-shm' \) -print)

# The server's data folders hold real people's data, whatever the files inside are called.
# Thư mục dữ liệu của máy chủ chứa dữ liệu người thật, dù file bên trong tên gì.
for folder in server/data server/keys server/releases; do
  if [ -d "$ROOT/$folder" ] && ! git -C "$ROOT" check-ignore -q "$folder" 2>/dev/null; then
    printf '%s  [private folder]\n' "$folder"
    problems=$((problems + 1))
  fi
done

# The owner's signing keys stay out of the public repository: the file holds comments only.
# Khoá ký của chủ dự án không nằm trong repo công khai: file chỉ có chú thích.
if [ -f "$ROOT/keys/allowed_signers" ] && grep -qvE '^[[:space:]]*(#|$)' "$ROOT/keys/allowed_signers"; then
  printf '%s  [signing key]\n' "keys/allowed_signers"
  problems=$((problems + 1))
fi

# A skipped build folder is safe only while git does not track it, because tracked files get published.
# Thư mục dựng được bỏ qua chỉ an toàn khi git không theo dõi nó, vì file được theo dõi sẽ bị công khai.
if [ "$SEARCH_ALL" = 0 ]; then
  while IFS= read -r file; do
    printf '%s  [tracked file in a skipped folder]\n' "$(safe_path "$file")"
    problems=$((problems + 1))
  done < <(git -C "$ROOT" ls-files -- ':(glob)**/dist/**' ':(glob)**/releases/**' ':(glob)**/node_modules/**' 2>/dev/null)
fi

# Private words, also searched inside binary files; the list itself is never printed.
# Từ riêng, tìm cả trong file nhị phân; danh sách từ không bao giờ được in ra.
if [ -f "$DENY_FILE" ]; then
  n=0
  for word in ${WORDS[@]+"${WORDS[@]}"}; do
    n=$((n + 1))
    # Without UTF-8 a non-English word could slip through in another case, so the result cannot be called clean.
    # Không có UTF-8 thì từ ngoài tiếng Anh có thể lọt khi khác hoa thường, nên không thể coi kết quả là sạch.
    if [ -z "$WORD_LOCALE" ] && printf '%s' "$word" | LC_ALL=C grep -q '[^ -~]'; then
      printf 'Private word %d has non-English letters, and this computer has no UTF-8 locale to search it in every case.\n' "$n" >&2
      problems=$((problems + 1))
    fi
    while IFS= read -r file; do
      printf '%s  [private word %d]\n' "$(safe_path "$file")" "$n"
      problems=$((problems + 1))
    done < <(word_search -rliaF "${EXCLUDES[@]}" -- "$word" "$ROOT")
    # File and folder names can leak too.
    # Tên file và thư mục cũng có thể lộ.
    while IFS= read -r file; do
      printf '%s  [private word %d in a name]\n' "$(safe_path "$file")" "$n"
      problems=$((problems + 1))
    done < <(names="$(cd "$ROOT" && find . -path ./.git -prune -o -print | LC_ALL=C sed 's#^\./##')"
      { printf '%s\n' "$names" | LC_ALL=C grep -iF -- "$word"; printf '%s\n' "$names" | word_grep -iF -- "$word"; } 2>/dev/null | sort -u)
  done
  if [ "$n" -eq 0 ]; then
    echo "The private word list at $DENY_FILE has no words." >&2
    problems=$((problems + 1))
  fi
  # grep cannot see a word with its accents stored apart, in UTF-16, or in another case next to broken bytes, so a second pass decodes each file.
  # grep không thấy từ có dấu lưu tách rời, từ trong UTF-16, hoặc từ khác hoa thường cạnh byte hỏng, nên lượt thứ hai giải mã từng file.
  if command -v python3 >/dev/null 2>&1 && [ "$n" -gt 0 ]; then
    while IFS=$'\t' read -r file rule; do
      printf '%s  [%s]\n' "$file" "$rule"
      problems=$((problems + 1))
    done < <(printf '%s\n' "${WORDS[@]}" | SEARCH_ALL="$SEARCH_ALL" python3 -I -c "$DEEP_SEARCH" "$ROOT")
  elif [ "$n" -gt 0 ]; then
    echo "python3 is missing, so accents stored apart and UTF-16 files were not searched." >&2
    problems=$((problems + 1))
  fi
elif [ "${AI_WORKER_NO_DENY:-}" = 1 ]; then
  echo "Warning: no private word list at $DENY_FILE, so only the built-in rules ran." >&2
else
  echo "No private word list at $DENY_FILE. Create it, or set AI_WORKER_NO_DENY=1 to run only the built-in rules." >&2
  problems=$((problems + 1))
fi

if [ "$problems" -gt 0 ]; then
  echo "NOT CLEAN: $problems problem(s). Nothing should be published." >&2
  exit 1
fi
echo "Clean."
