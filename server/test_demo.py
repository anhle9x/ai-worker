#!/usr/bin/env python3
"""Test of the demo, standard library only: python3 -m unittest test_demo (run in the server folder).
The demo is started as its own program, the way a visitor starts it, with the settings of a pretend real board
in its environment to prove it ignores them.
  Test của bản thử, chỉ dùng thư viện chuẩn: python3 -m unittest test_demo (chạy trong thư mục server).
  Bản thử được bật như một chương trình riêng, đúng cách người ghé xem bật nó, kèm cấu hình của một bảng thật giả định
  trong môi trường để chứng minh nó bỏ qua các cấu hình đó."""
import http.client
import ipaddress
import json
import os
import queue
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import demo

HERE = os.path.dirname(os.path.abspath(__file__))


class SampleData(unittest.TestCase):
    """The sample itself: made-up, complete, and the same on every run.
    Chính dữ liệu mẫu: bịa hoàn toàn, đủ, và lần chạy nào cũng giống nhau."""

    def test_same_seed_gives_the_same_numbers(self):
        self.assertEqual(demo.sample_reports(1_800_000_000.0), demo.sample_reports(1_800_000_000.0))

    def test_nobody_looks_real(self):
        for r in demo.sample_reports(time.time()):
            with self.subTest(person=r["device"]):
                self.assertTrue(r["account"].endswith("@example.com"))
                self.assertTrue(ipaddress.ip_address(r["lanIp"]).is_private)
                self.assertRegex(r["device"], r"^device-demo\d\d$")

    def test_every_person_sits_in_one_office(self):
        branches = demo.sample_branches()["branches"]
        seated = [e for b in branches for e in b["people"]]
        self.assertEqual(sorted(seated), sorted(demo.email_of(i) for i in range(len(demo.PEOPLE))))
        self.assertEqual([b["isHq"] for b in branches].count(True), 1)

    def test_refresh_keeps_people_online_and_leaves_the_offline_one_offline(self):
        start = 1_800_000_000.0
        reports = demo.sample_reports(start)
        offline = [r["device"] for r in reports if r["openSessions"] == 0]
        self.assertEqual(len(offline), 1)
        rnd = random.Random(1)
        for step in range(1, 40):
            demo.refresh_reports(reports, start + step * demo.REFRESH_SECONDS, rnd)
        later_ms = int((start + 39 * demo.REFRESH_SECONDS) * 1000)
        for r in reports:
            with self.subTest(person=r["device"]):
                if r["device"] in offline:
                    self.assertLess(r["updatedAt"], start * 1000)
                else:
                    self.assertEqual(r["updatedAt"], later_ms)
                self.assertLessEqual(r["working"] + r["waiting"], 1)


class RunsForReal(unittest.TestCase):
    """Starts the demo, logs in with the code it prints, reads the board, stops it.
    Bật bản thử, đăng nhập bằng mã nó in ra, đọc bảng, rồi dừng."""

    @classmethod
    def setUpClass(cls):
        cls.box = tempfile.mkdtemp(prefix="test-demo-")
        cls.real_data = os.path.join(cls.box, "real-data")
        cls.demo_tmp = os.path.join(cls.box, "tmp")
        for folder in (cls.real_data, cls.demo_tmp):
            os.makedirs(folder)
        # what a shell on a real board server would hold: the demo must use none of it
        # những gì một cửa sổ lệnh trên máy chủ bảng thật sẽ có: bản thử không được dùng thứ nào
        env = dict(os.environ, DATA_DIR=cls.real_data, KEYS_DIR=cls.real_data, INGEST_KEY="real-key", OTP="boss:MFRGGZDFMZTWQ2LK", OTP_ADMINS="boss",
                   TELEGRAM_BOT_TOKEN="1:real", TELEGRAM_BOT_NAME="realbot", BIND_ADDR="0.0.0.0", PORT="1", TMPDIR=cls.demo_tmp, TEMP=cls.demo_tmp, TMP=cls.demo_tmp)
        # on Windows the demo gets its own group, so the test can send it Ctrl+Break without stopping itself
        # trên Windows bản thử có nhóm riêng, để bài test gửi được Ctrl+Break cho nó mà không tự dừng mình
        cls.proc = subprocess.Popen([sys.executable, os.path.join(HERE, "demo.py"), "--port", "0"], cwd=cls.box, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        cls.lines = queue.Queue()
        threading.Thread(target=lambda: [cls.lines.put(line) for line in cls.proc.stdout], daemon=True).start()
        cls.printed = []
        cls.port = int(cls.wait_for(r"^Open\s+http://127\.0\.0\.1:(\d+)$"))
        cls.code = cls.wait_for(r"^Code\s+(\d{6})$")

    @classmethod
    def wait_for(cls, pattern: str, seconds: float = 30) -> str:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                line = cls.lines.get(timeout=0.2).rstrip("\n")
            except queue.Empty:
                if cls.proc.poll() is not None:
                    break
                continue
            cls.printed.append(line)
            found = re.match(pattern, line)
            if found:
                return found.group(1)
        raise AssertionError("the demo did not print %s; it printed: %r" % (pattern, cls.printed))

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.kill()
        cls.proc.wait(10)
        cls.proc.stdout.close()
        shutil.rmtree(cls.box, ignore_errors=True)

    def call(self, method, path, body=None, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body, {"Cookie": cookie} if cookie else {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data, r.getheader("Set-Cookie")

    def test_1_answers_and_asks_for_a_login(self):
        self.assertEqual(self.call("GET", "/health")[0], 200)
        self.assertEqual(self.call("GET", "/data")[0], 401)

    def test_2_the_printed_code_opens_the_board(self):
        status, _, set_cookie = self.call("POST", "/login", "account=%s&code=%s" % (demo.ACCOUNT, self.code))
        self.assertEqual(status, 303)
        status, body, _ = self.call("GET", "/data", cookie=set_cookie.split(";")[0])
        self.assertEqual(status, 200)
        board = json.loads(body)
        self.assertEqual(board["role"], "admin")
        self.assertEqual(len(board["people"]), len(demo.PEOPLE))
        self.assertEqual([b["name"] for b in board["branches"]], [o[1] for o in demo.OFFICES])
        self.assertEqual({p["status"] for p in board["people"]} - {"working", "waiting", "open", "offline"}, set())
        self.assertEqual([p["status"] for p in board["people"]].count("offline"), 1)

    def test_3_a_real_board_s_settings_are_ignored(self):
        # the account and the send key from the environment do not exist in the demo, and nothing was written to that data folder
        # tài khoản và mã gửi lấy từ môi trường không tồn tại trong bản thử, và không gì được ghi vào thư mục dữ liệu đó
        self.assertEqual(self.call("POST", "/login", "account=boss&code=000000")[0], 401)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/ingest", "{}", {"Authorization": "Bearer real-key", "Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 401)
        conn.close()
        self.assertEqual(os.listdir(self.real_data), [])
        self.assertEqual(self.call("GET", "/login/telegram")[0], 404)

    def test_4_stopping_deletes_the_sample_data(self):
        self.assertEqual(len(os.listdir(self.demo_tmp)), 1)
        # a plain kill on Windows ends a program at once with no chance to tidy up, so the test presses Ctrl+Break there
        # lệnh kill thường trên Windows kết thúc chương trình ngay, không kịp dọn, nên ở đó bài test bấm Ctrl+Break
        self.proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        self.assertEqual(self.proc.wait(15), 0)
        self.assertEqual(os.listdir(self.demo_tmp), [])
        self.wait_for(r"^(Demo stopped, sample data deleted\.)$", 5)


@unittest.skipIf(os.name == "nt", "Windows has no hang-up signal")
class ClosedTerminal(unittest.TestCase):
    def test_closing_the_terminal_window_deletes_the_sample_data(self):
        box = tempfile.mkdtemp(prefix="test-demo-")
        self.addCleanup(shutil.rmtree, box, True)
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, "demo.py"), "--port", "0"], cwd=box, env=dict(os.environ, TMPDIR=box),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        for line in proc.stdout:
            if line.startswith("Code"):
                break
        self.assertEqual(len(os.listdir(box)), 1)
        proc.send_signal(signal.SIGHUP)
        self.assertEqual(proc.wait(15), 0)
        self.assertEqual(os.listdir(box), [])


if __name__ == "__main__":
    unittest.main()
