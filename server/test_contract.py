#!/usr/bin/env python3
"""Contract test of /ingest formats v: 1 and v: 2, standard library only: python3 -m unittest test_contract (run in the server folder).
Plays the shared sample tests/contract/ingest-v2/cases.json into the server's own code: the same activity sent as v: 1 and as v: 2 must give
exactly the same board (role_view), the same history and the same totals per day, and both must end with the book the sample expects.
The Go receiver plays the same file.
  Test hợp đồng của định dạng /ingest v: 1 và v: 2, chỉ thư viện chuẩn: python3 -m unittest test_contract (chạy trong thư mục server).
  Chạy bộ dữ liệu mẫu chung tests/contract/ingest-v2/cases.json qua chính mã của máy chủ: cùng một chuỗi hoạt động gửi bằng v: 1 và bằng v: 2
  phải ra đúng cùng một bảng (role_view), cùng lịch sử và cùng tổng theo ngày, và cả hai phải kết thúc với đúng sổ mà bộ mẫu chờ.
  Bộ nhận Go chạy cùng file đó."""
import http.client
import importlib.util
import json
import os
import threading
import time
import unittest

# imported first: it points the server at temporary folders before any board module reads its settings
# nhập trước tiên: nó trỏ máy chủ sang thư mục tạm trước khi module board nào đọc cấu hình
import test_webhook as tw  # noqa: F401
import webhook as w
from board import daily, db, devices, security, settings, views

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(HERE, "..", "tests", "contract", "ingest-v2")


def load_sample() -> dict:
    with open(os.path.join(SAMPLE_DIR, "cases.json"), encoding="utf-8") as f:
        return json.load(f)


SAMPLE = load_sample()


def drop_rows(names) -> None:
    with db.data_db().tx() as c:
        for device in names:
            c.execute("DELETE FROM devices WHERE device = ?", (device,))
    devices.DEVICES.forget()
    for device in names:
        devices._FULL_AT.pop(device, None)


def snapshot(case_devices: set, at: float) -> dict:
    """What a person looking at the board would see of the case's computers: the admin board, the rows the history records, the totals per day.
    Những gì người xem bảng thấy về các máy của ca: bảng của quản trị, các dòng lịch sử ghi lại, tổng theo ngày."""
    kept = [m for m in devices.read_all_devices() if m["device"] in case_devices]
    accounts = {m.get("account") for m in kept}
    board = views.role_view(security.ADMIN, at)
    rows = devices.group_by_person(kept, at)
    return {
        "people": sorted((p for p in board["people"] if p.get("account") in accounts), key=lambda p: json.dumps(p, sort_keys=True)),
        "history": sorted((r["name"], r["account"], views.status_of(r, at), list(r["delegating"])) for r in rows),
        "days": {day: {k: dict(v) for k, v in by.items()} for day, by in daily.totals_by_day(kept, at).items()},
    }


def play(case: dict, form: str) -> list:
    """Play one case in one format; returns the snapshot after every step to compare, and checks each v: 2 outcome.
    Chạy một ca theo một định dạng; trả về ảnh chụp sau mỗi bước cần so, và kiểm kết quả của từng lần gửi v: 2."""
    case_devices = set(case["expect"])
    drop_rows(case_devices)
    shots = []
    for i, step in enumerate(case["steps"]):
        if step.get("dropRowFirst"):
            drop_rows([step["device"]])
        sent = step[form]
        if sent is None:
            continue
        if step["delivered"]:
            cleaned = devices.clean_payload(json.loads(json.dumps(sent)), step["at"])
            assert cleaned, (case["name"], i)
            outcome = devices.save_ingest(cleaned, step["at"], devices.send_kind(sent))
            want = step["expectV2"] if form == "v2" else devices.SAVED
            if outcome != want:
                raise AssertionError("%s step %d (%s): %s, expected %s" % (case["name"], i, form, outcome, want))
        if step["compare"]:
            shots.append((i, snapshot(case_devices, step["at"])))
    return shots


def book_of(device: str) -> dict:
    m = devices.read_device(device)
    return {k: m[k] for k in devices.HOUR_KINDS if k in m}


class SharedSample(unittest.TestCase):
    """The sample file itself: made by make_cases.py from the cases written there, in the time zone the server counts days in.
    Chính file mẫu: do make_cases.py dựng từ các ca viết ở đó, theo múi giờ máy chủ dùng để đếm ngày."""

    def test_the_file_is_what_make_cases_writes(self):
        spec = importlib.util.spec_from_file_location("make_cases", os.path.join(SAMPLE_DIR, "make_cases.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with open(module.OUT, encoding="utf-8") as f:
            self.assertEqual(f.read(), module.text(), "run python3 tests/contract/ingest-v2/make_cases.py again")

    def test_same_time_zone_as_the_server(self):
        self.assertEqual(settings.LOCAL_TZ.utcoffset(None).total_seconds(), SAMPLE["tzHours"] * 3600)


class SameBoardFromBothFormats(unittest.TestCase):
    """The contract: v: 1 and v: 2 of the same activity give the same board, history and totals per day, and the book the sample expects.
    Hợp đồng: v: 1 và v: 2 của cùng một chuỗi hoạt động cho ra cùng bảng, lịch sử và tổng theo ngày, và đúng sổ bộ mẫu chờ."""

    def tearDown(self):
        drop_rows({d for case in SAMPLE["cases"] for d in case["expect"]})

    def check_end(self, case: dict, form: str) -> None:
        for device, want in case["expect"].items():
            self.assertEqual(book_of(device), want["book"], "%s %s %s" % (case["name"], form, device))
            m = devices.read_device(device)
            got = {day.isoformat(): {"usdMicro": v["usdMicro"], **{k: v[k] for k in ("tokensIn", "tokensOut", "gemini", "chatgpt", "gemma")}}
                   for day, v in sorted(devices.hours_of(m)["days"].items())}
            self.assertEqual(got, want["days"], "%s %s %s" % (case["name"], form, device))

    def test_every_case(self):
        for case in SAMPLE["cases"]:
            with self.subTest(case=case["name"]):
                v2 = play(case, "v2")
                self.check_end(case, "v2")
                if case["v2Only"]:
                    continue
                v1 = play(case, "v1")
                self.check_end(case, "v1")
                self.assertEqual([i for i, _ in v1], [i for i, _ in v2])
                for (i, one), (_, two) in zip(v1, v2):
                    self.assertTrue(one["people"], "%s step %d shows nobody" % (case["name"], i))
                    self.assertEqual(one, two, "%s step %d" % (case["name"], i))


class MergeHours(unittest.TestCase):
    """merge_hours is the part the Go receiver copies: pure, and the same answer for a send repeated.
    merge_hours là phần bộ nhận Go chép lại: hàm thuần, và gửi lặp vẫn cho cùng kết quả."""

    def test_pure_and_repeatable(self):
        kept = {"ledger": {"10": {"usdMicro": 1, "usd": 1e-06}}, "tasks": {}}
        sent = {"ledger": {"11": {"usdMicro": 2, "usd": 2e-06}, "10": {}}, "tasks": {"11": {"gemini": 1}}}
        before = json.dumps([kept, sent], sort_keys=True)
        once = devices.merge_hours(kept, sent)
        self.assertEqual(json.dumps([kept, sent], sort_keys=True), before)
        self.assertEqual(once, {"ledger": {"11": {"usdMicro": 2, "usd": 2e-06}}, "tasks": {"11": {"gemini": 1}}})
        self.assertEqual(devices.merge_hours(once, sent), once)

    def test_keeps_the_newest_hours(self):
        kept = {"ledger": {str(h): {"usdMicro": h} for h in range(settings.MAX_HOURS_PER_DEVICE)}, "tasks": {}}
        out = devices.merge_hours(kept, {"ledger": {"100000": {"usdMicro": 1}}})
        self.assertEqual(len(out["ledger"]), settings.MAX_HOURS_PER_DEVICE)
        self.assertNotIn("0", out["ledger"])
        self.assertIn("100000", out["ledger"])


class IngestAnswers(unittest.TestCase):
    """/ingest over HTTP: what it answers, needFull, the limits on hours and on full books, and an older plugin left as it was.
    /ingest qua HTTP: nó trả lời gì, needFull, giới hạn giờ và sổ đủ, và plugin cũ vẫn như trước."""

    DEVICES = ("device-v2a", "device-v2b", "device-v2c", "device-v2d", "device-v2e")

    @classmethod
    def setUpClass(cls):
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.keys = {}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        views.INGEST_GATE.buckets, views.INGEST_GATE.new_devices = {}, {}

    def tearDown(self):
        drop_rows(self.DEVICES)

    def send(self, packet: dict):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            # the shared key of the test server, until the server hands the computer its own
            # khoá chung của máy chủ thử, cho tới khi máy chủ trao cho máy khoá riêng
            key = self.keys.get(packet["device"], settings.INGEST_KEY)
            conn.request("POST", "/ingest", json.dumps(packet), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            r = conn.getresponse()
            answer = json.loads(r.read() or b"{}")
        finally:
            conn.close()
        if answer.get("deviceKey"):
            self.keys[packet["device"]] = answer["deviceKey"]
        return r.status, answer

    def packet(self, device: str, v: int = 2, **fields) -> dict:
        base = {"v": v, "device": device, "name": "Vee", "account": "vee-%s@example.com" % device, "updatedAt": int(time.time() * 1000),
                "openSessions": 1, "working": 1}
        return dict(base, **fields)

    def hour(self, back: int = 0) -> str:
        return str(int(time.time() // 3600) - back)

    def test_the_answer_says_what_the_server_reads_and_wants(self):
        status, answer = self.send(self.packet("device-v2a", v=1))
        self.assertEqual(status, 200)
        self.assertEqual(answer["accepts"], [1, 2])
        self.assertEqual((answer["minGapMs"], answer["stateGapMs"], answer["maxGapMs"]),
                         (settings.INGEST_MIN_GAP_MS, settings.INGEST_STATE_GAP_MS, settings.INGEST_MAX_GAP_MS))
        self.assertIs(answer["needFull"], False)
        self.assertEqual(answer["boot"], devices.BOOT_ID)
        self.assertRegex(answer["boot"], r"\A[0-9a-f]{16}\Z")

    def test_changed_hours_from_an_unknown_computer_ask_for_the_whole_book(self):
        h = self.hour()
        status, answer = self.send(self.packet("device-v2b", full=False, hours={"ledger": {h: {"usdMicro": 5}}}))
        self.assertEqual((status, answer["needFull"]), (200, True))
        self.assertIsNone(devices.read_device("device-v2b"))
        status, answer = self.send(self.packet("device-v2b", full=True, hours={"ledger": {h: {"usdMicro": 5, "input": 1}}}))
        self.assertEqual((status, answer["needFull"]), (200, False))
        self.assertEqual(devices.read_device("device-v2b")["ledger"], {h: {"usdMicro": 5, "usd": 5e-06, "input": 1}})

    def test_v2_hours_are_cleaned_like_v1(self):
        h, old, ahead = self.hour(), self.hour(settings.MAX_HOURS_PER_DEVICE + 5), str(int(time.time() // 3600) + 30)
        self.send(self.packet("device-v2c", full=True, hours={
            "ledger": {h: {"usdMicro": 7, "prompt": "never kept", "input": -1}, old: {"usdMicro": 1}, ahead: {"usdMicro": 1}},
            "tasks": {h: {"gemini": 2, "nobody": 9}}, "blocks": {h: {"secret": 1, "words": 3}}}))
        m = devices.read_device("device-v2c")
        self.assertEqual(m["ledger"], {h: {"usdMicro": 7, "usd": 7e-06}})
        self.assertEqual(m["tasks"], {h: {"gemini": 2}})
        self.assertEqual(m["blocks"], {h: {"secret": 1}})
        self.assertNotIn("hours", m)
        self.assertEqual(m["v"], 1)

    def test_a_second_full_book_soon_after_is_merged_not_replaced(self):
        h, before = self.hour(), self.hour(1)
        self.send(self.packet("device-v2d", full=True, hours={"ledger": {before: {"usdMicro": 3}, h: {"usdMicro": 4}}}))
        # a full book that no longer holds the hour before: within the hour it is merged, so the hour before stays
        # sổ đủ không còn giờ trước: trong vòng một giờ nó được ghép, nên giờ trước vẫn còn
        self.send(self.packet("device-v2d", full=True, hours={"ledger": {h: {"usdMicro": 6}}}))
        self.assertEqual(sorted(devices.read_device("device-v2d")["ledger"]), sorted([before, h]))
        self.assertEqual(devices.read_device("device-v2d")["ledger"][h]["usdMicro"], 6)
        # after FULL_BOOK_SECONDS a full book replaces again
        # sau FULL_BOOK_SECONDS một sổ đủ lại thay được cả sổ
        devices._FULL_AT["device-v2d"] -= settings.FULL_BOOK_SECONDS
        self.send(self.packet("device-v2d", full=True, hours={"ledger": {h: {"usdMicro": 6}}}))
        self.assertEqual(sorted(devices.read_device("device-v2d")["ledger"]), [h])

    def test_a_send_older_than_what_is_kept_is_dropped_but_a_clock_put_back_is_not(self):
        h, now_ms = self.hour(), int(time.time() * 1000)
        self.send(self.packet("device-v2e", full=True, hours={"ledger": {h: {"usdMicro": 9}}}, updatedAt=now_ms))
        status, answer = self.send(self.packet("device-v2e", hours={"ledger": {h: {"usdMicro": 8}}}, updatedAt=now_ms - 1000, waiting=1))
        self.assertEqual(status, 200)
        m = devices.read_device("device-v2e")
        self.assertEqual((m["ledger"][h]["usdMicro"], m["waiting"]), (9, 0))
        self.send(self.packet("device-v2e", hours={"ledger": {h: {"usdMicro": 10}}}, updatedAt=now_ms - settings.REORDER_WINDOW_MS - 1000))
        self.assertEqual(devices.read_device("device-v2e")["ledger"][h]["usdMicro"], 10)

    def test_a_wrong_version_or_hours_that_are_not_a_table_are_handled(self):
        status, _ = self.send(self.packet("device-v2a", v=3))
        self.assertEqual(status, 400)
        status, answer = self.send(self.packet("device-v2a", full=True, hours=["not", "a", "table"]))
        self.assertEqual((status, answer["needFull"]), (200, False))
        self.assertEqual(devices.read_device("device-v2a")["ledger"], {})


class OneWayToTheHours(unittest.TestCase):
    """The hour books are read only through board/devices.py (book_of, read_book, hours_of, blocks_of), so stage 2 can move them into
    rows of their own by changing that one file. Nothing else reads a record's ledger or blocks, or the inside of DeviceCache.
    Sổ giờ chỉ được đọc qua board/devices.py (book_of, read_book, hours_of, blocks_of), để đợt 2 chuyển chúng sang các dòng riêng
    chỉ bằng cách sửa đúng file đó. Không chỗ nào khác đọc ledger hay blocks của một bản ghi, hay phần bên trong DeviceCache."""

    def test_no_reader_outside_devices_py(self):
        import glob
        import re
        found = []
        for path in [os.path.join(HERE, "webhook.py")] + glob.glob(os.path.join(HERE, "board", "*.py")):
            if os.path.basename(path) == "devices.py":
                continue
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if re.search(r'\[\s*"(ledger|blocks)"\s*\]|\.get\(\s*"(ledger|blocks)"|DEVICES\.(devices|summaries|people)\b', line):
                        found.append("%s:%d" % (os.path.relpath(path, HERE), n))
        self.assertEqual(found, [])


class SendsAtTheSameMoment(unittest.TestCase):
    """Two Claude Code sessions on one computer send changed hours at the same moment: neither loses the other's hour.
    Hai phiên Claude Code trên một máy gửi các giờ đã đổi cùng lúc: không lần nào làm mất giờ của lần kia."""

    def tearDown(self):
        drop_rows(["device-v2race"])

    def test_no_hour_is_lost(self):
        now = time.time()
        base = {"v": 2, "device": "device-v2race", "name": "Race", "account": "race@example.com", "updatedAt": int(now * 1000)}
        devices.save_ingest(devices.clean_payload(dict(base, full=True, hours={}), now), now, "full")
        first = int(now // 3600) - 100
        hours = [str(first + i) for i in range(80)]

        def send(h):
            sent = dict(base, hours={"ledger": {h: {"usdMicro": 1}}})
            devices.save_ingest(devices.clean_payload(sent, now), now, "hours")
        threads = [threading.Thread(target=send, args=(h,)) for h in hours]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(devices.read_device("device-v2race")["ledger"]), sorted(hours))


if __name__ == "__main__":
    unittest.main()
