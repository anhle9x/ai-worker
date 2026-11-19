"""What each role may see, the admin data and actions, and the history of the board.
Mỗi vai được thấy gì, số liệu và thao tác quản trị, và lịch sử của bảng."""

import csv
import hashlib
import hmac
import io
import ipaddress
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime

from board import packages, settings
from board.assets import UI_VERSION
from board.daily import NUMBERS, PERIODS, DailyStore, totals_by_day
from board.db import data_db, dumps, keys_db
from board.devices import (
    IngestGate,
    blocks_since,
    group_by_person,
    load_branches,
    read_all_devices,
    status_of,
)
from board.lang import tx
from board.login import SESSIONS
from board.packages import menubar_extension, menubar_mac_dmg
from board.tgapp import SESSIONS as TG_APP_SESSIONS
from board.security import ACCOUNT_NAME_RE, ADMIN, VIEWER, WALL
from board.settings import (
    DAILY_RECOUNT_SECONDS,
    KIND_EXTENSION,
    KIND_MCP,
    KIND_PLUGIN,
    KIND_TELEGRAM,
    MCP_KEYS_MAX,
    LOCAL_TZ,
    OTP_LABEL,
    TELEGRAM_CHATS_MAX,
    TV_ABSENT_SECONDS,
    TV_MAX,
    USD_RATE,
)
from board.stores import (
    ACCOUNTS,
    AUDIT_LOG,
    KEEP_LOCATION_DAYS,
    LOCATIONS,
    TEAM,
    TELEGRAM_BOT,
    TV,
    MCP_SCOPE_PEOPLE,
    MCP_SCOPE_TOTALS,
    TV_PAIRING,
    TV_STATUS,
    WAIT_TRACKER,
    clean_tv_name,
    device_label,
    side_of,
)


def all_branches() -> list:
    """Branches in the file declared by IT plus locations named on the board.
    Chi nhánh trong file do IT khai báo cộng với địa điểm đã đặt tên trên bảng."""
    loc_data = LOCATIONS.read()
    branches = [dict(b, networks=list(b["networks"]), customNetworks=[]) for b in load_branches()]
    branches += [{"id": b["id"], "name": b["name"], "lat": b["lat"], "lon": b["lon"], "isHq": b.get("isHq") is True,
            "people": set(), "networks": [], "customNetworks": []} for b in loc_data.get("branches", [])]
    by_id = {b["id"]: b for b in branches}
    for ip, location_id in loc_data.get("ipToLocation", {}).items():
        if location_id in by_id:
            by_id[location_id]["networks"].append(ipaddress.ip_network(ip))
            by_id[location_id]["customNetworks"].append(ip)
    return branches


def unnamed_groups(rows: list, branches: list, now: float) -> list:
    """People not in any branch yet, grouped by the most recent public IP; bigger groups first.
    Người chưa thuộc chi nhánh nào, gom theo IP công cộng gửi gần nhất; nhóm đông lên trước."""
    groups = {}
    for r in rows:
        ip = r.get("latestIp")
        if not ip or now - r["updatedAt"] / 1000 > KEEP_LOCATION_DAYS * 86400 or branch_of(r, branches):
            continue
        groups.setdefault(ip, []).append(r["name"])
    return [{"ip": ip, "people": sorted(name)} for ip, name in sorted(groups.items(), key=lambda x: (-len(x[1]), x[0]))]


def edit_location(d: dict, body: dict) -> None:
    """body: {ip, remove: true} removes a network; {ip, id} attaches it to an existing branch; {ip, name, lat, lon, isHq} creates a new location.
    body: {ip, remove: true} gỡ mạng; {ip, id} gắn vào chi nhánh đã có; {ip, name, lat, lon, isHq} tạo địa điểm mới."""
    # a wrong shape raises ValueError
    # sai dạng thì ném ValueError
    ip = str(ipaddress.ip_address(str(body.get("ip"))))
    ip_map, locations = d.setdefault("ipToLocation", {}), d.setdefault("branches", [])
    if body.get("remove") is True:
        location_id = ip_map.pop(ip, None)
        # a location set on the board with no network left is dropped too; enough is logged to set it again by hand
        # địa điểm đặt trên bảng không còn mạng nào thì bỏ luôn; ghi đủ để đặt lại tay
        if location_id and location_id not in ip_map.values():
            removed = next((b for b in locations if b["id"] == location_id), None)
            if body.get("confirm") is not True:
                raise ValueError(tx("This is the last network of the location, please confirm"))
            d["branches"] = [b for b in locations if b["id"] != location_id]
            return {"action": "unassign-delete-location", "ip": ip, "location": removed}
        return {"action": "unassign", "ip": ip, "id": location_id}
    if len(ip_map) >= 500 and ip not in ip_map:
        raise ValueError(tx("network limit reached"))
    location_id = body.get("id")
    if location_id is not None:
        if str(location_id) not in {b["id"] for b in all_branches()}:
            raise ValueError(tx("no such branch"))
        ip_map[ip] = str(location_id)
        return
    name = re.sub(r"[\x00-\x1f\x7f]", " ", str(body.get("name") or "")).strip()[:60]
    lat, lon = float(body.get("lat")), float(body.get("lon"))
    if not name or not (8 <= lat <= 24 and 102 <= lon <= 118):
        raise ValueError(tx("the name is missing or the position is wrong"))
    if len(locations) >= 100:
        raise ValueError(tx("location limit reached"))
    location_id = "loc" + secrets.token_hex(4)
    if body.get("isHq") is True:
        for b in locations:
            b["isHq"] = False
    locations.append({"id": location_id, "name": name, "lat": lat, "lon": lon, "isHq": body.get("isHq") is True})
    ip_map[ip] = location_id


def csv_number(o) -> float:
    try:
        n = float(str(o or "0").replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0
    # "nan" and "inf" parse as numbers but break the JSON that the pages read
    # "nan" và "inf" đọc được thành số nhưng làm hỏng JSON mà các trang đọc
    return n if math.isfinite(n) else 0.0


def parse_team_csv(text: str) -> dict:
    """Merge the Team plan "Export spend report" file per person. Column names are matched loosely, because the documentation does not promise the exact wording.
    Claude Code is kept apart: the plugin already counts that part on the machine, adding it would count it twice.
    Gộp file "Export spend report" của gói Team theo từng người. Tên cột so khớp lỏng, vì tài liệu không cam kết nguyên văn.
    Claude Code tách riêng: phần đó plugin đã đếm trên máy, cộng vào là tính hai lần."""
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    header_row = [h.strip().lower() for h in next(reader, [])]
    def column(*needles):
        return next((i for i, h in enumerate(header_row) if any(k in h for k in needles)), None)
    col_email, col_product = column("email"), column("product")
    col_requests, col_in, col_out, col_net, col_gross = column("request"), column("prompt"), column("completion"), column("net"), column("gross")
    if col_email is None or col_product is None or (col_net is None and col_gross is None and col_in is None):
        raise ValueError(tx("The file is missing the needed columns (email, product, cost or tokens). Use Export spend report."))
    people = {}
    for i, h in enumerate(reader):
        if i >= 50000:
            raise ValueError(tx("The file has too many rows"))
        if len(h) <= max(col_email, col_product):
            continue
        email = h[col_email].strip().lower()[:120]
        if "@" not in email:
            continue
        bucket = "code" if h[col_product].strip().lower() in ("claude code", "code") else "other"
        r = people.setdefault(email, {k: {"requests": 0, "tokensIn": 0, "tokensOut": 0, "net": 0.0, "gross": 0.0} for k in ("other", "code")})[bucket]
        for k, c in (("requests", col_requests), ("tokensIn", col_in), ("tokensOut", col_out), ("net", col_net), ("gross", col_gross)):
            if c is not None and c < len(h):
                r[k] += csv_number(h[c])
    if not people:
        raise ValueError(tx("The file has no user rows"))
    return people


def team_summary(rows: list):
    t = TEAM.read()
    if not t.get("people"):
        return None
    sale = set(LOCATIONS.read().get("salesTeam", []))
    device_accounts = {r["account"].lower() for r in rows if r["account"]}
    items = [{"email": e, "isSales": e in sale, "hasDevice": e in device_accounts, "other": v["other"], "code": v["code"]} for e, v in t["people"].items()]
    items.sort(key=lambda x: -(x["other"]["net"] or x["other"]["gross"]))
    return {"updatedAt": t.get("updatedAt"), "dateFrom": t.get("dateFrom", ""), "dateTo": t.get("dateTo", ""), "items": items}


def branch_of(r: dict, branches: list) -> str:
    """Which branch a person belongs to: by the name or email declared first, then by the declared public IP range.
    Người thuộc chi nhánh nào: theo tên hoặc email đã khai báo trước, sau đó theo dải IP công cộng đã khai báo."""
    person_keys = {str(r.get("account") or "").lower(), str(r.get("name") or "").lower()}
    for b in branches:
        if b["people"] & person_keys:
            return b["id"]
    for text in [r["latestIp"]] if r.get("latestIp") else r.get("ip") or []:
        try:
            ip = ipaddress.ip_address(text)
        except ValueError:
            continue
        for b in branches:
            if any(ip in m for m in b["networks"]):
                return b["id"]
    return ""


ALIAS_SALT = secrets.token_bytes(16)


def alias(text: str) -> str:
    """Replace an email with an unreadable code that still tells people apart; it changes after every start.
    Thay email bằng mã không đọc được, vẫn phân biệt được người; đổi sau mỗi lần khởi động."""
    return hmac.new(ALIAS_SALT, text.encode(), hashlib.sha256).hexdigest()[:10] if text else ""


def wall_name(name: str) -> str:
    """A device with no name declared may have an email or IP as its name: keep it off the wall display.
    Máy chưa khai tên thì tên có thể là email hoặc IP: không đưa lên màn hình treo tường."""
    return tx("Device {id}", id=alias(name)[:6]) if "@" in name or re.fullmatch(r"\d+\.\d+\.\d+\.\d+|[0-9a-fA-F:]*:[0-9a-fA-F:]*", name) else name


# what each role sees: an allow list, so a new field does not leak by itself. A field added to _raw_data must be ranked here
# (test_webhook.py turns red if you forget); a field not ranked reaches no role. An unknown role counts as wall, the role that sees the least.
# Mỗi vai thấy gì: danh sách cho phép, nên trường mới không tự lộ. Thêm trường vào _raw_data thì phải xếp nó ở đây
# (test_webhook.py đỏ nếu quên); trường chưa xếp thì không vai nào nhận được. Vai lạ coi như treo tường, là vai thấy ít nhất.
# teamDays: the whole team's cost on each of the last TEAM_DAYS days, for the small chart of the menu bar window. One number per day,
# no person and no office, so the wall role may have it; everything else of the daily totals stays with admins and viewers (usage_view).
# teamDays: chi phí của cả team trong từng ngày của TEAM_DAYS ngày gần nhất, cho biểu đồ nhỏ của khung thanh menu. Một con số mỗi ngày,
# không có người, không có văn phòng, nên vai treo tường được nhận; mọi phần khác của tổng theo ngày vẫn chỉ cho quản trị và người xem (usage_view).
TEAM_DAYS = 7
# one day of teamDays: the day and the team's cost that day, nothing else
# một ngày của teamDays: ngày đó và chi phí của cả team ngày đó, không gì khác
TEAM_DAY_FIELDS = frozenset({"day", "usd"})
COMMON_FIELDS_ALL = frozenset({"updatedAt", "usdRate", "tasks24", "tzOffsetHours", "people", "branches", "teamDays"})
COMMON_FIELDS_BY_ROLE = {
    ADMIN: COMMON_FIELDS_ALL | {"unnamedGroups", "team", "blocked7d"},
    VIEWER: COMMON_FIELDS_ALL | {"team", "blocked7d"},
    WALL: COMMON_FIELDS_ALL,
}
PERSON_FIELDS_ALL = frozenset({
    "branch", "name", "account", "shared", "deviceCount", "status", "openSessions", "working", "waiting", "delegating", "subagents",
    "usdToday", "usd7d", "tokensIn", "tokensOut", "tasks", "updatedAt", "waitingSince", "models", "assistants", "quota", "pluginVersion", "hourly24", "tools",
})
PERSON_FIELDS_BY_ROLE = {
    ADMIN: PERSON_FIELDS_ALL | {"lanIps", "enteredAccounts"},
    VIEWER: PERSON_FIELDS_ALL | {"lanIps", "enteredAccounts"},
    WALL: PERSON_FIELDS_ALL,
}
BRANCH_FIELDS_ALL = frozenset({"id", "name", "lat", "lon", "isHq"})
BRANCH_FIELDS_BY_ROLE = {
    ADMIN: BRANCH_FIELDS_ALL | {"customNetworks"},
    VIEWER: BRANCH_FIELDS_ALL,
    WALL: BRANCH_FIELDS_ALL,
}
HISTORY_ROW_FIELDS = frozenset({"at", "name", "account", "status", "delegating"})
COMMON_FIELDS_DECLARED = frozenset().union(*COMMON_FIELDS_BY_ROLE.values())
PERSON_FIELDS_DECLARED = frozenset().union(*PERSON_FIELDS_BY_ROLE.values())
BRANCH_FIELDS_DECLARED = frozenset().union(*BRANCH_FIELDS_BY_ROLE.values())


def _pick(d: dict, allowed: frozenset) -> dict:
    return {k: v for k, v in d.items() if k in allowed}


def role_view(role: str, now: float, every_branch: bool = False) -> dict:
    """The board's numbers by role: the only way user data goes out.
    A branch is on the board once a computer there has sent numbers; one that is only declared, with no computer yet,
    is left out unless every_branch is set (the Admin page, which has to manage those too).
    Số liệu của bảng đúng theo vai: đường duy nhất đưa số liệu người dùng ra ngoài.
    Chi nhánh có mặt trên bảng khi đã có máy ở đó gửi số liệu; nơi mới chỉ khai báo, chưa có máy nào,
    bị bỏ ra trừ khi đặt every_branch (trang Quản trị, nơi vẫn phải quản lý cả những chi nhánh đó)."""
    raw = _raw_data(now)
    v = role if role in COMMON_FIELDS_BY_ROLE else WALL
    d = _pick(raw, COMMON_FIELDS_BY_ROLE[v])
    d["people"] = [_pick(p, PERSON_FIELDS_BY_ROLE[v]) for p in raw["people"]]
    connected = {p["branch"] for p in raw["people"]}
    d["branches"] = [_pick(b, BRANCH_FIELDS_BY_ROLE[v]) for b in raw["branches"] if every_branch or b["id"] in connected]
    if v == WALL:
        for p in d["people"]:
            p.update(name=wall_name(p["name"]), account=alias(p["account"]))
    d["teamDays"] = [_pick(x, TEAM_DAY_FIELDS) for x in d.get("teamDays", [])]
    d.update(role=v, uiVersion=UI_VERSION)
    return d


def totals_view(now: float) -> dict:
    """What the window inside Telegram reads for a chat that reads totals only: the team's counts, added up here, and no person.
    Thứ khung bên trong Telegram đọc cho chat chỉ được đọc tổng: các con số của cả team, cộng sẵn ở đây, và không có người nào."""
    d = role_view(WALL, now)
    people = d.get("people", [])
    online = [p for p in people if p.get("status") != "offline"]
    return {
        "totalsOnly": True, "updatedAt": d["updatedAt"], "usdRate": d["usdRate"], "tzOffsetHours": d["tzOffsetHours"],
        "tasks24": d["tasks24"], "teamDays": d["teamDays"], "people": [], "role": d["role"], "uiVersion": d["uiVersion"],
        "totals": {
            "waiting": sum(1 for p in online if p.get("waiting")),
            "working": sum(1 for p in online if p.get("working") and not p.get("waiting")),
            "openSessions": sum(int(p.get("openSessions") or 0) for p in online),
            "usdToday": round(sum(float(p.get("usdToday") or 0) for p in people), 4),
            "tokens": sum(int(p.get("tokensIn") or 0) + int(p.get("tokensOut") or 0) for p in people),
        },
    }


def _team_days(now: float) -> list:
    """The team's last TEAM_DAYS days for role_view; an empty list when the side table cannot be read, so the board still answers.
    TEAM_DAYS ngày gần nhất của cả team cho role_view; danh sách rỗng khi không đọc được bảng phụ, để bảng vẫn trả lời."""
    try:
        return DAILY.team_days(now, TEAM_DAYS)
    except Exception as e:
        sys.stderr.write("daily: %s\n" % e)
        return []


# Use over weeks and months, built from the daily totals: the same kind of allow list, apart from the live board. Only an admin and a viewer
# get it; the wall role gets nothing of it (only teamDays in role_view, one team total per day), so a TV screen, the menu bar, the extension, the plugin and the MCP endpoint have none of it.
# Mức dùng theo tuần và theo tháng, dựng từ tổng theo ngày: cùng kiểu danh sách cho phép, tách khỏi bảng trực tiếp. Chỉ quản trị và người xem
# nhận được; vai treo tường không nhận gì của phần này (chỉ teamDays trong role_view, một tổng của cả team mỗi ngày), nên màn hình TV, thanh menu, tiện ích, plugin và cổng MCP đều không có phần này.
USAGE_FIELDS_ALL = frozenset({"today", "since", "periods", "team", "offices", "people", "weeks", "months"})
USAGE_FIELDS_BY_ROLE = {ADMIN: USAGE_FIELDS_ALL, VIEWER: USAGE_FIELDS_ALL, WALL: frozenset()}
USAGE_OFFICE_FIELDS_ALL = frozenset({"id", "name", "weeks"}) | frozenset(PERIODS)
USAGE_OFFICE_FIELDS_BY_ROLE = {ADMIN: USAGE_OFFICE_FIELDS_ALL, VIEWER: USAGE_OFFICE_FIELDS_ALL, WALL: frozenset()}
USAGE_PERSON_FIELDS_ALL = frozenset({"name", "account", "office"}) | frozenset(PERIODS)
USAGE_PERSON_FIELDS_BY_ROLE = {ADMIN: USAGE_PERSON_FIELDS_ALL, VIEWER: USAGE_PERSON_FIELDS_ALL, WALL: frozenset()}
USAGE_NUMBER_FIELDS = frozenset(NUMBERS)
# one week or month of the charts
# một tuần hoặc một tháng của biểu đồ
USAGE_SPAN_FIELDS = frozenset({"from", "to", "kept", "whole", "usd"})
USAGE_FIELDS_DECLARED = frozenset().union(*USAGE_FIELDS_BY_ROLE.values())
USAGE_OFFICE_FIELDS_DECLARED = frozenset().union(*USAGE_OFFICE_FIELDS_BY_ROLE.values())
USAGE_PERSON_FIELDS_DECLARED = frozenset().union(*USAGE_PERSON_FIELDS_BY_ROLE.values())


def _pick_usage(d: dict, allowed: frozenset) -> dict:
    """One team, office or person of the usage numbers: the allowed fields only, and inside each span the known numbers only.
    Một đội, một văn phòng hay một người trong số liệu mức dùng: chỉ các trường được phép, và trong mỗi khoảng chỉ các con số đã biết."""
    out = {k: _pick(v, USAGE_NUMBER_FIELDS) if k in PERIODS else v for k, v in d.items() if k in allowed}
    if "weeks" in out:
        out["weeks"] = [n for n in out["weeks"] if isinstance(n, (int, float))]
    return out


def usage_view(role: str, now: float) -> dict:
    """Use by week and by month, by role: the only way the daily totals go out. A role that may not see them gets an empty dict.
    Mức dùng theo tuần và theo tháng, đúng theo vai: đường duy nhất đưa tổng theo ngày ra ngoài. Vai không được xem thì nhận một dict rỗng."""
    v = role if role in USAGE_FIELDS_BY_ROLE else WALL
    if not USAGE_FIELDS_BY_ROLE[v]:
        return {}
    raw = _raw_usage(now)
    d = _pick(raw, USAGE_FIELDS_BY_ROLE[v])
    d["team"] = _pick_usage(raw["team"], frozenset(PERIODS))
    for kind in ("weeks", "months"):
        d[kind] = [_pick(span, USAGE_SPAN_FIELDS) for span in raw[kind]]
    d["offices"] = [_pick_usage(o, USAGE_OFFICE_FIELDS_BY_ROLE[v]) for o in raw["offices"]]
    d["people"] = [_pick_usage(p, USAGE_PERSON_FIELDS_BY_ROLE[v]) for p in raw["people"]]
    return d


def history_view(role: str, now: float) -> dict:
    """The 24-hour history by role, same rule as role_view.
    Diễn biến 24 giờ theo vai, cùng nguyên tắc với role_view."""
    d = HISTORY.read(now)
    rows = [_pick(x, HISTORY_ROW_FIELDS) for x in d.get("items", [])]
    if role not in (ADMIN, VIEWER):
        rows = [{**x, "name": wall_name(x["name"]), "account": alias(x.get("account", ""))} for x in rows]
    return {**d, "items": rows}


def branch_name_for_ip(ip: str) -> str:
    branches = all_branches()
    branch_id = branch_of({"latestIp": ip}, branches)
    return next((b["name"] for b in branches if b["id"] == branch_id), "")


def tv_action(path: str, body: dict, actor: str) -> tuple:
    """View a request, approve, revoke, rename a screen. Returns (the part for the log, the part to send back).
    Xem yêu cầu, duyệt, thu hồi, đổi tên màn hình. Trả (phần ghi nhật ký, phần trả về)."""
    now = time.time()
    if path == "/admin/tv-reload":
        tv_id = str(body.get("id") or "")
        if tv_id not in TV.d:
            raise ValueError(tx("This screen no longer exists"))
        TV_STATUS.request_reload(tv_id)
        return {"action": "tv-reload", "tv": TV.d[tv_id]["name"], "id": tv_id}, {}
    if path == "/admin/tv-revoke":
        tv_id = str(body.get("id") or "")
        kind = (TV.d.get(tv_id) or {}).get("kind", "")
        return {"action": "tv-revoke", "tv": TV.revoke(tv_id), "id": tv_id, **({"kind": kind} if kind else {})}, {}
    if path == "/admin/tv-rename":
        tv_id, name = str(body.get("id") or ""), clean_tv_name(body.get("name"))
        TV.check_name(name, tv_id, now)
        TV.rename(tv_id, name)
        return {"action": "tv-rename", "tv": name, "id": tv_id}, {}
    if path == "/admin/tv-app":
        # a Telegram chat may open the board's window inside Telegram, or no longer; the bot process sets its menu button within a minute
        # một chat Telegram được mở khung của bảng bên trong Telegram, hoặc thôi; tiến trình bot đặt nút menu của nó trong vòng một phút
        tv_id, on = str(body.get("id") or ""), body.get("on")
        if not isinstance(on, bool):
            raise ValueError(tx("Invalid settings"))
        row = TV.set_app(tv_id, on)
        if not on:
            TG_APP_SESSIONS.end_chat(str(row.get("telegramId", "")))
        return {"action": "telegram-app-on" if on else "telegram-app-off", "tv": row["name"], "id": tv_id, "kind": KIND_TELEGRAM}, {}
    code = re.sub(r"\D", "", str(body.get("code") or ""))
    if path == "/admin/tv-view":
        r = TV_PAIRING.peek(code, actor, now)
        result = {"ip": r["ip"], "branch": branch_name_for_ip(r["ip"]), "device": device_label(r["device"]), "createdAt": int(r["createdAt"] * 1000), "secondsLeft": int(r["expiresAt"] - now),
               "similar": TV.similar(r["ip"], r["device"], now, side_of(r.get("kind"))), "kind": r.get("kind", "")}
        if r.get("kind") == KIND_TELEGRAM:
            # a chat has no IP and no browser: the admin sees whose Telegram it is, and the board account linked to that Telegram, if any.
            # A chat replaces its own earlier row by itself, so no row is offered to replace
            # chat không có IP hay trình duyệt: quản trị thấy đó là Telegram của ai, và tài khoản bảng đã liên kết với Telegram đó, nếu có.
            # Chat tự thay dòng cũ của chính nó, nên không gợi ý dòng nào để thay
            result.update(similar=[], device="Telegram", telegramUser=r.get("telegramUser", ""), telegramId=r.get("telegramId", ""),
                          account=ACCOUNTS.find_by_telegram(r.get("telegramId", "")) or "")
        return {"action": "tv-view", "tvIp": r["ip"], "tvDevice": result["device"], **({"kind": r["kind"]} if r.get("kind") else {}),
                **({"telegramUser": r.get("telegramUser", "")} if r.get("kind") == KIND_TELEGRAM else {})}, result
    name, replace_id = clean_tv_name(body.get("name")), str(body.get("replaceId") or "")
    if replace_id and replace_id not in TV.d:
        raise ValueError(tx("The screen to replace no longer exists"))
    TV.check_name(name, replace_id, now)
    side = side_of(TV_PAIRING.kind_of(code, now))
    # a row is replaced only by one of its own side: a screen's row must not turn into a key for the MCP endpoint or into a Telegram
    # chat, nor the other way round. A chat replaces only its own earlier row, which it does by itself
    # một dòng chỉ được thay bằng dòng cùng phía: dòng của màn hình không được biến thành khoá cho cổng MCP hay thành chat Telegram,
    # và ngược lại. Chat chỉ thay dòng cũ của chính nó, và nó tự làm việc đó
    if replace_id and (side_of(TV.d[replace_id].get("kind")) != side or side == KIND_TELEGRAM):
        raise ValueError(tx("The screen to replace no longer exists"))
    if not replace_id and side == KIND_MCP and TV.count(now, KIND_MCP) >= MCP_KEYS_MAX:
        raise ValueError(tx("Limit of {n} MCP keys reached, revoke some first", n=MCP_KEYS_MAX))
    if side == KIND_TELEGRAM and TV.count(now, KIND_TELEGRAM) >= TELEGRAM_CHATS_MAX:
        raise ValueError(tx("Limit of {n} Telegram chats reached, revoke some first", n=TELEGRAM_CHATS_MAX))
    if not replace_id and not side and TV.count(now) >= TV_MAX:
        raise ValueError(tx("Limit of {n} screens reached, remove some first", n=TV_MAX))
    # what an MCP key or a Telegram chat may read is the admin's choice at this step; with no choice sent, it reads totals only
    # khoá MCP hay chat Telegram được đọc gì là lựa chọn của quản trị ở bước này; không gửi lựa chọn thì chỉ đọc số gộp
    scope = (MCP_SCOPE_PEOPLE if body.get("scope") == MCP_SCOPE_PEOPLE else MCP_SCOPE_TOTALS) if side else ""
    r = TV_PAIRING.approve(code, name, actor, now, replace_id, scope)
    return {"action": "tv-approve", "tv": name, **({"replacedId": replace_id} if replace_id else {}), **({"kind": r["kind"]} if r.get("kind") else {}), **({"scope": scope} if scope else {}),
            **({"telegramUser": r.get("telegramUser", "")} if r.get("kind") == KIND_TELEGRAM else {}),
            "tvIp": r["ip"], "tvDevice": device_label(r["device"]), "branch": branch_name_for_ip(r["ip"])}, {}


def admin_data(now: float, cookie: str, month: str) -> dict:
    d = role_view(ADMIN, now, every_branch=True)
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        month = datetime.fromtimestamp(now, LOCAL_TZ).strftime("%Y-%m")
    tv = []
    for x in TV.list_screens(now):
        seen_state = None if x["exitedAt"] else TV_STATUS.read(x["id"])
        tv.append(dict(x, branch=branch_name_for_ip(x["lastIp"]), device=device_label(x["device"]), upToDate=None if x.get("owner") or x["kind"] in (KIND_EXTENSION, KIND_PLUGIN, KIND_MCP, KIND_TELEGRAM) or re.search(r"menu ?bar", x["device"], re.I) else (seen_state["ui"] == UI_VERSION) if seen_state else None,
                       lastSeenAt=int(seen_state["seenAt"] * 1000) if seen_state else None, running=bool(seen_state) and now - seen_state["seenAt"] < TV_ABSENT_SECONDS,
                       # a key for an AI tool: whole days since it was last used (or made), so a key nobody uses any more stands out
                       # khoá cho công cụ AI: số ngày tròn từ lần dùng cuối (hoặc lúc tạo), để khoá không ai dùng nữa nổi lên
                       idleDays=idle_days(x, now) if x["kind"] == KIND_MCP else None))
    return {"accounts": ACCOUNTS.list_accounts(), "screens": tv, "sessions": SESSIONS.list_sessions(cookie, now), "unnamedGroups": d["unnamedGroups"], "branches": d["branches"], "team": d["team"], "blocked7d": d.get("blocked7d"),
            "usdRate": USD_RATE, "month": month, "auditLog": AUDIT_LOG.read(month), "auditChain": AUDIT_LOG.check(now), "mcpCalls": AUDIT_LOG.read_calls(month, 100),
            # work handed to ChatGPT, Gemini or Gemma this month: totals and the newest records, never the text
            # việc giao cho ChatGPT, Gemini hay Gemma trong tháng: số tổng và các biên bản mới nhất, không bao giờ có chữ
            "delegations": AUDIT_LOG.read_delegations(month, 50), "delegationTotals": AUDIT_LOG.delegation_totals(month), "menubarDmg": bool(menubar_mac_dmg()),
            "menubarMsi": os.path.isfile(os.path.join(packages.MENUBAR_DIR, "AI-Worker.msi")), "menubarExtension": bool(menubar_extension()),
            # asking the board from Telegram: whether it is turned on, and what the bot process last said about itself
            # hỏi bảng qua Telegram: có đang bật không, và tiến trình bot nói gì gần nhất về chính nó
            "telegramAsk": dict(TELEGRAM_BOT.read(), on=settings.TELEGRAM_ASK_ENABLED, app=settings.TELEGRAM_APP_ENABLED),
            # whether /mcp/connect exists, so the page points to it only when it does (MCP=0 turns it off)
            # /mcp/connect có tồn tại không, để trang chỉ trỏ tới khi có (MCP=0 tắt nó)
            "mcpOn": settings.MCP_ENABLED, "mcpIdleDays": settings.MCP_IDLE_DAYS}


def idle_days(row: dict, now: float) -> int:
    """Whole days since a paired row was last used, or made when it never was. Use is written at most once a day, so this is right to the day.
    Số ngày tròn từ lần cuối một dòng đã ghép được dùng, hoặc từ lúc tạo nếu chưa dùng lần nào. Lần dùng ghi tối đa mỗi ngày một lần, nên đúng tới ngày."""
    last = max(int(row.get("lastUsedAt") or 0), int(row.get("createdAt") or 0))
    return max(0, int((now - last) // 86400)) if last else 0


def manage_account(body: dict, actor: str, token: str) -> tuple:
    """Create, reissue, change role, delete. Returns (the part for the log, the part to send back); the key is only in the part sent back.
    Tạo, cấp lại, đổi vai, xoá. Trả (phần ghi nhật ký, phần trả về); khoá chỉ nằm ở phần trả về."""
    jobs, name, role = body.get("action"), str(body.get("name") or ""), body.get("role")
    if not ACCOUNT_NAME_RE.fullmatch(name):
        raise ValueError(tx("Use only letters without accents, digits, . _ - (up to 30 characters)"))
    if jobs in ("create", "role") and role not in (ADMIN, VIEWER, WALL):
        raise ValueError(tx("Wrong role"))
    result = {}
    if jobs == "create":
        result["secret"] = ACCOUNTS.create(name, role, actor)
    elif jobs == "reissue":
        result["secret"] = ACCOUNTS.reissue(name)
        # a Telegram link made with the old key may be someone else's: it has to be made again
        # liên kết Telegram làm bằng khoá cũ có thể là của người khác: phải liên kết lại
        ACCOUNTS.unlink_telegram(name)
        # the old key may have leaked: drop this person's other sessions
        # khoá cũ có thể đã lộ: bỏ các phiên khác của người này
        SESSIONS.end_sessions_of(name, token)
    elif jobs == "role":
        old_role = ACCOUNTS.change_role(name, role)
        # wall sessions last longer: leaving or entering that role means logging in again, so the lifetime is right
        # phiên treo tường dài hơn: rời hoặc vào vai đó thì đăng nhập lại cho đúng hạn
        if WALL in (old_role, role) and old_role != role:
            SESSIONS.end_sessions_of(name)
        # only a viewer or an admin may own menu bar computers
        # chỉ vai xem hoặc quản trị được có máy thanh menu
        if role == WALL:
            TV.revoke_owner(name)
            ACCOUNTS.unlink_telegram(name)
    elif jobs == "telegram-unlink":
        if not ACCOUNTS.unlink_telegram(name):
            raise ValueError(tx("This account has no Telegram linked"))
    elif jobs == "delete":
        if name == actor:
            raise ValueError(tx("You cannot delete yourself, ask another admin"))
        ACCOUNTS.delete(name)
        SESSIONS.end_sessions_of(name)
        TV.revoke_owner(name)
    else:
        raise ValueError(tx("Wrong action"))
    if "secret" in result:
        result["uri"] = "otpauth://totp/%s:%s?secret=%s&issuer=%s&digits=6&period=30" % (OTP_LABEL, name, result["secret"], OTP_LABEL)
    return {"action": "account-" + jobs, "accountName": name, **({"newRole": role} if jobs in ("create", "role") else {})}, result


def _raw_data(now: float) -> dict:
    """All the numbers, unfiltered: only role_view may call it, do not return this function directly.
    Mọi số liệu, chưa lọc: chỉ role_view được gọi, đừng trả thẳng hàm này ra ngoài."""
    devices = read_all_devices()
    rows = group_by_person(devices, now)
    this_hour = int(now // 3600)
    out = []
    branches = all_branches()
    for r in rows:
        out.append({
            "branch": branch_of(r, branches),
            "name": r["name"], "account": r["account"], "shared": r["shared"], "deviceCount": r["deviceCount"],
            "lanIps": r["lanIps"], "enteredAccounts": r["enteredAccounts"], "status": status_of(r, now),
            "openSessions": r["openSessions"], "working": r["working"], "waiting": r["waiting"], "delegating": r["delegating"],
            # which tools have a session open now, each with its own counts
            # công cụ nào đang có phiên mở, mỗi công cụ kèm số của nó
            "tools": r["tools"],
            "subagents": [{"name": k, "count": v} for k, v in sorted(r["subagents"].items())],
            "usdToday": round(r["usdToday"], 4), "usd7d": round(r["usd7d"], 4), "tokensIn": r["tokensIn"], "tokensOut": r["tokensOut"],
            "tasks": r["tasks"], "updatedAt": r["updatedAt"],
            "waitingSince": WAIT_TRACKER.note(r["account"] + "|" + r["name"], r["waiting"] if r["online"] else 0, now),
            "models": r["models"], "assistants": {"known": r["known"], "gemma": r["gemma"], "chatgpt": r["chatgpt"], "gemini": r["gemini"],
                                             "chatgptModels": r["chatgptModels"], "geminiModels": r["geminiModels"]},
            "quota": r["quota"], "pluginVersion": r["pluginVersion"],
            # cost per hour, last 24 hours, oldest first
            # chi phí từng giờ, 24 giờ gần nhất, cũ trước mới sau
            "hourly24": [round(r["costByHour"].get(this_hour - 23 + i, 0.0), 4) for i in range(24)],
        })
    # tasks delegated to each AI per hour, whole team, last 24 hours
    # việc giao cho từng AI theo giờ, cả team, 24 giờ gần nhất
    jobs24 = [[sum(r["tasksByHour"].get(this_hour - 23 + i, [0, 0, 0])[k] for r in rows) for i in range(24)] for k in range(3)]
    return {"updatedAt": int(now * 1000), "usdRate": USD_RATE, "tasks24": jobs24, "tzOffsetHours": LOCAL_TZ.utcoffset(None).total_seconds() / 3600, "teamDays": _team_days(now), "people": out,
            # what ai-worker stopped or asked about across the team in the last 7 days, totals only
            # những gì ai-worker đã chặn hay hỏi trên cả team trong 7 ngày qua, chỉ số tổng
            "blocked7d": blocks_since(devices, this_hour - 7 * 24 + 1),
            "branches": [{"id": b["id"], "name": b["name"], "lat": b["lat"], "lon": b["lon"], "isHq": b["isHq"], "customNetworks": b["customNetworks"]} for b in branches],
            "unnamedGroups": unnamed_groups(rows, branches, now), "team": team_summary(rows)}


class History:
    """24-hour history for the rewind button: whenever a person's state changes, one row is added
    (time, person, state, number of tasks being delegated to Gemini/ChatGPT/Gemma). No chat content.
    Diễn biến 24 giờ cho nút tua lại: mỗi khi trạng thái một người đổi thì thêm một dòng
    (thời điểm, người, trạng thái, số việc đang giao cho Gemini/ChatGPT/Gemma). Không có nội dung chat."""

    KEEP_SECONDS = 24 * 3600

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()
        self.rows = []
        self.last = {}
        self.cleaned_at = 0.0
        for at, name, account, status, delegating in database.rows("SELECT at, name, account, status, delegating FROM history ORDER BY id"):
            try:
                delegating = json.loads(delegating) if delegating else None
            except ValueError:
                delegating = None
            d = {"at": at, "name": name, "account": account, "status": status, "delegating": delegating}
            self.rows.append(d)
            self.last[(name, account)] = (status, delegating)

    def record_if_changed(self, rows: list, now: float) -> None:
        new_rows = []
        with self.lock:
            for r in rows:
                k = (r["name"], r["account"])
                state = (status_of(r, now), list(r["delegating"]))
                if self.last.get(k) == state:
                    continue
                self.last[k] = state
                new_rows.append({"at": int(now * 1000), "name": r["name"], "account": r["account"], "status": state[0], "delegating": state[1]})
            if new_rows:
                self.rows.extend(new_rows)
                with self.db.tx() as c:
                    for d in new_rows:
                        c.execute("INSERT INTO history (at, name, account, status, delegating) VALUES (?, ?, ?, ?, ?)",
                                  (d["at"], d["name"], d["account"], d["status"], dumps(d["delegating"])))
            # every hour drop what is older than 24 hours (keep each person's last row before the cutoff as the starting state)
            # mỗi giờ bỏ phần quá 24 giờ (giữ lại dòng cuối trước mốc của từng người làm trạng thái đầu)
            if now - self.cleaned_at > 3600:
                self.cleaned_at = now
                self.rows = self._last_24h(now)
                with self.db.tx() as c:
                    c.execute("DELETE FROM history")
                    for d in self.rows:
                        c.execute("INSERT INTO history (at, name, account, status, delegating) VALUES (?, ?, ?, ?, ?)",
                                  (d["at"], d["name"], d.get("account", ""), d.get("status"), dumps(d.get("delegating"))))

    def _last_24h(self, now: float) -> list:
        cutoff = int((now - self.KEEP_SECONDS) * 1000)
        first, after = {}, []
        for d in self.rows:
            if d["at"] < cutoff:
                first[(d["name"], d.get("account", ""))] = dict(d, at=cutoff)
            else:
                after.append(d)
        return list(first.values()) + after

    def read(self, now: float) -> dict:
        with self.lock:
            return {"now": int(now * 1000), "since": int((now - self.KEEP_SECONDS) * 1000), "items": self._last_24h(now)}


HISTORY = History(data_db())
INGEST_GATE = IngestGate(data_db())
DAILY = DailyStore(data_db())


def _raw_usage(now: float) -> dict:
    """The usage numbers, unfiltered: only usage_view may call it, do not return this function directly.
    Số liệu mức dùng, chưa lọc: chỉ usage_view được gọi, đừng trả thẳng hàm này ra ngoài."""
    return DAILY.summary(now, {b["id"]: b["name"] for b in all_branches()})


def record_daily() -> None:
    """Count the last days again from what the computers hold and write them over the daily totals; also drops rows and upgrade backups past their time.
    Đếm lại những ngày gần nhất từ thứ các máy đang giữ rồi ghi đè lên tổng theo ngày; đồng thời bỏ các dòng và bản sao lưu nâng cấp đã quá hạn."""
    try:
        now = time.time()
        devices = read_all_devices()
        branches = all_branches()
        names = {b["id"]: b["name"] for b in branches}
        offices = {}
        for r in group_by_person(devices, now):
            branch = branch_of(r, branches)
            offices[r["key"]] = (branch, names.get(branch, ""))
        DAILY.record(totals_by_day(devices, now), offices, now)
        for database in (data_db(), keys_db()):
            database.drop_old_upgrade_backups(now)
    # a side table: if it breaks, say so and carry on, do not crash the webhook
    # bảng phụ: hỏng thì báo rồi chạy tiếp, không làm sập webhook
    except Exception as e:
        sys.stderr.write("daily: %s\n" % e)


def daily_loop() -> None:
    """Keep the daily totals up to date: at start, then every DAILY_RECOUNT_SECONDS.
    Giữ tổng theo ngày luôn mới: lúc khởi động, rồi mỗi DAILY_RECOUNT_SECONDS."""
    while True:
        record_daily()
        time.sleep(DAILY_RECOUNT_SECONDS)


def record_history() -> None:
    try:
        now = time.time()
        HISTORY.record_if_changed(group_by_person(read_all_devices(), now), now)
    # a side log: if it breaks, ignore it, do not crash the webhook
    # nhật ký phụ: hỏng thì bỏ qua, không làm sập webhook
    except Exception as e:
        sys.stderr.write("history: %s\n" % e)


def history_loop() -> None:
    """A device that is switched off sends nothing, so the webhook must look again regularly (to record the switch to offline).
    Máy tắt không gửi gì nên phải tự xem lại định kỳ (để ghi được lúc chuyển sang ngoại tuyến)."""
    while True:
        record_history()
        time.sleep(30)
