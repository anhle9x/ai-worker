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
# What the shared INGEST_KEY may still do now that each computer gets a key of its own (board/devicekeys.py):
# allow: any computer without a key of its own may send with it, and gets its own key in the answer (the default);
# known-only: only computers the server already knows, so a leaked package cannot add new ones;
# off: nobody sends with it any more (the plugin's updates still download with it).
# Khoá chung INGEST_KEY còn được làm gì khi mỗi máy đã có khoá riêng (board/devicekeys.py):
# allow: máy nào chưa có khoá riêng cũng gửi được bằng nó, và nhận khoá riêng trong câu trả lời (mặc định);
# known-only: chỉ những máy máy chủ đã biết, để một gói cài bị lộ không thêm được máy mới;
# off: không ai gửi bằng nó nữa (bản cập nhật của plugin vẫn tải bằng nó).
SHARED_KEY_MODE = os.environ.get("SHARED_KEY_MODE", "allow") if os.environ.get("SHARED_KEY_MODE", "allow") in ("allow", "known-only", "off") else "allow"
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
# Requests being answered at once past which the server is busy: then a send, or a request from someone not logged in, gets 503 at once
# with Retry-After, instead of waiting behind the others until everything times out. Logged-in people and keyed devices are still answered.
# Số yêu cầu đang được trả lời cùng lúc mà quá mức đó thì máy chủ đang bận: khi đó một lần gửi, hay yêu cầu của người chưa đăng nhập, nhận 503
# ngay kèm Retry-After, thay vì xếp hàng sau các yêu cầu khác cho tới khi tất cả hết giờ. Người đã đăng nhập và thiết bị có khoá vẫn được trả lời.
BUSY_REQUESTS = max(1, int(os.environ.get("BUSY_REQUESTS", "32")))
BUSY_RETRY_SECONDS = 30
# the most of a turned-away request's body the server still reads, so the sender gets the 503; past it the connection is just closed
# phần thân nhiều nhất của yêu cầu bị từ chối mà máy chủ vẫn đọc, để máy gửi nhận được 503; quá mức đó thì chỉ đóng kết nối
BUSY_READ_BYTES = 16 * 1024
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
# the kind of a key an AI project or application sends its own measurements with (skills/ai-cost-report): made by an admin on the
# Admin page, shown once, kept apart like an MCP key. It works on /projects/ingest only, writes only, and no other key works there
# loại của khoá mà một dự án hay ứng dụng AI dùng để gửi số đo của chính nó (skills/ai-cost-report): quản trị tạo trên trang
# Quản trị, hiện một lần, tách riêng như khoá MCP. Nó chỉ dùng được ở /projects/ingest, chỉ ghi, và không khoá nào khác dùng được ở đó
KIND_PROJECT = "project"
# AI_PROJECTS=1 turns on the paths for AI projects and applications. Off by default: updating the server opens no new path by itself
# AI_PROJECTS=1 bật các đường cho dự án hay ứng dụng AI. Mặc định tắt: cập nhật máy chủ không tự mở thêm đường nào
PROJECTS_ENABLED = os.environ.get("AI_PROJECTS", "0").strip() == "1"
PROJECT_KEYS_MAX = 20
# one send: its size, how many turns it may hold; how often one key may send, and how many turns it may add in a day
# một lần gửi: dung lượng, số lượt tối đa; một khoá được gửi bao nhiêu lần, và thêm được bao nhiêu lượt trong một ngày
PROJECT_SEND_MAX_BYTES = 256 * 1024
PROJECT_SEND_MAX_TURNS = 500
PROJECT_SENDS_PER_KEY = 120
PROJECT_SENDS_WINDOW_SECONDS = 600
PROJECT_TURNS_PER_DAY = 100000
# each turn is kept this many days; the totals per day for the current month and the 12 before it, like the people's totals
# mỗi lượt giữ ngần này ngày; tổng theo ngày giữ cho tháng hiện tại và 12 tháng trước, như tổng của từng người
PROJECT_TURN_KEEP_DAYS = 30
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
# limits on sending data: each computer has a bucket of INGEST_BURST sends that refills INGEST_PER_SECOND a second (the plugin sends
# at most every 2 seconds), new devices per IP per day, total number of devices; nothing per address, since a whole office can share one
# giới hạn gửi số liệu: mỗi máy một xô INGEST_BURST lượt gửi, tự đầy lại INGEST_PER_SECOND lượt mỗi giây (plugin gửi nhiều nhất 2 giây
# một lần), máy mới mỗi IP mỗi ngày, tổng số máy; không giới hạn theo địa chỉ, vì cả văn phòng có thể đi chung một địa chỉ
INGEST_BURST = max(1, int(os.environ.get("INGEST_BURST", "20")))
INGEST_PER_SECOND = max(0.01, float(os.environ.get("INGEST_PER_SECOND", "1")))
# what /ingest tells a computer about its pace (format v: 2, docs/DATA-MODEL.md): the shortest gap between sends of numbers and of state,
# and the longest silence allowed; the board shows a computer silent for 12 minutes as offline, so the longest gap stays well below that
# những gì /ingest dặn máy về nhịp gửi (định dạng v: 2, docs/DATA-MODEL.vi.md): khoảng cách ngắn nhất giữa hai lần gửi số và gửi trạng thái,
# và khoảng im lâu nhất được phép; bảng coi máy im 12 phút là ngoại tuyến, nên khoảng im lâu nhất phải dưới mức đó nhiều
INGEST_MIN_GAP_MS = min(max(1000, int(os.environ.get("INGEST_MIN_GAP_MS", "2000"))), 120_000)
INGEST_STATE_GAP_MS = min(max(1000, int(os.environ.get("INGEST_STATE_GAP_MS", "2000"))), 120_000)
INGEST_MAX_GAP_MS = min(max(30_000, int(os.environ.get("INGEST_MAX_GAP_MS", "240000"))), 300_000)
# a computer may replace its whole hour book (full: true) once in this many seconds unless the server asked; a send above that is merged
# hour by hour instead, so nothing is lost
# một máy được thay cả sổ giờ (full: true) một lần trong ngần này giây nếu máy chủ không yêu cầu; gửi dày hơn thì được ghép từng giờ,
# nên không mất số nào
FULL_BOOK_SECONDS = 3600
# a v: 2 send stamped up to this much older than what the server holds arrived out of order and is dropped; further back is a clock put back
# gói v: 2 có giờ cũ hơn bản máy chủ đang giữ trong khoảng này là tới sai thứ tự và bị bỏ; cũ hơn nữa là đồng hồ bị chỉnh lùi
REORDER_WINDOW_MS = 60_000
NEW_DEVICES_PER_IP = 10
# MAX_DEVICES counts computers, not people: a laptop, a desktop and a connector are three. Above the default, measure first (docs/BENCHMARK.md).
# MAX_DEVICES đếm máy, không đếm người: laptop, máy bàn và bộ nối là ba. Trên mức mặc định thì đo trước (docs/BENCHMARK.md).
MAX_DEVICES = min(max(1, int(os.environ.get("MAX_DEVICES", "300"))), 200000)
# The optional receiver written in Go (receiver/, docs/RECEIVER.md) for large organisations: RECEIVER=1 opens the paths it uses on this
# machine (/internal/...) and writes the file of secrets it reads; off, those paths are 404 and nothing is written, as for a small company.
# Bộ nhận tuỳ chọn viết bằng Go (receiver/, docs/RECEIVER.vi.md) cho tổ chức lớn: RECEIVER=1 mở các đường nó dùng trên máy này
# (/internal/...) và ghi file bí mật nó đọc; tắt thì các đường đó là 404 và không ghi gì, như với công ty nhỏ.
RECEIVER_ENABLED = os.environ.get("RECEIVER", "0").strip() == "1"
RECEIVER_SECRETS_FILE = os.environ.get("RECEIVER_SECRETS_FILE", "").strip() or os.path.join(KEYS_DIR, "receiver-secrets.json")
# the share of sends the receiver also hands over as they came, for this server to clean again and compare (the third check of docs/RECEIVER.md)
# phần trăm số lần gửi mà bộ nhận cũng chuyển nguyên văn, để máy chủ này làm sạch lại và so (lớp đối chiếu thứ ba của docs/RECEIVER.vi.md)
RECEIVER_CHECK_PERCENT = min(max(0.0, float(os.environ.get("RECEIVER_CHECK_PERCENT", "1"))), 100.0)
# how often at most the table of people the receiver asks for (/internal/people) is built again, in seconds
# bảng người bộ nhận hỏi (/internal/people) được dựng lại nhiều nhất bao lâu một lần, tính bằng giây
RECEIVER_PEOPLE_SECONDS = max(0.0, float(os.environ.get("RECEIVER_PEOPLE_SECONDS", "").strip() or "5"))
# The live feed of the board from the receiver (docs/RECEIVER.md, section 3): RECEIVER_LIVE_URL is the receiver's address as the boards
# reach it (https://ingest.example.com), RECEIVER_BOARD_ORIGIN the board's own (https://board.example.com), the only page the receiver lets
# open the feed. Both, with RECEIVER=1, open POST /sse/ticket and add the receiver to the pages' connect-src; either missing, neither happens.
# Luồng số trực tiếp của bảng từ bộ nhận (docs/RECEIVER.vi.md, mục 3): RECEIVER_LIVE_URL là địa chỉ của bộ nhận như các bảng tới được
# (https://ingest.example.com), RECEIVER_BOARD_ORIGIN là địa chỉ của chính bảng (https://board.example.com), trang duy nhất bộ nhận cho mở
# luồng. Có cả hai, cùng RECEIVER=1, thì mở POST /sse/ticket và thêm bộ nhận vào connect-src của các trang; thiếu một thì không có gì.
def _origin(v: str) -> str:
    v = v.strip().rstrip("/")
    return v if re.fullmatch(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?", v) else ""


RECEIVER_LIVE_URL = _origin(os.environ.get("RECEIVER_LIVE_URL", ""))
RECEIVER_BOARD_ORIGIN = _origin(os.environ.get("RECEIVER_BOARD_ORIGIN", ""))
# how long a ticket for the live feed lives, in seconds; the feed it opened ends with it, and the board asks for a new one
# vé của luồng số trực tiếp sống bao lâu, tính bằng giây; luồng nó mở kết thúc cùng nó, và bảng xin vé mới
TICKET_SECONDS = 300


def live_enabled() -> bool:
    """Whether the live feed is set up: the receiver is on and both addresses are given.
    Luồng số trực tiếp đã được cài chưa: bộ nhận đang bật và có đủ hai địa chỉ."""
    return RECEIVER_ENABLED and bool(RECEIVER_LIVE_URL) and bool(RECEIVER_BOARD_ORIGIN)
