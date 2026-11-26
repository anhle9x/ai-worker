#!/usr/bin/env python3
"""Test of what this server gives the optional Go receiver (board/receiver.py), standard library only: python3 -m unittest test_receiver.
The internal paths, the file of secrets, the batches of rows, the policy, the books loaded at a start and turning the signing secret.
  Test những gì máy chủ này cấp cho bộ nhận Go tuỳ chọn (board/receiver.py), chỉ thư viện chuẩn: python3 -m unittest test_receiver.
  Các đường nội bộ, file bí mật, các lô dòng, tài liệu chính sách, sổ giờ nạp lúc khởi động và việc xoay bí mật ký."""
import base64
import hashlib
import hmac
import http.client
import json
import os
import stat
import threading
import time
import unittest

# imported first: it points the server at temporary folders before any board module reads its settings
# nhập trước tiên: nó trỏ máy chủ sang thư mục tạm trước khi module board nào đọc cấu hình
import test_webhook as tw  # noqa: F401
import webhook as w
from board import db, devicekeys, devices, login, receiver, security, settings, stores, views
from test_contract import drop_rows

DEVICES = ("device-rcva", "device-rcvb", "device-rcvc")


class Receiver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        settings.RECEIVER_ENABLED = True
        views.INGEST_GATE.buckets, views.INGEST_GATE.new_devices = {}, {}
        self.code = devicekeys.DEVICE_KEYS.internal_code()

    def tearDown(self):
        settings.RECEIVER_ENABLED = False
        drop_rows(DEVICES)
        for device in DEVICES:
            devicekeys.DEVICE_KEYS.forget(device)
            views.INGEST_GATE.identities.pop(device, None)

    def call(self, method: str, path: str, body=None, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, None if body is None else json.dumps(body), headers)
            r = conn.getresponse()
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
        finally:
            conn.close()

    def internal(self, method: str, path: str, body=None, **headers):
        return self.call(method, path, body, Authorization="Bearer " + self.code, **headers)

    def enrol(self, device: str) -> str:
        """A first send with the shared key, as a new computer makes it: the server knows who it is and gives it its own key.
        Lần gửi đầu bằng khoá chung, như một máy mới gửi: máy chủ biết đó là ai và trao khoá riêng."""
        status, answer = self.call("POST", "/ingest", {"v": 2, "device": device, "name": "Rae", "account": device + "@example.com",
                                                      "updatedAt": int(time.time() * 1000), "full": True, "hours": {}},
                                   Authorization="Bearer " + settings.INGEST_KEY)
        self.assertEqual(status, 200)
        return answer["deviceKey"]

    def row(self, device: str, hours: dict, kind: str = "hours", **state) -> dict:
        at = int(time.time() * 1000)
        v = dict({"v": 2, "device": device, "updatedAt": at, "openSessions": 1, "working": 1, "full": kind == "full", "hours": hours}, **state)
        return {"k": ["m", device], "at": at, "kind": kind, "ip": "203.0.113.9", "v": v}

    def test_the_paths_are_not_there_when_off_or_from_elsewhere(self):
        settings.RECEIVER_ENABLED = False
        self.assertEqual(self.internal("GET", "/internal/policy")[0], 404)
        settings.RECEIVER_ENABLED = True
        self.assertEqual(self.internal("GET", "/internal/policy")[0], 200)
        # through a proxy, with a wrong code, or with none: the path does not exist
        # qua proxy, mã sai, hay không có mã: đường không tồn tại
        self.assertEqual(self.internal("GET", "/internal/policy", **{"X-Forwarded-For": "198.51.100.1"})[0], 404)
        self.assertEqual(self.call("GET", "/internal/policy", Authorization="Bearer wrong")[0], 404)
        self.assertEqual(self.call("GET", "/internal/policy")[0], 404)
        self.assertEqual(self.call("POST", "/internal/rows", {}, Authorization="Bearer " + settings.INGEST_KEY)[0], 404)

    def test_the_file_of_secrets(self):
        path = receiver.write_secrets(time.time())
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        signing = [e for e in entries if e["alg"] == "HS256"]
        self.assertTrue(signing)
        self.assertEqual(entries[-2], {"kid": "internal", "alg": "internal", "secret": self.code})
        self.assertEqual(entries[-1]["alg"], "ticket")
        self.assertEqual({e["org"] for e in signing}, {devicekeys.DEVICE_KEYS.org})
        self.assertFalse([n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")])

    def people(self, since: int = 0, boot: str = "", limit: int = 5000, loading: bool = False) -> dict:
        # built again on each ask here, as it is past RECEIVER_PEOPLE_SECONDS
        # dựng lại mỗi lần hỏi ở đây, như khi đã quá RECEIVER_PEOPLE_SECONDS
        receiver.PEOPLE.built_at = None
        status, answer = self.internal("GET", "/internal/people?since=%d&boot=%s&limit=%d%s" % (since, boot, limit, "&loading=1" if loading else ""))
        self.assertEqual(status, 200)
        return answer

    def test_the_table_of_people(self):
        """/internal/people: each computer with the code of its person's row on the board and its branch, then only what changed: a move
        to another branch, a computer gone; a page at a time; another start or a number ahead starts again from nothing; no email.
        /internal/people: mỗi máy kèm mã dòng của người của nó trên bảng và chi nhánh của nó, rồi chỉ phần đổi: chuyển sang chi nhánh
        khác, một máy đã mất; từng trang một; một lần khởi động khác hay một số đi trước thì bắt đầu lại từ đầu; không có email."""
        self.enrol("device-rcva")
        self.enrol("device-rcvb")
        first = self.people()
        self.assertTrue(first["reset"])
        self.assertFalse(first["more"])
        self.assertEqual(first["gone"], [])
        mine = {p["device"]: p for p in first["people"] if p["device"] in DEVICES}
        self.assertEqual(set(mine), {"device-rcva", "device-rcvb"})
        board = {p["account"]: p["row"] for p in views.role_view(views.ADMIN, time.time())["people"]}
        for device, p in mine.items():
            self.assertEqual(p, {"device": device, "row": board[device + "@example.com"], "scope": ""})
        self.assertNotIn("@", json.dumps(first))
        boot, seq = first["boot"], first["seq"]
        again = self.people(seq, boot)
        self.assertEqual((again["reset"], again["people"], again["gone"], again["seq"]), (False, [], [], seq))
        # a branch for the address they send from: both move, and only that is given
        # một chi nhánh cho địa chỉ họ gửi từ đó: cả hai chuyển, và chỉ phần đó được đưa
        ip = devices.read_device("device-rcva")["ip"]
        stores.LOCATIONS.mutate(lambda d: views.edit_location(d, {"ip": ip, "name": "Hue", "lat": 16.46, "lon": 107.59}))
        try:
            branch = stores.LOCATIONS.read()["ipToLocation"][ip]
            moved = self.people(seq, boot)
        finally:
            stores.LOCATIONS.mutate(lambda d: views.edit_location(d, {"ip": ip, "remove": True, "confirm": True}))
        self.assertFalse(moved["reset"])
        self.assertEqual({p["device"]: p["scope"] for p in moved["people"] if p["device"] in DEVICES}, {"device-rcva": branch, "device-rcvb": branch})
        self.assertEqual({p["row"] for p in moved["people"] if p["device"] in DEVICES}, {p["row"] for p in mine.values()})
        # a computer gone is named once
        # một máy đã mất được nêu tên một lần
        drop_rows(["device-rcvb"])
        gone = self.people(moved["seq"], boot)
        self.assertIn("device-rcvb", gone["gone"])
        self.assertNotIn("device-rcvb", [p["device"] for p in gone["people"]])
        self.assertNotIn("device-rcvb", self.people(gone["seq"], boot)["gone"])
        # another start: the whole table a page at a time, the pages after the first asked with loading. A page after the first may
        # still name a computer gone, so one that goes while the table loads is not kept
        # một lần khởi động khác: cả bảng từng trang một, các trang sau trang đầu hỏi với loading. Trang sau trang đầu vẫn có thể nêu
        # máy đã mất, để máy mất trong lúc bảng đang nạp không bị giữ lại
        page, seen = self.people(gone["seq"], "another-start", limit=1), []
        self.assertTrue(page["reset"])
        self.assertEqual(page["gone"], [])
        while True:
            seen += [p["device"] for p in page["people"]]
            if not page["more"]:
                break
            page = self.people(page["seq"], page["boot"], limit=1, loading=True)
            self.assertFalse(page["reset"])
        self.assertIn("device-rcva", seen)
        self.assertNotIn("device-rcvb", seen)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(self.people(10 ** 9, boot)["reset"])

    def test_the_table_of_people_stays_small(self):
        """The log keeps one pair per computer once it grows; past PEOPLE_GONE_MAX computers gone the oldest are forgotten, and a
        receiver holding a number from before them starts again from nothing, unless it is loading the whole table.
        Nhật ký giữ mỗi máy một cặp khi nó lớn lên; quá PEOPLE_GONE_MAX máy đã mất thì quên các máy cũ nhất, và bộ nhận giữ một số từ
        trước đó bắt đầu lại từ đầu, trừ khi nó đang nạp cả bảng."""
        table = receiver.People()
        names = {"now": ["device-a", "device-b", "device-c"]}
        saved = (receiver.read_all_devices, receiver.PEOPLE_GONE_MAX)
        receiver.read_all_devices = lambda: [{"v": 1, "device": d, "account": "", "name": d, "updatedAt": 1000} for d in names["now"]]
        receiver.PEOPLE_GONE_MAX = 1
        try:
            first = table.page(0, "", 100, 1.0)
            self.assertEqual(len(first["people"]), 3)
            names["now"] = ["device-a", "device-b"]
            one = table.page(first["seq"], devices.BOOT_ID, 100, 10.0)
            self.assertEqual((one["reset"], one["gone"]), (False, ["device-c"]))
            names["now"] = ["device-a"]
            two = table.page(one["seq"], devices.BOOT_ID, 100, 20.0)
            self.assertEqual((two["reset"], two["gone"]), (False, ["device-b"]))
            # two gone, one remembered: device-c is forgotten, so a number from before it went is too old
            # hai máy mất, nhớ một: device-c bị quên, nên một số từ trước khi nó mất đã quá cũ
            self.assertEqual(table.gone, 1)
            self.assertTrue(table.page(first["seq"], devices.BOOT_ID, 100, 20.0)["reset"])
            self.assertFalse(table.page(first["seq"], devices.BOOT_ID, 100, 20.0, loading=True)["reset"])
            for i in range(1, 1200):
                names["now"] = ["device-a"] if i % 2 else ["device-a", "device-b"]
                table.page(0, "", 1, 20.0 + 10 * i)
            self.assertLessEqual(len(table.log), 2 * len(table.rows) + 1001)
        finally:
            receiver.read_all_devices, receiver.PEOPLE_GONE_MAX = saved

    def test_the_branch_of_each_person_is_the_board_s(self):
        """The table of people finds each person's branch from branch_facts, without building the board: for random computers (several per
        person, addresses changing, ties in time, computers without a time) it gives the branch group_by_person's rows give.
        Bảng người tìm chi nhánh của mỗi người từ branch_facts, không dựng bảng: với các máy ngẫu nhiên (nhiều máy mỗi người, địa chỉ đổi,
        trùng thời điểm, máy không có thời điểm) nó cho đúng chi nhánh mà các dòng của group_by_person cho."""
        import ipaddress
        import random
        rng = random.Random(3)
        nets = [ipaddress.ip_network("10.%d.0.0/16" % i) for i in range(4)]
        names = ["p%02d@example.com" % i for i in range(12)] + ["Person %02d" % i for i in range(12)]
        for _ in range(40):
            branches = [{"id": "b%d" % b, "people": set(rng.sample(names, rng.randint(0, 4))), "networks": rng.sample(nets, rng.randint(0, 2))}
                        for b in range(rng.randint(1, 4))]
            devs = []
            for i in range(rng.randint(1, 60)):
                p = rng.randrange(12)
                m = {"v": 1, "device": "device-r%03d" % i, "account": rng.choice(["p%02d@example.com" % p, ""]), "name": "Person %02d" % p,
                     "ip": rng.choice(["", "10.%d.1.%d" % (rng.randrange(5), rng.randrange(9))]), "updatedAt": rng.choice([1000, 1000, 2000, 3000])}
                if rng.random() < 0.05:
                    m.pop("updatedAt")
                devs.append(m)
            want = {r["key"]: views.branch_of(r, branches) for r in devices.group_by_person(devs, time.time())}
            got = {key: views.branch_of(r, branches) for key, r in devices.branch_facts(devs).items()}
            self.assertEqual(got, want)

    def test_a_batch_is_written_with_the_known_name_once(self):
        self.enrol("device-rcva")
        h = str(int(time.time() // 3600))
        batch = {"src": "go-1", "boot": "b1", "seq": 1, "rows": [self.row("device-rcva", {"ledger": {h: {"usdMicro": 5}}}, name="Someone Else")]}
        status, answer = self.internal("POST", "/internal/rows", batch)
        self.assertEqual((status, answer), (200, {"ok": True, "seq": 1, "needFull": [], "unknown": [], "incomplete": [], "bad": []}))
        # the receiver takes only sends made with the computer's own key: from now on the shared key no longer sends for it
        # bộ nhận chỉ nhận lần gửi bằng khoá riêng: từ giờ khoá chung không gửi thay máy này được nữa
        self.assertEqual(devicekeys.DEVICE_KEYS.state("device-rcva", time.time()), "active")
        m = devices.read_device("device-rcva")
        self.assertEqual((m["name"], m["account"], m["ip"]), ("rae", "device-rcva@example.com", "203.0.113.9"))
        self.assertEqual(m["ledger"][h]["usdMicro"], 5)
        # the enrolment came from 127.0.0.1 maybe in the same millisecond, so the order of the two is not fixed
        # lần ghi danh tới từ 127.0.0.1 có thể trong cùng một mili giây, nên thứ tự của hai địa chỉ không cố định
        self.assertIn("203.0.113.9", [e["ip"] for e in m["ipHistory"]])
        # the same batch again is answered and not written twice; a later one is written
        # cùng lô gửi lại được trả lời và không ghi hai lần; lô sau thì được ghi
        batch["rows"][0]["v"]["hours"]["ledger"][h]["usdMicro"] = 99
        self.assertEqual(self.internal("POST", "/internal/rows", batch)[1]["seq"], 1)
        self.assertEqual(devices.read_device("device-rcva")["ledger"][h]["usdMicro"], 5)
        batch["seq"] = 2
        self.internal("POST", "/internal/rows", batch)
        self.assertEqual(devices.read_device("device-rcva")["ledger"][h]["usdMicro"], 99)

    def test_a_row_older_than_a_send_written_here_is_left_out(self):
        """The computer sent a newer book straight here while its row waited in a batch of the receiver: the row, taken by the receiver
        before that send, comes after and must not put the book back. Times are this server's clock, never the computer's.
        Máy đã gửi một sổ mới hơn thẳng tới đây trong lúc dòng của nó chờ trong một lô của bộ nhận: dòng đó, bộ nhận nhận trước lần gửi
        kia, tới sau và không được kéo sổ lùi lại. Thời điểm theo đồng hồ của máy chủ này, không bao giờ theo đồng hồ của máy."""
        key = self.enrol("device-rcva")
        h = str(int(time.time() // 3600))
        older = self.row("device-rcva", {"ledger": {h: {"usdMicro": 5}}}, kind="full")
        time.sleep(0.01)
        status, _ = self.call("POST", "/ingest", {"v": 2, "device": "device-rcva", "updatedAt": int(time.time() * 1000), "full": True,
                                                  "hours": {"ledger": {h: {"usdMicro": 9}}}}, Authorization="Bearer " + key)
        self.assertEqual(status, 200)
        self.assertEqual(devices.read_device("device-rcva")["ledger"][h]["usdMicro"], 9)
        status, answer = self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b-stale", "seq": 1, "rows": [older]})
        self.assertEqual((status, answer["bad"], answer["needFull"]), (200, [], []))
        self.assertEqual(devices.read_device("device-rcva")["ledger"][h]["usdMicro"], 9)
        # a row the receiver took after that send is written as usual
        # một dòng bộ nhận nhận sau lần gửi đó được ghi như thường
        time.sleep(0.01)
        later = self.row("device-rcva", {"ledger": {h: {"usdMicro": 12}}}, kind="full")
        self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b-stale", "seq": 2, "rows": [later]})
        self.assertEqual(devices.read_device("device-rcva")["ledger"][h]["usdMicro"], 12)

    def test_a_row_that_fails_is_left_out_alone(self):
        self.enrol("device-rcva")
        self.enrol("device-rcvb")
        h = str(int(time.time() // 3600))
        real = receiver.save_ingest

        def broken(d, *args, **kw):
            if d["device"] == "device-rcva":
                real(d, *args, **kw)
                raise RuntimeError("disk said no")
            return real(d, *args, **kw)
        receiver.save_ingest = broken
        try:
            status, answer = self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b4", "seq": 1, "rows": [
                self.row("device-rcva", {"ledger": {h: {"usdMicro": 3}}}), self.row("device-rcvb", {"ledger": {h: {"usdMicro": 4}}})]})
        finally:
            receiver.save_ingest = real
        self.assertEqual((status, answer["bad"]), (200, ["device-rcva"]))
        # the failed row is taken back in the table and in memory; the other row is written
        # dòng hỏng được rút lại cả trong bảng lẫn trong bộ nhớ; dòng kia được ghi
        self.assertEqual(devices.read_device("device-rcva")["ledger"], {})
        self.assertEqual(devices.read_device("device-rcvb")["ledger"][h]["usdMicro"], 4)
        devices.DEVICES.forget()
        self.assertEqual(devices.read_device("device-rcva")["ledger"], {})

    def test_a_person_without_a_name_is_named_incomplete(self):
        status, answer = self.call("POST", "/ingest", {"v": 1, "device": "device-rcvc", "account": "rcvc@example.com", "updatedAt": int(time.time() * 1000)},
                                   Authorization="Bearer " + settings.INGEST_KEY)
        self.assertEqual(status, 200)
        answer = self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b5", "seq": 1, "rows": [self.row("device-rcvc", {})]})[1]
        self.assertEqual(answer["incomplete"], ["device-rcvc"])

    def test_a_name_filled_in_later_gets_a_new_key(self):
        now = int(time.time() * 1000)
        status, answer = self.call("POST", "/ingest", {"v": 1, "device": "device-rcvc", "account": "rcvc@example.com", "updatedAt": now},
                                   Authorization="Bearer " + settings.INGEST_KEY)
        first = answer["deviceKey"]
        status, answer = self.call("POST", "/ingest", {"v": 1, "device": "device-rcvc", "account": "rcvc@example.com", "updatedAt": now + 1},
                                   Authorization="Bearer " + first)
        self.assertNotIn("deviceKey", answer)
        status, answer = self.call("POST", "/ingest", {"v": 1, "device": "device-rcvc", "account": "rcvc@example.com", "name": "Cee", "updatedAt": now + 2},
                                   Authorization="Bearer " + first)
        self.assertEqual(status, 200)
        self.assertNotEqual(answer["deviceKey"].split(".")[3], first.split(".")[3])

    def test_rows_for_unknown_or_bookless_computers(self):
        h = str(int(time.time() // 3600))
        status, answer = self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b2", "seq": 1,
                                                                  "rows": [self.row("device-rcvb", {"ledger": {h: {"usdMicro": 1}}})]})
        self.assertEqual((status, answer["needFull"], answer["unknown"]), (200, [], ["device-rcvb"]))
        self.assertIsNone(devices.read_device("device-rcvb"))
        self.enrol("device-rcvb")
        drop_rows(["device-rcvb"])
        status, answer = self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b2", "seq": 2,
                                                                  "rows": [self.row("device-rcvb", {"ledger": {h: {"usdMicro": 1}}})]})
        self.assertEqual(answer["needFull"], ["device-rcvb"])
        self.assertEqual(self.internal("POST", "/internal/rows", {"rows": []})[0], 400)

    def test_a_send_passed_on_keeps_the_real_address_and_the_computers_key(self):
        key = self.enrol("device-rcvc")
        packet = {"v": 2, "device": "device-rcvc", "updatedAt": int(time.time() * 1000), "full": True, "hours": {}}
        status, _ = self.internal("POST", "/internal/ingest", packet, **{"X-Receiver-Client-Ip": "198.51.100.7", "X-Receiver-Authorization": "Bearer " + key})
        self.assertEqual(status, 200)
        self.assertEqual(devices.read_device("device-rcvc")["ip"], "198.51.100.7")
        # the computer has a key of its own now: the shared key passed on is refused as on /ingest
        # máy giờ đã có khoá riêng: khoá chung được chuyển tới bị từ chối như ở /ingest
        status, _ = self.internal("POST", "/internal/ingest", packet, **{"X-Receiver-Client-Ip": "198.51.100.7",
                                                                       "X-Receiver-Authorization": "Bearer " + settings.INGEST_KEY})
        self.assertEqual(status, 401)
        self.assertEqual(self.internal("POST", "/internal/ingest", packet, **{"X-Receiver-Authorization": "Bearer " + key})[0], 400)

    def test_the_policy_lists_computers_written_here(self):
        start = self.internal("GET", "/internal/policy?since=0&boot=" + devices.BOOT_ID)[1]
        self.assertIs(start["reset"], False)
        self.enrol("device-rcva")
        policy = self.internal("GET", "/internal/policy?since=%d&boot=%s" % (start["seq"], devices.BOOT_ID))[1]
        self.assertEqual(policy["written"], ["device-rcva"])
        self.assertEqual(policy["boot"], devices.BOOT_ID)
        self.assertIs(self.internal("GET", "/internal/policy?since=0&boot=another")[1]["reset"], True)
        devicekeys.DEVICE_KEYS.revoke("device-rcva", time.time())
        self.assertIn("device-rcva", self.internal("GET", "/internal/policy")[1]["revoked"])

    def test_the_books_come_a_page_at_a_time(self):
        for device in DEVICES:
            self.enrol(device)
        seen, after = [], ""
        while True:
            page = self.internal("GET", "/internal/devices?limit=1&after=" + after)[1]
            seen += [m["device"] for m in page["devices"]]
            if not page["next"]:
                break
            after = page["next"]
        self.assertTrue(set(DEVICES) <= set(seen))
        self.assertEqual(seen, sorted(seen))
        one = self.internal("GET", "/internal/devices?device=device-rcvb")[1]["devices"]
        self.assertEqual([sorted(one[0])], [sorted(["device", "updatedAt", "openSessions", "working", "waiting", "delegating", "ledger", "tasks", "stamps"])])

    def ledger_of(self, device: str) -> dict:
        return {h: v["usdMicro"] for h, v in receiver.book_for_receiver(device)["ledger"].items()}

    def test_an_older_row_of_the_receiver_never_writes_over_a_newer_send(self):
        # the computer sent straight here after the receiver took an older row of it, then this server started again: nothing kept in
        # memory, but the hour keeps the time of the send that wrote it (board/order.py), so the older row leaves it; C48 and C50 lost
        # money this way
        # máy gửi thẳng tới đây sau khi bộ nhận đã nhận một dòng cũ hơn của nó, rồi máy chủ này khởi động lại: không còn gì trong bộ nhớ,
        # nhưng giờ giữ thời điểm của lần gửi đã ghi nó (board/order.py), nên dòng cũ hơn để nguyên giờ đó; C48 và C50 mất tiền theo cách này
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h, other = str(t // 3_600_000), str(t // 3_600_000 - 1)
        status, _ = self.call("POST", "/ingest", {"v": 2, "device": "device-rcva", "updatedAt": t, "hours": {"ledger": {h: {"usdMicro": 200}}}},
                              Authorization="Bearer " + key)
        self.assertEqual(status, 200)
        devices.DEVICES.forget()
        row = self.row("device-rcva", {"ledger": {h: {"usdMicro": 100}, other: {"usdMicro": 5}}})
        row["at"] = row["v"]["updatedAt"] = t - 30_000
        self.assertEqual(self.internal("POST", "/internal/rows", {"src": "go-order", "boot": "b1", "seq": 1, "rows": [row]})[0], 200)
        self.assertEqual(self.ledger_of("device-rcva"), {h: 200, other: 5})

    def test_a_batch_sent_again_gets_the_answer_it_had(self):
        # its answer was lost (the receiver gave up waiting): sent again, it is not written twice and says again who needs a whole book
        # câu trả lời của nó bị mất (bộ nhận thôi chờ): gửi lại, nó không bị ghi hai lần và vẫn nói lại máy nào cần cả sổ
        self.enrol("device-rcva")
        drop_rows(["device-rcva"])
        batch = {"src": "go-again", "boot": "b1", "seq": 1, "rows": [self.row("device-rcva", {"ledger": {}})]}
        first = self.internal("POST", "/internal/rows", batch)[1]
        self.assertEqual(first["needFull"], ["device-rcva"])
        self.assertEqual(self.internal("POST", "/internal/rows", batch)[1], first)

    def test_a_send_left_waiting_never_writes_over_a_newer_one(self):
        # a send the computer gave up waiting for, taken here 90 seconds later, after a newer one: past the window of 60 seconds too
        # lần gửi máy đã thôi chờ, được nhận ở đây 90 giây sau, sau một lần gửi mới hơn: vượt cả cửa sổ 60 giây
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h = str(t // 3_600_000)
        for at, usd in ((t, 200), (t - 90_000, 100)):
            status, _ = self.call("POST", "/ingest", {"v": 2, "device": "device-rcva", "updatedAt": at, "hours": {"ledger": {h: {"usdMicro": usd}}}},
                                  Authorization="Bearer " + key)
            self.assertEqual(status, 200)
        self.assertEqual(self.ledger_of("device-rcva"), {h: 200})

    def straight(self, key: str, device: str, at: int, ledger: dict) -> None:
        status, _ = self.call("POST", "/ingest", {"v": 2, "device": device, "updatedAt": at, "hours": {"ledger": ledger}}, Authorization="Bearer " + key)
        self.assertEqual(status, 200)

    def test_an_hour_of_an_older_send_in_a_merged_row_never_writes_over_a_straight_send(self):
        # the receiver put two sends of the computer in one row (proto 3): an hour of the older one comes with its own time, so a send
        # straight here between the two keeps that hour, and the row's newer hour is written
        # bộ nhận gộp hai lần gửi của máy thành một dòng (proto 3): giờ của lần cũ hơn đi kèm thời điểm của chính nó, nên một lần gửi thẳng
        # tới đây ở giữa hai lần đó giữ được giờ ấy, và giờ mới hơn của dòng vẫn được ghi
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h, other = str(t // 3_600_000), str(t // 3_600_000 - 1)
        self.straight(key, "device-rcva", t + 10_000, {h: {"usdMicro": 300}})
        row = self.row("device-rcva", {"ledger": {h: {"usdMicro": 100}, other: {"usdMicro": 7}}})
        row["at"] = row["v"]["updatedAt"] = t + 20_000
        row["stamp"], row["stamps"] = t + 20_000, {"ledger": {h: t + 5_000, other: t + 20_000}}
        self.assertEqual(self.internal("POST", "/internal/rows", {"src": "go-merged", "boot": "b1", "seq": 1, "rows": [row]})[0], 200)
        self.assertEqual(self.ledger_of("device-rcva"), {h: 300, other: 7})

    def test_the_admin_page_counts_the_hours_left_as_older(self):
        # an hour of an older send left as it was counts once, with its computer, and the Admin page reads both
        # một giờ của lần gửi cũ hơn được giữ nguyên thì đếm một lần, cùng máy của nó, và trang Quản trị đọc cả hai
        from board import order
        order.reset()
        self.assertEqual(views.admin_data(time.time(), "", "")["olderHours"], {"hours": 0, "computers": 0})
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h = str(t // 3_600_000)
        self.straight(key, "device-rcva", t + 10_000, {h: {"usdMicro": 300}})
        self.straight(key, "device-rcva", t - 90_000, {h: {"usdMicro": 100}})
        self.straight(key, "device-rcva", t - 80_000, {h: {"usdMicro": 200}})
        self.assertEqual(views.admin_data(time.time(), "", "")["olderHours"], {"hours": 2, "computers": 1})

    def test_a_whole_book_in_a_row_keeps_what_its_stamps_say(self):
        # a whole book with a newer hour put on it (proto 3): an hour gone at a time older than a straight send stays, one gone after it
        # leaves, and the book's own hours keep the book's time
        # một sổ đủ có giờ mới hơn đặt lên (proto 3): giờ vắng ở thời điểm cũ hơn một lần gửi thẳng thì ở lại, giờ vắng sau lần đó thì đi,
        # và các giờ của chính sổ giữ thời điểm của sổ
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h0, h1, h2 = (str(t // 3_600_000 - i) for i in range(3))
        self.straight(key, "device-rcva", t + 10_000, {h1: {"usdMicro": 11}, h2: {"usdMicro": 22}})
        row = self.row("device-rcva", {"ledger": {h0: {"usdMicro": 5}}}, kind="full")
        row["at"] = row["v"]["updatedAt"] = t + 20_000
        row["stamp"], row["stamps"] = t + 5_000, {"ledger": {h0: t + 20_000, h2: t + 20_000}}
        self.assertEqual(self.internal("POST", "/internal/rows", {"src": "go-whole", "boot": "b1", "seq": 1, "rows": [row]})[0], 200)
        self.assertEqual(self.ledger_of("device-rcva"), {h0: 5, h1: 11})
        self.assertEqual(receiver.book_for_receiver("device-rcva")["stamps"]["ledger"], {h0: t + 20_000, h1: t + 10_000})

    def test_seq_orders_the_sends_of_a_computer_whose_clock_went_back(self):
        # the plugin numbers its sends (seq): one made after the clock went back two minutes is still the newer one, and so is one made
        # after it went back another 30 seconds, which the window of a minute (REORDER_WINDOW_MS) would have dropped by updatedAt. seq is
        # kept in the record for that window but, like updatedAt, never makes the row of the computer written again by itself
        # plugin đánh số các lần gửi (seq): lần gửi sau khi đồng hồ lùi hai phút vẫn là lần mới hơn, lần gửi sau khi lùi thêm 30 giây cũng
        # vậy, dù cửa sổ một phút (REORDER_WINDOW_MS) mà so theo updatedAt thì đã bỏ nó. seq được giữ trong bản ghi cho cửa sổ đó nhưng,
        # như updatedAt, tự nó không bao giờ làm dòng của máy phải ghi lại
        key, t = self.enrol("device-rcva"), int(time.time() * 1000)
        h = str(t // 3_600_000 - 1)
        for at, seq, usd in ((t, t, 100), (t - 120_000, t + 1, 200), (t - 150_000, t + 2, 300)):
            status, _ = self.call("POST", "/ingest", {"v": 2, "device": "device-rcva", "updatedAt": at, "seq": seq,
                                                      "hours": {"ledger": {h: {"usdMicro": usd}}}}, Authorization="Bearer " + key)
            self.assertEqual(status, 200)
        self.assertEqual(self.ledger_of("device-rcva"), {h: 300})
        self.assertEqual(receiver.book_for_receiver("device-rcva")["seq"], t + 2)
        m = devices.DEVICES.get("device-rcva")
        self.assertEqual(devices._steady(dict(m, seq=1)), devices._steady(dict(m, seq=2)))
        now = time.time()
        self.assertEqual(devices.clean_payload({"v": 1, "device": "device-rcva", "updatedAt": 5, "seq": 9}, now)["seq"], 9)
        self.assertNotIn("seq", devices.clean_payload({"v": 1, "device": "device-rcva", "updatedAt": 5, "seq": True}, now))

    def test_no_batch_is_written_between_two_books_of_a_page(self):
        # the lock of the devices is held for the whole page, so a batch (apply_rows holds it too) waits for the page to end
        # khoá các máy được giữ cả trang, nên một lô (apply_rows cũng giữ nó) phải chờ trang xong
        for device in DEVICES:
            self.enrol(device)
        got, one = [], receiver.book_for_receiver

        def book(device, whole=False):
            other = threading.Thread(target=lambda: got.append(devices.DEVICES.lock.acquire(timeout=0.5) and devices.DEVICES.lock.release() is None))
            other.start()
            other.join()
            return one(device, whole)

        receiver.book_for_receiver = book
        try:
            page = receiver.devices_page("", 1000)
        finally:
            receiver.book_for_receiver = one
        self.assertTrue(set(DEVICES) <= {m["device"] for m in page["devices"]})
        self.assertTrue(got and not any(got), got)

    def test_the_record_carries_the_state_of_the_board(self):
        # what the receiver's live numbers need of a computer besides its hours (STATE_FIELDS), and nothing that tells who it is
        # thứ số trực tiếp của bộ nhận cần về một máy ngoài các giờ (STATE_FIELDS), và không có gì cho biết đó là ai
        self.enrol("device-rcva")
        row = self.row("device-rcva", {}, "full", waiting=1, delegating={"gemma": 2}, tools={"codex": {"openSessions": 1, "working": 1}})
        self.internal("POST", "/internal/rows", {"src": "go-state", "boot": "b1", "seq": 1, "rows": [row]})
        one = self.internal("GET", "/internal/devices?device=device-rcva")[1]["devices"][0]
        self.assertEqual({k: one[k] for k in receiver.STATE_FIELDS},
                         {"openSessions": 1, "working": 1, "waiting": 0, "delegating": {"gemma": 2}, "tools": {"codex": {"openSessions": 1, "working": 1, "waiting": 0}}})
        self.assertFalse({"name", "account", "ip", "lanIp", "ipHistory"} & set(one))

    def test_the_third_check_counts_a_difference(self):
        self.enrol("device-rcva")
        h = str(int(time.time() // 3600))
        row = self.row("device-rcva", {"ledger": {h: {"usdMicro": 5}}})
        row["raw"] = dict(row["v"], hours={"ledger": {h: {"usdMicro": 6}}})
        before = receiver.POLICY.mismatches
        self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b3", "seq": 1, "rows": [row]})
        self.assertEqual(receiver.POLICY.mismatches, before + 1)
        row["raw"] = row["v"]
        self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b3", "seq": 2, "rows": [row]})
        self.assertEqual(receiver.POLICY.mismatches, before + 1)

    def test_a_check_row_is_compared_and_never_written(self):
        self.enrol("device-rcva")
        h = str(int(time.time() // 3600))
        row = dict(self.row("device-rcva", {"ledger": {h: {"usdMicro": 8}}}), kind="check")
        row["raw"] = dict(row["v"], hours={"ledger": {h: {"usdMicro": 9}}})
        before, checked = receiver.POLICY.mismatches, receiver.POLICY.checked
        self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b6", "seq": 1, "rows": [row]})
        self.assertEqual((receiver.POLICY.checked, receiver.POLICY.mismatches), (checked + 1, before + 1))
        self.assertNotIn(h, devices.read_book("device-rcva")["ledger"])
        self.assertEqual(self.internal("GET", "/internal/policy")[1]["proto"], receiver.PROTO)

    def test_the_receiver_loads_only_the_hours_of_today(self):
        self.enrol("device-rcva")
        now = time.time()
        first = devices.today_first_hour(now)
        sent = {"ledger": {str(first - 30): {"usdMicro": 1}, str(first): {"usdMicro": 2}, str(int(now // 3600)): {"usdMicro": 3}}}
        self.internal("POST", "/internal/rows", {"src": "go-1", "boot": "b7", "seq": 1, "rows": [self.row("device-rcva", sent)]})
        today = self.internal("GET", "/internal/devices?device=device-rcva")[1]["devices"][0]["ledger"]
        self.assertEqual(sorted(today), sorted({str(first), str(int(now // 3600))}))
        whole = self.internal("GET", "/internal/devices?device=device-rcva&whole=1")[1]["devices"][0]["ledger"]
        self.assertIn(str(first - 30), whole)


class NoWaitingForTheInternalCode(unittest.TestCase):
    """Once read, the receiver's internal code is given without waiting for the lock of the keys, and the interpreter switches threads
    every SWITCH_MS (0.5 ms by default): both kept the receiver's batches from queuing behind other requests (docs/RECEIVER.md, section 7).
    Đã đọc rồi thì mã nội bộ của bộ nhận được trả mà không chờ khoá của bộ khoá, và trình thông dịch đổi luồng mỗi SWITCH_MS (mặc định
    0,5 ms): cả hai giữ cho các lô của bộ nhận không xếp hàng sau các yêu cầu khác."""

    def test_the_code_is_given_while_the_lock_is_held(self):
        keys = devicekeys.DEVICE_KEYS
        code = keys.internal_code()
        got = []
        with keys.lock:
            t = threading.Thread(target=lambda: got.append(keys.internal_code()))
            t.start()
            t.join(2)
        self.assertEqual(got, [code])
        self.assertTrue(code)

    def test_the_computers_of_a_batch_are_noted_in_one_transaction(self):
        """note_used_many writes the device_keys rows of new computers in one transaction, and leaves alone those already noted.
        note_used_many ghi các dòng device_keys của máy mới trong một giao dịch, và để yên các máy đã ghi nhận."""
        keys, database = devicekeys.DEVICE_KEYS, db.data_db()
        names = ["device-many%d" % i for i in range(5)]
        keys.note_used(names[0], None, time.time())
        begins = []
        database.conn.set_trace_callback(lambda sql: begins.append(sql) if sql.startswith("BEGIN") else None)
        try:
            keys.note_used_many(names + names[:2], None, time.time())
            self.assertEqual(len(begins), 1)
            keys.note_used_many(names, None, time.time())
            self.assertEqual(len(begins), 1)
        finally:
            database.conn.set_trace_callback(None)
        with database.lock:
            got = {r[0] for r in database.conn.execute("SELECT device FROM device_keys WHERE device LIKE 'device-many%'")}
        self.assertEqual(got, set(names))

    def test_the_switch_interval(self):
        self.assertEqual(settings.SWITCH_MS, 0.5)


class IngestRoute(unittest.TestCase):
    """Where the computers send (docs/RECEIVER.md, section 4): told only with their own key, only when chosen, never by default. It
    borrows the server and the helpers of Receiver without running its tests again.
    Các máy gửi tới đâu (docs/RECEIVER.vi.md, mục 4): chỉ báo khi gửi bằng khoá riêng, chỉ khi được chọn, mặc định không báo. Lớp này
    mượn máy chủ và các hàm phụ của Receiver mà không chạy lại các test của nó."""

    URLS = ["https://ingest.example.com", "https://ingest2.example.com"]
    setUpClass = Receiver.__dict__["setUpClass"]
    tearDownClass = Receiver.__dict__["tearDownClass"]
    call = Receiver.call
    enrol = Receiver.enrol

    def setUp(self):
        Receiver.setUp(self)
        self.was = (settings.RECEIVER_INGEST_URLS, settings.RECEIVER_INGEST_DEVICES, settings.RECEIVER_INGEST_PERCENT, settings.TRUST_PROXY,
                    settings.OFFICE_NETS)
        # no rule of the office here, unless a test sets one
        # ở đây không có luật văn phòng, trừ khi một test đặt
        settings.TRUST_PROXY, settings.OFFICE_NETS = False, settings.parse_office_nets("")

    def tearDown(self):
        (settings.RECEIVER_INGEST_URLS, settings.RECEIVER_INGEST_DEVICES, settings.RECEIVER_INGEST_PERCENT, settings.TRUST_PROXY,
         settings.OFFICE_NETS) = self.was
        Receiver.tearDown(self)

    def send(self, device: str, key: str, v: int = 2):
        body = {"v": v, "device": device, "name": "Rae", "account": device + "@example.com", "updatedAt": int(time.time() * 1000)}
        if v == 2:
            body.update({"full": True, "hours": {}})
        return self.call("POST", "/ingest", body, Authorization="Bearer " + key)

    def test_nothing_is_said_by_default(self):
        key = self.enrol(DEVICES[0])
        status, answer = self.send(DEVICES[0], key)
        self.assertEqual(status, 200)
        self.assertNotIn("ingestUrls", answer)
        self.assertNotIn("ingestTtlMs", answer)
        self.assertEqual(self.call("GET", "/ingest/route", Authorization="Bearer " + key), (200, {"ingestUrls": [], "ingestTtlMs": 3600000}))

    def test_a_chosen_computer_is_told_with_its_own_key_only(self):
        settings.RECEIVER_INGEST_URLS, settings.RECEIVER_INGEST_DEVICES = list(self.URLS), frozenset({DEVICES[0]})
        # the first send, with the shared key, gets its own key and no address: the receiver never takes the shared key
        # lần gửi đầu, bằng khoá chung, nhận khoá riêng mà không nhận địa chỉ: bộ nhận không bao giờ nhận khoá chung
        status, answer = self.call("POST", "/ingest", {"v": 1, "device": DEVICES[0], "name": "Rae", "account": DEVICES[0] + "@example.com",
                                                      "updatedAt": int(time.time() * 1000)}, Authorization="Bearer " + settings.INGEST_KEY)
        self.assertEqual(status, 200)
        self.assertNotIn("ingestUrls", answer)
        key = answer["deviceKey"]
        status, answer = self.send(DEVICES[0], key)
        self.assertEqual((status, answer["ingestUrls"], answer["ingestTtlMs"]), (200, self.URLS, 3600000))
        self.assertEqual(self.call("GET", "/ingest/route?v=2", Authorization="Bearer " + key), (200, {"ingestUrls": self.URLS, "ingestTtlMs": 3600000}))
        # a plugin that sends v: 1 (0.50.13) is never told: its whole book of 8 days in every send is too heavy for the receiver
        # plugin gửi v: 1 (0.50.13) không bao giờ được báo: cả sổ 8 ngày trong mỗi lần gửi quá nặng cho bộ nhận
        status, answer = self.send(DEVICES[0], key, v=1)
        self.assertEqual(status, 200)
        self.assertNotIn("ingestUrls", answer)
        self.assertEqual(self.call("GET", "/ingest/route", Authorization="Bearer " + key)[1]["ingestUrls"], [])
        self.assertEqual(self.call("GET", "/ingest/route", Authorization="Bearer " + settings.INGEST_KEY)[0], 403)
        self.assertEqual(self.call("GET", "/ingest/route")[0], 401)
        # another computer, not on the list, is not told
        # máy khác, không có trong danh sách, không được báo
        other = self.enrol(DEVICES[1])
        self.assertNotIn("ingestUrls", self.send(DEVICES[1], other)[1])
        # the receiver turned off: nobody is told, and the route sends everyone back here
        # tắt bộ nhận: không ai được báo, và đường tuyến đưa mọi máy về lại đây
        settings.RECEIVER_ENABLED = False
        self.assertNotIn("ingestUrls", self.send(DEVICES[0], key)[1])
        self.assertEqual(self.call("GET", "/ingest/route?v=2", Authorization="Bearer " + key)[1]["ingestUrls"], [])

    def test_a_computer_kept_to_the_office_stays_here(self):
        # the receiver does not know which computers may send only from the office: where that rule can apply (OFFICE_NETS, or Caddy in
        # front that marks a send from outside), only a computer an admin let send from any network goes to it
        # bộ nhận không biết máy nào chỉ được gửi từ văn phòng: ở nơi luật đó có thể áp (OFFICE_NETS, hay Caddy đứng trước đánh dấu lần
        # gửi từ bên ngoài), chỉ máy quản trị đã cho gửi từ mọi mạng mới đi tới nó
        settings.RECEIVER_INGEST_URLS, settings.RECEIVER_INGEST_DEVICES = list(self.URLS), frozenset({DEVICES[0]})
        key = self.enrol(DEVICES[0])
        self.assertIn("ingestUrls", self.send(DEVICES[0], key)[1])
        settings.TRUST_PROXY = True
        self.assertNotIn("ingestUrls", self.send(DEVICES[0], key)[1])
        self.assertEqual(self.call("GET", "/ingest/route?v=2", Authorization="Bearer " + key)[1]["ingestUrls"], [])
        self.assertTrue(devicekeys.DEVICE_KEYS.set_roaming(DEVICES[0], True, "test", time.time()))
        self.assertEqual(self.send(DEVICES[0], key)[1]["ingestUrls"], self.URLS)
        self.assertTrue(devicekeys.DEVICE_KEYS.set_roaming(DEVICES[0], False, "test", time.time()))
        settings.TRUST_PROXY, settings.OFFICE_NETS = False, settings.parse_office_nets("10.0.0.0/8")
        self.assertIsNone(receiver.ingest_route(DEVICES[0]))

    def test_the_percentage_is_stable_and_only_adds(self):
        settings.RECEIVER_INGEST_URLS = list(self.URLS)
        ids = ["device-%05d" % i for i in range(2000)]
        chosen = {}
        for percent in (0, 5, 25, 100):
            settings.RECEIVER_INGEST_PERCENT = float(percent)
            chosen[percent] = {d for d in ids if receiver.ingest_route(d)}
            self.assertEqual(chosen[percent], {d for d in ids if receiver.ingest_route(d)})
        self.assertEqual(len(chosen[0]), 0)
        self.assertEqual(len(chosen[100]), len(ids))
        self.assertTrue(chosen[0] <= chosen[5] <= chosen[25] <= chosen[100])
        self.assertTrue(50 <= len(chosen[5]) <= 150, len(chosen[5]))

    def test_the_addresses_given(self):
        self.assertEqual(settings._https_origins("https://a.example.com, http://b.example.com, https://c.example.com/path, https://a.example.com,"
                                                 " https://d.example.com:8443, https://e.example.com, https://f.example.com, https://g.example.com"),
                         ["https://a.example.com", "https://d.example.com:8443", "https://e.example.com", "https://f.example.com"])
        self.assertEqual(settings._https_origins(""), [])


class SendPaceTest(unittest.TestCase):
    """The gap told on /ingest widens with the computers that sent in the last minute, past INGEST_SENDS_PER_SECOND.
    Khoảng cách dặn trên /ingest giãn theo số máy đã gửi trong phút vừa qua, khi quá INGEST_SENDS_PER_SECOND."""

    def setUp(self):
        self.was = settings.INGEST_SENDS_PER_SECOND

    def tearDown(self):
        settings.INGEST_SENDS_PER_SECOND = self.was

    def test_the_gap_widens_with_the_computers(self):
        settings.INGEST_SENDS_PER_SECOND = 100.0
        pace, t = devices.SendPace(), 1000.0
        gaps = [pace.note("device-%05d" % i, t) for i in range(1000)]
        # up to 200 computers fit in 100 sends a second at 2 seconds; 1,000 need 10 seconds
        # tới 200 máy vừa 100 lần gửi mỗi giây với 2 giây; 1.000 máy cần 10 giây
        self.assertEqual(gaps[0], settings.INGEST_MIN_GAP_MS)
        self.assertEqual(gaps[199], settings.INGEST_MIN_GAP_MS)
        self.assertEqual(gaps[-1], 10_000)
        # the same computer again does not count twice; a minute later the quiet ones are forgotten
        # cùng một máy gửi lại không đếm hai lần; một phút sau các máy đã im bị quên
        self.assertEqual(pace.note("device-00000", t + 1), 10_000)
        self.assertEqual(pace.note("device-00000", t + 61), settings.INGEST_MIN_GAP_MS)
        # never past 2 minutes, and 0 turns it off
        # không bao giờ quá 2 phút, và 0 thì tắt
        settings.INGEST_SENDS_PER_SECOND = 0.001
        self.assertEqual(pace.note("device-x", t + 62), devices.SendPace.MAX_GAP_MS)
        settings.INGEST_SENDS_PER_SECOND = 0.0
        self.assertEqual(pace.note("device-y", t + 62), settings.INGEST_MIN_GAP_MS)


class TurningTheSecret(unittest.TestCase):
    """Each test puts the secrets and the computers' keys back as they were, so the other tests keep their keys.
    Mỗi bài test trả bí mật và khoá của các máy về như cũ, để các bài test khác giữ được khoá của chúng."""

    def setUp(self):
        self.meta = {k: db.keys_db().get_meta(k) for k in (devicekeys.SECRETS_KEY, devicekeys.RENEW_BEFORE_KEY, devicekeys.TICKET_KEY)}
        self.rows = db.data_db().rows("SELECT device, iat FROM device_keys")

    def tearDown(self):
        devicekeys.DEVICE_KEYS.forget("device-rot")
        with db.keys_db().tx() as c:
            for k, v in self.meta.items():
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, v))
        with db.data_db().tx() as c:
            for device, iat in self.rows:
                c.execute("UPDATE device_keys SET iat = ? WHERE device = ?", (iat, device))
        devicekeys.DEVICE_KEYS.reload()

    def test_rotate_renews_every_key_and_drop_old_lets_them_enrol_again(self):
        keys, now = devicekeys.DEVICE_KEYS, time.time()
        key = keys.issue("device-rot", "rot@example.com", "Rot", now)
        claims, _ = keys.check(key, now)
        self.assertFalse(keys.needs_renewal(claims, now))
        # the computer sends with it, so it has a key it must use
        # máy gửi bằng khoá đó, nên nó có khoá phải dùng
        keys.note_used("device-rot", claims["iat"], now)
        ticket_kid = keys.ticket_secret()[0]
        kid = keys.rotate(now + 1)
        self.assertEqual(keys.receiver_secrets(now)[0]["kid"], kid)
        # the tickets' secret, in the same file, is turned with it
        # bí mật của vé, ở cùng file, được xoay cùng
        self.assertNotEqual(keys.ticket_secret()[0], ticket_kid)
        self.assertEqual([e["kid"] for e in keys.receiver_secrets(now) if e["alg"] == "ticket"], [keys.ticket_secret()[0]])
        # the old key still checks, and is renewed at its next send
        # khoá cũ vẫn kiểm được, và được cấp mới ở lần gửi sau
        claims, _ = keys.check(key, now)
        self.assertTrue(claims and keys.needs_renewal(claims, now))
        self.assertNotEqual(keys.issue("device-rot", "rot@example.com", "Rot", now).split(".")[1], claims["kid"])
        keys.rotate(now + 1, drop_old=True)
        self.assertEqual(keys.check(key, now + 1), (None, "unknown signing key"))
        self.assertEqual(keys.state("device-rot", now + 1), "expired")
        self.assertEqual(len([e for e in keys.receiver_secrets(now + 1) if e["alg"] == "HS256"]), 1)

    def test_an_old_secret_goes_once_its_successor_is_older_than_a_key_lives(self):
        keys, now = devicekeys.DEVICE_KEYS, time.time()
        keys.rotate(now)
        later = now + devicekeys.KEY_DAYS * 86400 + 60
        self.assertEqual(len([e for e in keys.receiver_secrets(later) if e["alg"] == "HS256"]), 1)
        self.assertGreaterEqual(len([e for e in keys.receiver_secrets(now) if e["alg"] == "HS256"]), 2)


class LiveTickets(unittest.TestCase):
    """The tickets of the board's live feed: given only to a logged-in board, for a scope that exists, with the feed set up; signed with
    a secret of their own that the receiver gets in its file; and the sessions closed since are named in the policy.
    Vé của luồng số trực tiếp: chỉ cấp cho bảng đã đăng nhập, cho một phạm vi có thật, khi luồng đã được cài; ký bằng một bí mật riêng
    mà bộ nhận nhận trong file của nó; và các phiên đóng từ đó được nêu trong chính sách."""

    @classmethod
    def setUpClass(cls):
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        cls.origin = "http://127.0.0.1:%d" % cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.saved = (settings.RECEIVER_ENABLED, settings.RECEIVER_LIVE_URL, settings.RECEIVER_BOARD_ORIGIN, dict(stores.ACCOUNTS.d))
        settings.RECEIVER_ENABLED, settings.RECEIVER_LIVE_URL, settings.RECEIVER_BOARD_ORIGIN = True, "https://ingest.example.com", "https://board.example.com"
        stores.ACCOUNTS.d = {"accounts": {"t-adm": {"role": security.ADMIN, "secret": ""}, "t-wall": {"role": security.WALL, "secret": ""}}}
        for name in ("t-adm", "t-wall"):
            login.SESSIONS.sessions["tick-" + name] = (name, time.time() + 3600)
        receiver.TICKETS.issued = {}
        security.BOT.__init__()

    def tearDown(self):
        settings.RECEIVER_ENABLED, settings.RECEIVER_LIVE_URL, settings.RECEIVER_BOARD_ORIGIN, stores.ACCOUNTS.d = self.saved
        for name in ("t-adm", "t-wall"):
            login.SESSIONS.sessions.pop("tick-" + name, None)
        receiver.TICKETS.issued = {}

    def ask(self, token, body, origin=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Cookie"] = "session=" + token
        if origin:
            headers["Origin"] = self.origin
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/sse/ticket", json.dumps(body), headers)
            r = conn.getresponse()
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
        finally:
            conn.close()

    def parts(self, ticket):
        p = ticket.split(".")
        kid, secret = devicekeys.DEVICE_KEYS.ticket_secret()
        body = ".".join(p[:6])
        self.assertEqual(p[7 - 1], receiver._b64(hmac.new(secret, body.encode(), hashlib.sha256).digest()))
        self.assertEqual((p[0], p[1]), ("awt1", kid))
        return {"role": p[2], "scope": base64.urlsafe_b64decode(p[3] + "=" * (-len(p[3]) % 4)).decode(), "sid": p[4], "expires": int(p[5])}

    def test_a_ticket_for_a_logged_in_board_and_a_scope_that_exists(self):
        status, t = self.ask("tick-t-wall", {"scope": "org"})
        self.assertEqual(status, 200)
        got = self.parts(t["ticket"])
        self.assertEqual((got["role"], got["scope"]), (security.WALL, "org"))
        self.assertAlmostEqual(got["expires"], time.time() + settings.TICKET_SECONDS, delta=5)
        self.assertEqual((t["live"], t["snap"], t["expiresAt"]), ("https://ingest.example.com/live", "https://ingest.example.com/live/snap", got["expires"] * 1000))
        # the sid stays for the session and gives back neither the session nor the name
        # sid giữ nguyên cho phiên và không cho lại phiên hay tên
        again = self.parts(self.ask("tick-t-wall", {"scope": "branch:"})[1]["ticket"])
        self.assertEqual((again["sid"], again["scope"]), (got["sid"], "branch:"))
        self.assertNotEqual(self.parts(self.ask("tick-t-adm", {"scope": "org"})[1]["ticket"])["sid"], got["sid"])
        self.assertNotIn("t-wall", t["ticket"])
        self.assertNotIn("tick", t["ticket"])

    def test_a_ticket_is_refused_without_login_origin_scope_or_set_up(self):
        self.assertEqual(self.ask(None, {"scope": "org"})[0], 401)
        self.assertEqual(self.ask("tick-t-adm", {"scope": "org"}, origin=False)[0], 403)
        for body in ({"scope": "nowhere"}, {"scope": "branch:nowhere"}, {}, {"scope": 1}, ["org"]):
            with self.subTest(body=body):
                self.assertEqual(self.ask("tick-t-adm", body)[0], 400)
        settings.RECEIVER_LIVE_URL = ""
        self.assertEqual(self.ask("tick-t-adm", {"scope": "org"})[0], 404)
        settings.RECEIVER_LIVE_URL, settings.RECEIVER_ENABLED = "https://ingest.example.com", False
        self.assertEqual(self.ask("tick-t-adm", {"scope": "org"})[0], 404)
        self.assertEqual(receiver.TICKETS.issued, {})

    def test_the_policy_names_the_sessions_closed_since(self):
        wall = self.parts(self.ask("tick-t-wall", {"scope": "org"})[1]["ticket"])["sid"]
        adm = self.parts(self.ask("tick-t-adm", {"scope": "org"})[1]["ticket"])["sid"]
        doc = receiver.POLICY.document(0, "")
        self.assertEqual((doc["endedSessions"], doc["boardOrigins"]), ([], ["https://board.example.com"]))
        login.SESSIONS.logout("session=tick-t-wall")
        self.assertEqual(receiver.POLICY.document(0, "")["endedSessions"], [wall])
        # a role changed is a ticket that no longer says the truth
        # vai đã đổi là một vé không còn nói đúng
        stores.ACCOUNTS.d["accounts"]["t-adm"]["role"] = security.VIEWER
        self.assertEqual(receiver.POLICY.document(0, "")["endedSessions"], sorted([wall, adm]))
        # once the tickets are dead, nothing is left to name
        # khi các vé đã chết thì không còn gì để nêu
        self.assertEqual(receiver.TICKETS.ended(time.time() + settings.TICKET_SECONDS + 1), [])
        self.assertEqual(receiver.TICKETS.issued, {})
        settings.RECEIVER_BOARD_ORIGIN = ""
        self.assertEqual(receiver.POLICY.document(0, "")["boardOrigins"], [])

    def test_the_pages_may_reach_the_receiver_only_when_the_feed_is_set_up(self):
        def csp():
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            try:
                conn.request("GET", "/")
                r = conn.getresponse()
                r.read()
                return r.getheader("Content-Security-Policy")
            finally:
                conn.close()

        self.assertIn("connect-src 'self' https://ingest.example.com;", csp())
        settings.RECEIVER_BOARD_ORIGIN = ""
        self.assertIn("connect-src 'self';", csp())

    def test_the_receivers_file_has_the_tickets_secret_apart(self):
        entries = devicekeys.DEVICE_KEYS.receiver_secrets(time.time())
        ticket = [e for e in entries if e["alg"] == "ticket"]
        kid, secret = devicekeys.DEVICE_KEYS.ticket_secret()
        self.assertEqual([(e["kid"], e["secret"]) for e in ticket], [(kid, receiver._b64(secret))])
        self.assertEqual(len(secret), 32)
        self.assertNotIn(ticket[0]["secret"], [e["secret"] for e in entries if e["alg"] != "ticket"])

    def test_the_shared_sample_of_tickets(self):
        # the receiver checks the same file (receiver/internal/feed/ticket_test.go)
        # bộ nhận kiểm cùng file này (receiver/internal/feed/ticket_test.go)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "contract", "ticket", "cases.json"), encoding="utf-8") as f:
            doc = json.load(f)
        secret = base64.urlsafe_b64decode(doc["secret"] + "=" * (-len(doc["secret"]) % 4))
        for c in doc["cases"]:
            with self.subTest(scope=c["scope"]):
                self.assertEqual(receiver.make_ticket(doc["kid"], secret, c["role"], c["scope"], c["sid"], c["expires"]), c["ticket"])


if __name__ == "__main__":
    unittest.main()
