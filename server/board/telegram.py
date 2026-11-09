"""Log in with Telegram, through Telegram's login widget: check what Telegram signed, and keep the one-time links that wait for a code.
The server never calls Telegram: the visitor's browser talks to Telegram, and the server only checks the signature with the bot token.
Đăng nhập bằng Telegram, qua nút đăng nhập của Telegram: kiểm phần Telegram đã ký, và giữ các lần liên kết dùng một lần đang chờ mã. Máy chủ không bao giờ gọi Telegram: trình duyệt của người xem nói chuyện với Telegram, máy chủ chỉ kiểm chữ ký bằng khoá của bot."""

import hashlib
import hmac
import re
import secrets
import threading
from typing import Optional

from board import settings

# a signed login is accepted for 5 minutes, and only once
# một lần đăng nhập đã ký chỉ nhận trong 5 phút, và chỉ một lần
MAX_AGE_SECONDS = 300
# a link started with the 6-digit code must be finished within 5 minutes
# lần liên kết bắt đầu bằng mã 6 số phải xong trong 5 phút
LINK_SECONDS = 300
BOT_NAME_RE = re.compile(r"[A-Za-z0-9_]{5,32}")
# our own parameter on the link address; Telegram does not sign it
# tham số riêng của mình trên địa chỉ liên kết; Telegram không ký nó
OWN_PARAMS = ("n",)


def enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN) and BOT_NAME_RE.fullmatch(settings.TELEGRAM_BOT_NAME or "") is not None


def bot_name() -> str:
    return settings.TELEGRAM_BOT_NAME if enabled() else ""


def bot_id() -> str:
    """The bot's number, the part of the token before the colon; Telegram's login page needs it.
    Số của bot, phần của khoá trước dấu hai chấm; trang đăng nhập của Telegram cần số này."""
    head = settings.TELEGRAM_BOT_TOKEN.split(":", 1)[0]
    return head if enabled() and re.fullmatch(r"[0-9]{1,20}", head) else ""


def check_signature(fields: dict, token: str) -> bool:
    """Telegram's rule: HMAC-SHA256 over the fields sorted by name as key=value lines, keyed by SHA256 of the bot token.
    Quy tắc của Telegram: HMAC-SHA256 trên các trường xếp theo tên, mỗi dòng key=value, khoá là SHA256 của khoá bot."""
    given = fields.get("hash", "")
    data = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields) if k != "hash")
    good = hmac.new(hashlib.sha256(token.encode()).digest(), data.encode(), hashlib.sha256).hexdigest()
    return bool(given) and hmac.compare_digest(good, given)


class TelegramGate:
    def __init__(self):
        self.lock = threading.Lock()
        # hash -> time it can be forgotten, so the same signed login cannot be used twice
        # hash -> lúc có thể quên, để cùng một lần đăng nhập đã ký không dùng được hai lần
        self.used = {}
        # session token -> (one-time link code, expiry)
        # mã phiên -> (mã liên kết dùng một lần, hết hạn)
        self.pending = {}

    def verify(self, query: dict, now: float) -> Optional[dict]:
        """The Telegram user from the widget's address parameters (as parse_qs gives them), or None. Uses the signature up.
        Người dùng Telegram từ các tham số địa chỉ của nút (dạng parse_qs trả về), hoặc None. Dùng xong thì chữ ký hết hiệu lực."""
        if not enabled():
            return None
        fields = {}
        for k, v in query.items():
            if k in OWN_PARAMS:
                continue
            if not re.fullmatch(r"[a-z_]{1,20}", k) or len(v) != 1 or len(v[0]) > 512 or len(fields) >= 12:
                return None
            fields[k] = v[0]
        if not re.fullmatch(r"[0-9]{1,20}", fields.get("id", "")) or not re.fullmatch(r"[0-9]{1,12}", fields.get("auth_date", "")):
            return None
        if not re.fullmatch(r"[0-9a-f]{64}", fields.get("hash", "")):
            return None
        signed_at = int(fields["auth_date"])
        if not (now - MAX_AGE_SECONDS <= signed_at <= now + 60):
            return None
        if not check_signature(fields, settings.TELEGRAM_BOT_TOKEN):
            return None
        with self.lock:
            self.used = {h: t for h, t in self.used.items() if t > now}
            if fields["hash"] in self.used:
                return None
            self.used[fields["hash"]] = signed_at + MAX_AGE_SECONDS + 120
        username = fields.get("username", "")
        return {"id": fields["id"], "username": username if re.fullmatch(r"[A-Za-z0-9_]{1,32}", username) else ""}

    def start_link(self, session_token: str, now: float) -> str:
        code = secrets.token_urlsafe(18)
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v[1] > now}
            self.pending[session_token] = (code, now + LINK_SECONDS)
        return code

    def take_link(self, session_token: str, code: str, now: float) -> bool:
        """True once for the code given to this session; the code is gone afterwards either way.
        True một lần cho mã đã giao cho phiên này; sau đó mã mất dù đúng hay sai."""
        with self.lock:
            p = self.pending.pop(session_token, None)
        return bool(p and code and p[1] > now and hmac.compare_digest(p[0], code))


TELEGRAM = TelegramGate()
