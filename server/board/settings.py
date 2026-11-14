"""Settings of the board server: environment variables, limits and time windows.
Cấu hình máy chủ bảng tổng: biến môi trường, giới hạn và khoảng thời gian."""

import http.client
import os
import re
from datetime import timedelta, timezone

# the server folder: webhook.py, static/, menubar/ and the default data/ and keys/ sit here
# thư mục máy chủ: webhook.py, static/, menubar/ và data/, keys/ mặc định nằm ở đây
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PORT = int(os.environ.get("PORT", "8788"))
BIND_ADDR = os.environ.get("BIND_ADDR", "127.0.0.1")
INGEST_KEY = os.environ.get("INGEST_KEY", "")
# Log in with Telegram (optional): the bot's token and its @username without the @, both from @BotFather. Off while either is empty.
# The token can sign a login for anyone, so it stays in the env file like INGEST_KEY, never in git.
# Đăng nhập bằng Telegram (tuỳ chọn): khoá của bot và tên @ của bot không có @, cả hai lấy từ @BotFather. Tắt khi thiếu một trong hai.
# Khoá này ký được lần đăng nhập của bất kỳ ai, nên nằm trong file env như INGEST_KEY, không bao giờ vào git.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_NAME = os.environ.get("TELEGRAM_BOT_NAME", "").strip().lstrip("@")
# Listening only inside the machine means a local proxy is the way in, so its X-Forwarded-For is trusted by default.
# Without this, one person's wrong codes would lock everyone, because everyone looks like 127.0.0.1. TRUST_PROXY=0 turns it off.
# Chỉ nghe trong máy nghĩa là đi vào qua proxy trên máy, nên mặc định tin X-Forwarded-For của proxy đó.
# Nếu không, một người nhập sai sẽ khoá mọi người, vì ai cũng giống 127.0.0.1. TRUST_PROXY=0 để tắt.
TRUST_PROXY = (os.environ.get("TRUST_PROXY") or ("1" if BIND_ADDR in ("127.0.0.1", "::1", "localhost") else "0")) == "1"
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(SERVER_DIR, "data"))

MAX_BODY_BYTES = 256 * 1024
# Limits that stop one client from using up the server: open connections in all, per IP, and the life of one connection.
# Giới hạn để một máy không làm cạn máy chủ: tổng số kết nối, số kết nối mỗi IP, và thời gian sống của một kết nối.
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "256"))
MAX_CONNECTIONS_PER_IP = 16
CONNECTION_DEADLINE_SECONDS = 120
# Request headers are held in memory before any login check, so keep them small.
# Header của yêu cầu nằm trong bộ nhớ trước mọi bước kiểm đăng nhập, nên giữ ở mức nhỏ.
http.client._MAXLINE = 8190
http.client._MAXHEADERS = 64
# a device silent for too long (left the job, changed computer) is dropped from the board
# máy im lặng quá lâu (nghỉ việc, đổi máy) thì bỏ khỏi bảng
KEEP_DAYS = 30
# the plugin sends 8 days of hours; a little room above that
# plugin gửi 8 ngày theo giờ; để dư một chút
MAX_HOURS_PER_DEVICE = 8 * 24 + 48
DEVICE_NAME_RE = re.compile(r"device-[a-z0-9]{1,40}\Z")

USD_RATE = float(os.environ.get("USD_RATE", "26000"))
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET", "7"))))
# a device that has not sent for over 12 minutes counts as offline (same as the board on the manager's machine)
# máy không gửi quá 12 phút thì coi là ngoại tuyến (giống bảng trên máy quản lý)
OFFLINE_SECONDS = 12 * 60
# a device silent for more than a day: dimmed on /board and not counted (its file is still kept KEEP_DAYS days)
# máy không gửi quá 1 ngày: trên /board làm mờ và không tính vào số máy (file vẫn giữ KEEP_DAYS ngày)
STALE_DEVICE_SECONDS = 24 * 3600
IP_HISTORY_MAX = 10
SESSION_SECONDS = 8 * 3600
WALL_SESSION_SECONDS = 7 * 86400
# after one OTP re-entry, account actions do not ask again for this many seconds
# nhập lại OTP một lần thì các thao tác về tài khoản không hỏi lại trong ngần này giây
CONFIRM_SECONDS = 5 * 60
CONFIRM_MAX_FAILS = 5
MAX_ACCOUNTS = 200
# TV pairing: the code shown on the TV lives this many seconds; once approved, the TV has this many seconds to receive the session
# ghép màn hình TV: mã hiện trên TV sống ngần này giây, duyệt rồi thì TV có ngần này giây để nhận phiên
TV_CODE_SECONDS = 600
TV_APPROVE_SECONDS = 300
TV_SESSION_SECONDS = 30 * 86400
# menu bar window: a one-time code that lets the window take the paired computer's session, single use
# khung thanh menu: mã dùng một lần để khung nhận phiên của máy đã ghép, dùng xong là hết
MINI_HANDOFF_SECONDS = 90
MINI_HANDOFF_MAX = 500
# live one-time codes per paired computer; asking for one more drops that computer's oldest, so one computer cannot fill the table
# số mã dùng một lần còn hạn của mỗi máy đã ghép; xin thêm thì bỏ mã cũ nhất của máy đó, để một máy không lấp đầy bảng
MINI_HANDOFF_PER_TOKEN = 3
MINI_NOTIFY_MINUTES = (5, 10, 15, 30, 60)
# a manager pairs the menu bar with their own account and OTP; at most this many computers per account
# quản lý tự ghép thanh menu bằng tài khoản và OTP của mình; mỗi tài khoản tối đa bấy nhiêu máy
MENUBAR_PER_ACCOUNT = 2
TV_CEILING_SECONDS = 365 * 86400
TV_RENEW_WHEN_LEFT = 25 * 86400
TV_MAX = 20
TV_PENDING_PER_IP = 3
TV_PENDING_TOTAL = 30
TV_VIEW_MAX_FAILS = 20
TV_VIEW_FAIL_SECONDS = 600
# the TV sends a request every 10 seconds; only past this many seconds is it reported as not seen for a while
# TV gửi yêu cầu mỗi 10 giây; quá ngần này mới báo là lâu chưa thấy
TV_ABSENT_SECONDS = 120
# a revoked key is remembered this long, so its later use can be written to the log; each key is logged at most once an hour
# khoá đã thu hồi được nhớ ngần này, để lần dùng sau đó ghi được vào nhật ký; mỗi khoá ghi tối đa mỗi giờ một lần
TV_REVOKED_KEEP_SECONDS = TV_SESSION_SECONDS
TV_REVOKED_MAX = 500
TV_REVOKED_LOG_SECONDS = 3600
# the kind of a pairing made by the manager browser extension, shown apart from screens in /admin
# loại của lần ghép do tiện ích trình duyệt cho quản lý tạo, hiện riêng với màn hình trong /admin
KIND_EXTENSION = "extension"
# the kind of a pairing made by a manager's Claude plugin, which reads the board so Claude can answer questions about it:
# the same pairing, the same wall view and the same revoking as the extension, named apart in /admin
# loại của lần ghép do plugin Claude của quản lý tạo, plugin đọc bảng để Claude trả lời câu hỏi về bảng:
# cùng cách ghép, cùng phần treo tường và cùng cách thu hồi như tiện ích, được gọi tên riêng trong /admin
KIND_PLUGIN = "plugin"
KEYS_DIR = os.environ.get("KEYS_DIR", os.path.join(SERVER_DIR, "keys"))
OTP_LABEL = os.environ.get("OTP_LABEL", "AI-Worker")
MAX_FAILS = 5
FAIL_WINDOW_SECONDS = 15 * 60
# Wrong entries per account: stops guessing from many addresses without letting a stranger lock the whole site.
# Số lần sai theo từng tài khoản: chặn đoán từ nhiều địa chỉ mà người lạ không khoá được cả trang.
MAX_FAILS_PER_ACCOUNT = 20
# limits on sending data: per IP per 10 minutes, new devices per IP per day, total number of devices
# giới hạn gửi số liệu: mỗi IP / 10 phút, máy mới mỗi IP / ngày, tổng số máy
INGEST_PER_IP = 300
NEW_DEVICES_PER_IP = 10
MAX_DEVICES = 300
