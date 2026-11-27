#!/usr/bin/env python3
"""The guard for a faster way of writing the receiver's batches (RECEIVER_FAST_APPLY): the same seeded run of batches goes through
receiver.apply_rows twice, each time in a process of its own on its own copy of one temporary data folder, once with RECEIVER_FAST_APPLY=0
and once with 1, and the two must leave the same tables, the same /data for every role byte for byte, the same views before and after
DEVICES.forget() and the same answers. device_days must also equal a count of device_hours. Standard library only:
python3 -m unittest test_apply_paths.
  Chốt chặn cho cách ghi nhanh hơn các lô của bộ nhận (RECEIVER_FAST_APPLY): cùng một chuỗi lô có hạt giống chạy qua receiver.apply_rows
  hai lần, mỗi lần trong một tiến trình riêng trên bản sao riêng của cùng một thư mục dữ liệu tạm, một lần với RECEIVER_FAST_APPLY=0 và một
  lần với 1, và hai lần phải để lại cùng các bảng, cùng /data của mọi vai từng byte, cùng khung nhìn trước và sau DEVICES.forget() và cùng
  câu trả lời. device_days cũng phải bằng tổng đếm lại từ device_hours. Chỉ thư viện chuẩn: python3 -m unittest test_apply_paths.

The run holds every kind of row the receiver sends: hours, full, v1, an empty hour, a computer's clock going back, midnight, more hours
than a book keeps, a row that fails in the middle of a batch, rows that are not rows, a batch sent again, a computer never enrolled,
one computer twice in one batch. Time is a fixed clock moved by the run, so both processes see the same seconds.
  Chuỗi có mọi loại dòng bộ nhận gửi: hours, full, v1, giờ rỗng, đồng hồ của máy lùi, qua nửa đêm, nhiều giờ hơn sổ giữ, một dòng hỏng
  giữa lô, những thứ không phải dòng, một lô gửi lại, một máy chưa từng ghi danh, một máy hai lần trong một lô. Thời gian là một đồng hồ
  cố định do chuỗi đẩy đi, nên hai tiến trình thấy cùng các giây.
"""
import calendar
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 21:00 UTC with TZ_OFFSET=0, so the run passes midnight
# 21:00 UTC với TZ_OFFSET=0, để chuỗi đi qua nửa đêm
BASE = calendar.timegm((2026, 11, 20, 21, 0, 0))
SEEDS = (1, 2)
PACKS = 70
KNOWN = ["device-apply%02d" % i for i in range(10)]
LATE = "device-applylate"
NONAME = "device-applynoname"
STRANGER = "device-applystranger"
# the money of a ledger hour whose write fails on purpose: the row is taken back alone and named in "bad"
# số tiền của một giờ trong sổ mà lần ghi cố ý hỏng: dòng đó bị rút lại một mình và có tên trong "bad"
FAIL_MICRO = 13131313
# MAX_HOURS_PER_DEVICE in board/settings.py
# MAX_HOURS_PER_DEVICE trong board/settings.py
MAX_HOURS = 8 * 24 + 48
TABLES = ("devices", "device_hours", "device_days", "history", "identities", "device_keys", "delegations_seen")


# ---- the child: one run of the batches in a process of its own ----
# ---- tiến trình con: một lần chạy chuỗi lô trong tiến trình riêng ----

def _child(mode: str, data_dir: str, keys_dir: str, seed: int, out_path: str) -> None:
    """Run in a process of its own: "init" makes the data and keys folders both runs start from; "run" applies the seeded batches and
    writes what the parent compares to out_path. APPLY_TEST_BREAK names a fault put in on purpose, to show the comparison sees it.
    Chạy trong tiến trình riêng: "init" tạo thư mục dữ liệu và khoá mà cả hai lần chạy bắt đầu từ đó; "run" áp chuỗi lô có hạt giống và
    ghi ra out_path những gì tiến trình cha so. APPLY_TEST_BREAK nêu một lỗi cài cố ý, để thấy phép so bắt được nó."""
    import time
    clock = [float(BASE)]
    # every clock the server reads is this one, moved only by the run
    # mọi đồng hồ máy chủ đọc đều là đồng hồ này, chỉ chuỗi đẩy nó đi
    time.time = lambda: clock[0]
    os.environ.update(DATA_DIR=data_dir, KEYS_DIR=keys_dir, TZ_OFFSET="0", RECEIVER="1", INGEST_KEY="test-apply-key",
                      RELEASES_DIR=os.path.join(data_dir, "releases"), BRANCHES_FILE=os.path.join(data_dir, "no-branches.json"),
                      RECEIVER_CHECK_PERCENT="0", VIEW_CACHE_SECONDS="0")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(keys_dir, exist_ok=True)
    sys.path.insert(0, HERE)
    random.seed(seed)
    from board import db, devices, devicestore, receiver, security, views
    from board.devicekeys import DEVICE_KEYS
    from board.settings import MAX_HOURS_PER_DEVICE
    assert MAX_HOURS_PER_DEVICE == MAX_HOURS, "MAX_HOURS here must follow board/settings.py"

    if mode == "init":
        gate = views.INGEST_GATE
        for i, d in enumerate(KNOWN + [LATE]):
            # two computers of one person
            # hai máy của cùng một người
            n = i // 2 if i < 4 else i
            gate.identities[d] = ["p%d@example.com" % n, "person %d" % n]
            if i == 5:
                # a name the server keeps that cleaning still cuts: a control character, longer than a name may be
                # một cái tên máy chủ giữ mà bước làm sạch vẫn cắt: có ký tự điều khiển, dài hơn mức một cái tên được phép
                gate.identities[d] = ["p%d@example.com" % n, "person\x07 " + "x" * 130]
            gate._save(d)
        gate.identities[NONAME] = ["noname@example.com", ""]
        gate._save(NONAME)
        DEVICE_KEYS.alias("make the secrets now")
        receiver.write_secrets(clock[0])
        return

    _break(os.environ.get("APPLY_TEST_BREAK", ""), devicestore, devices, receiver)
    # _clean_again must give what clean_payload gives, field for field and in the same order: each time it is used, both are compared
    # _clean_again phải cho đúng thứ clean_payload cho, từng trường và cùng thứ tự: mỗi lần nó được dùng, hai cách được so với nhau
    cleaned_apart, cleaned_again = [], [0]
    real_again = devices._clean_again

    def _clean_again(d, now):
        mine = real_again(d, now)
        cleaned_again[0] += 1
        full = devices.clean_payload(d, now)
        for kind in devices.HOUR_KINDS:
            (full or {}).pop(kind, None)
        if json.dumps(mine) != json.dumps(full):
            cleaned_apart.append([d.get("device"), json.dumps(mine)[:300], json.dumps(full)[:300]])
        return mine
    devices._clean_again = _clean_again
    real_put = devicestore.put_hours

    def put_hours(c, rows):
        if any(str(FAIL_MICRO) in r[3] for r in rows):
            raise RuntimeError("the disk said no")
        return real_put(c, rows)
    devicestore.put_hours = put_hours

    rng = random.Random(seed)
    tool = sorted(devices.DELEGATION_TOOLS)[0]
    skew = {}
    answers = []
    last = None
    boot, seq = "boot-1", 0
    for step in range(PACKS):
        # mostly a few seconds apart, as a beat of the receiver, so devices rows are held back (DeviceCache.late); now and then minutes
        # phần lớn cách nhau vài giây, như một nhịp của bộ nhận, để có dòng devices được để sau (DeviceCache.late); thỉnh thoảng vài phút
        clock[0] += rng.randint(1, 20) if step % 3 else rng.randint(5, 1800)
        if step == PACKS // 2:
            # the receiver started again: a new boot, its numbers from 1 again
            # bộ nhận khởi động lại: boot mới, số lại từ 1
            boot, seq = "boot-2", 0
        if last is not None and step % 11 == 5:
            # the same batch sent again, its values changed: answered, never written
            # cùng lô gửi lại, giá trị đã đổi: được trả lời, không ghi
            again = json.loads(json.dumps(last))
            for row in again["rows"]:
                if isinstance(row, dict) and isinstance(row.get("v"), dict):
                    row["v"]["openSessions"] = 99
            answers.append(receiver.apply_rows(again, clock[0]))
        for d in KNOWN + [NONAME]:
            r = rng.random()
            if r < 0.04:
                # the computer's clock goes back hours or days
                # đồng hồ của máy lùi vài giờ hay vài ngày
                skew[d] = -rng.choice([2, 5, 30, 60]) * 3600 * 1000
            elif r < 0.08:
                skew[d] = 0
            elif r < 0.09:
                skew[d] = 3 * 3600 * 1000
        rows = []
        for _ in range(rng.randint(1, 8)):
            rows.append(_row(rng, clock[0], skew, tool, step))
        if rng.random() < 0.3:
            # one computer twice in one batch, the second row newer
            # một máy hai lần trong một lô, dòng sau mới hơn
            first = next((r for r in rows if isinstance(r, dict) and r.get("kind") in ("hours", "full", "v1")
                          and r.get("k") in [["m", d] for d in KNOWN]), None)
            if first:
                rows.append(_hours_row(rng, first["k"][1], clock[0] + 1, skew.get(first["k"][1], 0)))
        if step == 2:
            # a computer known but with no book yet sends only hours: the answer asks for the whole book
            # máy đã biết mà chưa có sổ chỉ gửi các giờ: câu trả lời xin cả sổ
            rows.append(_hours_row(rng, LATE, clock[0], 0))
        if step == 3:
            # not a batch: no answer
            # không phải một lô: không có câu trả lời
            answers.append(receiver.apply_rows({"src": "go-test", "boot": boot, "rows": rows}, clock[0]))
        if step == 12:
            # a book exactly full, then a new hour: the oldest hour leaves the book and its day
            # một sổ đầy đúng mức, rồi một giờ mới: giờ cũ nhất rời sổ và rời ngày của nó
            rows.append(_full_row(rng, KNOWN[3], clock[0], 0, "max"))
        if step == 13:
            row = _hours_row(rng, KNOWN[3], clock[0] + 3600, 0)
            row["v"]["hours"] = {"ledger": {str(int(clock[0] + 3600) // 3600): {"usdMicro": 7, "input": 1}}}
            rows.append(row)
        if step == 9:
            rows.append(_full_row(rng, LATE, clock[0], 0, 30))
        seq += 1
        batch = {"src": "go-test", "boot": boot, "seq": seq, "rows": rows}
        last = batch
        answers.append(receiver.apply_rows(json.loads(json.dumps(batch)), clock[0]))
        # history_loop between two batches: with RECEIVER_FAST_APPLY the batches leave the history to it, so both ways must give
        # the same history from here
        # history_loop giữa hai lô: với RECEIVER_FAST_APPLY các lô để lịch sử cho nó, nên từ đây hai đường phải cho cùng lịch sử
        views.record_history()
    clock[0] += 30
    now = clock[0]

    # the devices rows held back (RECEIVER_FAST_APPLY) are written, as state_loop does every 30 seconds
    # các dòng devices đang để sau (RECEIVER_FAST_APPLY) được ghi, như state_loop làm mỗi 30 giây
    late_written = devices.DEVICES.write_late()
    database = db.data_db()

    def tables():
        out = {}
        with database.lock:
            c = database.conn
            have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for t in TABLES:
                if t in have:
                    rows = [list(r) for r in c.execute("SELECT * FROM %s" % t)]
                    if t == "devices":
                        # what a devices row says once read again, without when it was written: with RECEIVER_FAST_APPLY a row whose state
                        # only changed is written up to a minute later (DeviceCache.late), and from the cache instead of the send
                        # những gì một dòng devices nói khi đọc lại, bỏ lúc nó được ghi: với RECEIVER_FAST_APPLY một dòng chỉ đổi trạng thái
                        # được ghi muộn tới một phút (DeviceCache.late), và từ bộ nhớ đệm thay vì từ lần gửi
                        rows = [[r[0], devices.clean_text(r[1], 120), devices.clean_text(r[2], 120),
                                 json.dumps(devices._steady(devices._clean_state(r[-1], now) or {}), sort_keys=True)] for r in rows]
                    # history without its id: rows of one second come in the order of a set of people, which is not fixed
                    # history bỏ id: các dòng cùng một giây theo thứ tự của một tập người, vốn không cố định
                    out[t] = sorted((r[1:] if t == "history" else r for r in rows), key=repr)
            # the audit log without its own time and chain, which come from the wall clock
            # nhật ký kiểm toán bỏ thời điểm và chuỗi băm của nó, vốn lấy từ đồng hồ thật
            out["audit"] = []
            for action, body in c.execute("SELECT action, body FROM audit ORDER BY id"):
                b = json.loads(body)
                out["audit"].append([action, {k: v for k, v in b.items() if k not in ("at", "prev", "hash")}])
        return out

    def view():
        out = {role: json.dumps(views.role_view(role, now), ensure_ascii=False) for role in (security.ADMIN, security.VIEWER, security.WALL)}
        out["books"] = json.dumps({d: devices.read_device(d) for d in KNOWN + [LATE, NONAME, STRANGER]}, sort_keys=True)
        return out

    result = {"answers": answers, "tables": tables(), "before": view()}
    devices.DEVICES.forget()
    result["after"] = view()
    result["daysWrong"] = days_wrong(database, devices, devicestore)
    result["cleanedApart"] = cleaned_apart
    result["cleanedAgain"] = cleaned_again[0]
    result["lateWritten"] = late_written
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


def days_wrong(database, devices, devicestore) -> list:
    """The computers whose device_days differ from a count of their device_hours, with both.
    Các máy có device_days khác với tổng đếm lại từ device_hours của chúng, kèm cả hai."""
    wrong = []
    with database.lock:
        c = database.conn
        ids = sorted({r[0] for r in c.execute("SELECT device FROM device_hours UNION SELECT device FROM device_days")})
        for d in ids:
            kept = sorted(list(r) for r in devicestore.days(c, d))
            counted = devices._add_up(devices._rows_to_book(devicestore.hours(c, d, ("ledger", "tasks"))))["days"]
            counted = sorted(list(devices._day_row(d, day, v)) for day, v in counted.items())
            if kept != counted:
                wrong.append([d, kept, counted])
    return wrong


def _state(rng, device: str, updated: int) -> dict:
    return {"device": device, "updatedAt": updated, "openSessions": rng.randint(0, 3), "working": rng.randint(0, 2),
            "waiting": rng.randint(0, 1), "models": {"claude-opus-5-5": rng.randint(0, 3)}, "pluginVersion": "0.50.0",
            # a computer mostly keeps its address, and now and then moves
            # một máy phần lớn giữ địa chỉ của nó, thỉnh thoảng mới đổi
            "lanIp": "10.0.0.%d" % (sum(map(ord, device)) % 200) if rng.random() < 0.85 else rng.choice(["10.0.0.5", "10.0.0.6", "10.0.1.7"]), "name": rng.choice(["", "Someone Else"]),
            "quota": {"readAt": updated, "windows": [{"kind": "five_hour", "pct": rng.randint(0, 99), "resetsAt": updated + 3600000}]}}


def _tables(rng, hours: list, empty: float) -> dict:
    out = {"ledger": {}, "tasks": {}, "blocks": {}}
    for h in hours:
        out["ledger"][str(h)] = {} if rng.random() < empty else {"usdMicro": rng.randint(0, 900000), "input": rng.randint(0, 50000),
                                                                 "output": rng.randint(0, 9000), "cacheRead": rng.randint(0, 5), "cacheWrite": 0}
        if rng.random() < 0.3:
            out["tasks"][str(h)] = {} if rng.random() < empty else {"gemini": rng.randint(0, 3), "chatgpt": rng.randint(0, 3), "gemma": rng.randint(0, 2)}
        if rng.random() < 0.15:
            out["blocks"][str(h)] = {} if rng.random() < empty else {rng.choice(["secret", "commit", "risky", "page", "answer"]): rng.randint(1, 3)}
    return out


def _hours_row(rng, device: str, at: float, skew: int) -> dict:
    updated = int(at * 1000) + skew
    top = updated // 3_600_000
    hours = sorted({top + rng.randint(-30, 1) for _ in range(rng.randint(1, 4))})
    if rng.random() < 0.05:
        # an hour older than the book keeps
        # một giờ cũ hơn sổ giữ
        hours.append(top - rng.randint(235, 260))
    v = dict(_state(rng, device, updated), v=2, full=False, hours=_tables(rng, hours, 0.2))
    return {"k": ["m", device], "at": int(at * 1000), "kind": "hours", "ip": "203.0.113.9" if rng.random() < 0.85 else rng.choice(["198.51.100.4", "198.51.100.7\x1f"]), "v": v}


def _full_row(rng, device: str, at: float, skew: int, n: int) -> dict:
    updated = int(at * 1000) + skew
    top = updated // 3_600_000
    # "max": a book exactly as full as it may be, so the next new hour pushes the oldest out
    # "max": một sổ đầy đúng mức cho phép, để giờ mới kế tiếp đẩy giờ cũ nhất ra
    hours = list(range(top - MAX_HOURS + 1, top + 1)) if n == "max" else sorted(rng.sample(range(top - 300, top + 1), n))
    v = dict(_state(rng, device, updated), v=2, full=True, hours=_tables(rng, hours, 0 if n == "max" else 0.1))
    return {"k": ["m", device], "at": int(at * 1000), "kind": "full", "ip": "203.0.113.9", "v": v}


def _row(rng, at: float, skew: dict, tool: str, step: int):
    """One row of a batch, of a kind drawn at random.
    Một dòng của lô, loại rút ngẫu nhiên."""
    device = rng.choice(KNOWN + [NONAME])
    s = skew.get(device, 0)
    r = rng.random()
    if r < 0.45:
        return _hours_row(rng, device, at, s)
    if r < 0.58:
        # a whole book: none, a few hours, or more than a book keeps
        # cả sổ: không giờ nào, vài giờ, hay nhiều hơn sổ giữ
        return _full_row(rng, device, at, s, rng.choice([0, 3, 20, 260, "max"]))
    if r < 0.68:
        updated = int(at * 1000) + s
        top = updated // 3_600_000
        book = _tables(rng, sorted({top - rng.randint(0, 40) for _ in range(rng.randint(0, 6))}), 0)
        v = dict(_state(rng, device, updated), v=1, ledger=book["ledger"], tasks=book["tasks"], blocks=book["blocks"])
        return {"k": ["m", device], "at": int(at * 1000), "kind": "v1", "ip": "198.51.100.4", "v": v}
    if r < 0.74:
        row = _hours_row(rng, device, at, s)
        row["kind"] = "delegations"
        row["v"]["delegations"] = [{"id": "%024x" % rng.getrandbits(96), "tool": tool, "at": int(at * 1000) - 1000, "outcome": "ok",
                                    "promptChars": rng.randint(1, 900)}]
        return row
    if r < 0.79:
        # a row that is not a row
        # thứ không phải một dòng
        other = _hours_row(rng, device, at, s)
        return rng.choice([42, "text", {"k": ["m", device], "kind": "hours"}, dict(other, k=["m", KNOWN[0] if device != KNOWN[0] else KNOWN[1]]),
                           dict(other, kind="weird"), dict(other, k=["x"]), dict(other, v="text")])
    if r < 0.83:
        return _hours_row(rng, STRANGER, at, 0)
    if r < 0.87:
        # a row whose write fails in the middle of the batch
        # một dòng mà lần ghi hỏng giữa lô
        row = _hours_row(rng, device, at, s)
        hour = next(iter(row["v"]["hours"]["ledger"]))
        row["v"]["hours"]["ledger"][hour] = {"usdMicro": FAIL_MICRO}
        return row
    # a send with nothing but its state, at the computer's clock
    # lần gửi chỉ có trạng thái, theo đồng hồ của máy
    row = _hours_row(rng, device, at, s)
    row["v"]["hours"] = {}
    return row


def _break(name: str, devicestore, devices, receiver) -> None:
    """Faults put in on purpose, so the test shows it would catch them (see BREAKS). Each names the shared step it breaks: when a new way
    of writing stops going through that step, move the fault to the step it does go through.
    Các lỗi cài cố ý, để test cho thấy nó bắt được chúng (xem BREAKS). Mỗi lỗi nêu bước dùng chung mà nó làm hỏng: khi cách ghi mới
    không còn đi qua bước đó, chuyển lỗi sang bước nó đi qua."""
    if not name:
        return
    if name == "day-off-by-one":
        put = devicestore.put_days
        devicestore.put_days = lambda c, rows: put(c, [(r[0], r[1], r[2] + 1) + tuple(r[3:]) for r in rows])
    elif name == "hour-not-dropped":
        devicestore.drop_hours = lambda c, keys: None
    elif name == "state-not-written":
        put = devicestore.put_state
        devicestore.put_state = lambda c, device, account, name_, seen_at, body: None if seen_at % 3 == 0 else put(c, device, account, name_, seen_at, body)
    elif name == "memory-day-lost":
        real = devices.DeviceCache._set

        def _set(self, device, seen_at, state, summary):
            if summary and summary.get("days"):
                summary = dict(summary, days={k: v for k, v in summary["days"].items() if k != max(summary["days"])})
            return real(self, device, seen_at, state, summary)
        devices.DeviceCache._set = _set
    elif name == "difference-off-by-one":
        # the days by difference (RECEIVER_FAST_APPLY) come out one usdMicro more
        # các ngày tính bằng hiệu số (RECEIVER_FAST_APPLY) ra dư một usdMicro
        real = devices._days_by_difference

        def _days_by_difference(days, touched, changed):
            out = real(days, touched, changed)
            return {day: devices._day_numbers([v["usdMicro"] + 1] + [v[k] for k in devices._DAY_FIELDS[1:]]) for day, v in out.items()} if out else out
        devices._days_by_difference = _days_by_difference
    elif name == "held-hour-lost":
        # the writes held for a batch (RECEIVER_FAST_APPLY) lose the last hour each time they are written
        # các lệnh ghi được giữ cho một lô (RECEIVER_FAST_APPLY) mất giờ cuối cùng mỗi lần được ghi
        real = devicestore.Held.write

        def write(self):
            self.rows["hours"] = self.rows["hours"][:-1]
            return real(self)
        devicestore.Held.write = write
    elif name == "cache-not-put-back":
        # a batch taken back whole (RECEIVER_FAST_APPLY) leaves in the cache what it had written
        # lô bị rút lại cả (RECEIVER_FAST_APPLY) để lại trong bộ nhớ đệm những gì nó đã ghi
        devices.DeviceCache._put_back = lambda self, kept: None
    elif name == "clean-again-skips-name":
        # cleaning only what was set after cleaning (RECEIVER_FAST_APPLY) leaves the name as the server keeps it
        # làm sạch lại chỉ những gì được đặt sau khi làm sạch (RECEIVER_FAST_APPLY) để nguyên cái tên như máy chủ giữ
        real = devices._clean_again

        def _clean_again(d, now):
            out = real(d, now)
            if out is not None and d.get("name"):
                out["name"] = d["name"]
            return out
        devices._clean_again = _clean_again
    elif name == "late-not-written":
        # the devices rows held back (RECEIVER_FAST_APPLY) are never written
        # các dòng devices đang để sau (RECEIVER_FAST_APPLY) không bao giờ được ghi
        devices.DeviceCache.write_late = lambda self: 0
    elif name == "answer-loses-need-full":
        real = receiver.apply_rows

        def apply_rows(batch, now):
            answer = real(batch, now)
            return dict(answer, needFull=[]) if answer else answer
        receiver.apply_rows = apply_rows
    elif name == "rows-reversed":
        real = receiver.apply_rows

        def apply_rows(batch, now):
            if isinstance(batch, dict) and isinstance(batch.get("rows"), list):
                batch = dict(batch, rows=batch["rows"][::-1])
            return real(batch, now)
        receiver.apply_rows = apply_rows
    else:
        raise SystemExit("no such fault: " + name)


# ---- the parent: unittest ----
# ---- tiến trình cha: unittest ----

def _run_child(mode: str, data_dir: str, keys_dir: str, seed: int, out_path: str, **env) -> None:
    full = dict(os.environ, **env)
    p = subprocess.run([sys.executable, os.path.abspath(__file__), mode, data_dir, keys_dir, str(seed), out_path], cwd=HERE, env=full,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if p.returncode != 0:
        raise AssertionError("the %s run failed:\n%s" % (mode, p.stderr.decode(errors="replace")[-4000:]))


def run_twice(seed: int, fast_env: dict) -> tuple:
    """The seeded run on two copies of one start: first the old way (RECEIVER_FAST_APPLY=0), then with fast_env. Returns both results.
    Chuỗi có hạt giống trên hai bản sao của cùng một điểm đầu: trước theo đường cũ (RECEIVER_FAST_APPLY=0), sau với fast_env.
    Trả về cả hai kết quả."""
    tmp = tempfile.mkdtemp(prefix="test-apply-paths-")
    try:
        start = os.path.join(tmp, "start")
        _run_child("init", os.path.join(start, "data"), os.path.join(start, "keys"), seed, "")
        out = []
        for name, env in (("old", {"RECEIVER_FAST_APPLY": "0", "APPLY_TEST_BREAK": ""}), ("new", dict({"RECEIVER_FAST_APPLY": "1"}, **fast_env))):
            shutil.copytree(start, os.path.join(tmp, name))
            path = os.path.join(tmp, name + ".json")
            _run_child("run", os.path.join(tmp, name, "data"), os.path.join(tmp, name, "keys"), seed, path, **env)
            with open(path, encoding="utf-8") as f:
                out.append(json.load(f))
        return tuple(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def differences(old: dict, new: dict) -> dict:
    """What differs, by part: a table, the /data of a role or the books, before or after forget(), the answers, the count of the days.
    Also what differs inside one run: its view before and after forget(). Each value is a short line saying where.
    Những gì khác nhau, theo từng phần: một bảng, /data của một vai hay các sổ, trước hay sau forget(), câu trả lời, phép đếm lại ngày.
    Cả những gì khác trong cùng một lần chạy: khung nhìn trước và sau forget(). Mỗi giá trị là một dòng ngắn nói chỗ khác."""
    out = {}
    for t in sorted(set(old["tables"]) | set(new["tables"])):
        a, b = old["tables"].get(t), new["tables"].get(t)
        if a != b:
            extra = [r for r in (b or []) if r not in (a or [])][:2]
            gone = [r for r in (a or []) if r not in (b or [])][:2]
            out["table " + t] = "only new %s, only old %s" % (extra, gone)
    for when in ("before", "after"):
        for part in sorted(old[when]):
            if old[when][part] != new[when].get(part):
                a, b = old[when][part], new[when].get(part) or ""
                i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                out["%s %s" % (when, part)] = "from byte %d: old ...%s... new ...%s..." % (i, a[max(0, i - 60):i + 60], b[max(0, i - 60):i + 60])
    for name, r in (("old", old), ("new", new)):
        for part in sorted(r["before"]):
            if same_order_free(r["before"][part]) != same_order_free(r["after"].get(part)):
                out["%s forget %s" % (name, part)] = "the view changed once read again from the tables"
        if r["daysWrong"]:
            out[name + " days"] = "device_days differ from device_hours: %s" % r["daysWrong"][:2]
        if r.get("cleanedApart"):
            out[name + " cleaning"] = "_clean_again differs from clean_payload: %s" % r["cleanedApart"][:2]
    if old["answers"] != new["answers"]:
        i = next(i for i, (x, y) in enumerate(zip(old["answers"] + [None], new["answers"] + [None])) if x != y)
        out["answers"] = "batch %d: old %s new %s" % (i, (old["answers"] + [None])[i], (new["answers"] + [None])[i])
    return out


def same_order_free(text):
    """A /data or the books with the lists of text in each person's row sorted: those lists (lanIps, ip, ...) follow the order the
    computers sit in memory, the order of their last write, which becomes the order of the table once read again. Only for the
    comparison before and after forget(); the old way and the new way are compared byte for byte.
    Một /data hay các sổ với các danh sách chữ trong dòng của mỗi người đã được sắp: các danh sách đó (lanIps, ip, ...) theo thứ tự
    các máy nằm trong bộ nhớ, tức thứ tự lần ghi gần nhất, và thành thứ tự của bảng khi đọc lại. Chỉ cho phép so trước và sau
    forget(); đường cũ và đường mới được so từng byte."""
    d = json.loads(text) if text else None
    for p in d.get("people", []) if isinstance(d, dict) else []:
        for k, v in p.items():
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                p[k] = sorted(v)
    return d


# each fault put in on purpose, and a part the comparison must name for it
# mỗi lỗi cài cố ý, và một phần mà phép so phải nêu cho nó
BREAKS = {
    "day-off-by-one": "table device_days",
    "difference-off-by-one": "table device_days",
    "held-hour-lost": "table device_hours",
    "clean-again-skips-name": "new cleaning",
    "late-not-written": "table devices",
    "cache-not-put-back": "before admin",
    "hour-not-dropped": "table device_hours",
    "state-not-written": "table devices",
    "memory-day-lost": "new forget admin",
    "answer-loses-need-full": "answers",
    "rows-reversed": "table device_hours",
}


class SameTablesBothWays(unittest.TestCase):
    def test_both_ways_leave_the_same_tables_views_and_answers(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                old, new = run_twice(seed, {})
                self.assertEqual(differences(old, new), {})
                # the run did reach what it is for
                # chuỗi thật sự chạm tới những gì nó cần
                answers = old["answers"]
                for part in ("needFull", "unknown", "incomplete", "bad"):
                    self.assertTrue(any(a and a.get(part) for a in answers), part)
                self.assertTrue(old["tables"]["device_days"] and old["tables"]["device_hours"] and old["tables"]["audit"])
                days = {r[0] for r in old["tables"]["device_days"]}
                self.assertTrue({"2026-11-20", "2026-11-21"} <= days, days)
                # the new way did clean only what was set after cleaning, and the old way never did
                # đường mới thật sự chỉ làm sạch lại những gì được đặt sau khi làm sạch, còn đường cũ thì không bao giờ
                self.assertGreater(new["cleanedAgain"], 100)
                self.assertEqual(old["cleanedAgain"], 0)
                # rows held back were written at the end, and the old way held none
                # có những dòng để sau được ghi ở cuối, còn đường cũ không để sau dòng nào
                self.assertGreater(new["lateWritten"], 0)
                self.assertEqual(old["lateWritten"], 0)

    def test_the_comparison_catches_faults_put_in_on_purpose(self):
        for name, part in sorted(BREAKS.items()):
            with self.subTest(fault=name):
                old, new = run_twice(SEEDS[0], {"APPLY_TEST_BREAK": name})
                found = differences(old, new)
                self.assertIn(part, found, "the fault %s was not seen; seen: %s" % (name, sorted(found)))


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] in ("init", "run"):
        _child(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5])
    else:
        unittest.main()
