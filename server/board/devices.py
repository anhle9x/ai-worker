"""Numbers sent by each computer: checking, cleaning, saving and grouping them by person.
Số liệu từng máy gửi: kiểm, làm sạch, lưu và gộp theo người."""

import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from datetime import date, datetime, timedelta

from board import devicestore, order, settings, turns
from board.db import data_db, dumps
from board.settings import (
    CONNECTOR_OFFLINE_SECONDS,
    CONNECTOR_TOOLS,
    CONNECTOR_WORKING_SECONDS,
    DEVICE_NAME_RE,
    INGEST_BURST,
    INGEST_PER_SECOND,
    IP_HISTORY_MAX,
    FULL_BOOK_SECONDS,
    KEEP_DAYS,
    LOCAL_TZ,
    MAX_DEVICES,
    MAX_HOURS_PER_DEVICE,
    NEW_DEVICES_PER_IP,
    OFFLINE_SECONDS,
    RECEIVER_FAST_APPLY,
    REORDER_WINDOW_MS,
)


def key_matches(header: str, key: str) -> bool:
    ingest_times = header[7:] if header.startswith("Bearer ") else ""
    return bool(key) and hmac.compare_digest(ingest_times.encode(), key.encode())


def is_valid_payload(d) -> bool:
    return (
        isinstance(d, dict)
        and d.get("v") in (1, 2)
        and isinstance(d.get("device"), str)
        and DEVICE_NAME_RE.match(d["device"]) is not None
        and isinstance(d.get("updatedAt"), (int, float))
    )


def refuse_constant(name: str):
    """json.loads calls this for NaN and Infinity, which are not valid JSON.
    json.loads gọi hàm này với NaN và Infinity, là những giá trị không hợp lệ trong JSON."""
    raise ValueError(name)


def clean_number(v, high: float = 1e15):
    """A finite number from 0 to high, or None. True and False are not numbers here.
    Một số hữu hạn từ 0 tới high, hoặc None. True và False không tính là số."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        return v if math.isfinite(v) and 0 <= v <= high else None
    except OverflowError:
        return None


def clean_text(v, limit: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", v)[:limit] if isinstance(v, str) else ""


def clean_counts(v, keys=None, max_keys: int = 16, key_limit: int = 24) -> dict:
    """A small table of numbers: anything else in it is dropped.
    Một bảng số nhỏ: mọi thứ khác trong đó đều bị bỏ."""
    out = {}
    if isinstance(v, dict):
        for k, n in v.items():
            n = clean_number(n)
            if n is not None and isinstance(k, str) and len(k) <= key_limit and (keys is None or k in keys) and len(out) < max_keys:
                out[k] = n
    return out


def clean_hours(v, now_ms: float, keys=None, oldest_hour=None, keep_empty: bool = False) -> dict:
    """Numbers per hour, newest hours kept. A real hour number only, up to one day ahead for a wrong clock.
    oldest_hour drops older hours; keep_empty keeps an hour that cleans to nothing, as an empty table (v: 2: that hour is now empty).
    Số liệu theo giờ, giữ các giờ mới nhất. Chỉ nhận số giờ thật, tối đa sớm hơn một ngày cho đồng hồ lệch.
    oldest_hour bỏ các giờ cũ hơn; keep_empty giữ giờ làm sạch xong không còn gì, dưới dạng bảng rỗng (v: 2: giờ đó giờ đã rỗng)."""
    out = {}
    if isinstance(v, dict):
        top = int(now_ms / 3_600_000) + 24
        hours = [k for k in v if isinstance(k, str) and re.fullmatch(r"[0-9]{1,8}", k) and int(k) <= top
                 and (oldest_hour is None or int(k) >= oldest_hour)]
        for k in sorted(hours, key=int)[-MAX_HOURS_PER_DEVICE:]:
            table = clean_counts(v[k], keys)
            if table or keep_empty:
                out[k] = table
    return out


def clean_ledger_hours(v, now_ms: float, oldest_hour=None, keep_empty: bool = False) -> dict:
    """Spend per hour. Money is a whole number of millionths of a dollar (usdMicro), so sums are exact and the same in any language;
    a v: 1 send has only dollars (usd), turned into usdMicro here. usd is kept beside it, worked out from usdMicro, for older versions.
    Chi tiêu theo giờ. Tiền là số nguyên phần triệu đô la (usdMicro), để cộng ra đúng tuyệt đối và như nhau ở mọi ngôn ngữ;
    gói v: 1 chỉ có đô la (usd), được đổi sang usdMicro ở đây. usd vẫn giữ bên cạnh, tính từ usdMicro, cho các bản cũ."""
    out = clean_hours(v, now_ms, None, oldest_hour, keep_empty)
    for table in out.values():
        micro = table.get("usdMicro")
        micro = int(round(micro)) if micro is not None else int(round(table.get("usd", 0) * 1_000_000))
        table.pop("usd", None)
        table.pop("usdMicro", None)
        if micro or table:
            table["usdMicro"] = micro
            table["usd"] = micro / 1_000_000
    return out if keep_empty else {hour: table for hour, table in out.items() if table}


def ledger_micro(v: dict) -> int:
    """The money of one ledger hour in usdMicro, for a cleaned hour or an older one that has only usd.
    Tiền của một giờ trong sổ, theo usdMicro, cho giờ đã làm sạch hoặc giờ cũ chỉ có usd."""
    micro = v.get("usdMicro")
    if isinstance(micro, int) and not isinstance(micro, bool):
        return micro
    usd = v.get("usd")
    return int(round(usd * 1_000_000)) if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0


SESSION_COUNTS = ("openSessions", "working", "waiting")
# secret: text for ChatGPT or Gemini held a secret, not sent; commit: a commit that adds a secret, asked first;
# risky: a command that destroys work or weakens the computer, asked first; page: a page tried to steer Claude
# secret: chữ gửi ChatGPT hay Gemini có bí mật, không gửi; commit: commit thêm bí mật, hỏi trước;
# risky: lệnh phá huỷ công việc hay làm yếu máy, hỏi trước; page: một trang cố lái Claude
# answer: an answer from ChatGPT, Gemini or Gemma held a secret, text aimed at an AI or a command that cannot be undone
# answer: câu trả lời của ChatGPT, Gemini hay Gemma có bí mật, chữ nhắm vào AI hay lệnh không hoàn tác được
BLOCK_KINDS = ("secret", "commit", "risky", "page", "answer")

# The record of one piece of work handed to a helper, as a computer sends it: a fixed list of fields and values.
# Never the prompt or the answer; the fingerprint is salted on the computer, so it cannot be matched to a guessed text here.
# Biên bản của một việc giao cho trợ lý, như máy gửi lên: danh sách trường và giá trị cố định.
# Không bao giờ có đề bài hay câu trả lời; dấu vân tay có muối trên máy, nên ở đây không so được với một câu đoán thử.
DELEGATION_TOOLS = {"ask_chatgpt": "chatgpt", "ask_gemini": "gemini", "generate_image": "gemini", "ask_local": "gemma"}
DELEGATION_OUTCOMES = ("ok", "error", "refused", "declined")
DELEGATION_CHECKS = ("secret", "aimed", "command")
DELEGATION_VIA = ("plugin", "ai-workers")
MAX_DELEGATIONS = 100
DELEGATION_MAX_AGE_MS = 3 * 86_400_000


def clean_delegations(v, now_ms: float) -> list:
    """The records of work handed to helpers, rebuilt from a fixed list; anything else, too old or from the future is dropped.
    Các biên bản giao việc cho trợ lý, dựng lại từ danh sách cố định; mọi thứ khác, quá cũ hay ở tương lai đều bị bỏ."""
    out = []
    for d in v[-MAX_DELEGATIONS:] if isinstance(v, list) else ():
        if not isinstance(d, dict):
            continue
        rid, tool, at = d.get("id"), d.get("tool"), clean_number(d.get("at"))
        # a tool that is not text (a list, a table) cannot be looked up in DELEGATION_TOOLS: it used to stop the whole send with an error
        # công cụ không phải chữ (một danh sách, một bảng) không tra được trong DELEGATION_TOOLS: trước đây nó làm cả lần gửi dừng vì lỗi
        if not (isinstance(rid, str) and re.fullmatch(r"[0-9a-f]{24}", rid) and isinstance(tool, str) and tool in DELEGATION_TOOLS and at is not None):
            continue
        if not now_ms - DELEGATION_MAX_AGE_MS < at < now_ms + 86_400_000:
            continue
        digest = d.get("promptHash")
        found = d.get("found") if isinstance(d.get("found"), list) else []
        checks = d.get("check") if isinstance(d.get("check"), list) else []
        out.append({
            "id": rid, "at": int(at), "tool": tool, "worker": DELEGATION_TOOLS[tool],
            "via": d.get("via") if d.get("via") in DELEGATION_VIA else "plugin",
            "promptChars": int(clean_number(d.get("promptChars"), 10_000_000) or 0),
            "answerChars": int(clean_number(d.get("answerChars"), 100_000_000) or 0),
            "promptHash": digest if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{32}", digest) else "",
            "outcome": d.get("outcome") if d.get("outcome") in DELEGATION_OUTCOMES else "error",
            "check": [c for c in DELEGATION_CHECKS if c in checks],
            # the kinds of secret the plugin names, such as "GitHub token": short words only, never a value
            # các loại bí mật plugin gọi tên, như "GitHub token": chỉ chữ ngắn, không bao giờ có giá trị
            "found": sorted({f for f in found[:8] if isinstance(f, str) and re.fullmatch(r"[A-Za-z][A-Za-z .]{1,39}", f)}),
        })
    return out


def book_of(m: dict) -> dict:
    """The hour book a record carries in itself: {"ledger", "tasks", "blocks"?}, each {hour: table}: a send, or a dict made by hand.
    A record DeviceCache holds carries none: its book is in device_hours (read_book), its sums in hours_of and blocks_of.
    Sổ giờ một bản ghi tự mang trong nó: {"ledger", "tasks", "blocks"?}, mỗi loại {giờ: bảng}: một lần gửi, hay một dict tự dựng.
    Bản ghi DeviceCache đang giữ không mang sổ: sổ của nó nằm trong device_hours (read_book), các tổng trong hours_of và blocks_of."""
    out = {}
    for kind in HOUR_KINDS:
        table = m.get(kind) if isinstance(m, dict) else None
        if isinstance(table, dict):
            out[kind] = table
    return out


def blocks_of(m: dict) -> dict:
    """The blocks hours of a record: for one DeviceCache holds, those of its last BLOCK_HOURS hours, kept with it.
    Các giờ blocks của một bản ghi: với bản ghi DeviceCache đang giữ, là các giờ trong BLOCK_HOURS giờ cuối, giữ cùng nó."""
    kept = DEVICES.summaries.get(id(m))
    if kept and kept[0] is m:
        return kept[1]["blocks"]
    return book_of(m).get("blocks") or {}


def blocks_since(devices: list, from_hour: int) -> dict:
    """The whole team's counts of each kind from that hour on, every computer added up: no person, no computer.
    Số đếm từng loại của cả team từ giờ đó trở đi, cộng mọi máy: không có người, không có máy."""
    out = dict.fromkeys(BLOCK_KINDS, 0)
    for m in devices:
        for hour, v in blocks_of(m).items():
            if not (isinstance(hour, str) and hour.isdigit() and int(hour) >= from_hour and isinstance(v, dict)):
                continue
            for kind in BLOCK_KINDS:
                n = v.get(kind)
                if isinstance(n, int) and not isinstance(n, bool) and 0 < n < 100000:
                    out[kind] += n
    return out


def from_connector(m: dict) -> bool:
    """Whether a report comes from the connector for other coding tools, not from the Claude Code plugin: only the connector sends a "tools" table.
    Báo cáo này đến từ bộ nối cho các công cụ lập trình khác, không phải từ plugin Claude Code: chỉ bộ nối gửi bảng "tools"."""
    return isinstance(m.get("tools"), dict)


def is_fresh(m: dict, now: float) -> bool:
    """Whether a report still says what its computer is doing: 12 minutes for the plugin, which sends on a beat;
    longer for the connector, which sends only on an event.
    Báo cáo còn nói đúng máy đang làm gì hay không: 12 phút với plugin, vì plugin gửi theo nhịp;
    lâu hơn với bộ nối, vì bộ nối chỉ gửi khi có sự kiện."""
    return now - m["updatedAt"] / 1000 < (CONNECTOR_OFFLINE_SECONDS if from_connector(m) else OFFLINE_SECONDS)


def _clean_seq(d: dict, out: dict, now_ms: float) -> None:
    # the number the plugin gives its sends, so they keep their order when the computer's clock goes back (board/order.py): a whole number,
    # no further ahead than a day, as for updatedAt
    # số plugin đánh cho các lần gửi, để chúng giữ thứ tự khi đồng hồ của máy lùi lại (board/order.py): một số nguyên, không vượt quá một
    # ngày phía trước, như với updatedAt
    seq = clean_number(d.get("seq"))
    if isinstance(seq, int):
        out["seq"] = min(seq, int(now_ms) + 86_400_000)


def clean_payload(d, now: float):
    """Rebuild what a device sent from a fixed list of fields, types and sizes; None if it is not a device report.
    Runs on /ingest and again when a row is loaded from the table into memory, so one bad row cannot take down the pages for everyone.
    Dựng lại số liệu một máy gửi từ danh sách cố định các trường, kiểu và cỡ; None nếu không phải báo cáo của máy.
    Chạy ở /ingest và lại chạy khi một dòng được nạp từ bảng vào bộ nhớ, để một dòng xấu không làm sập trang của mọi người.
    A field added here goes into _clean_again too, at the same place.
    Trường thêm ở đây cũng phải thêm vào _clean_again, ở cùng chỗ."""
    now_ms = now * 1000
    if not is_valid_payload(d):
        return None
    updated_at = clean_number(d["updatedAt"])
    if updated_at is None:
        return None
    out = {"v": 1, "device": d["device"], "updatedAt": min(updated_at, now_ms + 86_400_000)}
    _clean_seq(d, out, now_ms)
    for field, limit in (("name", 120), ("account", 120), ("enteredAccount", 120), ("lanIp", 45), ("ip", 45), ("pluginVersion", 20)):
        text = clean_text(d.get(field), limit)
        if text:
            out[field] = text
    for field in SESSION_COUNTS:
        out[field] = int(clean_number(d.get(field), 100000) or 0)
    # a report from the connector for other coding tools: session counts per tool, tool names from a fixed list.
    # The totals are added up here, so they always agree with the parts.
    # báo cáo của bộ nối cho các công cụ lập trình khác: số phiên theo từng công cụ, tên công cụ theo danh sách cố định.
    # Tổng được cộng ở đây, nên luôn khớp với từng phần.
    if isinstance(d.get("tools"), dict):
        out["tools"] = {}
        for tool in CONNECTOR_TOOLS:
            counts = d["tools"].get(tool)
            if isinstance(counts, dict):
                out["tools"][tool] = {field: int(clean_number(counts.get(field), 100000) or 0) for field in SESSION_COUNTS}
        for field in SESSION_COUNTS:
            out[field] = sum(counts[field] for counts in out["tools"].values())
    # one-way hash of the hardware id: the same computer even when a reinstalled plugin gets a new device id
    # dấu phần cứng đã băm một chiều: cùng máy vật lý dù plugin cài lại có mã máy mới
    if isinstance(d.get("hardwareMark"), str) and re.fullmatch(r"[0-9a-f]{32}", d["hardwareMark"]):
        out["hardwareMark"] = d["hardwareMark"]
    # IP history written by the server (ingest replaces whatever the device sent)
    # lịch sử IP do máy chủ ghi (ingest ghi đè phần máy gửi lên)
    history = []
    for e in d.get("ipHistory") if isinstance(d.get("ipHistory"), list) else []:
        if isinstance(e, dict) and clean_text(e.get("ip"), 45) and clean_number(e.get("from")) is not None and clean_number(e.get("to")) is not None:
            history.append({"ip": clean_text(e["ip"], 45), "from": e["from"], "to": e["to"]})
    if history:
        out["ipHistory"] = history[:IP_HISTORY_MAX]
    workers = ("gemini", "chatgpt", "gemma")
    out["delegating"] = clean_counts(d.get("delegating"), workers)
    out["models"] = clean_counts(d.get("models"), None, 20, 79)
    out["subagents"] = clean_counts(d.get("subagents"), None, 10, 40)
    # v: 1 carries the whole hour book at the top; v: 2 carries in "hours" only the hours that changed (or all of them with full: true),
    # an hour that is now empty as an empty table. What comes out is always v: 1: merge_hours puts a v: 2 send on the book already kept
    # v: 1 mang cả sổ giờ ở ngoài cùng; v: 2 mang trong "hours" chỉ các giờ đã đổi (hoặc mọi giờ khi full: true),
    # giờ nay đã rỗng là một bảng rỗng. Thứ đi ra luôn là v: 1: merge_hours đặt gói v: 2 lên sổ đang giữ
    second = d["v"] == 2
    book = d.get("hours") if second else d
    book = book if isinstance(book, dict) else {}
    oldest = int(now_ms / 3_600_000) - MAX_HOURS_PER_DEVICE if second else None
    out["ledger"] = clean_ledger_hours(book.get("ledger"), now_ms, oldest, second)
    out["tasks"] = clean_hours(book.get("tasks"), now_ms, workers, oldest, second)
    # what ai-worker stopped or put to the person on that computer, by hour: counts of a fixed list of kinds, never what it was
    # những gì ai-worker đã chặn hay đưa người dùng xem trên máy đó, theo giờ: số đếm của một danh sách loại cố định, không bao giờ là nội dung
    blocks = clean_hours(book.get("blocks"), now_ms, BLOCK_KINDS, oldest, second)
    if blocks:
        out["blocks"] = blocks
    assistants = d.get("assistants")
    if isinstance(assistants, dict):
        out["assistants"] = {"chatgpt": assistants.get("chatgpt") is True, "gemini": assistants.get("gemini") is True,
                             "gemma": clean_text(assistants.get("gemma"), 40), "chatgptModel": clean_text(assistants.get("chatgptModel"), 60),
                             "geminiModel": clean_text(assistants.get("geminiModel"), 60)}
    quota = d.get("quota")
    if isinstance(quota, dict) and clean_number(quota.get("readAt")) is not None and isinstance(quota.get("windows"), list):
        windows = []
        for w in quota["windows"][:5]:
            if isinstance(w, dict) and isinstance(w.get("kind"), str) and clean_number(w.get("pct"), 999) is not None:
                entry = {"kind": w["kind"][:30], "pct": w["pct"]}
                if clean_number(w.get("resetsAt")) is not None:
                    entry["resetsAt"] = w["resetsAt"]
                windows.append(entry)
        out["quota"] = {"readAt": quota["readAt"], "windows": windows}
    return out


# the fields a send of the receiver gets from this server after clean_payload (board/receiver.py, save_ingest), with their limits
# các trường mà lần gửi của bộ nhận nhận từ máy chủ này sau clean_payload (board/receiver.py, save_ingest), kèm giới hạn
_SET_AFTER = {"name": 120, "account": 120, "ip": 45}


def _clean_again(d: dict, now: float):
    """clean_payload(d, now) without its hours, for a d that came out of clean_payload and since got only name, account, ip and ipHistory
    (and its hours): those are cleaned again, every other field is taken as it is, since cleaning a cleaned field gives it back unchanged.
    The fields come in the same order. server/test_apply_paths.py checks that both give the same.
    clean_payload(d, now) không kèm sổ giờ, cho d đã ra từ clean_payload và từ đó chỉ được đặt name, account, ip và ipHistory (cùng
    các giờ của nó): các trường đó được làm sạch lại, mọi trường khác lấy nguyên, vì làm sạch một trường đã sạch cho lại đúng nó.
    Các trường đi ra cùng thứ tự. server/test_apply_paths.py kiểm hai cách cho cùng kết quả."""
    if not is_valid_payload(d):
        return None
    updated_at = clean_number(d["updatedAt"])
    if updated_at is None:
        return None
    out = {"v": 1, "device": d["device"], "updatedAt": min(updated_at, now * 1000 + 86_400_000)}
    _clean_seq(d, out, now * 1000)
    for field in ("name", "account", "enteredAccount", "lanIp", "ip", "pluginVersion"):
        text = clean_text(d.get(field), _SET_AFTER[field]) if field in _SET_AFTER else d.get(field)
        if text:
            out[field] = text
    for field in SESSION_COUNTS:
        out[field] = d[field]
    for field in ("tools", "hardwareMark"):
        if field in d:
            out[field] = d[field]
    history = []
    for e in d.get("ipHistory") if isinstance(d.get("ipHistory"), list) else []:
        if isinstance(e, dict) and clean_text(e.get("ip"), 45) and clean_number(e.get("from")) is not None and clean_number(e.get("to")) is not None:
            history.append({"ip": clean_text(e["ip"], 45), "from": e["from"], "to": e["to"]})
    if history:
        out["ipHistory"] = history[:IP_HISTORY_MAX]
    for field in ("delegating", "models", "subagents", "assistants", "quota"):
        if field in d:
            out[field] = d[field]
    return out


def add_ip_history(old: list, ip: str, at_ms: float) -> list:
    """Add this send to a device's IP history: one row per IP (from, to), rows older than KEEP_DAYS dropped, the newest IP_HISTORY_MAX kept.
    Thêm lần gửi này vào lịch sử IP của máy: mỗi IP một dòng (từ lúc, tới lúc), bỏ dòng quá KEEP_DAYS, giữ IP_HISTORY_MAX dòng mới nhất."""
    out = [dict(e) for e in old if at_ms - e["to"] < KEEP_DAYS * 86_400_000 and e["ip"] != ip]
    same = [e for e in old if e["ip"] == ip]
    out.append({"ip": ip, "from": min([e["from"] for e in same] + [at_ms]), "to": at_ms})
    return sorted(out, key=lambda e: -e["to"])[:IP_HISTORY_MAX]


_EPOCH_DAY = date(1970, 1, 1).toordinal()
_TZ_SECONDS = int(LOCAL_TZ.utcoffset(None).total_seconds())
_WORKERS = ("gemini", "chatgpt", "gemma")


def local_day_of_hour(hour: int) -> date:
    """The local day an hour number (hours since 1970, UTC) falls in, by arithmetic: LOCAL_TZ is a fixed offset.
    Ngày địa phương mà một số giờ (số giờ từ 1970, giờ UTC) rơi vào, tính bằng số học: LOCAL_TZ là độ lệch cố định."""
    return date.fromordinal(_EPOCH_DAY + (hour * 3600 + _TZ_SECONDS) // 86400)


def hours_of(m: dict) -> dict:
    """One device's hourly numbers, added up: per local day, and the hours newest first for the last-24-hours charts (money in usdMicro).
    A device kept by DeviceCache never changes, so its summary is kept with it: the days come from device_days and only the hours near its
    last send are in memory (see RECENT_HOURS). Any other dict is added up afresh from its own book.
    Số liệu theo giờ của một máy, đã cộng: theo từng ngày địa phương, và các giờ mới trước cũ sau cho biểu đồ 24 giờ (tiền theo usdMicro).
    Máy giữ trong DeviceCache không bao giờ đổi, nên bản cộng của nó được giữ cùng nó: các ngày lấy từ device_days và chỉ các giờ gần
    lần gửi cuối nằm trong bộ nhớ (xem RECENT_HOURS). Dict khác thì được cộng lại từ đầu từ chính sổ của nó."""
    kept = DEVICES.summaries.get(id(m))
    if kept and kept[0] is m:
        return kept[1]
    return add_up_hours(m)


def add_up_hours(m: dict) -> dict:
    return _add_up(book_of(m))


def _add_up(book: dict, only=None) -> dict:
    """Add up a book's ledger and tasks hours per local day (only those days when only is a set), with the lists of hours newest first.
    Cộng các giờ ledger và tasks của một sổ theo từng ngày địa phương (chỉ các ngày đó khi only là một tập), kèm danh sách giờ mới trước."""
    days, ledger_hours, task_hours = {}, [], []
    for field in ("ledger", "tasks"):
        for hour, v in (book.get(field) or {}).items():
            if not isinstance(v, dict):
                continue
            try:
                h = int(hour)
                day = local_day_of_hour(h)
            except (ValueError, OverflowError, TypeError):
                continue
            if only is not None and day not in only:
                continue
            r = days.setdefault(day, {"usd": 0, "tokensIn": 0, "tokensOut": 0, "gemini": 0, "chatgpt": 0, "gemma": 0})
            if field == "ledger":
                # added up in whole usdMicro, turned into dollars once at the end: the same sum in any order and in any language
                # cộng bằng số nguyên usdMicro, đổi ra đô la một lần ở cuối: cùng một tổng dù cộng theo thứ tự nào, ở ngôn ngữ nào
                micro = ledger_micro(v)
                r["usd"] += micro
                r["tokensIn"] += int(v.get("input") or 0) + int(v.get("cacheRead") or 0) + int(v.get("cacheWrite") or 0)
                r["tokensOut"] += int(v.get("output") or 0)
                ledger_hours.append((h, micro))
            else:
                counts = [int(v.get(worker) or 0) for worker in _WORKERS]
                for worker, n in zip(_WORKERS, counts):
                    r[worker] += n
                task_hours.append((h, counts))
    for r in days.values():
        r["usdMicro"] = r["usd"]
        r["usd"] = r["usd"] / 1_000_000
    ledger_hours.sort(key=lambda x: -x[0])
    task_hours.sort(key=lambda x: -x[0])
    return {"days": days, "ledgerHours": ledger_hours, "taskHours": task_hours}


def today_first_hour(now: float) -> int:
    """The first hour number of the local day now falls in.
    Số giờ đầu tiên của ngày địa phương mà lúc này rơi vào."""
    return _day_hours(datetime.fromtimestamp(now, LOCAL_TZ).date())[0]


def zone_seconds() -> int:
    """The offset from UTC, in seconds, the days are counted in (TZ_OFFSET).
    Độ lệch so với UTC, tính bằng giây, mà các ngày được đếm theo (TZ_OFFSET)."""
    return _TZ_SECONDS


def _day_hours(day: date) -> tuple:
    """The hour numbers (lo, hi) of one local day: lo <= hour < hi. The offset may be a part of an hour.
    Các số giờ (lo, hi) của một ngày địa phương: lo <= giờ < hi. Độ lệch có thể là một phần của giờ."""
    n = day.toordinal() - _EPOCH_DAY
    return -((_TZ_SECONDS - n * 86400) // 3600), -((_TZ_SECONDS - (n + 1) * 86400) // 3600)


def _day_row(device: str, day: date, v: dict) -> tuple:
    return (day.isoformat(), device, v["usdMicro"], v["tokensIn"], v["tokensOut"], v["gemini"], v["chatgpt"], v["gemma"])


def _day_numbers(row) -> dict:
    micro, tokens_in, tokens_out, gemini, chatgpt, gemma = (int(x or 0) for x in row)
    return {"usd": micro / 1_000_000, "tokensIn": tokens_in, "tokensOut": tokens_out, "gemini": gemini, "chatgpt": chatgpt, "gemma": gemma, "usdMicro": micro}


def _counts(v) -> list:
    return [int(v.get(worker) or 0) for worker in _WORKERS]


def _rows_to_book(rows) -> dict:
    """Rows (kind, hour, body) into a book {kind: {hour: table}}; a body that is not a table of JSON is left out.
    Các dòng (loại, giờ, nội dung) thành một sổ {loại: {giờ: bảng}}; nội dung không phải một bảng JSON thì bỏ qua."""
    book = {}
    for kind, hour, body in rows:
        try:
            table = json.loads(body)
        except (ValueError, RecursionError, TypeError):
            continue
        if isinstance(table, dict):
            book.setdefault(kind, {})[str(hour)] = table
    return book


# the hours of ledger and tasks DeviceCache keeps in memory for each computer, back from its last send: the board's charts show the last
# 24, and a computer's clock may be a day ahead. The whole book stays in device_hours (read_book)
# số giờ ledger và tasks mà DeviceCache giữ trong bộ nhớ cho mỗi máy, tính lùi từ lần gửi cuối: biểu đồ của bảng hiện 24 giờ gần nhất,
# và đồng hồ của máy có thể nhanh một ngày. Cả sổ vẫn nằm trong device_hours (read_book)
RECENT_HOURS = 48
# the hours of blocks it keeps: the board shows the last 7 days of them
# số giờ blocks nó giữ: bảng hiện 7 ngày gần nhất của chúng
BLOCK_HOURS = 8 * 24
# a send that changes nothing but its time and where it is now is written to the devices row at most this often; the memory always
# holds the newest, so only the last seconds before a crash are lost, and every computer sends again when BOOT_ID changes
# lần gửi không đổi gì ngoài thời điểm và nơi máy đang ở được ghi vào dòng devices nhiều nhất bấy lâu một lần; bộ nhớ luôn giữ bản mới
# nhất, nên chỉ mất vài giây cuối trước lúc sập, và mọi máy gửi lại khi BOOT_ID đổi
STATE_REWRITE_SECONDS = 60


def _window(m: dict, now: float) -> tuple:
    """The first hour of ledger and tasks, and of blocks, kept in memory for this record: back from its last send, or from now if that is
    earlier, so any board built from now on finds every hour it shows.
    Giờ đầu tiên của ledger và tasks, và của blocks, được giữ trong bộ nhớ cho bản ghi này: lùi từ lần gửi cuối, hoặc từ lúc này nếu sớm
    hơn, để mọi lần dựng bảng từ nay đều có đủ các giờ nó hiện."""
    anchor = min(int(now // 3600), int(m["updatedAt"] // 3_600_000))
    return anchor - RECENT_HOURS, anchor - BLOCK_HOURS


def _summary(days: dict, ledger: dict, tasks: dict, blocks: dict, lo: int, blo: int) -> dict:
    """What hours_of gives for a kept record: its days, and its hours from lo (blocks from blo) newest first.
    ledger is {hour: usdMicro}, tasks {hour: [gemini, chatgpt, gemma]}, blocks {hour: table}, the hours as numbers.
    Thứ hours_of trả cho một bản ghi đang giữ: các ngày của nó, và các giờ từ lo (blocks từ blo) mới trước cũ sau.
    ledger là {giờ: usdMicro}, tasks {giờ: [gemini, chatgpt, gemma]}, blocks {giờ: bảng}, giờ là số."""
    return {"days": days, "ledgerHours": sorted(((h, v) for h, v in ledger.items() if h >= lo), key=lambda x: -x[0]),
            "taskHours": sorted(((h, v) for h, v in tasks.items() if h >= lo), key=lambda x: -x[0]),
            "blocks": {str(h): blocks[h] for h in sorted(blocks) if h >= blo}, "from": lo, "blocksFrom": blo}


def _window_values(rows) -> tuple:
    """Rows (kind, hour, body) into the ledger, tasks and blocks values a summary keeps; a broken row is left out.
    Các dòng (loại, giờ, nội dung) thành các giá trị ledger, tasks và blocks mà một bản cộng giữ; dòng hỏng thì bỏ qua."""
    ledger, tasks, blocks = {}, {}, {}
    for kind, hour, body in rows:
        try:
            table = json.loads(body)
            if not isinstance(table, dict):
                continue
            if kind == "ledger":
                ledger[hour] = ledger_micro(table)
            elif kind == "tasks":
                tasks[hour] = _counts(table)
            elif kind == "blocks":
                blocks[hour] = table
        except (ValueError, RecursionError, TypeError):
            continue
    return ledger, tasks, blocks


def _steady(m: dict) -> tuple:
    """What a send changes besides its time: everything but updatedAt, and the IP history without the moment each address was last seen.
    Những gì một lần gửi làm đổi ngoài thời điểm: mọi thứ trừ updatedAt, và lịch sử IP bỏ lúc mỗi địa chỉ được thấy lần cuối."""
    rest = {k: v for k, v in m.items() if k not in ("updatedAt", "ipHistory")}
    return rest, [(e.get("ip"), e.get("from")) for e in m.get("ipHistory") or ()]


# the fields that say who and where a computer is: a change of them is written to its devices row at once, with the receiver too
# (see DeviceCache._write_state, late)
# các trường cho biết máy là của ai và ở đâu: khi chúng đổi thì ghi ngay vào dòng devices, kể cả khi có bộ nhận
# (xem DeviceCache._write_state, late)
IDENTITY_FIELDS = ("device", "name", "account", "enteredAccount", "lanIp", "ip", "pluginVersion", "hardwareMark", "assistants")
# how often state_loop writes the devices rows held back (see late)
# state_loop ghi các dòng devices đang để sau bao lâu một lần (xem late)
LATE_WRITE_SECONDS = 30


def _identity(m: dict) -> tuple:
    return tuple(m.get(k) for k in IDENTITY_FIELDS), [(e.get("ip"), e.get("from")) for e in m.get("ipHistory") or ()]


def write_book(c, device: str, book: dict, old_days=None, stamp=None) -> tuple:
    """Make device_hours and device_days hold this book for one computer, inside the caller's transaction: only the hours that differ from
    the rows there are written, only the days that change. old_days is the days kept in memory, or None to write them all again. stamp,
    the times of the send (order.Stamps), keeps every hour written by a newer send as it is, there or not in the book (board/order.py);
    None (the upgrade to version 6, a record replaced by hand) writes the book exactly. Returns (the days, the book now held).
    Làm cho device_hours và device_days chứa sổ này của một máy, trong giao dịch của bên gọi: chỉ ghi các giờ khác với dòng đang có, chỉ
    các ngày có đổi. old_days là các ngày đang giữ trong bộ nhớ, hoặc None để ghi lại tất cả. stamp, các thời điểm của lần gửi
    (order.Stamps), giữ nguyên mọi giờ do một lần gửi mới hơn ghi, dù có trong sổ hay không (board/order.py); None (lần nâng lên phiên bản
    6, bản ghi thay bằng tay) ghi đúng sổ. Trả về (các ngày, sổ đang giữ sau khi ghi)."""
    old = {(kind, hour): body for kind, hour, body in devicestore.hours(c, device, HOUR_KINDS)}
    kept = devicestore.stamps(c, device, HOUR_KINDS) if stamp is not None else {}
    new, older = {}, 0
    for kind in HOUR_KINDS:
        for hour, table in (book.get(kind) or {}).items():
            key = (kind, int(hour))
            if order.wins(stamp.of(*key), kept.get(key)) if stamp is not None else True:
                new[key] = dumps(table)
            elif key in old:
                new[key], older = old[key], older + 1
    for key, body in old.items():
        if key not in new and stamp is not None and not order.wins(stamp.of(*key), kept.get(key)):
            new[key], older = body, older + 1
    order.note_older(older)
    put = [(hour, kind, device, body) + ((stamp.of(kind, hour),) if stamp is not None else ()) for (kind, hour), body in new.items()
           if old.get((kind, hour)) != body]
    drop = [(hour, kind, device) for (kind, hour) in old if (kind, hour) not in new]
    devicestore.put_hours(c, put)
    devicestore.drop_hours(c, drop)
    if older:
        book = _rows_to_book([(kind, hour, body) for (kind, hour), body in new.items()])
    if old_days is None:
        days = _add_up(book)["days"]
        devicestore.drop_days_of(c, device)
        devicestore.put_days(c, [_day_row(device, day, v) for day, v in days.items()])
        return days, book
    touched = {local_day_of_hour(r[0]) for r in put + drop if r[1] != "blocks"}
    if not touched:
        return old_days, book
    fresh = _add_up(book, touched)["days"]
    days = {day: v for day, v in old_days.items() if day not in touched}
    days.update(fresh)
    _write_days(c, device, touched, fresh, old_days)
    return days, book


def _hour_numbers(kind: str, body: str) -> tuple:
    """What one stored ledger or tasks hour adds to its day, as _add_up adds it: (usdMicro, tokensIn, tokensOut, gemini, chatgpt, gemma),
    whole numbers. None if the body is not a table of JSON.
    Phần một giờ ledger hay tasks đã lưu cộng vào ngày của nó, đúng như _add_up cộng: (usdMicro, tokensIn, tokensOut, gemini, chatgpt,
    gemma), số nguyên. None nếu nội dung không phải một bảng JSON."""
    v = json.loads(body)
    if not isinstance(v, dict):
        return None
    if kind == "ledger":
        return (ledger_micro(v), int(v.get("input") or 0) + int(v.get("cacheRead") or 0) + int(v.get("cacheWrite") or 0),
                int(v.get("output") or 0), 0, 0, 0)
    return (0, 0, 0) + tuple(_counts(v))


_DAY_FIELDS = ("usdMicro", "tokensIn", "tokensOut", "gemini", "chatgpt", "gemma")


def _days_by_difference(days: dict, touched: set, changed: list):
    """The touched days moved by the hours that changed: each day kept, less what each hour held before, plus what it holds now, in
    whole numbers, so the result is what _add_up gives on the hours of those days. changed is [(kind, hour, body before or None,
    body now)], only hours written over or added. None when the result cannot be sure (a day not kept, a body that does not read,
    a number below zero): then the days are added up again from their hours.
    Các ngày bị chạm, dịch đi bằng các giờ đã đổi: mỗi ngày đang giữ, trừ những gì mỗi giờ có trước đó, cộng những gì nó có bây giờ,
    bằng số nguyên, để kết quả đúng như _add_up cho trên các giờ của các ngày đó. changed là [(loại, giờ, nội dung trước hoặc None,
    nội dung giờ)], chỉ các giờ được ghi đè hay thêm. None khi kết quả không chắc chắn (ngày không có trong bộ nhớ, nội dung không đọc
    được, số dưới không): khi đó các ngày được cộng lại từ các giờ của chúng."""
    try:
        sums = {}
        for kind, h, before, now in changed:
            day = local_day_of_hour(h)
            if day not in touched or day not in days:
                return None
            r = sums.get(day)
            if r is None:
                r = sums[day] = [days[day][k] for k in _DAY_FIELDS]
                if not all(isinstance(x, int) and not isinstance(x, bool) for x in r):
                    return None
            new = _hour_numbers(kind, now)
            old = _hour_numbers(kind, before) if before is not None else (0,) * 6
            if new is None or old is None:
                return None
            for i in range(6):
                r[i] += new[i] - old[i]
    except (ValueError, RecursionError, TypeError, OverflowError, KeyError):
        return None
    if set(sums) != touched or any(x < 0 for r in sums.values() for x in r):
        return None
    return {day: _day_numbers(r) for day, r in sums.items()}


def _write_days(c, device: str, touched: set, fresh: dict, old_days: dict) -> None:
    devicestore.put_days(c, [_day_row(device, day, fresh[day]) for day in touched if day in fresh and fresh[day] != old_days.get(day)])
    devicestore.drop_days(c, [(day.isoformat(), device) for day in touched if day not in fresh and day in old_days])


def _recount_days(c) -> None:
    """Count device_days again from every hour: TZ_OFFSET changed since they were counted.
    Đếm lại device_days từ mọi giờ: TZ_OFFSET đã đổi từ lần đếm trước."""
    devicestore.clear_days(c)
    rows = {}
    for device, kind, hour, body in devicestore.all_hours(c):
        rows.setdefault(device, []).append((kind, hour, body))
    for device, these in rows.items():
        days = _add_up(_rows_to_book(these))["days"]
        devicestore.put_days(c, [_day_row(device, day, v) for day, v in days.items()])
    devicestore.set_days_zone(c, _TZ_SECONDS)
    sys.stderr.write("counted the days of %d computers again in the time zone %+d s\n" % (len(rows), _TZ_SECONDS))


def _clean_state(body: str, now: float):
    """A devices row's body cleaned, without hour books; None if it is not a good record. An hour book in it is not read: since schema
    version 6 the books are in device_hours.
    Nội dung một dòng devices đã làm sạch, không có sổ giờ; None nếu không phải bản ghi tốt. Sổ giờ nằm trong đó thì không đọc: từ lược đồ
    phiên bản 6 sổ nằm trong device_hours."""
    try:
        cleaned = clean_payload(json.loads(body), now)
    except (ValueError, RecursionError, TypeError):
        return None
    if cleaned:
        for kind in HOUR_KINDS:
            cleaned.pop(kind, None)
    return cleaned


class DeviceCache:
    """Every computer's last send, cleaned once and kept in memory without its hour book: what it is doing, its totals per day, and its
    hours near its last send (RECENT_HOURS, BLOCK_HOURS). A send or a read of the board no longer cleans every device again, and a send
    writes only the hours that changed. The tables stay the record (board/devicestore.py); this is rebuilt from them when the server starts,
    when another program (such as --forget-device) changed the file, or when forget() is called after a write that did not go through it.
    Lần gửi mới nhất của mọi máy, làm sạch một lần rồi giữ trong bộ nhớ, không kèm sổ giờ: máy đang làm gì, tổng theo từng ngày, và các
    giờ gần lần gửi cuối (RECENT_HOURS, BLOCK_HOURS). Một lần gửi hay một lần đọc bảng không còn làm sạch lại mọi máy, và một lần gửi chỉ
    ghi các giờ đã đổi. Các bảng vẫn là bản gốc (board/devicestore.py); bản này dựng lại từ chúng khi máy chủ khởi động, khi chương trình
    khác (như --forget-device) đổi file, hoặc khi gọi forget() sau một lần ghi không đi qua nó."""

    def __init__(self):
        self.lock = threading.RLock()
        self.db = None
        self.version = None
        # device -> (seen_at, cleaned record without its hour book); a record is never changed in place, only replaced
        # máy -> (seen_at, bản ghi đã làm sạch không kèm sổ giờ); bản ghi không bao giờ bị sửa tại chỗ, chỉ bị thay
        self.devices = {}
        # person_key -> set of devices, so a send can look at one person's devices without going through everyone's
        # person_key -> tập máy, để một lần gửi xem được các máy của một người mà không phải đi qua máy của mọi người
        self.people = {}
        # id of a kept record -> (that record, its summary): see hours_of
        # id của một bản ghi đang giữ -> (bản ghi đó, bản cộng của nó): xem hours_of
        self.summaries = {}
        # device -> seen_at of its devices row as last written (see STATE_REWRITE_SECONDS)
        # máy -> seen_at của dòng devices của nó lúc ghi gần nhất (xem STATE_REWRITE_SECONDS)
        self.written = {}
        # device -> seen_at of a send of the receiver whose devices row is held back: only its state changed since a write less than
        # STATE_REWRITE_SECONDS ago. state_loop writes them every LATE_WRITE_SECONDS, so after a crash the table is at most about a
        # minute behind on what the computers are doing, never on who they are or what they spent (the hours are written at once)
        # máy -> seen_at của một lần gửi qua bộ nhận mà dòng devices đang để sau: chỉ trạng thái đổi kể từ lần ghi cách đây chưa tới
        # STATE_REWRITE_SECONDS. state_loop ghi chúng mỗi LATE_WRITE_SECONDS, nên sau khi sập bảng chậm nhiều nhất khoảng một phút về
        # việc các máy đang làm, không bao giờ về máy là của ai hay đã tiêu bao nhiêu (các giờ được ghi ngay)
        self.late = {}
        # the database while a batch is written inside its own write transaction (see pin): no other program can write it then
        # cơ sở dữ liệu trong lúc một lô được ghi bên trong giao dịch ghi của nó (xem pin): khi đó không chương trình nào khác ghi được
        self.pinned = None

    def pin(self):
        """For a batch written inside one write transaction (BEGIN IMMEDIATE): look at data_version once, at the start, instead of at
        each row; while the transaction holds the lock no other program can write. A context manager, under self.lock.
        Cho một lô ghi bên trong một giao dịch ghi (BEGIN IMMEDIATE): xem data_version một lần, lúc đầu, thay vì ở mỗi dòng; trong lúc
        giao dịch giữ khoá không chương trình nào khác ghi được. Là một trình quản lý ngữ cảnh, gọi khi giữ self.lock."""
        cache = self

        class _Pin:
            def __enter__(self):
                cache.pinned = cache._fresh()

            def __exit__(self, *exc):
                cache.pinned = None
        return _Pin()

    def _data_version(self, db) -> int:
        return db.rows("PRAGMA data_version")[0][0]

    def _fresh(self):
        """The cache of the current database, loaded again if it is another database or another program wrote to it.
        Bộ nhớ đệm của cơ sở dữ liệu hiện tại, nạp lại nếu đó là cơ sở dữ liệu khác hoặc có chương trình khác đã ghi vào."""
        db = data_db()
        if self.pinned is not None and db is self.pinned and db is self.db:
            return db
        if db is not self.db or self._data_version(db) != self.version:
            self._load_all(db)
            self.db, self.version = db, self._data_version(db)
        return db

    def _load_all(self, db) -> None:
        """Every record, its days and its recent hours. The hours of the last days of every computer come in one read of the end of
        device_hours; a computer quiet for longer reads its own.
        Mọi bản ghi, các ngày và các giờ gần đây của nó. Giờ của mấy ngày cuối của mọi máy đến trong một lần đọc phần cuối của
        device_hours; máy im lâu hơn thì đọc riêng của nó."""
        self.devices, self.people, self.summaries, self.written, self.late = {}, {}, {}, {}, {}
        now = time.time()
        top = int(now // 3600)
        lo_all, blo_all = top - RECENT_HOURS - 24, top - BLOCK_HOURS - 24
        with db.lock:
            c = db.conn
            if devicestore.days_zone(c) != str(_TZ_SECONDS):
                with db.tx() as t:
                    _recount_days(t)
            days = {}
            for row in devicestore.days(c):
                try:
                    days.setdefault(row[1], {})[date.fromisoformat(row[0])] = _day_numbers(row[2:])
                except (ValueError, TypeError):
                    continue
            near = {}
            for device, kind, hour, body in devicestore.recent(c, lo_all):
                near.setdefault(device, []).append((kind, hour, body))
            for device, hour, body in devicestore.recent_blocks(c, blo_all):
                near.setdefault(device, []).append(("blocks", hour, body))
            for device, seen_at, body in devicestore.states(c):
                self._set(device, seen_at, *self._read(c, device, body, now, days.get(device, {}), near.get(device, []), lo_all, blo_all))
                self.written[device] = seen_at

    def _read(self, c, device: str, body: str, now: float, days: dict, rows: list, lo_all: int, blo_all: int) -> tuple:
        state = _clean_state(body, now)
        if not state:
            return None, None
        lo, blo = _window(state, now)
        if lo < lo_all:
            rows = rows + devicestore.hours(c, device, ("ledger", "tasks"), lo, lo_all)
        if blo < blo_all:
            rows = rows + devicestore.hours(c, device, ("blocks",), blo, blo_all)
        return state, _summary(days, *_window_values(rows), lo, blo)

    def _set(self, device: str, seen_at: int, state, summary) -> None:
        self._drop(device)
        # a broken row is still counted as a device, as the table counts it, but never reaches a page
        # dòng hỏng vẫn được đếm là một máy như bảng đếm, nhưng không bao giờ tới trang nào
        self.devices[device] = (seen_at, state)
        if state:
            self.people.setdefault(person_key(state), set()).add(device)
            self.summaries[id(state)] = (state, summary)

    def _drop(self, device: str) -> None:
        was = self.devices.pop(device, None)
        if was and was[1]:
            self.summaries.pop(id(was[1]), None)
            key = person_key(was[1])
            self.people.get(key, set()).discard(device)
            if not self.people.get(key):
                self.people.pop(key, None)

    def _kept(self, device: str):
        """(record, summary) kept for a device, or (None, None).
        (bản ghi, bản cộng) đang giữ của một máy, hoặc (None, None)."""
        m = (self.devices.get(device) or (0, None))[1]
        return (m, self.summaries[id(m)][1]) if m else (None, None)

    def _write_state(self, c, d: dict, state: dict, seen_at: int, old, lazy: bool, late: bool = False) -> None:
        """Write the devices row, unless lazy and nothing but the time changed since a write less than STATE_REWRITE_SECONDS ago.
        late (a send of the receiver, RECEIVER_FAST_APPLY): also held back when only the state changed, not who or where the computer
        is (IDENTITY_FIELDS); state_loop writes it later (see self.late).
        Ghi dòng devices, trừ khi lazy và không gì ngoài thời điểm đã đổi kể từ lần ghi cách đây chưa tới STATE_REWRITE_SECONDS.
        late (lần gửi qua bộ nhận, RECEIVER_FAST_APPLY): cũng để sau khi chỉ trạng thái đổi, không phải máy là của ai hay ở đâu
        (IDENTITY_FIELDS); state_loop ghi nó sau (xem self.late)."""
        device = d["device"]
        if late and old is not None and state and seen_at - self.written.get(device, -STATE_REWRITE_SECONDS) < STATE_REWRITE_SECONDS \
                and _identity(old) == _identity(state):
            self.late[device] = seen_at
            return
        self.late.pop(device, None)
        if lazy and old is not None and seen_at - self.written.get(device, -STATE_REWRITE_SECONDS) < STATE_REWRITE_SECONDS and _steady(old) == _steady(state):
            return
        body = {k: v for k, v in d.items() if k not in HOUR_KINDS}
        devicestore.put_state(c, device, str(d.get("account") or ""), str(d.get("name") or ""), seen_at, dumps(body))
        self.written[device] = seen_at

    def save(self, d: dict, seen_at: int, lazy: bool = False, cleaned: bool = False, again: bool = False, stamp=None) -> None:
        """Write one device's whole record (its hour book inside it, replacing the one kept) to the tables, then to the cache, under the
        same lock, so a read never sees one without the other. cleaned: d already came out of clean_payload, so its book is not cleaned
        again. lazy: see STATE_REWRITE_SECONDS. again: d is what _clean_again takes, so only the fields set after cleaning are cleaned again.
        stamp: the times of the send (order.Stamps), see write_book.
        Ghi cả bản ghi của một máy (sổ giờ nằm trong đó, thay sổ đang giữ) vào các bảng rồi vào bộ nhớ đệm, dưới cùng một khoá, để lần
        đọc không bao giờ thấy cái này mà thiếu cái kia. cleaned: d đã qua clean_payload, nên sổ của nó không làm sạch lại.
        lazy: xem STATE_REWRITE_SECONDS. again: d là thứ _clean_again nhận, nên chỉ các trường được đặt sau khi làm sạch được làm sạch lại.
        stamp: các thời điểm của lần gửi (order.Stamps), xem write_book."""
        now = time.time()
        with self.lock:
            db = self._fresh()
            device = d["device"]
            whole = d if cleaned else clean_payload(d, now)
            state = (_clean_again if again else clean_payload)({k: v for k, v in whole.items() if k not in HOUR_KINDS}, now) if whole else None
            for kind in HOUR_KINDS if state else ():
                state.pop(kind, None)
            old, summary = self._kept(device)
            with db.tx() as c:
                self._write_state(c, d, state, seen_at, old if state else None, lazy and bool(state), again)
                if not whole or not state:
                    devicestore.drop_days_of(c, device)
                    devicestore.drop_hours(c, [(h, k, device) for k, h, _ in devicestore.hours(c, device, HOUR_KINDS)])
                    self._set(device, seen_at, None, None)
                    return
                days, book = write_book(c, device, book_of(whole), summary["days"] if summary else None, stamp)
            lo, blo = _window(state, now)
            ledger = {int(h): ledger_micro(v) for h, v in book.get("ledger", {}).items()}
            tasks = {int(h): _counts(v) for h, v in book.get("tasks", {}).items()}
            blocks = {int(h): v for h, v in book.get("blocks", {}).items()}
            self._set(device, seen_at, state, _summary(days, ledger, tasks, blocks, lo, blo))

    def merge(self, d: dict, sent: dict, seen_at: int, lazy: bool = True, again: bool = False, stamp=None) -> None:
        """Write a record whose hours come as a v: 2 send has them (merge_hours): each hour sent replaces the row of that hour, an empty
        one removes it, the newest MAX_HOURS_PER_DEVICE of each kind are kept; only those hours and the days they fall in are written.
        d is the record without hours, already cleaned; sent is {kind: {hour: table}}. again: as for save.
        Ghi một bản ghi có các giờ đến như gói v: 2 mang chúng (merge_hours): mỗi giờ gửi lên thay dòng của giờ đó, giờ rỗng thì xoá nó,
        mỗi loại giữ MAX_HOURS_PER_DEVICE giờ mới nhất; chỉ các giờ đó và các ngày chúng rơi vào được ghi. d là bản ghi không kèm giờ,
        đã làm sạch; sent là {loại: {giờ: bảng}}. again: như với save. stamp: các thời điểm của lần gửi (order.Stamps); giờ do một lần
        gửi mới hơn ghi thì giữ nguyên (board/order.py)."""
        now = time.time()
        with self.lock:
            db = self._fresh()
            device = d["device"]
            state = (_clean_again if again else clean_payload)({k: v for k, v in d.items() if k not in HOUR_KINDS}, now)
            for kind in HOUR_KINDS:
                state.pop(kind, None)
            old, summary = self._kept(device)
            lo, blo = _window(state, now)
            ledger = {h: v for h, v in summary["ledgerHours"]}
            tasks = {h: v for h, v in summary["taskHours"]}
            blocks = {int(h): v for h, v in summary["blocks"].items()}
            with db.tx() as c:
                self._write_state(c, d, state, seen_at, old, lazy, again)
                # the window kept reaches further back than before (the computer's clock went back): read what is missing
                # cửa sổ đang giữ lùi xa hơn trước (đồng hồ của máy lùi lại): đọc phần còn thiếu
                more_ledger, more_tasks, more_blocks = _window_values(
                    (devicestore.hours(c, device, ("ledger", "tasks"), lo, summary["from"]) if lo < summary["from"] else [])
                    + (devicestore.hours(c, device, ("blocks",), blo, summary["blocksFrom"]) if blo < summary["blocksFrom"] else []))
                ledger.update(more_ledger)
                tasks.update(more_tasks)
                blocks.update(more_blocks)
                touched, added = set(), set()
                # ledger and tasks hours written over or added, as (kind, hour, body before or None, body now), for the days by difference;
                # None once an hour of them is removed, and the days are added up again from their hours
                # các giờ ledger và tasks được ghi đè hay thêm, dạng (loại, giờ, nội dung trước hoặc None, nội dung giờ), cho các ngày tính bằng
                # hiệu số; thành None khi có một giờ của chúng bị xoá, và các ngày được cộng lại từ các giờ của chúng
                changed = [] if RECEIVER_FAST_APPLY else None
                # the hours of each kind once this send is written, newest first, read before writing it (see devicestore.Held)
                # các giờ của mỗi loại sau khi ghi lần gửi này, mới trước cũ sau, đọc trước khi ghi nó (xem devicestore.Held)
                numbers = {}
                for kind in HOUR_KINDS:
                    these = {int(h): table for h, table in (sent.get(kind) or {}).items()}
                    if not these:
                        continue
                    was = {h: body for _, h, body in devicestore.hours(c, device, (kind,), min(these), max(these) + 1) if h in these}
                    if stamp is not None:
                        # an hour written by a newer send stays as it is
                        # giờ do một lần gửi mới hơn ghi thì giữ nguyên
                        kept = devicestore.stamps(c, device, (kind,), min(these), max(these) + 1)
                        older = {h for h in these if not order.wins(stamp.of(kind, h), kept.get((kind, h)))}
                        order.note_older(len(older))
                        these = {h: t for h, t in these.items() if h not in older}
                    put, drop = [], []
                    for h, table in these.items():
                        if table:
                            body = dumps(table)
                            if was.get(h) != body:
                                put.append((h, kind, device, body) + ((stamp.of(kind, h),) if stamp is not None else ()))
                                if changed is not None and kind != "blocks":
                                    changed.append((kind, h, was.get(h), body))
                                self._hold(kind, h, table, ledger, tasks, blocks)
                                if h not in was:
                                    added.add(kind)
                        elif h in was:
                            drop.append((h, kind, device))
                            if kind != "blocks":
                                changed = None
                            self._hold(kind, h, None, ledger, tasks, blocks)
                    if RECEIVER_FAST_APPLY and kind in added:
                        have = set(devicestore.hour_numbers(c, device, kind)) | {r[0] for r in put}
                        numbers[kind] = sorted(have - {r[0] for r in drop}, reverse=True)
                    devicestore.put_hours(c, put)
                    devicestore.drop_hours(c, drop)
                    if kind != "blocks":
                        touched.update(local_day_of_hour(r[0]) for r in put + drop)
                # a new hour may push the oldest one out of the book
                # một giờ mới có thể đẩy giờ cũ nhất ra khỏi sổ
                for kind in added:
                    beyond = (numbers[kind] if kind in numbers else devicestore.hour_numbers(c, device, kind))[MAX_HOURS_PER_DEVICE:]
                    devicestore.drop_hours(c, [(h, kind, device) for h in beyond])
                    for h in beyond:
                        self._hold(kind, h, None, ledger, tasks, blocks)
                    if kind != "blocks":
                        touched.update(local_day_of_hour(h) for h in beyond)
                        if beyond:
                            changed = None
                days = summary["days"]
                if touched:
                    fresh = _days_by_difference(days, touched, changed) if changed else None
                    if fresh is None:
                        rows = []
                        for day in touched:
                            rows += devicestore.hours(c, device, ("ledger", "tasks"), *_day_hours(day))
                        fresh = _add_up(_rows_to_book(rows), touched)["days"]
                    _write_days(c, device, touched, fresh, days)
                    days = dict((day, v) for day, v in days.items() if day not in touched)
                    days.update(fresh)
            self._set(device, seen_at, state, _summary(days, ledger, tasks, blocks, lo, blo))

    @staticmethod
    def _hold(kind: str, h: int, table, ledger: dict, tasks: dict, blocks: dict) -> None:
        target, value = {"ledger": (ledger, ledger_micro), "tasks": (tasks, _counts), "blocks": (blocks, lambda t: t)}[kind]
        if table is None:
            target.pop(h, None)
        else:
            target[h] = value(table)

    def reload_one(self, device: str) -> None:
        """Read one device's rows again from the tables into the cache: after a write of it was taken back inside a transaction.
        Đọc lại các dòng của một máy từ các bảng vào bộ nhớ đệm: sau khi một lần ghi nó bị rút lại bên trong một giao dịch."""
        with self.lock:
            db = self._fresh()
            with db.lock:
                c = db.conn
                row = devicestore.state(c, device)
                self.late.pop(device, None)
                if not row:
                    self._drop(device)
                    self.written.pop(device, None)
                    return
                days = {}
                for r in devicestore.days(c, device):
                    try:
                        days[date.fromisoformat(r[0])] = _day_numbers(r[2:])
                    except (ValueError, TypeError):
                        continue
                far = 1 << 62
                self._set(device, row[1], *self._read(c, device, row[2], time.time(), days, [], far, far))
                self.written[device] = row[1]

    def book(self, device: str, lo: int = None, stamps: dict = None):
        """The hour book of a device with a good record, read from device_hours and cleaned: the whole book, or its hours from lo on;
        None if there is no good record. A dict given as stamps gets the time of the send that wrote each hour of it, {kind: {hour: time}}.
        Sổ giờ của một máy có bản ghi tốt, đọc từ device_hours và làm sạch: cả sổ, hoặc các giờ từ lo trở đi; None nếu không có bản ghi
        tốt. Dict truyền vào stamps nhận thời điểm của lần gửi đã ghi từng giờ của sổ, {loại: {giờ: thời điểm}}."""
        with self.lock:
            db = self._fresh()
            if not self._kept(device)[0]:
                return None
            with db.lock:
                rows = devicestore.hours(db.conn, device, HOUR_KINDS, -(1 << 62) if lo is None else lo, stamped=True)
        raw = _rows_to_book([r[:3] for r in rows])
        now_ms = time.time() * 1000
        out = {"ledger": clean_ledger_hours(raw.get("ledger"), now_ms), "tasks": clean_hours(raw.get("tasks"), now_ms, _WORKERS)}
        blocks = clean_hours(raw.get("blocks"), now_ms, BLOCK_KINDS)
        if blocks:
            out["blocks"] = blocks
        if stamps is not None:
            for kind, hour, _, sent_at in rows:
                if str(hour) in out.get(kind, ()):
                    stamps.setdefault(kind, {})[str(hour)] = sent_at
        return out

    def holds(self, m: dict) -> bool:
        """Whether this dict is a record the cache holds now (so its summary is kept with it).
        Dict này có phải bản ghi bộ nhớ đệm đang giữ không (khi đó bản cộng của nó được giữ cùng)."""
        kept = self.summaries.get(id(m))
        return bool(kept) and kept[0] is m

    def ids_after(self, after: str, limit: int) -> list:
        """The ids of the devices with a good record, in order, after the one given; at most limit.
        Mã các máy có bản ghi tốt, theo thứ tự, sau mã đã cho; nhiều nhất limit mã."""
        with self.lock:
            self._fresh()
            return sorted(k for k, (_, m) in self.devices.items() if m and k > after)[:limit]

    def get(self, device: str):
        with self.lock:
            self._fresh()
            return (self.devices.get(device) or (0, None))[1]

    def count(self) -> int:
        with self.lock:
            self._fresh()
            return len(self.devices)

    def of_person(self, key: str) -> list:
        with self.lock:
            self._fresh()
            return [self.devices[k][1] for k in sorted(self.people.get(key, ()))]

    def all(self) -> list:
        """Every device seen in the last KEEP_DAYS days; older ones are deleted from the tables, with their hours and days, and the cache.
        Mọi máy đã gửi trong KEEP_DAYS ngày gần nhất; máy cũ hơn bị xoá khỏi các bảng, cùng giờ và ngày của nó, và khỏi bộ nhớ đệm."""
        cutoff = time.time() - KEEP_DAYS * 86400
        with self.lock:
            db = self._fresh()
            old = [k for k, (seen_at, _) in self.devices.items() if seen_at < cutoff]
            if old:
                with db.tx() as c:
                    devicestore.drop_devices(c, old)
                for k in old:
                    self._drop(k)
                    self.written.pop(k, None)
                    self.late.pop(k, None)
            return [cleaned for _, cleaned in self.devices.values() if cleaned]

    def keep(self, devices) -> tuple:
        """What the cache holds for these devices, and the order of every device in memory, for put_back: before a batch is written
        the fast way, which is taken back whole if a row of it fails (board/receiver.py). Under self.lock.
        Những gì bộ nhớ đệm giữ cho các máy này, và thứ tự mọi máy trong bộ nhớ, cho put_back: trước khi ghi một lô theo cách nhanh,
        cách này bị rút lại cả lô nếu một dòng của nó hỏng (board/receiver.py). Gọi khi giữ self.lock."""
        none = object()
        kept = {}
        for device in devices:
            entry = self.devices.get(device)
            summary = self.summaries[id(entry[1])][1] if entry and entry[1] else None
            kept[device] = (entry, summary, self.written.get(device, none), _FULL_AT.get(device, none), self.late.get(device, none))
        return self.devices, self.db, self.version, list(self.devices), kept, none

    def put_back(self, kept: tuple) -> None:
        """Make the cache hold again what keep() saw, in the same order. If it was loaded again since, it is loaded again at the next use.
        Làm bộ nhớ đệm giữ lại đúng những gì keep() đã thấy, cùng thứ tự. Nếu từ đó nó đã được nạp lại, thì nạp lại ở lần dùng sau."""
        table, db, version, order, saved, none = kept
        if table is not self.devices or db is not self.db or version != self.version:
            self.db = None
            return
        for device, (entry, summary, written, full_at, late) in saved.items():
            if entry is None:
                self._drop(device)
            else:
                self._set(device, entry[0], entry[1], summary)
            for target, value in ((self.written, written), (_FULL_AT, full_at), (self.late, late)):
                if value is none:
                    target.pop(device, None)
                else:
                    target[device] = value
        # _set puts a device last; the board lists a person's computers in this order
        # _set đặt máy xuống cuối; bảng liệt kê các máy của một người theo thứ tự này
        devices = self.devices
        self.devices = {d: devices[d] for d in order if d in devices}
        self.devices.update((d, v) for d, v in devices.items() if d not in self.devices)

    def write_late(self) -> int:
        """Write the devices rows held back (see self.late) from what the cache holds now; returns how many were written.
        Ghi các dòng devices đang để sau (xem self.late) từ những gì bộ nhớ đệm đang giữ; trả về số dòng đã ghi."""
        with turns.writing(), self.lock:
            if not self.late:
                return 0
            db = self._fresh()
            rows = []
            for device in self.late:
                seen_at, state = self.devices.get(device) or (0, None)
                if state:
                    rows.append((device, str(state.get("account") or ""), str(state.get("name") or ""), seen_at, dumps(state)))
            with db.tx() as c, devicestore.held(c):
                for row in rows:
                    devicestore.put_state(c, *row)
            for row in rows:
                self.written[row[0]] = row[3]
            self.late = {}
            return len(rows)

    def forget(self) -> None:
        """Load again from the tables at the next use: for code that wrote the devices table itself (tests, migrations).
        Nạp lại từ các bảng ở lần dùng sau: cho đoạn mã tự ghi vào bảng devices (test, chuyển dữ liệu)."""
        with self.lock:
            self.db = None


DEVICES = DeviceCache()


def state_loop() -> None:
    """With the receiver: write the devices rows held back every LATE_WRITE_SECONDS (see DeviceCache.late).
    Khi có bộ nhận: ghi các dòng devices đang để sau mỗi LATE_WRITE_SECONDS (xem DeviceCache.late)."""
    while True:
        time.sleep(LATE_WRITE_SECONDS)
        try:
            DEVICES.write_late()
        except Exception as e:
            sys.stderr.write("devices: the rows held back were not written: %r\n" % (e,))


def read_device(device: str):
    """A device's whole record, cleaned, with its hour book read from device_hours; None if there is none or it is broken.
    A new dict each time: for code that needs the book (tests, export); the board uses DEVICES.get, the record without its book.
    Cả bản ghi của một máy, đã làm sạch, kèm sổ giờ đọc từ device_hours; None nếu chưa có hoặc hỏng.
    Mỗi lần một dict mới: cho đoạn mã cần sổ (test, xuất dữ liệu); bảng dùng DEVICES.get, bản ghi không kèm sổ."""
    with DEVICES.lock:
        m = DEVICES.get(device)
        book = DEVICES.book(device) if m else None
    return dict(m, **book) if m else None


def read_book(device: str):
    """A device's whole hour book {"ledger", "tasks", "blocks"?}, read from device_hours; None if there is no good record of it.
    Cả sổ giờ của một máy {"ledger", "tasks", "blocks"?}, đọc từ device_hours; None nếu không có bản ghi tốt của nó."""
    return DEVICES.book(device)


def whole_record(device: str, body: str) -> str:
    """A devices row's body with its hour book put back from device_hours, as the record was stored before schema version 6 (export_json).
    A body that is not a good record is given as it is.
    Nội dung một dòng devices với sổ giờ đặt lại từ device_hours, như bản ghi được lưu trước lược đồ phiên bản 6 (export_json).
    Nội dung không phải bản ghi tốt thì trả nguyên như cũ."""
    try:
        d = json.loads(body)
    except (ValueError, RecursionError):
        return body
    if not isinstance(d, dict) or not clean_payload(d, time.time()):
        return body
    db = data_db()
    with db.lock:
        book = _rows_to_book(devicestore.hours(db.conn, device, HOUR_KINDS))
    for kind in HOUR_KINDS:
        if book.get(kind) or kind != "blocks":
            d[kind] = book.get(kind) or {}
    return dumps(d)


# what save_ingest did with a send
# save_ingest đã làm gì với một lần gửi
SAVED, NEED_FULL, STALE = "saved", "need-full", "stale"
HOUR_KINDS = ("ledger", "tasks", "blocks")
# a new value every time the server starts, given in every answer of /ingest: a computer that sees it change sends its latest hours again,
# in case the last seconds before a crash were not written
# giá trị mới mỗi lần máy chủ khởi động, có trong mọi câu trả lời của /ingest: máy thấy nó đổi thì gửi lại các giờ gần nhất,
# phòng khi vài giây cuối trước lúc sập chưa kịp ghi
BOOT_ID = secrets.token_hex(8)
# device -> when it last replaced its whole hour book; kept in memory only, so after a start every computer may send one full book
# máy -> lần cuối nó thay cả sổ giờ; chỉ giữ trong bộ nhớ, nên sau khi khởi động máy nào cũng được gửi một sổ đủ
_FULL_AT = {}


def send_kind(raw) -> str:
    """How a cleaned send treats the hour book: "v1" and "full" bring the whole book, "hours" only the hours that changed.
    Một lần gửi đã làm sạch đối xử với sổ giờ thế nào: "v1" và "full" mang cả sổ, "hours" chỉ mang các giờ đã đổi."""
    if not isinstance(raw, dict) or raw.get("v") != 2:
        return "v1"
    return "full" if raw.get("full") is True else "hours"


def replace_hours(sent: dict) -> dict:
    """The hour book a v: 1 send or a v: 2 send with full: true stands for: every hour it holds, the empty ones left out.
    Sổ giờ mà gói v: 1 hoặc gói v: 2 có full: true mang theo: mọi giờ trong gói, bỏ các giờ rỗng."""
    out = {}
    for kind in HOUR_KINDS:
        book = {hour: table for hour, table in (sent.get(kind) or {}).items() if table}
        if book or kind != "blocks":
            out[kind] = book
    return out


def merge_hours(kept: dict, sent: dict) -> dict:
    """Put the hours of a v: 2 send on the hour book kept for that computer. Each hour sent is the whole value of that hour and replaces it;
    an empty hour removes it; an hour not sent stays as it was; the newest MAX_HOURS_PER_DEVICE hours of each kind are kept.
    Pure: no database, no clock, nothing shared, and neither argument is changed. The Go receiver must give the same result.
    Đặt các giờ của một gói v: 2 lên sổ giờ đang giữ của máy đó. Mỗi giờ gửi lên là giá trị đầy đủ của giờ đó và thay giờ cũ;
    giờ rỗng thì xoá giờ đó; giờ không gửi thì giữ nguyên; mỗi loại giữ MAX_HOURS_PER_DEVICE giờ mới nhất.
    Hàm thuần: không cơ sở dữ liệu, không đồng hồ, không dùng chung gì, và không sửa đối số nào. Bộ nhận Go phải cho cùng kết quả."""
    out = {}
    for kind in HOUR_KINDS:
        book = dict(kept.get(kind) or {})
        for hour, table in (sent.get(kind) or {}).items():
            if table:
                book[hour] = table
            else:
                book.pop(hour, None)
        book = {hour: book[hour] for hour in sorted(book, key=int)[-MAX_HOURS_PER_DEVICE:]}
        if book or kind != "blocks":
            out[kind] = book
    return out


def save_ingest(d: dict, now: float, kind: str = "v1", decided: bool = False, stamp=None) -> str:
    """Save one send and say what was done (SAVED, NEED_FULL or STALE). The IP history comes from the device's previous row, never from the device.
    kind is send_kind() of what was sent. stamp: the times its hours are written with (order.Stamps), by default the send's own
    (order.stamp_of). Reading the row kept, merging and writing happen under one lock, so two sends of one computer at the same moment (one
    per Claude Code session) never merge on the same old row and lose each other's hours.
    Ghi một lần máy gửi và cho biết đã làm gì (SAVED, NEED_FULL hay STALE). Lịch sử IP lấy từ dòng cũ của máy, không lấy từ máy gửi.
    kind là send_kind() của gói đã gửi. stamp: các thời điểm dùng để ghi các giờ của nó (order.Stamps), mặc định là của chính lần gửi
    (order.stamp_of). Đọc dòng đang giữ, ghép và ghi nằm trong một khoá, để hai lần gửi cùng lúc của một máy (mỗi phiên Claude Code một
    lần) không bao giờ ghép trên cùng một dòng cũ rồi làm mất giờ của nhau."""
    with DEVICES.lock:
        old = DEVICES.get(d["device"])
        if kind == "hours" and old is None:
            # only changed hours, and no book here to put them on (a new computer, a lost or broken row): ask for the whole book
            # chỉ có các giờ đã đổi mà ở đây không có sổ để đặt lên (máy mới, dòng bị mất hay hỏng): xin cả sổ
            return NEED_FULL
        # decided: the Go receiver already dropped what came out of order and chose between replacing and merging (board/receiver.py)
        # decided: bộ nhận Go đã bỏ gói tới sai thứ tự và đã chọn giữa thay cả sổ và ghép (board/receiver.py)
        if not decided and kind != "v1" and old and 0 < old["updatedAt"] - d["updatedAt"] <= REORDER_WINDOW_MS:
            return STALE
        if not decided and kind == "full" and old is not None and now - _FULL_AT.get(d["device"], -FULL_BOOK_SECONDS) < FULL_BOOK_SECONDS:
            # a whole book again too soon: its hours are merged one by one instead, which loses nothing
            # lại cả sổ quá sớm: các giờ của nó được ghép từng giờ, không mất gì
            kind = "hours"
        if kind == "full":
            _FULL_AT[d["device"]] = now
        # seq only orders the sends: kept in the record it would make the row of the computer written at every send
        # seq chỉ để xếp thứ tự các lần gửi: giữ trong bản ghi thì nó làm dòng của máy phải ghi lại mỗi lần gửi
        new = {k: v for k, v in d.items() if k not in HOUR_KINDS and k != "seq"}
        ip = new.get("lanIp") or new.get("ip")
        history = (old or {}).get("ipHistory", [])
        new["ipHistory"] = add_ip_history(history, ip, int(now * 1000)) if ip else history
        # only the hours that changed are written, and the devices row only when more than the time changed (STATE_REWRITE_SECONDS);
        # the result is what merge_hours or replace_hours gives on the whole book
        # chỉ ghi các giờ đã đổi, và dòng devices chỉ khi đổi nhiều hơn thời điểm (STATE_REWRITE_SECONDS); kết quả đúng như
        # merge_hours hay replace_hours cho trên cả sổ
        # decided: d came out of clean_payload in board/receiver.py, and only name, account and ip were set since (see _clean_again)
        # decided: d đã ra từ clean_payload trong board/receiver.py, và từ đó chỉ name, account và ip được đặt (xem _clean_again)
        again = decided and RECEIVER_FAST_APPLY
        # the hours keep the send's own time, so an older one that comes later, here or from the receiver, writes none over (board/order.py)
        # các giờ giữ thời điểm của chính lần gửi, để lần gửi cũ hơn tới sau, ở đây hay từ bộ nhận, không ghi đè giờ nào (board/order.py)
        stamp = stamp or order.Stamps(order.stamp_of(d))
        if kind == "hours":
            DEVICES.merge(new, {k: d.get(k) or {} for k in HOUR_KINDS}, int(time.time()), again=again, stamp=stamp)
        else:
            DEVICES.save(dict(new, **replace_hours(d)), int(time.time()), lazy=True, cleaned=True, again=again, stamp=stamp)
        return SAVED


def save_device(d: dict) -> None:
    """Replace one device's whole record, its hour book inside it; seen_at is the server's time of the send, used by the 30-day limit.
    Thay cả bản ghi của một máy, sổ giờ nằm trong đó; seen_at là giờ máy chủ nhận, dùng cho hạn 30 ngày."""
    DEVICES.save(d, int(time.time()))


class SendPace:
    """The gap between sends told to the computers on /ingest: INGEST_MIN_GAP_MS while the computers that sent in the last minute fit in
    INGEST_SENDS_PER_SECOND, wider past it (computers over sends a second), at most 2 minutes. Counts only, nothing about who.
    Khoảng cách giữa hai lần gửi dặn các máy trên /ingest: INGEST_MIN_GAP_MS khi số máy đã gửi trong phút vừa qua còn vừa
    INGEST_SENDS_PER_SECOND, rộng hơn khi quá (số máy chia số lần gửi mỗi giây), tối đa 2 phút. Chỉ đếm, không ghi gì về ai."""

    WINDOW = 60.0
    MAX_GAP_MS = 120_000

    def __init__(self):
        self.lock = threading.Lock()
        self.seen = {}
        self.pruned = 0.0

    def note(self, device: str, now: float) -> int:
        """Counts this computer's send and gives the gap to tell it, in milliseconds.
        Đếm lần gửi của máy này và cho khoảng cách cần dặn nó, tính bằng mili giây."""
        with self.lock:
            self.seen[device] = now
            if now - self.pruned > 5:
                self.pruned = now
                self.seen = {d: t for d, t in self.seen.items() if now - t < self.WINDOW}
            computers = len(self.seen)
        rate = settings.INGEST_SENDS_PER_SECOND
        if rate <= 0:
            return settings.INGEST_MIN_GAP_MS
        return int(min(self.MAX_GAP_MS, max(settings.INGEST_MIN_GAP_MS, math.ceil(computers / rate * 1000))))


SEND_PACE = SendPace()


class IngestGate:
    """Gatekeeper of /ingest: each device can only send for the person who sent first, and the number of sends is limited.
    INGEST_KEY is in every staff member's install package, so it is not enough to tell who is who.
    Gác cổng /ingest: mỗi máy chỉ gửi được cho đúng người đã gửi lần đầu, và giới hạn số lần gửi.
    INGEST_KEY nằm trong gói cài của mọi nhân viên nên không đủ để biết ai là ai."""

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()
        # device -> [sends left, when that was counted]: a bucket per computer, not per address, so many computers behind one
        # office address are not stopped together (see INGEST_BURST and INGEST_PER_SECOND)
        # máy -> [số lượt gửi còn lại, lúc đếm]: mỗi máy một xô, không theo địa chỉ, để nhiều máy chung một địa chỉ văn phòng
        # không bị chặn cùng lúc (xem INGEST_BURST và INGEST_PER_SECOND)
        self.buckets = {}
        # ip -> [times a new device was created in the last day]
        # ip -> [các lần tạo máy mới trong 1 ngày]
        self.new_devices = {}
        self.swept_at = 0.0
        self.identities = {k: [a, n] for k, a, n in database.rows("SELECT device, account, name FROM identities")}

    def _save(self, device: str) -> None:
        account, name = self.identities[device]
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO identities VALUES (?, ?, ?)", (device, account, name))

    def check(self, d: dict, ip: str, now: float, device_count: int):
        """None if sending is allowed; otherwise: (HTTP code, reason).
        None nếu cho gửi; nếu không: (mã HTTP, lý do)."""
        account = str(d.get("account") or "").strip().lower()[:120]
        name = str(d.get("name") or "").strip().lower()[:120]
        with self.lock:
            # drop the buckets and new-device counts nobody used for a while, once a minute, not on every send
            # bỏ các xô và các lần đếm máy mới đã lâu không dùng, mỗi phút một lần, không phải ở mọi lần gửi
            if now - self.swept_at > 60:
                self.swept_at = now
                self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 600}
                self.new_devices = {k: v for k, v in self.new_devices.items() if v and now - v[-1] < 86400}
            tokens, counted = self.buckets.get(d["device"], (INGEST_BURST, now))
            tokens = min(INGEST_BURST, tokens + max(0.0, now - counted) * INGEST_PER_SECOND)
            if tokens < 1:
                self.buckets[d["device"]] = (tokens, now)
                return 429, "too many submissions"
            self.buckets[d["device"]] = (tokens - 1, now)
            known = self.identities.get(d["device"])
            if known is None:
                recent_new = [t for t in self.new_devices.get(ip, []) if now - t < 86400]
                if len(recent_new) >= NEW_DEVICES_PER_IP:
                    return 429, "too many new devices from one address"
                if device_count >= MAX_DEVICES:
                    return 507, "device limit reached"
                self.new_devices[ip] = recent_new + [now]
                self.identities[d["device"]] = [account, name]
                self._save(d["device"])
                return None
            # the first time the email / name is not known yet (freshly installed device): fill it in, not counted as a change
            # lần đầu chưa biết email / tên (máy mới cài): điền thêm, không coi là đổi
            changed = False
            for i, v in enumerate((account, name)):
                if v and not known[i]:
                    known[i], changed = v, True
                elif v and known[i] and v != known[i]:
                    return 409, "this device is linked to another person"
            if changed:
                self._save(d["device"])
            # a device that leaves out its email or name stays with the person it is linked to
            # máy bỏ trống email hoặc tên vẫn thuộc về người đã gắn với nó
            for field, v in zip(("account", "name"), known):
                if v and not d.get(field):
                    d[field] = v
            return None


def read_all_devices() -> list:
    """Every device that sent in the last KEEP_DAYS days, cleaned; older rows are deleted. The dicts are shared: do not change them.
    Mọi máy đã gửi trong KEEP_DAYS ngày gần nhất, đã làm sạch; dòng cũ hơn bị xoá. Các dict dùng chung: đừng sửa chúng."""
    return DEVICES.all()


def filter_quota(quota, now: float):
    """Account quota sent by the device, filtered: {readAt, windows: [{kind, pct, resetsAt?}]}; dropped when older than 7 days or malformed.
    Hạn mức tài khoản máy gửi lên, đã lọc: {readAt, windows: [{kind, pct, resetsAt?}]}; quá 7 ngày hoặc sai dạng thì bỏ."""
    if not isinstance(quota, dict) or not isinstance(quota.get("readAt"), (int, float)) or not isinstance(quota.get("windows"), list):
        return None
    if now - quota["readAt"] / 1000 > 7 * 24 * 3600:
        return None
    windows = []
    for c in quota["windows"][:5]:
        if not isinstance(c, dict) or not isinstance(c.get("kind"), str) or not isinstance(c.get("pct"), (int, float)):
            continue
        resets_at = c.get("resetsAt")
        entry = {"kind": c["kind"][:30], "pct": round(min(max(float(c["pct"]), 0), 999), 1)}
        # a window past its reset time: the old number is no longer true, treat it as 0%
        # khung đã qua giờ làm mới thì số cũ không còn đúng: coi như 0%
        if isinstance(resets_at, (int, float)):
            entry["resetsAt"] = int(resets_at)
            if resets_at / 1000 < now:
                entry["pct"] = 0
        windows.append(entry)
    return {"readAt": int(quota["readAt"]), "windows": windows} if windows else None


def person_key(m: dict) -> str:
    """What tells one person from another in the reports: the account plus the name; a report with no name falls back to its address, then its device id.
    Thứ phân biệt người này với người khác trong các báo cáo: tài khoản cộng với tên; báo cáo không có tên thì lấy địa chỉ, rồi tới mã máy."""
    return (str(m.get("account") or "") + "|" + (str(m.get("name") or "") or str(m.get("lanIp") or "") or str(m.get("ip") or "") or str(m.get("device")))).lower()


def person_name(m: dict) -> str:
    return str(m.get("name") or m.get("account") or m.get("lanIp") or m.get("ip") or m.get("device"))


# person_key -> (ids of the devices, the devices, built at, good until, row)
# person_key -> (id các máy, các máy, lúc dựng, dùng được tới, dòng)
_ROWS = {}


def _person_row(key: str, group: list, now: float, today, since_7_days) -> dict:
    """One person's row, kept while their devices are the same objects DeviceCache holds and no moment that changes it has come:
    the next hour (the 24-hour charts), the next local midnight (today, 7 days), a device going quiet, a connector's work going stale,
    a quota window resetting or getting too old. Devices the cache does not hold (tests, the demo's history) are added up afresh.
    Dòng của một người, được giữ khi các máy của họ vẫn là đúng các đối tượng DeviceCache đang giữ và chưa tới thời điểm làm nó đổi:
    giờ kế tiếp (biểu đồ 24 giờ), nửa đêm địa phương kế tiếp (hôm nay, 7 ngày), một máy im, việc của bộ nối hết còn mới,
    một khung hạn mức làm mới hay quá cũ. Máy bộ nhớ đệm không giữ (test, lịch sử của bản thử) thì được cộng lại từ đầu."""
    kept = all(DEVICES.summaries.get(id(m), (None,))[0] is m for m in group)
    ids = tuple(id(m) for m in group)
    hit = _ROWS.get(key) if kept else None
    if hit and hit[0] == ids and all(a is b for a, b in zip(hit[1], group)) and hit[2] <= now < hit[3]:
        return hit[4]
    row = _build_person_row(group, now, today, since_7_days)
    if kept:
        _ROWS[key] = (ids, tuple(group), now, _good_until(group, now, today), row)
    return row


def _good_until(group: list, now: float, today) -> float:
    """The first moment after now at which the same devices could give another row.
    Thời điểm đầu tiên sau lúc này mà cùng các máy có thể cho ra dòng khác."""
    moments = [(now // 3600 + 1) * 3600, (today.toordinal() - _EPOCH_DAY + 1) * 86400 - _TZ_SECONDS]
    for m in group:
        seen = m["updatedAt"] / 1000
        connector = from_connector(m)
        moments.append(seen + (CONNECTOR_OFFLINE_SECONDS if connector else OFFLINE_SECONDS))
        if connector:
            moments.append(seen + CONNECTOR_WORKING_SECONDS)
        quota = m.get("quota")
        if isinstance(quota, dict):
            if isinstance(quota.get("readAt"), (int, float)):
                moments.append(quota["readAt"] / 1000 + 7 * 24 * 3600)
            for w in quota.get("windows") or ():
                if isinstance(w, dict) and isinstance(w.get("resetsAt"), (int, float)):
                    moments.append(w["resetsAt"] / 1000)
    return min([t for t in moments if t > now] or [now])


def _note_ip(r: dict, m: dict, ip: str) -> None:
    """Where a person sent from most recently (so an old computer at the office does not keep a person who is travelling), and every address.
    Nơi một người gửi gần nhất (để máy cũ ở văn phòng không giữ người đang đi công tác), và mọi địa chỉ."""
    if ip and m["updatedAt"] >= r["latestIpAt"]:
        r["latestIp"], r["latestIpAt"] = ip, m["updatedAt"]
    if ip and ip not in r["ip"]:
        r["ip"].append(ip)


def branch_facts(devices: list) -> dict:
    """person key -> the fields of that person's row branch_of reads (name, account, latestIp, ip), exactly as group_by_person sets them,
    without adding up anything else: the table of people the Go receiver asks for every few seconds (board/receiver.py, People.rebuild).
    khoá người -> các trường trong dòng của người đó mà branch_of đọc (tên, tài khoản, latestIp, ip), đúng như group_by_person đặt, mà không
    cộng thêm gì khác: bảng người bộ nhận Go hỏi vài giây một lần."""
    out = {}
    for i, m in enumerate(devices):
        turns.rest(i)
        if not isinstance(m, dict) or m.get("v") != 1 or not isinstance(m.get("updatedAt"), (int, float)):
            continue
        key = person_key(m)
        r = out.get(key)
        if r is None:
            r = out[key] = {"key": key, "name": person_name(m), "account": str(m.get("account") or ""), "latestIp": "", "latestIpAt": 0, "ip": []}
        _note_ip(r, m, str(m.get("ip") or ""))
    return out


def _build_person_row(group: list, now: float, today, since_7_days) -> dict:
    people = {}
    for m in group:
        if not isinstance(m, dict) or m.get("v") != 1 or not isinstance(m.get("updatedAt"), (int, float)):
            continue
        ip, lan_ip = str(m.get("ip") or ""), str(m.get("lanIp") or "")
        name, group_key = person_name(m), person_key(m)
        r = people.setdefault(group_key, {"key": group_key, "name": name, "account": str(m.get("account") or ""), "deviceCount": 0, "lanIps": [], "ip": [],
                                    "enteredAccounts": [], "delegating": [0, 0, 0], "subagents": {}, "costByHour": {}, "tasksByHour": {}, "models": {},
                                    "gemma": [], "chatgpt": 0, "gemini": 0, "known": 0, "chatgptModels": [], "geminiModels": [], "updatedAt": 0, "openSessions": 0, "working": 0, "waiting": 0,
                                    "usdToday": 0, "tokensIn": 0, "tokensOut": 0, "usd7d": 0, "tasks": [0, 0, 0], "quota": None, "pluginVersion": [], "devices": [],
                                    "latestIp": "", "latestIpAt": 0, "online": False, "tools": {}})
        connector = from_connector(m)
        # the connector is not a plugin install: it is not counted as a computer and has no plugin version to show
        # bộ nối không phải một bản cài plugin: không tính là một máy và không có phiên bản plugin để hiện
        if not connector:
            r["deviceCount"] += 1
        _note_ip(r, m, ip)
        if lan_ip and lan_ip not in r["lanIps"]:
            r["lanIps"].append(lan_ip)
        entered = str(m.get("enteredAccount") or "")
        if entered and entered not in r["enteredAccounts"]:
            r["enteredAccounts"].append(entered)
        r["updatedAt"] = max(r["updatedAt"], m["updatedAt"])
        # plugin version of each device (an old device that has not sent it: leave empty)
        # phiên bản plugin từng máy (máy bản cũ chưa gửi: để trống)
        version = m.get("pluginVersion")
        if not connector and isinstance(version, str) and re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,19}", version) and version not in r["pluginVersion"]:
            r["pluginVersion"].append(version)
        # each device on its own: which version is on which device, and which device went quiet
        # từng máy riêng: biết phiên bản nào của máy nào, máy nào lâu không gửi
        if not connector:
            r["devices"].append({"ip": lan_ip or ip, "version": version if isinstance(version, str) and re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,19}", version) else "",
                                 "at": m["updatedAt"], "mark": m.get("hardwareMark") or m.get("device") or "", "ipHistory": m.get("ipHistory") or []})
        # 5-hour / 7-day quota of the account: take the newest reading among this person's devices
        # hạn mức 5 giờ / 7 ngày của tài khoản: lấy lần đọc mới nhất trong các máy của người này
        quota = filter_quota(m.get("quota"), now)
        if quota and (not r["quota"] or quota["readAt"] > r["quota"]["readAt"]):
            r["quota"] = quota
        # assistants installed on each device (an old device that does not send it: counts as unknown)
        # trợ lý đã cài trên từng máy (máy bản cũ không gửi: tính là chưa biết)
        assistants = m.get("assistants")
        if isinstance(assistants, dict):
            r["known"] += 1
            g = assistants.get("gemma")
            if isinstance(g, str) and g and g not in r["gemma"]:
                r["gemma"].append(g[:40])
            r["chatgpt"] += 1 if assistants.get("chatgpt") else 0
            r["gemini"] += 1 if assistants.get("gemini") else 0
            # model that answered most recently (only after the device has delegated at least once)
            # mô hình đã trả lời lần gần nhất (chỉ có sau khi máy đã giao việc ít nhất một lần)
            for source_key, target_key in (("chatgptModel", "chatgptModels"), ("geminiModel", "geminiModels")):
                v = assistants.get(source_key)
                if isinstance(v, str) and v and v[:60] not in r[target_key]:
                    r[target_key].append(v[:60])
        if is_fresh(m, now):
            # the plugin sends on a beat while Claude is open, so a fresh report means the person is there;
            # the connector also sends when the last session closes, and that report means no tool is open
            # plugin gửi theo nhịp khi Claude đang mở, nên báo cáo còn mới nghĩa là người đó đang ở đó;
            # bộ nối còn gửi cả khi phiên cuối đóng lại, và báo cáo đó nghĩa là không công cụ nào đang mở
            if not connector or int(m.get("openSessions") or 0) > 0:
                r["online"] = True
            # sessions per tool, for the tools that have a session open: the plugin's report is Claude Code, the connector's names its tools
            # số phiên theo từng công cụ, với công cụ đang có phiên mở: báo cáo của plugin là Claude Code, của bộ nối thì ghi tên từng công cụ
            for tool, counts in (m["tools"] if connector else {"claude": m}).items():
                if not isinstance(counts, dict) or not (tool == "claude" or tool in CONNECTOR_TOOLS):
                    continue
                numbers = {k: int(counts.get(k) or 0) for k in SESSION_COUNTS}
                # a connector report this old no longer proves that work goes on: the session stays open, not working
                # báo cáo của bộ nối cũ tới mức này không còn chứng tỏ việc vẫn đang chạy: phiên vẫn mở, không còn đang làm
                if connector and now - m["updatedAt"] / 1000 >= CONNECTOR_WORKING_SECONDS:
                    numbers["working"] = 0
                for k in SESSION_COUNTS:
                    r[k] += numbers[k]
                if numbers["openSessions"] > 0:
                    per_tool = r["tools"].setdefault(tool, dict.fromkeys(SESSION_COUNTS, 0))
                    for k in SESSION_COUNTS:
                        per_tool[k] += numbers[k]
            model = m.get("models") or {}
            if isinstance(model, dict):
                for model_key, amount in model.items():
                    if isinstance(model_key, str) and len(model_key) < 80:
                        r["models"][model_key] = r["models"].get(model_key, 0) + int(amount or 0)
            # running sub-assistants: only the type name, the device does not send the content of the task
            # trợ lý phụ đang chạy: chỉ có tên loại, máy không gửi nội dung việc
            sub_agents = m.get("subagents")
            if isinstance(sub_agents, dict):
                for agent_name, agent_count in list(sub_agents.items())[:10]:
                    if isinstance(agent_name, str) and re.fullmatch(r"[A-Za-z0-9:_.-][A-Za-z0-9:_. ()-]{0,39}", agent_name) and isinstance(agent_count, int) and 0 < agent_count <= 50:
                        r["subagents"][agent_name] = r["subagents"].get(agent_name, 0) + agent_count
            delegating = m.get("delegating") or {}
            if isinstance(delegating, dict):
                for i, tool in enumerate(("gemini", "chatgpt", "gemma")):
                    r["delegating"][i] += int(delegating.get(tool) or 0)
        # the hourly numbers come added up per day once per send (hours_of): only the last 24 hours are gone through here
        # số liệu theo giờ đã được cộng theo ngày một lần cho mỗi lần gửi (hours_of): ở đây chỉ đi qua 24 giờ gần nhất
        hours = hours_of(m)
        for day, v in hours["days"].items():
            # whole usdMicro while adding up, dollars once the person's computers are all in (see the end of this function)
            # cộng bằng số nguyên usdMicro, đổi ra đô la khi đã cộng đủ các máy của người đó (xem cuối hàm này)
            if day >= since_7_days:
                r["usd7d"] += v["usdMicro"]
            if day == today:
                r["usdToday"] += v["usdMicro"]
                r["tokensIn"] += v["tokensIn"]
                r["tokensOut"] += v["tokensOut"]
                for i, worker in enumerate(("gemini", "chatgpt", "gemma")):
                    r["tasks"][i] += v[worker]
        # last 24 hours, for the charts on the dashboard; the hours are newest first, so stop at the first older one
        # 24 giờ gần nhất, cho các biểu đồ của bảng điều khiển; các giờ xếp mới trước, nên dừng ở giờ cũ hơn đầu tiên
        for hour, micro in hours["ledgerHours"]:
            if hour * 3600 <= now - 24 * 3600:
                break
            r["costByHour"][hour] = r["costByHour"].get(hour, 0) + micro
        for hour, counts in hours["taskHours"]:
            if hour * 3600 <= now - 24 * 3600:
                break
            hour_counts = r["tasksByHour"].setdefault(hour, [0, 0, 0])
            for i in range(3):
                hour_counts[i] += counts[i]
    for r in people.values():
        r["usdToday"], r["usd7d"] = r["usdToday"] / 1_000_000, r["usd7d"] / 1_000_000
        r["costByHour"] = {hour: micro / 1_000_000 for hour, micro in r["costByHour"].items()}
    return next(iter(people.values()))


def group_by_person(devices: list, now: float) -> list:
    """Merge device files into one row per person: same account + same name (sharing an account still keeps people apart).
    A person's row is kept and given again until one of their devices sends or a moment that changes it comes (see _person_row),
    so a build of the board only adds up the people who changed.
    Gộp file các máy thành mỗi người một dòng: cùng tài khoản + cùng tên (dùng chung tài khoản vẫn tách người).
    Dòng của một người được giữ và trả lại cho tới khi một máy của họ gửi hoặc tới một thời điểm làm nó đổi (xem _person_row),
    nên một lần dựng bảng chỉ phải cộng những người đã đổi."""
    today = datetime.fromtimestamp(now, LOCAL_TZ).date()
    since_7_days = today - timedelta(days=6)
    groups = {}
    for m in devices:
        if not isinstance(m, dict) or m.get("v") != 1 or not isinstance(m.get("updatedAt"), (int, float)):
            continue
        groups.setdefault(person_key(m), []).append(m)
    # rows of people no longer there are dropped on a build of the whole board, not on the build of one person after a send
    # dòng của người không còn nữa được bỏ ở lần dựng cả bảng, không phải ở lần dựng một người sau một lần gửi
    if len(_ROWS) > 2 * len(groups) + 100 and 4 * len(groups) > len(_ROWS):
        for gone in [k for k in _ROWS if k not in groups]:
            _ROWS.pop(gone, None)
    # a copy of each kept row, since the account-wide fields below are written on it
    # bản sao của mỗi dòng đang giữ, vì các trường theo tài khoản bên dưới được ghi lên nó
    out = []
    for i, (key, group) in enumerate(groups.items()):
        # between two people a build holds no lock: it rests while the receiver's rows are written (board/turns.py)
        # giữa hai người, lần dựng không giữ khoá nào: nó nghỉ trong lúc các dòng của bộ nhận đang được ghi
        turns.rest(i)
        out.append(dict(_person_row(key, group, now, today, since_7_days)))
    out.sort(key=lambda r: r["name"].lower())
    per_account = {}
    for r in out:
        per_account[r["account"]] = per_account.get(r["account"], 0) + 1
    # quota belongs to the account: people sharing an account get the same newest reading
    # hạn mức là của tài khoản: người dùng chung tài khoản cùng nhận lần đọc mới nhất
    latest_quota = {}
    for r in out:
        quota = r["quota"]
        if r["account"] and quota and (r["account"] not in latest_quota or quota["readAt"] > latest_quota[r["account"]]["readAt"]):
            latest_quota[r["account"]] = quota
    for r in out:
        r["shared"] = bool(r["account"]) and per_account[r["account"]] > 1
        if r["account"] in latest_quota:
            r["quota"] = latest_quota[r["account"]]
    return out


def status_of(r: dict, now: float) -> str:
    """working: Claude or another tool is working; waiting: waiting for a person to reply; open: a session is open but idle;
    offline: no report of this person is fresh (see is_fresh).
    working: Claude hoặc công cụ khác đang làm; waiting: đang chờ người trả lời; open: mở phiên nhưng rảnh;
    offline: không báo cáo nào của người này còn mới (xem is_fresh)."""
    if not r["online"]:
        return "offline"
    if r["waiting"]:
        return "waiting"
    if r["working"]:
        return "working"
    return "open"


BRANCHES_FILE = os.environ.get("BRANCHES_FILE", "/etc/ai-worker-branches.json")
_branches_cache = {"mtime": None, "items": []}


def load_branches() -> list:
    """List of branches declared by an admin; read again when the file changes. No file or a bad file gives an empty list.
    Danh sách chi nhánh do người quản trị khai báo; đọc lại khi file đổi. Không có file hoặc file sai thì danh sách rỗng."""
    try:
        mtime = os.path.getmtime(BRANCHES_FILE)
    except OSError:
        _branches_cache.update(mtime=None, items=[])
        return []
    if mtime == _branches_cache["mtime"]:
        return _branches_cache["items"]
    branches = []
    try:
        with open(BRANCHES_FILE, encoding="utf-8") as f:
            for b in json.load(f).get("branches", []):
                networks = []
                for x in b.get("ip") or []:
                    try:
                        networks.append(ipaddress.ip_network(str(x), strict=False))
                    except ValueError:
                        sys.stderr.write("branch %s: ignoring invalid IP range\n" % b.get("id"))
                branches.append({"id": str(b["id"]), "name": str(b["name"]), "lat": float(b["lat"]), "lon": float(b["lon"]), "isHq": b.get("isHq") is True,
                           "people": {str(n).strip().lower() for n in b.get("people") or []}, "networks": networks})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        sys.stderr.write("cannot read the branches file: %s\n" % e)
        branches = []
    _branches_cache.update(mtime=mtime, items=branches)
    return branches
