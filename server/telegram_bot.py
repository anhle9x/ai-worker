#!/usr/bin/env python3
"""The Telegram bot process: the only part of the server that talks to the Internet, and only to Telegram. Optional and off by default;
it is for asking the board from a Telegram chat. Run: python3 telegram_bot.py, with the settings below in the environment.

It is a pipe and decides nothing. It asks Telegram for new messages (getUpdates, a call that goes out and waits, so no port is opened),
hands each one to the webhook on this same machine (POST /bot/telegram), and sends back what the webhook answers. Whether a chat is
approved, what it may read and how often it may ask is decided by the webhook. Every 20 seconds or so it also asks the webhook which chats'
menu buttons should open the board's window inside Telegram (TELEGRAM_APP=1), and sets them. This process holds the bot's token and the key of that
one path, and nothing else: no database, no OTP keys, no send key, no texts of its own. It keeps nothing on disk.

Settings (environment):
  TELEGRAM_ASK_TOKEN  the token of a bot made with @BotFather for this purpose. Not the bot used for logging in to the board.
  TELEGRAM_ASK_KEY    the key the webhook expects on /bot/telegram, the same value as in the webhook's own settings.
  PORT                the webhook's port on this machine (8788 by default); or BOARD_URL, which must be an address of this machine.
  TELEGRAM_API_URL    where Telegram's Bot API is (https://api.telegram.org by default).

  Tiến trình bot Telegram: phần duy nhất của máy chủ nói chuyện với Internet, và chỉ với Telegram. Tuỳ chọn và mặc định tắt;
  nó dùng để hỏi bảng từ một chat Telegram. Chạy: python3 telegram_bot.py, với các cấu hình dưới đây trong môi trường.

  Nó là một ống dẫn và không quyết định điều gì. Nó hỏi Telegram có tin mới không (getUpdates, một lời gọi đi ra rồi chờ, nên không mở
  cổng nào), đưa từng tin cho webhook trên chính máy này (POST /bot/telegram), rồi gửi lại thứ webhook trả lời. Chat đã được duyệt chưa,
  được đọc gì và được hỏi bao nhiêu lần là do webhook quyết định. Cứ khoảng 20 giây nó cũng hỏi webhook nút menu của chat
  nào cần mở khung bảng bên trong Telegram (TELEGRAM_APP=1), rồi đặt các nút đó. Tiến trình này cầm khoá của bot và khoá của đúng một đường đó,
  ngoài ra không có gì: không cơ sở dữ liệu, không khoá OTP, không mã gửi, không chữ nào của riêng nó. Nó không ghi gì xuống đĩa.

  Cấu hình (môi trường):
    TELEGRAM_ASK_TOKEN  khoá của một bot tạo bằng @BotFather riêng cho việc này. Không phải bot dùng để đăng nhập bảng.
    TELEGRAM_ASK_KEY    khoá mà webhook chờ ở /bot/telegram, cùng giá trị với cấu hình của chính webhook.
    PORT                cổng của webhook trên máy này (mặc định 8788); hoặc BOARD_URL, phải là một địa chỉ của chính máy này.
    TELEGRAM_API_URL    nơi đặt Bot API của Telegram (mặc định https://api.telegram.org)."""

import http.client
import json
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

TELEGRAM_API = "https://api.telegram.org"
# how long one getUpdates call waits at Telegram for a message; the answer comes at once when there is one
# một lời gọi getUpdates chờ ở Telegram bao lâu để có tin; có tin thì câu trả lời về ngay
POLL_SECONDS = 50
# a message older than this is not answered: after the server was off, yesterday's questions must not all be answered at once
# tin cũ hơn ngần này thì không trả lời: sau khi máy chủ tắt, không được trả lời dồn các câu hỏi của hôm qua
STALE_SECONDS = 120
# the webhook is told the bot is still running this often, for the Admin page
# cứ ngần này thì báo cho webhook rằng bot vẫn đang chạy, để trang Quản trị hiện
HEARTBEAT_SECONDS = 300
# the webhook is asked which menu buttons to change at most this often
# hỏi webhook cần đổi nút menu nào tối đa ngần này một lần
MENU_SECONDS = 20
# Telegram takes 1 to 4096 characters in one message
# Telegram nhận 1 tới 4096 ký tự trong một tin
TEXT_LIMIT = 4096
# an answer from Telegram or from the webhook is never near this size
# câu trả lời của Telegram hay của webhook không bao giờ gần cỡ này
MAX_REPLY_BYTES = 4 * 1024 * 1024
# the states the webhook knows (TelegramBotStatus in board/stores.py)
# các trạng thái webhook biết (TelegramBotStatus trong board/stores.py)
OK, UNAUTHORIZED, CONFLICT, UNREACHABLE = "ok", "unauthorized", "conflict", "unreachable"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


class Refused(Exception):
    """The webhook does not take this process: asking from Telegram is off there, or the key differs. Nothing to do but stop.
    Webhook không nhận tiến trình này: việc hỏi qua Telegram đang tắt ở đó, hoặc khoá khác nhau. Chỉ còn cách dừng."""


def read_json(raw: bytes) -> dict:
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


class Bot:
    def __init__(self, token: str, board_url: str, board_key: str, api_url: str = TELEGRAM_API, sleep=time.sleep, clock=time.time, log=None, poll_seconds: int = POLL_SECONDS):
        self.token = token
        self.api_base = api_url.rstrip("/") + "/bot" + token + "/"
        self.board_endpoint = board_url.rstrip("/") + "/bot/telegram"
        self.board_key = board_key
        self.sleep, self.clock, self.poll_seconds = sleep, clock, poll_seconds
        self.write = log or (lambda line: print(line, file=sys.stderr, flush=True))
        # the webhook is on this machine: never through a proxy, whatever the environment says. A proxy would get the key,
        # and the webhook refuses a call that carries a proxy's headers
        # webhook nằm trên chính máy này: không bao giờ đi qua proxy, dù môi trường có khai gì. Proxy sẽ nhận được khoá,
        # và webhook từ chối lời gọi mang header của proxy
        self.board_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # the next update to ask Telegram for; None until the first one came
        # tin kế tiếp cần hỏi Telegram; None cho tới khi nhận tin đầu tiên
        self.offset = None
        self.bot_name = ""
        self.state, self.reported_at = "", 0.0
        self.commands_set = False
        self.failures = 0
        # when the menu buttons were last asked about, and whether the webhook answered the last call at all
        # lần gần nhất hỏi về nút menu, và webhook có trả lời lời gọi gần nhất không
        self.menus_at, self.board_down = None, False

    def log(self, text: str) -> None:
        """One line for the service's log. The token is taken out if it ever got into the text; messages, names and numbers of people are never put in.
        Một dòng cho nhật ký của dịch vụ. Khoá của bot bị gỡ ra nếu có lọt vào chữ; tin nhắn, tên và số của người dùng không bao giờ được đưa vào."""
        self.write("telegram bot: " + text.replace(self.token, "***"))

    def telegram(self, method: str, payload: dict, timeout: float = 20):
        """One call of Telegram's Bot API. Returns (HTTP status, the JSON answer); status 0 when Telegram could not be reached.
        Một lời gọi Bot API của Telegram. Trả (mã HTTP, câu trả lời JSON); mã 0 khi không tới được Telegram."""
        request = urllib.request.Request(self.api_base + method, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as r:
                return r.status, read_json(r.read(MAX_REPLY_BYTES))
        except urllib.error.HTTPError as e:
            with e:
                return e.code, read_json(e.read(MAX_REPLY_BYTES))
        # the address holds the token, so only the kind of error is logged, never the error's own text
        # địa chỉ có chứa khoá của bot, nên chỉ ghi loại lỗi, không bao giờ ghi chữ của chính lỗi đó
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
            self.log("Telegram could not be reached (%s) while calling %s" % (type(e).__name__, method))
            return 0, {}

    def board(self, payload: dict):
        """One call of the webhook on this machine. Returns (HTTP status, the JSON answer); status 0 when it did not answer after three tries.
        Một lời gọi webhook trên máy này. Trả (mã HTTP, câu trả lời JSON); mã 0 khi thử ba lần mà nó không trả lời."""
        request = urllib.request.Request(self.board_endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json", "Authorization": "Bearer " + self.board_key})
        for attempt in range(3):
            if attempt:
                self.sleep(1)
            try:
                with self.board_opener.open(request, timeout=10) as r:
                    self.board_down = False
                    return r.status, read_json(r.read(MAX_REPLY_BYTES))
            except urllib.error.HTTPError as e:
                e.close()
                if e.code in (401, 404):
                    raise Refused("the board answered %d on /bot/telegram: TELEGRAM_ASK is not 1 there, or TELEGRAM_ASK_KEY is not the same on both sides" % e.code) from None
                return e.code, {}
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
                continue
        self.log("the board did not answer on this machine")
        self.board_down = True
        return 0, {}

    def note(self, state: str) -> None:
        """Tell the webhook how the bot is doing, when that changes and every few minutes; the Admin page shows it.
        Báo cho webhook biết bot đang ra sao, khi có thay đổi và cứ vài phút một lần; trang Quản trị hiện điều đó."""
        now = self.clock()
        if state == self.state and now - self.reported_at < HEARTBEAT_SECONDS:
            return
        if state != self.state:
            self.log({OK: "reading messages as @%s" % self.bot_name, UNAUTHORIZED: "Telegram refuses the token: check TELEGRAM_ASK_TOKEN, or make a new token with @BotFather",
                      CONFLICT: "another program reads this bot's messages, or a webhook is set on it: one bot, one reader",
                      UNREACHABLE: "Telegram cannot be reached from this machine"}.get(state, state))
        self.state, self.reported_at = state, now
        status, answer = self.board({"report": state, "bot": self.bot_name})
        if state == OK and not self.commands_set and status == 200:
            self.commands_set = self.set_commands(answer.get("commands"))

    def set_commands(self, commands) -> bool:
        """Give Telegram the list of commands it shows next to the message field. The list comes from the webhook: English for
        everyone, and each other language for people whose Telegram app is in it.
        Đưa cho Telegram danh sách lệnh nó hiện cạnh ô nhập tin. Danh sách tới từ webhook: tiếng Anh cho mọi người,
        và từng ngôn ngữ khác cho người dùng app Telegram bằng ngôn ngữ đó."""
        if not isinstance(commands, dict) or not isinstance(commands.get("en"), list):
            return False
        done = True
        for language, rows in sorted(commands.items()):
            if not re.fullmatch(r"[a-z]{2}", str(language)) or not isinstance(rows, list):
                continue
            listed = [{"command": row[0], "description": row[1][:256]} for row in rows
                      if isinstance(row, list) and len(row) == 2 and isinstance(row[1], str) and row[1] and isinstance(row[0], str) and re.fullmatch(r"[a-z0-9_]{1,32}", row[0])]
            status, answer = self.telegram("setMyCommands", dict({"commands": listed}, **({} if language == "en" else {"language_code": language})))
            done = done and status == 200 and answer.get("ok") is True
        return done

    def step(self) -> float:
        """One round: ask Telegram for messages and answer each. Returns how many seconds to wait before the next round.
        Một vòng: hỏi Telegram có tin không và trả lời từng tin. Trả số giây cần chờ trước vòng kế tiếp."""
        if not self.bot_name:
            status, answer = self.telegram("getMe", {})
            me = answer.get("result") if status == 200 and answer.get("ok") is True else None
            name = me.get("username") if isinstance(me, dict) else None
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", name):
                return self.trouble(status, answer)
            self.bot_name = name
            # Telegram took the token, so the bot is reading: said now, not after the first call for messages, which may wait a long while
            # Telegram đã nhận khoá, tức bot đang đọc: nói ngay lúc này, không chờ tới sau lời gọi lấy tin đầu tiên, vốn có thể chờ rất lâu
            self.note(OK)
        ask = {"timeout": self.poll_seconds, "allowed_updates": ["message"]}
        if self.offset is not None:
            ask["offset"] = self.offset
        asked_at = self.clock()
        status, answer = self.telegram("getUpdates", ask, timeout=self.poll_seconds + 15)
        updates = answer.get("result") if status == 200 and answer.get("ok") is True else None
        if not isinstance(updates, list):
            return self.trouble(status, answer)
        self.failures = 0
        self.note(OK)
        for update in updates:
            if not isinstance(update, dict) or not isinstance(update.get("update_id"), int) or isinstance(update.get("update_id"), bool):
                continue
            # confirmed before it is handled: a message that cannot be answered is dropped, not asked for again and again
            # xác nhận trước khi xử lý: tin không trả lời được thì bỏ, không hỏi lại hết lần này tới lần khác
            self.offset = update["update_id"] + 1
            self.handle(update.get("message"))
        self.sync_menus()
        # Telegram holds the call until a message comes. Something in between that answers "nothing" at once must not
        # turn this into a loop that calls without pause
        # Telegram giữ lời gọi cho tới khi có tin. Thứ gì đó ở giữa trả lời "không có gì" ngay lập tức thì không được
        # biến việc này thành một vòng lặp gọi không nghỉ
        return 1 if not updates and self.poll_seconds and self.clock() - asked_at < 1 else 0

    def trouble(self, status: int, answer: dict) -> float:
        """Telegram did not give messages. Says why to the webhook, and how long to wait.
        Telegram không đưa tin. Báo lý do cho webhook, và cho biết cần chờ bao lâu."""
        if status in (401, 404):
            self.note(UNAUTHORIZED)
            return 60
        if status == 409:
            self.note(CONFLICT)
            return 30
        if status == 429:
            return self.retry_after(answer, 60)
        self.failures += 1
        if self.failures >= 3:
            self.note(UNREACHABLE)
        return min(60, 5 * self.failures)

    @staticmethod
    def retry_after(answer: dict, most: int) -> float:
        parameters = answer.get("parameters")
        seconds = parameters.get("retry_after") if isinstance(parameters, dict) else None
        return float(min(most, max(1, seconds))) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else 5.0

    def handle(self, message) -> None:
        """Hand one message to the webhook and send what it answers. Only what the webhook needs is passed on: who sent it,
        the kind of chat, the language of their app and the text.
        Đưa một tin nhắn cho webhook và gửi thứ nó trả lời. Chỉ chuyển những gì webhook cần: ai gửi,
        loại chat, ngôn ngữ app của họ và nội dung chữ."""
        if not isinstance(message, dict):
            return
        sender, chat = message.get("from"), message.get("chat")
        if not isinstance(sender, dict) or not isinstance(chat, dict) or sender.get("is_bot") is True:
            return
        chat_id = chat.get("id")
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return
        sent_at = message.get("date")
        if not isinstance(sent_at, (int, float)) or isinstance(sent_at, bool) or self.clock() - sent_at > STALE_SECONDS:
            self.log("left out a message that is too old to answer; if this happens to new messages, check this machine's clock")
            return
        status, answer = self.board({"from": sender.get("id"), "chat": chat.get("type"), "username": sender.get("username"), "lang": sender.get("language_code"), "text": message.get("text")})
        if status != 200:
            return
        if answer.get("leave") is True and chat.get("type") != "private":
            self.telegram("leaveChat", {"chat_id": chat_id})
        text = answer.get("text")
        if isinstance(text, str) and text:
            self.send(chat_id, text, answer)

    def send(self, chat_id: int, text: str, answer: dict, markup=None) -> None:
        # protect_content: Telegram's apps do not let the answer be forwarded or saved. No formatting is asked for: the text goes as it is
        # protect_content: các app Telegram không cho chuyển tiếp hay lưu câu trả lời. Không yêu cầu định dạng nào: chữ đi nguyên như nó là
        payload = {"chat_id": chat_id, "text": text[:TEXT_LIMIT], "protect_content": True, "link_preview_options": {"is_disabled": True}}
        keyboard = answer.get("keyboard")
        if isinstance(keyboard, list) and keyboard and all(isinstance(row, list) and row and all(isinstance(label, str) and label for label in row) for row in keyboard):
            payload["reply_markup"] = {"keyboard": [[{"text": label} for label in row] for row in keyboard], "resize_keyboard": True, "is_persistent": True}
        elif answer.get("removeKeyboard") is True:
            payload["reply_markup"] = {"remove_keyboard": True}
        if markup:
            payload["reply_markup"] = markup
        status, reply = self.telegram("sendMessage", payload)
        if status == 429:
            self.sleep(self.retry_after(reply, 30))
            status, reply = self.telegram("sendMessage", payload)
        # Telegram refused the buttons under the message: the words still go, since the webhook has already counted the message as sent
        # Telegram từ chối các nút dưới tin: phần chữ vẫn được gửi, vì webhook đã tính tin này là đã gửi rồi
        if status == 400 and markup:
            payload.pop("reply_markup", None)
            status, reply = self.telegram("sendMessage", payload)
        if status != 200:
            self.log("an answer could not be sent (status %d)" % status)

    def sync_menus(self) -> None:
        """Ask the webhook which chats' menu buttons to change, and change them: a button that opens the board's window inside Telegram
        for a chat an admin allowed, the plain menu for one that lost it. The webhook decides; an old webhook answers nothing to this.
        Hỏi webhook cần đổi nút menu của chat nào, rồi đổi: nút mở khung của bảng bên trong Telegram cho chat được quản trị cho phép,
        menu thường cho chat bị bỏ quyền đó. Webhook quyết định; webhook bản cũ không trả lời gì cho câu hỏi này."""
        now = self.clock()
        if self.board_down or (self.menus_at is not None and now - self.menus_at < MENU_SECONDS):
            return
        self.menus_at = now
        status, answer = self.board({"tick": True})
        menus, text = answer.get("menus"), answer.get("menuText")
        if status != 200 or not isinstance(menus, list):
            return
        text = text if isinstance(text, str) and 0 < len(text) <= 32 else "AI Worker"
        for row in menus[:100]:
            chat_id, url = (row.get("to"), row.get("url")) if isinstance(row, dict) else (None, None)
            if not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat_id <= 0:
                continue
            # Telegram opens only an https:// address in a window; anything else from the webhook is taken as "the plain menu"
            # Telegram chỉ mở địa chỉ https:// trong một khung; thứ gì khác webhook gửi đều coi như "menu thường"
            button = {"type": "web_app", "text": text, "web_app": {"url": url}} if isinstance(url, str) and url.startswith("https://") and len(url) <= 512 else {"type": "default"}
            status, reply = self.telegram("setChatMenuButton", {"chat_id": chat_id, "menu_button": button})
            if status == 429:
                self.sleep(self.retry_after(reply, 30))
                status, reply = self.telegram("setChatMenuButton", {"chat_id": chat_id, "menu_button": button})
            if status != 200:
                self.log("a menu button could not be set (status %d)" % status)
        # messages to chats that turned alerts on, each with a button that opens the window when the chat may open it
        # tin tới các chat đã bật báo, mỗi tin kèm nút mở khung khi chat được mở khung
        sends = answer.get("send")
        for row in sends[:100] if isinstance(sends, list) else []:
            chat_id, text, url = (row.get("to"), row.get("text"), row.get("app")) if isinstance(row, dict) else (None, None, None)
            if not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat_id <= 0 or not isinstance(text, str) or not text:
                continue
            buttons = [{"text": "AI Worker", "web_app": {"url": url}}] if isinstance(url, str) and url.startswith("https://") and len(url) <= 512 else []
            # a button that puts one short text on the clipboard (Telegram's copy_text, 1 to 256 characters): the message itself stays protected
            # một nút đưa một đoạn chữ ngắn vào bộ nhớ tạm (copy_text của Telegram, 1 tới 256 ký tự): bản thân tin nhắn vẫn được bảo vệ
            copy = row.get("copy")
            label, value = (copy.get("label"), copy.get("text")) if isinstance(copy, dict) else (None, None)
            if isinstance(label, str) and 0 < len(label) <= 64 and isinstance(value, str) and 0 < len(value) <= 256:
                buttons.append({"text": label, "copy_text": {"text": value}})
            self.send(chat_id, text, {}, {"inline_keyboard": [[b] for b in buttons]} if buttons else None)

    def run(self) -> None:
        # the webhook may still be starting: wait for it, and stop at once if it does not take this process
        # webhook có thể còn đang khởi động: chờ nó, và dừng ngay nếu nó không nhận tiến trình này
        while self.board({"report": "", "bot": ""})[0] != 200:
            self.sleep(5)
        self.log("the board takes this process; asking Telegram for messages")
        while True:
            try:
                wait = self.step()
            except Refused:
                raise
            # one bad round must not end the service; the kind of error is enough to look for it
            # một vòng hỏng không được làm dừng dịch vụ; loại lỗi là đủ để đi tìm
            except Exception as e:
                self.log("a round failed (%s)" % type(e).__name__)
                wait = 5
            if wait:
                self.sleep(wait)


def settings_from(env) -> tuple:
    """(token, board address, board key, API address) from the environment, or a ValueError that says what is wrong.
    (khoá bot, địa chỉ bảng, khoá của bảng, địa chỉ API) lấy từ môi trường, hoặc ValueError nói rõ sai ở đâu."""
    token, key = env.get("TELEGRAM_ASK_TOKEN", "").strip(), env.get("TELEGRAM_ASK_KEY", "").strip()
    if not re.fullmatch(r"[0-9]{1,20}:[A-Za-z0-9_-]{20,100}", token):
        raise ValueError("TELEGRAM_ASK_TOKEN is missing or does not look like a token from @BotFather (digits, a colon, then letters)")
    if len(key) < 32:
        raise ValueError("TELEGRAM_ASK_KEY is missing or shorter than 32 characters; it must equal the webhook's own TELEGRAM_ASK_KEY")
    port = env.get("PORT", "8788").strip() or "8788"
    board = env.get("BOARD_URL", "").strip() or "http://127.0.0.1:%s" % port
    try:
        board_host, board_scheme = urlparse(board).hostname, urlparse(board).scheme
    except ValueError:
        board_host, board_scheme = None, ""
    # the key of /bot/telegram travels to this address unencrypted, and the webhook takes the call only from its own machine
    # khoá của /bot/telegram đi tới địa chỉ này không mã hoá, và webhook chỉ nhận lời gọi từ chính máy của nó
    if board_scheme != "http" or board_host not in LOCAL_HOSTS:
        raise ValueError("BOARD_URL must be the webhook on this same machine, such as http://127.0.0.1:8788")
    api = env.get("TELEGRAM_API_URL", "").strip() or TELEGRAM_API
    try:
        api_host, api_scheme = urlparse(api).hostname, urlparse(api).scheme
    except ValueError:
        api_host, api_scheme = None, ""
    # the token is part of every address called: it goes out over HTTPS, or to a Bot API server on this machine
    # khoá của bot nằm trong mọi địa chỉ được gọi: nó đi ra qua HTTPS, hoặc tới một máy chủ Bot API trên chính máy này
    if not api_host or not (api_scheme == "https" or (api_scheme == "http" and api_host in LOCAL_HOSTS)):
        raise ValueError("TELEGRAM_API_URL must start with https://")
    return token, board, key, api


def stop(signum, frame):
    raise SystemExit(0)


if __name__ == "__main__":
    try:
        bot_token, board_address, board_key, api_address = settings_from(os.environ)
    except ValueError as problem:
        sys.exit("telegram bot: %s" % problem)
    signal.signal(signal.SIGTERM, stop)
    try:
        Bot(bot_token, board_address, board_key, api_address).run()
    except Refused as problem:
        sys.exit("telegram bot: %s" % problem)
    except KeyboardInterrupt:
        sys.exit(0)
