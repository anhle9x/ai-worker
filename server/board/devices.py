"""Numbers sent by each computer: checking, cleaning, saving and grouping them by person.
Số liệu từng máy gửi: kiểm, làm sạch, lưu và gộp theo người."""

import hmac
import ipaddress
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta

from board.db import data_db, device_row
from board.settings import (
    CONNECTOR_OFFLINE_SECONDS,
    CONNECTOR_TOOLS,
    CONNECTOR_WORKING_SECONDS,
    DEVICE_NAME_RE,
    INGEST_PER_IP,
    IP_HISTORY_MAX,
    KEEP_DAYS,
    LOCAL_TZ,
    MAX_DEVICES,
    MAX_HOURS_PER_DEVICE,
    NEW_DEVICES_PER_IP,
    OFFLINE_SECONDS,
)


def key_matches(header: str, key: str) -> bool:
    ingest_times = header[7:] if header.startswith("Bearer ") else ""
    return bool(key) and hmac.compare_digest(ingest_times.encode(), key.encode())


def is_valid_payload(d) -> bool:
    return (
        isinstance(d, dict)
        and d.get("v") == 1
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


def clean_hours(v, now_ms: float, keys=None) -> dict:
    """Numbers per hour, newest hours kept. A real hour number only, up to one day ahead for a wrong clock.
    Số liệu theo giờ, giữ các giờ mới nhất. Chỉ nhận số giờ thật, tối đa sớm hơn một ngày cho đồng hồ lệch."""
    out = {}
    if isinstance(v, dict):
        top = int(now_ms / 3_600_000) + 24
        hours = [k for k in v if isinstance(k, str) and re.fullmatch(r"[0-9]{1,8}", k) and int(k) <= top]
        for k in sorted(hours, key=int)[-MAX_HOURS_PER_DEVICE:]:
            table = clean_counts(v[k], keys)
            if table:
                out[k] = table
    return out


SESSION_COUNTS = ("openSessions", "working", "waiting")


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


def clean_payload(d, now: float):
    """Rebuild what a device sent from a fixed list of fields, types and sizes; None if it is not a device report.
    Runs on /ingest and again on every file read, so one bad file cannot take down the pages for everyone.
    Dựng lại số liệu một máy gửi từ danh sách cố định các trường, kiểu và cỡ; None nếu không phải báo cáo của máy.
    Chạy ở /ingest và mỗi lần đọc file, để một file xấu không làm sập trang của mọi người."""
    now_ms = now * 1000
    if not is_valid_payload(d):
        return None
    updated_at = clean_number(d["updatedAt"])
    if updated_at is None:
        return None
    out = {"v": 1, "device": d["device"], "updatedAt": min(updated_at, now_ms + 86_400_000)}
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
    out["ledger"] = clean_hours(d.get("ledger"), now_ms)
    out["tasks"] = clean_hours(d.get("tasks"), now_ms, workers)
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


def add_ip_history(old: list, ip: str, at_ms: float) -> list:
    """Add this send to a device's IP history: one row per IP (from, to), rows older than KEEP_DAYS dropped, the newest IP_HISTORY_MAX kept.
    Thêm lần gửi này vào lịch sử IP của máy: mỗi IP một dòng (từ lúc, tới lúc), bỏ dòng quá KEEP_DAYS, giữ IP_HISTORY_MAX dòng mới nhất."""
    out = [dict(e) for e in old if at_ms - e["to"] < KEEP_DAYS * 86_400_000 and e["ip"] != ip]
    same = [e for e in old if e["ip"] == ip]
    out.append({"ip": ip, "from": min([e["from"] for e in same] + [at_ms]), "to": at_ms})
    return sorted(out, key=lambda e: -e["to"])[:IP_HISTORY_MAX]


def read_device(device: str):
    """A device's current file, cleaned; None if there is none or it is broken.
    File hiện có của một máy, đã làm sạch; None nếu chưa có hoặc hỏng."""
    r = data_db().rows("SELECT body FROM devices WHERE device = ?", (device,))
    try:
        return clean_payload(json.loads(r[0][0]), time.time()) if r else None
    except (ValueError, RecursionError):
        return None


def save_ingest(d: dict, now: float) -> None:
    """Save one send: the IP history comes from the device's previous file, never from the device.
    Ghi một lần máy gửi: lịch sử IP lấy từ file cũ của máy, không lấy từ máy gửi."""
    old = read_device(d["device"]) or {}
    ip = d.get("lanIp") or d.get("ip")
    d["ipHistory"] = add_ip_history(old.get("ipHistory", []), ip, int(now * 1000)) if ip else old.get("ipHistory", [])
    save_device(d)


def save_device(d: dict) -> None:
    """One row per device; seen_at is the server's time of the send, used by the 30-day limit.
    Mỗi máy một dòng; seen_at là giờ máy chủ nhận, dùng cho hạn 30 ngày."""
    with data_db().tx() as c:
        c.execute("INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?, ?)", device_row(d, int(time.time())))


class IngestGate:
    """Gatekeeper of /ingest: each device can only send for the person who sent first, and the number of sends is limited.
    INGEST_KEY is in every staff member's install package, so it is not enough to tell who is who.
    Gác cổng /ingest: mỗi máy chỉ gửi được cho đúng người đã gửi lần đầu, và giới hạn số lần gửi.
    INGEST_KEY nằm trong gói cài của mọi nhân viên nên không đủ để biết ai là ai."""

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()
        # ip -> [times of sending in the last 10 minutes]
        # ip -> [các lần gửi trong 10 phút]
        self.ingest_times = {}
        # ip -> [times a new device was created in the last day]
        # ip -> [các lần tạo máy mới trong 1 ngày]
        self.new_devices = {}
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
            attempts = [t for t in self.ingest_times.get(ip, []) if now - t < 600]
            if len(attempts) >= INGEST_PER_IP:
                self.ingest_times[ip] = attempts
                return 429, "too many submissions"
            attempts.append(now)
            self.ingest_times[ip] = attempts
            if len(self.ingest_times) > 2000:
                self.ingest_times = {k: v for k, v in self.ingest_times.items() if v and now - v[-1] < 600}
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
    """Every device that sent in the last KEEP_DAYS days, cleaned; older rows are deleted.
    Mọi máy đã gửi trong KEEP_DAYS ngày gần nhất, đã làm sạch; dòng cũ hơn bị xoá."""
    out, cutoff = [], time.time() - KEEP_DAYS * 86400
    db = data_db()
    if db.rows("SELECT 1 FROM devices WHERE seen_at < ? LIMIT 1", (cutoff,)):
        with db.tx() as c:
            c.execute("DELETE FROM devices WHERE seen_at < ?", (cutoff,))
    for (body,) in db.rows("SELECT body FROM devices"):
        try:
            device = clean_payload(json.loads(body), time.time())
        except (ValueError, RecursionError):
            continue
        if device:
            out.append(device)
    return out


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


def group_by_person(devices: list, now: float) -> list:
    """Merge device files into one row per person: same account + same name (sharing an account still keeps people apart).
    Gộp file các máy thành mỗi người một dòng: cùng tài khoản + cùng tên (dùng chung tài khoản vẫn tách người)."""
    today = datetime.fromtimestamp(now, LOCAL_TZ).date()
    since_7_days = today - timedelta(days=6)
    people = {}
    for m in devices:
        if not isinstance(m, dict) or m.get("v") != 1 or not isinstance(m.get("updatedAt"), (int, float)):
            continue
        ip, lan_ip = str(m.get("ip") or ""), str(m.get("lanIp") or "")
        name, group_key = person_name(m), person_key(m)
        r = people.setdefault(group_key, {"key": group_key, "name": name, "account": str(m.get("account") or ""), "deviceCount": 0, "lanIps": [], "ip": [],
                                    "enteredAccounts": [], "delegating": [0, 0, 0], "subagents": {}, "costByHour": {}, "tasksByHour": {}, "models": {},
                                    "gemma": [], "chatgpt": 0, "gemini": 0, "known": 0, "chatgptModels": [], "geminiModels": [], "updatedAt": 0, "openSessions": 0, "working": 0, "waiting": 0,
                                    "usdToday": 0.0, "tokensIn": 0, "tokensOut": 0, "usd7d": 0.0, "tasks": [0, 0, 0], "quota": None, "pluginVersion": [], "devices": [],
                                    "latestIp": "", "latestIpAt": 0, "online": False, "tools": {}})
        connector = from_connector(m)
        # the connector is not a plugin install: it is not counted as a computer and has no plugin version to show
        # bộ nối không phải một bản cài plugin: không tính là một máy và không có phiên bản plugin để hiện
        if not connector:
            r["deviceCount"] += 1
        # where this person sent from most recently: so an old computer at the office does not keep a person who is travelling
        # nơi người này gửi gần nhất: để máy cũ ở văn phòng không giữ người đang đi công tác
        if ip and m["updatedAt"] >= r["latestIpAt"]:
            r["latestIp"], r["latestIpAt"] = ip, m["updatedAt"]
        for k, v in (("lanIps", lan_ip), ("ip", ip)):
            if v and v not in r[k]:
                r[k].append(v)
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
                    if isinstance(agent_name, str) and re.fullmatch(r"[A-Za-z0-9:_.-]{1,40}", agent_name) and isinstance(agent_count, int) and 0 < agent_count <= 50:
                        r["subagents"][agent_name] = r["subagents"].get(agent_name, 0) + agent_count
            delegating = m.get("delegating") or {}
            if isinstance(delegating, dict):
                for i, tool in enumerate(("gemini", "chatgpt", "gemma")):
                    r["delegating"][i] += int(delegating.get(tool) or 0)
        for hour, v in (m.get("ledger") or {}).items():
            try:
                day = datetime.fromtimestamp(int(hour) * 3600, LOCAL_TZ).date()
            except (ValueError, OverflowError):
                continue
            if day >= since_7_days:
                r["usd7d"] += float(v.get("usd") or 0)
            # last 24 hours, for the chart on the dashboard
            # 24 giờ gần nhất, cho biểu đồ của bảng điều khiển
            if int(hour) * 3600 > now - 24 * 3600:
                r["costByHour"][int(hour)] = r["costByHour"].get(int(hour), 0.0) + float(v.get("usd") or 0)
            if day == today:
                r["usdToday"] += float(v.get("usd") or 0)
                r["tokensIn"] += int(v.get("input") or 0) + int(v.get("cacheRead") or 0) + int(v.get("cacheWrite") or 0)
                r["tokensOut"] += int(v.get("output") or 0)
        for hour, v in (m.get("tasks") or {}).items():
            try:
                if int(hour) * 3600 > now - 24 * 3600:
                    hour_counts = r["tasksByHour"].setdefault(int(hour), [0, 0, 0])
                    for i, tool in enumerate(("gemini", "chatgpt", "gemma")):
                        hour_counts[i] += int(v.get(tool) or 0)
            except (ValueError, TypeError, AttributeError):
                pass
            try:
                if datetime.fromtimestamp(int(hour) * 3600, LOCAL_TZ).date() != today:
                    continue
            except (ValueError, OverflowError):
                continue
            for i, tool in enumerate(("gemini", "chatgpt", "gemma")):
                r["tasks"][i] += int(v.get(tool) or 0)
    out = sorted(people.values(), key=lambda r: r["name"].lower())
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
