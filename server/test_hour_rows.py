#!/usr/bin/env python3
"""Tests of schema version 6, standard library only: python3 -m unittest test_hour_rows (run in the server folder).
The hour books moved out of the devices rows into device_hours and device_days: a board.db of schema version 5 must give the same board,
history, totals per day and export after the upgrade, and the rows written send by send must always be the book merge_hours and
replace_hours give on the whole book.
  Test của lược đồ phiên bản 6, chỉ thư viện chuẩn: python3 -m unittest test_hour_rows (chạy trong thư mục server).
  Sổ giờ rời các dòng devices sang device_hours và device_days: một board.db lược đồ phiên bản 5 phải cho cùng bảng, lịch sử, tổng theo
  ngày và bản xuất sau khi nâng, và các dòng ghi qua từng lần gửi phải luôn là đúng sổ mà merge_hours và replace_hours cho trên cả sổ."""
import json
import os
import random
import shutil
import sqlite3
import tempfile
import time
import unittest

# imported first: it points the server at temporary folders before any board module reads its settings
# nhập trước tiên: nó trỏ máy chủ sang thư mục tạm trước khi module board nào đọc cấu hình
import test_webhook as tw  # noqa: F401
import demo
from board import daily, db, devices, devicestore, security, settings, views

AT = time.time()


def report(i: int, rnd: random.Random, at: float, **fields) -> dict:
    """A computer's send of real size: 8 days of hours, tasks, a few blocks, quota.
    Một lần gửi của máy đúng cỡ thật: 8 ngày theo giờ, việc giao, vài lần chặn, hạn mức."""
    hour = int(at // 3600)
    ledger, tasks = demo.sample_hours(rnd, hour, demo.LEDGER_HOURS, demo.busy_of(i))
    out = {"v": 1, "device": "device-six%02d" % i, "name": "Six %d" % (i % 4), "account": "six%d@example.com" % (i % 4), "updatedAt": int(at * 1000),
           "openSessions": 1, "working": i % 2, "waiting": int(i % 3 == 0), "ledger": ledger, "tasks": tasks, "lanIp": "10.6.0.%d" % (i + 1),
           "blocks": {str(hour - 30): {"secret": 1}, str(hour - 2): {"risky": 2}}, "delegating": {"gemini": i % 2},
           "quota": {"readAt": int(at * 1000), "windows": [{"kind": "five_hour", "pct": 10 + i, "resetsAt": int((at + 3600) * 1000)}]}}
    out.update(fields)
    return out


def records(rnd: random.Random) -> list:
    """Cleaned records as schema version 5 stored them: busy computers, one quiet for three days, one whose clock is a day ahead.
    Bản ghi đã làm sạch như lược đồ phiên bản 5 lưu: các máy đang bận, một máy im ba ngày, một máy đồng hồ nhanh một ngày."""
    out = [devices.clean_payload(report(i, rnd, AT), AT) for i in range(8)]
    out.append(devices.clean_payload(report(8, rnd, AT - 3 * 86400), AT))
    out.append(devices.clean_payload(report(9, rnd, AT + 86000), AT))
    return out


def board_of(found: list) -> dict:
    """What a person sees of these records: the admin board, the rows the history records, the totals per day.
    Những gì một người thấy về các bản ghi này: bảng của quản trị, các dòng lịch sử ghi lại, tổng theo ngày."""
    rows = devices.group_by_person(found, AT)
    return {
        "board": views.role_view(security.ADMIN, AT),
        "history": sorted((r["name"], r["account"], views.status_of(r, AT), list(r["delegating"])) for r in rows),
        "days": daily.totals_by_day(found, AT),
    }


class FromSchemaFive(unittest.TestCase):
    """A board.db of schema version 5 upgraded to 6: the same board, history, totals per day and export, a copy kept to go back.
    Một board.db lược đồ phiên bản 5 nâng lên 6: cùng bảng, lịch sử, tổng theo ngày và bản xuất, có bản sao để quay lui."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="test-schema6-")
        self.path = os.path.join(self.folder, db.DATA_DB_NAME)
        self.saved = db._OPEN.get("data")
        os.environ["VIEW_CACHE_SECONDS"] = "0"

    def tearDown(self):
        opened = db._OPEN.get("data")
        if opened is not self.saved:
            opened.conn.close()
        db._OPEN["data"] = self.saved
        devices.DEVICES.forget()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_five(self, kept: list, extra: list = ()) -> None:
        five = db.Database(self.path, db.DATA_STEPS[:5], "NORMAL")
        with five.tx() as c:
            for m in kept:
                c.execute("INSERT INTO devices VALUES (?, ?, ?, ?, ?)", db.device_row(m, int(AT)))
            for row in extra:
                c.execute("INSERT INTO devices VALUES (?, ?, ?, ?, ?)", row)
        five.conn.close()

    def use(self, database) -> None:
        db._OPEN["data"] = database
        devices.DEVICES.forget()

    def test_the_board_and_the_export_are_the_same_after_the_upgrade(self):
        kept = records(random.Random(6))
        broken = ("device-sixbad", "", "", int(AT), "{not json")
        odd = ("device-sixodd", "", "Odd", int(AT), json.dumps({"v": 1, "device": "device-sixodd", "updatedAt": "late", "ledger": {"1": {"usd": 1}}}))
        self.make_five(kept, [broken, odd])
        five = sqlite3.connect(self.path)
        try:
            bodies = dict(five.execute("SELECT device, body FROM devices"))
        finally:
            five.close()
        # before: what the server of schema version 5 showed, each row cleaned as it loaded them
        # trước: thứ máy chủ của lược đồ phiên bản 5 hiện, mỗi dòng làm sạch như lúc nó nạp
        loaded = [m for m in (devices.clean_payload(json.loads(b), AT) for b in bodies.values() if b.startswith("{\"v\"")) if m]
        real = views.read_all_devices
        views.read_all_devices = lambda: loaded
        try:
            before = board_of(loaded)
        finally:
            views.read_all_devices = real
        upgraded = db.Database(self.path, db.DATA_STEPS, "NORMAL")
        self.use(upgraded)
        self.assertEqual(upgraded.rows("PRAGMA user_version"), [(len(db.DATA_STEPS),)])
        found = devices.read_all_devices()
        self.assertEqual(board_of(found), before)
        # the books left the rows, and every record still has its whole book
        # sổ đã rời các dòng, và mọi bản ghi vẫn có đủ sổ của nó
        for m in kept:
            body = json.loads(upgraded.rows("SELECT body FROM devices WHERE device = ?", (m["device"],))[0][0])
            self.assertFalse(set(devices.HOUR_KINDS) & set(body), m["device"])
            self.assertEqual(devices.read_book(m["device"]), devices.book_of(m))
            self.assertEqual(devices.hours_of(devices.DEVICES.get(m["device"]))["days"], devices.add_up_hours(m)["days"])
        self.assertEqual(upgraded.get_meta(devicestore.DAYS_ZONE_KEY), str(devices.zone_seconds()))
        # the rows the board cannot read are left as they were
        # các dòng bảng không đọc được thì để nguyên
        for device, _, _, _, body in (broken, odd):
            self.assertEqual(upgraded.rows("SELECT body FROM devices WHERE device = ?", (device,)), [(body,)])
        # the export gives the old files back: each record with its whole book
        # bản xuất trả lại các file cũ: mỗi bản ghi kèm đủ sổ của nó
        out = os.path.join(self.folder, "export")
        db.export_json(out)
        for device, body in bodies.items():
            with open(os.path.join(out, "data", device + ".json"), encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text if not body.startswith("{\"v\"") else json.loads(text), body if not body.startswith("{\"v\"") else json.loads(body), device)
        # the way back: the copy made before the upgrade, still at schema version 5, with the books in the rows
        # đường lui: bản sao làm trước lần nâng, vẫn ở lược đồ phiên bản 5, sổ vẫn nằm trong các dòng
        back = sqlite3.connect(self.path + db.UPGRADE_BACKUP_SUFFIX % 5)
        try:
            self.assertEqual(back.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(dict(back.execute("SELECT device, body FROM devices")), bodies)
        finally:
            back.close()

    def test_a_new_time_zone_counts_the_days_again(self):
        kept = records(random.Random(7))
        self.make_five(kept)
        upgraded = db.Database(self.path, db.DATA_STEPS, "NORMAL")
        right = upgraded.rows("SELECT * FROM device_days ORDER BY device, day")
        with upgraded.tx() as c:
            devicestore.clear_days(c)
            devicestore.set_days_zone(c, devices.zone_seconds() + 3600)
        self.use(upgraded)
        devices.read_all_devices()
        self.assertEqual(upgraded.rows("SELECT * FROM device_days ORDER BY device, day"), right)
        self.assertEqual(upgraded.get_meta(devicestore.DAYS_ZONE_KEY), str(devices.zone_seconds()))


class RowsAreTheBook(unittest.TestCase):
    """Send after send, in any order of kinds, the rows are exactly the book merge_hours and replace_hours give on the whole book, the days
    in device_days and in memory are its days, and the hours kept in memory are those near the last send.
    Lần gửi nối lần gửi, theo mọi thứ tự loại, các dòng đúng là sổ mà merge_hours và replace_hours cho trên cả sổ, các ngày trong
    device_days và trong bộ nhớ là đúng các ngày của nó, và các giờ giữ trong bộ nhớ là các giờ gần lần gửi cuối."""

    DEVICE = "device-sixrows"

    def tearDown(self):
        with db.data_db().tx() as c:
            devicestore.drop_devices(c, [self.DEVICE])
        devices.DEVICES.forget()
        devices._FULL_AT.pop(self.DEVICE, None)

    def check(self, book: dict, at: float) -> None:
        self.assertEqual(devices.read_book(self.DEVICE), book)
        m = devices.DEVICES.get(self.DEVICE)
        summary = devices.hours_of(m)
        want = devices._add_up(book)
        self.assertEqual(summary["days"], want["days"])
        lo, blo = devices._window(m, time.time())
        self.assertEqual(summary["ledgerHours"], [x for x in want["ledgerHours"] if x[0] >= lo])
        self.assertEqual(summary["taskHours"], [x for x in want["taskHours"] if x[0] >= lo])
        self.assertEqual(devices.blocks_of(m), {h: v for h, v in book.get("blocks", {}).items() if int(h) >= blo})
        stored = {devices.date.fromisoformat(day): devices._day_numbers(rest) for day, _, *rest in devicestore.days(db.data_db().conn, self.DEVICE)}
        self.assertEqual(stored, want["days"])

    def test_random_sends(self):
        rnd = random.Random(66)
        now = time.time()
        top = int(now // 3600)
        base = {"device": self.DEVICE, "name": "Rows", "account": "rows@example.com"}
        book = None
        for step in range(150):
            at = now + step
            what = rnd.choice(("v1", "full", "hours", "hours", "hours", "hours"))
            hours = [str(top - rnd.randint(-20, settings.MAX_HOURS_PER_DEVICE + 30)) for _ in range(rnd.randint(0, 6))]
            sent = {kind: {h: ({} if rnd.random() < 0.25 else {field: rnd.randint(1, 9)}) for h in hours if rnd.random() < 0.7}
                    for kind, field in (("ledger", "usdMicro"), ("tasks", "gemini"), ("blocks", "secret"))}
            if what == "v1":
                raw = dict(base, v=1, updatedAt=int(at * 1000), **sent)
            else:
                raw = dict(base, v=2, updatedAt=int(at * 1000), hours=sent, **({"full": True} if what == "full" else {}))
            d = devices.clean_payload(raw, at)
            kind = devices.send_kind(raw)
            # what save_ingest does with it: a whole book again too soon is merged hour by hour
            # thứ save_ingest làm với nó: lại cả sổ quá sớm thì được ghép từng giờ
            merged = kind == "hours" or (kind == "full" and book is not None
                                         and at - devices._FULL_AT.get(self.DEVICE, -settings.FULL_BOOK_SECONDS) < settings.FULL_BOOK_SECONDS)
            outcome = devices.save_ingest(d, at, kind)
            if outcome == devices.NEED_FULL:
                self.assertIsNone(book)
                continue
            self.assertEqual(outcome, devices.SAVED)
            book = devices.merge_hours(book, d) if merged else devices.replace_hours(d)
            self.check(book, at)
            # now and then the server starts again: the same, read from the tables
            # thỉnh thoảng máy chủ khởi động lại: vẫn vậy, đọc từ các bảng
            if step % 40 == 39:
                devices.DEVICES.forget()
                self.check(book, at)

    def test_a_new_hour_pushes_the_oldest_out(self):
        now = time.time()
        top = int(now // 3600)
        base = {"v": 2, "device": self.DEVICE, "name": "Rows", "account": "rows@example.com", "updatedAt": int(now * 1000)}
        full = {"ledger": {str(top - i): {"usdMicro": i + 1} for i in range(settings.MAX_HOURS_PER_DEVICE)}, "tasks": {str(top - 230): {"gemini": 1}}}
        d = devices.clean_payload(dict(base, full=True, hours=full), now)
        devices.save_ingest(d, now, "full")
        book = devices.replace_hours(d)
        d = devices.clean_payload(dict(base, updatedAt=int(now * 1000) + 1, hours={"ledger": {str(top + 1): {"usdMicro": 5}}}), now)
        devices.save_ingest(d, now, "hours")
        book = devices.merge_hours(book, d)
        self.assertNotIn(str(top - settings.MAX_HOURS_PER_DEVICE + 1), book["ledger"])
        self.check(book, now)

    def test_only_the_hours_that_changed_are_written(self):
        now = time.time()
        raw = report(1, random.Random(3), now, device=self.DEVICE)
        devices.save_ingest(devices.clean_payload(raw, now), now)
        changes = db.data_db().conn.total_changes
        devices.save_ingest(devices.clean_payload(dict(raw, updatedAt=int(now * 1000) + 1000), now + 1), now + 1)
        # the same book and the same state a second later: nothing to write at all
        # cùng sổ và cùng trạng thái một giây sau: không có gì để ghi
        self.assertEqual(db.data_db().conn.total_changes, changes)
        hour = str(int(now // 3600))
        raw["ledger"][hour] = {"usd": 9.5}
        devices.save_ingest(devices.clean_payload(dict(raw, updatedAt=int(now * 1000) + 2000), now + 2), now + 2)
        # one hour and its day
        # một giờ và ngày của nó
        self.assertEqual(db.data_db().conn.total_changes - changes, 2)
        self.assertEqual(devices.read_book(self.DEVICE)["ledger"][hour]["usdMicro"], 9_500_000)
        # a change of what the computer is doing writes its row at once
        # máy đổi việc đang làm thì dòng của nó được ghi ngay
        devices.save_ingest(devices.clean_payload(dict(raw, updatedAt=int(now * 1000) + 3000, working=0, waiting=1), now + 3), now + 3)
        devices.DEVICES.forget()
        self.assertEqual(devices.DEVICES.get(self.DEVICE)["waiting"], 1)

    def test_a_quiet_computer_is_read_back_whole(self):
        quiet = time.time() - 5 * 86400
        raw = report(2, random.Random(4), quiet, device=self.DEVICE)
        cleaned = devices.clean_payload(raw, quiet)
        devices.save_ingest(cleaned, quiet)
        devices.DEVICES.forget()
        self.check(devices.book_of(cleaned), quiet)



class RowsAreTheBookOnOlderSQLite(RowsAreTheBook):
    """The same with an SQLite older than 3.24, which has no INSERT ... ON CONFLICT: an UPDATE, then an INSERT.
    Như trên với SQLite cũ hơn 3.24, không có INSERT ... ON CONFLICT: một UPDATE, rồi một INSERT."""

    def setUp(self):
        self.addCleanup(setattr, devicestore, "UPSERT", devicestore.UPSERT)
        devicestore.UPSERT = False


if __name__ == "__main__":
    unittest.main()
