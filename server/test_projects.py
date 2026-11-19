#!/usr/bin/env python3
"""Test of AI projects and applications on the board, standard library only: python3 -m unittest test_projects (run in the server folder).
It shares the fake data folder of test_webhook, and turns AI_PROJECTS on for its own tests only.
  Test dự án hay ứng dụng AI trên bảng, chỉ dùng thư viện chuẩn: python3 -m unittest test_projects (chạy trong thư mục server).
  Nó dùng chung thư mục dữ liệu giả của test_webhook, và chỉ bật AI_PROJECTS cho các test của chính nó."""
import http.client
import json
import os
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

# test_webhook sets the fake folders first
# test_webhook đặt các thư mục giả trước
import test_webhook as tw  # noqa: F401
import webhook as w
from board import costreport, login, projects, security, settings, stores

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "ai-cost-report")
# words that must never be stored or shown, whatever field a sender hides them in
# các từ không bao giờ được lưu hay hiện, dù người gửi giấu chúng trong trường nào
PRIVATE = ("customer-plate-51A", "private-answer-text", "someone@example.com")


def turn(n: int, ms: int = 100, at: datetime = None, **more) -> dict:
    at = at or datetime.now(timezone.utc) - timedelta(minutes=5)
    t = {"v": 1, "turnId": "%016x" % n, "at": at.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "durationMs": ms, "outcome": "ok", "env": "prod",
         "models": [{"provider": "anthropic", "model": "claude-sonnet-5-5", "calls": 1, "errors": 0, "retries": 0, "unmeasured": 0,
                     "input": 1000, "output": 100, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}]}
    t.update(more)
    return t


class SameCode(unittest.TestCase):
    def test_the_board_uses_the_skills_own_report(self):
        # the board cleans and prices with a copy of the skill's report: the copies must not drift apart
        # bảng làm sạch và tính tiền bằng bản sao của báo cáo trong skill: các bản sao không được lệch nhau
        for mine, theirs in (("costreport.py", "report.py"), ("labels.json", "labels.json"), ("prices.json", "prices.json")):
            with open(os.path.join(HERE, "board", mine), encoding="utf-8") as a, open(os.path.join(SKILL, theirs), encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read(), "server/board/%s must equal skills/ai-cost-report/%s" % (mine, theirs))


class Projects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.was = settings.PROJECTS_ENABLED
        settings.PROJECTS_ENABLED = True
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": ""},
                                          "wall": {"role": security.WALL, "secret": ""}}}
        for name in ("adm", "viewer", "wall"):
            login.SESSIONS.sessions["tok-" + name] = (name, time.time() + 3600)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        cls.origin = "http://127.0.0.1:%d" % cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        settings.PROJECTS_ENABLED = cls.was

    def setUp(self):
        security.BOT.__init__()
        login.SESSIONS.confirmed_at.clear()
        w.PROJECT_LIMIT.__init__(settings.PROJECT_SENDS_PER_KEY, settings.PROJECT_SENDS_WINDOW_SECONDS)
        self.key_id, self.key = stores.TV.create({"name": "Car price", "approvedBy": "adm", "ip": "127.0.0.1", "device": "AI project",
                                                  "kind": settings.KIND_PROJECT}, time.time())

    def tearDown(self):
        if self.key_id in stores.TV.d:
            stores.TV.revoke(self.key_id)
        with projects.PROJECTS.db.tx() as c:
            c.execute("DELETE FROM project_turns")
            c.execute("DELETE FROM project_daily")
        projects.PROJECTS.received.clear()

    def call(self, method, path, body=None, key=None, cookie=None, **headers):
        security.BOT.__init__()
        headers = {k.replace("_", "-"): v for k, v in headers.items()}
        if key:
            headers["Authorization"] = "Bearer " + key
        if cookie:
            headers["Cookie"] = "session=" + cookie
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read(), dict(r.getheaders())
        finally:
            conn.close()

    def send(self, turns, key=None, **headers):
        status, b, _ = self.call("POST", "/projects/ingest", {"turns": turns}, key=key or self.key, **headers)
        return status, json.loads(b or b"{}")

    def stored(self) -> str:
        return json.dumps(projects.PROJECTS.db.rows("SELECT * FROM project_turns")) + json.dumps(projects.PROJECTS.db.rows("SELECT * FROM project_daily"))

    # keys
    # khoá
    def test_only_a_live_project_key_may_send(self):
        self.assertEqual(self.send([turn(1)])[0], 200)
        mcp_id, mcp_key = stores.TV.create({"name": "Tool", "approvedBy": "adm", "ip": "127.0.0.1", "device": "x", "kind": settings.KIND_MCP}, time.time())
        tv_id, tv_key = stores.TV.create({"name": "TV", "approvedBy": "adm", "ip": "127.0.0.1", "device": "x"}, time.time())
        try:
            for key in ("", "prj_" + "x" * 43, mcp_key, tv_key, "test"):
                self.assertEqual(self.send([turn(2)], key=key or "none")[0], 401, key[:6])
            # a key put in a web page is useless: a browser sends an Origin
            # khoá đặt trong trang web là vô dụng: trình duyệt gửi Origin
            self.assertEqual(self.send([turn(3)], Origin="https://example.com")[0], 403)
            # the project key opens nothing else
            # khoá dự án không mở được gì khác
            self.assertEqual(self.call("POST", "/mcp", "{}", key=self.key)[0], 401)
            self.assertEqual(self.call("GET", "/ext/state", key=self.key)[0], 401)
            self.assertEqual(self.call("GET", "/projects", key=self.key)[0], 200)  # the login page, nothing else
            self.assertNotIn(b"Car price", self.call("GET", "/projects", key=self.key)[1])
        finally:
            stores.TV.revoke(mcp_id)
            stores.TV.revoke(tv_id)

    def test_a_revoked_key_stops_at_once_and_its_numbers_stay(self):
        self.assertEqual(self.send([turn(1)])[0], 200)
        stores.TV.revoke(self.key_id)
        self.assertEqual(self.send([turn(2)])[0], 401)
        self.assertIn(self.key_id, projects.known(time.time()))
        self.assertEqual(len(projects.PROJECTS.db.rows("SELECT 1 FROM project_turns")), 1)

    def test_the_paths_are_gone_when_turned_off(self):
        settings.PROJECTS_ENABLED = False
        try:
            self.assertEqual(self.send([turn(1)])[0], 404)
            self.assertEqual(self.call("GET", "/projects", cookie="tok-adm")[0], 404)
            self.assertEqual(self.call("POST", "/admin/project-key", {"name": "x"}, cookie="tok-adm", Origin=self.origin)[0], 404)
        finally:
            settings.PROJECTS_ENABLED = True

    # what is kept
    # thứ được giữ
    def test_unknown_fields_and_bad_turns_are_dropped(self):
        good = turn(1, prompt=PRIVATE[1], user=PRIVATE[2])
        good["models"][0]["note"] = PRIVATE[0]
        bad = [turn(2, durationMs=-1), turn(3, env="staging"), dict(turn(4), models=[{"provider": "Has Space", "model": "x"}]),
               turn(5, at=datetime.now(timezone.utc) - timedelta(days=settings.PROJECT_TURN_KEEP_DAYS + 1)),
               turn(6, at=datetime.now(timezone.utc) + timedelta(days=2)), "not a turn", None]
        status, r = self.send([good] + bad)
        self.assertEqual((status, r["accepted"], r["refused"]), (200, 1, len(bad)))
        everything = self.stored()
        for word in PRIVATE:
            self.assertNotIn(word, everything)

    def test_bad_sends_are_refused(self):
        for body in ("", "not json", "[]", '{"turns": 1}', json.dumps({"turns": [turn(i) for i in range(settings.PROJECT_SEND_MAX_TURNS + 1)]})):
            status = self.call("POST", "/projects/ingest", body, key=self.key)[0]
            self.assertIn(status, (400, 413), body[:20])
        big = json.dumps({"turns": [turn(1)], "pad": "x" * settings.PROJECT_SEND_MAX_BYTES})
        self.assertEqual(self.call("POST", "/projects/ingest", big, key=self.key)[0], 413)

    def test_a_turn_sent_twice_is_kept_once(self):
        self.assertEqual(self.send([turn(1), turn(2)])[1]["accepted"], 2)
        r = self.send([turn(2), turn(3)])[1]
        self.assertEqual((r["accepted"], r["duplicates"]), (1, 1))
        day = projects.PROJECTS.days(self.key_id, "2000-01-01", "2999-01-01", "all")
        self.assertEqual(sum(d["turns"] for d in day if not d["model"]), 3)
        self.assertEqual(sum(d["calls"] for d in day if d["model"]), 3)

    def test_a_key_that_sends_too_often_is_told_to_wait(self):
        w.PROJECT_LIMIT.__init__(2, 600)
        self.assertEqual([self.send([turn(i)])[0] for i in range(3)], [200, 200, 429])

    def test_the_days_limit(self):
        old = projects.PROJECT_TURNS_PER_DAY
        projects.PROJECT_TURNS_PER_DAY = 3
        projects.PROJECTS.received.clear()
        try:
            r = self.send([turn(i) for i in range(2)])[1]
            self.assertEqual((r["accepted"], r["overDailyLimit"]), (2, 0))
            # turns that say they are from an earlier day count against today too: the limit is on what the board takes in
            # lượt tự ghi là của ngày trước cũng tính vào hôm nay: giới hạn đặt trên lượng bảng nhận vào
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            r = self.send([turn(10 + i, at=yesterday) for i in range(3)])[1]
            self.assertEqual((r["accepted"], r["overDailyLimit"]), (1, 2))
        finally:
            projects.PROJECT_TURNS_PER_DAY = old
            projects.PROJECTS.received.clear()

    def test_tokens_not_measured_stay_unknown(self):
        t = turn(1)
        t["models"][0].update(unmeasured=1, input=None, output=None, cacheRead=None, cacheWrite=None, cacheWriteLong=None)
        self.send([t, turn(2)])
        first = datetime.now(timezone.utc).date().isoformat()
        r = projects.report(self.key_id, "Car price", first, first, "prod", "en", time.time())[0]
        self.assertEqual((r["turns"], r["measured"]), (2, 1))

    # who sees what
    # ai xem được gì
    def test_who_may_see_and_download(self):
        self.send([turn(1)])
        for path in ("/projects", "/projects/report.html", "/projects/report.csv"):
            for cookie, want in ((None, 200 if path == "/projects" else 401), ("tok-viewer", 200), ("tok-adm", 200), ("tok-wall", 303 if path == "/projects" else 403)):
                status, body, _ = self.call("GET", path, cookie=cookie)
                with self.subTest(path=path, cookie=cookie):
                    self.assertEqual(status, want)
                    if cookie in (None, "tok-wall"):
                        self.assertNotIn(b"Car price", body)

    def test_the_report_matches_the_skill_and_its_p95(self):
        self.send([turn(i, ms=i * 10) for i in range(1, 41)])
        status, csv_text, headers = self.call("GET", "/projects/report.csv?project=" + self.key_id, cookie="tok-viewer")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn("perTurnAverage,all,,40,1.000,,,1000.0,100.0,0.0,0.0,0.003000000,205.0,380,400", csv_text.decode())
        status, page, headers = self.call("GET", "/projects/report.html?project=" + self.key_id + "&env=prod", cookie="tok-adm")
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertIn(b"Car price", page)
        page = self.call("GET", "/projects?project=" + self.key_id, cookie="tok-viewer")[1].decode()
        self.assertIn("Totals per day", page)
        self.assertIn('name="from"', page)

    def test_an_unknown_project_in_the_query_falls_back(self):
        self.send([turn(1)])
        self.assertEqual(self.call("GET", "/projects/report.csv?project=../../etc", cookie="tok-adm")[0], 200)

    # the Admin page
    # trang Quản trị
    def test_making_a_key_needs_the_otp_and_shows_it_once(self):
        status, b, _ = self.call("POST", "/admin/project-key", {"name": "Chat bot"}, cookie="tok-adm", Origin=self.origin)
        self.assertEqual((status, json.loads(b).get("needsConfirm")), (403, True))
        for cookie in ("tok-viewer", "tok-wall"):
            self.assertEqual(self.call("POST", "/admin/project-key", {"name": "Chat bot"}, cookie=cookie, Origin=self.origin)[0], 403)
        login.SESSIONS.confirmed_at["tok-adm"] = time.time()
        status, b, _ = self.call("POST", "/admin/project-key", {"name": "Chat bot"}, cookie="tok-adm", Origin=self.origin)
        self.assertEqual(status, 200)
        d = json.loads(b)
        try:
            self.assertTrue(d["token"].startswith("prj_"))
            row = stores.TV.d[d["id"]]
            self.assertNotIn(d["token"], json.dumps(row))
            self.assertEqual(row["keyStart"], d["token"][:12])
            self.assertEqual(self.send([turn(9)], key=d["token"])[0], 200)
            log = json.dumps(stores.AUDIT_LOG.read(datetime.now().strftime("%Y-%m")))
            self.assertIn("project-key-created", log)
            self.assertNotIn(d["token"], log)
        finally:
            stores.TV.revoke(d["id"])

    def test_prices_an_admin_pastes(self):
        login.SESSIONS.confirmed_at["tok-adm"] = time.time()
        with open(os.path.join(SKILL, "my-prices.example.json"), encoding="utf-8") as f:
            mine = json.load(f)
        status = self.call("POST", "/admin/project-prices", {"prices": mine}, cookie="tok-adm", Origin=self.origin)[0]
        self.assertEqual(status, 200)
        try:
            self.assertEqual(projects.prices().at("example-model-large", "2026-11-20")["input"], 500000)
            for bad in ({"models": [{"model": "x y"}]}, {"models": [{"model": "m", "prices": [{"input": -1}]}]}, {"models": "x"}, [1]):
                self.assertEqual(self.call("POST", "/admin/project-prices", {"prices": bad}, cookie="tok-adm", Origin=self.origin)[0], 400)
        finally:
            self.call("POST", "/admin/project-prices", {"prices": None}, cookie="tok-adm", Origin=self.origin)
        self.assertEqual(projects.PRICES.read(), {})

    def test_old_turns_and_days_are_swept(self):
        self.send([turn(1)])
        later = time.time() + (settings.PROJECT_TURN_KEEP_DAYS + 1) * 86400
        projects.PROJECTS.sweep(later)
        self.assertEqual(projects.PROJECTS.db.rows("SELECT COUNT(*) FROM project_turns")[0][0], 0)
        self.assertTrue(projects.PROJECTS.db.rows("SELECT COUNT(*) FROM project_daily")[0][0])
        projects.PROJECTS.sweep(time.time() + 420 * 86400)
        self.assertEqual(projects.PROJECTS.db.rows("SELECT COUNT(*) FROM project_daily")[0][0], 0)


    # the meters of the skill, pointed at this board, send what they measured; the file is still written
    # bộ đo của skill, trỏ vào bảng này, gửi những gì đã đo; file vẫn được ghi
    def test_the_python_meter_sends_in_the_background(self):
        import sys
        import tempfile
        sys.path.insert(0, os.path.join(SKILL, "meter"))
        import ai_meter
        folder = tempfile.mkdtemp()
        m = ai_meter.Meter(os.path.join(folder, "m.jsonl"), send_url="http://127.0.0.1:%d/projects/ingest" % self.port, send_key=self.key)
        for _ in range(3):
            with m.turn() as t:
                t.record({"model": "claude-sonnet-5-5", "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 0}})
        m.sender.flush()
        self.assertEqual(projects.PROJECTS.db.rows("SELECT COUNT(*) FROM project_turns")[0][0], 3)
        with open(os.path.join(folder, "m.jsonl"), encoding="utf-8") as f:
            self.assertEqual(len(f.readlines()), 3)
        # a key is never sent over plain HTTP to another machine
        # khoá không bao giờ được gửi qua HTTP thường tới máy khác
        self.assertIsNone(ai_meter.Meter(os.path.join(folder, "n.jsonl"), send_url="http://board.example.com/projects/ingest", send_key="k").sender)
        # a board that does not answer costs the project nothing
        # bảng không trả lời thì dự án không mất gì
        dead = ai_meter.Meter(os.path.join(folder, "d.jsonl"), send_url="http://127.0.0.1:9/projects/ingest", send_key="k")
        started = time.monotonic()
        with dead.turn():
            pass
        self.assertLess(time.monotonic() - started, 0.5)

    @unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
    def test_the_node_meter_sends_in_the_background(self):
        import subprocess
        import tempfile
        script = ("const { Meter } = require(process.argv[1]);"
                  "const m = new Meter({ file: process.argv[2], sync: true, sendUrl: process.argv[3], sendKey: process.argv[4] });"
                  "(async () => { for (let i = 0; i < 2; i++) await m.turn(async (t) => t.record({ model: 'gpt-6-luna', usage: { prompt_tokens: 5, completion_tokens: 1 } }));"
                  " await m.sender.flush(); })()")
        r = subprocess.run(["node", "-e", script, os.path.join(SKILL, "meter", "ai-meter.cjs"), os.path.join(tempfile.mkdtemp(), "m.jsonl"),
                            "http://127.0.0.1:%d/projects/ingest" % self.port, self.key], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(projects.PROJECTS.db.rows("SELECT COUNT(*) FROM project_turns")[0][0], 2)


class Clean(unittest.TestCase):
    def test_p95_is_nearest_rank(self):
        self.assertEqual(costreport.p95(list(range(1, 21))), 19)


if __name__ == "__main__":
    unittest.main()
