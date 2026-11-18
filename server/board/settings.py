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
# totals per person per day are kept for this many calendar months, the current one included: 13 leaves the same month of last year whole
# tổng theo từng người từng ngày được giữ ngần này tháng dương lịch, tính cả tháng hiện tại: 13 thì tháng cùng kỳ năm trước còn trọn vẹn
DAILY_KEEP_MONTHS = 13
# every run counts today and the days before it again, this many days in all. A computer holds 8 days of hours, so 7 days are always whole;
# a day older than that is left as it was last written
# mỗi lần chạy đếm lại hôm nay và các ngày trước đó, tổng cộng ngần này ngày. Mỗi máy giữ 8 ngày theo giờ, nên 7 ngày luôn trọn vẹn;
# ngày cũ hơn thì giữ nguyên như lần ghi cuối
DAILY_RECOUNT_DAYS = 7
DAILY_RECOUNT_SECONDS = 5 * 60
# how many weeks the chart of cost per week on /board goes back, the current week included
# biểu đồ chi phí theo tuần trên /board lùi lại bao nhiêu tuần, tính cả tuần hiện tại
DAILY_CHART_WEEKS = 12

USD_RATE = float(os.environ.get("USD_RATE", "26000"))
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET", "7"))))
# a device that has not sent for over 12 minutes counts as offline (same as the board on the manager's machine)
# máy không gửi quá 12 phút thì coi là ngoại tuyến (giống bảng trên máy quản lý)
OFFLINE_SECONDS = 12 * 60
# coding tools other than Claude Code whose sessions a computer may report, through the connector in connectors/
# các công cụ lập trình ngoài Claude Code mà một máy có thể báo phiên, qua bộ nối trong connectors/
CONNECTOR_TOOLS = ("codex", "cursor", "gemini")
# the connector sends only when something happens in a tool, with no beat in between, so its report counts for longer:
# with the 12 minutes above, a person whose tool has waited 20 minutes for an answer would already be shown as offline
# bộ nối chỉ gửi khi có việc xảy ra trong công cụ, không có nhịp ở giữa, nên báo cáo của nó được tính lâu hơn:
# với 12 phút ở trên, người có công cụ đã chờ trả lời 20 phút sẽ bị hiện là ngoại tuyến
CONNECTOR_OFFLINE_SECONDS = 2 * 3600
# "working" from the connector is believed for less long: a tool whose turn fails or is cut short sends no event,
# so its session would stay "working". While work really goes on the connector sends again at least every 5 minutes.
# "đang làm" từ bộ nối được tin trong thời gian ngắn hơn: công cụ có lượt bị lỗi hoặc bị cắt ngang không gửi sự kiện nào,
# nên phiên của nó sẽ kẹt ở "đang làm". Khi việc thật sự còn chạy thì bộ nối gửi lại ít nhất 5 phút một lần.
CONNECTOR_WORKING_SECONDS = 30 * 60
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
# the kind of a key for the MCP endpoint, which lets any AI tool that speaks MCP read the board's numbers. Paired with a code an admin
# approves, like the others, but kept apart from them: this key works on /mcp only, and no other key works there
# loại của khoá cho cổng MCP, cổng cho mọi công cụ AI nói được MCP đọc số liệu của bảng. Ghép bằng mã do quản trị duyệt
# như các loại kia, nhưng tách riêng: khoá này chỉ dùng được ở /mcp, và không khoá nào khác dùng được ở đó
# a key for an AI tool unused this many days is pointed out on the Admin page, for an admin to revoke if nobody needs it
# khoá cho công cụ AI không dùng từng này ngày được chỉ ra trên trang Quản trị, để quản trị thu hồi nếu không ai cần
MCP_IDLE_DAYS = 30
KIND_MCP = "mcp"
# MCP=0 takes the MCP endpoint and its pairing paths away: they answer 404. On by default; nothing can be read until an admin approves a key
# MCP=0 gỡ cổng MCP và các đường ghép của nó: chúng trả 404. Mặc định bật; không đọc được gì cho tới khi quản trị duyệt một khoá
MCP_ENABLED = os.environ.get("MCP", "1").strip() != "0"
MCP_KEYS_MAX = 50
# requests one key may make in the window; a person asking questions through an AI tool stays far below it
# số yêu cầu một khoá được gửi trong khoảng thời gian; một người hỏi qua công cụ AI còn cách rất xa mức này
MCP_CALLS_PER_KEY = 120
MCP_CALLS_WINDOW_SECONDS = 600
# calls to the board's MCP tool stay in the log for this many months
# các lần gọi công cụ MCP của bảng được giữ trong nhật ký ngần này tháng
MCP_CALL_KEEP_MONTHS = 3
# the kind of a Telegram chat an admin approved to ask the board. Paired with a code an admin approves, like the others, and kept apart
# like an MCP key: what stands for the chat is the Telegram user's number, which is taken only on /bot/telegram and opens nothing else
# loại của một chat Telegram đã được quản trị duyệt cho hỏi bảng. Ghép bằng mã do quản trị duyệt như các loại kia, và tách riêng
# như khoá MCP: thứ đứng thay cho chat là số của người dùng Telegram, chỉ được nhận ở /bot/telegram và không mở được gì khác
KIND_TELEGRAM = "telegram"
# Asking the board from Telegram is off until the server's owner sets TELEGRAM_ASK=1. Once on, a separate bot process on this machine
# talks to Telegram, and names and costs reach a third party for each chat an admin approves. This webhook itself still never calls out.
# TELEGRAM_ASK_KEY is what that process shows on /bot/telegram; the installer makes it. With no key of 32 characters or more, it stays off
# Hỏi bảng qua Telegram tắt cho tới khi chủ máy chủ đặt TELEGRAM_ASK=1. Khi bật, một tiến trình bot riêng trên máy này nói chuyện với
# Telegram, và tên cùng chi phí tới một bên thứ ba cho mỗi chat được quản trị duyệt. Chính webhook này vẫn không bao giờ gọi ra ngoài.
# TELEGRAM_ASK_KEY là thứ tiến trình đó trình ra ở /bot/telegram; bộ cài tạo nó. Không có khoá từ 32 ký tự trở lên thì vẫn tắt
TELEGRAM_ASK_KEY = os.environ.get("TELEGRAM_ASK_KEY", "").strip()
TELEGRAM_ASK_ENABLED = os.environ.get("TELEGRAM_ASK", "0").strip() == "1" and len(TELEGRAM_ASK_KEY) >= 32
# The board's small window opened inside Telegram (a Telegram Mini App), for chats an admin allows one by one. Off unless the owner sets
# TELEGRAM_APP=1 and the address of the window, TELEGRAM_APP_URL (https://<board>/tg/app). The installer writes TELEGRAM_APP_KEY, the key
# Telegram's rule derives from the bot token to sign what it hands the window: it checks a signature but cannot drive the bot.
# Khung nhỏ của bảng mở bên trong Telegram (một Telegram Mini App), cho từng chat được quản trị cho phép. Tắt trừ khi chủ máy chủ đặt
# TELEGRAM_APP=1 và địa chỉ của khung, TELEGRAM_APP_URL (https://<bảng>/tg/app). Bộ cài ghi TELEGRAM_APP_KEY, khoá mà quy tắc của Telegram
# suy ra từ khoá bot để ký thứ nó giao cho khung: khoá này kiểm được chữ ký nhưng không điều khiển được bot.
TELEGRAM_APP_KEY = os.environ.get("TELEGRAM_APP_KEY", "").strip().lower()
TELEGRAM_APP_URL = os.environ.get("TELEGRAM_APP_URL", "").strip()
TELEGRAM_APP_ENABLED = (TELEGRAM_ASK_ENABLED and os.environ.get("TELEGRAM_APP", "0").strip() == "1" and re.fullmatch(r"[0-9a-f]{64}", TELEGRAM_APP_KEY) is not None
                        and re.fullmatch(r"https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/tg/app", TELEGRAM_APP_URL) is not None)
TELEGRAM_CHATS_MAX = 50
# chats waiting for an admin at one time. Counted apart from screens, so strangers who press Start cannot keep a TV from pairing
# số chat cùng lúc chờ quản trị. Đếm riêng với màn hình, để người lạ bấm Start không làm TV hết chỗ ghép
TELEGRAM_PENDING_MAX = 10
# messages one approved chat may send in the window; a person tapping buttons on a phone stays far below it
# số tin một chat đã duyệt được gửi trong khoảng thời gian; một người bấm nút trên điện thoại còn cách rất xa mức này
TELEGRAM_CALLS_PER_CHAT = 20
TELEGRAM_CALLS_WINDOW_SECONDS = 600
# a chat that is not approved is told so once in this time, and gets no answer in between
# chat chưa được duyệt được báo một lần trong khoảng này, giữa chừng thì không nhận câu trả lời nào
TELEGRAM_STRANGER_SECONDS = 3600
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
