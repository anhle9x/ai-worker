"""Answers to questions about the board asked from a Telegram chat: which command a message means, and the answer as a few short lines
for a person to read on a phone, in English or Vietnamese. No AI model reads the question: a command, a button or a keyword picks one of
a fixed set of answers, and every number comes straight from the wall view.
Pure: no sockets, no database, no keys and nothing of Telegram's protocol. The caller decides who may ask and what they may read (each
person, or totals only), passes the wall view, and sends the text.
  Câu trả lời cho các câu hỏi về bảng gửi từ một chat Telegram: một tin nhắn ứng với lệnh nào, và câu trả lời thành vài dòng ngắn
  cho người đọc trên điện thoại, bằng tiếng Anh hoặc tiếng Việt. Không mô hình AI nào đọc câu hỏi: một lệnh, một nút hay một từ khoá
  chọn một trong số câu trả lời cố định, và mọi con số lấy thẳng từ phần treo tường.
  Mã thuần: không socket, không cơ sở dữ liệu, không khoá và không có gì của giao thức Telegram. Bên gọi quyết định ai được hỏi và
  được đọc gì (từng người, hoặc chỉ số gộp), đưa phần treo tường, rồi gửi chữ đi."""

import re
import unicodedata
from typing import NamedTuple

from board import lang
from board.lang import speaking, tx
from board.summary import (
    SCOPE_PEOPLE,
    Office,
    Snapshot,
    clean_name,
    count,
    in_state,
    minutes_waiting,
    money,
    num,
    quota_pct,
    snapshot,
    state_of,
    total,
)
from webhook_vi import ASK_WORDS

WAITING, COST, OFFICES, TEAM, QUOTA, HELP, START, STOP, ALERTS = "waiting", "cost", "offices", "team", "quota", "help", "start", "stop", "alerts"
# the commands that read numbers; start and stop are about the chat itself and belong to the caller
# các lệnh đọc số liệu; start và stop là chuyện của chính chat đó và thuộc về bên gọi
DATA_COMMANDS = (WAITING, COST, OFFICES, TEAM, QUOTA)
COMMANDS = DATA_COMMANDS + (HELP, START, STOP, ALERTS)
# a second name for Vietnamese speakers. Telegram takes only lowercase English letters, digits and underscores in a command, so no accents
# tên thứ hai cho người nói tiếng Việt. Telegram chỉ nhận chữ thường tiếng Anh, chữ số và gạch dưới trong một lệnh, nên không có dấu
VI_NAMES = {WAITING: "cho", COST: "chiphi", OFFICES: "vanphong", TEAM: "tongquan", QUOTA: "hanmuc", ALERTS: "baocho"}
ALIASES = {name: command for command, name in VI_NAMES.items()}
# words in a typed question that point to a command. The Vietnamese ones are in webhook_vi.py (ASK_WORDS)
# các từ trong câu gõ tự do chỉ tới một lệnh. Các từ tiếng Việt nằm ở webhook_vi.py (ASK_WORDS)
WORDS_EN = {
    QUOTA: ("quota", "limit", "limits"),
    WAITING: ("waiting", "wait", "waits", "stuck"),
    COST: ("cost", "costs", "spend", "spent", "spending", "how much", "money"),
    OFFICES: ("office", "offices", "branch", "branches"),
    TEAM: ("team", "overview", "summary", "everyone"),
    HELP: ("help", "commands"),
}
# when a question names two things, the earlier one here wins: "which office spent most" is about cost, and the cost answer lists offices
# khi câu hỏi nhắc hai thứ, thứ đứng trước ở đây thắng: "văn phòng nào tốn nhất" là hỏi chi phí, và câu trả lời chi phí có liệt kê văn phòng
PRIORITY = (QUOTA, WAITING, COST, OFFICES, TEAM, HELP)

# One small picture at the head of a line, so a phone screen is read at a glance: the same pictures in both languages, on the
# buttons, in the list of commands and in the answers. They are plain characters, not formatting, so the text still goes as it is
# Một hình nhỏ ở đầu dòng, để nhìn lướt màn hình điện thoại là đọc được: cùng bộ hình cho cả hai ngôn ngữ, trên các nút,
# trong danh sách lệnh và trong câu trả lời. Chúng là ký tự thường, không phải định dạng, nên chữ vẫn đi nguyên như nó là
HEADER = "📊 AI Worker"
ICONS = {WAITING: "⏳", COST: "💰", OFFICES: "🏢", TEAM: "👥", QUOTA: "🔋", HELP: "❓", STOP: "🚪", ALERTS: "🔔"}
ALL_WELL, TOTALS_NOTE, NOTE, EMPTY, TOP, BULLET = "✅", "🔒", "📝", "📭", "📈", "•"
STATE_DOTS = (("working", "🟢"), ("waiting", "🟡"), ("open", "⚪"), ("offline", "⚫"))

# Telegram takes 1 to 4096 characters in one message
# Telegram nhận 1 tới 4096 ký tự trong một tin
TEXT_LIMIT = 4096
# only the start of a message is read for keywords
# chỉ đọc phần đầu của tin để tìm từ khoá
TEXT_READ = 200
# rows per list, so one answer stays within 30 lines, blank lines between its parts included
# số dòng mỗi danh sách, để một câu trả lời nằm trong 30 dòng, kể cả các dòng trống giữa các phần
ROWS = 20
COST_OFFICE_ROWS = 15
COST_PEOPLE_ROWS = 5
# a person shows in the quota answer from this share of a quota window
# một người hiện trong câu trả lời hạn mức từ mức dùng này của một khung hạn mức
QUOTA_NEAR = 80


class Asked(NamedTuple):
    command: str
    # the language the message was written in, when it shows: a Vietnamese command name, button or keyword. "" when it does not
    # ngôn ngữ của tin nhắn, khi nhìn ra được: tên lệnh, nút hay từ khoá tiếng Việt. "" khi không nhìn ra
    lang: str = ""


def _words(text: str) -> str:
    """Lowercase words with one space between and around them, so " cost " finds the word and not "costume".
    Các từ viết thường, một dấu cách ở giữa và hai đầu, để " cost " tìm đúng từ đó chứ không phải "costume"."""
    return " %s " % " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold()))


def _fold(text: str) -> str:
    """Vietnamese without its accents, as many people type it on a phone.
    Tiếng Việt bỏ dấu, như nhiều người gõ trên điện thoại."""
    plain = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    # the crossed d does not come apart into a letter and a mark
    # chữ d có gạch không tách được thành chữ cái và dấu
    return plain.replace(chr(0x111), "d")


def _word_table() -> list:
    """(words to find, command, language, whether to look in the text without accents), in the order they are tried.
    A single Vietnamese word counts only with its accents: without them it reads as other words. A phrase counts either way.
    (các từ cần tìm, lệnh, ngôn ngữ, có tìm trong câu đã bỏ dấu không), theo thứ tự thử.
    Một từ tiếng Việt đơn chỉ tính khi có dấu: bỏ dấu thì nó đọc ra từ khác. Một cụm từ thì có dấu hay không đều tính."""
    table = []
    for command in PRIORITY:
        vi = [_words(w) for w in ASK_WORDS.get(command, ())]
        table += [(w, command, "vi", False) for w in vi]
        table += [(" %s " % w, command, "en", False) for w in WORDS_EN[command]]
        table += [(_fold(w), command, "vi", True) for w in vi if " " in w.strip()]
    return table


def _button_pairs() -> list:
    """The buttons under the message field, in the language being spoken. A tap sends the label as a message, and match() reads it
    like any typed question: each label holds a keyword of its own command (a test checks this for both languages).
    Các nút dưới ô nhập tin, bằng ngôn ngữ đang nói. Bấm nút là gửi chữ trên nút như một tin nhắn, và match() đọc nó
    như mọi câu gõ tự do: mỗi nút có chứa một từ khoá của chính lệnh đó (có test kiểm cho cả hai ngôn ngữ)."""
    pairs = [(WAITING, tx("Who is waiting")), (COST, tx("Cost")), (OFFICES, tx("Offices")), (TEAM, tx("Team")), (QUOTA, tx("Quota"))]
    return [(command, "%s %s" % (ICONS[command], label)) for command, label in pairs]


WORDS = _word_table()


def match(text) -> Asked:
    """The command a message means. A message that means none of them, or is not text, gets the help: the bot does not guess.
    Lệnh mà một tin nhắn muốn nói. Tin không ứng với lệnh nào, hoặc không phải chữ, thì nhận phần trợ giúp: bot không đoán."""
    if not isinstance(text, str) or not text.strip():
        return Asked(HELP)
    text = text.strip()[:TEXT_READ]
    if text.startswith("/"):
        # /cost, /cost@some_bot, /start with a parameter
        # /cost, /cost@some_bot, /start kèm tham số
        m = re.match(r"/([A-Za-z0-9_]{1,32})(?:@[A-Za-z0-9_]{1,64})?(?:\s|$)", text)
        name = m.group(1).lower() if m else ""
        if name in COMMANDS:
            return Asked(name)
        return Asked(ALIASES[name], "vi") if name in ALIASES else Asked(HELP)
    words = _words(text)
    folded = _fold(words)
    for needle, command, language, in_folded in WORDS:
        if needle in (folded if in_folded else words):
            return Asked(command, language)
    return Asked(HELP)


def language_for(asked_lang: str, language_code) -> str:
    """The language to answer in: the one the message was written in when it shows, then the language of the person's Telegram app,
    then the server's default, then English.
    Ngôn ngữ để trả lời: ngôn ngữ của tin nhắn khi nhìn ra được, rồi ngôn ngữ app Telegram của người đó,
    rồi mặc định của máy chủ, rồi tiếng Anh."""
    if asked_lang in ("en", "vi"):
        return asked_lang
    if isinstance(language_code, str) and language_code.strip():
        return "vi" if re.match(r"vi\b", language_code.strip(), re.I) else "en"
    return lang.DEFAULT_LANG or "en"


def keyboard(language: str) -> list:
    """Rows of button labels for the keyboard shown under the message field.
    Các hàng chữ trên nút cho bàn phím hiện dưới ô nhập tin."""
    with speaking(language):
        labels = [label for _, label in _button_pairs()]
    return [labels[0:2], labels[2:4], labels[4:5]]


def _menu_pairs() -> list:
    return [
        (WAITING, tx("Who is waiting for an answer, longest first")),
        (COST, tx("Cost today and over 7 days")),
        (OFFICES, tx("Each office in one line")),
        (TEAM, tx("The whole team in short")),
        (QUOTA, tx("Who is close to their quota")),
        (ALERTS, tx("Message me when someone waits too long")),
        (HELP, tx("Show these commands")),
        (STOP, tx("Disconnect this chat from the board")),
    ]


def menu(language: str) -> list:
    """(command name, description) for the command list Telegram shows, in one language. Vietnamese gets the Vietnamese names.
    (tên lệnh, mô tả) cho danh sách lệnh Telegram hiện ra, bằng một ngôn ngữ. Tiếng Việt thì dùng tên tiếng Việt."""
    with speaking(language):
        return [(VI_NAMES.get(command, command) if language == "vi" else command, text) for command, text in _menu_pairs()]


def _name(v) -> str:
    """A name for a Telegram message. Telegram turns "name.example" into a link the reader can tap, so a dot that glues two words
    together becomes a space; the other marks Telegram reads (/ @ # and web addresses) are already taken out by clean_name.
    Tên để đưa vào tin Telegram. Telegram biến "name.example" thành liên kết bấm được, nên dấu chấm dính liền hai từ
    thành dấu cách; các dấu khác mà Telegram đọc (/ @ # và địa chỉ web) đã bị clean_name lọc sẵn."""
    return " ".join(re.sub(r"\.(?=\w)", " ", clean_name(v)).split())


def _dollars(v: float) -> str:
    return "$" + money(v)


def _duration(minutes: int) -> str:
    return tx("{h} h {m} min", h=minutes // 60, m=minutes % 60) if minutes >= 60 else tx("{m} min", m=minutes)


def _office_label(office: Office) -> str:
    return tx("Small offices") if office.merged else _name(office.name) if office.name else tx("No office")


def _capped(rows: list, limit: int) -> list:
    return rows if len(rows) <= limit else rows[:limit] + [tx("and {n} more", n=len(rows) - limit)]


def _numbered(rows: list) -> list:
    return ["%d. %s" % (i, row) for i, row in enumerate(rows, 1)]


def _totals_only() -> list:
    """The closing note of an answer that would have named people, after a blank line.
    Dòng chú thích cuối của một câu trả lời lẽ ra có nêu tên người, sau một dòng trống."""
    return ["", "%s %s" % (TOTALS_NOTE, tx("This chat reads totals only. An admin of the board can approve it to read each person too."))]


def _waiting(snap: Snapshot, with_people: bool, now_ms: float) -> list:
    waiting = [(minutes_waiting(p, now_ms), p, place) for p, place in zip(snap.people, snap.places) if state_of(p) == "waiting"]
    if not waiting:
        return ["%s %s" % (ALL_WELL, tx("Nobody is waiting for an answer."))]
    lines = ["%s %s" % (ICONS[WAITING], tx("Waiting for an answer: {n}", n=len(waiting)))]
    if not with_people:
        # one row of offices would only say the total again
        # một dòng văn phòng duy nhất thì chỉ nhắc lại tổng số
        rows = ["%s %s: %d" % (ICONS[OFFICES], _office_label(o), count(o.people, "waiting")) for o in snap.offices if count(o.people, "waiting")] if len(snap.offices) > 1 else []
        return lines + _capped(rows, ROWS) + _totals_only()
    rows = []
    # longest first; a wait whose start the board does not know goes last
    # lâu nhất trước; lần chờ mà bảng không rõ lúc bắt đầu thì xếp cuối
    for minutes, p, place in sorted(waiting, key=lambda row: -1 if row[0] is None else row[0], reverse=True):
        row = _name(p.get("name")) + (" (%s)" % _name(place) if place else "")
        rows.append(row if minutes is None else "%s: %s" % (row, _duration(minutes)))
    return lines + _capped(_numbered(rows), ROWS)


def _cost_line(people: list) -> str:
    return "%s %s" % (ICONS[COST], tx("Cost today: {today} · 7 days: {week}", today=_dollars(total(people, "usdToday")), week=_dollars(total(people, "usd7d"))))


def _cost(snap: Snapshot, with_people: bool, now_ms: float) -> list:
    lines = [_cost_line(snap.people)]
    dollars = ["", "%s %s" % (NOTE, tx("US dollars at API prices, not an invoice."))]
    # one row of offices would only say the total again, and an office that spent nothing adds nothing
    # một dòng văn phòng duy nhất thì chỉ nhắc lại tổng số, và văn phòng không tốn gì thì không thêm được gì
    offices = sorted((o for o in snap.offices if total(o.people, "usdToday") or total(o.people, "usd7d")), key=lambda o: total(o.people, "usdToday"), reverse=True)
    if len(snap.offices) > 1 and offices:
        lines += ["", "%s %s" % (ICONS[OFFICES], tx("By office (today · 7 days):"))]
        lines += _capped(["%s %s: %s · %s" % (BULLET, _office_label(o), _dollars(total(o.people, "usdToday")), _dollars(total(o.people, "usd7d"))) for o in offices], COST_OFFICE_ROWS)
    if not with_people:
        return lines + _totals_only() + dollars
    top = sorted((p for p in snap.people if num(p.get("usdToday")) > 0), key=lambda p: num(p.get("usdToday")), reverse=True)[:COST_PEOPLE_ROWS]
    if top:
        lines += ["", "%s %s" % (TOP, tx("Highest today:"))]
        lines += _numbered(["%s: %s" % (_name(p.get("name")), _dollars(num(p.get("usdToday")))) for p in top])
    return lines + dollars


def _offices(snap: Snapshot, with_people: bool, now_ms: float) -> list:
    return _capped(["%s %s" % (ICONS[OFFICES], tx("{name}: People {people} · Working {working} · Waiting {waiting} · Today {cost}", name=_office_label(o), people=len(o.people),
                                              working=count(o.people, "working"), waiting=count(o.people, "waiting"), cost=_dollars(total(o.people, "usdToday")))) for o in snap.offices], ROWS)


def _team(snap: Snapshot, with_people: bool, now_ms: float) -> list:
    people = snap.people
    # the same dots as on the board: green working, yellow waiting
    # cùng các chấm như trên bảng: xanh là đang làm, vàng là đang chờ
    words = {"working": tx("Working {n}", n=count(people, "working")), "waiting": tx("Waiting {n}", n=count(people, "waiting")),
             "open": tx("Idle {n}", n=count(people, "open")), "offline": tx("Offline {n}", n=count(people, "offline"))}
    # a person waiting in one session while another runs is in both counts: say so, or the four numbers look like more people than there are
    # người đang chờ ở một phiên trong khi phiên khác chạy nằm ở cả hai số: nói rõ, kẻo bốn con số trông như nhiều người hơn thực tế
    both = sum(1 for p in people if in_state(p, "waiting") and in_state(p, "working"))
    return [
        "%s %s" % (ICONS[TEAM], tx("People in the team: {n}", n=len(people))),
        " · ".join("%s %s" % (dot, words[state]) for state, dot in STATE_DOTS),
    ] + (["%s %s" % (NOTE, tx("{n} waiting in one session while another runs: counted in both.", n=both))] if both else []) + [
        _cost_line(people),
    ]


def _quota(snap: Snapshot, with_people: bool, now_ms: float) -> list:
    near = []
    for p in snap.people:
        five, seven = quota_pct(p, "five_hour"), quota_pct(p, "seven_day")
        used = [v for v in (five, seven) if v is not None and v >= QUOTA_NEAR]
        if used:
            near.append((max(used), p, five, seven))
    if not near:
        return ["%s %s" % (ALL_WELL, tx("Nobody has used {pct}% of a quota.", pct=QUOTA_NEAR))]
    lines = ["%s %s" % (ICONS[QUOTA], tx("Used {pct}% of a quota or more: {n}", pct=QUOTA_NEAR, n=len(near)))]
    if not with_people:
        return lines + _totals_only()
    rows = []
    for _, p, five, seven in sorted(near, key=lambda row: row[0], reverse=True):
        parts = []
        if five is not None and five >= QUOTA_NEAR:
            parts.append(tx("{pct}% of 5 hours", pct=five))
        if seven is not None and seven >= QUOTA_NEAR:
            parts.append(tx("{pct}% of 7 days", pct=seven))
        rows.append("%s: %s" % (_name(p.get("name")), ", ".join(parts)))
    return lines + _capped(_numbered(rows), ROWS)


WRITERS = {WAITING: _waiting, COST: _cost, OFFICES: _offices, TEAM: _team, QUOTA: _quota}


def answer(command: str, view, scope: str, now_ms: float, language: str) -> str:
    """The text to send back for one command, in one language. Only the fields named here and in board/summary.py go out, and without
    the "people" scope no line is about one person. A command that reads no numbers gets the list of commands.
    The first line never names a person: it is what a phone shows on its lock screen.
    Chữ gửi lại cho một lệnh, bằng một ngôn ngữ. Chỉ các trường nêu ở đây và trong board/summary.py đi ra, và không có phạm vi "people"
    thì không dòng nào nói về riêng một người. Lệnh không đọc số liệu thì nhận danh sách lệnh.
    Dòng đầu không bao giờ có tên người: đó là thứ điện thoại hiện trên màn hình khoá."""
    with speaking(language):
        if command in WRITERS:
            snap = snapshot(view, scope, now_ms)
            body = WRITERS[command](snap, scope == SCOPE_PEOPLE, now_ms) if snap.people else ["%s %s" % (EMPTY, tx("No computer has sent numbers yet."))]
            lines = ["%s · %s" % (HEADER, snap.at.strftime("%H:%M")), ""] + body
        else:
            names = VI_NAMES if language == "vi" else {}
            lines = [HEADER, "", tx("Tap a button, or send one of these:")] + ["%s /%s - %s" % (ICONS[c], names.get(c, c), text) for c, text in _menu_pairs()]
    return "\n".join(lines)[:TEXT_LIMIT]
