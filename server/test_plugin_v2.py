#!/usr/bin/env python3
"""The plugin's own code for format v: 2 against this server over HTTP: python3 -m unittest test_plugin_v2 (run in the server folder).
hooks/sendv2.ts and buildMachineSummary of hooks/team.ts run in Node (tests/contract/plugin-v2/bridge.mjs) and make every send; this test
posts it to the real /ingest, gives the answer back to the plugin's code, and checks that the book the server keeps is the book the computer
holds, after lost sends, lost answers, a lost row, another start of the server and two sessions sending at once. Skipped without Node 22.
  Chính mã của plugin cho định dạng v: 2 gặp máy chủ này qua HTTP: python3 -m unittest test_plugin_v2 (chạy trong thư mục server).
  hooks/sendv2.ts và buildMachineSummary của hooks/team.ts chạy trong Node và dựng mọi lần gửi; test này gửi nó tới /ingest thật, trả câu
  trả lời lại cho mã của plugin, và kiểm sổ máy chủ giữ đúng là sổ máy đang giữ, sau khi mất gói, mất câu trả lời, mất dòng, máy chủ khởi
  động lại và hai phiên gửi cùng lúc. Bỏ qua khi không có Node 22."""
import http.client
import json
import os
import random
import shutil
import subprocess
import threading
import time
import unittest

# imported first: it points the server at temporary folders before any board module reads its settings
# nhập trước tiên: nó trỏ máy chủ sang thư mục tạm trước khi module board nào đọc cấu hình
import test_webhook as tw  # noqa: F401
import webhook as w
from board import devices, settings, views
from test_contract import drop_rows

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "..", "tests", "contract", "plugin-v2", "bridge.mjs")


def node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    return out.split(".")[0].isdigit() and int(out.split(".")[0]) >= 22


@unittest.skipUnless(node_ok(), "needs Node 22 or later to run the plugin's TypeScript")
class PluginToServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.bridge = subprocess.Popen(["node", BRIDGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.bridge.stdin.close()
        cls.bridge.wait(timeout=10)
        cls.bridge.stdout.close()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        views.INGEST_GATE.buckets, views.INGEST_GATE.new_devices = {}, {}
        self.device = "device-plugin%s" % self._testMethodName[-6:].replace("_", "x")
        self.key, self.clock = settings.INGEST_KEY, int(time.time() * 1000)
        self.boot = w.BOOT_ID

    def tearDown(self):
        w.BOOT_ID = self.boot
        drop_rows([self.device])

    # ---- the plugin's side, through the bridge / phía plugin, qua cầu nối ----

    def call(self, command: dict) -> dict:
        self.bridge.stdin.write(json.dumps(command) + "\n")
        self.bridge.stdin.flush()
        return json.loads(self.bridge.stdout.readline())

    def packet(self, ledger: dict, state) -> dict:
        self.clock += 1000
        who = {"device": self.device, "name": "Plug In", "account": "plug-%s@example.com" % self.device}
        return self.call({"op": "packet", "ledger": ledger, "now": self.clock, "who": who, "state": state})

    def after(self, state, answer: str, sent: dict) -> dict:
        return self.call({"op": "after", "state": state, "answer": answer, "sent": sent, "now": self.clock})

    # ---- the server's side / phía máy chủ ----

    def post(self, body: dict):
        # the limit of sends per computer is not what is tested here / giới hạn số lần gửi mỗi máy không phải thứ được kiểm ở đây
        views.INGEST_GATE.buckets = {}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/ingest", json.dumps(body), {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
            r = conn.getresponse()
            text = r.read().decode()
        finally:
            conn.close()
        key = json.loads(text or "{}").get("deviceKey") if r.status == 200 else None
        if key:
            self.key = key
        return r.status, text

    def send(self, ledger: dict, state):
        """One send as the plugin makes it, answered by the server; returns the state after it and what was sent.
        Một lần gửi như plugin làm, máy chủ trả lời; trả trạng thái sau đó và gói đã gửi."""
        p = self.packet(ledger, state)
        status, text = self.post(p["body"])
        self.assertEqual(status, 200, text)
        return self.after(state, text, p), p

    def held(self) -> dict:
        kept = (devices.read_device(self.device) or {}).get("ledger", {})
        return {h: v["usdMicro"] for h, v in kept.items()}

    def assertSameBook(self, ledger: dict):
        self.assertEqual(self.held(), {h: round(v["usd"] * 1_000_000) for h, v in ledger.items() if v})

    def hour(self, back: int = 0) -> str:
        return str(self.clock // 3_600_000 - back)

    # ---- the cases / các trường hợp ----

    def test_after_any_send_the_server_holds_the_computer_s_book(self):
        rnd = random.Random(5)
        ledger = {self.hour(h): {"usd": round(rnd.random(), 6), "input": h} for h in range(0, 60, 3)}
        state, first = self.send(ledger, None)
        self.assertEqual((first["body"]["v"], state.get("v2")), (1, True))
        self.assertSameBook(ledger)
        for step in range(25):
            h = self.hour(rnd.randrange(0, 4))
            ledger[h] = {"usd": round(ledger.get(h, {"usd": 0})["usd"] + rnd.random(), 6), "input": step}
            if step % 7 == 6:
                # the oldest hour leaves the computer's 8 days / giờ cũ nhất rời khỏi 8 ngày của máy
                ledger.pop(min(ledger, key=int))
            state, p = self.send(dict(ledger), state)
            self.assertEqual(p["body"]["v"], 2)
            self.assertSameBook(ledger)
        # only the hours that changed went up, not the book / chỉ các giờ đã đổi được gửi, không phải cả sổ
        self.assertLessEqual(len(p["body"]["hours"]["ledger"]), 2)

    def test_lost_sends_and_lost_answers_are_made_good_by_the_next_send(self):
        ledger = {self.hour(1): {"usd": 1.0}, self.hour(): {"usd": 2.0}}
        state, _ = self.send(ledger, None)
        ledger[self.hour()] = {"usd": 2.5}
        # lost on the way: never posted
        # mất trên đường: không bao giờ tới
        self.packet(ledger, state)
        ledger[self.hour(1)] = {"usd": 1.25}
        p = self.packet(ledger, state)
        # taken, but its answer lost: the state does not move
        # đã nhận nhưng mất câu trả lời: trạng thái không đổi
        self.assertEqual(self.post(p["body"])[0], 200)
        ledger[self.hour()] = {"usd": 3.0}
        state, _ = self.send(ledger, state)
        self.assertSameBook(ledger)

    def test_a_lost_row_asks_for_the_whole_book_and_gets_it(self):
        ledger = {self.hour(h): {"usd": float(h + 1)} for h in range(5)}
        state, _ = self.send(ledger, None)
        state, _ = self.send(ledger, state)
        drop_rows([self.device])
        ledger[self.hour()] = {"usd": 9.0}
        state, p = self.send(ledger, state)
        self.assertEqual((p["full"], state.get("needFull")), (False, True))
        self.assertEqual(self.held(), {})
        state, p = self.send(ledger, state)
        self.assertTrue(p["body"]["full"])
        self.assertSameBook(ledger)

    def test_another_start_of_the_server_sends_the_last_two_days_again(self):
        old = self.hour(60)
        ledger = {old: {"usd": 4.0}, self.hour(1): {"usd": 1.0}, self.hour(): {"usd": 2.0}}
        state, _ = self.send(ledger, None)
        state, _ = self.send(ledger, state)
        # the server lost the last seconds before it stopped: it holds an older value of this hour, and starts again
        # máy chủ mất những giây cuối trước khi dừng: nó giữ giá trị cũ của giờ này, rồi khởi động lại
        stale = {"v": 2, "device": self.device, "name": "Plug In", "account": "plug-%s@example.com" % self.device, "updatedAt": self.clock + 500,
                 "openSessions": 0, "working": 0, "waiting": 0, "full": False, "hours": {"ledger": {self.hour(): {"usd": 0.5}}}}
        self.clock += 1000
        self.assertEqual(self.post(stale)[0], 200)
        w.BOOT_ID = "0123456789abcdef"
        # nothing changed here, but the start did
        # ở đây không đổi gì, nhưng lần khởi động đã đổi
        state, p = self.send(ledger, state)
        self.assertEqual(p["body"]["hours"]["ledger"], {})
        state, p = self.send(ledger, state)
        self.assertEqual(sorted(p["body"]["hours"]["ledger"]), sorted([self.hour(1), self.hour()]))
        self.assertSameBook(ledger)

    def test_two_sessions_of_one_computer_sending_at_once(self):
        ledger = {self.hour(1): {"usd": 1.0}, self.hour(): {"usd": 2.0}}
        state, _ = self.send(ledger, None)
        # both sessions read the same state; the second one's numbers are newer, and its answer is put down first
        # cả hai phiên đọc cùng một trạng thái; số của phiên sau mới hơn, và câu trả lời của nó được ghi trước
        a = self.packet(dict(ledger, **{self.hour(): {"usd": 2.5}}), state)
        ledger[self.hour()] = {"usd": 3.0}
        ledger[self.hour(1)] = {"usd": 1.5}
        b = self.packet(dict(ledger), state)
        answer_a, answer_b = self.post(a["body"])[1], self.post(b["body"])[1]
        state = self.after(self.after(state, answer_b, b), answer_a, a)
        self.assertSameBook(ledger)
        ledger[self.hour()] = {"usd": 3.5}
        state, _ = self.send(ledger, state)
        self.assertSameBook(ledger)


if __name__ == "__main__":
    unittest.main()
