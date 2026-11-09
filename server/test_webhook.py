#!/usr/bin/env python3
"""Server test, standard library only: python3 -m unittest test_webhook (run in the server folder).
All the data here is fake, kept in a temporary folder, deleted when the run ends.
  Test máy chủ, chỉ dùng thư viện chuẩn: python3 -m unittest test_webhook (chạy trong thư mục server).
Mọi dữ liệu ở đây là giả, nằm trong thư mục tạm, xoá khi chạy xong."""
import base64
import glob
import http.client
import inspect
import json
import os
import re
import socket
import sqlite3
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

TMP = tempfile.mkdtemp(prefix="test-webhook-")
os.environ.update(INGEST_KEY="test", DATA_DIR=os.path.join(TMP, "data"), KEYS_DIR=os.path.join(TMP, "keys"),
                  BRANCHES_FILE=os.path.join(TMP, "missing.json"), OTP="")
os.makedirs(os.environ["DATA_DIR"])

import webhook as w  # noqa: E402
from board import assets, db, devices, lang, login, packages, pages, security, settings, stores, views  # noqa: E402

NOW = time.time()
EMAIL = "an@example.com"
IP_LAN = "192.168.77.5"
IP_PUBLIC = "14.1.1.1"
NET_CUSTOM = "27.2.2.2"


def seed():
    device = {
        "v": 1, "device": "device-an", "name": "An", "account": EMAIL, "enteredAccount": "an-cu@example.com", "lanIp": IP_LAN, "ip": IP_PUBLIC,
        "updatedAt": int(NOW * 1000), "openSessions": 1, "working": 1, "subagents": {"general-purpose": 1}, "pluginVersion": "0.22.0",
    }
    # a device with no name declared: the name may be an email, it must not reach the wall display
    # máy chưa khai tên: tên có thể là email, không được lên màn treo tường
    no_name = dict(device, device="device-binh", name="", account="binh@example.com", enteredAccount="", ip=NET_CUSTOM)
    for d in (device, no_name):
        devices.save_device(d)
    stores.LOCATIONS.mutate(lambda d: views.edit_location(d, {"ip": NET_CUSTOM, "name": "Hanoi", "lat": 21.03, "lon": 105.85}))
    stores.TEAM.mutate(lambda d: d.update(updatedAt=1, dateFrom="", dateTo="", people={EMAIL: {"other": {"net": 1, "gross": 1, "tokensIn": 1, "tokensOut": 1},
                                                                  "code": {"net": 0, "gross": 0, "tokensIn": 0, "tokensOut": 0}}}))
    views.HISTORY.record_if_changed(devices.group_by_person(devices.read_all_devices(), NOW), NOW)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def stored_device(device: str) -> dict:
    """The row of a device exactly as stored, not cleaned again on reading.
    Dòng của một máy đúng như đã lưu, không làm sạch lại khi đọc."""
    rows = db.data_db().rows("SELECT body FROM devices WHERE device = ?", (device,))
    return json.loads(rows[0][0])


def drop_device(device: str) -> None:
    with db.data_db().tx() as c:
        c.execute("DELETE FROM devices WHERE device = ?", (device,))


def all_audit_rows() -> list:
    return [json.loads(b) for (b,) in db.data_db().rows("SELECT body FROM audit ORDER BY id")]


class RoleViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()

    def test_admin_sees_all(self):
        d = views.role_view(security.ADMIN, NOW)
        self.assertIn("team", d)
        self.assertIn("unnamedGroups", d)
        self.assertTrue(any(b.get("customNetworks") == [NET_CUSTOM] for b in d["branches"]))
        self.assertTrue(any(p["account"] == EMAIL and IP_LAN in p["lanIps"] for p in d["people"]))

    def test_viewer_has_no_admin_part(self):
        d = views.role_view(security.VIEWER, NOW)
        self.assertNotIn("unnamedGroups", d)
        self.assertTrue(all("customNetworks" not in b for b in d["branches"]))
        self.assertNotIn(NET_CUSTOM, json.dumps(d))
        self.assertTrue(any(p["account"] == EMAIL for p in d["people"]))
        self.assertIn("team", d)

    def test_wall_has_no_email_ip(self):
        d = views.role_view(security.WALL, NOW)
        raw_text = json.dumps(d, ensure_ascii=False)
        for forbidden in ("@example.com", IP_LAN, IP_PUBLIC, NET_CUSTOM):
            self.assertNotIn(forbidden, raw_text)
        self.assertNotIn("team", d)
        self.assertNotIn("unnamedGroups", d)
        self.assertTrue(all("lanIps" not in p and "enteredAccounts" not in p for p in d["people"]))
        self.assertIn("An", [p["name"] for p in d["people"]])

    def test_wall_still_tells_people_apart(self):
        d = views.role_view(security.WALL, NOW)
        aliases = [p["account"] for p in d["people"]]
        self.assertEqual(len(aliases), 2)
        self.assertEqual(len(set(aliases)), 2)

    def test_new_field_must_be_classified(self):
        """Add a field to the raw data without declaring it for each role and this test goes red.
        Thêm trường vào dữ liệu gốc mà chưa khai cho từng vai thì test này đỏ."""
        original = views._raw_data(NOW)
        self.assertEqual(set(original), views.COMMON_FIELDS_DECLARED)
        self.assertEqual(set(original["people"][0]), views.PERSON_FIELDS_DECLARED)
        self.assertEqual(set(original["branches"][0]), views.BRANCH_FIELDS_DECLARED)

    def test_unknown_field_does_not_leak(self):
        original = views._raw_data
        def with_unknown_field(now):
            d = original(now)
            d["extra"] = "secret-value"
            d["people"][0]["extra"] = "secret-value"
            d["branches"][0]["extra"] = "secret-value"
            return d
        views._raw_data = with_unknown_field
        try:
            for role in (security.ADMIN, security.VIEWER, security.WALL):
                self.assertNotIn("secret-value", json.dumps(views.role_view(role, NOW)), role)
        finally:
            views._raw_data = original

    def test_unknown_role_sees_least(self):
        self.assertNotIn(EMAIL, json.dumps(views.role_view("role-unknown", NOW)))

    def test_history_wall_has_no_email(self):
        rows = views.history_view(security.WALL, NOW)["items"]
        self.assertTrue(rows)
        self.assertNotIn("@example.com", json.dumps(rows))
        self.assertIn("@example.com", json.dumps(views.history_view(security.VIEWER, NOW)["items"]))

    def test_history_unknown_field_does_not_leak(self):
        original = views.HISTORY.read
        views.HISTORY.read = lambda now: {"now": 1, "since": 0, "items": [{"at": 1, "name": "An", "account": EMAIL, "status": "working", "delegating": [0, 0, 0], "extra": "secret-value"}]}
        try:
            for role in (security.VIEWER, security.WALL):
                self.assertNotIn("secret-value", json.dumps(views.history_view(role, NOW)))
        finally:
            views.HISTORY.read = original


class ViaHttp(unittest.TestCase):
    """Goes through the real /data and /history paths, to be sure the routes use the view.
    Đi qua đúng đường /data và /history, để chắc route dùng khung nhìn."""

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": ""}, "wall": {"role": security.WALL, "secret": ""}}}
        for name in ("adm", "viewer", "wall"):
            login.SESSIONS.sessions["tok-" + name] = (name, NOW + 3600)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def fetch(self, path, name):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers={"Cookie": "session=tok-" + name})
        with urllib.request.urlopen(r) as x:
            return json.loads(x.read())

    def test_data_by_role(self):
        self.assertEqual(self.fetch("/data", "adm")["role"], security.ADMIN)
        self.assertIn("unnamedGroups", self.fetch("/data", "adm"))
        self.assertNotIn("unnamedGroups", self.fetch("/data", "viewer"))
        wall = self.fetch("/data", "wall")
        self.assertEqual(wall["role"], security.WALL)
        self.assertEqual(wall["uiVersion"], assets.UI_VERSION)
        self.assertNotIn("@example.com", json.dumps(wall))

    def test_history_by_role(self):
        self.assertNotIn("@example.com", json.dumps(self.fetch("/history", "wall")))

    def test_not_logged_in(self):
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen("http://127.0.0.1:%d/data" % self.port)
        self.assertEqual(err.exception.code, 401)

    def test_admin_page_gets_unnamedGroups_and_customNetworks(self):
        d = self.fetch("/admin/data", "adm")
        self.assertIn("unnamedGroups", d)
        self.assertTrue(any(b.get("customNetworks") for b in d["branches"]))


class SafeDefaults(unittest.TestCase):
    def test_listens_internal_and_has_timeout(self):
        with open(settings.__file__, encoding="utf-8") as f:
            self.assertIn('BIND_ADDR = os.environ.get("BIND_ADDR", "127.0.0.1")', f.read())
        self.assertEqual(w.Handler.timeout, 30)
        self.assertNotIn("Python", w.Handler.sys_version)

    def test_login_page_asks_for_account(self):
        stores.ACCOUNTS.d.setdefault("accounts", {})["temp"] = {"role": security.VIEWER, "secret": "JBSWY3DPEHPK3PXP"}
        try:
            b = pages.page_login().decode()
            self.assertIn('name="account"', b)
            self.assertIn('name="code"', b)
        finally:
            stores.ACCOUNTS.d["accounts"].pop("temp", None)


class BoardPage(unittest.TestCase):
    def test_every_cell_has_label_for_card_view_on_narrow_screen(self):
        seed()
        b = pages.page_board("adm", NOW).decode()
        for label in ("Status", "Model", "Quota", "Today", "Tokens in / out", "Delegated", "Plugin", "Updated"):
            self.assertIn("data-label='%s'" % label, b)
        self.assertIn("Whole team (", b)

    def test_several_devices_show_version_per_device_and_dim_quiet_ones(self):
        new = {"v": 1, "device": "device-two1", "name": "Two", "account": "two@example.com", "lanIp": "192.168.9.1",
               "updatedAt": int(NOW * 1000), "pluginVersion": "0.25.1"}
        old = dict(new, device="device-two2", lanIp="192.168.9.2", updatedAt=int((NOW - 3 * 86400) * 1000), pluginVersion="0.24.0")
        r = [h for h in devices.group_by_person([new, old], NOW) if h["name"] == "Two"][0]
        self.assertEqual(len(pages.active_devices(r, NOW)), 1)
        cell = pages.device_version_cell(r, "0.25.1", NOW)
        self.assertIn("0.25.1</span> <span class=note>192.168.9.1 · sent ", cell)
        self.assertIn('<div class="device off" title="This device has not sent since', cell)
        self.assertIn("0.24.0 <span class=note>192.168.9.2 · sent ", cell)
        self.assertNotIn('class="waiting"', cell)
        one = devices.group_by_person([new], NOW)[0]
        self.assertEqual(pages.device_version_cell(one, "0.25.1", NOW), pages.version_cell(["0.25.1"], "0.25.1"))

    def test_same_hardware_mark_is_one_device_with_earlier_ip(self):
        mark = "ab" * 16
        new = {"v": 1, "device": "device-mark1", "name": "Mark", "account": "mark@example.com", "lanIp": "192.168.9.79",
               "updatedAt": int(NOW * 1000), "pluginVersion": "0.25.2", "hardwareMark": mark}
        old = dict(new, device="device-mark2", lanIp="192.168.9.67", updatedAt=int((NOW - 3600) * 1000), pluginVersion="0.24.0")
        r = devices.group_by_person([devices.clean_payload(new, NOW), devices.clean_payload(old, NOW)], NOW)[0]
        self.assertEqual(len(pages.physical_devices(r)), 1)
        cell = pages.device_version_cell(r, "0.25.2", NOW)
        self.assertIn("0.25.2", cell)
        self.assertNotIn("0.24.0", cell)
        self.assertIn("before: 192.168.9.67 until ", cell)
        self.assertNotIn(mark, pages.page_board("adm", NOW).decode())
        self.assertNotIn("hardwareMark", devices.clean_payload(dict(new, hardwareMark="NOT-HEX"), NOW))

    def test_ip_history_merges_and_expires(self):
        day = 86_400_000
        old = [{"ip": "a", "from": 0, "to": 5 * day}, {"ip": "b", "from": 0, "to": 1}]
        out = devices.add_ip_history(old, "a", 40 * day)
        self.assertEqual(out, [{"ip": "a", "from": 0, "to": 40 * day}])
        out = devices.add_ip_history(out, "c", 41 * day)
        self.assertEqual([e["ip"] for e in out], ["c", "a"])
        many = [{"ip": str(i), "from": i, "to": i} for i in range(30)]
        self.assertEqual(len(devices.add_ip_history(many, "x", 31)), settings.IP_HISTORY_MAX)

    def test_ingest_keeps_server_ip_history_not_the_devices(self):
        raw = {"v": 1, "device": "device-iphist", "name": "Ip", "account": "ip@example.com", "updatedAt": int(time.time() * 1000),
               "lanIp": "192.168.5.1", "ipHistory": [{"ip": "6.6.6.6", "from": 1, "to": 1}]}
        t = time.time()
        devices.save_ingest(devices.clean_payload(raw, t), t)
        devices.save_ingest(devices.clean_payload(dict(raw, lanIp="192.168.5.2"), t), t + 60)
        try:
            self.assertEqual([e["ip"] for e in devices.read_device("device-iphist")["ipHistory"]], ["192.168.5.2", "192.168.5.1"])
        finally:
            drop_device("device-iphist")


class MsiPackage(unittest.TestCase):
    """AI Worker.msi: the server fills its own address into the placeholder at the same length, and refuses when that is not safe.
    Gói AI Worker.msi: máy chủ điền địa chỉ của nó vào chỗ giữ chỗ, giữ nguyên độ dài, và từ chối khi không an toàn."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = packages.MENUBAR_DIR
        packages.MENUBAR_DIR = self.tmp

    def tearDown(self):
        packages.MENUBAR_DIR = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, body):
        with open(os.path.join(self.tmp, "AI-Worker.msi"), "wb") as f:
            f.write(body)

    def test_fills_the_address(self):
        self.write(b"head" + packages.MSI_PLACEHOLDER + b"tail")
        package = packages.menubar_msi("https://board.example.com/")  # the board address as the server builds it, with a trailing slash
        self.assertEqual(len(package), len(packages.MSI_PLACEHOLDER) + 8)
        self.assertTrue(package.startswith(b"headhttps://board.example.com "))
        self.assertTrue(package.endswith(b" tail"))
        self.assertNotIn(packages.MSI_PLACEHOLDER, package)

    def test_refuses(self):
        self.assertIsNone(packages.menubar_msi("https://board.example.com"))  # no package yet
        self.write(b"x" + packages.MSI_PLACEHOLDER + packages.MSI_PLACEHOLDER)
        self.assertIsNone(packages.menubar_msi("https://board.example.com"))  # placeholder twice
        self.write(packages.MSI_PLACEHOLDER)
        for bad in ("https://a.com/\"x", "https://" + "a" * 200 + ".com", "ftp://a.com", "https://a.com/path"):
            self.assertIsNone(packages.menubar_msi(bad), bad)


class RoutePermissions(unittest.TestCase):
    """Pins the current permission of each path and each role, so the permission gate can be changed without changing behavior.
    Chốt quyền hiện tại của từng đường dẫn và từng vai, để sửa cổng kiểm quyền mà không đổi hành vi."""

    # path: (not logged in, view only, wall, admin, TV screen)
    # đường dẫn: (chưa đăng nhập, chỉ xem, treo tường, quản trị, màn hình TV)
    GET = {
        "/": (200, 200, 200, 200, 200),
        "/?frame=wall": (200, 200, 200, 200, 200),
        "/board": (200, 200, 303, 200, 303),
        "/tv": (200, 303, 303, 303, 303),
        "/admin": (200, 303, 303, 200, 303),
        "/admin/data": (401, 403, 403, 200, 403),
        "/admin/data?month=2026-11": (401, 403, 403, 200, 403),
        "/data": (401, 200, 200, 200, 200),
        "/history": (401, 200, 200, 200, 200),
        "/mini": (200, 200, 200, 200, 200),
        "/mini?h=wrong": (303, 303, 303, 303, 303),
        "/mini/state": (401, 403, 403, 403, 200),
        # the extension's key goes only in the Authorization header: no cookie, not even a TV's, opens it
        # khoá của tiện ích chỉ đi trong header Authorization: không cookie nào, kể cả của TV, mở được
        "/ext/state": (401, 401, 401, 401, 401),
        "/ext/data": (401, 401, 401, 401, 401),
        "/ext/mini": (401, 401, 401, 401, 401),
        "/ext/mini?lang=vi": (401, 401, 401, 401, 401),
        "/mini/pair": (200, 200, 200, 200, 200),
        "/mini/logo-black.png": (200, 200, 200, 200, 200),
        "/mini/logo-white.png": (200, 200, 200, 200, 200),
        "/mini-pair.js": (200, 200, 200, 200, 200),
        "/menubar/install-mac.zip": (401, 403, 403, 200, 403),
        "/menubar/install-windows.zip": (401, 403, 403, 200, 403),
        "/menubar/install-windows.msi": (401, 403, 403, 200 if packages.menubar_msi("https://board.example.com") else 404, 403),
        "/menubar/install-mac.dmg": (401, 403, 403, 404, 403),
        "/menubar/install-ubuntu.deb": (401, 403, 403, 200, 403),
        "/static/mini.js": (401, 200, 200, 200, 200),
        "/static/ops.js": (401, 200, 200, 200, 200),
        "/static/missing.js": (401, 404, 404, 404, 404),
        "/static/../webhook.py": (401, 404, 404, 404, 404),
        "/robots.txt": (200, 200, 200, 200, 200),
        "/health": (200, 200, 200, 200, 200),
        "/login.js": (200, 200, 200, 200, 200),
        "/tv.js": (200, 200, 200, 200, 200),
        "/tv-qr.js": (200, 200, 200, 200, 200),
        "/tv/install-windows.bat": (200, 200, 200, 200, 200),
        "/tv/install-mac.zip": (200, 200, 200, 200, 200),
        "/releases/latest.json": (401, 401, 401, 401, 401),
        "/releases/ai-worker-1.0.0.zip": (401, 401, 401, 401, 401),
        "/missing": (404, 404, 404, 404, 404),
    }
    POST_ADMIN = ("/locations", "/team-csv", "/team-sale", "/admin/confirm", "/admin/accounts", "/admin/sessions",
                     "/admin/tv-view", "/admin/tv-approve", "/admin/tv-revoke", "/admin/tv-rename", "/admin/tv-reload")
    NEEDS_OTP_CONFIRM = ("/admin/accounts", "/admin/sessions", "/admin/tv-view", "/admin/tv-approve",
                        "/admin/tv-revoke", "/admin/tv-rename")

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": ""}, "wall": {"role": security.WALL, "secret": ""}}}
        for name in ("adm", "viewer", "wall"):
            login.SESSIONS.sessions["tok-" + name] = (name, NOW + 3600)
        cls.tv_id, cls.tv_token = stores.TV.create({"name": "Test TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        cls.token = (None, "tok-viewer", "tok-wall", "tok-adm", cls.tv_token)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        cls.origin = "http://127.0.0.1:%d" % cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        # this table calls many 401/404 in a row, they must not count as probing paths
        # bảng này gọi nhiều 401/404 liên tiếp, không để bị tính là dò đường dẫn
        security.BOT.__init__()
        login.SESSIONS.confirmed_at.clear()

    def call(self, method, path, token=None, body=None, **headers):
        security.BOT.__init__()
        headers = {k.replace("_", "-"): v for k, v in headers.items()}
        if token:
            headers["Cookie"] = "session=" + token
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def test_get_by_role(self):
        for path, expected in self.GET.items():
            for token, status in zip(self.token, expected):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.call("GET", path, token)[0], status)

    def test_mini_actions_only_for_paired_computer(self):
        for path in ("/mini/handoff", "/mini/settings", "/mini/unpair"):
            for token, status in zip(self.token, (401, 403, 403, 403)):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.call("POST", path, token, "{}", Origin=self.origin)[0], status)

    def test_mini_handoff_gives_session_once(self):
        status, b = self.call("POST", "/mini/handoff", self.tv_token)
        self.assertEqual(status, 200)
        code = json.loads(b)["code"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request("GET", "/mini?h=" + code)
            r = conn.getresponse()
            r.read()
            self.assertEqual(r.status, 303)
            self.assertEqual(r.getheader("Location"), "/mini")
            self.assertIn("session=" + self.tv_token, r.getheader("Set-Cookie") or "")
            conn.request("GET", "/mini?h=" + code)
            r = conn.getresponse()
            r.read()
            self.assertIsNone(r.getheader("Set-Cookie"))
        finally:
            conn.close()

    def test_mini_handoff_carries_the_chosen_language(self):
        code = json.loads(self.call("POST", "/mini/handoff", self.tv_token)[1])["code"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request("GET", "/mini?h=%s&lang=vi" % code)
            r = conn.getresponse()
            r.read()
            cookies = r.msg.get_all("Set-Cookie") or []
            self.assertEqual(r.status, 303)
            self.assertTrue(any(c.startswith("session=") for c in cookies))
            self.assertTrue(any(c.startswith("lang=vi;") for c in cookies))
            conn.request("GET", "/mini?lang=xx")
            r = conn.getresponse()
            r.read()
            self.assertFalse(any((c or "").startswith("lang=") for c in (r.msg.get_all("Set-Cookie") or [])))
        finally:
            conn.close()

    def test_mini_settings_saved_and_checked(self):
        self.assertEqual(self.call("POST", "/mini/settings", self.tv_token, '{"notify": false, "notifyMinutes": 15}', Origin=self.origin)[0], 200)
        state = json.loads(self.call("GET", "/mini/state", self.tv_token)[1])
        self.assertEqual((state["notify"], state["notifyMinutes"]), (False, 15))
        for bad in ('{"notify": true, "notifyMinutes": 7}', '{"notify": 1, "notifyMinutes": 10}', '{"notify": true, "notifyMinutes": true}', '[]'):
            with self.subTest(body=bad):
                self.assertEqual(self.call("POST", "/mini/settings", self.tv_token, bad, Origin=self.origin)[0], 400)
        self.assertEqual(self.call("POST", "/mini/settings", self.tv_token, '{"notify": true, "notifyMinutes": 10}')[0], 403)

    def self_pair(self, account, secret_bytes, code, otp_step_offset=0):
        otp = security.totp_code(secret_bytes, int(time.time() // 30) + otp_step_offset)
        return self.call("POST", "/mini/pair", None, json.dumps({"account": account, "otp": otp, "code": code}), Origin=self.origin)

    def test_mini_self_pair_with_own_otp(self):
        import base64
        secret = b"0123456789abcdef0123"
        saved = dict(stores.ACCOUNTS.d["accounts"])
        stores.ACCOUNTS.d["accounts"].update({"mgr": {"role": security.VIEWER, "secret": base64.b32encode(secret).decode()},
                                         "wallacc": {"role": security.WALL, "secret": base64.b32encode(secret).decode()}})
        try:
            login.SESSIONS.__init__()
            login.SESSIONS.sessions.update({"tok-" + n: (n, NOW + 3600) for n in ("adm", "viewer", "wall")})
            login.SESSIONS.used_step.clear()
            # a request from another IP cannot be approved from here
            # yêu cầu từ IP khác không duyệt được từ đây
            other, _ = stores.TV_PAIRING.request_code("", "10.9.9.9", "test", time.time(), menubar=True)
            self.assertEqual(self.self_pair("mgr", secret, other)[0], 400)
            login.SESSIONS.used_step.clear()
            # a wrong OTP is refused and counted
            # OTP sai bị từ chối và bị đếm
            code, key = stores.TV_PAIRING.request_code("", "127.0.0.1", "test", time.time(), menubar=True)
            status, b = self.call("POST", "/mini/pair", None, json.dumps({"account": "mgr", "otp": "000000", "code": code}), Origin=self.origin)
            self.assertEqual(status, 401)
            # a wall account may not own a menu bar computer
            # tài khoản treo tường không được có máy thanh menu
            self.assertEqual(self.self_pair("wallacc", secret, code)[0], 403)
            login.SESSIONS.used_step.clear()
            # the right OTP pairs it: the computer then gets its session by polling with its own key
            # OTP đúng thì ghép xong: máy nhận phiên khi hỏi bằng khoá của chính nó
            self.assertEqual(self.self_pair("mgr", secret, code)[0], 200)
            r = stores.TV_PAIRING.poll(key, time.time())
            self.assertEqual(r["owner"], "mgr")
            tv_id, token = stores.TV.create(r, time.time())
            self.assertEqual(stores.TV.d[tv_id]["owner"], "mgr")
            self.assertNotIn("mgr", json.dumps(stores.TV.d[tv_id]["hash"]))
            # Origin is required
            # bắt buộc có Origin
            self.assertEqual(self.call("POST", "/mini/pair", None, json.dumps({"account": "mgr", "otp": "1", "code": code}))[0], 403)
            # at most MENUBAR_PER_ACCOUNT computers per account
            # mỗi tài khoản tối đa MENUBAR_PER_ACCOUNT máy
            for _ in range(settings.MENUBAR_PER_ACCOUNT - 1):
                stores.TV.create({"name": "x", "approvedBy": "mgr", "owner": "mgr", "ip": "127.0.0.1", "device": "t"}, time.time())
            code3, _ = stores.TV_PAIRING.request_code("", "127.0.0.1", "test", time.time(), menubar=True)
            login.SESSIONS.used_step.clear()
            self.assertEqual(self.self_pair("mgr", secret, code3, 1)[0], 409)
            # ending the account's sessions removes its computers
            # kết thúc phiên của tài khoản thì gỡ các máy của nó
            self.assertEqual(len(stores.TV.revoke_owner("mgr")), settings.MENUBAR_PER_ACCOUNT)
            self.assertEqual(stores.TV.owned_by("mgr", time.time()), 0)
            self.assertIsNone(stores.TV.find(token, time.time()))
        finally:
            stores.ACCOUNTS.d["accounts"] = saved
            login.SESSIONS.__init__()
            login.SESSIONS.sessions.update({"tok-" + n: (n, NOW + 3600) for n in ("adm", "viewer", "wall")})

    def with_manager(self, test):
        """Runs test(secret) with a viewer account "mgr" that has an OTP secret, then puts the accounts and sessions back.
        Chạy test(secret) với tài khoản xem "mgr" có khoá OTP, rồi trả lại tài khoản và phiên như cũ."""
        import base64
        secret = b"0123456789abcdef0123"
        saved = dict(stores.ACCOUNTS.d["accounts"])
        stores.ACCOUNTS.d["accounts"]["mgr"] = {"role": security.VIEWER, "secret": base64.b32encode(secret).decode()}
        stores.TV_PAIRING.__init__()
        try:
            login.SESSIONS.__init__()
            login.SESSIONS.sessions.update({"tok-" + n: (n, NOW + 3600) for n in ("adm", "viewer", "wall")})
            test(secret)
        finally:
            stores.TV.revoke_owner("mgr")
            stores.TV_PAIRING.__init__()
            stores.ACCOUNTS.d["accounts"] = saved
            login.SESSIONS.__init__()
            login.SESSIONS.sessions.update({"tok-" + n: (n, NOW + 3600) for n in ("adm", "viewer", "wall")})

    def test_self_pair_counts_codes_approved_but_not_joined(self):
        def test(secret):
            # three codes from one computer's IP, approved before any of them joined: only MENUBAR_PER_ACCOUNT pass
            # ba mã từ IP của một máy, được duyệt trước khi mã nào nhận phiên: chỉ MENUBAR_PER_ACCOUNT mã qua được
            codes = [stores.TV_PAIRING.request_code("", "127.0.0.1", "AI Worker menu bar (macOS)", time.time(), menubar=True) for _ in range(3)]
            results = []
            for i, (code, _) in enumerate(codes):
                login.SESSIONS.used_step.clear()
                results.append(self.self_pair("mgr", secret, code, i % 2)[0])
            self.assertEqual(results, [200] * settings.MENUBAR_PER_ACCOUNT + [409] * (3 - settings.MENUBAR_PER_ACCOUNT))
            for _, key in codes:
                r = stores.TV_PAIRING.poll(key, time.time())
                if isinstance(r, dict):
                    stores.TV.create(r, time.time())
            self.assertEqual(stores.TV.owned_by("mgr", time.time()), settings.MENUBAR_PER_ACCOUNT)
            # the store checks again when the computer joins, so a request approved some other way cannot pass the limit either
            # kho kiểm lại khi máy nhận phiên, nên yêu cầu được duyệt bằng đường khác cũng không vượt được giới hạn
            with self.assertRaises(ValueError):
                stores.TV.create({"name": "extra", "approvedBy": "mgr", "owner": "mgr", "ip": "127.0.0.1", "device": "t"}, time.time())
            self.assertEqual(stores.TV.owned_by("mgr", time.time()), settings.MENUBAR_PER_ACCOUNT)
        self.with_manager(test)

    def test_self_pair_joining_past_the_limit_answers_expired(self):
        def test(secret):
            code, key = stores.TV_PAIRING.request_code("", "127.0.0.1", "AI Worker menu bar (macOS)", time.time(), menubar=True)
            login.SESSIONS.used_step.clear()
            self.assertEqual(self.self_pair("mgr", secret, code)[0], 200)
            for _ in range(settings.MENUBAR_PER_ACCOUNT):
                stores.TV.create({"name": "x", "approvedBy": "mgr", "owner": "mgr", "ip": "127.0.0.1", "device": "t"}, time.time())
            status, b = self.call("POST", "/tv/poll", None, "", Cookie="tv-pending=" + key)
            self.assertEqual((status, json.loads(b)["status"]), (200, "expired"))
            self.assertEqual(stores.TV.owned_by("mgr", time.time()), settings.MENUBAR_PER_ACCOUNT)
        self.with_manager(test)

    def test_self_pair_only_for_menu_bar_requests(self):
        def test(secret):
            # a wall TV and a browser extension on the same IP (office NAT): a viewer cannot approve them, only an admin can
            # TV treo tường và tiện ích trình duyệt cùng IP (NAT văn phòng): người xem không duyệt được, chỉ quản trị duyệt được
            tv_ua = "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) Version/6.0 TV Safari/537.36"
            conn = http.client.HTTPConnection("127.0.0.1", self.port)
            try:
                # at most TV_PENDING_PER_IP codes wait per IP: the approved ones go first and leave the list
                # mỗi IP tối đa TV_PENDING_PER_IP mã chờ: mã được duyệt đi trước và rời danh sách
                for ua, path, can in (("AIWorkerMenuBar/1.0 (Windows)", "/tv/request-code", True), ("AI Worker menu bar app (macOS)", "/tv/request-code", True),
                                      ("AI Worker thanh menu app (macOS)", "/tv/request-code", True),
                                      (tv_ua, "/tv/request-code", False), ("AI Worker menu bar (Linux)", "/ext/request-code", False),
                                      ("Mozilla/5.0 Chrome/130.0.0.0", "/tv/request-code", False)):
                    with self.subTest(ua=ua, path=path):
                        conn.request("POST", path, "", {"User-Agent": ua})
                        r = conn.getresponse()
                        code = json.loads(r.read())["code"]
                        login.SESSIONS.used_step.clear()
                        self.assertEqual(self.self_pair("mgr", secret, code)[0], 200 if can else 400)
                        if can:
                            stores.TV_PAIRING.pending.pop(code)
            finally:
                conn.close()
            # the refused codes still wait for an admin
            # các mã bị từ chối vẫn chờ quản trị duyệt
            self.assertEqual(sum(1 for r in stores.TV_PAIRING.pending.values() if not r["name"]), 3)
        self.with_manager(test)

    def test_mini_handoff_refuses_links_from_other_sites(self):
        code = json.loads(self.call("POST", "/mini/handoff", self.tv_token)[1])["code"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            # a link on another site: no session is set, and the code is not used up
            # đường dẫn trên trang khác: không đặt phiên, và mã chưa bị dùng mất
            for site in ("cross-site", "same-site"):
                conn.request("GET", "/mini?h=" + code, headers={"Sec-Fetch-Site": site})
                r = conn.getresponse()
                r.read()
                self.assertEqual((r.status, r.getheader("Location")), (303, "/mini"))
                self.assertIsNone(r.getheader("Set-Cookie"))
            # a person logged in to this browser keeps their own session
            # người đã đăng nhập trong trình duyệt này giữ phiên của mình
            conn.request("GET", "/mini?h=" + code, headers={"Cookie": "session=tok-viewer", "Sec-Fetch-Site": "none"})
            r = conn.getresponse()
            r.read()
            self.assertIsNone(r.getheader("Set-Cookie"))
            # the menu bar opening the address itself still works, once
            # thanh menu tự mở địa chỉ thì vẫn được, một lần
            conn.request("GET", "/mini?h=" + code, headers={"Sec-Fetch-Site": "none"})
            r = conn.getresponse()
            r.read()
            self.assertIn("session=" + self.tv_token, r.getheader("Set-Cookie") or "")
        finally:
            conn.close()

    def test_mini_handoff_keeps_few_codes_per_computer(self):
        codes = [json.loads(self.call("POST", "/mini/handoff", self.tv_token)[1])["code"] for _ in range(settings.MINI_HANDOFF_PER_TOKEN + 2)]
        live = [c for c in codes if c in stores.MINI_HANDOFF.codes]
        self.assertEqual(live, codes[-settings.MINI_HANDOFF_PER_TOKEN:])
        for c in live:
            stores.MINI_HANDOFF.take(c, time.time())

    def test_mini_unpair_removes_only_this_computer(self):
        own_id, own_token = stores.TV.create({"name": "Menu bar test", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        status, _ = self.call("POST", "/mini/unpair", own_token, "{}", Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertNotIn(own_id, stores.TV.d)
        self.assertEqual(self.call("GET", "/mini/state", own_token)[0], 401)
        self.assertEqual(self.call("GET", "/mini/state", self.tv_token)[0], 200)

    def test_menubar_installer_has_address_and_no_secret(self):
        import io, zipfile
        status, b = self.call("GET", "/menubar/install-mac.zip", "tok-adm", Host="board.example.com")
        self.assertEqual(status, 200)
        z = zipfile.ZipFile(io.BytesIO(b))
        names = z.namelist()
        self.assertIn("AI-Worker-menu-bar/Install AI Worker menu bar.command", names)
        self.assertIn("AI-Worker-menu-bar/icon-black.png", names)
        script = z.read("AI-Worker-menu-bar/Install AI Worker menu bar.command").decode()
        self.assertIn('BOARD_URL="http://board.example.com/"', script)
        self.assertEqual(z.getinfo("AI-Worker-menu-bar/Install AI Worker menu bar.command").external_attr >> 16 & 0o777, 0o755)
        everything = b"".join(z.read(n) for n in names)
        self.assertNotIn(self.tv_token.encode(), everything)
        status, b = self.call("GET", "/menubar/install-windows.zip", "tok-adm", Host="board.example.com")
        self.assertIn("AI-Worker-menu-bar/install-menubar.ps1", zipfile.ZipFile(io.BytesIO(b)).namelist())
        self.assertEqual(self.call("GET", "/menubar/install-mac.zip", "tok-adm", Host="bad host\"x")[0], 400)

    def test_menubar_deb_is_a_debian_package_with_the_address(self):
        import io, tarfile
        status, b = self.call("GET", "/menubar/install-ubuntu.deb", "tok-adm", Host="board.example.com")
        self.assertEqual(status, 200)
        self.assertTrue(b.startswith(b"!<arch>\ndebian-binary   "))
        members, pos = {}, 8
        while pos < len(b):
            name, size = b[pos:pos + 16].decode().strip(), int(b[pos + 48:pos + 58].decode().strip())
            members[name] = b[pos + 60:pos + 60 + size]
            pos += 60 + size + size % 2
        self.assertEqual(list(members), ["debian-binary", "control.tar.gz", "data.tar.gz"])
        self.assertEqual(members["debian-binary"], b"2.0\n")
        control = tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"])).extractfile("./control").read().decode()
        self.assertIn("Package: ai-worker-menubar", control)
        self.assertIn("ayatanaappindicator3", control)
        data = tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]))
        names = data.getnames()
        for n in ("./usr/bin/ai-worker-menubar", "./etc/xdg/autostart/ai-worker-menubar.desktop", "./usr/lib/ai-worker-menubar/ai-worker-indicator.py",
                  "./usr/lib/ai-worker-menubar/ai-worker.1m.py", "./usr/lib/ai-worker-menubar/icons/icon-white.png"):
            self.assertIn(n, names)
        self.assertEqual(data.getmember("./usr/bin/ai-worker-menubar").mode, 0o755)
        self.assertEqual(json.loads(data.extractfile("./usr/lib/ai-worker-menubar/config.json").read())["server"], "http://board.example.com")
        everything = b"".join(data.extractfile(m).read() for m in data.getmembers() if m.isfile())
        self.assertNotIn(self.tv_token.encode(), everything)

    def test_menubar_dmg_only_when_built_next_to_the_app(self):
        import tempfile
        old = packages.MENUBAR_MAC_APP
        with tempfile.TemporaryDirectory() as d:
            try:
                packages.MENUBAR_MAC_APP = os.path.join(d, "AI-Worker-menu-bar-mac-app.zip")
                with open(packages.MENUBAR_MAC_APP, "wb") as f:
                    f.write(b"PK zip")
                self.assertEqual(self.call("GET", "/menubar/install-mac.dmg", "tok-adm", Host="board.example.com")[0], 404)
                self.assertFalse(views.admin_data(time.time(), "", "")["menubarDmg"])
                with open(os.path.join(d, "AI-Worker-menu-bar-mac-app.dmg"), "wb") as f:
                    f.write(b"dmg bytes")
                status, b = self.call("GET", "/menubar/install-mac.dmg", "tok-adm", Host="board.example.com")
                self.assertEqual((status, b), (200, b"dmg bytes"))
                self.assertTrue(views.admin_data(time.time(), "", "")["menubarDmg"])
                self.assertEqual(self.call("GET", "/menubar/install-mac.zip", "tok-adm", Host="board.example.com")[1], b"PK zip")
            finally:
                packages.MENUBAR_MAC_APP = old

    def test_mini_state_has_wall_names_only(self):
        state = json.loads(self.call("GET", "/mini/state", self.tv_token)[1])
        self.assertNotIn("@", json.dumps(state))

    def test_not_logged_in_sees_no_data(self):
        for path in ("/", "/board", "/admin", "/tv"):
            with self.subTest(path=path):
                self.assertNotIn(EMAIL.encode(), self.call("GET", path)[1])

    def test_post_admin_blocks_other_roles(self):
        for path in self.POST_ADMIN:
            for token, status in ((None, 401), ("tok-viewer", 403), ("tok-wall", 403), (self.tv_token, 403)):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.call("POST", path, token, "{}", Origin=self.origin)[0], status)

    def test_post_wrong_origin(self):
        for path in self.POST_ADMIN:
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path, "tok-adm", "{}", Origin="https://other.example.com")[0], 403)

    def test_account_actions_require_origin(self):
        # OTP already re-entered, so a 403 here can only come from a missing origin
        # đã nhập lại OTP, để 403 ở đây chỉ có thể là do thiếu nguồn
        login.SESSIONS.confirmed_at["tok-adm"] = time.time()
        for path in self.POST_ADMIN:
            if path.startswith("/admin/"):
                with self.subTest(path=path):
                    status, body = self.call("POST", path, "tok-adm", "{}")
                    self.assertEqual(status, 403)
                    self.assertEqual(json.loads(body)["error"], "Wrong origin")

    def test_sensitive_actions_need_otp_confirm(self):
        for path in self.NEEDS_OTP_CONFIRM:
            with self.subTest(path=path):
                status, body = self.call("POST", path, "tok-adm", "{}", Origin=self.origin)
                self.assertEqual(status, 403)
                self.assertTrue(json.loads(body).get("needsConfirm"))

    def test_screen_reload_needs_no_otp_confirm(self):
        status, body = self.call("POST", "/admin/tv-reload", "tok-adm", "{}", Origin=self.origin)
        self.assertNotIn(b"needsConfirm", body)
        self.assertNotIn(status, (401, 403))

    def test_after_otp_confirm_passes_gate(self):
        login.SESSIONS.confirmed_at["tok-adm"] = time.time()
        for path in self.NEEDS_OTP_CONFIRM:
            with self.subTest(path=path):
                self.assertNotIn(self.call("POST", path, "tok-adm", "{}", Origin=self.origin)[0], (401, 403))

    def test_ingest_accepts_only_ingest_key(self):
        self.assertEqual(self.call("POST", "/ingest", None, "{}")[0], 401)
        self.assertEqual(self.call("POST", "/ingest", "tok-adm", "{}")[0], 401)
        self.assertEqual(self.call("POST", "/ingest", None, "{}", Authorization="Bearer wrong")[0], 401)
        self.assertEqual(self.call("POST", "/ingest", None, "{}", Authorization="Bearer test")[0], 400)

    def test_post_unknown_route(self):
        self.assertEqual(self.call("POST", "/missing", "tok-adm", "{}")[0], 404)

    def test_tv_pair_wrong_origin(self):
        for path in ("/tv/request-code", "/tv/poll"):
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path, None, "", Origin="https://other.example.com")[0], 403)

    def test_role_downgrade_takes_effect_immediately(self):
        login.SESSIONS.sessions["tok-demoted"] = ("demoted", NOW + 3600)
        stores.ACCOUNTS.d["accounts"]["demoted"] = {"role": security.ADMIN, "secret": ""}
        try:
            self.assertEqual(self.call("GET", "/admin/data", "tok-demoted")[0], 200)
            stores.ACCOUNTS.d["accounts"]["demoted"]["role"] = security.VIEWER
            self.assertEqual(self.call("GET", "/admin/data", "tok-demoted")[0], 403)
            del stores.ACCOUNTS.d["accounts"]["demoted"]
            self.assertEqual(self.call("GET", "/data", "tok-demoted")[0], 401)
        finally:
            stores.ACCOUNTS.d["accounts"].pop("demoted", None)
            login.SESSIONS.sessions.pop("tok-demoted", None)

    def test_tv_revoke_takes_effect_immediately(self):
        tv_id, token = stores.TV.create({"name": "Revoked TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        self.assertEqual(self.call("GET", "/data", token)[0], 200)
        stores.TV.revoke(tv_id)
        self.assertEqual(self.call("GET", "/data", token)[0], 401)

    def test_tv_self_exit_loses_session_but_keeps_row_for_repair(self):
        tv_id, token = stores.TV.create({"name": "Exited TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        stores.TV_STATUS.mark_seen(tv_id, "", time.time())
        try:
            self.assertEqual(self.call("POST", "/logout", token)[0], 303)
            self.assertEqual(self.call("GET", "/data", token)[0], 401)
            row = next(x for x in stores.TV.list_screens(time.time()) if x["id"] == tv_id)
            self.assertEqual(row["name"], "Exited TV")
            self.assertTrue(row["exitedAt"])
            self.assertNotIn("hash", row)
            admin_row = next(x for x in views.admin_data(time.time(), "", "")["screens"] if x["id"] == tv_id)
            self.assertFalse(admin_row["running"])
            self.assertIsNone(admin_row["upToDate"])
            # a duplicate name must choose to replace the old row
            # trùng tên thì phải chọn thay cho dòng cũ
            with self.assertRaises(ValueError):
                stores.TV.check_name("Exited TV", "", time.time())
            tv_id2, token2 = stores.TV.create({"name": "Exited TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test", "replaceId": tv_id}, time.time())
            self.assertNotIn(tv_id, stores.TV.d)
            self.assertFalse(next(x for x in stores.TV.list_screens(time.time()) if x["id"] == tv_id2)["exitedAt"])
            self.assertEqual(self.call("GET", "/data", token2)[0], 200)
            stores.TV.revoke(tv_id2)
        finally:
            stores.TV.d.pop(tv_id, None)

    def test_releases_need_ingest_key_and_serve_only_valid_names(self):
        auth = "Bearer " + settings.INGEST_KEY
        original = assets.RELEASES_DIR
        assets.RELEASES_DIR = tmp_dir = tempfile.mkdtemp(dir=TMP)
        try:
            # not released yet: an empty 200, it must not count as probing paths
            # chưa phát hành: 200 rỗng, không được tính là dò đường dẫn
            self.assertEqual(self.call("GET", "/releases/latest.json", None, None, Authorization=auth), (200, b"{}"))
            for name, body in (("latest.json", b'{"a":1}'), ("latest.json.sig", b"ky"), ("ai-worker-1.0.0.zip", b"zip"), ("secret.txt", b"x")):
                with open(os.path.join(tmp_dir, name), "wb") as f:
                    f.write(body)
            self.assertEqual(self.call("GET", "/releases/latest.json", None, None, Authorization=auth), (200, b'{"a":1}'))
            self.assertEqual(self.call("GET", "/releases/latest.json.sig", None, None, Authorization=auth), (200, b"ky"))
            self.assertEqual(self.call("GET", "/releases/ai-worker-1.0.0.zip", None, None, Authorization=auth), (200, b"zip"))
            for path in ("/releases/secret.txt", "/releases/../webhook.py", "/releases/..%2fwebhook.py", "/releases/latest.json?x=1"):
                with self.subTest(path=path):
                    self.assertEqual(self.call("GET", path, None, None, Authorization=auth)[0], 404)
            self.assertEqual(self.call("GET", "/releases/latest.json", None, None, Authorization="Bearer wrong")[0], 401)
        finally:
            assets.RELEASES_DIR = original

    def test_foreign_page_cannot_logout(self):
        login.SESSIONS.sessions["tok-dx"] = ("viewer", time.time() + 3600)
        self.assertEqual(self.call("POST", "/logout", "tok-dx", None, Origin="https://la.example")[0], 403)
        self.assertEqual(self.call("GET", "/data", "tok-dx")[0], 200)
        # a page with Referrer-Policy: no-referrer: the browser sends the form with Origin: null, the Log out button must still work
        # trang có Referrer-Policy: no-referrer: trình duyệt gửi form với Origin: null, nút Thoát vẫn phải chạy
        self.assertEqual(self.call("POST", "/logout", "tok-dx", None, Origin="null")[0], 303)
        self.assertEqual(self.call("GET", "/data", "tok-dx")[0], 401)
        # an action that requires the exact origin still refuses null
        # thao tác bắt buộc đúng nguồn thì null vẫn bị từ chối
        self.assertEqual(self.call("POST", "/admin/tv-reload", "tok-adm", "{}", Origin="null")[0], 403)

    def test_path_with_query_does_not_leak_to_other_action(self):
        for path in self.POST_ADMIN + ("/ingest", "/login", "/logout", "/tv/poll"):
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path + "?x=1", "tok-adm", "{}", Origin=self.origin)[0], 404)
        for path in ("/board", "/tv", "/history", "/health", "/tv.js"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path + "?x=1", "tok-adm")[0], 404)

    def test_empty_body_rejected_before_otp_check(self):
        for path in self.POST_ADMIN:
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path, "tok-adm", Origin=self.origin)[0], 413)

    def test_role_denial_is_audited(self):
        self.call("POST", "/locations", "tok-viewer", "{}", Origin=self.origin)
        self.assertIn("role-denied", [x.get("action") for x in all_audit_rows()])

    def test_login_and_logout(self):
        secret = base64.b32encode(b"otp-test-key").decode()
        stores.ACCOUNTS.d["accounts"]["fresh"] = {"role": security.VIEWER, "secret": secret}
        try:
            self.assertEqual(self.call("POST", "/login", None, "account=fresh&code=abc")[0], 401)
            code = security.totp_code(base64.b32decode(secret), int(time.time() // 30))
            # a right code with a missing or wrong name does not get in: each guess can test only one account
            # mã đúng mà thiếu tên hoặc sai tên thì không vào được: mỗi lần đoán chỉ thử được một tài khoản
            for body in ("code=" + code, "account=adm&code=" + code, "account=missing&code=" + code):
                with self.subTest(body=body.split("&")[0]):
                    self.assertEqual(self.call("POST", "/login", None, body)[0], 401)
            conn = http.client.HTTPConnection("127.0.0.1", self.port)
            conn.request("POST", "/login", "account=FRESH&code=" + code)
            r = conn.getresponse()
            r.read()
            self.assertEqual(r.status, 303)
            token = r.getheader("Set-Cookie").split(";")[0].split("=", 1)[1]
            conn.close()
            self.assertEqual(self.call("GET", "/data", token)[0], 200)
            self.assertEqual(self.call("POST", "/logout", token)[0], 303)
            self.assertEqual(self.call("GET", "/data", token)[0], 401)
        finally:
            stores.ACCOUNTS.d["accounts"].pop("fresh", None)

    def test_tv_request_code_needs_no_login(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("POST", "/tv/request-code", "", {"Origin": self.origin})
        r = conn.getresponse()
        self.assertEqual(r.status, 200)
        self.assertIn("code", json.loads(r.read()))
        pending_cookie = r.getheader("Set-Cookie").split(";")[0]
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("POST", "/tv/poll", "", {"Cookie": pending_cookie})
        r = conn.getresponse()
        self.assertEqual(r.status, 200)
        self.assertNotEqual(json.loads(r.read())["status"], "done")
        conn.close()

    def test_every_route_has_permission_test(self):
        self.assertEqual(set(w.GET_ROUTES), {d.split("?")[0] for d in self.GET if not d.startswith(("/static/", "/releases/")) and d != "/missing"})
        self.assertEqual(set(w.POST_ROUTES), set(self.POST_ADMIN) | {"/ingest", "/login", "/logout", "/tv/request-code", "/tv/poll",
                                                                       "/mini/handoff", "/mini/settings", "/mini/unpair", "/mini/pair",
                                                                       "/ext/request-code", "/ext/poll", "/ext/unpair"})

    def test_permission_check_only_in_gate(self):
        code = ""
        for path in [w.__file__] + glob.glob(os.path.join(os.path.dirname(w.__file__), "board", "*.py")):
            with open(path, encoding="utf-8") as f:
                code += f.read()
        self.assertEqual(code.count("SESSIONS.user_and_role("), 1)

    def test_unknown_role_cannot_enter_restricted(self):
        login.SESSIONS.sessions["tok-stranger"] = ("stranger", NOW + 3600)
        stores.ACCOUNTS.d["accounts"]["stranger"] = {"role": "role-unknown", "secret": ""}
        try:
            self.assertEqual(self.call("GET", "/board", "tok-stranger")[0], 303)
            self.assertEqual(self.call("GET", "/admin/data", "tok-stranger")[0], 403)
        finally:
            stores.ACCOUNTS.d["accounts"].pop("stranger", None)
            login.SESSIONS.sessions.pop("tok-stranger", None)

    def test_session_expired(self):
        login.SESSIONS.sessions["tok-expired"] = ("adm", time.time() - 1)
        try:
            self.assertEqual(self.call("GET", "/admin/data", "tok-expired")[0], 401)
        finally:
            login.SESSIONS.sessions.pop("tok-expired", None)


class ExtensionPairing(unittest.TestCase):
    """The manager browser extension pairs through the TV flow with its key in a header, reads only part of the wall view, and loses access at once when revoked.
    Tiện ích trình duyệt cho quản lý ghép qua quy trình của TV với khoá trong header, chỉ đọc một phần của phần treo tường, và mất quyền ngay khi bị thu hồi."""

    EXT_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}}}
        login.SESSIONS.sessions["tok-ext-adm"] = ("adm", NOW + 3600)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        cls.origin = "http://127.0.0.1:%d" % cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        security.BOT.__init__()
        stores.TV_PAIRING.__init__()
        login.SESSIONS.confirmed_at["tok-ext-adm"] = time.time()

    def call(self, method, path, body=None, **headers):
        headers = {k.replace("_", "-"): v for k, v in headers.items()}
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read(), r.getheader("Set-Cookie")
        finally:
            conn.close()

    def admin(self, path, body):
        return self.call("POST", path, json.dumps(body), Cookie="session=tok-ext-adm", Origin=self.origin)

    def audit_rows(self):
        return all_audit_rows()

    def pair(self, name="Laptop of Hoa"):
        status, b, cookie = self.call("POST", "/ext/request-code", "", Origin=self.EXT_ORIGIN, User_Agent=self.UA)
        self.assertEqual(status, 200)
        self.assertIsNone(cookie)
        d = json.loads(b)
        self.assertRegex(d["code"], r"^\d{8}$")
        auth = {"Authorization": "Bearer " + d["key"]}
        self.assertEqual(json.loads(self.call("POST", "/ext/poll", "", Origin=self.EXT_ORIGIN, **auth)[1])["status"], "pending")
        status, b, _ = self.admin("/admin/tv-view", {"code": d["code"]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(b)["kind"], "extension")
        self.assertEqual(self.admin("/admin/tv-approve", {"code": d["code"], "name": name})[0], 200)
        status, b, cookie = self.call("POST", "/ext/poll", "", Origin=self.EXT_ORIGIN, **auth)
        done = json.loads(b)
        self.assertEqual((status, done["status"], done["name"]), (200, "done", name))
        # the session comes in the reply, never as a cookie that would replace the manager's own login
        # phiên đi trong câu trả lời, không bao giờ thành cookie đè lên phiên đăng nhập của chính quản lý
        self.assertIsNone(cookie)
        self.assertTrue(done["token"].startswith("tv_"))
        return done["token"]

    def test_pair_read_and_revoke(self):
        token = self.pair()
        auth = {"Authorization": "Bearer " + token}
        status, b, _ = self.call("GET", "/ext/state", **auth)
        self.assertEqual(status, 200)
        state = json.loads(b)
        self.assertEqual(set(state), {"updatedAt", "people"})
        self.assertIn({"name": "An", "waiting": False, "working": True}, state["people"])
        # a device with no name declared shows a code, never its email
        # máy chưa khai tên hiện một mã, không bao giờ hiện email
        self.assertTrue(all(set(p) == {"name", "waiting", "working"} for p in state["people"]))
        # nothing beyond the wall view: no email, no internal IP, no cost
        # không gì hơn phần treo tường: không email, không IP nội bộ, không chi phí
        for leak in (EMAIL, IP_LAN, IP_PUBLIC, "usd", "account", "binh@"):
            self.assertNotIn(leak, b.decode())
        row = next(x for x in views.admin_data(time.time(), "", "")["screens"] if x["kind"] == "extension")
        self.assertEqual(row["name"], "Laptop of Hoa")
        self.assertTrue(row["running"])
        self.assertIsNone(row["upToDate"])
        self.assertEqual(self.admin("/admin/tv-revoke", {"id": row["id"]})[0], 200)
        # the next poll after revoking is refused, and that use is logged once
        # lần hỏi kế tiếp sau khi thu hồi bị từ chối, và lần dùng đó được ghi nhật ký một lần
        self.assertEqual(self.call("GET", "/ext/state", User_Agent=self.UA, **auth)[0], 401)
        self.assertEqual(self.call("GET", "/ext/state", **auth)[0], 401)
        rows = self.audit_rows()
        actions = [(x["action"], x.get("kind")) for x in rows if x.get("tv") == "Laptop of Hoa" or x.get("kind") == "extension"]
        for action in ("tv-request-code", "tv-view", "tv-approve", "tv-joined", "tv-revoke", "tv-revoked-key-used"):
            self.assertIn((action, "extension"), actions)
        used = [x for x in rows if x["action"] == "tv-revoked-key-used" and x["tv"] == "Laptop of Hoa"]
        self.assertEqual(len(used), 1)
        self.assertEqual(used[0]["device"], "Chrome on Mac")
        self.assertNotIn(token, json.dumps(rows))

    def test_mini_page_and_wall_data(self):
        token = self.pair("Laptop four")
        try:
            self.check_mini_page_and_wall_data(token)
        except BaseException:
            stores.TV.revoke(stores.TV.id_of(token))
            raise

    def check_mini_page_and_wall_data(self, token):
        auth = {"Authorization": "Bearer " + token}
        # the same numbers a wall screen gets from /data, and nothing more: no email, internal IP or account
        # cùng số liệu màn hình treo tường lấy từ /data, không hơn: không email, IP nội bộ hay tài khoản
        status, b, cookie = self.call("GET", "/ext/data", **auth)
        self.assertEqual(status, 200)
        self.assertIsNone(cookie)
        data = json.loads(b)
        wall = views.role_view(security.WALL, time.time())
        self.assertEqual(set(data), set(wall))
        self.assertEqual(sorted(p["name"] for p in data["people"]), sorted(p["name"] for p in wall["people"]))
        for leak in (EMAIL, IP_LAN, IP_PUBLIC, "binh@", '"email"', '"lanIp"', '"ip"', '"ipHistory"'):
            self.assertNotIn(leak, b.decode())
        # the wall view keys people by a short hash, never by the account name
        # phần treo tường gắn người bằng một mã băm ngắn, không bao giờ bằng tên tài khoản
        self.assertTrue(all("@" not in str(p.get("account", "")) for p in data["people"]))
        # the page of the menu bar window, in the language asked for, with no cookie needed or set
        # trang của khung thanh menu, theo ngôn ngữ được hỏi, không cần và không đặt cookie
        status, b, cookie = self.call("GET", "/ext/mini?lang=vi", **auth)
        page = b.decode()
        self.assertEqual(status, 200)
        self.assertIsNone(cookie)
        self.assertIn('<main class="mini">', page)
        self.assertIn('data-lang="vi"', page)
        self.assertIn(lang.VI["Unpair this browser"], page)
        self.assertNotIn(lang.VI["Unpair this computer"], page)
        page = self.call("GET", "/ext/mini?lang=en", Accept_Language="vi", **auth)[1].decode()
        self.assertIn('data-lang="en"', page)
        self.assertIn("Unpair this browser", page)
        self.assertIn('data-lang="vi"', self.call("GET", "/ext/mini", Accept_Language="vi", **auth)[1].decode())
        self.assertIn('data-lang="en"', self.call("GET", "/ext/mini?lang=xx", **auth)[1].decode())
        # the menu bar window itself still says "this computer"
        # khung thanh menu vẫn ghi "máy này"
        self.assertIn("Unpair this computer", pages.page_mini(True).decode())
        for path in ("/ext/data", "/ext/mini"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, Cookie="session=" + token)[0], 401)
        stores.TV.revoke(stores.TV.id_of(token))
        for path in ("/ext/data", "/ext/mini?lang=en"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, **auth)[0], 401)

    def test_cookie_and_wrong_key_refused(self):
        token = self.pair("Laptop two")
        self.assertEqual(self.call("GET", "/ext/state", Cookie="session=" + token)[0], 401)
        self.assertEqual(self.call("GET", "/ext/state", Authorization="Bearer tv_wrong")[0], 401)
        self.assertEqual(self.call("GET", "/ext/state", Authorization=token)[0], 401)
        self.assertFalse([x for x in self.audit_rows() if x["action"] == "tv-revoked-key-used" and x["tv"] == "Laptop two"])
        stores.TV.revoke(stores.TV.id_of(token))

    def test_unpair_revokes_the_key_on_the_server(self):
        token = self.pair("Laptop five")
        auth = {"Authorization": "Bearer " + token}
        # a foreign web page, or a cookie instead of the key, cannot unpair it
        # trang web lạ, hay cookie thay cho khoá, không bỏ ghép được
        self.assertEqual(self.call("POST", "/ext/unpair", "", Origin="https://other.example.com", **auth)[0], 403)
        self.assertEqual(self.call("POST", "/ext/unpair", "", Origin=self.EXT_ORIGIN, Cookie="session=" + token)[0], 401)
        self.assertEqual(self.call("GET", "/ext/state", **auth)[0], 200)
        self.assertEqual(self.call("POST", "/ext/unpair", "", Origin=self.EXT_ORIGIN, **auth)[0], 200)
        self.assertEqual(self.call("GET", "/ext/state", **auth)[0], 401)
        self.assertEqual(self.call("POST", "/ext/unpair", "", Origin=self.EXT_ORIGIN, **auth)[0], 401)
        self.assertIn(("tv-unpaired-itself", "extension"), [(x["action"], x.get("kind")) for x in self.audit_rows() if x.get("tv") == "Laptop five"])

    def test_foreign_page_cannot_ask_for_code(self):
        for path in ("/ext/request-code", "/ext/poll"):
            with self.subTest(path=path):
                self.assertEqual(self.call("POST", path, "", Origin="https://other.example.com")[0], 403)
        self.assertEqual(self.call("POST", "/ext/request-code", "")[0], 200)

    def test_paired_extension_not_blocked_as_probing(self):
        token = self.pair("Laptop three")
        for _ in range(security.BOT_ERRORS_PER_10_MIN):
            self.call("GET", "/missing")
        self.assertEqual(self.call("GET", "/missing")[0], 429)
        self.assertEqual(self.call("GET", "/ext/state", Authorization="Bearer " + token)[0], 200)
        self.assertEqual(self.call("GET", "/ext/data", Authorization="Bearer " + token)[0], 200)
        self.assertEqual(self.call("GET", "/ext/mini?lang=en", Authorization="Bearer " + token)[0], 200)
        stores.TV.revoke(stores.TV.id_of(token))

    def test_revoked_screen_cookie_is_logged(self):
        tv_id, token = stores.TV.create({"name": "Revoked hall TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        stores.TV.revoke(tv_id)
        self.assertEqual(self.call("GET", "/data", Cookie="session=" + token)[0], 401)
        self.assertTrue([x for x in self.audit_rows() if x["action"] == "tv-revoked-key-used" and x["tv"] == "Revoked hall TV"])


class Languages(unittest.TestCase):
    """The language of one request: cookie, DEFAULT_LANG, Accept-Language, then English.
    Ngôn ngữ của một yêu cầu: cookie, DEFAULT_LANG, Accept-Language, rồi tiếng Anh."""

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}}}
        login.SESSIONS.sessions["tok-lang"] = ("adm", NOW + 3600)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        security.BOT.__init__()
        self.addCleanup(setattr, w, "DEFAULT_LANG", lang.DEFAULT_LANG)
        lang.DEFAULT_LANG = ""

    def get(self, method, path, body=None, **headers):
        security.BOT.__init__()
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, {k.replace("_", "-"): v for k, v in headers.items()})
            r = conn.getresponse()
            return r.status, r.read().decode("utf-8"), r
        finally:
            conn.close()

    def test_lang_from_order(self):
        self.assertEqual(lang.lang_from("lang=vi", "en-US"), "vi")
        self.assertEqual(lang.lang_from("session=abc; lang=en", "vi"), "en")
        lang.DEFAULT_LANG = "vi"
        self.assertEqual(lang.lang_from("", "en-US"), "vi")
        self.assertEqual(lang.lang_from("lang=en", ""), "en")
        lang.DEFAULT_LANG = "en"
        self.assertEqual(lang.lang_from("", "vi-VN,vi;q=0.9"), "en")
        lang.DEFAULT_LANG = ""
        self.assertEqual(lang.lang_from("", "vi-VN,vi;q=0.9"), "vi")
        self.assertEqual(lang.lang_from("", "en-US,en;q=0.9,vi;q=0.8"), "en")
        self.assertEqual(lang.lang_from("", "fr-FR"), "en")
        self.assertEqual(lang.lang_from("", ""), "en")
        self.assertEqual(lang.lang_from(None, None), "en")
        self.assertEqual(lang.lang_from("lang=fr", "vi"), "vi")

    def test_lang_cookie_does_not_disturb_session_cookie(self):
        for cookie in ("lang=vi; session=abc", "session=abc; lang=en", "a=1; lang=vi; session=abc; b=2", "session=abc"):
            self.assertEqual(login.SESSIONS.token_of(cookie), "abc", cookie)
        self.assertEqual(login.SESSIONS.token_of("lang=vi"), "")
        self.assertEqual(login.SESSIONS.user_of("lang=vi; session=tok-lang", NOW), "adm")
        status, _, _ = self.get("GET", "/data", Cookie="lang=vi; session=tok-lang")
        self.assertEqual(status, 200)

    def test_tx_follows_the_request_and_falls_back_to_english(self):
        lang.REQUEST.lang = "vi"
        try:
            self.assertEqual(lang.tx("Wrong role"), lang.VI["Wrong role"])
            self.assertEqual(lang.tx("Limit of {n} screens reached, remove some first", n=3), lang.VI["Limit of {n} screens reached, remove some first"].format(n=3))
            self.assertEqual(lang.tx("Text that is not in the dictionary {n}", n=1), "Text that is not in the dictionary 1")
        finally:
            del lang.REQUEST.lang
        self.assertEqual(lang.tx("Wrong role"), "Wrong role")

    def test_every_vietnamese_entry_keeps_its_placeholders(self):
        for en, vi in lang.VI.items():
            self.assertEqual(sorted(re.findall(r"\{(\w+)\}", en)), sorted(re.findall(r"\{(\w+)\}", vi)), en)

    def test_login_page_in_both_languages_with_switch(self):
        _, en, r = self.get("GET", "/", Accept_Language="en-US")
        self.assertIn('<html lang="en"', en)
        self.assertIn("Wall screen: pair with a code", en)
        self.assertNotIn(lang.VI["Wall screen: pair with a code"], en)
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        _, vi, r = self.get("GET", "/", Cookie="lang=vi", Accept_Language="en-US")
        self.assertIn('<html lang="vi"', vi)
        self.assertIn(lang.VI["Wall screen: pair with a code"], vi)
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        _, vi2, _ = self.get("GET", "/", Accept_Language="vi-VN")
        self.assertIn(lang.VI["Wall screen: pair with a code"], vi2)
        # the switch lives in the page script, which the CSP allows
        # nút chuyển nằm trong script của trang, loại mà CSP cho phép
        _, js, r = self.get("GET", "/login.js")
        self.assertIn("lang=", js)
        self.assertIn("max-age=31536000; SameSite=Lax", js)
        self.assertEqual(r.getheader("Cache-Control"), "no-cache")
        self.assertNotIn("<script>", en)

    def test_tv_page_and_script_follow_language_and_never_cache(self):
        _, en_page, r = self.get("GET", "/tv", Accept_Language="en-US")
        self.assertIn("Only an admin can approve", en_page)
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        _, vi_page, _ = self.get("GET", "/tv", Cookie="lang=vi")
        self.assertIn(lang.VI["Only an admin can approve. Do not share the code with anyone."], vi_page)
        _, en_js, r = self.get("GET", "/tv.js", Cookie="lang=en")
        self.assertIn("Waiting for an admin to approve", en_js)
        self.assertEqual(r.getheader("Cache-Control"), "no-cache")
        _, vi_js, _ = self.get("GET", "/tv.js", Cookie="lang=vi")
        self.assertIn(lang.VI["Waiting for an admin to approve"], vi_js)
        self.assertNotIn("Waiting for an admin to approve", vi_js)
        # asking again in English gives English again: nothing is cached across languages
        # hỏi lại bằng tiếng Anh thì ra tiếng Anh: không có gì bị lưu đệm giữa các ngôn ngữ
        _, en_js2, _ = self.get("GET", "/tv.js", Cookie="lang=en")
        self.assertEqual(en_js, en_js2)
        self.assertIn("lang=", en_js)

    def test_board_and_errors_in_vietnamese(self):
        _, en, _ = self.get("GET", "/board", Cookie="session=tok-lang; lang=en")
        self.assertIn("data-label='Status'", en)
        self.assertIn("$", en)
        _, vi, _ = self.get("GET", "/board", Cookie="session=tok-lang; lang=vi")
        self.assertIn("data-label='%s'" % lang.VI["Status"], vi)
        self.assertIn(lang.VI["{amount} VND"].format(amount="0"), vi)
        status, body, _ = self.get("POST", "/admin/confirm", "{}", Cookie="session=tok-lang; lang=vi", Origin="null")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], lang.VI["Wrong origin"])

    def test_default_lang_applies_without_cookie(self):
        lang.DEFAULT_LANG = "vi"
        _, page, _ = self.get("GET", "/", Accept_Language="en-US")
        self.assertIn(lang.VI["Wall screen: pair with a code"], page)

    def test_machine_text_stays_english(self):
        status, body, _ = self.get("POST", "/ingest", "nope", Cookie="lang=vi", Authorization="Bearer test", Content_Length="4")
        self.assertEqual((status, json.loads(body)["error"]), (400, "not JSON"))
        status, body, _ = self.get("POST", "/ingest", "{}", Cookie="lang=vi", Authorization="Bearer wrong")
        self.assertEqual((status, json.loads(body)["error"]), (401, "wrong ingest key"))
        self.assertTrue(packages.TV_INSTALL_WINDOWS.isascii())
        self.assertTrue(packages.TV_INSTALL_MAC.isascii())

    def test_money_follows_language(self):
        self.assertEqual(pages.format_money(12.345), "$12.35")
        lang.REQUEST.lang = "vi"
        try:
            self.assertEqual(pages.format_money(1), lang.VI["{amount} VND"].format(amount="{:,.0f}".format(settings.USD_RATE).replace(",", ".")))
        finally:
            del lang.REQUEST.lang


# --- The page and the server must call a field by the same name ---------------------------------------------------------
# A rename once made the page send and read a wrong field with no test turning red. This group takes the real server reply (fake numbers),
# then compares it with the field names in JavaScript. It only reads the code with regular expressions: it catches mismatched names, it does not replace opening the page and looking.
# --- Trang và máy chủ phải gọi một trường cùng một tên ---------------------------------------------------------
# Đổi tên từng làm trang gửi và đọc sai trường mà không test nào đỏ. Nhóm này lấy phản hồi thật của máy chủ (số giả),
# rồi so với tên trường trong JavaScript. Chỉ đọc mã bằng biểu thức chính quy: bắt lệch tên, không thay được việc mở trang xem.
HERE = os.path.dirname(os.path.abspath(__file__))


class SecurityLimits(unittest.TestCase):
    """Attacks found in the security review must stay fixed.
    Các đòn tấn công tìm thấy khi rà soát bảo mật phải luôn bị chặn."""

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": "JBSWY3DPEHPK3PXP"}}}
        login.SESSIONS.sessions["tok-sec"] = ("adm", NOW + 3600)
        cls.saved_key = settings.INGEST_KEY
        settings.INGEST_KEY = "k" * 40
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        settings.INGEST_KEY = cls.saved_key
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        security.BOT.__init__()
        login.SESSIONS.fails, login.SESSIONS.account_fails, login.SESSIONS.used_step = {}, {}, {}
        views.INGEST_GATE.ingest_times, views.INGEST_GATE.new_devices = {}, {}
        login.SESSIONS.sessions["tok-sec"] = ("adm", time.time() + 3600)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body, headers or {})
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def ingest(self, raw):
        return self.call("POST", "/ingest", raw, {"Authorization": "Bearer " + "k" * 40, "Content-Type": "application/json"})[0]

    def report(self, **fields):
        base = {"v": 1, "device": "device-sec", "name": "Sec", "account": "sec@example.com", "updatedAt": int(time.time() * 1000)}
        return dict(base, **fields)

    def pages_still_work(self):
        cookie = {"Cookie": "session=tok-sec"}
        status, body = self.call("GET", "/data", None, cookie)
        self.assertEqual(status, 200)
        json.loads(body, parse_constant=lambda name: self.fail("not valid JSON: " + name))
        self.assertEqual(self.call("GET", "/board", None, cookie)[0], 200)
        self.assertEqual(self.call("GET", "/admin/data", None, cookie)[0], 200)

    def test_wrong_types_do_not_take_down_the_pages(self):
        for i, fields in enumerate(({"ledger": "x"}, {"ledger": {"500000": "x"}}, {"ledger": {"999999": {"usd": "x"}}}, {"working": "x"},
                                    {"models": {"m": [1]}}, {"tasks": 5}, {"delegating": "x"}, {"quota": {"readAt": "x", "windows": 1}},
                                    {"assistants": 1}, {"subagents": []}, {"updatedAt": 1e300})):
            self.assertIn(self.ingest(json.dumps(self.report(device="device-t%d" % i, **fields))), (200, 400), fields)
            self.pages_still_work()

    def test_nan_and_infinity_are_refused(self):
        for text in ('{"usd":NaN}', '{"usd":Infinity}', '{"usd":-Infinity}'):
            raw = '{"v":1,"device":"device-nan","updatedAt":%d,"ledger":{"1":%s}}' % (int(time.time() * 1000), text)
            self.assertEqual(self.ingest(raw), 400)
        huge = json.dumps(self.report(device="device-huge")).replace('"v": 1,', '"v": 1, "working": 1e999, "x": 1,')
        self.assertEqual(self.ingest(huge), 200)
        self.pages_still_work()

    def test_a_bad_row_already_stored_does_not_take_down_the_pages(self):
        body = '{"v":1,"device":"device-oldbad","updatedAt":%d,"name":"Old","working":"x","ledger":{"1":{"usd":NaN}}}' % int(time.time() * 1000)
        with db.data_db().tx() as c:
            c.execute("INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?, ?)", ("device-oldbad", "", "Old", int(time.time()), body))
            c.execute("INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?, ?)", ("device-broken", "", "", int(time.time()), "{not json"))
        self.addCleanup(drop_device, "device-oldbad")
        self.addCleanup(drop_device, "device-broken")
        self.pages_still_work()

    def test_long_text_is_cut_before_it_is_stored(self):
        self.assertEqual(self.ingest(json.dumps(self.report(device="device-long", name="N" * 100000, account="a" * 100000))), 200)
        stored = stored_device("device-long")
        self.assertEqual(len(stored["name"]), 120)
        self.assertEqual(len(stored["account"]), 120)

    def test_only_known_fields_are_stored(self):
        self.assertEqual(self.ingest(json.dumps(self.report(device="device-extra", secret="x" * 5000))), 200)
        self.assertNotIn("secret", stored_device("device-extra"))

    def test_a_real_report_keeps_its_numbers(self):
        hour = str(int(time.time() // 3600))
        report = self.report(device="device-real", working=1, openSessions=2, models={"claude-opus-5-5": 2}, subagents={"Explore": 1},
                             delegating={"gemini": 1}, assistants={"chatgpt": True, "gemini": False, "gemma": "gemma4:26b"},
                             ledger={hour: {"usd": 1.5, "input": 10, "output": 5, "cacheRead": 1, "cacheWrite": 2, "turns": 1}},
                             tasks={hour: {"gemini": 1, "chatgpt": 0, "gemma": 2}}, pluginVersion="0.24.0", lanIp="192.168.100.2",
                             quota={"readAt": int(time.time() * 1000), "windows": [{"kind": "five_hour", "pct": 12.5}]})
        self.assertEqual(self.ingest(json.dumps(report)), 200)
        stored = stored_device("device-real")
        for field, value in report.items():
            if field == "assistants":
                self.assertEqual(stored[field]["gemma"], "gemma4:26b")
            else:
                self.assertEqual(stored[field], value, field)

    def test_a_device_without_a_name_stays_with_its_person(self):
        self.assertEqual(self.ingest(json.dumps(self.report(device="device-keep", name="Keep", account="keep@example.com"))), 200)
        self.assertEqual(self.ingest(json.dumps({"v": 1, "device": "device-keep", "updatedAt": int(time.time() * 1000)})), 200)
        self.assertEqual(stored_device("device-keep")["account"], "keep@example.com")

    def test_device_name_with_a_newline_is_refused(self):
        self.assertEqual(self.ingest(json.dumps(self.report(device="device-nl\n"))), 400)

    def test_login_limit_holds_for_connections_released_together(self):
        body = b"account=adm&code=000000"
        head = b"POST /login HTTP/1.1\r\nHost: x\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %d\r\n\r\n" % len(body)
        socks = [socket.create_connection(("127.0.0.1", self.port), timeout=10) for _ in range(12)]
        for c in socks:
            c.sendall(head)
        time.sleep(0.2)
        codes = []
        for c in socks:
            c.sendall(body)
            codes.append(c.recv(16)[9:12])
            c.close()
        self.assertEqual(codes.count(b"401"), settings.MAX_FAILS)
        self.assertEqual(codes.count(b"429"), 12 - settings.MAX_FAILS)

    def test_strangers_cannot_lock_the_whole_site(self):
        now = time.time()
        for i in range(60):
            login.SESSIONS.login("nobody%d" % i, "000000", "198.51.100.%d" % (i // 5), now)
        code = security.totp_code(base64.b32decode("JBSWY3DPEHPK3PXP"), int(now // 30))
        self.assertEqual(login.SESSIONS.login("adm", code, "203.0.113.9", now)[0], "adm")

    def test_guessing_one_account_from_many_addresses_is_limited(self):
        now = time.time()
        for i in range(settings.MAX_FAILS_PER_ACCOUNT):
            self.assertIsNone(login.SESSIONS.login("adm", "000000", "198.51.100.%d" % i, now)[0])
        code = security.totp_code(base64.b32decode("JBSWY3DPEHPK3PXP"), int(now // 30))
        self.assertEqual(login.SESSIONS.login("adm", code, "203.0.113.9", now)[0], security.BLOCKED)

    def test_admin_otp_entry_is_not_locked_by_wrong_logins(self):
        now = time.time()
        for i in range(40):
            login.SESSIONS.login("adm", "000000", "198.51.100.%d" % i, now)
        code = security.totp_code(base64.b32decode("JBSWY3DPEHPK3PXP"), int(now // 30))
        status = self.call("POST", "/admin/confirm", json.dumps({"code": code}),
                           {"Cookie": "session=tok-sec", "Origin": "http://x", "Host": "x", "Content-Type": "application/json"})[0]
        self.assertEqual(status, 200)

    def test_non_ascii_digits_do_not_crash_login(self):
        digits = "\u0661\u0662\u0663\u0664\u0665\u0666"
        self.assertEqual(login.SESSIONS.login("adm", digits, "203.0.113.5", time.time()), (None, None))

    def test_ipv6_addresses_of_one_customer_count_together(self):
        self.assertEqual(security.ip_bucket("2001:db8:1:2::1"), security.ip_bucket("2001:db8:1:2:ffff::9"))
        self.assertNotEqual(security.ip_bucket("2001:db8:1:2::1"), security.ip_bucket("2001:db8:1:3::1"))
        self.assertEqual(security.ip_bucket("203.0.113.5"), "203.0.113.5")

    def test_too_many_connections_from_one_address_are_closed(self):
        socks = [socket.create_connection(("127.0.0.1", self.port), timeout=3) for _ in range(settings.MAX_CONNECTIONS_PER_IP)]
        try:
            time.sleep(0.2)
            saved = settings.TRUST_PROXY
            settings.TRUST_PROXY = False
            self.addCleanup(setattr, w, "TRUST_PROXY", saved)
            extra = socket.create_connection(("127.0.0.1", self.port), timeout=3)
            self.assertEqual(extra.recv(10), b"")
            extra.close()
        finally:
            for c in socks:
                c.close()
        time.sleep(0.2)
        self.assertEqual(self.call("GET", "/health")[0], 200)

    def test_oversized_headers_are_refused(self):
        c = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        c.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Pad: " + b"a" * 20000 + b"\r\n\r\n")
        self.assertIn(c.recv(16)[9:12], (b"400", b"431"))
        c.close()

    def test_admin_changes_need_the_origin_header(self):
        cookie = {"Cookie": "session=tok-sec", "Origin": "null", "Host": "x", "Content-Type": "application/json"}
        for path in ("/locations", "/team-csv", "/team-sale"):
            self.assertEqual(self.call("POST", path, "{}", cookie)[0], 403, path)


def read_text(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf8") as f:
        return f.read()


def js_block(src, marker):
    """The part inside the first pair of curly braces after marker.
    Đoạn trong cặp ngoặc nhọn đầu tiên sau marker."""
    start = src.index("{", src.index(marker))
    depth = 0
    for i in range(start, len(src)):
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        if depth == 0:
            return src[start:i + 1]
    raise AssertionError("Could not find the end of the block: " + marker)


def props(block, var):
    return set(re.findall(r"(?<![\w.$])%s\.(\w+)" % var, block))


def body_reads(source):
    """The fields the server reads from the request body.
    Các trường máy chủ đọc từ thân yêu cầu."""
    keys = set(re.findall(r"""body\.get\(["'](\w+)["']""", source))
    for names in re.findall(r"""for k in \(([^)]*)\)""", source):
        keys |= set(re.findall(r"""["'](\w+)["']""", names))
    return keys


def object_keys(text):
    return set(re.findall(r"(?:^|[{,])\s*(\w+)\s*(?=[:,}])", text))


class DatabaseStorage(unittest.TestCase):
    """SQLite storage: moving the old JSON files in, schema version, file modes, many threads, backup, export back to JSON.
    Lưu trữ SQLite: chuyển file JSON cũ vào, phiên bản lược đồ, quyền file, nhiều luồng, sao lưu, xuất ngược ra JSON."""

    def folder(self):
        path = tempfile.mkdtemp(dir=TMP)
        return path

    def write(self, path, text, mtime=None):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if mtime:
            os.utime(path, (mtime, mtime))

    def legacy_folders(self):
        data, keys = self.folder(), self.folder()
        old = int(time.time()) - 5 * 86400
        self.write(os.path.join(data, "identities.json"), json.dumps({"device-a": ["a@example.com", "an"], "bad": "x"}))
        self.write(os.path.join(data, "device-a.json"), json.dumps({"v": 1, "device": "device-a", "name": "An", "account": "a@example.com", "updatedAt": 1}), old)
        self.write(os.path.join(data, "device-b.json"), "{broken")
        self.write(os.path.join(data, "history.jsonl"), json.dumps({"at": 5, "name": "An", "account": "a@example.com", "status": "working", "delegating": [1, 0, 0]}) + "\nnot json\n")
        self.write(os.path.join(data, "tv.json"), json.dumps({"tv1": {"hash": "h1", "name": "Hall", "expiresAt": 9}}))
        self.write(os.path.join(data, "tv-revoked.json"), json.dumps({"h0": {"name": "Old", "kind": "", "revokedAt": 3}}))
        self.write(os.path.join(data, "locations.json"), json.dumps({"salesTeam": ["a@example.com"]}))
        self.write(os.path.join(data, "team-csv.json"), json.dumps({"people": {}}))
        self.write(os.path.join(data, "audit-2026-01.jsonl"), json.dumps({"at": "2026-01-02T00:00:00+07:00", "action": "login"}) + "\n")
        self.write(os.path.join(keys, "accounts.json"), json.dumps({"accounts": {"adm": {"role": "admin", "secret": "JBSWY3DPEHPK3PXP"}}, "imported": ["adm"]}))
        return data, keys, old

    def test_old_json_files_are_moved_in_once(self):
        data, keys, old = self.legacy_folders()
        d = db.Database(os.path.join(data, "board.db"), db.DATA_STEPS, "NORMAL")
        counts = db.migrate_data_json(d, data)
        self.assertEqual(counts, {"identities": 1, "devices": 1, "history": 1, "screens": 1, "revoked": 1, "documents": 2, "audit": 1})
        self.assertEqual(d.rows("SELECT seen_at FROM devices WHERE device = 'device-a'"), [(old,)])
        self.assertEqual(d.rows("SELECT body FROM documents WHERE name = 'locations'"), [('{"salesTeam":["a@example.com"]}',)])
        self.assertEqual(d.rows("SELECT month, action FROM audit"), [("2026-01", "login")])
        # every old file, the broken one too, is kept in legacy-json/ and nothing is left at the top
        # mọi file cũ, kể cả file hỏng, được giữ trong legacy-json/ và không còn file nào ở ngoài
        self.assertIn("device-b.json", os.listdir(os.path.join(data, "legacy-json")))
        self.assertEqual(sorted(os.listdir(data)), ["board.db", "board.db-shm", "board.db-wal", "legacy-json"])
        self.assertEqual(db.migrate_data_json(d, data), {})
        self.assertTrue(d.get_meta("migrated_from_json_at"))
        k = db.Database(os.path.join(keys, "accounts.db"), db.KEYS_STEPS, "FULL")
        self.assertEqual(db.migrate_keys_json(k, keys), 1)
        self.assertEqual(k.rows("SELECT name, role, secret FROM accounts"), [("adm", "admin", "JBSWY3DPEHPK3PXP")])
        self.assertEqual(k.rows("SELECT name FROM imported"), [("adm",)])
        self.assertFalse(os.path.exists(os.path.join(keys, "accounts.json")))

    def test_a_newer_database_is_refused(self):
        path = os.path.join(self.folder(), "board.db")
        db.Database(path, db.DATA_STEPS, "NORMAL").conn.execute("PRAGMA user_version=%d" % (len(db.DATA_STEPS) + 1))
        with self.assertRaises(SystemExit):
            db.Database(path, db.DATA_STEPS, "NORMAL")

    def test_files_are_owner_only_and_use_wal(self):
        d = db.data_db()
        self.assertEqual(d.rows("PRAGMA journal_mode"), [("wal",)])
        for path in (d.path, d.path + "-wal", db.keys_db().path):
            if os.path.exists(path):
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600, path)

    def test_many_threads_send_at_once(self):
        errors = []

        def send(i):
            try:
                devices.save_device({"v": 1, "device": "device-thread%d" % i, "name": "T%d" % i, "account": "", "updatedAt": 1})
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=send, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.addCleanup(lambda: [drop_device("device-thread%d" % i) for i in range(20)])
        self.assertEqual(errors, [])
        self.assertEqual(db.data_db().rows("SELECT COUNT(*) FROM devices WHERE device LIKE 'device-thread%'"), [(20,)])

    def test_otp_secrets_never_reach_the_numbers_database(self):
        secret = stores.ACCOUNTS.create("dbcheck", security.VIEWER, "test")
        self.addCleanup(stores.ACCOUNTS.mutate, lambda d: d["accounts"].pop("dbcheck", None))
        stores.AUDIT_LOG.write(action="account-created", account="dbcheck")
        raw = b""
        for path in (db.data_db().path, db.data_db().path + "-wal"):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    raw += f.read()
        self.assertNotIn(secret.encode(), raw)
        self.assertEqual(db.keys_db().rows("SELECT role FROM accounts WHERE name = 'dbcheck'"), [(security.VIEWER,)])

    def test_backup_while_running(self):
        devices.save_device({"v": 1, "device": "device-backup", "name": "B", "account": "", "updatedAt": 1})
        self.addCleanup(drop_device, "device-backup")
        target = os.path.join(self.folder(), "copy.db")
        db.data_db().backup(target)
        conn = sqlite3.connect(target)
        self.addCleanup(conn.close)
        self.assertGreater(conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0], 0)

    def test_export_back_to_json_and_in_again(self):
        out = self.folder()
        written = db.export_json(out)
        self.assertIn("keys/accounts.json", written)
        self.assertIn("data/identities.json", written)
        # the exported files are what the version before SQLite reads; moving them in again gives the same rows
        # file xuất ra là thứ bản trước SQLite đọc; chuyển vào lại thì ra đúng các dòng cũ
        d = db.Database(os.path.join(out, "data", "again.db"), db.DATA_STEPS, "NORMAL")
        db.migrate_data_json(d, os.path.join(out, "data"))
        self.assertEqual(d.rows("SELECT COUNT(*) FROM devices"), db.data_db().rows("SELECT COUNT(*) FROM devices"))
        self.assertEqual(sorted(d.rows("SELECT device FROM identities")), sorted(db.data_db().rows("SELECT device FROM identities")))
        k = db.Database(os.path.join(out, "keys", "again.db"), db.KEYS_STEPS, "FULL")
        db.migrate_keys_json(k, os.path.join(out, "keys"))
        self.assertEqual(sorted(k.rows("SELECT name, secret FROM accounts")), sorted(db.keys_db().rows("SELECT name, secret FROM accounts")))

    def test_audit_keeps_twelve_months(self):
        with db.data_db().tx() as c:
            c.execute("INSERT INTO audit (at, month, action, body) VALUES ('x', '2000-01', 'old', '{}')")
        stores.AUDIT_LOG.month = ""
        stores.AUDIT_LOG.write(action="check")
        self.assertEqual(db.data_db().rows("SELECT COUNT(*) FROM audit WHERE month = '2000-01'"), [(0,)])
        self.assertEqual(stores.AUDIT_LOG.read(time.strftime("%Y-%m"), 1)[0]["action"], "check")


class PageMatchesServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()
        cls.admin_js = read_text("static", "admin.js")
        cls.ops_js = read_text("static", "ops.js")
        cls.index_html = read_text("..", "web", "index.html")
        cls.data = views.admin_data(time.time(), "", "")

    def assert_subset(self, used, known, where):
        self.assertTrue(used, "%s: no field names could be read, the test is out of date" % where)
        self.assertEqual(sorted(used - set(known)), [], "%s: the page uses field names the server does not have" % where)

    def test_request_fields(self):
        action = inspect.getsource(w.Handler.admin_action)
        branch = lambda route: action.split('if self.path == "%s":' % route)[1].split("elif self.path")[0].split("else:")[0]
        tv = body_reads(inspect.getsource(views.tv_action))
        allowed = {
            "/admin/accounts": body_reads(inspect.getsource(views.manage_account)),
            "/admin/sessions": body_reads(branch("/admin/sessions")),
            "/admin/tv-approve": tv, "/admin/tv-reload": tv, "/admin/tv-rename": tv, "/admin/tv-revoke": tv, "/admin/tv-view": tv,
            "/locations": body_reads(inspect.getsource(views.edit_location)),
            "/team-csv": body_reads(branch("/team-csv")),
            "/team-sale": body_reads(branch("/team-sale")),
        }
        seen = set()
        for m in re.finditer(r"(?:post|submit)\('(/[\w/-]+)',\s*(\{|\w+)", self.admin_js):
            route = m.group(1)
            if m.group(2) == "{":
                text = js_block(self.admin_js[m.start(2):], "{")
            else:
                text = re.findall(r"const %s = (.*)" % m.group(2), self.admin_js[:m.start()])[-1]
            self.assertIn(route, allowed, "New route on the page, add it to the test")
            self.assert_subset(object_keys(text), allowed[route], "sent to " + route)
            seen.add(route)
        self.assertEqual(seen, set(allowed))

    def test_team_fields(self):
        team = self.data["team"]
        self.assertTrue(team and team["items"])
        item = team["items"][0]
        for name, src in (("admin.js", self.admin_js), ("ops.js", self.ops_js)):
            block = js_block(src, "function teamSection")
            self.assert_subset(props(block, "t"), team, name + " Team plan")
            self.assert_subset(props(block, "x"), item, name + " each person")
            self.assert_subset(props(block, "v"), item["other"], name + " cost")

    def test_tv_fields(self):
        now = time.time()
        code = stores.TV_PAIRING.request_code("", "14.1.1.2", "Mozilla/5.0 Chrome", now)[0]
        view = views.tv_action("/admin/tv-view", {"code": code}, "thu")[1]
        code2 = stores.TV_PAIRING.request_code("", "14.1.1.3", "Mozilla/5.0 Chrome", now)[0]
        views.tv_action("/admin/tv-approve", {"code": code2, "name": "TV doi chieu"}, "thu")
        stores.TV.create(stores.TV_PAIRING.pending[code2], now)
        screens = views.admin_data(time.time(), "", "")["screens"]
        for x in screens:
            self.addCleanup(stores.TV.d.pop, x["id"], None)
        self.assertTrue(screens)
        block = js_block(self.admin_js, "function tvSection")
        self.assert_subset(props(block, "y"), set(view) | {"code"}, "TV request card")
        self.assert_subset(props(block, "t"), screens[0], "TV list")

    def test_account_fields(self):
        result = views.manage_account({"action": "create", "name": "thu-doi-chieu", "role": security.ADMIN}, "thu", "khong-co")[1]
        self.addCleanup(stores.ACCOUNTS.d["accounts"].pop, "thu-doi-chieu", None)
        accounts = views.admin_data(time.time(), "", "")["accounts"]
        block = js_block(self.admin_js, "function accountsSection")
        self.assert_subset(props(block, "d"), result, "new key")
        self.assert_subset(props(block, "t"), accounts[0], "account list")

    def test_location_fields(self):
        self.assertTrue(self.data["branches"] and self.data["unnamedGroups"])
        for name in ("function groupForm", "function locationsSection"):
            block = js_block(self.admin_js, name)
            self.assert_subset(props(block, "b"), self.data["branches"][0], name)
            self.assert_subset(props(block, "g") or {"ip"}, self.data["unnamedGroups"][0], name)
        # b is also a button
        # b còn là nút bấm
        self.assert_subset(props(js_block(self.ops_js, "function drawMap"), "b"), set(self.data["branches"][0]) | {"addEventListener", "setAttribute", "title", "type"}, "map")

    def test_session_fields(self):
        login.SESSIONS.sessions["tok-doi-chieu"] = ("thu", time.time() + 60)
        self.addCleanup(login.SESSIONS.sessions.pop, "tok-doi-chieu", None)
        sessions = views.admin_data(time.time(), "", "")["sessions"]
        self.assertTrue(sessions)
        self.assert_subset(props(js_block(self.admin_js, "function sessionsSection"), "x"), sessions[0], "open sessions")

    def test_snapshot_fields(self):
        self.assert_subset(props(self.admin_js, "snapshot"), self.data, "admin.js")
        # the one-machine page in the plugin builds its numbers in web/index.html, with a few fields of its own
        # trang một máy trong plugin dựng số liệu ở web/index.html, có thêm vài trường riêng
        local_only = {k for k in ("hourlyTotal24", "machineQuota", "tokensInTotal", "usdTodayTotal") if re.search(r"\b%s:" % k, self.index_html)}
        known = set(views.role_view(security.ADMIN, NOW)) | set(self.data) | local_only
        self.assert_subset(props(self.ops_js, "snapshot"), known, "ops.js")

    def test_person_fields(self):
        # p in ops.js is also another variable (a drawing segment, a page element): those names are listed here, any other unknown name is a mismatch
        # p trong ops.js còn là biến khác (đoạn vẽ, phần tử trang): các tên đó liệt kê ở đây, tên lạ nào khác là lệch
        not_data = {"addEventListener", "append", "b", "bottom", "classList", "cls", "color", "critical", "draw", "h", "height", "json", "left",
                    "members", "onClick", "online", "setAttribute", "text", "textContent", "y"}
        person = re.search(r"return \{\s*name: d\.name(.*?)\n      \}", self.index_html, re.S)
        self.assertTrue(person, "Could not find the per-session numbers in web/index.html")
        known = set(views.PERSON_FIELDS_BY_ROLE[security.ADMIN]) | object_keys("{" + person.group(1)) | {"name"} | not_data
        self.assert_subset(props(self.ops_js, "p"), known, "ops.js each person")

    def test_history_fields(self):
        view = views.history_view(security.ADMIN, NOW)
        i = self.ops_js.index("fetch('/history'")
        block = self.ops_js[i:i + 700]
        self.assert_subset(props(block, "d"), view, "/history")

    def test_error_fields(self):
        replies = {k for line in re.findall(r"self\.reply\(\d+, \{(.*)\}", read_text("webhook.py")) for k in re.findall(r'"(\w+)":', line)}
        self.assertIn("error", replies)
        self.assert_subset(props(js_block(self.admin_js, "async function submit"), "d"), replies, "error reply")
        self.assert_subset(set(re.findall(r"\.catch\(\(\) => \(\{\}\)\)\)\.(\w+)", self.admin_js)), replies, "OTP confirm error")

    def test_css_reads_attributes_that_exist(self):
        js = "".join(read_text("static", f) for f in os.listdir(os.path.join(HERE, "static")) if f.endswith(".js") and f not in ("three.js", "qrcode.js"))
        py = read_text("webhook.py")
        for name in os.listdir(os.path.join(HERE, "static")):
            if not name.endswith(".css"):
                continue
            for attr in re.findall(r"attr\(data-([\w-]+)\)", read_text("static", name)):
                camel = re.sub(r"-(\w)", lambda m: m.group(1).upper(), attr)
                self.assertTrue("dataset.%s" % camel in js or "data-%s=" % attr in py + js, "%s reads data-%s but nothing sets it" % (name, attr))

    def test_no_word_damaged_by_rename(self):
        for text in (self.admin_js, self.ops_js, self.index_html, read_text("webhook.py")):
            self.assertNotIn("công rate", text)  # i18n-allow

    def test_plugin_writes_what_its_page_reads(self):
        """A rename once left the plugin writing __aiOffice* while its page read __aiWorker*.
        Một lần đổi tên từng khiến plugin ghi __aiOffice* trong khi trang đọc __aiWorker*."""
        page = read_text("..", "web", "index.html")
        hooks = read_text("..", "hooks", "register.tsx")
        read = set(re.findall(r"window\.(__ai\w+)", page)) - {"__aiWorkerConfig"}
        written = set(re.findall(r"window\.(__ai\w+)(?: =| &&)", hooks))
        self.assertTrue(read)
        self.assertEqual(read - written, set())

    def test_every_setting_is_in_the_env_template(self):
        """A new setting must also be documented in ai-worker.env.example.
        Cài đặt mới cũng phải được ghi trong ai-worker.env.example."""
        code = read_text("webhook.py") + "".join(read_text(os.path.join("board", f)) for f in sorted(os.listdir(os.path.join(HERE, "board"))) if f.endswith(".py"))
        used = set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', code))
        documented = set(re.findall(r"^([A-Z_]+)=", read_text("ai-worker.env.example"), re.M))
        self.assertEqual(used - documented, set())
        self.assertEqual(documented - used, set())
        self.assertRegex(read_text("ai-worker.env.example"), r"(?m)^INGEST_KEY=$")

    def test_web_copies_match_server(self):
        for name in ("i18n.js", "ops.vi.js", "ops.js", "ops.css", "ops3d.js"):
            self.assertEqual(read_text("..", "web", name), read_text("static", name), name)


if __name__ == "__main__":
    unittest.main()
