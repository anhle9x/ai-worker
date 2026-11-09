"""Account roles, OTP codes and the bot blocker.
Vai tài khoản, mã OTP và bộ chặn bot."""

import base64
import hashlib
import hmac
import ipaddress
import re
import struct
import sys
import threading

from board.settings import SESSION_SECONDS, WALL_SESSION_SECONDS


def parse_otp(text: str) -> dict:
    out = {}
    for fields in text.split(","):
        name, _, secret = fields.strip().partition(":")
        secret = secret.strip().replace(" ", "").upper()
        if name and secret:
            out[name.strip()] = base64.b32decode(secret + "=" * (-len(secret) % 8))
    return out


def parse_names(text: str) -> set:
    return {t.strip() for t in text.split(",") if t.strip()}


ADMIN, VIEWER, WALL = "admin", "viewer", "wall"
ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,30}$")


def session_lifetime(role: str) -> int:
    return WALL_SESSION_SECONDS if role == WALL else SESSION_SECONDS


def totp_code(secret: bytes, step: int) -> str:
    """6-digit TOTP code (RFC 6238, SHA-1, 30 seconds) like Google/Microsoft Authenticator.
    Mã TOTP 6 số (RFC 6238, SHA-1, 30 giây) như Google/Microsoft Authenticator."""
    h = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


# guard against scraping bots: only requests that are not logged in count; logged-in people and devices sending data (/ingest) are not affected.
# The whole office may share one IP, so the limits are wide: a person opening the login page never reaches them
# chặn bot cào: chỉ tính yêu cầu chưa đăng nhập; người đã đăng nhập và máy gửi số liệu (/ingest) không bị ảnh hưởng.
# Cả văn phòng có thể chung một IP nên ngưỡng để rộng: một người mở trang đăng nhập không bao giờ chạm tới
# requests that are not logged in, per minute
# yêu cầu chưa đăng nhập mỗi phút
BOT_PER_MINUTE = 60
# times of 401/404 in 10 minutes (probing paths)
# lần gặp 401/404 trong 10 phút (dò đường dẫn)
BOT_ERRORS_PER_10_MIN = 20
BOT_BLOCK_SECONDS = 15 * 60


class BotBlocker:
    def __init__(self):
        self.lock = threading.Lock()
        # ip -> [times of requests]
        # ip -> [thời điểm yêu cầu]
        self.seen = {}
        # ip -> [times of 401/404]
        # ip -> [thời điểm gặp 401/404]
        self.error = {}
        # ip -> blocked until
        # ip -> hết chặn lúc
        self.blocked_until = {}

    def is_blocked(self, ip: str, now: float) -> bool:
        """Record one request that is not logged in; True if this IP is blocked or has just gone over the limit.
        Ghi một yêu cầu chưa đăng nhập; True nếu IP này đang bị chặn hoặc vừa vượt ngưỡng."""
        with self.lock:
            if self.blocked_until.get(ip, 0) > now:
                return True
            self.blocked_until.pop(ip, None)
            if len(self.blocked_until) > 1000:
                self.blocked_until = {k: v for k, v in self.blocked_until.items() if v > now}
            attempts = [t for t in self.seen.get(ip, []) if t > now - 60]
            attempts.append(now)
            self.seen[ip] = attempts
            if len(self.seen) > 1000:
                self.seen = {k: v for k, v in self.seen.items() if v[-1] > now - 60}
            if len(attempts) > BOT_PER_MINUTE:
                self.blocked_until[ip] = now + BOT_BLOCK_SECONDS
                sys.stderr.write("blocked bot %s: over %d requests per minute\n" % (ip, BOT_PER_MINUTE))
                return True
            return False

    def record_error(self, ip: str, now: float) -> None:
        with self.lock:
            attempts = [t for t in self.error.get(ip, []) if t > now - 600]
            attempts.append(now)
            self.error[ip] = attempts
            if len(self.error) > 1000:
                self.error = {k: v for k, v in self.error.items() if v[-1] > now - 600}
            if len(attempts) >= BOT_ERRORS_PER_10_MIN:
                self.blocked_until[ip] = now + BOT_BLOCK_SECONDS
                sys.stderr.write("blocked bot %s: probing paths\n" % ip)


BOT = BotBlocker()


BLOCKED = "\0blocked"


def ip_bucket(ip: str) -> str:
    """One IPv6 customer usually holds a whole /64, so those addresses count as one.
    Một khách IPv6 thường giữ cả dải /64, nên các địa chỉ đó tính là một."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    return str(ipaddress.ip_network((parsed, 64), strict=False)) if parsed.version == 6 else ip


def account_key(name_input: str) -> str:
    return (name_input or "").strip().lower()[:60]
