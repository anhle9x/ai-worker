"""What the board says back to one message from a Telegram chat. The bot process on this machine receives the message from Telegram
and hands it over on /bot/telegram; every decision is made here, not in that process: is this chat approved, what may it read, has it
asked too often. board/ask.py picks the command and writes the answer; this module pairs the chat, limits it and writes the log.
Nothing here talks to Telegram, and the words a person typed are neither stored nor logged: only the command they came to.
  Bảng trả lời gì cho một tin nhắn từ một chat Telegram. Tiến trình bot trên máy này nhận tin từ Telegram rồi đưa tới /bot/telegram;
  mọi quyết định nằm ở đây, không nằm ở tiến trình đó: chat này đã được duyệt chưa, được đọc gì, đã hỏi quá nhiều chưa.
  board/ask.py chọn lệnh và viết câu trả lời; module này ghép chat, giới hạn nó và ghi nhật ký.
  Ở đây không có gì nói chuyện với Telegram, và chữ người dùng gõ không được lưu hay ghi nhật ký: chỉ ghi lệnh mà nó ứng với."""

import re
import threading

from board import ask, settings, tgapp
from board.alerts import ALERTS
from webhook_vi import ALERT_WORDS
from board.lang import speaking, tx
from board.security import WALL, CallLimit
from board.settings import KIND_TELEGRAM, TELEGRAM_CALLS_PER_CHAT, TELEGRAM_CALLS_WINDOW_SECONDS, TELEGRAM_STRANGER_SECONDS
from board.stores import AUDIT_LOG, TELEGRAM_BOT, TV, TV_PAIRING, TV_STATUS, chat_key
from board.summary import SCOPE_PEOPLE
from board.views import role_view

# one message with its few fields is far below this; Telegram's own limit is 4096 characters of text
# một tin nhắn cùng vài trường của nó còn cách rất xa mức này; giới hạn của chính Telegram là 4096 ký tự chữ
MAX_MESSAGE_BYTES = 32 * 1024
# how the bot process names the kind of chat a message came from; only this one is answered
# cách tiến trình bot gọi tên loại chat mà tin nhắn tới từ đó; chỉ loại này được trả lời
PRIVATE = "private"

LIMIT = CallLimit(TELEGRAM_CALLS_PER_CHAT, TELEGRAM_CALLS_WINDOW_SECONDS)


class Strangers:
    """When each chat that is not approved was last told so, in memory: it is told once in a while, then gets no answer,
    so the bot cannot be made to send message after message.
    Lần gần nhất mỗi chat chưa được duyệt được báo điều đó, giữ trong bộ nhớ: lâu lâu báo một lần, còn lại không trả lời,
    để không ai bắt bot gửi hết tin này tới tin khác được."""

    def __init__(self):
        self.lock = threading.Lock()
        # Telegram user id -> when it was last told
        # số của người dùng Telegram -> lần gần nhất được báo
        self.told = {}

    def may_tell(self, telegram_id: str, now: float) -> bool:
        with self.lock:
            if telegram_id in self.told and now - self.told[telegram_id] < TELEGRAM_STRANGER_SECONDS:
                return False
            if len(self.told) > 1000:
                self.told = {k: t for k, t in self.told.items() if now - t < TELEGRAM_STRANGER_SECONDS}
            self.told[telegram_id] = now
            return True


STRANGERS = Strangers()


def _say(text: str, keyboard=None, remove_keyboard: bool = False) -> dict:
    """What the bot process should send. An empty text means: send nothing.
    Thứ tiến trình bot cần gửi. Chữ rỗng nghĩa là: không gửi gì."""
    return {"text": text, **({"keyboard": keyboard} if keyboard else {}), **({"removeKeyboard": True} if remove_keyboard else {})}


def on_call(msg, now: float) -> dict:
    """Everything the bot process sends comes through here: a message from a chat, or a word about itself ({"report", "bot"}).
    A report is answered with the list of commands Telegram should show, in both languages: the bot process holds no texts of its own.
    Mọi thứ tiến trình bot gửi đều đi qua đây: một tin nhắn từ một chat, hoặc một lời về chính nó ({"report", "bot"}).
    Lời báo được trả lời bằng danh sách lệnh mà Telegram cần hiện, bằng cả hai ngôn ngữ: tiến trình bot không giữ chữ nào của riêng nó."""
    if isinstance(msg, dict) and "report" in msg:
        TELEGRAM_BOT.report(msg.get("report"), msg.get("bot"), now)
        return {"ok": True, "commands": {language: [list(row) for row in ask.menu(language)] for language in ("en", "vi")}}
    # once a round the bot process asks which chats' menu buttons to change: the board's window for a chat an admin allowed, the plain
    # menu for one that lost it (board/tgapp.py)
    # mỗi vòng tiến trình bot hỏi cần đổi nút menu của chat nào: khung của bảng cho chat được quản trị cho phép, menu thường cho chat
    # bị bỏ quyền đó (board/tgapp.py)
    if isinstance(msg, dict) and msg.get("tick") is True:
        return {"ok": True, "menus": tgapp.MENUS.changes(now), "menuText": tgapp.MENU_TEXT, "send": alerts_due(now)}
    TELEGRAM_BOT.seen(now)
    return on_message(msg, now)


def on_message(msg, now: float) -> dict:
    """The answer to one message: {"text", "keyboard"?, "removeKeyboard"?, "leave"?}. msg is what the bot process took from Telegram's
    update: "from" (the sender's Telegram number), "chat" (the kind of chat), "username", "lang" (the language of their app) and "text".
    Câu trả lời cho một tin nhắn: {"text", "keyboard"?, "removeKeyboard"?, "leave"?}. msg là những gì tiến trình bot lấy từ tin của
    Telegram: "from" (số Telegram của người gửi), "chat" (loại chat), "username", "lang" (ngôn ngữ app của họ) và "text"."""
    if not isinstance(msg, dict):
        return _say("")
    telegram_id = msg.get("from")
    if isinstance(telegram_id, int) and not isinstance(telegram_id, bool):
        telegram_id = str(telegram_id)
    if not isinstance(telegram_id, str) or not re.fullmatch(r"[0-9]{1,20}", telegram_id):
        return _say("")
    # a group or a channel: everyone there would read the answer, and who is there changes without the board's admin knowing
    # nhóm hay kênh: ai ở đó cũng đọc được câu trả lời, và người ra vào thì quản trị của bảng không biết
    if msg.get("chat") != PRIVATE:
        return dict(_say(""), leave=True)
    username = msg.get("username")
    username = username if isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_]{1,32}", username) else ""
    asked = ask.match(msg.get("text"))
    language = ask.language_for(asked.lang, msg.get("lang"))
    with speaking(language):
        return _answer(telegram_id, username, asked.command, language, now, msg.get("text"))


def alerts_due(now: float) -> list:
    """The messages the bot process should send now to chats that turned alerts on (board/alerts.py), each with the window's address
    when the chat may open it. One row in the log for each, with how many people and never who.
    Các tin tiến trình bot cần gửi ngay tới các chat đã bật báo (board/alerts.py), mỗi tin kèm địa chỉ của khung khi chat được mở khung.
    Mỗi tin một dòng nhật ký, ghi bao nhiêu người và không bao giờ ghi là ai."""
    chats = [dict(v, id=k) for k, v in TV.d.items() if v.get("kind") == KIND_TELEGRAM and v["expiresAt"] > now and v.get("notify") is True]
    if not chats:
        return []
    out = []
    for m in ALERTS.due(chats, role_view(WALL, now), now):
        chat = m["chat"]
        AUDIT_LOG.write(action="telegram-alert", tv=chat["name"], id=chat["id"], kind=KIND_TELEGRAM, people=m["count"])
        window = settings.TELEGRAM_APP_ENABLED and chat.get("app") is True and chat.get("scope") == SCOPE_PEOPLE
        out.append({"to": m["to"], "text": m["text"], "app": settings.TELEGRAM_APP_URL if window else None})
    return out


def _alerts(chat_id: str, chat: dict, text, language: str) -> dict:
    """/alerts in a chat: on with a number of minutes, off, or how it stands. The chat sets this for itself; the admin chose what it reads.
    /alerts trong một chat: bật kèm số phút, tắt, hoặc cho biết đang thế nào. Chat tự đặt việc này; quản trị đã chọn nó được đọc gì."""
    m = re.match(r"/[A-Za-z0-9_]+(?:@[A-Za-z0-9_]+)?\s*(.*)", text.strip()[:80]) if isinstance(text, str) else None
    arg = m.group(1).strip().casefold() if m else ""
    minutes = chat.get("notifyMinutes") if chat.get("notifyMinutes") in settings.MINI_NOTIFY_MINUTES else 10
    if arg in ("off", "0") + ALERT_WORDS["off"]:
        TV.set_alerts(chat_id, False, minutes, language)
        return _say("\n".join([ask.HEADER, "", "🔕 " + tx("Alerts are off. Send /alerts 10 to get them again.")]))
    if arg in ("on",) + ALERT_WORDS["on"] or (arg.isdigit() and int(arg) in settings.MINI_NOTIFY_MINUTES):
        minutes = int(arg) if arg.isdigit() else minutes
        TV.set_alerts(chat_id, True, minutes, language)
        return _say("\n".join([ask.HEADER, "", "🔔 " + tx("Alerts are on: a message when someone has waited more than {m} min.", m=minutes),
                                tx("At most one message every 5 minutes, none from 19:00 to 07:00. Send /alerts off to stop.")]))
    state = tx("Alerts are on: a message when someone has waited more than {m} min.", m=minutes) if chat.get("notify") is True else tx("Alerts are off.")
    return _say("\n".join([ask.HEADER, "", "🔔 " + state, tx("Send /alerts 10 for a message after 10 minutes of waiting (or 5, 15, 30, 60), /alerts off to stop.")]))


def _answer(telegram_id: str, username: str, command: str, language: str, now: float, text=None) -> dict:
    key = chat_key(telegram_id)
    chat, joined = TV.find(key, now, KIND_TELEGRAM), False
    if not chat:
        # the chat cannot be told when an admin approves its code, so its next message is what finishes the pairing
        # không báo được cho chat lúc quản trị duyệt mã của nó, nên tin nhắn kế tiếp của nó là thứ hoàn tất việc ghép
        approved = TV_PAIRING.poll(key, now, chat=True)
        if isinstance(approved, dict):
            try:
                chat_id, _ = TV.create(approved, now)
            except ValueError as e:
                AUDIT_LOG.write(action="error", error=str(e)[:200], kind=KIND_TELEGRAM)
                return _say("🚫 " + tx("This chat could not be connected: the board has no room for another Telegram chat. Ask an admin of the board."))
            AUDIT_LOG.write(action="tv-joined", tv=approved["name"], id=chat_id, kind=KIND_TELEGRAM, approvedBy=approved["approvedBy"], telegramUser=approved.get("telegramUser", ""))
            chat, joined = TV.find(key, now, KIND_TELEGRAM), True
    if not chat:
        return _stranger(telegram_id, username, command, now)
    chat_id = TV.id_of(key)
    if command == ask.STOP:
        TV.revoke(chat_id)
        AUDIT_LOG.write(action="telegram-stop", tv=chat["name"], id=chat_id, kind=KIND_TELEGRAM)
        return _say("👋 " + tx("Disconnected: this chat no longer reads the board. Send /start to ask for a new code."), remove_keyboard=True)
    if not LIMIT.allow(chat_id, now):
        if not LIMIT.first_refusal(chat_id, now):
            return _say("")
        AUDIT_LOG.write(action="telegram-rate-limited", tv=chat["name"], id=chat_id)
        return _say("🚦 " + tx("This chat has asked too often. Try again in a few minutes."))
    TV.touch(key, "", now, KIND_TELEGRAM)
    TV_STATUS.mark_seen(chat_id, "", now)
    if command == ask.ALERTS and not joined:
        return _alerts(chat_id, chat, text, language)
    keyboard = ask.keyboard(language)
    if command in ask.DATA_COMMANDS and not joined:
        text = ask.answer(command, role_view(WALL, now), chat.get("scope", ""), now * 1000, language)
        # the same fields as a call of the MCP tool, so the Admin page reads both in one list
        # cùng các trường với một lần gọi công cụ MCP, để trang Quản trị đọc cả hai trong một danh sách
        AUDIT_LOG.write(action=AUDIT_LOG.ASK_CALL, tv=chat["name"], id=chat_id, tool=command, ok=True, client="Telegram")
        return _say(text, keyboard)
    help_lines = ask.answer(ask.HELP, None, "", now * 1000, language).split("\n")
    if not joined and command != ask.START:
        return _say("\n".join(help_lines), keyboard)
    # the first line stays the neutral one: it is what a phone shows on its lock screen. Then the news, a blank line, and the commands
    # dòng đầu vẫn là dòng trung tính: đó là thứ điện thoại hiện trên màn hình khoá. Sau đó là tin báo, một dòng trống, rồi các lệnh
    return _say("\n".join(help_lines[:2] + [
        "✅ " + (tx("Connected to the board as: {name}", name=chat["name"]) if joined else tx("This chat is already connected to the board.")),
        ("👤 " + tx("This chat reads each person's numbers.")) if chat.get("scope") == SCOPE_PEOPLE else ("🔒 " + tx("This chat reads team and office totals only.")),
        "🔐 " + tx("This bot never asks for a login code or a password."),
        "",
    ] + help_lines[2:]), keyboard)


def _stranger(telegram_id: str, username: str, command: str, now: float) -> dict:
    """A chat no admin has approved. It reads nothing; with /start it gets a code to read to an admin.
    Chat chưa được quản trị nào duyệt. Nó không đọc được gì; gửi /start thì nhận một mã để đọc cho quản trị."""
    if command != ask.START:
        return _say("🔌 " + tx("This chat is not connected to the board. Send /start to get a pairing code.")) if STRANGERS.may_tell(telegram_id, now) else _say("")
    pending = TV_PAIRING.request_chat(telegram_id, username, now)
    if not pending:
        return _say("🚦 " + tx("Too many chats are waiting for approval. Try again in a few minutes.")) if STRANGERS.may_tell(telegram_id, now) else _say("")
    code, seconds_left, fresh = pending
    if fresh:
        AUDIT_LOG.write(action="tv-request-code", kind=KIND_TELEGRAM, telegramUser=username, telegramId=telegram_id)
    return _say("\n".join([
        ask.HEADER,
        "",
        "🔑 " + tx("Pairing code: {code} (good for {minutes} min).", code="%s-%s" % (code[:4], code[4:]), minutes=max(1, (seconds_left + 59) // 60)),
        tx("Read this code to an admin of the board yourself. The admin enters it on the Admin page, under TV screens, and chooses what this chat may read."),
        "",
        "🔐 " + tx("Then send any message here. This bot never asks for a login code or a password."),
    ]))
