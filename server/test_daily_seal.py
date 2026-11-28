#!/usr/bin/env python3
"""Sealing the daily cost totals into the audit chain (board/daily.py, AuditLog in board/stores.py) and telling the admins each
morning the fingerprint the log had at the end of a day (board/chat.py). Names and addresses here are made up.
  Niêm phong tổng chi phí theo ngày vào chuỗi nhật ký kiểm toán (board/daily.py, AuditLog trong board/stores.py) và mỗi sáng báo
cho quản trị dấu vân tay của nhật ký tới hết một ngày (board/chat.py). Tên và địa chỉ ở đây đều là tự đặt."""
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import test_webhook as tw  # noqa: F401  (sets the temporary folders before the board is imported)
from board import chat, daily, db, security, settings, stores


class Sealing(unittest.TestCase):
    """A day that is no longer counted again gets one daily-seal line in the chain, and the check of the chain counts it again.
    Một ngày không còn được đếm lại nhận một dòng daily-seal trong chuỗi, và lần kiểm chuỗi tính lại nó."""

    # a Wednesday at 15:00 on the server's clock: the last DAILY_RECOUNT_DAYS days (12 to 18 November) are still counted again
    # thứ Tư lúc 15:00 theo đồng hồ máy chủ: DAILY_RECOUNT_DAYS ngày gần nhất (12 tới 18 tháng 11) vẫn còn được đếm lại
    TODAY = date(2026, 11, 18)
    AN, BINH = "an@example.com|an", "binh@example.com|binh"

    def at(self, day: date, hour: int = 15) -> float:
        return datetime(day.year, day.month, day.day, hour, tzinfo=settings.LOCAL_TZ).timestamp()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = db.Database(os.path.join(self.tmp, "board.db"), db.DATA_STEPS, "NORMAL")
        self.store = daily.DailyStore(self.db)
        self.log = stores.AuditLog(self.db)
        with self.db.tx() as c:
            c.execute("INSERT INTO meta VALUES (?, ?)", (daily.SINCE_KEY, (self.TODAY - timedelta(days=12)).isoformat()))

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, day: date, person: str, usd: float) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO daily (" + daily.COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (day.isoformat(), person, person.split("|")[1].capitalize(), person.split("|")[0], "hq", "HQ", usd, 100, 200, 1, 2, 3))

    def seals(self) -> list:
        return [json.loads(b) for (b,) in self.db.rows("SELECT body FROM audit WHERE action = ? ORDER BY id", (daily.SEAL_ACTION,))]

    def check(self, now: float) -> dict:
        self.log.checked = None
        return self.log.check(now)

    def day(self, back: int) -> date:
        return self.TODAY - timedelta(days=back)

    def test_each_closed_day_is_sealed_once_and_a_counted_day_never(self):
        self.put(self.day(8), self.AN, 1.25)
        self.put(self.day(8), self.BINH, 2.5)
        self.put(self.day(7), self.AN, 4)
        self.put(self.day(6), self.AN, 9)
        self.assertEqual(self.store.seal(self.at(self.TODAY), self.log.write), 6)
        seals = self.seals()
        # from the first day counted (12 days back) to the last day no longer counted (7 days back), oldest first, empty days too
        # từ ngày đầu tiên được đếm (12 ngày trước) tới ngày cuối không còn được đếm (7 ngày trước), cũ trước, cả ngày trống
        self.assertEqual([s["day"] for s in seals], [self.day(n).isoformat() for n in range(12, 6, -1)])
        eight = seals[-2]
        self.assertEqual((eight["rows"], eight["usd"]), (2, 3.75))
        self.assertEqual(len(eight["digest"]), 64)
        self.assertEqual((seals[0]["rows"], seals[0]["usd"]), (0, 0))
        self.assertEqual(self.store.seal(self.at(self.TODAY, 16), self.log.write), 0)
        # the next morning one more day leaves the counting
        # sáng hôm sau thêm một ngày ra khỏi phần được đếm lại
        self.assertEqual(self.store.seal(self.at(self.TODAY + timedelta(days=1), 1), self.log.write), 1)
        self.assertEqual(self.seals()[-1]["day"], self.day(6).isoformat())
        self.assertEqual((self.seals()[-1]["rows"], self.seals()[-1]["usd"]), (1, 9))

    def test_nothing_is_sealed_before_the_first_count(self):
        with self.db.tx() as c:
            c.execute("DELETE FROM meta WHERE key = ?", (daily.SINCE_KEY,))
        self.assertEqual(self.store.seal(self.at(self.TODAY), self.log.write), 0)

    def test_a_day_whose_line_was_not_written_is_tried_again(self):
        self.assertEqual(self.store.seal(self.at(self.TODAY), lambda **fields: False), 0)
        self.assertEqual(self.seals(), [])
        self.assertEqual(self.store.seal(self.at(self.TODAY), self.log.write), 6)

    def test_the_check_names_a_sealed_day_whose_numbers_changed(self):
        self.put(self.day(8), self.AN, 1.25)
        self.put(self.day(8), self.BINH, 2.5)
        self.put(self.day(3), self.AN, 7)
        self.store.seal(self.at(self.TODAY), self.log.write)
        r = self.check(self.at(self.TODAY))
        self.assertEqual((r["ok"], r["changedDays"], r["sealedDays"]), (True, [], 6))
        # a day still counted again may change: nothing is said
        # ngày còn được đếm lại thì đổi được: không báo gì
        with self.db.tx() as c:
            c.execute("UPDATE daily SET usd = 70 WHERE day = ?", (self.day(3).isoformat(),))
        self.assertTrue(self.check(self.at(self.TODAY))["ok"])
        with self.db.tx() as c:
            c.execute("UPDATE daily SET usd = 0.25 WHERE day = ? AND person = ?", (self.day(8).isoformat(), self.AN))
        r = self.check(self.at(self.TODAY))
        self.assertEqual((r["ok"], r["changedDays"], r["brokenAt"]), (False, [self.day(8).isoformat()], ""))

    def test_a_token_count_changed_or_a_line_added_or_taken_out_shows_too(self):
        self.put(self.day(8), self.AN, 1.25)
        self.store.seal(self.at(self.TODAY), self.log.write)
        for sql, args in (("UPDATE daily SET tokens_in = 1 WHERE day = ?", (self.day(8).isoformat(),)),
                          ("DELETE FROM daily WHERE day = ?", (self.day(8).isoformat(),))):
            with self.db.tx() as c:
                c.execute(sql, args)
            self.assertEqual(self.check(self.at(self.TODAY))["changedDays"], [self.day(8).isoformat()], sql)
        with self.db.tx() as c:
            c.execute("DELETE FROM daily")
        self.put(self.day(8), self.AN, 1.25)
        self.assertTrue(self.check(self.at(self.TODAY))["ok"])
        self.put(self.day(10), self.BINH, 0.5)
        self.assertEqual(self.check(self.at(self.TODAY))["changedDays"], [self.day(10).isoformat()])

    def test_a_changed_seal_line_breaks_the_chain(self):
        self.put(self.day(8), self.AN, 1.25)
        self.store.seal(self.at(self.TODAY), self.log.write)
        rowid, body = self.db.rows("SELECT id, body FROM audit WHERE action = ? AND body LIKE ?", (daily.SEAL_ACTION, '%' + self.day(8).isoformat() + '%'))[0]
        with self.db.tx() as c:
            c.execute("UPDATE daily SET usd = 9 WHERE day = ?", (self.day(8).isoformat(),))
            c.execute("UPDATE audit SET body = ? WHERE id = ?", (body.replace('"usd":1.25', '"usd":9'), rowid))
        self.assertFalse(self.check(self.at(self.TODAY))["ok"])

    def test_days_dropped_by_age_are_not_called_changed(self):
        self.put(self.day(8), self.AN, 1.25)
        self.store.seal(self.at(self.TODAY), self.log.write)
        with self.db.tx() as c:
            c.execute("DELETE FROM daily")
        later = self.at(self.TODAY + timedelta(days=500))
        self.assertTrue(self.check(later)["ok"])

    def test_forgetting_a_person_seals_their_closed_days_again(self):
        self.put(self.day(8), self.AN, 1.25)
        self.put(self.day(8), self.BINH, 2.5)
        self.put(self.day(3), self.BINH, 4)
        self.store.seal(self.at(self.TODAY), self.log.write)
        self.assertEqual(self.store.forget("binh@example.com", self.log.write, self.at(self.TODAY)), 2)
        last = self.seals()[-1]
        self.assertEqual((last["day"], last["rows"], last["usd"], last["reason"]), (self.day(8).isoformat(), 1, 1.25, "forget-usage"))
        self.assertNotIn("binh", json.dumps(last).lower())
        self.assertTrue(self.check(self.at(self.TODAY))["ok"])
        # the day sealed again is listed once, with its newest numbers
        # ngày được niêm phong lại chỉ hiện một lần, với con số mới nhất
        listed = [s for s in self.log.seals(14) if s["day"] == self.day(8).isoformat()]
        self.assertEqual([(s["rows"], s["usd"]) for s in listed], [(1, 1.25)])

    def test_forgetting_on_a_day_already_dropped_by_age_seals_nothing_again(self):
        self.put(self.day(8), self.AN, 1.25)
        self.store.seal(self.at(self.TODAY), self.log.write)
        before = len(self.seals())
        self.assertEqual(self.store.forget("an@example.com", self.log.write, self.at(self.TODAY + timedelta(days=500))), 1)
        self.assertEqual(len(self.seals()), before)

    def test_seal_lines_are_listed_apart_newest_first_with_the_chain_fingerprint(self):
        self.put(self.day(8), self.AN, 1.25)
        self.log.write(action="login", actor="adm")
        self.store.seal(self.at(self.TODAY), self.log.write)
        month = datetime.now(settings.LOCAL_TZ).strftime("%Y-%m")
        self.assertEqual([r["action"] for r in self.log.read(month)], ["login"])
        listed = self.log.seals(3)
        self.assertEqual([s["day"] for s in listed], [self.day(n).isoformat() for n in (7, 8, 9)])
        newest = self.db.rows("SELECT body FROM audit ORDER BY id DESC LIMIT 1")[0][0]
        self.assertEqual(listed[0]["hash"], json.loads(newest)["hash"][:16])
        self.assertEqual((listed[1]["rows"], listed[1]["usd"]), (1, 1.25))
        self.assertEqual(self.log.latest_seal()["day"], self.day(7).isoformat())


class MorningMessage(unittest.TestCase):
    """Each morning a Telegram chat linked to an admin account gets the fingerprint of the newest sealed day: no name, no money.
    Mỗi sáng một chat Telegram đã liên kết với tài khoản quản trị nhận dấu vân tay của ngày niêm phong mới nhất: không tên, không tiền."""

    ADMIN_TG, VIEWER_TG, STRANGER_TG = "7001", "7002", "7003"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = db.Database(os.path.join(self.tmp, "board.db"), db.DATA_STEPS, "NORMAL")
        self.log = stores.AuditLog(self.db)
        patches = [mock.patch.object(chat, "AUDIT_LOG", self.log),
                   mock.patch.dict(stores.ACCOUNTS.d, {"accounts": {"boss": {"role": security.ADMIN, "secret": "", "telegramId": self.ADMIN_TG},
                                                                    "watcher": {"role": security.VIEWER, "secret": "", "telegramId": self.VIEWER_TG}}})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.before = json.loads(json.dumps(stores.TV.d))
        self.addCleanup(self.restore)
        now = time.time()
        self.ids = {}
        for tg in (self.ADMIN_TG, self.VIEWER_TG, self.STRANGER_TG):
            self.ids[tg], _ = stores.TV.create({"name": "Chat " + tg, "approvedBy": "boss", "ip": "", "device": "Telegram",
                                                "kind": settings.KIND_TELEGRAM, "telegramId": tg}, now)
        self.log.write(action=daily.SEAL_ACTION, day="2026-11-11", rows=3, usd=12.5, digest="d" * 64)

    def restore(self):
        stores.TV.mutate(lambda d: (d.clear(), d.update(self.before)))
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def morning(self, hour: int = 8) -> float:
        d = datetime.now(settings.LOCAL_TZ)
        return d.replace(hour=hour, minute=5, second=0, microsecond=0).timestamp()

    def test_only_an_admins_chat_is_told_once_a_day_with_no_name_and_no_money(self):
        out = chat.seals_due(self.morning())
        self.assertEqual([m["to"] for m in out], [int(self.ADMIN_TG)])
        text = out[0]["text"]
        fingerprint = self.log.latest_seal()["hash"]
        self.assertIn("2026-11-11", text)
        self.assertIn(fingerprint, text)
        self.assertEqual(out[0]["copy"], {"label": "Copy the fingerprint", "text": fingerprint})
        self.assertIn("3", text)
        for word in ("12.5", "12,5", "$", "boss", "Chat"):
            self.assertNotIn(word, text)
        self.assertEqual(chat.seals_due(self.morning(9)), [])
        told = [json.loads(b) for (b,) in self.db.rows("SELECT body FROM audit WHERE action = ?", ("telegram-seal",))]
        self.assertEqual([(t["id"], t["day"]) for t in told], [(self.ids[self.ADMIN_TG], "2026-11-11")])
        # a newer sealed day is told the next time
        # ngày niêm phong mới hơn được báo ở lần kế tiếp
        self.log.write(action=daily.SEAL_ACTION, day="2026-11-12", rows=0, usd=0, digest="e" * 64)
        self.assertEqual(len(chat.seals_due(self.morning(10))), 1)

    def test_nothing_at_night_and_nothing_without_a_seal(self):
        self.assertEqual(chat.seals_due(self.morning(3)), [])
        self.assertEqual(len(chat.seals_due(self.morning(8))), 1)
        with self.db.tx() as c:
            c.execute("DELETE FROM audit")
        stores.TV.mutate(lambda d: [r.pop("sealTold", None) for r in d.values()])
        self.assertEqual(chat.seals_due(self.morning(8)), [])

    def test_a_tick_of_the_bot_carries_the_message(self):
        with mock.patch.object(chat, "alerts_due", lambda now: []):
            sent = chat.on_call({"tick": True}, self.morning())["send"]
        self.assertEqual([m["to"] for m in sent], [int(self.ADMIN_TG)])


if __name__ == "__main__":
    unittest.main()
