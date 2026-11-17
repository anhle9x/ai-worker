"""The wall view read into plain numbers, for whatever answers a question about the board from outside its own pages: the MCP endpoint
(board/mcp.py) and the Telegram answers (board/ask.py). Both say the same things, so both count, group and clean names here.
Pure: no sockets, no database, no keys. The caller passes the wall view, which holds no email, IP or device id.
  Phần treo tường đọc thành các con số thường, cho mọi thứ trả lời câu hỏi về bảng từ bên ngoài các trang của bảng: cổng MCP
  (board/mcp.py) và các câu trả lời qua Telegram (board/ask.py). Hai bên nói cùng những điều, nên cùng đếm, gộp và lọc tên ở đây.
  Mã thuần: không socket, không cơ sở dữ liệu, không khoá. Bên gọi đưa phần treo tường, vốn không có email, IP hay mã máy."""

import math
import re
from datetime import datetime, timezone
from typing import NamedTuple, Optional

# what a key or a chat may read: each person's row, or the team and office totals only
# một khoá hay một chat được đọc gì: dòng của từng người, hoặc chỉ số gộp của cả đội và từng văn phòng
SCOPE_PEOPLE, SCOPE_TOTALS = "people", "totals"
# with totals, offices smaller than this share one row, so a row never is one person's numbers
# với số gộp, các văn phòng nhỏ hơn ngần này dùng chung một dòng, để một dòng không là số của riêng một người
SMALL_OFFICE = 3
NAME_LIMIT = 40
STATES = ("working", "waiting", "open", "offline")


def num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else 0.0


def round_half_up(v: float) -> int:
    """Half goes up, as on the plugin's side; Python's round() sends a half to the even number.
    Nửa thì làm tròn lên, như phía plugin; round() của Python đưa nửa về số chẵn."""
    return int(math.floor(v + 0.5))


def money(v: float) -> str:
    return "%.2f" % v


def clean_name(v) -> str:
    """A name as one short piece of plain text: letters of any language, digits, spaces and a few marks. Anything else, the column
    bar and line breaks included, becomes a space, so a name cannot add a row or pass for a line of its own.
    This makes a planted instruction harder to write, not impossible: the tool's description still calls every name data.
    Tên thành một đoạn chữ thường ngắn: chữ cái của mọi ngôn ngữ, chữ số, dấu cách và vài dấu. Mọi thứ khác, kể cả dấu gạch đứng
    và dấu xuống dòng, thành dấu cách, để một cái tên không thêm được dòng hay giả làm một dòng riêng.
    Việc này làm câu lệnh cài cắm khó viết hơn chứ không chặn hẳn: mô tả công cụ vẫn gọi mọi cái tên là dữ liệu."""
    text = "".join(ch if ch.isalnum() or ch in " .-_'()" else " " for ch in v) if isinstance(v, str) else ""
    return " ".join(text.split())[:NAME_LIMIT].strip() or "?"


def model_label(model_id: str) -> str:
    """claude-fable-5-2 reads as Fable 5.2; any other id is kept, cut down to the characters a model id is made of.
    claude-fable-5-2 đọc thành Fable 5.2; mã khác thì giữ, rút về các ký tự mà một mã mô hình dùng."""
    m = re.match(r"claude-([a-z]+)-(\d+)-(\d+)", model_id)
    return "%s %s.%s" % (m.group(1).capitalize(), m.group(2), m.group(3)) if m else re.sub(r"[^A-Za-z0-9._:-]", "", model_id)[:NAME_LIMIT] or "-"


def state_of(p: dict) -> str:
    status = p.get("status")
    return status if isinstance(status, str) and status in STATES else "offline"


def count(people: list, state: str) -> int:
    return sum(1 for p in people if state_of(p) == state)


def total(people: list, field: str) -> float:
    return sum(num(p.get(field)) for p in people)


def quota_pct(p: dict, kind: str) -> Optional[int]:
    """How much of one quota window a person has used, in percent, or None when the board does not know.
    Một người đã dùng bao nhiêu phần trăm của một khung hạn mức, hoặc None khi bảng không biết."""
    quota = p.get("quota")
    windows = quota.get("windows") if isinstance(quota, dict) else None
    for w in windows if isinstance(windows, list) else []:
        if isinstance(w, dict) and w.get("kind") == kind and isinstance(w.get("pct"), (int, float)) and not isinstance(w.get("pct"), bool):
            return round_half_up(w["pct"])
    return None


def top_model(p: dict) -> str:
    models = p.get("models")
    if not isinstance(models, dict) or not models:
        return "-"
    top = sorted(models.items(), key=lambda item: -num(item[1]))[0][0]
    return model_label(top) if isinstance(top, str) else "-"


def minutes_waiting(p: dict, now_ms: float) -> Optional[int]:
    """Whole minutes a person has waited for an answer, or None when they are not waiting or the start is unknown.
    Số phút tròn một người đã chờ trả lời, hoặc None khi họ không chờ hoặc không rõ lúc bắt đầu."""
    since = num(p.get("waitingSince"))
    return max(0, round_half_up((now_ms - since) / 60000)) if state_of(p) == "waiting" and since else None


class Office(NamedTuple):
    """One row of offices. name is "" for people with no office; merged marks the one row that stands for every small office.
    Một dòng văn phòng. name là "" với người chưa xếp văn phòng; merged đánh dấu dòng duy nhất đứng thay mọi văn phòng nhỏ."""
    name: str
    people: list
    merged: bool = False


class Snapshot(NamedTuple):
    people: list
    # the office of each person, in the same order as people; "" when the person has none
    # văn phòng của từng người, cùng thứ tự với people; "" khi người đó chưa có
    places: list
    # the office rows the scope may see: with totals, small offices come last as one merged row
    # các dòng văn phòng mà phạm vi được xem: với số gộp, các văn phòng nhỏ nằm cuối thành một dòng gộp
    offices: list
    # when the numbers were taken, already moved to the board's time zone
    # lúc lấy số liệu, đã chuyển sang múi giờ của bảng
    at: datetime
    tz_offset: float


def snapshot(view, scope: str, now_ms: float) -> Snapshot:
    """Read the wall view defensively: anything that is not the expected kind counts as missing. A scope that is not "people" reads totals.
    With totals, small offices share one row; a team or a leftover group of one or two people still shows through the totals.
    Đọc phần treo tường một cách dè chừng: thứ gì không đúng kiểu mong đợi thì coi như thiếu. Phạm vi khác "people" thì đọc số gộp.
    Với số gộp, các văn phòng nhỏ dùng chung một dòng; một đội hay một nhóm còn lại chỉ một hai người thì vẫn lộ qua số gộp."""
    view = view if isinstance(view, dict) else {}
    people = [p for p in view.get("people") or [] if isinstance(p, dict)] if isinstance(view.get("people"), list) else []
    names = {}
    for b in view.get("branches") if isinstance(view.get("branches"), list) else []:
        if isinstance(b, dict) and isinstance(b.get("id"), str):
            names[b["id"]] = clean_name(b.get("name") or b["id"])
    places = [names.get(p.get("branch") if isinstance(p.get("branch"), str) else "", "") for p in people]
    order = []
    for place in places:
        if place not in order:
            order.append(place)
    offices, small = [], []
    for name in order:
        here = [p for p, place in zip(people, places) if place == name]
        if scope == SCOPE_PEOPLE or len(here) >= SMALL_OFFICE:
            offices.append(Office(name, here))
        else:
            small += here
    if small:
        offices.append(Office("", small, merged=True))
    # the view comes from this server, but a time that cannot be a date must not stop the answer
    # phần xem do chính máy chủ này đưa, nhưng một mốc giờ không thể là ngày tháng thì không được làm hỏng câu trả lời
    offset = max(-14.0, min(14.0, num(view.get("tzOffsetHours"))))
    at = num(view.get("updatedAt"))
    at = at if 0 < at < 4e12 else now_ms
    return Snapshot(people, places, offices, datetime.fromtimestamp(at / 1000 + offset * 3600, timezone.utc), offset)
