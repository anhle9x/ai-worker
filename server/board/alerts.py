"""A message to a Telegram chat when someone has waited for an answer longer than the chat asked: the bot speaks first, without being asked.
Each chat turns it on itself (the window's settings, or /alerts), and it is off until then. Every wait is told once; several are told in
one message; a chat gets at most one message every 5 minutes, 6 an hour and 30 a day; nothing is sent at night. The first line names
nobody, since a phone shows it on its lock screen, and a chat that reads totals only is told how many, never who.
Nothing here talks to Telegram, and what was told is kept in memory: after a restart a wait still going may be told once more.
  Một tin nhắn tới chat Telegram khi có người chờ trả lời lâu hơn mức chat đó đặt: bot tự nói trước, không cần được hỏi.
  Mỗi chat tự bật (cài đặt trong khung, hoặc /alerts), và tắt cho tới lúc đó. Mỗi lần chờ chỉ báo một lần; nhiều lần chờ gộp trong
  một tin; một chat nhận tối đa một tin mỗi 5 phút, 6 tin mỗi giờ và 30 tin mỗi ngày; ban đêm không gửi gì. Dòng đầu không nêu tên ai,
  vì điện thoại hiện dòng đó trên màn hình khoá, và chat chỉ đọc số gộp chỉ được biết có bao nhiêu người, không bao giờ biết là ai.
  Ở đây không có gì nói chuyện với Telegram, và những gì đã báo được giữ trong bộ nhớ: sau khi khởi động lại, một lần chờ còn đang diễn ra
  có thể được báo thêm một lần."""

import re
import threading
from datetime import datetime

from board import lang, settings
from board.lang import speaking, tx
from board.summary import SCOPE_PEOPLE, clean_name, minutes_waiting, state_of

# a chat gets at most one message in this time; waits that pass the line in between go into the next one
# một chat nhận tối đa một tin trong khoảng này; những lần chờ vượt mức trong lúc đó vào tin kế tiếp
GAP_SECONDS = 300
PER_HOUR, PER_DAY = 6, 30
# a wait longer than this is taken for a session left open, not for a person waiting: it is not told
# lần chờ dài hơn mức này được coi là phiên bị bỏ mở, không phải người đang chờ: không báo
STALE_MINUTES = 240
# hours of the board's time zone when nothing is sent; a wait that passes the line then is not told the next morning
# các giờ (theo múi giờ của bảng) không gửi gì; lần chờ vượt mức trong lúc đó không được báo vào sáng hôm sau
QUIET_FROM, QUIET_TO = 19, 7
# people named in one message; the rest are counted
# số người được nêu tên trong một tin; số còn lại chỉ đếm
NAMES = 10


def quiet(at: datetime) -> bool:
    """Whether nothing is sent at this time. The same hour at both ends means no quiet hours.
    Lúc này có im lặng không. Hai đầu cùng một giờ nghĩa là không có giờ im lặng."""
    if QUIET_FROM == QUIET_TO:
        return False
    if QUIET_FROM > QUIET_TO:
        return at.hour >= QUIET_FROM or at.hour < QUIET_TO
    return QUIET_FROM <= at.hour < QUIET_TO


def waits(view, now_ms: float) -> list:
    """(key, name, minutes) of each person waiting now. The key is the person and the moment the wait began, so a new wait is a new key.
    (khoá, tên, số phút) của từng người đang chờ. Khoá là người đó và lúc bắt đầu chờ, nên lần chờ mới là khoá mới."""
    out = []
    people = view.get("people") if isinstance(view, dict) and isinstance(view.get("people"), list) else []
    for p in people:
        if not isinstance(p, dict) or state_of(p) != "waiting":
            continue
        minutes = minutes_waiting(p, now_ms)
        if minutes is None:
            continue
        name = " ".join(re.sub(r"\.(?=\w)", " ", clean_name(p.get("name"))).split())
        out.append(("%s|%s" % (name, p.get("waitingSince")), name, minutes))
    return out


def message(over: list, minutes: int, scope: str, language: str) -> str:
    """The text for one chat. over: (key, name, minutes), longest first.
    Chữ gửi cho một chat. over: (khoá, tên, số phút), lâu nhất trước."""
    with speaking(language):
        lines = ["⏳ AI Worker · " + tx("{n} waiting longer than {m} min", n=len(over), m=minutes)]
        if scope == SCOPE_PEOPLE:
            lines += ["• %s: %s" % (name, tx("{m} min", m=m)) for _, name, m in over[:NAMES]]
            if len(over) > NAMES:
                lines.append(tx("and {n} more", n=len(over) - NAMES))
        else:
            lines.append("🔒 " + tx("This chat reads totals only, so nobody is named."))
        lines += ["", tx("Turn these messages off with /alerts off.")]
    return "\n".join(lines)


class Alerts:
    def __init__(self):
        self.lock = threading.Lock()
        # Telegram user's number -> keys of the waits already told (or passed over at night)
        # số người dùng Telegram -> khoá của các lần chờ đã báo (hoặc bỏ qua ban đêm)
        self.told = {}
        # Telegram user's number -> times of the messages sent
        # số người dùng Telegram -> thời điểm các tin đã gửi
        self.sent = {}

    def due(self, chats: list, view, now: float) -> list:
        """[{"to", "text", "chat"}] to send now. chats: the rows of the Telegram chats that turned alerts on.
        [{"to", "text", "chat"}] cần gửi ngay. chats: các dòng của chat Telegram đã bật báo."""
        current = waits(view, now * 1000)
        at = datetime.fromtimestamp(now, settings.LOCAL_TZ)
        out = []
        with self.lock:
            live = {key for key, _, _ in current}
            for chat in chats:
                tg = str(chat.get("telegramId", ""))
                if not re.fullmatch(r"[0-9]{1,20}", tg):
                    continue
                minutes = chat.get("notifyMinutes") if chat.get("notifyMinutes") in settings.MINI_NOTIFY_MINUTES else 10
                # a wait that ended is forgotten, so the list stays as short as the waits going on
                # lần chờ đã xong thì quên, để danh sách chỉ dài bằng các lần chờ đang diễn ra
                told = self.told.setdefault(tg, set()) & live
                self.told[tg] = told
                over = sorted(((k, n, m) for k, n, m in current if minutes <= m <= STALE_MINUTES and k not in told), key=lambda w: -w[2])
                if not over:
                    continue
                if quiet(at):
                    told.update(k for k, _, _ in over)
                    continue
                times = [t for t in self.sent.get(tg, []) if now - t < 86400]
                self.sent[tg] = times
                if times and now - times[-1] < GAP_SECONDS:
                    continue
                if sum(1 for t in times if now - t < 3600) >= PER_HOUR or len(times) >= PER_DAY:
                    told.update(k for k, _, _ in over)
                    continue
                told.update(k for k, _, _ in over)
                times.append(now)
                language = chat.get("notifyLang") if chat.get("notifyLang") in ("en", "vi") else (lang.DEFAULT_LANG or "en")
                out.append({"to": int(tg), "text": message(over, minutes, chat.get("scope", ""), language), "chat": chat, "count": len(over)})
        return out

    def forget(self, telegram_id: str) -> None:
        with self.lock:
            self.told.pop(telegram_id, None)
            self.sent.pop(telegram_id, None)


ALERTS = Alerts()
