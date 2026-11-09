"""Login with account and OTP, and the sessions it opens.
Đăng nhập bằng tài khoản và OTP, và các phiên mở ra từ đó."""

import hmac
import re
import secrets
import threading

from board.security import (
    BLOCKED,
    WALL,
    account_key,
    ip_bucket,
    session_lifetime,
    totp_code,
)
from board.settings import (
    CONFIRM_MAX_FAILS,
    CONFIRM_SECONDS,
    FAIL_WINDOW_SECONDS,
    MAX_FAILS,
    MAX_FAILS_PER_ACCOUNT,
)
from board.stores import ACCOUNTS, TV


class LoginGate:
    """Login with OTP: sessions are kept in memory (restarting the webhook means logging in again), and guessing codes is blocked.
    Đăng nhập bằng OTP: phiên giữ trong bộ nhớ (khởi động lại webhook là đăng nhập lại), chặn đoán mã."""

    def __init__(self):
        self.lock = threading.Lock()
        # session id -> (name, expiry); the role is looked up each time, so a role change takes effect at once
        # mã phiên -> (tên, hết hạn); vai tra mỗi lần, đổi vai có hiệu lực ngay
        self.sessions = {}
        # session id -> time of the latest OTP re-entry
        # mã phiên -> lúc nhập lại OTP gần nhất
        self.confirmed_at = {}
        # session id -> number of wrong re-entries
        # mã phiên -> số lần nhập lại sai
        self.confirm_fails = {}
        # ip -> [times of wrong entries]
        # ip -> [các lần nhập sai]
        self.fails = {}
        # account name as typed -> [times of wrong entries]; a name that does not exist counts too, so it looks the same
        # tên tài khoản như đã gõ -> [các lần nhập sai]; tên không tồn tại cũng tính, để không phân biệt được
        self.account_fails = {}
        # name -> latest step used, so a code cannot be used twice
        # tên -> bước đã dùng gần nhất, không cho dùng lại một mã
        self.used_step = {}

    def _recent(self, table: dict, key: str, now: float) -> list:
        attempts = [t for t in table.get(key, []) if now - t < FAIL_WINDOW_SECONDS]
        if attempts:
            table[key] = attempts
        else:
            table.pop(key, None)
        return attempts

    def is_blocked(self, ip: str, now: float, name_input: str = "") -> bool:
        with self.lock:
            return self._is_blocked(ip_bucket(ip), account_key(name_input), now)

    def _is_blocked(self, ip_key: str, name_key: str, now: float) -> bool:
        return len(self._recent(self.fails, ip_key, now)) >= MAX_FAILS or len(self._recent(self.account_fails, name_key, now)) >= MAX_FAILS_PER_ACCOUNT

    def login(self, name_input: str, code: str, ip: str, now: float):
        """A name is required: each guess can test only one account, not all keys at once.
        Phải có tên: mỗi lần đoán chỉ thử được một tài khoản, không thử cùng lúc mọi khoá."""
        if not re.fullmatch(r"[0-9]{6}", code or ""):
            code = "x"
        step = int(now // 30)
        name_input = (name_input or "").strip().lower()
        ip_key, name_key = ip_bucket(ip), account_key(name_input)
        # Checking the limit and counting the attempt under one lock: held connections released together cannot slip past it.
        # Kiểm giới hạn và đếm lần thử trong cùng một khoá: các kết nối giữ lại rồi thả cùng lúc không lọt qua được.
        with self.lock:
            if self._is_blocked(ip_key, name_key, now):
                return BLOCKED, None
            for name, secret in ACCOUNTS.secrets_by_name().items():
                if name.lower() != name_input:
                    continue
                for b in (step - 1, step, step + 1):
                    if b > self.used_step.get(name, -1) and hmac.compare_digest(totp_code(secret, b), code):
                        self.used_step[name] = b
                        token = secrets.token_urlsafe(32)
                        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
                        self.sessions[token] = (name, now + session_lifetime(ACCOUNTS.role_of(name)))
                        return name, token
            self.fails.setdefault(ip_key, []).append(now)
            self.account_fails.setdefault(name_key, []).append(now)
            # drop old entries so the tables do not grow when probed from many places
            # bỏ mục cũ để các bảng không phình ra khi bị dò từ nhiều nơi
            if len(self.fails) > 1000:
                self.fails = {k: v for k, v in self.fails.items() if v and now - v[-1] < FAIL_WINDOW_SECONDS}
            if len(self.account_fails) > 1000:
                self.account_fails = {k: v for k, v in self.account_fails.items() if v and now - v[-1] < FAIL_WINDOW_SECONDS}
        return None, None

    def check_otp(self, name_input: str, code: str, ip: str, now: float):
        """Same checks and limits as logging in, but no session is kept: used to approve one's own menu bar computer.
        Cùng các bước kiểm và giới hạn như đăng nhập, nhưng không giữ phiên: dùng để tự duyệt máy thanh menu của mình."""
        name, token = self.login(name_input, code, ip, now)
        if token:
            with self.lock:
                self._drop(token)
        return name

    def user_of(self, cookie: str, now: float):
        return self.user_and_role(cookie, now)[0]

    @staticmethod
    def token_of(cookie: str) -> str:
        for part in (cookie or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "session":
                return v
        return ""

    def user_and_role(self, cookie: str, now: float):
        token = self.token_of(cookie)
        # a TV screen's session is always the wall role; it is on disk, so it survives a restart
        # phiên của màn hình TV luôn là vai treo tường, nằm trên đĩa nên không mất khi khởi động lại
        if token.startswith("tv_"):
            tv = TV.find(token, now)
            if tv:
                return "tv:" + tv["name"], WALL
        with self.lock:
            p = self.sessions.get(token)
            role = ACCOUNTS.role_of(p[0]) if p and p[1] > now else None
            return (p[0], role) if role else (None, None)

    def _drop(self, token: str) -> None:
        self.sessions.pop(token, None)
        self.confirmed_at.pop(token, None)
        self.confirm_fails.pop(token, None)

    def logout(self, cookie: str) -> None:
        with self.lock:
            self._drop(self.token_of(cookie))

    def is_confirmed(self, cookie: str, now: float) -> bool:
        with self.lock:
            return now - self.confirmed_at.get(self.token_of(cookie), 0) < CONFIRM_SECONDS

    def confirm(self, cookie: str, code: str, ip: str, now: float) -> str:
        """Re-enter the OTP of the person who is logged in. Returns "ok", "wrong", or "cancelled" when there are too many wrong tries and the session is dropped.
        Nhập lại OTP của chính người đang đăng nhập. Trả "ok", "wrong", hoặc "cancelled" khi sai quá nhiều và phiên bị bỏ."""
        if not re.fullmatch(r"[0-9]{6}", code or ""):
            code = "x"
        token = self.token_of(cookie)
        step = int(now // 30)
        with self.lock:
            p = self.sessions.get(token)
            secret = ACCOUNTS.secrets_by_name().get(p[0]) if p else None
            if secret:
                for b in (step - 1, step, step + 1):
                    if b > self.used_step.get(p[0], -1) and hmac.compare_digest(totp_code(secret, b), code):
                        self.used_step[p[0]] = b
                        self.confirmed_at[token] = now
                        self.confirm_fails.pop(token, None)
                        return "ok"
            self.fails.setdefault(ip_bucket(ip), []).append(now)
            self.confirm_fails[token] = self.confirm_fails.get(token, 0) + 1
            if self.confirm_fails[token] >= CONFIRM_MAX_FAILS:
                self._drop(token)
                return "cancelled"
            return "wrong"

    def end_sessions_of(self, name: str, except_token: str = "") -> int:
        """Drop every session of a name, except the session `except_token`.
        Bỏ mọi phiên của một tên, trừ phiên `except_token`."""
        with self.lock:
            tokens = [t for t, p in self.sessions.items() if p[0] == name and t != except_token]
            for t in tokens:
                self._drop(t)
            return len(tokens)

    def list_sessions(self, cookie: str, now: float) -> list:
        token = self.token_of(cookie)
        with self.lock:
            return [{"name": p[0], "role": ACCOUNTS.role_of(p[0]), "expiresAt": int(p[1] * 1000), "mine": t == token}
                    for t, p in self.sessions.items() if p[1] > now]


SESSIONS = LoginGate()
