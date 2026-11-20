#!/bin/bash
# Daily work is done on the /admin page. This command is only for rescue, when that page cannot be opened.
#   Rescue a lost admin:   sudo bash manage-otp.sh --rescue new-name    (creates or reissues an admin, prints the QR code)
#   Emergency delete:      sudo bash manage-otp.sh --delete name        (removes the account, everyone must log in again)
#   List accounts, roles:  sudo bash manage-otp.sh --list
#   Go back to a version before sealing:  sudo bash manage-otp.sh --unseal   (stores the OTP secrets as they are again, leaves the webhook stopped)
#   The OTP key is lost:   sudo bash manage-otp.sh --forget-sealed      (removes the accounts whose sealed secret no key here opens)
# The name shown in the app is "<OTP_LABEL>: <name>", OTP_LABEL defaults to AI-Worker
# Việc hằng ngày làm ở trang /admin. Lệnh này chỉ để cứu, khi không vào được trang đó.
#   Cứu khi mất quản trị:  sudo bash manage-otp.sh --rescue ten-moi     (tạo hoặc cấp lại một quản trị, in mã QR)
#   Xoá khẩn cấp:          sudo bash manage-otp.sh --delete ten         (bỏ tài khoản, mọi người phải đăng nhập lại)
#   Xem danh sách, vai:    sudo bash manage-otp.sh --list
#   Quay về bản trước khi niêm phong:  sudo bash manage-otp.sh --unseal   (lưu lại khoá OTP dạng thường, để webhook dừng)
#   Mất khoá OTP:          sudo bash manage-otp.sh --forget-sealed      (bỏ các tài khoản mà không khoá nào ở đây mở được khoá đã niêm phong)
# Tên hiện trong app là "<OTP_LABEL>: <tên>", OTP_LABEL mặc định AI-Worker
set -e
# Language of the messages: the same 8 lines as packaging/lang.sh, copied here because server/ is installed without packaging/.
# Ngôn ngữ của thông báo: đúng 8 dòng của packaging/lang.sh, chép vào đây vì server/ được cài mà không có packaging/.
case "${AI_WORKER_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
  vi*) AI_WORKER_LANG=vi ;;
  *) AI_WORKER_LANG=en ;;
esac
export AI_WORKER_LANG
say() { if [ "$AI_WORKER_LANG" = vi ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
if [ "$(id -u)" != 0 ]; then
  say "Run with sudo" "Cần chạy bằng sudo"
  exit 1
fi
ENV=/etc/ai-worker.env
APP_DIR=/opt/ai-worker
# the key that seals the OTP secrets; install.sh makes it, root reads it here directly
# khoá niêm phong khoá OTP; install.sh tạo nó, ở đây root đọc trực tiếp
export OTP_KEY_FILE=${OTP_KEY_FILE:-/etc/ai-worker-otp.key}
OTP_LABEL=${OTP_LABEL:-AI-Worker}
if ! [[ "$OTP_LABEL" =~ ^[A-Za-z0-9._-]{1,30}$ ]]; then
  say "OTP_LABEL may only contain letters without accents, digits, . _ -" "OTP_LABEL chỉ gồm chữ không dấu, số, . _ -"
  exit 1
fi
if [ ! -f "$ENV" ]; then
  say "The webhook is not installed (missing $ENV): run sudo bash install.sh first" "Chưa cài webhook (thiếu $ENV): chạy sudo bash install.sh trước"
  exit 1
fi

case "$1" in
  --rescue) ACTION=rescue; NAME="$2" ;;
  --delete) ACTION=delete; NAME="$2" ;;
  --list) ACTION=list; NAME="" ;;
  --unseal) ACTION=unseal; NAME="" ;;
  --forget-sealed) ACTION=forget-sealed; NAME="" ;;
  *)
    say "To create accounts, change roles or reissue keys, use the /admin page." "Tạo tài khoản, đổi vai, cấp lại khoá: dùng trang /admin."
    say "Lost the admin: sudo bash manage-otp.sh --rescue new-name" "Mất quản trị: sudo bash manage-otp.sh --rescue ten-moi"
    exit 1 ;;
esac
if { [ "$ACTION" = rescue ] || [ "$ACTION" = delete ]; } && ! [[ "$NAME" =~ ^[A-Za-z0-9._-]{1,30}$ ]]; then
  say "The name may only contain letters without accents, digits, . _ - (up to 30 characters)" "Tên chỉ gồm chữ không dấu, số, . _ - (tối đa 30)"
  exit 1
fi
# Text for the list, one line each: admin, wall, viewer, nobody yet. The Python part below prints it.
# Chữ cho danh sách, mỗi dòng một mục: quản trị, treo tường, chỉ xem, chưa có ai. Phần Python bên dưới in ra.
LABELS=$(
say "admin" "quản trị"
say "wall display" "treo tường"
say "view only" "chỉ xem"
say "(nobody yet)" "(chưa có ai)"
)
# What the Python part says when it stops, one line each: sealed secrets no key here opens, no key to unseal with, accounts removed.
# Điều phần Python nói khi dừng, mỗi dòng một câu: khoá đã niêm phong mà không khoá nào ở đây mở được, không có khoá để mở, các tài khoản đã bỏ.
WORDS=$(
say "Some OTP secrets are sealed with a key this server does not have ($OTP_KEY_FILE is missing or another key). Put the key file back from your backup; if it is lost for good: sudo bash manage-otp.sh --forget-sealed" "Một số khoá OTP đã niêm phong bằng một khoá mà máy chủ này không có ($OTP_KEY_FILE bị thiếu hoặc là khoá khác). Chép lại file khoá từ bản sao lưu; nếu mất hẳn: sudo bash manage-otp.sh --forget-sealed"
say "There is no OTP key in $OTP_KEY_FILE to open the sealed secrets with." "Không có khoá OTP trong $OTP_KEY_FILE để mở các khoá đã niêm phong."
say "Removed the accounts whose OTP secret could not be opened:" "Đã bỏ các tài khoản không mở được khoá OTP:"
)

# the webhook writes the accounts file while it runs, so stop it before editing; after a --unseal that worked it stays stopped,
# since starting this version again would seal the secrets once more
# webhook chỉ ghi file tài khoản lúc đang chạy, nên dừng trước khi sửa; sau một lần --unseal thành công thì để dừng,
# vì chạy lại bản này sẽ niêm phong khoá lần nữa
UNSEALED=0
[ "$ACTION" = list ] || systemctl stop ai-worker-webhook
trap '[ "$ACTION" = list ] || [ "$UNSEALED" = 1 ] || systemctl start ai-worker-webhook' EXIT

SECRET=$(python3 - "$ENV" "$APP_DIR" "$ACTION" "$NAME" "$LABELS" "$WORDS" <<'PY'
import base64, json, os, secrets, sys, time
env_path, app_dir, action, name, label_text, words = sys.argv[1:7]
label_admin, label_wall, label_viewer, label_nobody = label_text.split("\n")
say_foreign_key, say_no_key, say_removed = words.split("\n")
# the same code as the webhook opens the accounts database, so the schema is never copied here
# dùng chính code của webhook để mở cơ sở dữ liệu tài khoản, nên không chép lược đồ vào đây
keys_dir = os.path.join(app_dir, "keys")
os.environ["KEYS_DIR"], os.environ["DATA_DIR"] = keys_dir, os.path.join(app_dir, "data")
sys.path.insert(0, app_dir)
from board import db, sealing
keys = db.keys_db()
key = sealing.load_key()


# root may have created or written the database: give its files back to the webhook's account
# root có thể vừa tạo hoặc ghi cơ sở dữ liệu: trả các file lại cho tài khoản của webhook
def give_back():
    keys.conn.close()
    st = os.stat(keys_dir)
    for file_name in os.listdir(keys_dir):
        os.chown(os.path.join(keys_dir, file_name), st.st_uid, st.st_gid)


def stop(text):
    give_back()
    sys.exit(text)


rows = {n: (r, s, b) for n, r, s, b in keys.rows("SELECT name, role, secret, body FROM accounts")}
unreadable = [n for n, (_, s, _) in rows.items() if sealing.is_sealed(s) and sealing.plain(s, n, key) is None]
imported = {r[0] for r in keys.rows("SELECT name FROM imported")}
lines = open(env_path).read().splitlines()
def get(var):
    return next((x[len(var) + 1:] for x in lines if x.startswith(var + "=")), "")
entries = [m for m in get("OTP").split(",") if ":" in m]
admins = {t for t in get("OTP_ADMINS").split(",") if t}
wall = {t for t in get("OTP_WALL").split(",") if t}
if action == "list":
    # the accounts database is the main source; names not imported yet are read from the config for now
    # cơ sở dữ liệu tài khoản là nguồn chính; chưa nhập thì đọc tạm từ cấu hình
    listed = {n: r for n, (r, _, _) in rows.items()}
    for m in entries:
        t = m.split(":")[0]
        if t not in imported:
            listed.setdefault(t, "admin" if t in admins else "wall" if t in wall else "viewer")
    labels = {"admin": label_admin, "wall": label_wall, "viewer": label_viewer}
    print("\n".join(t + "  (" + labels.get(v, v) + ")" for t, v in sorted(listed.items())) or label_nobody, file=sys.stderr)
    give_back()
    sys.exit(0)

secret = ""
if action == "unseal":
    if unreadable:
        stop(say_foreign_key)
    if any(sealing.is_sealed(s) for _, s, _ in rows.values()) and not key:
        stop(say_no_key)
    with keys.tx() as c:
        for n, (r, s, b) in rows.items():
            if sealing.is_sealed(s):
                v = json.loads(b)
                v["secret"] = sealing.unseal(s, n, key)
                c.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)", db.account_row(n, v))
        c.execute("DELETE FROM meta WHERE key = 'otp_key_id'")
        # version 1 is the schema of the versions before sealing: they open the file again
        # phiên bản 1 là lược đồ của các bản trước khi niêm phong: chúng mở lại được file
        c.execute("PRAGMA user_version=1")
elif action == "forget-sealed":
    with keys.tx() as c:
        for n in unreadable:
            c.execute("DELETE FROM accounts WHERE name = ?", (n,))
            c.execute("INSERT OR IGNORE INTO imported VALUES (?)", (n,))
        c.execute("DELETE FROM meta WHERE key = 'otp_key_id'")
    print(say_removed + " " + (", ".join(sorted(unreadable)) or "-"), file=sys.stderr)
elif action == "rescue":
    # written straight into the database, sealed when there is a key: the secret never goes through the config file
    # ghi thẳng vào cơ sở dữ liệu, niêm phong khi có khoá: khoá không bao giờ đi qua file cấu hình
    if unreadable:
        stop(say_foreign_key)
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    old = json.loads(rows[name][2]) if name in rows else {"createdAt": int(time.time() * 1000), "createdBy": "rescue"}
    old.update({"role": "admin", "secret": sealing.stored(secret, name, key)})
    with keys.tx() as c:
        c.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)", db.account_row(name, old))
        c.execute("INSERT OR IGNORE INTO imported VALUES (?)", (name,))
    imported.add(name)
else:
    with keys.tx() as c:
        c.execute("DELETE FROM accounts WHERE name = ?", (name,))
        c.execute("INSERT OR IGNORE INTO imported VALUES (?)", (name,))
    imported.add(name)
# no old copy of a secret stays in the file's free pages or its WAL
# không bản cũ nào của khoá còn nằm trong các trang trống hay WAL của file
keys.compact()
# the config file keeps only the names not imported yet: an imported name's secret has no business there any more
# file cấu hình chỉ giữ các tên chưa nhập: khoá của tên đã nhập không còn lý do nằm ở đó
entries = [m for m in entries if m.split(":")[0] not in imported]
left = {m.split(":")[0] for m in entries}
lines = [x for x in lines if not x.startswith(("OTP=", "OTP_ADMINS=", "OTP_WALL="))]
if entries: lines.append("OTP=" + ",".join(entries))
if admins & left: lines.append("OTP_ADMINS=" + ",".join(sorted(admins & left)))
if wall & left: lines.append("OTP_WALL=" + ",".join(sorted(wall & left)))
tmp_path = env_path + ".tmp"
with open(os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
    f.write("\n".join(lines) + "\n")
os.replace(tmp_path, env_path)
give_back()
print(secret)
PY
)
[ "$ACTION" = list ] && exit 0
# leave a trace of who issued/revoked a key: look with journalctl -t ai-worker-otp
# để lại dấu vết ai cấp/thu hồi khoá: xem bằng journalctl -t ai-worker-otp
logger -t ai-worker-otp "$ACTION $NAME (by ${SUDO_USER:-root})" 2>/dev/null || true

if [ "$ACTION" = unseal ]; then
  UNSEALED=1
  say "The OTP secrets are stored as they are again, and the webhook is stopped. Now install the older version; to stay on this one instead, start the webhook (sudo systemctl start ai-worker-webhook) and it seals them again." "Khoá OTP đã lưu lại dạng thường, và webhook đang dừng. Giờ cài bản cũ; muốn ở lại bản này thì bật webhook (sudo systemctl start ai-worker-webhook), nó sẽ niêm phong lại."
  exit 0
fi
if [ "$ACTION" = forget-sealed ]; then
  say "Create those accounts again on the /admin page, or with --rescue for an admin." "Tạo lại các tài khoản đó ở trang /admin, hoặc bằng --rescue cho một quản trị."
  exit 0
fi
if [ "$ACTION" = delete ]; then
  say "Deleted the account $NAME. Everyone has to log in again." "Đã xoá tài khoản $NAME. Mọi người phải đăng nhập lại."
  exit 0
fi

URI="otpauth://totp/$OTP_LABEL:$NAME?secret=$SECRET&issuer=$OTP_LABEL&digits=6&period=30"
echo
say "Open Google Authenticator on your phone > the + sign > Scan QR code:" "Mở Google Authenticator trên điện thoại > dấu + > Quét mã QR:"
echo
if command -v qrencode >/dev/null; then
  qrencode -t ansiutf8 "$URI"
else
  say "(the server has no qrencode to print the QR code: sudo apt install qrencode, or use the key below)" "(máy chủ chưa có qrencode để in mã QR: sudo apt install qrencode, hoặc dùng khoá bên dưới)"
fi
echo
say "Or choose 'Enter a setup key' and type:" "Hoặc chọn 'Nhập khoá thiết lập' và gõ:"
say "  Account name: $OTP_LABEL: $NAME" "  Tên tài khoản: $OTP_LABEL: $NAME"
say "  Key: $(echo "$SECRET" | sed 's/.\{4\}/& /g')" "  Khoá: $(echo "$SECRET" | sed 's/.\{4\}/& /g')"
say "  Key type: Time based" "  Loại khoá: Dựa trên thời gian"
echo
say "When done, clear the screen (the clear command). $NAME is an admin; do everything else on the /admin page. Everyone has to log in again." "Xong thì xoá màn hình (lệnh clear). $NAME là quản trị, các việc khác làm ở trang /admin. Mọi người phải đăng nhập lại."
