"""Files the server keeps: accounts, TV and menu bar pairings, locations, team plan, audit log.
Các file máy chủ lưu: tài khoản, ghép TV và thanh menu, địa điểm, gói Team, nhật ký quản trị."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime

from board.db import account_row, data_db, dumps, keys_db, revoked_row, screen_row
from board.lang import tx
# what an MCP key may read: each person's row, or totals only. A key with neither word reads totals only
# khoá MCP được đọc gì: dòng của từng người, hoặc chỉ số gộp. Khoá không có chữ nào trong hai chữ này thì chỉ đọc số gộp
from board.mcp import SCOPE_PEOPLE as MCP_SCOPE_PEOPLE
from board.mcp import SCOPE_TOTALS as MCP_SCOPE_TOTALS
from board.security import ADMIN, VIEWER, WALL, parse_names, parse_otp
from board.settings import (
    KIND_MCP,
    KIND_PROJECT,
    KIND_TELEGRAM,
    LOCAL_TZ,
    MAX_ACCOUNTS,
    MCP_CALL_KEEP_MONTHS,
    MCP_KEYS_MAX,
    MENUBAR_PER_ACCOUNT,
    MINI_HANDOFF_MAX,
    MINI_HANDOFF_PER_TOKEN,
    MINI_HANDOFF_SECONDS,
    PROJECT_KEYS_MAX,
    TELEGRAM_CHATS_MAX,
    TELEGRAM_PENDING_MAX,
    TV_APPROVE_SECONDS,
    TV_CEILING_SECONDS,
    TV_CODE_SECONDS,
    TV_MAX,
    TV_PENDING_PER_IP,
    TV_PENDING_TOTAL,
    TV_RENEW_WHEN_LEFT,
    TV_REVOKED_KEEP_SECONDS,
    TV_REVOKED_LOG_SECONDS,
    TV_REVOKED_MAX,
    TV_SESSION_SECONDS,
    TV_VIEW_FAIL_SECONDS,
    TV_VIEW_MAX_FAILS,
)


class Store:
    """A table of the database kept as a dict in memory: read() gives the dict, mutate(edit) changes a copy and writes
    only the changed rows in one transaction; raising ValueError in edit writes nothing.
    Một bảng của cơ sở dữ liệu giữ dạng dict trong bộ nhớ: read() trả dict, mutate(edit) sửa bản sao rồi chỉ ghi
    các dòng đã đổi trong một giao dịch; edit ném ValueError thì không ghi gì."""

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()
        self.d = self.load()

    def load(self) -> dict:
        raise NotImplementedError

    def save(self, c, old: dict, new: dict) -> None:
        raise NotImplementedError

    def read(self) -> dict:
        return self.d

    def mutate(self, edit):
        with self.lock:
            copy = json.loads(json.dumps(self.d))
            out = edit(copy)
            with self.db.tx() as c:
                self.save(c, self.d, copy)
            self.d = copy
            return out


def save_keyed(c, table: str, key: str, row, old: dict, new: dict) -> None:
    """Write the rows of `new` that are missing or changed, delete the rows no longer in `new`.
    Ghi các dòng của `new` còn thiếu hoặc đã đổi, xoá các dòng không còn trong `new`."""
    there = {r[0] for r in c.execute("SELECT %s FROM %s" % (key, table))}
    for k in there - set(new):
        c.execute("DELETE FROM %s WHERE %s = ?" % (table, key), (k,))
    for k, v in new.items():
        if k not in there or old.get(k) != v:
            r = row(k, v)
            c.execute("INSERT OR REPLACE INTO %s VALUES (%s)" % (table, ", ".join("?" * len(r))), r)


class DocumentStore(Store):
    """One JSON document in the documents table, changed as a whole (locations, Team plan).
    Một tài liệu JSON trong bảng documents, sửa nguyên khối (địa điểm, gói Team)."""

    def __init__(self, database, name: str):
        self.name = name
        super().__init__(database)

    def load(self) -> dict:
        r = self.db.rows("SELECT body FROM documents WHERE name = ?", (self.name,))
        try:
            d = json.loads(r[0][0]) if r else {}
        except ValueError:
            d = {}
        return d if isinstance(d, dict) else {}

    def save(self, c, old: dict, new: dict) -> None:
        c.execute("INSERT OR REPLACE INTO documents VALUES (?, ?, ?)", (self.name, dumps(new), int(time.time() * 1000)))


def load_bodies(database, sql: str) -> dict:
    out = {}
    for k, body in database.rows(sql):
        try:
            v = json.loads(body)
        except ValueError:
            continue
        if isinstance(v, dict):
            out[k] = v
    return out


class Accounts(Store):
    """Login accounts: {accounts: {name: {role, secret (base32), createdAt, createdBy, lastLoginAt}}, imported: [names imported from env]}.
    They are in KEYS_DIR (accounts.db), outside the data folder, so data backups do not contain keys.
    Tài khoản đăng nhập: {accounts: {tên: {role, secret (base32), createdAt, createdBy, lastLoginAt}}, imported: [tên đã nhập từ env]}.
    Nằm ở KEYS_DIR (accounts.db), ngoài thư mục dữ liệu, để bản sao lưu số liệu không chứa khoá."""

    def load(self) -> dict:
        return {"accounts": load_bodies(self.db, "SELECT name, body FROM accounts"),
                "imported": [r[0] for r in self.db.rows("SELECT name FROM imported ORDER BY rowid")]}

    def save(self, c, old: dict, new: dict) -> None:
        save_keyed(c, "accounts", "name", account_row, old.get("accounts", {}), new.get("accounts", {}))
        imported = set(new.get("imported", []))
        there = {r[0] for r in c.execute("SELECT name FROM imported")}
        for k in there - imported:
            c.execute("DELETE FROM imported WHERE name = ?", (k,))
        for k in new.get("imported", []):
            if k not in there:
                c.execute("INSERT INTO imported VALUES (?)", (k,))

    def import_from_env(self) -> int:
        """A name in env that is not imported yet gets imported; an imported one is skipped, so an account deleted on the web does not come back.
        Tên có trong env mà chưa nhập thì nhập; đã nhập thì bỏ qua, nên tài khoản xoá trên web không sống lại."""
        otp = parse_otp(os.environ.get("OTP", ""))
        admins, wall_names = parse_names(os.environ.get("OTP_ADMINS", "")), parse_names(os.environ.get("OTP_WALL", ""))

        def change(d):
            accounts, imported = d.setdefault("accounts", {}), d.setdefault("imported", [])
            new_names = [t for t in otp if t not in imported]
            for t in new_names:
                accounts[t] = {"role": ADMIN if t in admins else WALL if t in wall_names else VIEWER, "secret": base64.b32encode(otp[t]).decode(),
                         "createdAt": int(time.time() * 1000), "createdBy": "install"}
                imported.append(t)
            return len(new_names)
        return self.mutate(change) if any(t not in self.d.get("imported", []) for t in otp) else 0

    def role_of(self, name: str):
        return self.d.get("accounts", {}).get(name, {}).get("role")

    def secrets_by_name(self) -> dict:
        return {t: base64.b32decode(m["secret"]) for t, m in self.d.get("accounts", {}).items()}

    def list_accounts(self) -> list:
        """Never includes the key.
        Không bao giờ có khoá."""
        return sorted(({"name": t, "role": m["role"], "createdAt": m.get("createdAt"), "createdBy": m.get("createdBy"), "lastLoginAt": m.get("lastLoginAt"),
                        "telegram": telegram_label(m)}
                       for t, m in self.d.get("accounts", {}).items()), key=lambda x: x["name"].lower())

    @staticmethod
    def _new_secret() -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode()

    @staticmethod
    def _ensure_admin_left(accounts: dict) -> None:
        if not any(m["role"] == ADMIN for m in accounts.values()):
            raise ValueError(tx("At least one admin must remain"))

    def create(self, name: str, role: str, created_by: str) -> str:
        secret = self._new_secret()

        def change(d):
            accounts = d.setdefault("accounts", {})
            if name in accounts:
                raise ValueError(tx("This name is already taken"))
            if len(accounts) >= MAX_ACCOUNTS:
                raise ValueError(tx("Account limit reached"))
            accounts[name] = {"role": role, "secret": secret, "createdAt": int(time.time() * 1000), "createdBy": created_by}
            if name not in d.setdefault("imported", []):
                d["imported"].append(name)
        self.mutate(change)
        return secret

    def reissue(self, name: str) -> str:
        secret = self._new_secret()

        def change(d):
            if name not in d.get("accounts", {}):
                raise ValueError(tx("This account no longer exists"))
            d["accounts"][name]["secret"] = secret
        self.mutate(change)
        return secret

    def change_role(self, name: str, role: str) -> str:
        def change(d):
            if name not in d.get("accounts", {}):
                raise ValueError(tx("This account no longer exists"))
            old_role = d["accounts"][name]["role"]
            d["accounts"][name]["role"] = role
            self._ensure_admin_left(d["accounts"])
            return old_role
        return self.mutate(change)

    def delete(self, name: str) -> None:
        def change(d):
            if name not in d.get("accounts", {}):
                raise ValueError(tx("This account no longer exists"))
            del d["accounts"][name]
            self._ensure_admin_left(d["accounts"])
        self.mutate(change)

    def find_by_telegram(self, telegram_id: str):
        """The account linked to this Telegram user, or None.
        Tài khoản đã liên kết với người dùng Telegram này, hoặc None."""
        for t, m in self.d.get("accounts", {}).items():
            if telegram_id and m.get("telegramId") == telegram_id:
                return t
        return None

    def telegram_of(self, name: str) -> str:
        """What to show for the linked Telegram of an account: @username, "linked", or "" when not linked.
        Chữ hiện cho Telegram đã liên kết của một tài khoản: @tên, "linked", hoặc "" khi chưa liên kết."""
        return telegram_label(self.d.get("accounts", {}).get(name, {}))

    def link_telegram(self, name: str, telegram_id: str, username: str) -> None:
        def change(d):
            accounts = d.get("accounts", {})
            if name not in accounts:
                raise ValueError(tx("This account no longer exists"))
            if accounts[name].get("role") == WALL:
                raise ValueError(tx("A wall display account cannot log in with Telegram"))
            for t, m in accounts.items():
                if t != name and m.get("telegramId") == telegram_id:
                    raise ValueError(tx("This Telegram account is already linked to another account"))
            accounts[name]["telegramId"] = telegram_id
            accounts[name]["telegramUser"] = username
        self.mutate(change)

    def unlink_telegram(self, name: str) -> bool:
        def change(d):
            m = d.get("accounts", {}).get(name)
            if not m or "telegramId" not in m:
                return False
            m.pop("telegramId", None)
            m.pop("telegramUser", None)
            return True
        return self.mutate(change)

    def mark_logged_in(self, name: str) -> None:
        def change(d):
            if name in d.get("accounts", {}):
                d["accounts"][name]["lastLoginAt"] = int(time.time() * 1000)
        self.mutate(change)


def telegram_label(m: dict) -> str:
    if not m.get("telegramId"):
        return ""
    return "@" + m["telegramUser"] if m.get("telegramUser") else "linked"


ACCOUNTS = Accounts(keys_db())


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def clean_tv_name(text) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).strip()[:40]
    if not name:
        raise ValueError(tx("Give the screen a name"))
    return name


def is_menubar_client(ua: str) -> bool:
    """A menu bar client names itself in its User-Agent (SwiftBar/Argos script, Ubuntu indicator, macOS app, Windows tray).
    A TV's or a manager's browser cannot be made to send this, so a wall screen's code never passes as a menu bar's.
    Ứng dụng thanh menu tự xưng tên trong User-Agent (script SwiftBar/Argos, biểu tượng Ubuntu, app macOS, khay Windows).
    Trình duyệt của TV hay của quản lý không bị ép gửi được chữ này, nên mã của màn hình treo tường không giả làm mã thanh menu được."""
    # the macOS app built in Vietnamese names itself "thanh menu" instead of "menu bar"
    # app macOS dựng bằng tiếng Việt tự xưng "thanh menu" thay cho "menu bar"
    return bool(re.search(r"menu ?bar|thanh ?menu", ua or "", re.I))


def is_plugin_client(ua: str) -> bool:
    """The Claude plugin names itself in its User-Agent when it asks to pair. Used only to name the pairing in /admin: it gives no extra right.
    Plugin Claude tự xưng tên trong User-Agent khi xin ghép. Chỉ dùng để gọi tên lần ghép trong /admin: không cho thêm quyền gì."""
    return bool(re.search(r"ai-worker-plugin", ua or "", re.I))


def device_label(ua: str) -> str:
    """Shorten the User-Agent so an admin can tell which device is asking to pair. For reading only, it can be faked.
    Rút gọn User-Agent để quản trị nhìn biết thiết bị nào đang xin ghép. Chỉ để đọc, giả được."""
    for pattern, label in (("Tizen", "Samsung Tizen TV"), ("Web0S", "LG webOS TV"), ("webOS", "LG webOS TV"), ("BRAVIA", "Sony Bravia TV"),
                     ("Android TV", "Android TV"), ("CrKey", "Chromecast"), ("SMART-TV", tx("Smart TV")), ("SmartTV", tx("Smart TV"))):
        if pattern in ua:
            return label
    # the menu bar scripts name themselves (Python on Mac/Linux, PowerShell on Windows)
    # script thanh menu tự xưng tên (Python trên Mac/Linux, PowerShell trên Windows)
    if is_plugin_client(ua):
        return tx("Claude plugin on {os}", os="Windows" if "Windows" in ua else "Mac" if "Mac" in ua else "Linux" if "Linux" in ua else tx("unknown device"))
    if is_menubar_client(ua):
        return tx("Menu bar on {os}", os="Windows" if "Windows" in ua else "Mac" if "macOS" in ua else "Linux" if "Linux" in ua else tx("unknown device"))
    os_name = "Windows" if "Windows" in ua else "iPhone/iPad" if "iPhone" in ua or "iPad" in ua else "Mac" if "Mac OS" in ua else "Android" if "Android" in ua else "Linux" if "Linux" in ua else tx("unknown device")
    browser = "Edge" if "Edg/" in ua else "Chrome" if "Chrome/" in ua else "Safari" if "Safari/" in ua else "Firefox" if "Firefox/" in ua else tx("unknown browser")
    return tx("{browser} on {os}", browser=browser, os=os_name)


def side_of(kind) -> str:
    """Paired rows live on three sides of a wall: keys for the MCP endpoint, Telegram chats, and everything else (""), which is
    screens, menu bar computers, extensions and plugins. A row is found, counted and replaced only on its own side.
    Các dòng đã ghép nằm ở ba phía của một bức tường: khoá cho cổng MCP, chat Telegram, và mọi thứ còn lại (""), tức
    màn hình, máy thanh menu, tiện ích và plugin. Một dòng chỉ được tìm, đếm và thay ở đúng phía của nó."""
    return kind if kind in (KIND_MCP, KIND_TELEGRAM, KIND_PROJECT) else ""


def chat_key(telegram_id: str) -> str:
    """What stands for a Telegram chat where the others hold a random key: the Telegram user's number, which Telegram vouches for.
    It is no secret, so it is taken only from the bot process on this machine, and only on the Telegram side of the wall.
    Thứ đứng thay cho một chat Telegram ở chỗ các loại khác cầm một khoá ngẫu nhiên: số của người dùng Telegram, do Telegram bảo đảm.
    Nó không bí mật, nên chỉ được nhận từ tiến trình bot trên máy này, và chỉ ở phía Telegram của bức tường."""
    return "tg_" + telegram_id


def is_tv(ua: str) -> bool:
    return "TV" in device_label(ua) or "Chromecast" in device_label(ua)


class MenubarLimit(ValueError):
    """The account already has MENUBAR_PER_ACCOUNT computers, counting the ones approved but not yet joined.
    Tài khoản đã có đủ MENUBAR_PER_ACCOUNT máy, tính cả máy đã duyệt mà chưa nhận phiên."""


class TvPairing:
    """Pairing requests that are waiting, in memory only. The code shown on the TV is typed by an admin; the device key is in the TV's cookie,
    so someone who sees the code still cannot take the session in place of the TV.
    Yêu cầu ghép đang chờ, chỉ trong bộ nhớ. Mã hiện trên TV để quản trị nhập; khoá máy nằm trong cookie của TV,
    nên người nhìn thấy mã cũng không nhận được phiên thay TV."""

    def __init__(self):
        self.lock = threading.Lock()
        # code -> {keyHash, ip, device, createdAt, expiresAt, name, approvedBy}
        # mã -> {keyHash, ip, device, createdAt, expiresAt, name, approvedBy}
        self.pending = {}
        # admin -> [wrong entries]
        # người quản trị -> [lần nhập sai]
        self.view_fails = {}

    def _sweep(self, now: float) -> None:
        self.pending = {m: r for m, r in self.pending.items() if r["expiresAt"] > now}

    def request_code(self, old_key: str, ip: str, user_agent: str, now: float, kind: str = "", menubar: bool = False):
        with self.lock:
            self._sweep(now)
            # a Telegram chat's request is left alone here: its key is a number anyone may know, and these paths are public
            # yêu cầu của chat Telegram không bị đụng tới ở đây: khoá của nó là một con số ai cũng có thể biết, mà các đường này là công khai
            if old_key:
                b = sha256_hex(old_key)
                self.pending = {m: r for m, r in self.pending.items() if r["keyHash"] != b or r.get("kind") == KIND_TELEGRAM}
            others = [r for r in self.pending.values() if r.get("kind") != KIND_TELEGRAM]
            if len(others) >= TV_PENDING_TOTAL or sum(1 for r in others if r["ip"] == ip) >= TV_PENDING_PER_IP:
                return None
            while True:
                code = "%08d" % secrets.randbelow(10 ** 8)
                if code not in self.pending:
                    break
            key = secrets.token_urlsafe(32)
            self.pending[code] = {"keyHash": sha256_hex(key), "ip": ip, "device": user_agent, "createdAt": now, "expiresAt": now + TV_CODE_SECONDS, "name": None, "approvedBy": None,
                                  **({"kind": kind} if kind else {}), **({"menubar": True} if menubar else {})}
            return code, key

    def request_chat(self, telegram_id: str, username: str, now: float):
        """A Telegram chat asks for a code. Returns (code, seconds left, whether the code is new): asking again while a code waits gives
        the same code. None when too many chats are waiting.
        Một chat Telegram xin mã. Trả (mã, số giây còn lại, mã có mới không): xin lại khi đang có mã chờ thì nhận đúng mã đó.
        None khi đang có quá nhiều chat chờ."""
        b = sha256_hex(chat_key(telegram_id))
        with self.lock:
            self._sweep(now)
            waiting = {m: r for m, r in self.pending.items() if r.get("kind") == KIND_TELEGRAM}
            for m, r in waiting.items():
                if r["keyHash"] == b:
                    return m, int(r["expiresAt"] - now), False
            if len(waiting) >= TELEGRAM_PENDING_MAX:
                return None
            while True:
                code = "%08d" % secrets.randbelow(10 ** 8)
                if code not in self.pending:
                    break
            self.pending[code] = {"keyHash": b, "ip": "", "device": "Telegram", "createdAt": now, "expiresAt": now + TV_CODE_SECONDS, "name": None, "approvedBy": None,
                                  "kind": KIND_TELEGRAM, "telegramId": telegram_id, "telegramUser": username}
            return code, TV_CODE_SECONDS, True

    def has_key(self, key: str) -> bool:
        b = sha256_hex(key)
        with self.lock:
            return any(r["keyHash"] == b and r.get("kind") != KIND_TELEGRAM for r in self.pending.values())

    def poll(self, key: str, now: float, chat: bool = False):
        """Returns "pending", "expired", or the approved request (and removes it from the waiting list). A Telegram chat's request
        is seen only with chat=True, and then nothing else is: the public pairing paths cannot take it by naming the chat's number.
        Trả "pending", "expired", hoặc yêu cầu đã duyệt (và bỏ nó khỏi danh sách chờ). Yêu cầu của chat Telegram chỉ được thấy
        khi chat=True, và khi đó không thấy thứ gì khác: các đường ghép công khai không lấy được nó bằng cách nêu số của chat."""
        b = sha256_hex(key)
        with self.lock:
            self._sweep(now)
            for m, r in self.pending.items():
                if r["keyHash"] == b and (r.get("kind") == KIND_TELEGRAM) == chat:
                    if not r["name"]:
                        return "pending"
                    return self.pending.pop(m)
        return "expired"

    def peek(self, code: str, admin: str, now: float):
        with self.lock:
            self._sweep(now)
            attempts = [t for t in self.view_fails.get(admin, []) if now - t < TV_VIEW_FAIL_SECONDS]
            if len(attempts) >= TV_VIEW_MAX_FAILS:
                self.view_fails[admin] = attempts
                raise ValueError(tx("Too many wrong tries, try again in 10 minutes"))
            r = self.pending.get(code)
            if not r or r["name"]:
                attempts.append(now)
                self.view_fails[admin] = attempts
                raise ValueError(tx("The code is wrong or has expired"))
            return dict(r)

    def self_approve(self, code: str, account: str, ip: str, now: float, owned: int = 0) -> None:
        """A manager approves their own computer: only a menu bar client's request made from the same IP as the person approving, so nobody pairs a computer elsewhere
        and a viewer cannot approve a wall screen or a browser extension, which need an admin. owned: the account's computers already paired;
        approved requests not yet joined count too, so several codes approved at once cannot pass MENUBAR_PER_ACCOUNT.
        Quản lý tự duyệt máy của mình: chỉ yêu cầu của ứng dụng thanh menu gửi từ cùng IP với người duyệt, để không ai ghép hộ một máy ở nơi khác
        và người xem không duyệt được màn hình treo tường hay tiện ích trình duyệt, những thứ cần quản trị. owned: số máy tài khoản đã ghép;
        yêu cầu đã duyệt mà chưa nhận phiên cũng được tính, để duyệt cùng lúc nhiều mã không vượt được MENUBAR_PER_ACCOUNT."""
        with self.lock:
            self._sweep(now)
            r = self.pending.get(code)
            if not r or r["name"] or r["ip"] != ip or not r.get("menubar") or r.get("kind"):
                raise ValueError(tx("The code is wrong or has expired"))
            if owned + sum(1 for x in self.pending.values() if x.get("owner") == account) >= MENUBAR_PER_ACCOUNT:
                raise MenubarLimit(tx("This account already has {n} computers. Remove one on the Admin page first.", n=MENUBAR_PER_ACCOUNT))
            r.update(name=tx("Menu bar · {account}", account=account), approvedBy=account, owner=account, replaceId="", expiresAt=now + TV_APPROVE_SECONDS)

    def kind_of(self, code: str, now: float) -> str:
        """The kind of the request waiting under this code; empty for a TV or when there is no such code.
        Loại của yêu cầu đang chờ dưới mã này; rỗng với TV hoặc khi không có mã đó."""
        with self.lock:
            self._sweep(now)
            return (self.pending.get(code) or {}).get("kind", "")

    def approve(self, code: str, name: str, approver: str, now: float, replace_id: str = "", scope: str = "") -> dict:
        """scope: for an MCP key or a Telegram chat, what the admin lets it read; kept with the request until the row is made.
        scope: cho khoá MCP hoặc chat Telegram, quản trị cho nó đọc gì; giữ cùng yêu cầu cho tới khi tạo dòng."""
        with self.lock:
            self._sweep(now)
            r = self.pending.get(code)
            if not r or r["name"]:
                raise ValueError(tx("The code is wrong or has expired"))
            r.update(name=name, approvedBy=approver, replaceId=replace_id, expiresAt=now + TV_APPROVE_SECONDS, **({"scope": scope} if scope else {}))
            return dict(r)


class TvStore(Store):
    """Paired screens: {id: {hash, name, createdAt, expiresAt, ceilingAt, approvedBy, createdIp, device, lastIp, lastUsedAt}}.
    Only a hash of the session is stored: reading the database does not let anyone use it.
    Màn hình đã ghép: {id: {hash, name, createdAt, expiresAt, ceilingAt, approvedBy, createdIp, device, lastIp, lastUsedAt}}.
    Chỉ lưu băm của phiên: đọc được cơ sở dữ liệu cũng không dùng được."""

    def load(self) -> dict:
        return load_bodies(self.db, "SELECT id, body FROM screens")

    def save(self, c, old: dict, new: dict) -> None:
        save_keyed(c, "screens", "id", screen_row, old, new)

    def find(self, token: str, now: float, side: str = ""):
        """The row of this key, on one side of the wall (see side_of). A key for the MCP endpoint is found only with side=KIND_MCP and
        a Telegram chat only with side=KIND_TELEGRAM, and then nothing else is: so neither opens a page, and a TV's, an extension's
        or a plugin's key opens neither the MCP endpoint nor the bot's path.
        Dòng của khoá này, ở một phía của bức tường (xem side_of). Khoá cho cổng MCP chỉ được tìm thấy với side=KIND_MCP và
        chat Telegram chỉ với side=KIND_TELEGRAM, và khi đó không thứ gì khác được tìm thấy: nên cả hai không mở được trang nào,
        và khoá của TV, tiện ích hay plugin không mở được cổng MCP lẫn đường của bot."""
        b = sha256_hex(token)
        for tv in self.d.values():
            if hmac.compare_digest(tv["hash"], b) and tv["expiresAt"] > now and side_of(tv.get("kind")) == side:
                return tv
        return None

    def count(self, now: float, side: str = "") -> int:
        """Live rows on one side of the wall: MCP keys, Telegram chats, or everything else. Each side has its own limit.
        Số dòng còn hạn ở một phía: khoá MCP, chat Telegram, hoặc mọi thứ còn lại. Mỗi phía có giới hạn riêng."""
        return sum(1 for v in self.d.values() if v["expiresAt"] > now and side_of(v.get("kind")) == side)

    def create(self, r: dict, now: float) -> tuple:
        side = side_of(r.get("kind"))
        mcp, chat, project = side == KIND_MCP, side == KIND_TELEGRAM, side == KIND_PROJECT
        token = chat_key(r["telegramId"]) if chat else ("mcp_" if mcp else "prj_" if project else "tv_") + secrets.token_urlsafe(32)
        tv_id = secrets.token_hex(6)

        def change(d):
            for k in [k for k, v in d.items() if v["expiresAt"] <= now]:
                del d[k]
            # re-pairing an old screen: drop the old row and the old session, leave no extra row
            # ghép lại cho màn hình cũ: bỏ dòng cũ và phiên cũ, không để lại dòng thừa
            d.pop(r.get("replaceId") or "", None)
            # a chat's key is always the same, so a row it left behind goes: one chat, one row
            # khoá của một chat luôn như cũ, nên dòng nó để lại bị bỏ: một chat, một dòng
            if chat:
                for k in [k for k, v in d.items() if v["hash"] == sha256_hex(token)]:
                    del d[k]
            same_side = sum(1 for v in d.values() if side_of(v.get("kind")) == side)
            if mcp and same_side >= MCP_KEYS_MAX:
                raise ValueError(tx("Limit of {n} MCP keys reached, revoke some first", n=MCP_KEYS_MAX))
            if project and same_side >= PROJECT_KEYS_MAX:
                raise ValueError(tx("Limit of {n} keys for AI projects and applications reached, revoke some first", n=PROJECT_KEYS_MAX))
            if chat and same_side >= TELEGRAM_CHATS_MAX:
                raise ValueError(tx("Limit of {n} Telegram chats reached, revoke some first", n=TELEGRAM_CHATS_MAX))
            if not side and same_side >= TV_MAX:
                raise ValueError(tx("Limit of {n} screens reached, remove some first", n=TV_MAX))
            # a computer a manager paired by itself: checked again here, under the store's lock, so approvals that raced cannot pass the limit
            # máy quản lý tự ghép: kiểm lại ở đây, trong khoá của kho, để các lần duyệt chạy cùng lúc không vượt được giới hạn
            if r.get("owner") and sum(1 for v in d.values() if v.get("owner") == r["owner"]) >= MENUBAR_PER_ACCOUNT:
                raise ValueError(tx("This account already has {n} computers. Remove one on the Admin page first.", n=MENUBAR_PER_ACCOUNT))
            d[tv_id] = {"hash": sha256_hex(token), "name": r["name"], "createdAt": int(now), "expiresAt": int(now + TV_SESSION_SECONDS), "ceilingAt": int(now + TV_CEILING_SECONDS),
                     "approvedBy": r["approvedBy"], "createdIp": r["ip"], "device": r["device"], "lastIp": r["ip"], "lastUsedAt": int(now),
                     **({"owner": r["owner"]} if r.get("owner") else {}), **({"kind": r["kind"]} if r.get("kind") else {}),
                     # an MCP key: what it may read, and its first characters so an admin can tell which key a row is. The rest is never stored
                     # khoá MCP: nó được đọc gì, và vài ký tự đầu để quản trị biết dòng nào là khoá nào. Phần còn lại không bao giờ được lưu
                     **({"scope": MCP_SCOPE_PEOPLE if r.get("scope") == MCP_SCOPE_PEOPLE else MCP_SCOPE_TOTALS} if side in (KIND_MCP, KIND_TELEGRAM) else {}),
                     **({"keyStart": token[:12]} if mcp or project else {}),
                     # a Telegram chat: whose it is, for the admin to read. The number is no secret, and it is all there is to store
                     # chat Telegram: của ai, để quản trị đọc. Con số này không bí mật, và cũng không còn gì khác để lưu
                     **({"telegramId": r["telegramId"], "telegramUser": r.get("telegramUser", "")} if chat else {})}
        self.mutate(change)
        return tv_id, token

    def touch(self, token: str, ip: str, now: float, side: str = "") -> bool:
        """Record use at most once a day, unless the IP changes; renew when close to expiry. True means the cookie must be sent again.
        Ghi lần dùng tối đa mỗi ngày một lần, trừ khi đổi IP; gần hết hạn thì gia hạn. True nghĩa là cần gửi lại cookie."""
        tv = self.find(token, now, side)
        if not tv:
            return False
        tv_id = next(k for k, v in self.d.items() if v["hash"] == tv["hash"])
        renew = tv["expiresAt"] - now < TV_RENEW_WHEN_LEFT and tv["expiresAt"] < tv["ceilingAt"]
        ip_changed = tv["lastIp"] != ip
        if not renew and not ip_changed and now - tv["lastUsedAt"] < 86400:
            return False

        def change(d):
            if tv_id in d:
                d[tv_id].update(lastIp=ip, lastUsedAt=int(now))
                if renew:
                    d[tv_id]["expiresAt"] = int(min(now + TV_SESSION_SECONDS, d[tv_id]["ceilingAt"]))
        self.mutate(change)
        if ip_changed:
            AUDIT_LOG.write(action="tv-ip-changed", tv=tv["name"], **({"kind": tv["kind"]} if tv.get("kind") else {}), oldIp=tv["lastIp"], latestIp=ip)
        if renew:
            AUDIT_LOG.write(action="tv-renewed", tv=tv["name"])
        return renew

    def list_screens(self, now: float) -> list:
        """Never includes the session hash.
        Không bao giờ có băm phiên."""
        return sorted(({"id": k, "exitedAt": v.get("exitedAt", 0), "owner": v.get("owner", ""), "kind": v.get("kind", ""), "scope": v.get("scope", ""), "keyStart": v.get("keyStart", ""),
                        "telegramUser": v.get("telegramUser", ""), "telegramId": v.get("telegramId", ""), "app": v.get("app") is True,
                        **{f: v[f] for f in ("name", "createdAt", "expiresAt", "ceilingAt", "approvedBy", "device", "lastIp", "lastUsedAt")}}
                       for k, v in self.d.items() if v["expiresAt"] > now), key=lambda x: x["name"].lower())

    def exit_screen(self, token: str, now: float) -> str:
        """A screen that exits by itself: drop the session but keep the row, so on re-pairing choose to replace this row and keep the name.
        Màn hình tự thoát: bỏ phiên nhưng giữ dòng, để ghép lại thì chọn thay cho dòng này và giữ được tên."""
        if not token.startswith("tv_"):
            return ""
        tv = self.find(token, now)
        if not tv:
            return ""
        tv_id = next(k for k, v in self.d.items() if v["hash"] == tv["hash"])

        def change(d):
            d[tv_id].update(hash="", exitedAt=int(now))
        self.mutate(change)
        return tv["name"]

    def id_of(self, token: str) -> str:
        b = sha256_hex(token)
        return next((k for k, v in self.d.items() if v["hash"] == b), "")

    def similar(self, ip: str, user_agent: str, now: float, side: str = "") -> list:
        """Paired screens with the same IP and the same type of device: it may be the very device asking to pair again.
        An MCP key is offered only another MCP key to replace, and nothing else is offered one.
        Màn hình đã ghép cùng IP và cùng loại máy: có thể chính là máy đang xin ghép lại.
        Khoá MCP chỉ được gợi ý thay cho một khoá MCP khác, và thứ khác không được gợi ý thay cho khoá MCP."""
        return [{"id": k, "name": v["name"]} for k, v in self.d.items()
                if v["expiresAt"] > now and v["lastIp"] == ip and device_label(v["device"]) == device_label(user_agent) and side_of(v.get("kind")) == side]

    def check_name(self, name: str, except_token: str, now: float) -> None:
        if any(x["name"].lower() == name.lower() and x["id"] != except_token for x in self.list_screens(now)):
            raise ValueError(tx("A screen with this name already exists. Choose to replace it, or use another name."))

    def owned_by(self, account: str, now: float) -> int:
        return sum(1 for v in self.d.values() if v.get("owner") == account and v["expiresAt"] > now)

    def revoke_owner(self, account: str) -> list:
        """Remove every computer an account paired by itself (account deleted, demoted, or its sessions ended).
        Gỡ mọi máy một tài khoản đã tự ghép (tài khoản bị xoá, hạ vai, hoặc bị kết thúc phiên)."""
        def change(d):
            gone = [d.pop(k) for k in [k for k, v in d.items() if v.get("owner") == account]]
            return gone
        rows = self.mutate(change) if any(v.get("owner") == account for v in self.d.values()) else []
        REVOKED_KEYS.remember(rows, time.time())
        return [r["name"] for r in rows]

    def mini_settings(self, token: str, now: float) -> dict:
        tv = self.find(token, now) or {}
        return {"notify": tv.get("notify", True), "notifyMinutes": tv.get("notifyMinutes", 10)}

    def set_mini_settings(self, token: str, notify: bool, minutes: int) -> None:
        tv_id = self.id_of(token)

        def change(d):
            if tv_id not in d:
                raise ValueError(tx("This screen no longer exists"))
            d[tv_id].update(notify=notify, notifyMinutes=minutes)
        self.mutate(change)

    def set_alerts(self, tv_id: str, notify: bool, minutes: int, language: str) -> dict:
        """A Telegram chat's own choice of messages when someone waits too long (board/alerts.py): off by default, set by the chat itself.
        Lựa chọn của chính một chat Telegram về tin báo khi có người chờ quá lâu (board/alerts.py): mặc định tắt, do chính chat đặt."""
        def change(d):
            if tv_id not in d or d[tv_id].get("kind") != KIND_TELEGRAM:
                raise ValueError(tx("This screen no longer exists"))
            d[tv_id].update(notify=notify, notifyMinutes=minutes, notifyLang=language if language in ("en", "vi") else "")
            return dict(d[tv_id])
        return self.mutate(change)

    def set_app(self, tv_id: str, on: bool) -> dict:
        """Let a Telegram chat open the board's window inside Telegram, or stop it. A chat that reads totals only gets totals: see board/tgapp.py.
        Cho một chat Telegram mở khung của bảng bên trong Telegram, hoặc thôi. Chat chỉ được đọc tổng thì nhận số tổng: xem board/tgapp.py."""
        def change(d):
            if tv_id not in d or d[tv_id].get("kind") != KIND_TELEGRAM:
                raise ValueError(tx("This screen no longer exists"))
            d[tv_id]["app"] = on
            return dict(d[tv_id])
        return self.mutate(change)

    def revoke(self, tv_id: str) -> str:
        def change(d):
            if tv_id not in d:
                raise ValueError(tx("This screen no longer exists"))
            return d.pop(tv_id)
        row = self.mutate(change)
        REVOKED_KEYS.remember([row], time.time())
        return row["name"]

    def rename(self, tv_id: str, name: str) -> None:
        def change(d):
            if tv_id not in d:
                raise ValueError(tx("This screen no longer exists"))
            d[tv_id]["name"] = name
        self.mutate(change)


class TvStatus:
    """UI version and the last time each TV sent a request, plus the reload command that is waiting. In memory only, because it changes every 10 seconds.
    Bản giao diện và lần cuối mỗi TV gửi yêu cầu, cùng lệnh tải lại đang chờ. Chỉ trong bộ nhớ, vì đổi mỗi 10 giây."""

    def __init__(self):
        self.lock = threading.Lock()
        # screen id -> {ui, seenAt}
        # id màn hình -> {ui, seenAt}
        self.seen = {}
        self.pending = set()

    def mark_seen(self, tv_id: str, ui_version: str, now: float) -> bool:
        """Record that the TV was seen; True if a reload command is waiting for it (the command is delivered once).
        Ghi lần thấy TV; True nếu đang có lệnh tải lại cho nó (lệnh chỉ giao một lần)."""
        with self.lock:
            self.seen[tv_id] = {"ui": ui_version, "seenAt": now}
            if tv_id in self.pending:
                self.pending.discard(tv_id)
                return True
            return False

    def request_reload(self, tv_id: str) -> None:
        with self.lock:
            self.pending.add(tv_id)

    def read(self, tv_id: str) -> dict:
        with self.lock:
            return dict(self.seen.get(tv_id) or {})


class TelegramBotStatus:
    """What the Telegram bot process last said about itself, in memory: the Admin page shows whether asking from Telegram works.
    For reading only: it comes from the bot process, which holds the key of /bot/telegram, and it decides nothing.
    Điều tiến trình bot Telegram nói gần nhất về chính nó, giữ trong bộ nhớ: trang Quản trị cho biết việc hỏi qua Telegram có chạy không.
    Chỉ để đọc: nó tới từ tiến trình bot, nơi cầm khoá của /bot/telegram, và không quyết định điều gì."""

    # running; Telegram refuses the bot's token; another program reads the same bot; Telegram cannot be reached
    # đang chạy; Telegram từ chối khoá của bot; một chương trình khác đang đọc cùng bot; không tới được Telegram
    STATES = ("ok", "unauthorized", "conflict", "unreachable")

    def __init__(self):
        self.lock = threading.Lock()
        self.state, self.bot, self.at = "", "", 0.0

    def report(self, state, bot, now: float) -> None:
        with self.lock:
            self.state = state if state in self.STATES else ""
            self.bot = bot if isinstance(bot, str) and re.fullmatch(r"[A-Za-z0-9_]{1,32}", bot) else ""
            self.at = now

    def seen(self, now: float) -> None:
        """The bot handed over a message, so it is reading from Telegram.
        Bot vừa đưa một tin nhắn, tức nó đang đọc được từ Telegram."""
        with self.lock:
            self.state, self.at = "ok", now

    def read(self) -> dict:
        with self.lock:
            return {"state": self.state, "bot": self.bot, "seenAt": int(self.at * 1000)}


class RevokedKeys(Store):
    """Hashes of revoked pairings: {hash: {name, kind, revokedAt}}. Only to tell the audit log that a revoked device still asks; it grants nothing.
    Băm của các lần ghép đã thu hồi: {hash: {name, kind, revokedAt}}. Chỉ để nhật ký biết thiết bị đã bị thu hồi vẫn còn hỏi; không cấp quyền gì."""

    def __init__(self, database):
        super().__init__(database)
        self.logged_lock = threading.Lock()
        # hash -> last time its use was written to the log, in memory
        # băm -> lần cuối ghi việc dùng nó vào nhật ký, trong bộ nhớ
        self.logged_at = {}

    def load(self) -> dict:
        return load_bodies(self.db, "SELECT hash, body FROM revoked")

    def save(self, c, old: dict, new: dict) -> None:
        save_keyed(c, "revoked", "hash", revoked_row, old, new)

    def remember(self, rows: list, now: float) -> None:
        rows = [r for r in rows if r.get("hash")]
        if not rows:
            return

        def change(d):
            for k in [k for k, v in d.items() if now - v.get("revokedAt", 0) > TV_REVOKED_KEEP_SECONDS]:
                del d[k]
            for r in rows:
                d[r["hash"]] = {"name": r["name"], "kind": r.get("kind", ""), "revokedAt": int(now)}
            for k in sorted(d, key=lambda k: d[k]["revokedAt"])[:max(0, len(d) - TV_REVOKED_MAX)]:
                del d[k]
        self.mutate(change)

    def used(self, token: str, now: float):
        """The revoked row of this key when its use should be logged now, else None.
        Dòng đã thu hồi của khoá này nếu lần dùng này cần ghi nhật ký, không thì None."""
        if not token.startswith(("tv_", "mcp_")):
            return None
        b = sha256_hex(token)
        r = self.d.get(b)
        if not r or now - r.get("revokedAt", 0) > TV_REVOKED_KEEP_SECONDS:
            return None
        with self.logged_lock:
            if now - self.logged_at.get(b, 0) < TV_REVOKED_LOG_SECONDS:
                return None
            self.logged_at = {k: t for k, t in self.logged_at.items() if now - t < TV_REVOKED_LOG_SECONDS}
            self.logged_at[b] = now
        return r


TV_PAIRING = TvPairing()
TV_STATUS = TvStatus()
TELEGRAM_BOT = TelegramBotStatus()
REVOKED_KEYS = RevokedKeys(data_db())
TV = TvStore(data_db())


class MiniHandoff:
    """One-time codes for the menu bar window, in memory only: the menu bar script, already paired, asks for one and opens the window with it;
    the server swaps it for the same session once, then forgets it.
    Mã dùng một lần cho khung thanh menu, chỉ trong bộ nhớ: script thanh menu đã ghép xin một mã rồi mở khung bằng mã đó;
    máy chủ đổi mã thành chính phiên đó một lần rồi quên."""

    def __init__(self):
        self.lock = threading.Lock()
        # code -> (session token, expiresAt)
        # mã -> (phiên, hết hạn lúc)
        self.codes = {}

    def issue(self, token: str, now: float) -> str:
        with self.lock:
            self.codes = {c: v for c, v in self.codes.items() if v[1] > now}
            # this computer's oldest live codes go first: dict order is the order they were issued
            # bỏ trước các mã còn hạn cũ nhất của máy này: thứ tự trong dict là thứ tự đã cấp
            own = [c for c, v in self.codes.items() if v[0] == token]
            for c in own[:max(0, len(own) - MINI_HANDOFF_PER_TOKEN + 1)]:
                del self.codes[c]
            if len(self.codes) >= MINI_HANDOFF_MAX:
                raise ValueError(tx("Too many requests, try again later."))
            code = secrets.token_urlsafe(24)
            self.codes[code] = (token, now + MINI_HANDOFF_SECONDS)
            return code

    def take(self, code: str, now: float) -> str:
        with self.lock:
            token, expires_at = self.codes.pop(code, ("", 0))
            return token if expires_at > now else ""


MINI_HANDOFF = MiniHandoff()


class WaitTracker:
    """When each person started waiting, so the menu bar can say how long; in memory, so a server restart starts the count again.
    Mỗi người bắt đầu chờ từ lúc nào, để thanh menu nói đã chờ bao lâu; trong bộ nhớ nên khởi động lại máy chủ thì đếm lại."""

    def __init__(self):
        self.lock = threading.Lock()
        self.since = {}

    def note(self, key: str, waiting: int, now: float):
        with self.lock:
            if waiting <= 0:
                self.since.pop(key, None)
                return None
            return self.since.setdefault(key, int(now * 1000))


WAIT_TRACKER = WaitTracker()
# location names the manager set on the board: {branches: [{id, name, lat, lon, isHq}], ipToLocation: {ip: id}, salesTeam: [email]}
# tên địa điểm quản lý đặt trên bảng: {branches: [{id, name, lat, lon, isHq}], ipToLocation: {ip: id}, salesTeam: [email]}
LOCATIONS = DocumentStore(data_db(), "locations")
# latest cost file of the Team plan, merged per person; loading it again replaces it entirely
# file chi phí mới nhất của gói Team, đã gộp theo người; nạp lại thì thay hẳn
TEAM = DocumentStore(data_db(), "team-csv")
# a group of computers with no name shows only if someone sent within this many days
# nhóm máy chưa đặt tên chỉ hiện nếu có người gửi trong ngần này ngày
KEEP_LOCATION_DAYS = 7
TEAM_CSV_MAX_BYTES = 8 * 1024 * 1024


class AuditLog:
    """Who changed what on the board, kept 12 months; CSV content is not copied.
    Ai đổi gì trên bảng, giữ 12 tháng; không chép nội dung CSV."""

    KEEP_MONTHS = 12
    # one row per call of the board's MCP tool: who asked and when, never what was asked, which the server does not see.
    # Many more rows than anything else here, so they are kept a shorter time and read apart from the admin's own log
    # mỗi lần gọi công cụ MCP của bảng một dòng: ai hỏi và lúc nào, không bao giờ có câu hỏi, thứ máy chủ không thấy.
    # Nhiều dòng hơn hẳn mọi thứ khác ở đây, nên giữ ngắn hơn và đọc tách khỏi nhật ký của quản trị
    MCP_CALL = "mcp-call"
    # one row per answer the board gave a Telegram chat: which chat and which command, never the words the person typed.
    # Kept and read with the MCP calls: both are reads of the board from outside its own pages
    # mỗi câu trả lời bảng đưa cho một chat Telegram một dòng: chat nào và lệnh nào, không bao giờ có chữ người đó gõ.
    # Giữ và đọc cùng các lần gọi MCP: cả hai đều là đọc bảng từ bên ngoài các trang của bảng
    ASK_CALL = "telegram-ask"
    READ_ACTIONS = (MCP_CALL, ASK_CALL)
    # one row per piece of work a computer handed to ChatGPT, Gemini or Gemma: who, which helper, lengths, what was stopped
    # and what the check of the answer found, never the text. Kept and read apart, like the reads above
    # mỗi việc một máy giao cho ChatGPT, Gemini hay Gemma một dòng: ai, trợ lý nào, độ dài, đã chặn gì và bước kiểm câu trả
    # lời thấy gì, không bao giờ có chữ. Giữ và đọc riêng, như các lần đọc ở trên
    DELEGATION = "ai-delegation"
    APART = READ_ACTIONS + (DELEGATION,)
    SEEN_DAYS = 4

    def __init__(self, database):
        self.db = database
        self.month = ""
        self.checked = None

    # each row carries the fingerprint of the row before it and its own, so a row changed or taken out of the database
    # by hand breaks the chain, and the Admin page says where. Someone who can rewrite the whole file and the last
    # fingerprint goes unseen: the fingerprint shown on the page is for an admin to note down and compare later.
    # mỗi dòng mang dấu vân tay của dòng trước và của chính nó, nên một dòng bị sửa hay bị xoá khỏi cơ sở dữ liệu bằng tay
    # làm đứt chuỗi, và trang Quản trị nói đứt ở đâu. Người viết lại được cả file lẫn dấu vân tay cuối thì không bị thấy:
    # dấu vân tay hiện trên trang là để quản trị ghi lại và so về sau.
    HEAD = "audit_head"
    CHECK_SECONDS = 60

    @staticmethod
    def fingerprint(prev: str, row: dict) -> str:
        return hashlib.sha256((prev + "\n" + dumps({k: v for k, v in row.items() if k != "hash"})).encode("utf-8")).hexdigest()

    def write_delegations(self, device: str, name: str, account: str, records: list) -> int:
        """Write the records a computer sent that are not in the log yet; returns how many were new.
        Ghi các biên bản một máy gửi mà nhật ký chưa có; trả về số biên bản mới."""
        if not records:
            return 0
        new = []
        try:
            now = int(time.time())
            with self.db.tx() as c:
                for r in records:
                    key = "%s|%s" % (device, r["id"])
                    if c.execute("INSERT OR IGNORE INTO delegations_seen (key, seen_at) VALUES (?, ?)", (key, now)).rowcount:
                        new.append(r)
                c.execute("DELETE FROM delegations_seen WHERE seen_at < ?", (now - self.SEEN_DAYS * 86400,))
        except sqlite3.Error as e:
            sys.stderr.write("audit log: %s\n" % e)
            return 0
        for r in new:
            done = datetime.fromtimestamp(r["at"] / 1000, LOCAL_TZ).isoformat(timespec="seconds")
            fields = {k: v for k, v in r.items() if k != "at" and (v or k not in ("check", "found"))}
            self.write(action=self.DELEGATION, device=device, name=name, account=account, doneAt=done, **fields)
        return len(new)

    def write(self, **fields) -> None:
        now = datetime.now(LOCAL_TZ)
        month = now.strftime("%Y-%m")
        row = {"at": now.isoformat(timespec="seconds"), **{k: v for k, v in fields.items() if k not in ("prev", "hash")}}
        try:
            with self.db.tx() as c:
                head = c.execute("SELECT value FROM meta WHERE key = ?", (self.HEAD,)).fetchone()
                row["prev"] = head[0] if head else ""
                row["hash"] = self.fingerprint(row["prev"], row)
                c.execute("INSERT INTO audit (at, month, action, body) VALUES (?, ?, ?, ?)", (row["at"], month, str(fields.get("action") or ""), dumps(row)))
                c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (self.HEAD, row["hash"]))
                self.checked = None
                if month != self.month:
                    self.month = month
                    year, month_index = now.year, now.month - self.KEEP_MONTHS
                    c.execute("DELETE FROM audit WHERE month < ?", ("%04d-%02d" % ((year, month_index) if month_index > 0 else (year - 1, month_index + 12)),))
                    month_index = now.month - MCP_CALL_KEEP_MONTHS
                    c.execute("DELETE FROM audit WHERE action IN (?, ?, ?) AND month < ?", self.APART + ("%04d-%02d" % ((year, month_index) if month_index > 0 else (year - 1, month_index + 12)),))
        # a broken log is reported, it does not block the action
        # nhật ký hỏng thì báo, không chặn thao tác
        except sqlite3.Error as e:
            sys.stderr.write("audit log: %s\n" % e)

    def read(self, month: str, limit: int = 300) -> list:
        """Newest rows first; `month` is already checked to be YYYY-MM.
        Dòng mới nhất trước; `month` đã kiểm dạng YYYY-MM."""
        return self._read("SELECT body FROM audit WHERE month = ? AND action NOT IN (?, ?, ?) ORDER BY id DESC LIMIT ?", (month,) + self.APART + (limit,))

    def read_calls(self, month: str, limit: int = 300) -> list:
        """The reads of the board from outside its pages in one month, newest first: calls of the MCP tool and answers to Telegram chats.
        Các lần đọc bảng từ bên ngoài các trang của bảng trong một tháng, mới nhất trước: lần gọi công cụ MCP và câu trả lời cho chat Telegram."""
        return self._read("SELECT body FROM audit WHERE month = ? AND action IN (?, ?) ORDER BY id DESC LIMIT ?", (month,) + self.READ_ACTIONS + (limit,))

    def read_delegations(self, month: str, limit: int = 300) -> list:
        """The work computers handed to ChatGPT, Gemini or Gemma in one month, newest first.
        Các việc các máy giao cho ChatGPT, Gemini hay Gemma trong một tháng, mới nhất trước."""
        return self._read("SELECT body FROM audit WHERE month = ? AND action = ? ORDER BY id DESC LIMIT ?", (month, self.DELEGATION, limit))

    def delegation_totals(self, month: str) -> dict:
        """The month's records added up: all, by helper, stopped before sending, and answers the check flagged.
        Biên bản của tháng cộng lại: tất cả, theo trợ lý, bị chặn trước khi gửi, và câu trả lời bước kiểm đã đánh dấu."""
        out = {"all": 0, "chatgpt": 0, "gemini": 0, "gemma": 0, "refused": 0, "flagged": 0}
        for row in self._read("SELECT body FROM audit WHERE month = ? AND action = ?", (month, self.DELEGATION)):
            out["all"] += 1
            if row.get("worker") in ("chatgpt", "gemini", "gemma"):
                out[row["worker"]] += 1
            out["refused"] += row.get("outcome") == "refused"
            out["flagged"] += bool(row.get("check"))
        return out

    def check(self, now: float) -> dict:
        """Walk the chain from the oldest row kept: {"ok", "rows", "since", "brokenAt", "head"}. Rows written before the chain
        began are not counted; the oldest row kept may point to a row already dropped by age. Kept a minute.
        Đi dọc chuỗi từ dòng cũ nhất còn giữ: {"ok", "rows", "since", "brokenAt", "head"}. Dòng ghi trước khi có chuỗi không
        được tính; dòng cũ nhất còn giữ có thể trỏ tới một dòng đã bị bỏ vì quá cũ. Giữ kết quả một phút."""
        if self.checked and now - self.checked[0] < self.CHECK_SECONDS:
            return self.checked[1]
        rows, since, broken, last = 0, "", "", None
        for (body,) in self.db.rows("SELECT body FROM audit ORDER BY id"):
            try:
                row = json.loads(body)
            except ValueError:
                row = {}
            if not isinstance(row, dict) or "hash" not in row:
                if last is not None and not broken:
                    broken = str(row.get("at", "")) if isinstance(row, dict) else ""
                continue
            if row["hash"] != self.fingerprint(str(row.get("prev", "")), row) or (last is not None and row.get("prev") != last):
                broken = broken or str(row.get("at", ""))
            since = since or str(row.get("at", ""))
            last = row["hash"]
            rows += 1
        head = self.db.get_meta(self.HEAD)
        # the newest rows taken out: the last fingerprint kept no longer matches the newest row
        # các dòng mới nhất bị xoá: dấu vân tay cuối được giữ không còn khớp dòng mới nhất
        if head and last != head:
            broken = broken or "end"
        result = {"ok": not broken, "rows": rows, "since": since, "brokenAt": broken, "head": head[:16]}
        self.checked = (now, result)
        return result

    def _read(self, sql: str, args: tuple) -> list:
        out = []
        for (body,) in self.db.rows(sql, args):
            try:
                row = json.loads(body)
            except ValueError:
                continue
            # the chain's fingerprints are for check() alone; readers get the row as it was written
            # dấu vân tay của chuỗi chỉ cho check(); người đọc nhận dòng đúng như lúc ghi
            if isinstance(row, dict):
                row.pop("prev", None)
                row.pop("hash", None)
            out.append(row)
        return out


AUDIT_LOG = AuditLog(data_db())
