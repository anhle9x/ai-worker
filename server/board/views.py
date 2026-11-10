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

from board import packages
from board.assets import UI_VERSION
from board.db import data_db, dumps
from board.devices import (
    IngestGate,
    group_by_person,
    load_branches,
    read_all_devices,
    status_of,
)
from board.lang import tx
from board.login import SESSIONS
from board.packages import menubar_extension, menubar_mac_dmg
from board.security import ACCOUNT_NAME_RE, ADMIN, VIEWER, WALL
from board.settings import (
    KIND_EXTENSION,
    LOCAL_TZ,
    OFFLINE_SECONDS,
    OTP_LABEL,
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
    TV,
    TV_PAIRING,
    TV_STATUS,
    WAIT_TRACKER,
    clean_tv_name,
    device_label,
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
COMMON_FIELDS_ALL = frozenset({"updatedAt", "usdRate", "tasks24", "tzOffsetHours", "people", "branches"})
COMMON_FIELDS_BY_ROLE = {
    ADMIN: COMMON_FIELDS_ALL | {"unnamedGroups", "team"},
    VIEWER: COMMON_FIELDS_ALL | {"team"},
    WALL: COMMON_FIELDS_ALL,
}
PERSON_FIELDS_ALL = frozenset({
    "branch", "name", "account", "shared", "deviceCount", "status", "openSessions", "working", "waiting", "delegating", "subagents",
    "usdToday", "usd7d", "tokensIn", "tokensOut", "tasks", "updatedAt", "waitingSince", "models", "assistants", "quota", "pluginVersion", "hourly24",
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


def role_view(role: str, now: float) -> dict:
    """The board's numbers by role: the only way user data goes out.
    Số liệu của bảng đúng theo vai: đường duy nhất đưa số liệu người dùng ra ngoài."""
    raw = _raw_data(now)
    v = role if role in COMMON_FIELDS_BY_ROLE else WALL
    d = _pick(raw, COMMON_FIELDS_BY_ROLE[v])
    d["people"] = [_pick(p, PERSON_FIELDS_BY_ROLE[v]) for p in raw["people"]]
    d["branches"] = [_pick(b, BRANCH_FIELDS_BY_ROLE[v]) for b in raw["branches"]]
    if v == WALL:
        for p in d["people"]:
            p.update(name=wall_name(p["name"]), account=alias(p["account"]))
    d.update(role=v, uiVersion=UI_VERSION)
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
    code = re.sub(r"\D", "", str(body.get("code") or ""))
    if path == "/admin/tv-view":
        r = TV_PAIRING.peek(code, actor, now)
        result = {"ip": r["ip"], "branch": branch_name_for_ip(r["ip"]), "device": device_label(r["device"]), "createdAt": int(r["createdAt"] * 1000), "secondsLeft": int(r["expiresAt"] - now),
               "similar": TV.similar(r["ip"], r["device"], now), "kind": r.get("kind", "")}
        return {"action": "tv-view", "tvIp": r["ip"], "tvDevice": result["device"], **({"kind": r["kind"]} if r.get("kind") else {})}, result
    name, replace_id = clean_tv_name(body.get("name")), str(body.get("replaceId") or "")
    if replace_id and replace_id not in TV.d:
        raise ValueError(tx("The screen to replace no longer exists"))
    TV.check_name(name, replace_id, now)
    if not replace_id and len(TV.list_screens(now)) >= TV_MAX:
        raise ValueError(tx("Limit of {n} screens reached, remove some first", n=TV_MAX))
    r = TV_PAIRING.approve(code, name, actor, now, replace_id)
    return {"action": "tv-approve", "tv": name, **({"replacedId": replace_id} if replace_id else {}), **({"kind": r["kind"]} if r.get("kind") else {}), "tvIp": r["ip"], "tvDevice": device_label(r["device"]), "branch": branch_name_for_ip(r["ip"])}, {}


def admin_data(now: float, cookie: str, month: str) -> dict:
    d = role_view(ADMIN, now)
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        month = datetime.fromtimestamp(now, LOCAL_TZ).strftime("%Y-%m")
    tv = []
    for x in TV.list_screens(now):
        seen_state = None if x["exitedAt"] else TV_STATUS.read(x["id"])
        tv.append(dict(x, branch=branch_name_for_ip(x["lastIp"]), device=device_label(x["device"]), upToDate=None if x.get("owner") or x["kind"] == KIND_EXTENSION or re.search(r"menu ?bar", x["device"], re.I) else (seen_state["ui"] == UI_VERSION) if seen_state else None,
                       lastSeenAt=int(seen_state["seenAt"] * 1000) if seen_state else None, running=bool(seen_state) and now - seen_state["seenAt"] < TV_ABSENT_SECONDS))
    return {"accounts": ACCOUNTS.list_accounts(), "screens": tv, "sessions": SESSIONS.list_sessions(cookie, now), "unnamedGroups": d["unnamedGroups"], "branches": d["branches"], "team": d["team"],
            "usdRate": USD_RATE, "month": month, "auditLog": AUDIT_LOG.read(month), "menubarDmg": bool(menubar_mac_dmg()),
            "menubarMsi": os.path.isfile(os.path.join(packages.MENUBAR_DIR, "AI-Worker.msi")), "menubarExtension": bool(menubar_extension())}


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
    rows = group_by_person(read_all_devices(), now)
    this_hour = int(now // 3600)
    out = []
    branches = all_branches()
    for r in rows:
        out.append({
            "branch": branch_of(r, branches),
            "name": r["name"], "account": r["account"], "shared": r["shared"], "deviceCount": r["deviceCount"],
            "lanIps": r["lanIps"], "enteredAccounts": r["enteredAccounts"], "status": status_of(r, now),
            "openSessions": r["openSessions"], "working": r["working"], "waiting": r["waiting"], "delegating": r["delegating"],
            "subagents": [{"name": k, "count": v} for k, v in sorted(r["subagents"].items())],
            "usdToday": round(r["usdToday"], 4), "usd7d": round(r["usd7d"], 4), "tokensIn": r["tokensIn"], "tokensOut": r["tokensOut"],
            "tasks": r["tasks"], "updatedAt": r["updatedAt"],
            "waitingSince": WAIT_TRACKER.note(r["account"] + "|" + r["name"], r["waiting"] if now - r["updatedAt"] / 1000 < OFFLINE_SECONDS else 0, now),
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
    return {"updatedAt": int(now * 1000), "usdRate": USD_RATE, "tasks24": jobs24, "tzOffsetHours": LOCAL_TZ.utcoffset(None).total_seconds() / 3600, "people": out,
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
