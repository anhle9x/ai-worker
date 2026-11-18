#!/usr/bin/env python3
"""Webhook of the AI Worker Office dashboard: takes numbers from the computers and gives them back to the manager's computer.

Standard library only, Python 3.8+. Settings come from environment variables:
  PORT             port to listen on (default 8788)
  BIND_ADDR        address to listen on (default 127.0.0.1)
  INGEST_KEY       key the computers use to send numbers (required)
  DATA_DIR         where the numbers database board.db is kept (default ./data)
  KEYS_DIR         where the accounts database accounts.db with the OTP keys is kept, apart from the backed-up data (default ./keys)
  OTP              only to import accounts once: "name:SECRET,name2:SECRET2" (SECRET in base32); manage them on /admin afterwards
  OTP_ADMINS       names in OTP imported as admin: "name,name2"; anyone not named here or in OTP_WALL can only view
  OTP_WALL         names in OTP imported as wall display: long session, sees no email, IP or /board
  USD_RATE         dong per US dollar on the dashboard, Vietnamese pages only (default 26000)
  TZ_OFFSET        hours from UTC used to split "today" (default 7)
  DEFAULT_LANG     language of the pages when the visitor has not chosen: en or vi; empty (default) follows the browser
  All settings, with notes: ai-worker.env.example

  POST /ingest   Authorization: Bearer <INGEST_KEY>   body: the numbers of one computer (JSON)
  GET  /health                                answers: ok
  GET  /                                        operations dashboard of the whole team (text board: /board), login with a 6-digit OTP
  GET  /data, /static/<file>                   numbers and files of the 3D page (login required)
  POST /locations, /team-csv, /team-sale         name locations, load the Team plan CSV, mark the sales team (login required)
  POST /mcp      Authorization: Bearer <key approved by an admin>   one MCP message; read-only, the wall view as text (MCP=0 removes it)

Each computer (device-...) is tied to the account + name of its first send (table identities): even someone with
INGEST_KEY cannot overwrite another person's row. To give a computer to someone else: stop the webhook, run
webhook.py --forget-device <device-id> as the webhook's user, start it again.

  webhook.py --export-json <folder>    write the databases back as the JSON files of the version before SQLite
  webhook.py --forget-usage <email or name>    delete one person's totals per day (kept 13 months); run it as the webhook's user

Use over weeks and months comes from one total per person per day, added up from the hours the computers already send. Before the
first start on an older database the server copies it to board.db.schema-<old version>.bak next to it; see docs/OPERATIONS.md.

Only numbers are stored (sessions, tokens, money, tasks delegated); a computer never sends chat content or file names.

  Webhook của bảng tổng Văn phòng AI Worker: nhận số liệu từ các máy, trả lại cho máy quản lý.

  Chỉ dùng thư viện chuẩn của Python 3.8+. Cấu hình qua biến môi trường:
  PORT             cổng nghe (mặc định 8788)
  BIND_ADDR        địa chỉ nghe (mặc định 127.0.0.1)
  INGEST_KEY       mã các máy dùng để gửi số liệu (bắt buộc)
  DATA_DIR         nơi lưu cơ sở dữ liệu số liệu board.db (mặc định ./data)
  KEYS_DIR         nơi lưu cơ sở dữ liệu tài khoản accounts.db cùng khoá OTP, tách khỏi dữ liệu sao lưu (mặc định ./keys)
  OTP              chỉ để nhập một lần vào tài khoản: "name:SECRET,name2:SECRET2" (SECRET base32); sau đó quản lý ở /admin
  OTP_ADMINS       tên trong OTP nhập với vai quản trị: "name,name2"; ai không có tên ở đây và OTP_WALL thì chỉ xem
  OTP_WALL         tên trong OTP nhập với vai màn hình treo tường: phiên dài, không thấy email, IP và /board
  USD_RATE         đô la ra đồng trên trang bảng tổng, chỉ cho trang tiếng Việt (mặc định 26000)
  TZ_OFFSET        giờ lệch UTC để chia "hôm nay" (mặc định 7)
  DEFAULT_LANG     ngôn ngữ của trang khi người xem chưa chọn: en hoặc vi; để trống (mặc định) thì theo trình duyệt

  POST /ingest   Authorization: Bearer <INGEST_KEY>   thân: số liệu một máy (JSON)
  GET  /health                                trả: ok
  GET  /                                        bảng điều khiển vận hành cả team (bảng chữ: /board), đăng nhập bằng mã OTP 6 số
  GET  /data, /static/<file>                   số liệu và file của trang 3D (cần đăng nhập)
  POST /locations, /team-csv, /team-sale         đặt tên địa điểm, nạp CSV gói Team, đánh dấu đội sale (cần đăng nhập)
  POST /mcp      Authorization: Bearer <khoá do quản trị duyệt>   một thông điệp MCP; chỉ đọc, phần treo tường dạng chữ (MCP=0 thì gỡ)

  Mỗi máy (device-...) gắn với tài khoản + tên gửi lần đầu (bảng identities): ai có INGEST_KEY cũng không
  ghi đè được dòng của người khác. Chuyển máy cho người khác: dừng webhook, chạy webhook.py --forget-device <mã-máy>
  bằng tài khoản của webhook, rồi bật lại.

  webhook.py --export-json <thư-mục>   ghi cơ sở dữ liệu ngược ra file JSON của bản trước SQLite
  webhook.py --forget-usage <email hoặc tên>   xoá tổng theo ngày của một người (giữ 13 tháng); chạy bằng tài khoản của webhook

  Mức dùng theo tuần và theo tháng lấy từ một con số tổng cho mỗi người mỗi ngày, cộng từ số liệu theo giờ mà các máy vốn đã gửi. Trước
  lần chạy đầu trên cơ sở dữ liệu cũ, máy chủ chép nó thành board.db.schema-<phiên bản cũ>.bak nằm ngay cạnh; xem docs/OPERATIONS.vi.md.

  Chỉ lưu số liệu (số phiên, token, tiền, số việc giao); máy gửi không bao giờ gửi nội dung chat hay tên file.
"""
import csv
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, NamedTuple, Optional
from urllib.parse import parse_qs, quote, urlparse

from board import assets, chat, db, mcp, packages, settings, tgapp
from board.assets import RELEASE_NAME_RE, STATIC_DIR, STATIC_FILES, has_3d_page
from board.devices import clean_payload, key_matches, refuse_constant, save_ingest
from board.lang import REQUEST, lang_from, tx
from board.login import SESSIONS
from board.telegram import TELEGRAM
from board.telegram import bot_id as telegram_bot_id
from board.telegram import enabled as telegram_enabled
from board.packages import (
    MENUBAR_ICON_DIR,
    TV_INSTALL_WINDOWS,
    menubar_deb,
    menubar_extension,
    menubar_mac_dmg,
    menubar_msi,
    menubar_zip,
    tv_mac_zip,
)
from board.pages import (
    JS_LOGIN,
    MINI_PAIR_JS,
    ext_state,
    js_tv,
    mini_state,
    page_3d,
    page_admin,
    page_board,
    page_login,
    page_telegram,
    page_telegram_back,
    js_mcp_connect,
    page_mcp_connect,
    page_mini,
    page_mini_pair,
    page_tv,
)
from board.security import (
    ADMIN,
    BLOCKED,
    BOT,
    BOT_BLOCK_SECONDS,
    VIEWER,
    WALL,
    CallLimit,
    session_lifetime,
)
from board.settings import (
    BIND_ADDR,
    CONNECTION_DEADLINE_SECONDS,
    DATA_DIR,
    KIND_EXTENSION,
    KIND_MCP,
    KIND_TELEGRAM,
    KIND_PLUGIN,
    MAX_BODY_BYTES,
    MCP_CALLS_PER_KEY,
    MCP_CALLS_WINDOW_SECONDS,
    MAX_CONNECTIONS,
    MAX_CONNECTIONS_PER_IP,
    MINI_HANDOFF_SECONDS,
    MINI_NOTIFY_MINUTES,
    PORT,
    TV_CODE_SECONDS,
    TV_SESSION_SECONDS,
)
from board.stores import (
    ACCOUNTS,
    AUDIT_LOG,
    LOCATIONS,
    MINI_HANDOFF,
    REVOKED_KEYS,
    TEAM,
    TEAM_CSV_MAX_BYTES,
    TV,
    TV_PAIRING,
    TV_STATUS,
    MenubarLimit,
    chat_key,
    device_label,
    is_menubar_client,
    is_plugin_client,
    is_tv,
)
from board.views import (
    DAILY,
    INGEST_GATE,
    admin_data,
    daily_loop,
    edit_location,
    history_loop,
    history_view,
    manage_account,
    parse_team_csv,
    record_history,
    role_view,
    tv_action,
)


class Handler(BaseHTTPRequestHandler):
    server_version = "Webhook"
    sys_version = ""
    # a hanging connection must not hold a thread forever
    # kết nối treo không được giữ luồng mãi
    timeout = 30

    def bot_guard(self) -> bool:
        """A request that is not logged in, from an IP that is probing or calling too much, gets 429. True means it has been answered.
        Yêu cầu chưa đăng nhập từ IP đang dò hoặc gọi quá nhiều thì trả 429. True nghĩa là đã trả lời."""
        now = time.time()
        cookie = self.headers.get("Cookie", "")
        # a TV waiting for approval asks every 10 seconds; many TVs on one IP are not counted as probing
        # TV đang chờ duyệt hỏi đều mỗi 10 giây, nhiều TV chung một IP cũng không tính là dò
        if self.path == "/tv/poll" and self.pending_key() and TV_PAIRING.has_key(self.pending_key()):
            return False
        # the browser extension holds its key in a header, not a cookie: a paired or waiting extension is not probing either
        # tiện ích trình duyệt giữ khoá trong header, không trong cookie: tiện ích đã ghép hoặc đang chờ cũng không phải đang dò
        bearer = self.bearer()
        if bearer and ((self.path in ("/ext/poll", "/mcp/poll") and TV_PAIRING.has_key(bearer)) or
                       (self.path.split("?", 1)[0] in EXT_KEY_PATHS and bearer.startswith("tv_") and TV.find(bearer, now))):
            return False
        # an AI tool with a live MCP key is not probing either; how often it may ask is counted per key, in mcp_post
        # công cụ AI có khoá MCP còn hạn cũng không phải đang dò; nó được hỏi bao nhiêu lần thì đếm theo khoá, trong mcp_post
        if bearer.startswith("mcp_") and self.path == "/mcp" and settings.MCP_ENABLED and TV.find(bearer, now, side=KIND_MCP):
            return False
        # nor is the board's window inside Telegram holding a live session; /tg/session counts its own tries per IP and per chat
        # khung bảng bên trong Telegram đang giữ phiên còn sống cũng vậy; /tg/session tự đếm số lần thử theo IP và theo chat
        if bearer.startswith(tgapp.SESSION_PREFIX) and self.path in ("/tg/data", "/tg/unpair") and settings.TELEGRAM_APP_ENABLED and tgapp.SESSIONS.owner(bearer, now):
            return False
        # nor is the Telegram bot process of this machine, which shows its own key on its own path
        # tiến trình bot Telegram của chính máy này cũng vậy, nó trình khoá riêng trên đường riêng
        if self.path == "/bot/telegram" and settings.TELEGRAM_ASK_ENABLED and self.from_this_machine() and key_matches(self.headers.get("Authorization", ""), settings.TELEGRAM_ASK_KEY):
            return False
        if SESSIONS.user_of(cookie, now) or not BOT.is_blocked(self.client_ip(), now):
            return False
        self.send_response(429)
        self.send_header("Retry-After", str(BOT_BLOCK_SECONDS))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def reply(self, status: int, body, quiet: bool = False, headers: tuple = ()) -> None:
        """quiet: a 401 or 404 that is an ordinary answer, not a sign of probing, so it is not counted against the IP.
        quiet: một 401 hay 404 là câu trả lời bình thường, không phải dấu hiệu dò, nên không tính vào IP."""
        b = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        if status in (401, 404) and self.path != "/ingest" and not quiet:
            BOT.record_error(self.client_ip(), time.time())
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def reply_page(self, status: int, b: bytes, cookie: str = "", content_type: str = "text/html; charset=utf-8", cache_control: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie:
            # reached over HTTPS (through Caddy): the cookie is only sent on an encrypted connection
            # vào bằng HTTPS (qua Caddy): cookie chỉ gửi trên kết nối mã hoá
            if self.via_proxy() and self.headers.get("X-Forwarded-Proto", "") == "https":
                cookie += "; Secure"
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(b)

    def board_url_from_host(self) -> str:
        """The board address written into the file for the TV computer; Host comes from the browser, so check it before it goes into a file that runs.
        Địa chỉ bảng ghi vào file cho máy cắm TV; Host do trình duyệt gửi nên phải kiểm trước khi đưa vào file chạy."""
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"[A-Za-z0-9.-]+(:[0-9]{1,5})?", host):
            return ""
        https = self.via_proxy() and self.headers.get("X-Forwarded-Proto", "") == "https"
        return "%s://%s/" % ("https" if https else "http", host)

    def pending_key(self) -> str:
        for part in (self.headers.get("Cookie", "") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "tv-pending":
                return v
        return ""

    def bearer(self) -> str:
        header = self.headers.get("Authorization", "") or ""
        return header[7:].strip()[:200] if header.startswith("Bearer ") else ""

    def note_revoked_key(self, token: str, now: float) -> None:
        """A revoked screen or extension that still asks is written to the audit log, at most once an hour per key.
        Màn hình hay tiện ích đã bị thu hồi mà vẫn hỏi thì ghi vào nhật ký, mỗi khoá tối đa mỗi giờ một lần."""
        r = REVOKED_KEYS.used(token, now)
        if r:
            AUDIT_LOG.write(action="tv-revoked-key-used", tv=r["name"], **({"kind": r["kind"]} if r.get("kind") else {}), clientIp=self.client_ip(),
                            device=device_label(self.headers.get("User-Agent", "")))

    def redirect_home(self, cookie: str = "", dest: str = "/", extra_cookies: tuple = ()) -> None:
        self.send_response(303)
        self.send_header("Location", dest)
        self.send_header("Content-Length", "0")
        for c in ((cookie,) if cookie else ()) + tuple(extra_cookies):
            if self.via_proxy() and self.headers.get("X-Forwarded-Proto", "") == "https":
                c += "; Secure"
            self.send_header("Set-Cookie", c)
        self.end_headers()

    def set_request_lang(self) -> None:
        REQUEST.lang = lang_from(self.headers.get("Cookie", ""), self.headers.get("Accept-Language", ""))

    def do_GET(self):
        self.set_request_lang()
        if self.path != "/health" and self.bot_guard():
            return
        self.dispatch(find_get_route(self.path))

    def do_POST(self):
        self.set_request_lang()
        if self.path != "/ingest" and self.bot_guard():
            return
        # POST matches the whole string: a path with a query must not slip into another path's action
        # POST so khớp cả chuỗi: đường có query không được lọt vào việc của đường khác
        self.dispatch(POST_ROUTES.get(self.path))

    def do_DELETE(self):
        # only the MCP endpoint is ever asked with DELETE, by an AI tool closing a session this server never opened: it gets the 405 a GET gets
        # chỉ cổng MCP mới bị hỏi bằng DELETE, do công cụ AI đóng một phiên mà máy chủ này chưa từng mở: trả 405 như với GET
        self.set_request_lang()
        if self.bot_guard():
            return
        self.dispatch(GET_ROUTES.get(self.path) if self.path == "/mcp" else None)

    def dispatch(self, d: Optional["Route"]) -> None:
        # with MCP=0 the MCP paths are gone: 404, the same as a path that was never there
        # với MCP=0 các đường MCP biến mất: 404, như một đường chưa từng có
        if d and d.mcp and not settings.MCP_ENABLED:
            d = None
        # the same for the Telegram bot's path, which is there only when the server's owner turned asking from Telegram on
        # đường của bot Telegram cũng thế, nó chỉ có mặt khi chủ máy chủ đã bật việc hỏi qua Telegram
        if d and d.telegram_ask and not settings.TELEGRAM_ASK_ENABLED:
            d = None
        # and for the window inside Telegram, which is there only with TELEGRAM_APP=1 as well
        # và cho khung bên trong Telegram, chỉ có mặt khi cũng có TELEGRAM_APP=1
        if d and d.telegram_app and not settings.TELEGRAM_APP_ENABLED:
            d = None
        if not d:
            return self.reply(404, {"error": tx("Not found")})
        y = self.gate(d)
        if y:
            d.handler(self, y)

    def gate(self, d: "Route") -> Optional["RequestCtx"]:
        """The only permission gate, in order: send key or login, origin, role. None means a refusal has been sent.
        Cổng kiểm quyền duy nhất, theo thứ tự: mã gửi hoặc đăng nhập, nguồn gửi, vai. None nghĩa là đã trả lời từ chối."""
        now, cookie = time.time(), self.headers.get("Cookie", "")
        if d.permission == PERM_INGEST_KEY:
            if key_matches(self.headers.get("Authorization", ""), settings.INGEST_KEY):
                return RequestCtx(None, None, cookie, now)
            self.reply(401, {"error": "wrong ingest key"})
            return None
        if d.permission == PERM_DEVICE_KEY:
            # a paired browser extension: the key is in the Authorization header, cookies are ignored, the role is always wall
            # tiện ích trình duyệt đã ghép: khoá nằm trong header Authorization, bỏ qua cookie, vai luôn là treo tường
            token = self.bearer()
            # a POST with the key is still refused from a foreign web page; the extension's own pages send chrome-extension://...
            # POST kèm khoá vẫn bị từ chối nếu từ trang web lạ; trang của chính tiện ích gửi chrome-extension://...
            origin = self.headers.get("Origin")
            if d.origin_policy == ORIGIN_EXTENSION and origin and not origin.startswith("chrome-extension://") and urlparse(origin).netloc != self.headers.get("Host"):
                self.reply(403, {"error": tx("Wrong origin")})
                return None
            tv = TV.find(token, now) if token.startswith("tv_") else None
            if tv:
                return RequestCtx("tv:" + tv["name"], WALL, "", now)
            self.note_revoked_key(token, now)
            self.reply(401, {"error": tx("Not paired")})
            return None
        if d.permission == PERM_BOT_KEY:
            # the Telegram bot process on this same machine, calling the webhook's port directly with the key the installer gave both.
            # Anything that came through the proxy, from any network, is told the path does not exist; cookies and logins count for nothing
            # tiến trình bot Telegram trên chính máy này, gọi thẳng cổng của webhook bằng khoá mà bộ cài giao cho cả hai.
            # Mọi thứ đi qua proxy, từ mạng nào cũng vậy, được báo là đường này không tồn tại; cookie và phiên đăng nhập không có giá trị gì
            if not self.from_this_machine():
                self.reply(404, {"error": tx("Not found")})
                return None
            if key_matches(self.headers.get("Authorization", ""), settings.TELEGRAM_ASK_KEY):
                return RequestCtx("bot:telegram", WALL, "", now)
            self.reply(401, {"error": "wrong bot key"})
            return None
        if d.permission == PERM_TG_SESSION:
            # the window inside Telegram: a session from /tg/session, in the Authorization header; cookies count for nothing. The chat is
            # found again on every call, so a chat revoked or no longer allowed the window is refused at once
            # khung bên trong Telegram: phiên lấy ở /tg/session, nằm trong header Authorization; cookie không có giá trị gì. Chat được
            # tìm lại ở mỗi lần gọi, nên chat bị thu hồi hay không còn được mở khung bị từ chối ngay
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.reply(403, {"error": tx("Wrong origin")})
                return None
            telegram_id = tgapp.SESSIONS.owner(self.bearer(), now)
            chat_row = tgapp.allowed_chat(telegram_id, now) if telegram_id else None
            if chat_row:
                return RequestCtx("tg:" + telegram_id, WALL, "", now)
            if telegram_id:
                tgapp.SESSIONS.end_chat(telegram_id)
            self.reply(401, {"error": tx("Close this window and open it again from the chat.")}, quiet=True)
            return None
        if d.permission == PERM_MCP_KEY:
            # an AI tool on the MCP endpoint: its key is in the Authorization header and cookies are ignored. A tool sends no Origin;
            # a web page on another site does, and is refused whatever key it holds (the MCP transport asks for this check)
            # công cụ AI ở cổng MCP: khoá của nó nằm trong header Authorization và cookie bị bỏ qua. Công cụ thì không gửi Origin;
            # trang web ở nơi khác thì có gửi, và bị từ chối dù cầm khoá nào (kiểu truyền của MCP đòi bước kiểm này)
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.reply(403, {"error": tx("Wrong origin")})
                return None
            token = self.bearer()
            key = TV.find(token, now, side=KIND_MCP) if token.startswith("mcp_") else None
            if key:
                return RequestCtx("mcp:" + key["name"], WALL, "", now)
            self.note_revoked_key(token, now)
            self.reply(401, {"error": tx("This endpoint needs a key from the board, sent as Authorization: Bearer. Open /mcp/connect on the board to ask for one; an admin approves each key.")},
                       headers=(("WWW-Authenticate", 'Bearer realm="AI Worker board"'),))
            return None
        user, role = SESSIONS.user_and_role(cookie, now)
        if not user and SESSIONS.token_of(cookie).startswith("tv_"):
            self.note_revoked_key(SESSIONS.token_of(cookie), now)
        if d.permission != PERM_PUBLIC and not user:
            if d.is_page:
                self.reply_page(200, page_login())
            else:
                self.reply(401, {"error": tx("Not logged in")})
            return None
        # the browser always sends Origin with a fetch POST; account actions require it
        # trình duyệt luôn gửi Origin với fetch POST; thao tác về tài khoản thì bắt buộc phải có
        origin = self.headers.get("Origin")
        # a form on a page with no-referrer sends Origin: null, treated as no Origin; actions that require the exact origin still refuse it
        # form trên trang có no-referrer gửi Origin: null, coi như không có Origin; thao tác bắt buộc đúng nguồn vẫn từ chối
        if origin == "null" and d.origin_policy == ORIGIN_IF_PRESENT:
            origin = None
        # a browser extension's own pages and service worker send their own origin; any other foreign page is refused
        # trang và service worker của tiện ích trình duyệt gửi nguồn của chính nó; mọi trang lạ khác bị từ chối
        if d.origin_policy == ORIGIN_EXTENSION and origin and origin.startswith("chrome-extension://"):
            origin = None
        if (d.origin_policy and origin and urlparse(origin).netloc != self.headers.get("Host")) or (d.origin_policy == ORIGIN_REQUIRED and not origin):
            self.reply(403, {"error": tx("Wrong origin")})
            return None
        y = RequestCtx(user, role, cookie, now)
        if d.permission in ROLES_ALLOWED and role not in ROLES_ALLOWED[d.permission]:
            if self.command == "POST":
                sys.stderr.write("%s: denied %s (%s)\n" % (self.path, user, role))
                self.audit_request(y, action="role-denied")
            if d.is_page:
                self.redirect_home()
            else:
                self.reply(403, {"error": tx("This account can only view")})
            return None
        return y

    def audit_request(self, y: "RequestCtx", **fields) -> None:
        AUDIT_LOG.write(actor=y.user, role=y.role, clientIp=self.client_ip(), path=self.path, **fields)

    def get_robots(self, y: "RequestCtx") -> None:
        self.reply_page(200, b"User-agent: *\nDisallow: /\n", content_type="text/plain; charset=utf-8")

    def get_home(self, y: "RequestCtx") -> None:
        if not y.user:
            if is_tv(self.headers.get("User-Agent", "")):
                return self.redirect_home(dest="/tv")
            return self.reply_page(200, page_login())
        if y.role == WALL and not has_3d_page():
            return self.reply(503, {"error": tx("The wall display page is missing")})
        self.reply_page(200, page_3d(y.user, y.role) if has_3d_page() else page_board(y.user, y.now, y.role))

    def get_board(self, y: "RequestCtx") -> None:
        self.reply_page(200, page_board(y.user, y.now, y.role))

    def get_tv(self, y: "RequestCtx") -> None:
        if y.user:
            return self.redirect_home()
        self.reply_page(200, page_tv(self.headers.get("User-Agent", "")))

    def is_paired_computer(self, y: "RequestCtx") -> bool:
        return bool(y.user) and SESSIONS.token_of(y.cookie).startswith("tv_")

    def get_mini(self, y: "RequestCtx") -> None:
        """The menu bar window. With ?h=<one-time code> it takes the paired computer's session and comes back without the code in the address.
        Khung thanh menu. Có ?h=<mã dùng một lần> thì nhận phiên của máy đã ghép rồi quay lại, địa chỉ không còn mã."""
        query = parse_qs(urlparse(self.path).query)
        code = query.get("h", [""])[0]
        # the tray opening the window says which language the person chose (?lang=en|vi), so the page and the tray menu agree
        # khay mở khung kèm ngôn ngữ người dùng đã chọn (?lang=en|vi), để trang và menu ở khay khớp nhau
        lang = query.get("lang", [""])[0]
        lang_cookie = ("lang=%s; Path=/; Max-Age=31536000; SameSite=Lax" % lang,) if lang in ("en", "vi") else ()
        if code:
            # a link from another site must not swap the browser's session (login CSRF): the real clients open this address themselves,
            # so the browser sends Sec-Fetch-Site: none, or no such header at all in an older web view
            # đường dẫn từ trang khác không được đổi phiên của trình duyệt (CSRF đăng nhập): ứng dụng thật tự mở địa chỉ này,
            # nên trình duyệt gửi Sec-Fetch-Site: none, hoặc không có header đó ở web view cũ
            if self.headers.get("Sec-Fetch-Site", "none") not in ("none", "same-origin"):
                return self.redirect_home(dest="/mini", extra_cookies=lang_cookie)
            # a person already logged in to this browser keeps their own session; only a paired computer's session is replaced
            # người đã đăng nhập trong trình duyệt này giữ phiên của mình; chỉ phiên của máy đã ghép mới bị thay
            if y.user and not self.is_paired_computer(y):
                return self.redirect_home(dest="/mini", extra_cookies=lang_cookie)
            token = MINI_HANDOFF.take(code, y.now)
            if token and TV.find(token, y.now):
                return self.redirect_home("session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (token, TV_SESSION_SECONDS), dest="/mini",
                                          extra_cookies=lang_cookie)
            return self.redirect_home(dest="/mini", extra_cookies=lang_cookie)
        if lang_cookie:
            return self.redirect_home(dest="/mini", extra_cookies=lang_cookie)
        self.reply_page(200, page_mini(bool(y.user)))

    def get_mini_logo(self, y: "RequestCtx") -> None:
        """The logo at the top of the small window, the same one the menu bar icon uses (MENUBAR_ICON_DIR, else the shipped one); black or white for a light or dark background.
        Logo ở đầu khung nhỏ, đúng logo biểu tượng thanh menu đang dùng (MENUBAR_ICON_DIR, không thì logo đi kèm); bản đen hoặc trắng cho nền sáng hay tối."""
        color = "white" if self.path.endswith("white.png") else "black"
        own = os.path.join(MENUBAR_ICON_DIR, "icon-%s.png" % color) if MENUBAR_ICON_DIR else ""
        path = own if own and os.path.isfile(own) else os.path.join(packages.MENUBAR_DIR, "icons", "generic-%s.png" % color)
        with open(path, "rb") as f:
            self.reply_page(200, f.read(), content_type="image/png", cache_control="private, max-age=86400")

    def get_mini_pair(self, y: "RequestCtx") -> None:
        self.reply_page(200, page_mini_pair())

    def get_mini_pair_js(self, y: "RequestCtx") -> None:
        self.reply_page(200, MINI_PAIR_JS.encode(), content_type="text/javascript; charset=utf-8", cache_control="no-cache")

    def mini_self_pair(self, y: "RequestCtx") -> None:
        """A manager pairs their own menu bar computer with their account and OTP: same limits as logging in, the request must come from the same IP,
        at most MENUBAR_PER_ACCOUNT computers, viewer or admin only. Nobody else needs to approve.
        Quản lý tự ghép máy thanh menu bằng tài khoản và OTP: cùng giới hạn như đăng nhập, yêu cầu phải cùng IP,
        tối đa MENUBAR_PER_ACCOUNT máy, chỉ vai xem hoặc quản trị. Không cần ai khác duyệt."""
        ip = self.client_ip()
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 1024:
            return self.reply(413, {"error": tx("Too large")})
        try:
            body = json.loads(self.rfile.read(n), parse_constant=refuse_constant)
            if not isinstance(body, dict):
                raise ValueError("body")
        except (ValueError, RecursionError):
            return self.reply(400, {"error": tx("Invalid format")})
        code = str(body.get("code") or "")
        if not re.fullmatch(r"[0-9]{8}", code):
            return self.reply(400, {"error": tx("The code is wrong or has expired")})
        now = time.time()
        account = SESSIONS.check_otp(str(body.get("account") or "")[:120], str(body.get("otp") or "").strip(), ip, now)
        if account == BLOCKED:
            return self.reply(429, {"error": tx("Too many wrong tries. Try again in 15 minutes.")})
        if not account:
            AUDIT_LOG.write(action="menubar-pair-failed", clientIp=ip)
            return self.reply(401, {"error": tx("Wrong name or code, or the code was already used. Wait for a new code and enter it again.")})
        if ACCOUNTS.role_of(account) not in (ADMIN, VIEWER):
            return self.reply(403, {"error": tx("This account cannot pair a menu bar computer")})
        try:
            TV_PAIRING.self_approve(code, account, ip, now, TV.owned_by(account, now))
        except MenubarLimit as e:
            return self.reply(409, {"error": str(e)})
        except ValueError as e:
            AUDIT_LOG.write(action="menubar-pair-refused", actor=account, clientIp=ip)
            return self.reply(400, {"error": str(e)})
        AUDIT_LOG.write(action="menubar-self-pair", actor=account, clientIp=ip)
        self.reply(200, {"ok": True})

    def get_mini_state(self, y: "RequestCtx") -> None:
        if not self.is_paired_computer(y):
            return self.reply(403, {"error": tx("Only a paired computer can do this")})
        token = SESSIONS.token_of(y.cookie)
        # the menu bar script asks every minute: a computer still in use is renewed like a TV screen, up to TV_CEILING_SECONDS
        # script thanh menu hỏi mỗi phút: máy còn dùng thì gia hạn như màn hình TV, tới TV_CEILING_SECONDS thì phải ghép lại
        TV.touch(token, self.client_ip(), y.now)
        self.reply(200, mini_state(token, y.now))

    def get_ext_state(self, y: "RequestCtx") -> None:
        """The browser extension asks every minute with its key: renewed like a TV screen, seen on the Admin page like one.
        Tiện ích trình duyệt hỏi mỗi phút bằng khoá của nó: gia hạn như màn hình TV, hiện trên trang Quản trị như màn hình."""
        token = self.bearer()
        TV.touch(token, self.client_ip(), y.now)
        TV_STATUS.mark_seen(TV.id_of(token), "", y.now)
        self.reply(200, ext_state(y.now))

    def get_ext_mini(self, y: "RequestCtx") -> None:
        """The menu bar window's page for the extension's popup, in ?lang=en|vi (else the request's language). Needs no cookie:
        the popup copies its words and layout and runs its own copy of mini.js, which reads /ext/data.
        Trang khung thanh menu cho cửa sổ nhỏ của tiện ích, theo ?lang=en|vi (không có thì theo ngôn ngữ của yêu cầu). Không cần cookie:
        cửa sổ nhỏ chép chữ và bố cục rồi chạy bản mini.js của nó, bản này đọc /ext/data."""
        lang = parse_qs(urlparse(self.path).query).get("lang", [""])[0]
        if lang in ("en", "vi"):
            REQUEST.lang = lang
        self.reply_page(200, page_mini(True, browser=True))

    def get_ext_data(self, y: "RequestCtx") -> None:
        """What /data gives a wall screen, for the extension's popup: the same view the menu bar window reads, renewed like /ext/state.
        Những gì /data đưa cho màn hình treo tường, cho cửa sổ nhỏ của tiện ích: cùng phần khung thanh menu đọc, gia hạn như /ext/state."""
        token = self.bearer()
        TV.touch(token, self.client_ip(), y.now)
        TV_STATUS.mark_seen(TV.id_of(token), "", y.now)
        self.reply_page(200, json.dumps(role_view(WALL, y.now), ensure_ascii=False).encode(), content_type="application/json; charset=utf-8")

    def ext_unpair(self, y: "RequestCtx") -> None:
        """The browser extension unpairs itself: its key stops working on the server at once, not only in the browser.
        Tiện ích trình duyệt tự bỏ ghép: khoá của nó hết dùng được trên máy chủ ngay, không chỉ bị quên trong trình duyệt."""
        tv_id = TV.id_of(self.bearer())
        kind = TV.d.get(tv_id, {}).get("kind", "")
        try:
            name = TV.revoke(tv_id)
        except ValueError as e:
            return self.reply(400, {"error": str(e)[:200]})
        AUDIT_LOG.write(action="tv-unpaired-itself", tv=name, id=tv_id, **({"kind": kind} if kind else {}), clientIp=self.client_ip())
        self.reply(200, {"ok": True})

    def get_tg_app(self, y: "RequestCtx") -> None:
        """The board's window inside Telegram, in ?lang=en|vi (else the request's language). The page holds no numbers: its script
        reads Telegram's signed fields from the address and asks /tg/session for a session first.
        Khung bảng bên trong Telegram, theo ?lang=en|vi (không có thì theo ngôn ngữ của yêu cầu). Trang không chứa số liệu: script của nó
        đọc các trường Telegram đã ký trong địa chỉ và xin /tg/session một phiên trước."""
        lang = parse_qs(urlparse(self.path).query).get("lang", [""])[0]
        if lang in ("en", "vi"):
            REQUEST.lang = lang
        self.reply_page(200, page_mini(True, telegram=True))

    def get_tg_file(self, y: "RequestCtx") -> None:
        """The window's own script and the menu bar window's script and style, served under /tg/ with no login.
        Script riêng của khung và script, kiểu trình bày của khung thanh menu, phục vụ dưới /tg/ không cần đăng nhập."""
        file_name = {"/tg/app.js": "tg-app.js", "/tg/mini.js": "mini.js", "/tg/mini.css": "mini.css"}[self.path.split("?", 1)[0]]
        with open(os.path.join(assets.STATIC_DIR, file_name), "rb") as f:
            self.reply_page(200, f.read(), content_type=("text/css" if file_name.endswith(".css") else "text/javascript") + "; charset=utf-8", cache_control="no-cache")

    def tg_session(self, y: "RequestCtx") -> None:
        """Telegram's signed fields in, a session out, for a chat an admin approved and allowed the window. A wrong signature counts as
        probing; fields that are only too old do not, so a phone left open for a while cannot get its office blocked.
        Nhận các trường Telegram đã ký, trả một phiên, cho chat đã được quản trị duyệt và cho mở khung. Chữ ký sai tính là dò;
        các trường chỉ quá cũ thì không, để một điện thoại để mở lâu không làm cả văn phòng bị chặn."""
        ip = self.client_ip()
        if not tgapp.SESSION_LIMIT_IP.allow(ip, y.now):
            return self.reply(429, {"error": tx("Too many tries. Try again in a minute.")})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > tgapp.INIT_DATA_MAX_BYTES + 256:
            return self.reply(413, {"error": tx("Too large")})
        try:
            body = json.loads(self.rfile.read(n), parse_constant=refuse_constant)
            raw = body.get("initData") if isinstance(body, dict) else None
        except ValueError:
            return self.reply(400, {"error": tx("Not JSON")})
        telegram_id = tgapp.check_init_data(raw, settings.TELEGRAM_APP_KEY, y.now)
        if not telegram_id:
            # the same fields with a signature that still holds, only too old: a quiet answer; anything else is counted against the IP
            # cùng các trường với chữ ký vẫn đúng, chỉ quá cũ: trả lời êm; mọi thứ khác bị tính vào IP
            stale = self.signed_but_old(raw)
            AUDIT_LOG.write(action="telegram-app-refused", reason="old" if stale else "signature", clientIp=ip)
            return self.reply(401, {"error": tx("Close this window and open it again from the chat.")}, quiet=stale)
        chat_row = tgapp.allowed_chat(telegram_id, y.now)
        if not chat_row or not tgapp.SESSION_LIMIT_CHAT.allow(telegram_id, y.now):
            AUDIT_LOG.write(action="telegram-app-refused", reason="not-allowed" if not chat_row else "rate", telegramId=telegram_id, clientIp=ip)
            return self.reply(403, {"error": tx("This chat may not open the board's window. Ask an admin of the board.")}, quiet=True)
        token = tgapp.SESSIONS.issue(telegram_id, y.now)
        chat_id = TV.id_of(chat_key(telegram_id))
        TV_STATUS.mark_seen(chat_id, "", y.now)
        AUDIT_LOG.write(action="telegram-app-open", tv=chat_row["name"], id=chat_id, kind=KIND_TELEGRAM, clientIp=ip)
        self.reply(200, {"token": token})

    @staticmethod
    def signed_but_old(raw) -> bool:
        """Whether Telegram signed these fields, whatever their age: told apart from a forged signature only to choose how to answer.
        Telegram có ký các trường này không, bất kể chúng cũ bao lâu: chỉ để phân biệt với chữ ký giả khi chọn cách trả lời."""
        if not isinstance(raw, str):
            return False
        signed = re.search(r"(?:^|&)auth_date=([0-9]{1,12})(?:&|$)", raw)
        return bool(signed) and tgapp.check_init_data(raw, settings.TELEGRAM_APP_KEY, int(signed.group(1))) is not None

    def get_tg_data(self, y: "RequestCtx") -> None:
        """What the menu bar window reads, for the window inside Telegram: the wall view, as for the browser extension. Only a chat that
        reads each person gets here (board/tgapp.py), so it shows no more than the chat's own answers already do.
        Thứ khung thanh menu đọc, cho khung bên trong Telegram: phần màn hình treo tường, như với tiện ích trình duyệt. Chỉ chat được đọc
        từng người mới tới được đây (board/tgapp.py), nên nó không cho thấy gì hơn các câu trả lời của chính chat đó."""
        telegram_id = y.user[len("tg:"):]
        if not tgapp.DATA_LIMIT.allow(telegram_id, y.now):
            return self.reply(429, {"error": tx("Too many tries. Try again in a minute.")}, quiet=True)
        TV_STATUS.mark_seen(TV.id_of(chat_key(telegram_id)), "", y.now)
        self.reply_page(200, json.dumps(role_view(WALL, y.now), ensure_ascii=False).encode(), content_type="application/json; charset=utf-8")

    def tg_unpair(self, y: "RequestCtx") -> None:
        """The window disconnects its own chat, as /stop in the chat does: the chat reads nothing more until an admin approves it again.
        Khung ngắt chính chat của nó, như gõ /stop trong chat: chat không đọc được gì nữa cho tới khi quản trị duyệt lại."""
        telegram_id = y.user[len("tg:"):]
        chat_id = TV.id_of(chat_key(telegram_id))
        try:
            name = TV.revoke(chat_id)
        except ValueError as e:
            return self.reply(400, {"error": str(e)[:200]})
        tgapp.SESSIONS.end_chat(telegram_id)
        AUDIT_LOG.write(action="telegram-stop", tv=name, id=chat_id, kind=KIND_TELEGRAM, via="window")
        self.reply(200, {"ok": True})

    def mini_action(self, y: "RequestCtx") -> None:
        """Handoff, settings and unpair for a paired computer. Only the computer's own pairing is touched.
        Đổi mã, cài đặt và bỏ ghép cho máy đã ghép. Chỉ đụng tới lần ghép của chính máy đó."""
        if not self.is_paired_computer(y):
            return self.reply(403, {"error": tx("Only a paired computer can do this")})
        token = SESSIONS.token_of(y.cookie)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 1024:
            return self.reply(413, {"error": tx("Too large")})
        try:
            body = json.loads(self.rfile.read(n) or b"{}", parse_constant=refuse_constant) if n else {}
            if not isinstance(body, dict):
                raise ValueError("body")
            if self.path == "/mini/handoff":
                return self.reply(200, {"code": MINI_HANDOFF.issue(token, y.now), "secondsLeft": MINI_HANDOFF_SECONDS})
            if self.path == "/mini/settings":
                minutes = body.get("notifyMinutes")
                if not isinstance(body.get("notify"), bool) or minutes not in MINI_NOTIFY_MINUTES or isinstance(minutes, bool):
                    raise ValueError(tx("Invalid settings"))
                TV.set_mini_settings(token, body["notify"], minutes)
                return self.reply(200, {"ok": True})
            name = TV.revoke(TV.id_of(token))
            AUDIT_LOG.write(action="tv-unpaired-itself", tv=name, clientIp=self.client_ip())
            return self.reply_page(200, b'{"ok": true}', cookie="session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict",
                                   content_type="application/json; charset=utf-8")
        except (ValueError, RecursionError) as e:
            return self.reply(400, {"error": str(e)[:200]})

    def get_tv_installer(self, y: "RequestCtx") -> None:
        board_url = self.board_url_from_host()
        if not board_url:
            return self.reply(400, {"error": tx("Invalid address")})
        if self.path.endswith(".bat"):
            return self.reply_page(200, TV_INSTALL_WINDOWS.replace("__BOARD_URL__", board_url).encode(), content_type="application/octet-stream")
        self.reply_page(200, tv_mac_zip(board_url), content_type="application/zip")

    def get_menubar_installer(self, y: "RequestCtx") -> None:
        board_url = self.board_url_from_host()
        if not board_url:
            return self.reply(400, {"error": tx("Invalid address")})
        if self.path.endswith(".deb"):
            return self.reply_page(200, menubar_deb(board_url), content_type="application/vnd.debian.binary-package")
        if self.path.endswith(".msi"):
            package = menubar_msi(board_url)
            if package is None:
                return self.reply(404, {"error": tx("Not found")})
            return self.reply_page(200, package, content_type="application/x-msi")
        if self.path.endswith("extension.zip"):
            extension = menubar_extension()
            if not extension:
                return self.reply(404, {"error": tx("Not found")})
            with open(extension, "rb") as f:
                return self.reply_page(200, f.read(), content_type="application/zip")
        if self.path.endswith(".dmg"):
            dmg = menubar_mac_dmg()
            if not dmg:
                return self.reply(404, {"error": tx("Not found")})
            with open(dmg, "rb") as f:
                return self.reply_page(200, f.read(), content_type="application/x-apple-diskimage")
        system = "windows" if self.path.endswith("windows.zip") else "mac"
        if system == "mac" and packages.MENUBAR_MAC_APP and os.path.isfile(packages.MENUBAR_MAC_APP):
            with open(packages.MENUBAR_MAC_APP, "rb") as f:
                return self.reply_page(200, f.read(), content_type="application/zip")
        self.reply_page(200, menubar_zip(board_url, system), content_type="application/zip")

    def get_tv_qr(self, y: "RequestCtx") -> None:
        # the QR drawing library, holds no data; a TV that is not logged in needs it to show the code
        # thư viện vẽ QR, không chứa dữ liệu; TV chưa đăng nhập cần nó để hiện mã
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "qrcode.js"), "rb") as f:
                return self.reply_page(200, f.read(), content_type="text/javascript; charset=utf-8", cache_control="max-age=86400")
        except OSError:
            return self.reply(404, {"error": tx("Not found")})

    def get_tv_js(self, y: "RequestCtx") -> None:
        self.reply_page(200, js_tv(), content_type="text/javascript; charset=utf-8", cache_control="no-cache")

    def get_admin(self, y: "RequestCtx") -> None:
        self.reply_page(200, page_admin(y.user))

    def get_admin_data(self, y: "RequestCtx") -> None:
        month = parse_qs(urlparse(self.path).query).get("month", [""])[0]
        self.reply(200, admin_data(y.now, y.cookie, month))

    def get_history(self, y: "RequestCtx") -> None:
        b = json.dumps(history_view(y.role, y.now), ensure_ascii=False).encode()
        self.reply_page(200, b, content_type="application/json; charset=utf-8")

    def get_data(self, y: "RequestCtx") -> None:
        d = role_view(y.role, y.now)
        token = SESSIONS.token_of(y.cookie)
        if token.startswith("tv_"):
            ui_version = parse_qs(urlparse(self.path).query).get("ui", [""])[0]
            if TV_STATUS.mark_seen(TV.id_of(token), ui_version if ui_version.isdigit() else "", y.now):
                d["reload"] = True
        b = json.dumps(d, ensure_ascii=False).encode()
        # a TV screen still in use is renewed; TV_CEILING_SECONDS is the cap, after that it must be paired again
        # màn hình TV còn dùng thì gia hạn; TV_CEILING_SECONDS là trần, tới đó phải ghép lại
        renewed = token.startswith("tv_") and TV.touch(token, self.client_ip(), y.now)
        cookie = "session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (token, TV_SESSION_SECONDS) if renewed else ""
        self.reply_page(200, b, cookie=cookie, content_type="application/json; charset=utf-8")

    def get_static(self, y: "RequestCtx") -> None:
        file_name = self.path[len("/static/"):].split("?")[0]
        if file_name not in STATIC_FILES:
            return self.reply(404, {"error": tx("Not found")})
        with open(os.path.join(STATIC_DIR, file_name), "rb") as f:
            # three.js is heavy (~2 MB) and does not change: let the browser keep it for a long time
            # three.js nặng (~2 MB) và không đổi: cho trình duyệt giữ lâu
            cache_control = "private, max-age=604800" if file_name == "three.js" or file_name.endswith(".json") else "private, max-age=300"
            self.reply_page(200, f.read(), content_type=STATIC_FILES[file_name] + "; charset=utf-8", cache_control=cache_control)

    def get_release(self, y: "RequestCtx") -> None:
        """Plugin updates. The server signs nothing: the receiving machine checks the signature itself.
        Bản cập nhật plugin. Máy chủ không ký gì: máy nhận tự kiểm chữ ký."""
        file_name = self.path[len("/releases/"):]
        file_path = os.path.join(assets.RELEASES_DIR, file_name)
        if not RELEASE_NAME_RE.match(file_name):
            return self.reply(404, {"error": tx("Not found")})
        if not os.path.isfile(file_path):
            # not released yet is normal: every device asks, it must not count as probing paths
            # chưa phát hành là bình thường: mọi máy đều hỏi, không được tính là dò đường dẫn
            return self.reply_page(200, b"{}", content_type="application/json; charset=utf-8", cache_control="no-store")
        with open(file_path, "rb") as f:
            self.reply_page(200, f.read(), content_type="application/zip" if file_name.endswith(".zip") else "text/plain; charset=utf-8", cache_control="no-store")

    def get_login_js(self, y: "RequestCtx") -> None:
        self.reply_page(200, JS_LOGIN, content_type="text/javascript; charset=utf-8", cache_control="no-cache")

    def get_health(self, y: "RequestCtx") -> None:
        self.reply(200, {"ok": True})

    def logout(self, y: "RequestCtx") -> None:
        SESSIONS.logout(y.cookie)
        # a TV screen that exits by itself loses its session on disk and must pair with a code to come back; the row and the name are kept
        # màn hình TV tự thoát thì bỏ luôn phiên trên đĩa, muốn vào lại phải ghép mã; dòng và tên vẫn giữ
        tv_name = TV.exit_screen(SESSIONS.token_of(y.cookie), time.time())
        if tv_name:
            AUDIT_LOG.write(action="tv-self-exit", tv=tv_name, clientIp=self.client_ip())
        self.redirect_home("session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")

    def ingest(self, y: "RequestCtx") -> None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY_BYTES:
            return self.reply(413, {"error": "too large"})
        try:
            d = clean_payload(json.loads(self.rfile.read(n), parse_constant=refuse_constant), time.time())
        except (ValueError, RecursionError):
            return self.reply(400, {"error": "not JSON"})
        if not d:
            return self.reply(400, {"error": "invalid format"})
        # the IP is written by the server, the sending device cannot claim one
        # IP do máy chủ tự ghi, máy gửi không tự khai được
        d["ip"] = self.client_ip()
        device_count = db.data_db().rows("SELECT COUNT(*) FROM devices")[0][0]
        rejection = INGEST_GATE.check(d, d["ip"], time.time(), device_count)
        if rejection:
            sys.stderr.write("rejected ingest from %s at %s: %s\n" % (d["device"], d["ip"], rejection[1]))
            return self.reply(rejection[0], {"error": rejection[1]})
        save_ingest(d, time.time())
        record_history()
        self.reply(200, {"ok": True})

    def tv_pair(self, y: "RequestCtx") -> None:
        """A TV that is not logged in asks for a code and asks whether it is approved. Always returns 200 so it is not counted as probing paths.
        TV chưa đăng nhập xin mã và hỏi đã được duyệt chưa. Luôn trả 200 để không bị tính là dò đường dẫn."""
        now, ip = time.time(), self.client_ip()
        user_agent = re.sub(r"[^\x20-\x7e]", "", self.headers.get("User-Agent", ""))[:200]
        # the browser extension (/ext/...) uses the same flow, but its keys travel in the Authorization header and the JSON reply:
        # a cookie would land in the manager's own browser and replace their login to the board
        # tiện ích trình duyệt (/ext/...) dùng cùng quy trình, nhưng khoá đi trong header Authorization và trong JSON trả về:
        # cookie sẽ nằm trong chính trình duyệt của quản lý và đè lên phiên đăng nhập bảng của họ
        mcp_key = self.path.startswith("/mcp/")
        extension = self.path.startswith("/ext/") or mcp_key
        # a manager's Claude plugin pairs on the extension's paths and names itself, so /admin can tell the two apart.
        # A key for the MCP endpoint is asked for on its own paths, by the board's own page: the kind is set by the path, not by a name the client gives
        # plugin Claude của quản lý ghép trên các đường dẫn của tiện ích và tự xưng tên, để /admin phân biệt được hai loại.
        # Khoá cho cổng MCP được xin trên các đường riêng của nó, từ trang của chính bảng: loại do đường dẫn quyết, không do tên client tự khai
        kind = KIND_MCP if mcp_key else (KIND_PLUGIN if is_plugin_client(user_agent) else KIND_EXTENSION) if extension else ""
        key = self.bearer() if extension else self.pending_key()
        if self.path in ("/tv/request-code", "/ext/request-code", "/mcp/request-code"):
            # only a menu bar client's code may later be approved by its owner on /mini/pair; a TV's or an extension's needs an admin
            # chỉ mã của ứng dụng thanh menu mới được chủ máy tự duyệt ở /mini/pair; mã của TV hay tiện ích cần quản trị duyệt
            result = TV_PAIRING.request_code(key, ip, user_agent, now, kind, menubar=not extension and is_menubar_client(user_agent))
            if not result:
                AUDIT_LOG.write(action="tv-refused", **({"kind": kind} if kind else {}), clientIp=ip, device=user_agent)
                return self.reply(429, {"error": tx("Too many screens are waiting, try again later.")})
            AUDIT_LOG.write(action="tv-request-code", **({"kind": kind} if kind else {}), clientIp=ip, device=user_agent)
            if extension:
                return self.reply(200, {"code": result[0], "key": result[1], "secondsLeft": TV_CODE_SECONDS})
            b = json.dumps({"code": result[0], "secondsLeft": TV_CODE_SECONDS}).encode()
            return self.reply_page(200, b, cookie="tv-pending=%s; Path=/tv; Max-Age=%d; HttpOnly; SameSite=Strict" % (result[1], TV_CODE_SECONDS + 300),
                                  content_type="application/json; charset=utf-8")
        r = TV_PAIRING.poll(key, now) if key else "expired"
        if isinstance(r, str):
            return self.reply(200, {"status": r})
        try:
            tv_id, token = TV.create(r, now)
        except ValueError as e:
            AUDIT_LOG.write(action="error", error=str(e)[:200], clientIp=ip)
            return self.reply(200, {"status": "expired"})
        AUDIT_LOG.write(action="tv-joined", tv=r["name"], id=tv_id, **({"kind": r["kind"]} if r.get("kind") else {}), clientIp=ip, approvedBy=r["approvedBy"])
        sys.stderr.write("screen %s joined from %s, approved by %s\n" % (r["name"], ip, r["approvedBy"]))
        if extension:
            return self.reply(200, {"status": "done", "name": r["name"], "token": token, **({"scope": TV.d[tv_id]["scope"]} if r.get("kind") == KIND_MCP else {})})
        b = json.dumps({"status": "done", "name": r["name"]}, ensure_ascii=False).encode()
        return self.reply_page(200, b, cookie="session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (token, TV_SESSION_SECONDS),
                              content_type="application/json; charset=utf-8")

    def mcp_post(self, y: "RequestCtx") -> None:
        """One MCP message from an AI tool that holds a key an admin approved. Read-only: the tool gets the wall view as text, cut down to what
        its key may read. board/mcp.py speaks the protocol; this method counts, logs and sends. The gate has already checked the key and the origin.
        Một thông điệp MCP từ công cụ AI cầm khoá đã được quản trị duyệt. Chỉ đọc: công cụ nhận phần treo tường dạng chữ, rút gọn theo thứ
        khoá của nó được đọc. board/mcp.py lo phần giao thức; hàm này đếm, ghi nhật ký và gửi. Cổng đã kiểm khoá và nguồn gửi."""
        token, ip = self.bearer(), self.client_ip()
        key, key_id = TV.find(token, y.now, side=KIND_MCP), TV.id_of(token)
        if not key:
            # revoked between the gate and here
            # bị thu hồi giữa lúc qua cổng và lúc tới đây
            return self.reply(401, {"error": tx("Not paired")}, quiet=True)
        if not MCP_LIMIT.allow(key_id, y.now):
            if MCP_LIMIT.first_refusal(key_id, y.now):
                AUDIT_LOG.write(action="mcp-rate-limited", tv=key["name"], id=key_id, clientIp=ip)
            return self.reply(429, {"error": tx("This key has asked too often. Try again in a few minutes.")}, headers=(("Retry-After", str(MCP_LIMIT.retry_after(key_id, y.now))),))
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > mcp.MAX_REQUEST_BYTES:
            return self.reply(413, {"error": tx("Too large")})
        raw = self.rfile.read(n)
        TV.touch(token, ip, y.now, side=KIND_MCP)
        TV_STATUS.mark_seen(key_id, "", y.now)
        r = mcp.handle(raw, {k.lower(): v for k, v in self.headers.items()}, key.get("scope", ""), lambda: role_view(WALL, y.now), y.now * 1000)
        # an older tool names itself once, in initialize: remember the name for its later calls. For the log only, it can be faked
        # công cụ đời cũ chỉ xưng tên một lần, trong initialize: nhớ tên cho các lần gọi sau. Chỉ để ghi nhật ký, giả được
        if r.client:
            MCP_CLIENTS[key_id] = r.client
        if r.method == "tools/call":
            client = MCP_CLIENTS.get(key_id) or re.sub(r"[^A-Za-z0-9 ._+/-]", "", self.headers.get("User-Agent", ""))[:60]
            AUDIT_LOG.write(action=AUDIT_LOG.MCP_CALL, tv=key["name"], id=key_id, tool=r.tool, ok=bool(r.tool), clientIp=ip, client=client, protocol=r.era)
        if r.body is None:
            self.send_response(r.status)
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        # a 404 here answers a method this server does not offer: the tool is paired, it is not probing
        # 404 ở đây là trả lời cho một phương thức máy chủ không có: công cụ đã ghép, không phải đang dò
        self.reply(r.status, r.body, quiet=True)

    def bot_telegram(self, y: "RequestCtx") -> None:
        """One message the Telegram bot process on this machine got from Telegram. The answer says what to send back, or nothing.
        board/chat.py decides: whether the chat is approved, what it may read, how often it may ask. The gate has already checked the key.
        Một tin nhắn tiến trình bot Telegram trên máy này nhận từ Telegram. Câu trả lời cho biết gửi lại gì, hoặc không gửi gì.
        board/chat.py quyết định: chat đã được duyệt chưa, được đọc gì, được hỏi bao nhiêu lần. Cổng đã kiểm khoá."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > chat.MAX_MESSAGE_BYTES:
            return self.reply(413, {"error": tx("Too large")})
        try:
            msg = json.loads(self.rfile.read(n), parse_constant=refuse_constant)
            if not isinstance(msg, dict):
                raise ValueError
        except ValueError:
            return self.reply(400, {"error": tx("Not JSON")})
        self.reply(200, chat.on_call(msg, y.now), quiet=True)

    def get_mcp_connect(self, y: "RequestCtx") -> None:
        self.reply_page(200, page_mcp_connect())

    def get_mcp_connect_js(self, y: "RequestCtx") -> None:
        self.reply_page(200, js_mcp_connect(), content_type="text/javascript; charset=utf-8", cache_control="no-cache")

    def mcp_not_allowed(self, y: "RequestCtx") -> None:
        """GET or DELETE on the MCP endpoint: this server opens no stream and keeps no session, which the protocol answers with 405.
        GET hoặc DELETE ở cổng MCP: máy chủ này không mở luồng và không giữ phiên, giao thức quy định trả 405."""
        self.reply(405, {"error": "Use POST"}, headers=(("Allow", "POST"),))

    def get_no_oauth(self, y: "RequestCtx") -> None:
        """Some AI tools look for OAuth settings after a 401 from the MCP endpoint. There are none: a plain 404, not counted as probing,
        so a tool holding a wrong key cannot get its whole office blocked.
        Vài công cụ AI đi tìm cấu hình OAuth sau khi nhận 401 từ cổng MCP. Không có cấu hình nào: trả 404 thường, không tính là dò,
        để một công cụ cầm khoá sai không làm cả văn phòng bị chặn."""
        self.reply(404, {"error": "This server has no OAuth: the MCP endpoint takes a key from the board in the Authorization header."}, quiet=True)

    def admin_action(self, y: "RequestCtx") -> None:
        """Manager actions on the board: name locations, load the Team plan CSV, mark the sales team. The gate has already checked login, origin and role.
        Việc của quản lý trên bảng: đặt tên địa điểm, nạp CSV gói Team, đánh dấu đội sale. Cổng đã kiểm đăng nhập, nguồn gửi và vai."""
        user, cookie = y.user, y.cookie
        audit = lambda **fields: self.audit_request(y, **fields)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > (TEAM_CSV_MAX_BYTES if self.path == "/team-csv" else 4096):
            return self.reply(413, {"error": tx("Too large")})
        try:
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.reply(400, {"error": tx("Not JSON")})
        if self.path == "/admin/confirm":
            now, ip = time.time(), self.client_ip()
            # only a logged-in admin gets here, and wrong tries end the session: a stranger's wrong logins must not lock this
            # chỉ quản trị đã đăng nhập mới tới đây, và nhập sai nhiều sẽ kết thúc phiên: người lạ nhập sai không được khoá bước này
            result = SESSIONS.confirm(cookie, str(body.get("code") or ""), ip, now)
            audit(action="confirmed" if result == "ok" else "confirm-failed", result=result)
            if result == "ok":
                return self.reply(200, {"ok": True})
            if result == "cancelled":
                return self.reply(401, {"error": tx("Too many wrong tries, the session has ended")})
            return self.reply(403, {"error": tx("Wrong or already used code. Wait for a new code and enter it again.")})
        if POST_ROUTES[self.path].require_otp and not SESSIONS.is_confirmed(cookie, time.time()):
            audit(action="confirm-required")
            return self.reply(403, {"error": tx("Enter the OTP code again"), "needsConfirm": True})
        extra = {}
        try:
            if self.path == "/admin/accounts":
                details, extra = manage_account(body, user, SESSIONS.token_of(cookie))
            elif self.path.startswith("/admin/tv-"):
                details, extra = tv_action(self.path, body, user)
            elif self.path == "/admin/sessions":
                account_name = str(body.get("name") or "")
                details = {"action": "end-session", "accountName": account_name, "sessionCount": SESSIONS.end_sessions_of(account_name, SESSIONS.token_of(cookie)),
                           "menuBarRevoked": len(TV.revoke_owner(account_name))}
            elif self.path == "/locations":
                outcome = LOCATIONS.mutate(lambda d: edit_location(d, body))
                details = outcome or {"action": "assign", **{k: body.get(k) for k in ("ip", "id", "name", "lat", "lon", "isHq") if k in body}}
            elif self.path == "/team-sale":
                email = str(body.get("email") or "").strip().lower()[:120]
                if "@" not in email:
                    raise ValueError(tx("invalid email"))
                def set_sales(d):
                    rest = set(d.get("salesTeam", [])) - {email}
                    d["salesTeam"] = sorted(rest | {email}) if body.get("isSales") is True else sorted(rest)
                LOCATIONS.mutate(set_sales)
                details = {"action": "set-sales", "email": email, "isSales": body.get("isSales") is True}
            elif self.path == "/team-csv":
                people = parse_team_csv(str(body.get("csv") or ""))
                date_from, date_to = (str(body.get(k) or "") for k in ("dateFrom", "dateTo"))
                if not all(re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", x) for x in (date_from, date_to)):
                    raise ValueError(tx("invalid date"))
                TEAM.mutate(lambda d: d.update(updatedAt=int(time.time() * 1000), dateFrom=date_from, dateTo=date_to, people=people))
                details = {"action": "csv", "dateFrom": date_from, "dateTo": date_to, "personCount": len(people), "byte": n}
            else:
                raise ValueError(tx("no such action"))
        except (ValueError, TypeError, csv.Error) as e:
            audit(action="error", error=str(e)[:200])
            return self.reply(400, {"error": str(e)[:200] or tx("invalid data")})
        sys.stderr.write("%s: changed by %s\n" % (self.path, user))
        audit(**details)
        return self.reply(200, {"ok": True, **extra})

    def login(self, y: "RequestCtx") -> None:
        now, ip = time.time(), self.client_ip()
        # the browser does not tell a web page the computer name or internal IP; only the device/browser type is there to tell them apart
        # trình duyệt không cho trang web biết tên máy hay IP nội bộ; chỉ có loại máy/trình duyệt để phân biệt thêm
        user_agent = re.sub(r"[^\x20-\x7e]", "", self.headers.get("User-Agent", ""))[:120]
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        form = parse_qs(self.rfile.read(min(max(n, 0), 1024)).decode("utf-8", "replace"))
        # the time and the limit are checked after the body arrives, however long the client took to send it
        # thời điểm và giới hạn được xét sau khi đã nhận thân yêu cầu, dù máy gửi có gửi chậm bao lâu
        now = time.time()
        account_name, token = SESSIONS.login(form.get("account", [""])[0], form.get("code", [""])[0].strip(), ip, now)
        if account_name == BLOCKED:
            return self.reply_page(429, page_login(tx("Too many wrong tries. Try again in 15 minutes.")))
        if not account_name:
            sys.stderr.write("failed login from %s · %s\n" % (ip, user_agent))
            AUDIT_LOG.write(action="login-failed", clientIp=ip, device=user_agent)
            return self.reply_page(401, page_login(tx("Wrong name or code, or the code was already used. Wait for a new code and enter it again.")))
        role = ACCOUNTS.role_of(account_name)
        ACCOUNTS.mark_logged_in(account_name)
        sys.stderr.write("login: %s (%s) from %s · %s\n" % (account_name, role, ip, user_agent))
        AUDIT_LOG.write(action="login", actor=account_name, role=role, clientIp=ip, device=user_agent)
        self.redirect_home("session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (token, session_lifetime(role)))

    def login_telegram(self, y: "RequestCtx") -> None:
        """Telegram's button sends the browser here with the signed fields. Only an account linked before can log in this way.
        Nút của Telegram đưa trình duyệt tới đây kèm các trường đã ký. Chỉ tài khoản đã liên kết trước mới đăng nhập được kiểu này."""
        now, ip = time.time(), self.client_ip()
        user_agent = re.sub(r"[^\x20-\x7e]", "", self.headers.get("User-Agent", ""))[:120]
        if not telegram_enabled():
            return self.reply(404, {"error": tx("Not found")})
        if SESSIONS.is_blocked(ip, now):
            return self.reply_page(429, page_login(tx("Too many wrong tries. Try again in 15 minutes.")))
        who = TELEGRAM.verify(parse_qs(urlparse(self.path).query, keep_blank_values=True), now)
        if not who:
            SESSIONS.note_failure(ip, now)
            AUDIT_LOG.write(action="login-failed", method="telegram", clientIp=ip, device=user_agent)
            return self.reply_page(401, page_login(tx("The Telegram login could not be checked or has expired. Press the Telegram button again.")))
        account_name, token = SESSIONS.login_telegram(who["id"], ip, now)
        if account_name == BLOCKED:
            return self.reply_page(429, page_login(tx("Too many wrong tries. Try again in 15 minutes.")))
        if not account_name:
            AUDIT_LOG.write(action="login-failed", method="telegram", reason="not-linked", clientIp=ip, device=user_agent)
            return self.reply_page(401, page_login(tx("This Telegram account is not linked yet. Log in with your name and code, then link Telegram from the detail board.")))
        role = ACCOUNTS.role_of(account_name)
        ACCOUNTS.mark_logged_in(account_name)
        sys.stderr.write("login: %s (%s) with Telegram from %s · %s\n" % (account_name, role, ip, user_agent))
        AUDIT_LOG.write(action="login", method="telegram", actor=account_name, role=role, clientIp=ip, device=user_agent)
        self.redirect_home("session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (token, session_lifetime(role)))

    def telegram_go(self, y: "RequestCtx") -> None:
        """The Telegram button: send the browser to Telegram's login page, which comes back to /telegram/back with the signed login.
        Nút Telegram: đưa trình duyệt sang trang đăng nhập của Telegram, trang đó quay về /telegram/back kèm phần đăng nhập đã ký."""
        if not telegram_bot_id():
            return self.reply(404, {"error": tx("Not found")})
        # Telegram checks the origin against the bot's domain (/setdomain), so a made-up Host only gets refused there
        # Telegram so nguồn với tên miền của bot (/setdomain), nên Host giả chỉ bị Telegram từ chối
        scheme = "https" if self.via_proxy() and self.headers.get("X-Forwarded-Proto", "") == "https" else "http"
        host = re.sub(r"[^A-Za-z0-9.:\[\]-]", "", self.headers.get("Host", ""))[:255]
        origin = "%s://%s" % (scheme, host)
        n = parse_qs(urlparse(self.path).query).get("n", [""])[0]
        back = origin + "/telegram/back" + ("?n=" + n if re.fullmatch(r"[A-Za-z0-9_-]{10,40}", n) else "")
        dest = "https://oauth.telegram.org/auth?bot_id=%s&origin=%s&return_to=%s" % (telegram_bot_id(), quote(origin, safe=""), quote(back, safe=""))
        self.redirect_home(dest=dest)

    def telegram_back(self, y: "RequestCtx") -> None:
        if not telegram_enabled():
            return self.reply(404, {"error": tx("Not found")})
        self.reply_page(200, page_telegram_back())

    def get_telegram(self, y: "RequestCtx") -> None:
        if not telegram_enabled():
            return self.redirect_home()
        # ?done=unlinked: back here after unlinking, so a reload does not post the form again
        # ?done=unlinked: quay lại đây sau khi gỡ, để tải lại trang không gửi lại biểu mẫu
        done = parse_qs(urlparse(self.path).query).get("done", [""])[0]
        notice = tx("Telegram is unlinked. From now on, log in with your name and code, or link again below.") if done == "unlinked" else ""
        self.reply_page(200, page_telegram(y.user, notice=notice))

    def telegram_code(self, y: "RequestCtx"):
        """Check the 6-digit code posted from the Telegram page; replies and returns False when it is wrong.
        Kiểm mã 6 số gửi từ trang Telegram; trả lời và trả False khi sai."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        code = parse_qs(self.rfile.read(min(max(n, 0), 256)).decode("utf-8", "replace")).get("code", [""])[0].strip()
        if SESSIONS.is_blocked(self.client_ip(), y.now):
            self.reply_page(429, page_telegram(y.user, error=tx("Too many wrong tries. Try again in 15 minutes.")))
            return False
        result = SESSIONS.confirm(y.cookie, code, self.client_ip(), y.now)
        if result == "ok":
            return True
        self.audit_request(y, action="confirm-failed", result=result)
        if result == "cancelled":
            self.redirect_home("session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
        else:
            self.reply_page(403, page_telegram(y.user, error=tx("Wrong or already used code. Wait for a new code and enter it again.")))
        return False

    def telegram_start(self, y: "RequestCtx") -> None:
        if not telegram_enabled():
            return self.redirect_home()
        if self.telegram_code(y):
            self.reply_page(200, page_telegram(y.user, link_code=TELEGRAM.start_link(SESSIONS.token_of(y.cookie), y.now)))

    def telegram_link(self, y: "RequestCtx") -> None:
        if not telegram_enabled():
            return self.redirect_home()
        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        if not TELEGRAM.take_link(SESSIONS.token_of(y.cookie), query.get("n", [""])[0], y.now):
            self.audit_request(y, action="telegram-link-failed", reason="no-code")
            return self.reply_page(403, page_telegram(y.user, error=tx("This link step has expired. Enter the code again.")))
        who = TELEGRAM.verify(query, y.now)
        if not who:
            SESSIONS.note_failure(self.client_ip(), y.now)
            self.audit_request(y, action="telegram-link-failed", reason="signature")
            return self.reply_page(403, page_telegram(y.user, error=tx("The Telegram login could not be checked or has expired. Press the Telegram button again.")))
        try:
            ACCOUNTS.link_telegram(y.user, who["id"], who["username"])
        except ValueError as e:
            self.audit_request(y, action="telegram-link-failed", reason=str(e)[:100])
            return self.reply_page(409, page_telegram(y.user, error=str(e)))
        self.audit_request(y, action="telegram-link", accountName=y.user, telegramUser=who["username"])
        self.reply_page(200, page_telegram(y.user, notice=tx("Telegram is linked. Next time, press the Telegram button on the login page."), go_home=True))

    def telegram_unlink(self, y: "RequestCtx") -> None:
        if not telegram_enabled():
            return self.redirect_home()
        if self.telegram_code(y):
            ACCOUNTS.unlink_telegram(y.user)
            self.audit_request(y, action="telegram-unlink", accountName=y.user)
            self.redirect_home(dest="/telegram?done=unlinked")

    def from_this_machine(self) -> bool:
        """A program on the server itself calling the webhook's port directly, not a request a proxy passed on. Caddy and nginx connect
        from this machine too, but they add forwarding headers that the caller cannot take off; a browser adds Origin.
        Một chương trình trên chính máy chủ gọi thẳng cổng của webhook, không phải yêu cầu do proxy chuyển tới. Caddy và nginx cũng kết nối
        từ máy này, nhưng chúng gắn các header chuyển tiếp mà bên gọi không gỡ được; trình duyệt thì gắn Origin."""
        return self.client_address[0] in ("127.0.0.1", "::1") and not any(self.headers.get(h) is not None for h in FORWARDED_HEADERS)

    def via_proxy(self) -> bool:
        """A request forwarded by Caddy/nginx on the server itself: only then are the X-Forwarded-* headers trusted.
        Someone calling the webhook port directly from another machine cannot fake the IP (the wrong-login lock counts by IP).
        Yêu cầu do Caddy/nginx trên chính máy chủ chuyển tới: chỉ khi đó mới tin các header X-Forwarded-*.
        Ai gọi thẳng cổng webhook từ máy khác thì không giả được IP (khoá đăng nhập sai tính theo IP)."""
        return settings.TRUST_PROXY and self.client_address[0] in ("127.0.0.1", "::1")

    def client_ip(self) -> str:
        if self.via_proxy():
            # Caddy appends the IP it sees at the end: the first part is what the sending device claims, do not trust it
            # Caddy ghi IP nó thấy vào cuối: phần đầu là thứ máy gửi tự khai, không tin
            xff = self.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
            if xff:
                return xff[:45]
        return self.client_address[0]

    def log_message(self, fmt, *args):
        # only log errors; do not log every send
        # chỉ ghi lỗi; không ghi từng lần gửi
        if len(args) > 1 and str(args[1])[:1] in "45":
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


class LimitedServer(ThreadingHTTPServer):
    """One thread per connection, with a ceiling: new connections past a limit are closed, and any connection is closed
    at the deadline, so slow senders cannot hold threads and memory for ever.
    Mỗi kết nối một luồng nhưng có trần: kết nối mới vượt giới hạn bị đóng, và mọi kết nối bị đóng khi hết hạn,
    để máy gửi chậm không giữ luồng và bộ nhớ mãi được."""

    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, handler):
        self.open_connections = {}
        self.open_lock = threading.Lock()
        super().__init__(address, handler)
        threading.Thread(target=self.close_overdue, daemon=True).start()

    def verify_request(self, request, client_address) -> bool:
        ip = client_address[0]
        with self.open_lock:
            same_ip = sum(1 for other, _ in self.open_connections.values() if other == ip)
            # behind a local proxy every connection has the proxy's address, so only the total applies there
            # sau proxy trên máy, mọi kết nối đều mang địa chỉ của proxy, nên chỉ áp dụng giới hạn tổng
            behind_proxy = settings.TRUST_PROXY and ip in ("127.0.0.1", "::1")
            if len(self.open_connections) >= MAX_CONNECTIONS or (not behind_proxy and same_ip >= MAX_CONNECTIONS_PER_IP):
                return False
            self.open_connections[request] = (ip, time.monotonic())
        return True

    def shutdown_request(self, request) -> None:
        with self.open_lock:
            self.open_connections.pop(request, None)
        super().shutdown_request(request)

    def close_overdue(self) -> None:
        while True:
            time.sleep(5)
            cutoff = time.monotonic() - CONNECTION_DEADLINE_SECONDS
            with self.open_lock:
                overdue = [c for c, (_, started) in self.open_connections.items() if started < cutoff]
            for connection in overdue:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


PERM_PUBLIC, PERM_INGEST_KEY, PERM_LOGIN, PERM_NOT_WALL, PERM_ADMIN = "public", "ingest-key", "login", "not-wall", "admin"
# a paired device key in the Authorization header (the browser extension); always the wall role
# khoá thiết bị đã ghép trong header Authorization (tiện ích trình duyệt); luôn là vai treo tường
PERM_DEVICE_KEY = "device-key"
# a key for the MCP endpoint in the Authorization header: only that kind of key, and it opens nothing else
# khoá cho cổng MCP trong header Authorization: chỉ loại khoá đó, và nó không mở được gì khác
PERM_MCP_KEY = "mcp-key"
# the key of the Telegram bot process, from this machine only: see Handler.from_this_machine
# khoá của tiến trình bot Telegram, chỉ từ chính máy này: xem Handler.from_this_machine
PERM_BOT_KEY = "bot-key"
# a session of the board's window inside Telegram in the Authorization header, given on /tg/session: see board/tgapp.py
# phiên của khung bảng bên trong Telegram trong header Authorization, cấp ở /tg/session: xem board/tgapp.py
PERM_TG_SESSION = "tg-session"
# a request that carries one of these did not come straight from a program on this machine
# yêu cầu mang một trong các header này thì không tới thẳng từ một chương trình trên máy này
FORWARDED_HEADERS = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Real-IP", "Forwarded", "Via", "Origin")
# how often each MCP key may ask, and the name each AI tool last gave for itself
# mỗi khoá MCP được hỏi bao nhiêu lần, và cái tên mỗi công cụ AI tự xưng gần nhất
MCP_LIMIT = CallLimit(MCP_CALLS_PER_KEY, MCP_CALLS_WINDOW_SECONDS)
MCP_CLIENTS = {}
# where an AI tool looks for OAuth settings after a 401: this server has none
# nơi công cụ AI tìm cấu hình OAuth sau khi nhận 401: máy chủ này không có
NO_OAUTH_PATHS = ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-authorization-server",
                  "/.well-known/oauth-authorization-server/mcp", "/.well-known/openid-configuration", "/.well-known/openid-configuration/mcp")
# the paths a paired extension asks with its key; the probing guard lets them through
# các đường tiện ích đã ghép hỏi bằng khoá của nó; lớp chặn dò cho đi qua
EXT_KEY_PATHS = ("/ext/state", "/ext/data", "/ext/mini")
ORIGIN_IF_PRESENT, ORIGIN_REQUIRED, ORIGIN_EXTENSION = "if-present", "required", "extension"
# a permission that is not here has no role check
# quyền nào không có ở đây thì không xét vai
ROLES_ALLOWED = {PERM_NOT_WALL: (ADMIN, VIEWER), PERM_ADMIN: (ADMIN,)}


class RequestCtx(NamedTuple):
    user: Optional[str]
    role: Optional[str]
    cookie: str
    now: float


class Route(NamedTuple):
    handler: Callable
    permission: str
    # page: not logged in shows the login page, a wrong role goes to the home page; the rest return 401/403 JSON
    # trang: chưa đăng nhập thì hiện trang đăng nhập, sai vai thì về trang chủ; còn lại trả 401/403 JSON
    is_page: bool = False
    # GET: also accepted when there is a ?...
    # GET: nhận cả khi có ?...
    allow_query: bool = False
    origin_policy: Optional[str] = None
    require_otp: bool = False
    # part of the MCP endpoint: gone (404) when MCP=0
    # thuộc cổng MCP: biến mất (404) khi MCP=0
    mcp: bool = False
    # part of asking the board from Telegram: gone (404) unless TELEGRAM_ASK=1
    # thuộc việc hỏi bảng qua Telegram: biến mất (404) trừ khi TELEGRAM_ASK=1
    telegram_ask: bool = False
    # part of the board's window inside Telegram: gone (404) unless TELEGRAM_APP=1
    # thuộc khung bảng bên trong Telegram: biến mất (404) trừ khi TELEGRAM_APP=1
    telegram_app: bool = False


# Every path of the server is listed here; one that is not here is 404. Add a new path to the permission table in test_webhook.py too.
# Mọi đường dẫn của máy chủ nằm ở đây, không có ở đây là 404. Thêm đường mới thì thêm vào bảng quyền trong test_webhook.py.
GET_ROUTES = {
    "/": Route(Handler.get_home, PERM_PUBLIC, allow_query=True),
    "/robots.txt": Route(Handler.get_robots, PERM_PUBLIC),
    "/health": Route(Handler.get_health, PERM_PUBLIC),
    "/login.js": Route(Handler.get_login_js, PERM_PUBLIC),
    "/tv": Route(Handler.get_tv, PERM_PUBLIC),
    "/tv.js": Route(Handler.get_tv_js, PERM_PUBLIC),
    "/tv-qr.js": Route(Handler.get_tv_qr, PERM_PUBLIC),
    "/tv/install-windows.bat": Route(Handler.get_tv_installer, PERM_PUBLIC),
    "/tv/install-mac.zip": Route(Handler.get_tv_installer, PERM_PUBLIC),
    "/data": Route(Handler.get_data, PERM_LOGIN, allow_query=True),
    "/mini": Route(Handler.get_mini, PERM_PUBLIC, allow_query=True),
    "/mini/state": Route(Handler.get_mini_state, PERM_LOGIN),
    "/ext/state": Route(Handler.get_ext_state, PERM_DEVICE_KEY),
    "/ext/data": Route(Handler.get_ext_data, PERM_DEVICE_KEY),
    "/ext/mini": Route(Handler.get_ext_mini, PERM_DEVICE_KEY, allow_query=True),
    "/mini/pair": Route(Handler.get_mini_pair, PERM_PUBLIC),
    "/mini/logo-black.png": Route(Handler.get_mini_logo, PERM_PUBLIC),
    "/mini/logo-white.png": Route(Handler.get_mini_logo, PERM_PUBLIC),
    "/mini-pair.js": Route(Handler.get_mini_pair_js, PERM_PUBLIC),
    "/menubar/install-mac.zip": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/menubar/install-windows.zip": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/menubar/install-windows.msi": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/menubar/install-mac.dmg": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/menubar/extension.zip": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/menubar/install-ubuntu.deb": Route(Handler.get_menubar_installer, PERM_ADMIN),
    "/history": Route(Handler.get_history, PERM_LOGIN),
    # the text board has each person's email and IP: the wall display must not open it
    # bảng chữ có email và IP từng người: màn hình treo tường không được mở
    "/board": Route(Handler.get_board, PERM_NOT_WALL, is_page=True),
    "/admin": Route(Handler.get_admin, PERM_ADMIN, is_page=True, allow_query=True),
    "/login/telegram": Route(Handler.login_telegram, PERM_PUBLIC, allow_query=True),
    "/telegram/go": Route(Handler.telegram_go, PERM_PUBLIC, allow_query=True),
    "/telegram/back": Route(Handler.telegram_back, PERM_PUBLIC, allow_query=True),
    "/telegram": Route(Handler.get_telegram, PERM_NOT_WALL, is_page=True, allow_query=True),
    "/telegram/link": Route(Handler.telegram_link, PERM_NOT_WALL, is_page=True, allow_query=True),
    "/admin/data": Route(Handler.get_admin_data, PERM_ADMIN, allow_query=True),
    # the board's window inside Telegram: a page with no numbers and its files, all under /tg/ so a proxy can let just that part through;
    # the numbers come only with a session that /tg/session gives for Telegram's signed fields
    # khung bảng bên trong Telegram: một trang không có số liệu và các file của nó, đều nằm dưới /tg/ để proxy có thể chỉ cho riêng phần đó đi qua;
    # số liệu chỉ có khi cầm phiên mà /tg/session cấp cho các trường Telegram đã ký
    "/tg/app": Route(Handler.get_tg_app, PERM_PUBLIC, allow_query=True, telegram_app=True),
    "/tg/app.js": Route(Handler.get_tg_file, PERM_PUBLIC, allow_query=True, telegram_app=True),
    "/tg/mini.js": Route(Handler.get_tg_file, PERM_PUBLIC, allow_query=True, telegram_app=True),
    "/tg/mini.css": Route(Handler.get_tg_file, PERM_PUBLIC, allow_query=True, telegram_app=True),
    "/tg/data": Route(Handler.get_tg_data, PERM_TG_SESSION, telegram_app=True),
    # the MCP endpoint takes POST only; do_DELETE comes here too
    # cổng MCP chỉ nhận POST; do_DELETE cũng về đây
    "/mcp": Route(Handler.mcp_not_allowed, PERM_MCP_KEY, mcp=True),
    # where a person asks for a key for their own AI tool; nothing is given out until an admin approves the code the page shows
    # nơi một người xin khoá cho công cụ AI của chính mình; không cấp gì cho tới khi quản trị duyệt mã trang hiện ra
    "/mcp/connect": Route(Handler.get_mcp_connect, PERM_PUBLIC, mcp=True),
    "/mcp-connect.js": Route(Handler.get_mcp_connect_js, PERM_PUBLIC, mcp=True),
    **{path: Route(Handler.get_no_oauth, PERM_PUBLIC, mcp=True) for path in NO_OAUTH_PATHS},
}
STATIC_ROUTE = Route(Handler.get_static, PERM_LOGIN)
RELEASES_ROUTE = Route(Handler.get_release, PERM_INGEST_KEY)
POST_ROUTES = {
    "/login": Route(Handler.login, PERM_PUBLIC),
    "/logout": Route(Handler.logout, PERM_PUBLIC, origin_policy=ORIGIN_IF_PRESENT),
    "/telegram/start": Route(Handler.telegram_start, PERM_NOT_WALL, origin_policy=ORIGIN_IF_PRESENT),
    "/telegram/unlink": Route(Handler.telegram_unlink, PERM_NOT_WALL, origin_policy=ORIGIN_IF_PRESENT),
    "/tv/request-code": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_IF_PRESENT),
    "/tv/poll": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_IF_PRESENT),
    # the extension sends Origin chrome-extension://... and no cookie; a foreign web page is refused like on /tv/...
    # tiện ích gửi Origin chrome-extension://... và không có cookie; trang web lạ bị từ chối như với /tv/...
    "/ext/request-code": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_EXTENSION),
    "/ext/poll": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_EXTENSION),
    # the extension's own key in the Authorization header revokes only that key
    # khoá của chính tiện ích trong header Authorization chỉ thu hồi khoá đó
    "/ext/unpair": Route(Handler.ext_unpair, PERM_DEVICE_KEY, origin_policy=ORIGIN_EXTENSION),
    "/ingest": Route(Handler.ingest, PERM_INGEST_KEY),
    # an AI tool with a key an admin approved asks the board's numbers; read-only
    # công cụ AI có khoá đã được quản trị duyệt hỏi số liệu của bảng; chỉ đọc
    "/mcp": Route(Handler.mcp_post, PERM_MCP_KEY, mcp=True),
    # the board's own page asks for a code and then for the key; a page on another site, or a request with no Origin, is refused
    # trang của chính bảng xin mã rồi xin khoá; trang ở nơi khác, hoặc yêu cầu không có Origin, bị từ chối
    "/mcp/request-code": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_REQUIRED, mcp=True),
    "/mcp/poll": Route(Handler.tv_pair, PERM_PUBLIC, origin_policy=ORIGIN_REQUIRED, mcp=True),
    # the Telegram bot process on this machine hands over each message it gets, and is told what to answer
    # tiến trình bot Telegram trên máy này đưa từng tin nó nhận được, và được cho biết phải trả lời gì
    "/bot/telegram": Route(Handler.bot_telegram, PERM_BOT_KEY, telegram_ask=True),
    # the window inside Telegram trades Telegram's signed fields for a session, and can disconnect its own chat
    # khung bên trong Telegram đổi các trường Telegram đã ký lấy một phiên, và có thể ngắt chính chat của nó
    "/tg/session": Route(Handler.tg_session, PERM_PUBLIC, origin_policy=ORIGIN_IF_PRESENT, telegram_app=True),
    "/tg/unpair": Route(Handler.tg_unpair, PERM_TG_SESSION, telegram_app=True),
    "/mini/handoff": Route(Handler.mini_action, PERM_LOGIN, origin_policy=ORIGIN_IF_PRESENT),
    "/mini/pair": Route(Handler.mini_self_pair, PERM_PUBLIC, origin_policy=ORIGIN_REQUIRED),
    "/mini/settings": Route(Handler.mini_action, PERM_LOGIN, origin_policy=ORIGIN_REQUIRED),
    "/mini/unpair": Route(Handler.mini_action, PERM_LOGIN, origin_policy=ORIGIN_REQUIRED),
    "/locations": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED),
    "/team-csv": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED),
    "/team-sale": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED),
    "/admin/confirm": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED),
    "/admin/accounts": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/sessions": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/tv-view": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/tv-approve": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/tv-revoke": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/tv-rename": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    "/admin/tv-app": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED, require_otp=True),
    # reloading a screen changes no permission or data, so it does not require re-entering the OTP
    # tải lại màn hình không đổi quyền hay dữ liệu gì, nên không bắt nhập lại OTP
    "/admin/tv-reload": Route(Handler.admin_action, PERM_ADMIN, origin_policy=ORIGIN_REQUIRED),
}


def find_get_route(path: str) -> Optional[Route]:
    base_path = path.split("?", 1)[0]
    if base_path.startswith("/static/"):
        return STATIC_ROUTE
    if base_path.startswith("/releases/"):
        return RELEASES_ROUTE
    d = GET_ROUTES.get(base_path)
    return d if d and (base_path == path or d.allow_query) else None


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export-json":
        for rel in db.export_json(sys.argv[2]):
            print(rel)
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--forget-device":
        with db.data_db().tx() as c:
            forgotten = c.execute("DELETE FROM identities WHERE device = ?", (sys.argv[2],)).rowcount
        print("forgot %s" % sys.argv[2] if forgotten else "no such device: %s" % sys.argv[2])
        sys.exit(0 if forgotten else 1)
    if len(sys.argv) == 3 and sys.argv[1] == "--forget-usage":
        forgotten = DAILY.forget(sys.argv[2])
        print("deleted %d daily rows of %s" % (forgotten, sys.argv[2]) if forgotten else "no daily rows for: %s" % sys.argv[2])
        sys.exit(0 if forgotten else 1)
    if not settings.INGEST_KEY:
        sys.exit("INGEST_KEY is required. See README.md.")
    # data files readable only by the account running the webhook
    # file dữ liệu chỉ tài khoản chạy webhook đọc được
    os.umask(0o077)
    print("AI Worker webhook listening on %s:%d, data in %s (SQLite %s)" % (BIND_ADDR, PORT, DATA_DIR, sqlite3.sqlite_version), flush=True)
    imported_count = ACCOUNTS.import_from_env()
    if imported_count:
        print("Imported %d accounts from the config file" % imported_count, flush=True)
    count = [t["role"] for t in ACCOUNTS.list_accounts()]
    print("Accounts: %d admin, %d wall display, %d view only" % (count.count(ADMIN), count.count(WALL), count.count(VIEWER)), flush=True)
    if ADMIN not in count:
        print("No admin yet, nobody can open /admin: sudo bash manage-otp.sh --rescue <name>", flush=True)
    threading.Thread(target=history_loop, daemon=True).start()
    threading.Thread(target=daily_loop, daemon=True).start()
    LimitedServer((BIND_ADDR, PORT), Handler).serve_forever()
