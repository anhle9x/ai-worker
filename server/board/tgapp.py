"""The board's small window inside Telegram (a Telegram Mini App), for chats an admin allows one by one. Off unless TELEGRAM_APP=1.
When a person opens the window from the bot's menu button, Telegram hands the page a few signed fields (initData) after the # in its address,
so they never reach the server's logs. The page sends them once to /tg/session; this module checks Telegram's signature with the key the
installer derived from the bot token, finds the approved chat of that Telegram user, and gives the page a short-lived session that lives
in memory only. Every later call finds the chat again, so revoking it on the Admin page, or /stop in the chat, ends the window at once.
Nothing here talks to Telegram: the bot process sets the menu button, from what menu_changes() says.
  Khung nhỏ của bảng bên trong Telegram (một Telegram Mini App), cho từng chat được quản trị cho phép. Tắt trừ khi TELEGRAM_APP=1.
  Khi một người mở khung từ nút menu của bot, Telegram giao cho trang vài trường đã ký (initData) nằm sau dấu # của địa chỉ, nên chúng
  không bao giờ vào nhật ký của máy chủ. Trang gửi chúng một lần tới /tg/session; module này kiểm chữ ký của Telegram bằng khoá bộ cài
  suy ra từ khoá bot, tìm chat đã được duyệt của người dùng Telegram đó, và cấp cho trang một phiên ngắn hạn chỉ nằm trong bộ nhớ.
  Mỗi lần gọi sau đó lại tìm chat, nên thu hồi chat ở trang Quản trị, hoặc gõ /stop trong chat, là khung hết dùng được ngay.
  Ở đây không có gì nói chuyện với Telegram: tiến trình bot đặt nút menu, theo những gì menu_changes() cho biết."""

import hashlib
import hmac
import json
import re
import secrets
import threading
from typing import Optional
from urllib.parse import parse_qsl

from board import settings
from board.security import CallLimit
from board.settings import KIND_TELEGRAM
from board.stores import TV, chat_key
from board.summary import SCOPE_PEOPLE

# what Telegram signs is accepted for this long after the window opened (auth_date), and up to a minute ahead for a fast clock
# phần Telegram ký được nhận trong ngần này sau lúc khung mở (auth_date), và sớm tối đa một phút cho đồng hồ chạy nhanh
INIT_DATA_SECONDS = 300
INIT_DATA_MAX_BYTES = 4096
# a session lives an hour after its last use, 12 hours at most, and a chat holds at most 3 (a phone, a computer, one more)
# một phiên sống một giờ sau lần dùng cuối, tối đa 12 giờ, và mỗi chat giữ tối đa 3 phiên (điện thoại, máy tính, thêm một)
SESSION_IDLE_SECONDS = 3600
SESSION_MAX_SECONDS = 12 * 3600
SESSIONS_PER_CHAT = 3
# /tg/session per IP and per chat; /tg/data per session (the window asks every 30 seconds, which is 20 in 10 minutes)
# /tg/session theo IP và theo chat; /tg/data theo phiên (khung hỏi mỗi 30 giây, tức 20 lần trong 10 phút)
SESSION_LIMIT_IP = CallLimit(10, 60)
SESSION_LIMIT_CHAT = CallLimit(20, 600)
DATA_LIMIT = CallLimit(60, 600)
SESSION_PREFIX = "tgs_"
# the text on the menu button: a name, the same in every language
# chữ trên nút menu: một cái tên, như nhau ở mọi ngôn ngữ
MENU_TEXT = "AI Worker"


def check_init_data(raw, key_hex: str, now: float) -> Optional[str]:
    """The Telegram user's number from the fields Telegram handed the window, or None when they are not Telegram's, are too old,
    or are not what a window gets. Telegram's rule: HMAC-SHA256 over the fields except hash, sorted by name as key=value lines,
    keyed by HMAC-SHA256("WebAppData", bot token), which is key_hex.
    Số của người dùng Telegram lấy từ các trường Telegram giao cho khung, hoặc None khi chúng không phải của Telegram, quá cũ,
    hay không phải thứ một khung nhận được. Quy tắc của Telegram: HMAC-SHA256 trên các trường trừ hash, xếp theo tên, mỗi dòng key=value,
    khoá là HMAC-SHA256("WebAppData", khoá bot), chính là key_hex."""
    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > INIT_DATA_MAX_BYTES or not re.fullmatch(r"[0-9a-f]{64}", key_hex or ""):
        return None
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    fields = {}
    for k, v in pairs:
        if k in fields or not re.fullmatch(r"[a-z_]{1,32}", k) or len(fields) >= 20:
            return None
        fields[k] = v
    given = fields.get("hash", "")
    if not re.fullmatch(r"[0-9a-f]{64}", given) or not re.fullmatch(r"[0-9]{1,12}", fields.get("auth_date", "")):
        return None
    signed_at = int(fields["auth_date"])
    if not (now - INIT_DATA_SECONDS <= signed_at <= now + 60):
        return None
    data = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields) if k != "hash")
    good = hmac.new(bytes.fromhex(key_hex), data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, given):
        return None
    try:
        user = json.loads(fields.get("user", ""))
    except ValueError:
        return None
    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(user_id, int) or isinstance(user_id, bool) or not 0 < user_id < 10 ** 20:
        return None
    return str(user_id)


def app_key_from_token(token: str) -> str:
    """The key the installer writes as TELEGRAM_APP_KEY; here for the tests and for anyone checking the installer's work.
    Khoá bộ cài ghi thành TELEGRAM_APP_KEY; để ở đây cho bài test và cho ai muốn kiểm việc của bộ cài."""
    return hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).hexdigest()


def allowed_chat(telegram_id: str, now: float) -> Optional[dict]:
    """The approved chat of this Telegram user, if an admin let it open the window. Only a chat that reads each person may for now:
    the window draws each person's numbers, and a chat that reads totals only would see more than it was approved for.
    Chat đã được duyệt của người dùng Telegram này, nếu quản trị cho nó mở khung. Hiện chỉ chat được đọc từng người mới được:
    khung vẽ số của từng người, và chat chỉ được đọc tổng sẽ thấy nhiều hơn phần được duyệt."""
    chat = TV.find(chat_key(telegram_id), now, KIND_TELEGRAM)
    return chat if chat and chat.get("app") is True and chat.get("scope") == SCOPE_PEOPLE else None


class AppSessions:
    """Sessions of the window, in memory only: a restart of the server ends them, and the window asks Telegram's fields again.
    Only a hash of each session is kept, with the Telegram user it belongs to.
    Phiên của khung, chỉ trong bộ nhớ: khởi động lại máy chủ là hết, và khung lại xin các trường của Telegram.
    Chỉ giữ băm của mỗi phiên, cùng người dùng Telegram sở hữu nó."""

    def __init__(self):
        self.lock = threading.Lock()
        # sha256 of the session -> {"tg": Telegram user's number, "at": created, "last": last used}
        # sha256 của phiên -> {"tg": số người dùng Telegram, "at": lúc tạo, "last": lần dùng cuối}
        self.rows = {}

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _live(self, now: float) -> None:
        self.rows = {h: r for h, r in self.rows.items() if now - r["last"] < SESSION_IDLE_SECONDS and now - r["at"] < SESSION_MAX_SECONDS}

    def issue(self, telegram_id: str, now: float) -> str:
        token = SESSION_PREFIX + secrets.token_urlsafe(32)
        with self.lock:
            self._live(now)
            mine = sorted((r["at"], h) for h, r in self.rows.items() if r["tg"] == telegram_id)
            for _, h in mine[:max(0, len(mine) - SESSIONS_PER_CHAT + 1)]:
                del self.rows[h]
            self.rows[self._hash(token)] = {"tg": telegram_id, "at": now, "last": now}
        return token

    def owner(self, token: str, now: float) -> str:
        """The Telegram user's number of a live session, renewed by this use; "" when there is none.
        Số người dùng Telegram của một phiên còn sống, gia hạn nhờ lần dùng này; "" khi không có."""
        if not isinstance(token, str) or not token.startswith(SESSION_PREFIX) or len(token) > 100:
            return ""
        h = self._hash(token)
        with self.lock:
            self._live(now)
            r = self.rows.get(h)
            if not r:
                return ""
            r["last"] = now
            return r["tg"]

    def end_chat(self, telegram_id: str) -> None:
        with self.lock:
            self.rows = {h: r for h, r in self.rows.items() if r["tg"] != telegram_id}


SESSIONS = AppSessions()


class MenuSync:
    """Which chats should show the window on the bot's menu button, and what the bot process was last told to set. In memory: after a
    restart every live chat is told again, so a chat that lost the window while the server was down gets its plain menu back.
    Chat nào cần có khung trên nút menu của bot, và lần gần nhất tiến trình bot được bảo đặt gì. Trong bộ nhớ: sau khi khởi động lại,
    mọi chat còn hạn đều được báo lại, nên chat bị bỏ khung lúc máy chủ tắt cũng được trả lại nút menu thường."""

    def __init__(self):
        self.lock = threading.Lock()
        # Telegram user's number -> the address its menu button opens, "" for the plain menu; None until the first round
        # số người dùng Telegram -> địa chỉ nút menu của nó mở, "" cho menu thường; None cho tới vòng đầu tiên
        self.told = None

    def changes(self, now: float) -> list:
        """[{"to": number, "url": address or None}] for the bot process to set now; empty when nothing changed.
        [{"to": số, "url": địa chỉ hoặc None}] để tiến trình bot đặt ngay; rỗng khi không có gì đổi."""
        want = {}
        for row in TV.d.values():
            if row.get("kind") != KIND_TELEGRAM or row["expiresAt"] <= now or not re.fullmatch(r"[0-9]{1,20}", str(row.get("telegramId", ""))):
                continue
            on = settings.TELEGRAM_APP_ENABLED and row.get("app") is True and row.get("scope") == SCOPE_PEOPLE
            want[row["telegramId"]] = settings.TELEGRAM_APP_URL if on else ""
        with self.lock:
            told = self.told if self.told is not None else {}
            first = self.told is None
            out = [{"to": int(tg), "url": url or None} for tg, url in sorted(want.items()) if first or told.get(tg) != url]
            # a chat that was revoked since the last round goes back to the plain menu, once
            # chat bị thu hồi từ vòng trước được trả về menu thường, một lần
            out += [{"to": int(tg), "url": None} for tg, url in sorted(told.items()) if tg not in want and url]
            self.told = want
        return out


MENUS = MenuSync()
