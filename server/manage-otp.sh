#!/bin/bash
# Daily work is done on the /admin page. This command is only for rescue, when that page cannot be opened.
#   Rescue a lost admin:   sudo bash manage-otp.sh --rescue new-name    (creates or reissues an admin, prints the QR code)
#   Emergency delete:      sudo bash manage-otp.sh --delete name        (removes the account, everyone must log in again)
#   List accounts, roles:  sudo bash manage-otp.sh --list
# The name shown in the app is "<OTP_LABEL>: <name>", OTP_LABEL defaults to AI-Worker
# Việc hằng ngày làm ở trang /admin. Lệnh này chỉ để cứu, khi không vào được trang đó.
#   Cứu khi mất quản trị:  sudo bash manage-otp.sh --rescue ten-moi     (tạo hoặc cấp lại một quản trị, in mã QR)
#   Xoá khẩn cấp:          sudo bash manage-otp.sh --delete ten         (bỏ tài khoản, mọi người phải đăng nhập lại)
#   Xem danh sách, vai:    sudo bash manage-otp.sh --list
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
  *)
    say "To create accounts, change roles or reissue keys, use the /admin page." "Tạo tài khoản, đổi vai, cấp lại khoá: dùng trang /admin."
    say "Lost the admin: sudo bash manage-otp.sh --rescue new-name" "Mất quản trị: sudo bash manage-otp.sh --rescue ten-moi"
    exit 1 ;;
esac
if [ "$ACTION" != list ] && ! [[ "$NAME" =~ ^[A-Za-z0-9._-]{1,30}$ ]]; then
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

# the webhook writes the accounts file while it runs, so stop it before editing
# webhook chỉ ghi file tài khoản lúc đang chạy, nên dừng trước khi sửa
[ "$ACTION" = list ] || systemctl stop ai-worker-webhook
trap '[ "$ACTION" = list ] || systemctl start ai-worker-webhook' EXIT

SECRET=$(python3 - "$ENV" "$APP_DIR" "$ACTION" "$NAME" "$LABELS" <<'PY'
import base64, os, secrets, sys
env_path, app_dir, action, name, label_text = sys.argv[1:6]
label_admin, label_wall, label_viewer, label_nobody = label_text.split("\n")
# the same code as the webhook opens the accounts database, so the schema is never copied here
# dùng chính code của webhook để mở cơ sở dữ liệu tài khoản, nên không chép lược đồ vào đây
keys_dir = os.path.join(app_dir, "keys")
os.environ["KEYS_DIR"], os.environ["DATA_DIR"] = keys_dir, os.path.join(app_dir, "data")
sys.path.insert(0, app_dir)
from board import db
keys = db.keys_db()


# root may have created or written the database: give its files back to the webhook's account
# root có thể vừa tạo hoặc ghi cơ sở dữ liệu: trả các file lại cho tài khoản của webhook
def give_back():
    keys.conn.close()
    st = os.stat(keys_dir)
    for file_name in os.listdir(keys_dir):
        os.chown(os.path.join(keys_dir, file_name), st.st_uid, st.st_gid)


accounts = {t: r for t, r in keys.rows("SELECT name, role FROM accounts")}
imported = [r[0] for r in keys.rows("SELECT name FROM imported")]
lines = open(env_path).read().splitlines()
def get(var):
    return next((x[len(var) + 1:] for x in lines if x.startswith(var + "=")), "")
entries = [m for m in get("OTP").split(",") if ":" in m]
admins = {t for t in get("OTP_ADMINS").split(",") if t}
wall = {t for t in get("OTP_WALL").split(",") if t}
if action == "list":
    # the accounts database is the main source; names not imported yet are read from the config for now
    # cơ sở dữ liệu tài khoản là nguồn chính; chưa nhập thì đọc tạm từ cấu hình
    rows = dict(accounts)
    for m in entries:
        t = m.split(":")[0]
        if t not in imported:
            rows.setdefault(t, "admin" if t in admins else "wall" if t in wall else "viewer")
    labels = {"admin": label_admin, "wall": label_wall, "viewer": label_viewer}
    print("\n".join(t + "  (" + labels.get(v, v) + ")" for t, v in sorted(rows.items())) or label_nobody, file=sys.stderr)
    give_back()
    sys.exit(0)
entries = [m for m in entries if m.split(":")[0] != name]
admins.discard(name); wall.discard(name)
secret = ""
if action == "rescue":
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    entries.append(name + ":" + secret)
    admins.add(name)
    # remove it from the imported list so the webhook imports it again at start
    # bỏ khỏi danh sách đã nhập để webhook nhập lại khi khởi động
    with keys.tx() as c:
        c.execute("DELETE FROM imported WHERE name = ?", (name,))
else:
    with keys.tx() as c:
        c.execute("DELETE FROM accounts WHERE name = ?", (name,))
        c.execute("INSERT OR IGNORE INTO imported VALUES (?)", (name,))
lines = [x for x in lines if not x.startswith(("OTP=", "OTP_ADMINS=", "OTP_WALL="))]
if entries: lines.append("OTP=" + ",".join(entries))
if admins: lines.append("OTP_ADMINS=" + ",".join(sorted(admins)))
if wall: lines.append("OTP_WALL=" + ",".join(sorted(wall)))
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
