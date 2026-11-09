#!/usr/bin/env bash
# Tests packaging/check-clean.sh with made-up private words. Run from anywhere; it only writes in a temporary folder.
# Thử packaging/check-clean.sh bằng từ riêng giả. Chạy ở đâu cũng được; chỉ ghi trong thư mục tạm.
set -u
CHECK="$(cd "$(dirname "$0")/.." && pwd)/packaging/check-clean.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1
printf 'zebrafoo\nđườngxanh\n' > deny.txt # i18n-allow
export AI_WORKER_DENY_FILE="$WORK/deny.txt"
fails=0
count=0

# expect NAME CODE [check-clean arguments]: the exit code must be CODE, and the private words never printed.
# expect TÊN MÃ [tham số check-clean]: mã thoát phải là MÃ, và không bao giờ in từ riêng.
expect() {
  local name="$1" want="$2" out got
  shift 2
  out="$(bash "$CHECK" "$@" 2>&1)"
  got=$?
  count=$((count + 1))
  if [ "$got" != "$want" ]; then
    echo "FAIL $name: exit $got, wanted $want"
    fails=$((fails + 1))
  elif printf '%s' "$out" | python3 -I -c 'import sys,unicodedata as u; t=u.normalize("NFC",sys.stdin.read()).casefold(); sys.exit(any(w in t for w in ("zebrafoo","đườngxanh")))'; then # i18n-allow
    echo "ok   $name"
  else
    echo "FAIL $name: printed a private word"
    fails=$((fails + 1))
  fi
}

# Writes text to a file, given as Python: python_write FILE EXPRESSION.
# Ghi vào file, nội dung viết bằng Python: python_write FILE BIỂU_THỨC.
python_write() {
  python3 -I -c "import sys,unicodedata as u; word='đườngxanh'; open(sys.argv[1],'wb').write($2)" "$1" # i18n-allow
}

mkdir clean
echo nothing here > clean/x.txt
expect "a clean folder" 0 clean
expect "a missing folder" 2 "$WORK/missing"

for folder in dist releases node_modules; do
  mkdir -p "all-$folder/$folder"
  echo zebrafoo > "all-$folder/$folder/x.txt"
  expect "$folder is searched with --all" 1 --all "all-$folder"
  expect "$folder is skipped without --all" 0 "all-$folder"
done

mkdir tracked
git -C tracked init -q
mkdir tracked/dist
echo nothing here > tracked/dist/x.txt
git -C tracked add dist/x.txt
expect "a tracked file in a skipped folder" 1 tracked

mkdir self
echo zebrafoo > self/check-clean.sh
expect "a file named check-clean.sh" 1 self

mkdir ascii; echo ZEBRAFOO > ascii/x.txt
expect "another case" 1 ascii
mkdir upper; python_write upper/x.txt "word.upper().encode()"
expect "Vietnamese in another case" 1 upper
LC_ALL=C expect "Vietnamese in another case without a locale" 1 upper
mkdir nfd; python_write nfd/x.txt "u.normalize('NFD',word).encode()"
expect "accents stored apart" 1 nfd
mkdir broken; python_write broken/x.bin "b'\xff\xfe\x00'+word.upper().encode()+b'\x00'"
expect "another case next to broken bytes" 1 broken
mkdir utf16; python_write utf16/x.bin "word.encode('utf-16-le')"
expect "UTF-16" 1 utf16
mkdir utf16be; python_write utf16be/x.bin "b'\x00'+word.encode('utf-16-be')"
expect "UTF-16 at an odd offset" 1 utf16be

mkdir name; echo x > name/zebrafoo.txt
expect "a file name" 1 name
mkdir 'hash#path'; echo x > 'hash#path/zebrafoo.txt'
expect "a file name under a path with #" 1 'hash#path'
mkdir 'bracket[path'; echo x > 'bracket[path/zebrafoo.txt'
expect "a file name under a path with [" 1 'bracket[path'
mkdir nfdname; python3 -I -c "import unicodedata as u; open('nfdname/'+u.normalize('NFD','đườngxanh.txt'),'w').write('x')" # i18n-allow
expect "a file name with accents stored apart" 1 nfdname

: > empty.txt
AI_WORKER_DENY_FILE="$WORK/empty.txt" expect "an empty word list" 1 clean
AI_WORKER_DENY_FILE="$WORK/none.txt" expect "no word list" 1 clean
AI_WORKER_DENY_FILE="$WORK/none.txt" AI_WORKER_NO_DENY=1 expect "no word list, allowed on purpose" 0 clean
printf 'zebrafoo\r\n' > crlf.txt
AI_WORKER_DENY_FILE="$WORK/crlf.txt" expect "a word list saved on Windows" 1 ascii

echo "$((count - fails)) of $count passed"
[ "$fails" -eq 0 ]
