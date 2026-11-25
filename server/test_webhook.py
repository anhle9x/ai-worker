#!/usr/bin/env python3
"""Server test, standard library only: python3 -m unittest test_webhook (run in the server folder).
All the data here is fake, kept in a temporary folder, deleted when the run ends.
  Test máy chủ, chỉ dùng thư viện chuẩn: python3 -m unittest test_webhook (chạy trong thư mục server).
Mọi dữ liệu ở đây là giả, nằm trong thư mục tạm, xoá khi chạy xong."""
import base64
import contextlib
import glob
import hashlib
import hmac
import http.client
import inspect
import io
import json
import random
import os
import re
import socket
import sqlite3
import shutil
import tempfile
import zipfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

TMP = tempfile.mkdtemp(prefix="test-webhook-")
os.environ.update(INGEST_KEY="test", DATA_DIR=os.path.join(TMP, "data"), KEYS_DIR=os.path.join(TMP, "keys"),
                  BRANCHES_FILE=os.path.join(TMP, "missing.json"), OTP="", OTP_KEY_FILE=os.path.join(TMP, "no-otp.key"),
                  # every request builds the board afresh, so a test sees what it just changed
                  # mỗi yêu cầu dựng bảng mới, để test thấy ngay thứ nó vừa đổi
                  VIEW_CACHE_SECONDS="0")
os.makedirs(os.environ["DATA_DIR"])

import telegram_bot  # noqa: E402
import test_ask  # noqa: E402
import test_mcp  # noqa: E402
import test_telegram_bot  # noqa: E402
import webhook as w  # noqa: E402
import webhook_vi  # noqa: E402
from board import ask, assets, chat, daily, db, devicekeys, devices, lang, login, mcp, packages, pages, security, settings, stores, views  # noqa: E402

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
    """The row of a device exactly as stored, not cleaned again on reading, with its hour rows put back in it as export_json does.
    Dòng của một máy đúng như đã lưu, không làm sạch lại khi đọc, với các dòng giờ của nó đặt lại vào như export_json làm."""
    rows = db.data_db().rows("SELECT body FROM devices WHERE device = ?", (device,))
    return json.loads(devices.whole_record(device, rows[0][0]))


def drop_device(device: str) -> None:
    with db.data_db().tx() as c:
        c.execute("DELETE FROM devices WHERE device = ?", (device,))
    # written past save_device, so the devices kept in memory are read again
    # ghi không qua save_device, nên các máy giữ trong bộ nhớ được đọc lại
    devices.DEVICES.forget()


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

    def test_wall_codes_stay_the_same_after_a_restart(self):
        """The code that stands for an email on the wall comes from a secret kept in the keys database: a restarted server
        (a new DeviceKeys reading the same file) gives the same code, and the code is not a plain hash of the email.
        Mã thay email trên màn treo tường lấy từ bí mật giữ trong cơ sở dữ liệu khoá: máy chủ khởi động lại
        (một DeviceKeys mới đọc cùng file) cho cùng mã, và mã không phải bản băm trần của email."""
        before = views.alias(EMAIL)
        self.assertRegex(before, r"\A[0-9a-f]{10}\Z")
        self.assertEqual(devicekeys.DeviceKeys().alias(EMAIL), before)
        self.assertNotEqual(before, hashlib.sha256(EMAIL.encode()).hexdigest()[:10])
        self.assertNotEqual(views.alias("binh@example.com"), before)
        self.assertEqual(views.alias(""), "")
        d = views.role_view(security.WALL, NOW)
        self.assertIn(before, [p["account"] for p in d["people"]])

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
        # the code of the row is there only with the Go receiver
        # mã dòng chỉ có khi có bộ nhận Go
        self.assertEqual(set(original["people"][0]), views.PERSON_FIELDS_DECLARED - {"row"})
        settings.RECEIVER_ENABLED = True
        try:
            self.assertEqual(set(views._raw_data(NOW)["people"][0]), views.PERSON_FIELDS_DECLARED)
        finally:
            settings.RECEIVER_ENABLED = False
        self.assertEqual(set(original["branches"][0]), views.BRANCH_FIELDS_DECLARED)
        self.assertEqual({k for x in original["teamDays"] for k in x}, views.TEAM_DAY_FIELDS)

    def test_the_code_of_a_row(self):
        """With RECEIVER=1 each person has the code of their row: the same for every role and after a restart, apart for each person,
        not the wall's code for the email nor a plain hash, and never an email on the wall. Without it, /data is what it was.
        Với RECEIVER=1 mỗi người có mã dòng: như nhau cho mọi vai và sau khi khởi động lại, khác nhau cho từng người, không trùng mã
        thay email trên màn treo tường cũng không phải bản băm trần, và không bao giờ có email trên màn treo tường. Không bật thì /data
        như trước."""
        off = {role: views.role_view(role, NOW) for role in (security.ADMIN, security.VIEWER, security.WALL)}
        settings.RECEIVER_ENABLED = True
        try:
            on = {role: views.role_view(role, NOW) for role in off}
        finally:
            settings.RECEIVER_ENABLED = False
        for role in off:
            self.assertNotIn('"row"', json.dumps(off[role]))
            self.assertEqual([{k: v for k, v in p.items() if k != "row"} for p in on[role]["people"]], off[role]["people"], role)
            self.assertEqual({k: v for k, v in on[role].items() if k != "people"}, {k: v for k, v in off[role].items() if k != "people"}, role)
        rows = [p["row"] for p in on[security.ADMIN]["people"]]
        self.assertEqual(len(set(rows)), 2)
        for row in rows:
            self.assertRegex(row, r"\A[0-9a-f]{12}\Z")
        self.assertEqual([p["row"] for p in on[security.WALL]["people"]], rows)
        self.assertEqual([p["row"] for p in on[security.VIEWER]["people"]], rows)
        key = devices.person_key(devices.read_device("device-an"))
        self.assertIn(devicekeys.DeviceKeys().row_code(key), rows)
        self.assertNotIn(hashlib.sha256(key.encode()).hexdigest()[:12], rows)
        self.assertNotIn(views.alias(EMAIL), [r[:10] for r in rows])
        self.assertNotIn("@example.com", json.dumps(on[security.WALL]))

    def test_someone_waiting_while_another_session_runs_is_in_both_counts(self):
        """A person waiting in one session while another runs counts as waiting and as working, in the totals of a branch and in the
        totals a chat reads; so working + waiting may pass the people online.
        Người đang chờ ở một phiên trong khi phiên khác chạy được đếm là đang chờ và đang làm, trong tổng của chi nhánh và trong tổng một
        chat đọc; nên đang làm + đang chờ có thể vượt số người trực tuyến."""
        row = {"branch": "hn", "status": "waiting", "openSessions": 2, "working": 1, "waiting": 1, "usdToday": 0, "tokensIn": 0, "tokensOut": 0}
        d = {"branches": [{"id": "hn"}], "people": [row, dict(row, status="working", waiting=0), dict(row, status="waiting", working=0),
                                                   dict(row, status="offline", working=1, waiting=1)],
             "updatedAt": 0, "usdRate": 0, "tzOffsetHours": 7, "tasks24": [], "teamDays": [], "role": "wall", "uiVersion": "x"}
        hn = views.branch_totals(d)[0]
        self.assertEqual((hn["people"], hn["online"], hn["working"], hn["waiting"]), (4, 3, 2, 2))
        views.VIEWS.view = lambda role, now: d
        try:
            t = views.totals_view(0)["totals"]
        finally:
            del views.VIEWS.view
        self.assertEqual((t["working"], t["waiting"]), (2, 2))

    def test_scopes(self):
        """/data?scope=: a branch gives its people only, a page at a time by name; the whole organisation gives the totals of each branch,
        and its people only up to PAGE_PEOPLE; each from the view of the same role.
        /data?scope=: một chi nhánh chỉ cho người của nó, từng trang theo tên; cả tổ chức cho tổng của từng chi nhánh, và người của nó chỉ
        tới PAGE_PEOPLE; mỗi phần lấy từ khung nhìn của cùng vai."""
        wall = views.role_view(security.WALL, NOW)
        hanoi = next(b["id"] for b in wall["branches"] if b["name"] == "Hanoi")
        self.assertEqual(views.parse_scope("org"), "org")
        self.assertEqual(views.parse_scope("branch:" + hanoi), "branch:" + hanoi)
        self.assertEqual(views.parse_scope("branch:"), "branch:")
        for bad in ("", "branch:nowhere", "Org", "hanoi"):
            self.assertIsNone(views.parse_scope(bad), bad)
        org = views.scoped_view(wall, "org", 0)
        self.assertEqual(org["people"], wall["people"])
        self.assertEqual(org["peopleTotal"], 2)
        totals = {t["id"]: t for t in org["branchTotals"]}
        self.assertEqual(set(totals), {hanoi, ""})
        self.assertEqual(set(totals[hanoi]), views.BRANCH_TOTAL_FIELDS)
        self.assertEqual((totals[hanoi]["people"], totals[""]["people"]), (1, 1))
        self.assertEqual(org["branchTotals"][-1]["id"], "")
        self.assertEqual(set(org) - set(wall), {"scope", "peopleTotal", "branchTotals"})
        self.assertTrue(set(org) - set(wall) <= views.SCOPE_FIELDS)
        mine = views.scoped_view(wall, "branch:" + hanoi, 0)
        self.assertEqual([p["branch"] for p in mine["people"]], [hanoi])
        self.assertEqual((mine["page"], mine["pages"], mine["peopleTotal"]), (0, 1, 1))
        self.assertEqual(views.scoped_view(wall, "branch:", 0)["people"][0]["name"], "An")
        self.assertNotIn("@example.com", json.dumps([org, mine]))
        # past PAGE_PEOPLE: the whole organisation gives totals only, a branch gives pages in the order of the names
        # quá PAGE_PEOPLE: cả tổ chức chỉ cho tổng, một chi nhánh cho các trang theo thứ tự tên
        many = dict(wall, people=[dict(wall["people"][0], name="P%d" % i, branch=hanoi) for i in (3, 1, 4, 0, 2)])
        old = views.PAGE_PEOPLE
        views.PAGE_PEOPLE = 2
        try:
            self.assertEqual(views.scoped_view(many, "org", 0)["people"], [])
            self.assertEqual(views.scoped_view(many, "org", 0)["branchTotals"][0]["people"], 5)
            pages = [views.scoped_view(many, "branch:" + hanoi, n) for n in range(4)]
        finally:
            views.PAGE_PEOPLE = old
        self.assertEqual([[p["name"] for p in x["people"]] for x in pages], [["P0", "P1"], ["P2", "P3"], ["P4"], ["P4"]])
        self.assertEqual({x["pages"] for x in pages}, {3})
        self.assertEqual([x["page"] for x in pages], [0, 1, 2, 2])
        self.assertEqual(pages[0]["pageNames"], [["P0", "P1"], ["P2", "P3"], ["P4", "P4"]])

    def test_unknown_field_does_not_leak(self):
        original = views._raw_data
        def with_unknown_field(now):
            d = original(now)
            d["extra"] = "secret-value"
            d["people"][0]["extra"] = "secret-value"
            d["branches"][0]["extra"] = "secret-value"
            d["teamDays"][0]["extra"] = "secret-value"
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

    def test_data_by_scope(self):
        """/data?scope= goes through the same view of the role; a scope that does not exist is refused; plain /data has no scope part.
        /data?scope= đi qua cùng khung nhìn của vai; phạm vi không có thì bị từ chối; /data không có phạm vi thì không có phần phạm vi."""
        self.assertFalse(set(self.fetch("/data", "adm")) & views.SCOPE_FIELDS)
        for name in ("adm", "viewer", "wall"):
            org = self.fetch("/data?scope=org", name)
            self.assertEqual(org["scope"], "org")
            self.assertEqual(sum(t["people"] for t in org["branchTotals"]), len(org["people"]))
            none = self.fetch("/data?scope=branch:&page=9", name)
            self.assertEqual((none["page"], none["pages"]), (0, 1))
        self.assertNotIn("@example.com", json.dumps(self.fetch("/data?scope=org", "wall")))
        self.assertIn("@example.com", json.dumps(self.fetch("/data?scope=org", "adm")))
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.fetch("/data?scope=branch:nowhere", "adm")
        self.assertEqual(err.exception.code, 400)

    def test_not_logged_in(self):
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen("http://127.0.0.1:%d/data" % self.port)
        self.assertEqual(err.exception.code, 401)

    def test_admin_page_gets_unnamedGroups_and_customNetworks(self):
        d = self.fetch("/admin/data", "adm")
        self.assertIn("unnamedGroups", d)
        self.assertTrue(any(b.get("customNetworks") for b in d["branches"]))

    def test_a_branch_is_on_the_board_only_once_a_computer_has_sent_from_it(self):
        network = "45.5.5.5"
        stores.LOCATIONS.mutate(lambda d: views.edit_location(d, {"ip": network, "name": "Da Nang", "lat": 16.05, "lon": 108.2}))
        try:
            # declared, no computer yet: the Admin page manages it, the board and the wall display leave it out
            # đã khai báo, chưa có máy nào: trang Quản trị quản lý nó, bảng và màn hình treo tường bỏ nó ra
            for name in ("adm", "viewer", "wall"):
                with self.subTest(role=name):
                    names = [b["name"] for b in self.fetch("/data", name)["branches"]]
                    self.assertIn("Hanoi", names)
                    self.assertNotIn("Da Nang", names)
            self.assertIn("Da Nang", [b["name"] for b in self.fetch("/admin/data", "adm")["branches"]])
            # one computer sends from that network: the branch is on the board from then on, even after the computer goes offline
            # một máy gửi từ mạng đó: chi nhánh có mặt trên bảng từ lúc ấy, kể cả sau khi máy ngoại tuyến
            devices.save_device({"v": 1, "device": "device-chi", "name": "Chi", "account": "chi@example.com", "ip": network,
                                 "updatedAt": int((NOW - 3 * 86400) * 1000), "openSessions": 0, "working": 0})
            for name in ("adm", "viewer", "wall"):
                with self.subTest(role=name, sent=True):
                    self.assertIn("Da Nang", [b["name"] for b in self.fetch("/data", name)["branches"]])
            board = self.fetch("/data", "adm")
            chi = next(p for p in board["people"] if p["name"] == "Chi")
            self.assertEqual(chi["status"], "offline")
            self.assertEqual(chi["branch"], next(b["id"] for b in board["branches"] if b["name"] == "Da Nang"))
        finally:
            drop_device("device-chi")
            stores.LOCATIONS.mutate(lambda d: views.edit_location(d, {"ip": network, "remove": True, "confirm": True}))


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


class ConnectorReports(unittest.TestCase):
    """Reports from the connector for Codex, Cursor and Gemini CLI: a "tools" table next to the plugin's own report.
    Báo cáo của bộ nối cho Codex, Cursor và Gemini CLI: một bảng "tools" bên cạnh báo cáo của chính plugin."""

    def connector(self, minutes_ago: float = 0, **fields):
        base = {"v": 1, "device": "device-conn1", "name": "Tool", "account": "tool@example.com", "updatedAt": int((NOW - minutes_ago * 60) * 1000),
                "tools": {"codex": {"openSessions": 2, "working": 1, "waiting": 1}}}
        return dict(base, **fields)

    def plugin(self, minutes_ago: float = 0, **fields):
        base = {"v": 1, "device": "device-conn2", "name": "Tool", "account": "tool@example.com", "updatedAt": int((NOW - minutes_ago * 60) * 1000),
                "openSessions": 1, "working": 1, "waiting": 0, "pluginVersion": "0.31.17"}
        return dict(base, **fields)

    def person(self, *reports):
        return devices.group_by_person([devices.clean_payload(r, NOW) for r in reports], NOW)[0]

    def test_only_known_tools_and_counts_are_kept_and_the_totals_are_rebuilt(self):
        raw = self.connector(openSessions=99, working=99, waiting=99, tools={
            "codex": {"openSessions": 2, "working": 1, "waiting": 0, "prompt": "secret"}, "cursor": {"openSessions": 1, "working": "x", "waiting": -4},
            "gemini": "x", "other-tool": {"openSessions": 5}})
        clean = devices.clean_payload(raw, NOW)
        self.assertEqual(clean["tools"], {"codex": {"openSessions": 2, "working": 1, "waiting": 0}, "cursor": {"openSessions": 1, "working": 0, "waiting": 0}})
        self.assertEqual([clean[k] for k in devices.SESSION_COUNTS], [3, 1, 0])
        self.assertNotIn("secret", json.dumps(clean))

    def test_a_plugin_report_has_no_tools_table(self):
        self.assertNotIn("tools", devices.clean_payload(self.plugin(), NOW))
        self.assertNotIn("tools", devices.clean_payload(self.plugin(tools="codex"), NOW))
        self.assertFalse(devices.from_connector(devices.clean_payload(self.plugin(), NOW)))
        self.assertTrue(devices.from_connector(devices.clean_payload(self.connector(tools={}), NOW)))

    def test_one_person_shows_each_tool_with_its_own_counts(self):
        r = self.person(self.plugin(), self.connector(tools={"codex": {"openSessions": 2, "working": 1, "waiting": 1}, "gemini": {"openSessions": 0}}))
        self.assertEqual(r["tools"], {"claude": {"openSessions": 1, "working": 1, "waiting": 0}, "codex": {"openSessions": 2, "working": 1, "waiting": 1}})
        self.assertEqual([r[k] for k in devices.SESSION_COUNTS], [3, 2, 1])
        self.assertEqual(devices.status_of(r, NOW), "waiting")

    def test_the_connector_is_not_counted_as_a_computer_or_a_plugin(self):
        r = self.person(self.plugin(), self.connector(pluginVersion="9.9.9"))
        self.assertEqual(r["deviceCount"], 1)
        self.assertEqual(r["pluginVersion"], ["0.31.17"])
        self.assertEqual(len(r["devices"]), 1)
        alone = self.person(self.connector())
        self.assertEqual((alone["deviceCount"], alone["devices"], alone["pluginVersion"]), (0, [], []))
        self.assertIn("—", pages.device_version_cell(alone, "0.31.17", NOW))

    def test_a_connector_report_counts_for_two_hours_a_plugin_report_for_twelve_minutes(self):
        self.assertEqual(devices.status_of(self.person(self.connector(30)), NOW), "waiting")
        self.assertEqual(devices.status_of(self.person(self.connector(119)), NOW), "waiting")
        late = self.person(self.connector(121))
        self.assertEqual(devices.status_of(late, NOW), "offline")
        self.assertEqual((late["tools"], late["waiting"], late["openSessions"]), ({}, 0, 0))
        self.assertEqual(devices.status_of(self.person(self.plugin(11)), NOW), "working")
        self.assertEqual(devices.status_of(self.person(self.plugin(13)), NOW), "offline")

    def test_a_connector_with_no_session_open_does_not_keep_a_person_online(self):
        closed = self.person(self.connector(tools={}))
        self.assertEqual((devices.status_of(closed, NOW), closed["tools"]), ("offline", {}))
        self.assertEqual(devices.status_of(self.person(self.connector(tools={"codex": {"openSessions": 0, "working": 0, "waiting": 0}})), NOW), "offline")
        # with Claude open on the same computer the person is there all the same
        # khi Claude đang mở trên cùng máy thì người đó vẫn đang ở đó
        self.assertEqual(devices.status_of(self.person(self.plugin(working=0), self.connector(tools={})), NOW), "open")

    def test_working_from_a_connector_is_believed_for_thirty_minutes_waiting_for_two_hours(self):
        busy = {"codex": {"openSessions": 1, "working": 1, "waiting": 0}}
        self.assertEqual(devices.status_of(self.person(self.connector(29, tools=busy)), NOW), "working")
        quiet = self.person(self.connector(31, tools=busy))
        self.assertEqual((devices.status_of(quiet, NOW), quiet["working"]), ("open", 0))
        self.assertEqual(quiet["tools"], {"codex": {"openSessions": 1, "working": 0, "waiting": 0}})
        both = self.person(self.connector(31))
        self.assertEqual((devices.status_of(both, NOW), both["tools"]["codex"]), ("waiting", {"openSessions": 2, "working": 0, "waiting": 1}))
        # the plugin sends on a beat, so its "working" needs no such limit inside its own 12 minutes
        # plugin gửi theo nhịp, nên "đang làm" của nó không cần giới hạn này trong 12 phút của chính nó
        self.assertEqual(devices.status_of(self.person(self.plugin(11)), NOW), "working")

    def test_an_old_plugin_report_does_not_hide_a_fresh_connector_report(self):
        r = self.person(self.plugin(20), self.connector(20))
        self.assertEqual(devices.status_of(r, NOW), "waiting")
        self.assertEqual(r["tools"], {"codex": {"openSessions": 2, "working": 1, "waiting": 1}})
        self.assertEqual([r[k] for k in devices.SESSION_COUNTS], [2, 1, 1])

    def test_every_role_gets_the_tools_and_the_board_page_names_them(self):
        devices.save_device(devices.clean_payload(self.connector(20, name="Codex Only", account="", tools={"codex": {"openSessions": 1, "waiting": 1}, "cursor": {"openSessions": 2, "working": 1}}), NOW))
        self.addCleanup(drop_device, "device-conn1")
        for role in (security.ADMIN, security.VIEWER, security.WALL):
            p = [x for x in views.role_view(role, NOW)["people"] if x["name"] == "Codex Only"][0]
            self.assertEqual(p["tools"], {"codex": {"openSessions": 1, "working": 0, "waiting": 1}, "cursor": {"openSessions": 2, "working": 1, "waiting": 0}})
            self.assertEqual((p["status"], p["deviceCount"], p["pluginVersion"]), ("waiting", 0, []))
            self.assertIsNotNone(p["waitingSince"])
        b = pages.page_board("adm", NOW).decode()
        self.assertIn("<span class=note>Codex 1 · Cursor 2</span>", b)
        row = b[b.index("Codex Only"):]
        row = row[:row.index("</tr>")]
        # quota, cost, tokens, delegated tasks and plugin version: a dash each, because only the plugin counts them
        # hạn mức, chi phí, token, việc đã giao và phiên bản plugin: mỗi ô một gạch, vì chỉ plugin đếm những thứ đó
        self.assertEqual(row.count('<span class="off">—</span>'), 5)

    def test_the_board_page_shows_sessions_waiting_and_running_at_once(self):
        devices.save_device(devices.clean_payload(self.connector(20, name="Both Ways", account="", tools={"codex": {"openSessions": 1, "waiting": 1}, "cursor": {"openSessions": 2, "working": 2}}), NOW))
        self.addCleanup(drop_device, "device-conn1")
        b = pages.page_board("adm", NOW).decode()
        row = b[b.index("Both Ways"):]
        row = row[:row.index("</tr>")]
        self.assertIn('<span class="waiting">waiting for reply (1)</span> · <span class="working">working (2)</span>', row)

    def test_the_board_page_names_no_tool_for_a_person_on_claude_code_only(self):
        self.assertEqual(pages.tools_note({"claude": {"openSessions": 2, "working": 1, "waiting": 0}}), "")
        self.assertEqual(pages.tools_note({}), "")
        self.assertIn("Claude Code 2 · Gemini CLI 1", pages.tools_note({"gemini": {"openSessions": 1}, "claude": {"openSessions": 2}}))


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


class PluginMsiPackage(unittest.TestCase):
    """AI Worker plugin.msi: the server fills the company settings (address, send code, update keys) into the placeholder at the same length.
    Gói AI Worker plugin.msi: máy chủ điền thiết lập công ty (địa chỉ, mã gửi, khoá cập nhật) vào chỗ giữ chỗ, giữ nguyên độ dài."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = packages.MENUBAR_DIR
        packages.MENUBAR_DIR = self.tmp

    def tearDown(self):
        packages.MENUBAR_DIR = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, body):
        with open(os.path.join(self.tmp, packages.PLUGIN_MSI_NAME), "wb") as f:
            f.write(body)

    def test_the_placeholder_is_the_one_the_build_uses(self):
        # build-msi.ps1 makes the placeholder; the server must look for the very same text
        # build-msi.ps1 dựng chuỗi giữ chỗ; máy chủ phải tìm đúng chữ đó
        with open(os.path.join(os.path.dirname(__file__), "..", "packaging", "windows-msi", "build-msi.ps1"), encoding="utf-8") as f:
            self.assertIn("$placeholder = 'AIWORKER-COMPANY-' + ('0' * 2031)", f.read())
        self.assertEqual(len(packages.PLUGIN_MSI_PLACEHOLDER), 2048)

    def test_fills_the_company_settings(self):
        self.assertFalse(packages.plugin_msi_available())
        self.write(b"head" + packages.PLUGIN_MSI_PLACEHOLDER + b"tail")
        self.assertTrue(packages.plugin_msi_available())
        signers = "ai-worker ssh-ed25519 AAAAexample\n"
        package = packages.plugin_msi("https://board.example.com/", "k" * 32, signers)
        self.assertEqual(len(package), len(packages.PLUGIN_MSI_PLACEHOLDER) + 8)
        self.assertNotIn(packages.PLUGIN_MSI_PLACEHOLDER, package)
        filled = package[4:-4].rstrip(b" ")
        settings_ = json.loads(base64.b64decode(filled))
        self.assertEqual(settings_["company"], {"sharing": {"enabled": True, "webhook": "https://board.example.com", "ingestKey": "k" * 32}})
        self.assertEqual(settings_["signers"], signers)

    def test_refuses(self):
        self.assertIsNone(packages.plugin_msi("https://board.example.com", "k", ""))  # no package yet
        self.write(packages.PLUGIN_MSI_PLACEHOLDER)
        self.assertIsNone(packages.plugin_msi("https://board.example.com", "", ""))  # no send code on this server
        for bad in ("https://a.com/\"x", "ftp://a.com", "https://a.com/path"):
            self.assertIsNone(packages.plugin_msi(bad, "k", ""), bad)
        self.assertIsNone(packages.plugin_msi("https://board.example.com", "k" * 2000, ""))  # too long for the placeholder
        self.write(packages.PLUGIN_MSI_PLACEHOLDER * 2)
        self.assertIsNone(packages.plugin_msi("https://board.example.com", "k", ""))  # placeholder twice

    def test_signers_come_from_the_newest_release(self):
        releases = os.path.join(self.tmp, "releases")
        os.makedirs(releases)
        self.assertEqual(packages.release_signers(releases), "")  # nothing released yet
        with zipfile.ZipFile(os.path.join(releases, "ai-worker-1.2.3.zip"), "w") as z:
            z.writestr("keys/allowed_signers", "ai-worker ssh-ed25519 AAAAexample\n")
        with open(os.path.join(releases, "latest.json"), "w") as f:
            json.dump({"version": "1.2.3", "name": "ai-worker-1.2.3.zip"}, f)
        self.assertEqual(packages.release_signers(releases), "ai-worker ssh-ed25519 AAAAexample\n")
        with open(os.path.join(releases, "latest.json"), "w") as f:
            json.dump({"name": "../secret.zip"}, f)
        self.assertEqual(packages.release_signers(releases), "")  # an odd name is not opened

    def test_the_download_is_logged(self):
        self.write(packages.PLUGIN_MSI_PLACEHOLDER)
        source = inspect.getsource(w.Handler.get_plugin_installer)
        self.assertIn('action="plugin-msi"', source)
        self.assertIn('cache_control="no-store"', source)


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
        # Telegram is off in the tests: the paths answer as if it were not set up
        # Telegram tắt khi chạy thử: các đường trả lời như chưa cài
        "/login/telegram": (404, 404, 404, 404, 404),
        "/login/telegram?id=1&hash=x": (404, 404, 404, 404, 404),
        "/telegram/go": (404, 404, 404, 404, 404),
        "/telegram/go?n=abcdefghijkl": (404, 404, 404, 404, 404),
        "/telegram/back": (404, 404, 404, 404, 404),
        "/telegram": (200, 303, 303, 303, 303),
        "/telegram?done=unlinked": (200, 303, 303, 303, 303),
        "/telegram/link": (200, 303, 303, 303, 303),
        "/admin/data": (401, 403, 403, 200, 403),
        "/admin/data?month=2026-11": (401, 403, 403, 200, 403),
        "/data": (401, 200, 200, 200, 200),
        "/data?scope=org": (401, 200, 200, 200, 200),
        "/data?scope=branch:&page=3": (401, 200, 200, 200, 200),
        "/data?scope=nowhere": (401, 400, 400, 400, 400),
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
        # the plugin .msi carries the send code: admins only, like the menu bar installers
        # gói .msi plugin mang mã gửi: chỉ quản trị, như các gói cài thanh menu
        "/plugin/install-windows.msi": (401, 403, 403, 200 if packages.plugin_msi("https://board.example.com", settings.INGEST_KEY, "") else 404, 403),
        "/menubar/install-mac.dmg": (401, 403, 403, 404, 403),
        "/menubar/extension.zip": (401, 403, 403, 200 if packages.menubar_extension() else 404, 403),
        "/menubar/install-ubuntu.deb": (401, 403, 403, 200, 403),
        "/static/mini.js": (401, 200, 200, 200, 200),
        "/static/ops.js": (401, 200, 200, 200, 200),
        "/static/missing.js": (401, 404, 404, 404, 404),
        "/static/../webhook.py": (401, 404, 404, 404, 404),
        "/robots.txt": (200, 200, 200, 200, 200),
        "/health": (200, 200, 200, 200, 200),
        "/ingest/route": (401, 401, 401, 401, 401),
        "/login.js": (200, 200, 200, 200, 200),
        "/tv.js": (200, 200, 200, 200, 200),
        "/tv-qr.js": (200, 200, 200, 200, 200),
        "/tv/install-windows.bat": (200, 200, 200, 200, 200),
        "/tv/install-mac.zip": (200, 200, 200, 200, 200),
        "/releases/latest.json": (401, 401, 401, 401, 401),
        "/releases/ai-worker-1.0.0.zip": (401, 401, 401, 401, 401),
        # the MCP endpoint takes its own kind of key in the Authorization header: no login and no TV key opens it
        # cổng MCP nhận loại khoá riêng của nó trong header Authorization: không phiên đăng nhập hay khoá TV nào mở được
        "/mcp": (401, 401, 401, 401, 401),
        # the page that asks for a key is open like the TV pairing page: it gives nothing out until an admin approves its code
        # trang xin khoá mở như trang ghép TV: không cấp gì cho tới khi quản trị duyệt mã của nó
        "/mcp/connect": (200, 200, 200, 200, 200),
        # the Go receiver's paths are off in the tests, and never open to a login anyway
        # đường của bộ nhận Go tắt khi chạy thử, và dù sao cũng không bao giờ mở cho phiên đăng nhập
        "/internal/policy": (404, 404, 404, 404, 404),
        "/internal/devices?after=": (404, 404, 404, 404, 404),
        "/internal/people?since=0": (404, 404, 404, 404, 404),
        # AI projects and applications are off in these tests (AI_PROJECTS is not 1): their paths answer as if they were not there.
        # test_projects.py turns them on and pins who may open them
        # dự án hay ứng dụng AI tắt trong các test này (AI_PROJECTS không phải 1): các đường của nó trả lời như không có.
        # test_projects.py bật chúng lên và chốt ai được mở
        "/projects": (404, 404, 404, 404, 404),
        "/projects/report.html": (404, 404, 404, 404, 404),
        "/projects/report.csv": (404, 404, 404, 404, 404),
        "/mcp-connect.js": (200, 200, 200, 200, 200),
        # the board's window inside Telegram is off in the tests: its paths answer as if they were not there
        # khung bảng bên trong Telegram tắt khi chạy thử: các đường của nó trả lời như không có
        "/tg/app": (404, 404, 404, 404, 404),
        "/tg/app?lang=vi": (404, 404, 404, 404, 404),
        "/tg/app.js": (404, 404, 404, 404, 404),
        "/tg/mini.js": (404, 404, 404, 404, 404),
        "/tg/mini.css": (404, 404, 404, 404, 404),
        "/tg/data": (404, 404, 404, 404, 404),
        "/tg/state": (404, 404, 404, 404, 404),
        "/.well-known/oauth-protected-resource": (404, 404, 404, 404, 404),
        "/.well-known/oauth-protected-resource/mcp": (404, 404, 404, 404, 404),
        "/.well-known/oauth-authorization-server": (404, 404, 404, 404, 404),
        "/.well-known/oauth-authorization-server/mcp": (404, 404, 404, 404, 404),
        "/.well-known/openid-configuration": (404, 404, 404, 404, 404),
        "/.well-known/openid-configuration/mcp": (404, 404, 404, 404, 404),
        "/missing": (404, 404, 404, 404, 404),
    }
    POST_ADMIN = ("/locations", "/team-csv", "/team-sale", "/admin/confirm", "/admin/accounts", "/admin/sessions",
                     "/admin/tv-view", "/admin/tv-approve", "/admin/tv-revoke", "/admin/tv-rename", "/admin/tv-reload", "/admin/tv-app",
                     "/admin/device-revoke", "/admin/device-forget", "/admin/device-roam")
    NEEDS_OTP_CONFIRM = ("/admin/accounts", "/admin/sessions", "/admin/tv-view", "/admin/tv-approve",
                        "/admin/tv-revoke", "/admin/tv-rename", "/admin/tv-app", "/admin/device-revoke", "/admin/device-forget", "/admin/device-roam")

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

    def test_extension_only_when_zipped_into_menubar(self):
        import tempfile
        old = packages.MENUBAR_DIR
        with tempfile.TemporaryDirectory() as d:
            try:
                packages.MENUBAR_DIR = d
                self.assertEqual(self.call("GET", "/menubar/extension.zip", "tok-adm", Host="board.example.com")[0], 404)
                self.assertFalse(views.admin_data(time.time(), "", "")["menubarExtension"])
                with open(os.path.join(d, "AI-Worker-extension.zip"), "wb") as f:
                    f.write(b"PK extension")
                status, b = self.call("GET", "/menubar/extension.zip", "tok-adm", Host="board.example.com")
                self.assertEqual((status, b), (200, b"PK extension"))
                self.assertTrue(views.admin_data(time.time(), "", "")["menubarExtension"])
                self.assertEqual(self.call("GET", "/menubar/extension.zip", "tok-viewer", Host="board.example.com")[0], 403)
            finally:
                packages.MENUBAR_DIR = old

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

    def test_login_from_another_site_is_refused_before_it_counts(self):
        # another site's form, with its own origin or a no-referrer null, gets 403 and leaves the IP's count alone
        # form của site khác, với nguồn của nó hay null do no-referrer, nhận 403 và không đụng tới số lần đếm của IP
        form = "account=nobody&code=000000"
        login.SESSIONS.fails, login.SESSIONS.account_fails = {}, {}
        for _ in range(8):
            self.assertEqual(self.call("POST", "/login", None, form, Origin="https://other.example.com")[0], 403)
            self.assertEqual(self.call("POST", "/login", None, form, Origin="null", **{"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual((login.SESSIONS.fails, login.SESSIONS.account_fails), ({}, {}))
        # the board's own login form: Origin null from its no-referrer page, Sec-Fetch-Site same-origin; a wrong code is 401, not locked out
        # form đăng nhập của chính bảng: Origin null vì trang no-referrer, Sec-Fetch-Site same-origin; mã sai là 401, không bị khoá
        self.assertEqual(self.call("POST", "/login", None, form, Origin="null", **{"Sec-Fetch-Site": "same-origin"})[0], 401)
        self.assertEqual(self.call("POST", "/login", None, form, Origin=self.origin)[0], 401)

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
                                                                       "/ext/request-code", "/ext/poll", "/ext/unpair", "/telegram/start", "/telegram/unlink",
                                                                       "/mcp", "/mcp/request-code", "/mcp/poll", "/bot/telegram", "/tg/session", "/tg/unpair", "/tg/settings",
                                                                       "/projects/ingest", "/admin/project-key", "/admin/project-prices", "/admin/project-delete",
                                                                       "/internal/rows", "/internal/ingest", "/sse/ticket"})

    def test_the_live_feeds_ticket_is_not_there_while_the_receiver_is_off(self):
        # off in the tests, for every role and every origin; test_receiver.LiveTickets turns it on and pins who gets one
        # tắt khi chạy thử, với mọi vai và mọi nguồn; test_receiver.LiveTickets bật nó lên và chốt ai được cấp
        for token in self.token:
            with self.subTest(token=token):
                self.assertEqual(self.call("POST", "/sse/ticket", token, '{"scope": "org"}', Origin=self.origin)[0], 404)

    def test_the_telegram_bots_path_is_not_there_until_it_is_turned_on(self):
        self.assertFalse(settings.TELEGRAM_ASK_ENABLED)
        for token in self.token:
            for headers in ({}, {"Authorization": "Bearer " + "k" * 40}, {"Authorization": "Bearer test"}):
                self.assertEqual(self.call("POST", "/bot/telegram", token, "{}", **headers)[0], 404)
        self.assertEqual(self.call("GET", "/bot/telegram")[0], 404)

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

    PLUGIN_UA = "AI-Worker-Plugin/1.2.3 (Mac)"

    def test_a_claude_plugin_pairs_like_the_extension_and_is_named_apart(self):
        status, b, cookie = self.call("POST", "/ext/request-code", "", User_Agent=self.PLUGIN_UA)
        self.assertEqual(status, 200)
        self.assertIsNone(cookie)
        d = json.loads(b)
        pending = {"Authorization": "Bearer " + d["key"]}
        # the key that waits for approval reads nothing
        # khoá đang chờ duyệt không đọc được gì
        self.assertEqual(self.call("GET", "/ext/data", **pending)[0], 401)
        status, b, _ = self.admin("/admin/tv-view", {"code": d["code"]})
        view = json.loads(b)
        self.assertEqual((status, view["kind"], view["device"]), (200, "plugin", "Claude plugin on Mac"))
        self.assertEqual(self.admin("/admin/tv-approve", {"code": d["code"], "name": "Claude of Hoa"})[0], 200)
        done = json.loads(self.call("POST", "/ext/poll", "", **pending)[1])
        self.assertEqual((done["status"], done["name"]), ("done", "Claude of Hoa"))
        token = {"Authorization": "Bearer " + done["token"]}
        # what Claude gets to read: the wall view, so names and numbers but no email and no IP
        # thứ Claude được đọc: phần treo tường, tức tên và số liệu nhưng không có email và không có IP
        status, b, _ = self.call("GET", "/ext/data", **token)
        board = json.loads(b)
        self.assertEqual((status, board["role"]), (200, security.WALL))
        self.assertIn("An", [p["name"] for p in board["people"]])
        for private in ("@example.com", IP_LAN, IP_PUBLIC, NET_CUSTOM):
            self.assertNotIn(private, b.decode())
        row = next(t for t in json.loads(self.call("GET", "/admin/data", Cookie="session=tok-ext-adm")[1])["screens"] if t["name"] == "Claude of Hoa")
        self.assertEqual((row["kind"], row["device"], row["upToDate"]), ("plugin", "Claude plugin on Mac", None))
        self.assertIn("tv-joined", [x.get("action") for x in self.audit_rows() if x.get("kind") == "plugin"])
        # revoked in /admin: the key stops working at once
        # thu hồi trong /admin: khoá hết dùng được ngay
        self.assertEqual(self.admin("/admin/tv-revoke", {"id": row["id"]})[0], 200)
        self.assertEqual(self.call("GET", "/ext/data", **token)[0], 401)

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


class McpEndpoint(unittest.TestCase):
    """The MCP endpoint: an AI tool gets a key through a code an admin approves, reads the wall view as text within what its key may read,
    and the key opens nothing else. Other keys do not open the endpoint.
    Cổng MCP: công cụ AI nhận khoá qua một mã do quản trị duyệt, đọc phần treo tường dạng chữ trong phạm vi khoá của nó được đọc,
    và khoá đó không mở được gì khác. Khoá khác không mở được cổng này."""

    PRIVATE = ("@example.com", IP_LAN, IP_PUBLIC, NET_CUSTOM, "device-an", "device-binh")

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": ""}}}
        login.SESSIONS.sessions["tok-mcp-adm"] = ("adm", NOW + 3600)
        login.SESSIONS.sessions["tok-mcp-viewer"] = ("viewer", NOW + 3600)
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
        w.MCP_LIMIT.__init__(settings.MCP_CALLS_PER_KEY, settings.MCP_CALLS_WINDOW_SECONDS)
        login.SESSIONS.confirmed_at["tok-mcp-adm"] = time.time()
        self.rows_before = set(stores.TV.d)

    def tearDown(self):
        # the store swaps its table on every change, so the rows a test made are taken out of the table as it is now
        # kho đổi bảng của nó sau mỗi lần sửa, nên các dòng một bài test tạo ra được gỡ khỏi bảng đúng như nó đang là
        for tv_id in set(stores.TV.d) - self.rows_before:
            stores.TV.d.pop(tv_id, None)

    def call(self, method, path, body=None, **headers):
        headers = {k.replace("_", "-"): v for k, v in headers.items()}
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read(), r
        finally:
            conn.close()

    def admin(self, path, body):
        return self.call("POST", path, json.dumps(body), Cookie="session=tok-mcp-adm", Origin=self.origin)

    def pair(self, name="Cursor of Hoa", scope=None):
        """The board's own page asks for a code, an admin approves it with a scope, the page gets the key once.
        Trang của chính bảng xin mã, quản trị duyệt kèm phạm vi, trang nhận khoá một lần."""
        status, b, _ = self.call("POST", "/mcp/request-code", "", Origin=self.origin)
        self.assertEqual(status, 200)
        d = json.loads(b)
        self.assertRegex(d["code"], r"^\d{8}$")
        pending = {"Authorization": "Bearer " + d["key"]}
        self.assertEqual(json.loads(self.call("POST", "/mcp/poll", "", Origin=self.origin, **pending)[1])["status"], "pending")
        # the key that waits for approval reads nothing
        # khoá đang chờ duyệt không đọc được gì
        self.assertEqual(self.ask(d["key"], test_mcp.modern("tools/list"))[0], 401)
        view = json.loads(self.admin("/admin/tv-view", {"code": d["code"]})[1])
        self.assertEqual(view["kind"], "mcp")
        self.assertEqual(self.admin("/admin/tv-approve", dict({"code": d["code"], "name": name}, **({"scope": scope} if scope else {})))[0], 200)
        status, b, r = self.call("POST", "/mcp/poll", "", Origin=self.origin, **pending)
        done = json.loads(b)
        self.assertEqual((status, done["status"], done["name"], done["scope"]), (200, "done", name, scope if scope == "people" else "totals"))
        self.assertIsNone(r.getheader("Set-Cookie"))
        self.assertRegex(done["token"], r"^mcp_[A-Za-z0-9_-]{40,}$")
        return done["token"]

    def ask(self, token, request, **more):
        """One MCP message to the endpoint. Returns (status, parsed body or None, the response).
        Một thông điệp MCP gửi tới cổng. Trả (mã trạng thái, thân đã phân tích hoặc None, câu trả lời)."""
        raw, headers = request
        headers = dict(headers, **{"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        if token:
            headers["Authorization"] = "Bearer " + token
        headers.update({k.replace("_", "-"): v for k, v in more.items()})
        status, b, r = self.call("POST", "/mcp", raw, **headers)
        return status, (json.loads(b) if b else None), r

    def summary(self, token, request=None):
        status, body, _ = self.ask(token, request or test_mcp.modern("tools/call", {"name": "board_summary", "arguments": {}}))
        self.assertEqual(status, 200)
        return body["result"]["content"][0]["text"]

    def month(self):
        return datetime.now(settings.LOCAL_TZ).strftime("%Y-%m")

    def test_a_people_key_reads_names_and_numbers_but_nothing_private(self):
        token = self.pair(scope="people")
        status, body, r = self.ask(token, test_mcp.modern("server/discover"))
        self.assertEqual((status, body["result"]["capabilities"], body["result"]["supportedVersions"][0]), (200, {"tools": {}}, "2026-07-28"))
        self.assertIn("application/json", r.getheader("Content-Type"))
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        status, body, _ = self.ask(token, test_mcp.modern("tools/list"))
        self.assertEqual([t["name"] for t in body["result"]["tools"]], ["board_summary"])
        text = self.summary(token)
        self.assertIn("Team: 2 people, 2 working", text)
        self.assertRegex(text, r"\n- An \| [^\n]* \| working \| ")
        # the device with no name declared shows as a code, never as its email
        # máy chưa khai tên hiện thành một mã, không bao giờ hiện email
        self.assertRegex(text, r"\n- Device [0-9a-f]{6} \| Hanoi \| ")
        for private in self.PRIVATE:
            self.assertNotIn(private, text)

    def test_a_key_approved_with_no_scope_reads_totals_only(self):
        for scope in (None, "totals", "everything"):
            with self.subTest(scope=scope):
                stores.TV_PAIRING.__init__()
                status, b, _ = self.call("POST", "/mcp/request-code", "", Origin=self.origin)
                d = json.loads(b)
                self.assertEqual(self.admin("/admin/tv-approve", dict({"code": d["code"], "name": "Totals %s" % scope}, **({"scope": scope} if scope else {})))[0], 200)
                done = json.loads(self.call("POST", "/mcp/poll", "", Origin=self.origin, Authorization="Bearer " + d["key"])[1])
                self.assertEqual(done["scope"], "totals")
                # what the request asks for changes nothing: the key decides
                # yêu cầu xin gì cũng không đổi được: khoá quyết định
                text = self.summary(done["token"], test_mcp.modern("tools/call", {"name": "board_summary", "arguments": {"scope": "people"}}))
                self.assertIn("Team: 2 people", text)
                self.assertIn(mcp.TOTALS_ONLY, text)
                self.assertNotIn("- An |", text)
                for private in self.PRIVATE:
                    self.assertNotIn(private, text)

    def test_an_older_tool_opens_with_initialize(self):
        token = self.pair("Codex of Hoa", "people")
        params = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "codex-mcp-client", "version": "0.164.0"}}
        status, body, r = self.ask(token, test_mcp.legacy("initialize", params))
        self.assertEqual((status, body["result"]["protocolVersion"], body["result"]["capabilities"]), (200, "2025-06-18", {"tools": {}}))
        self.assertIsNone(r.getheader("Mcp-Session-Id"))
        version = {"mcp-protocol-version": "2025-06-18"}
        status, b, r = self.call("POST", "/mcp", json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}), Authorization="Bearer " + token, **version)
        self.assertEqual((status, b, r.getheader("Content-Length")), (202, b"", "0"))
        self.assertEqual(self.ask(token, test_mcp.legacy("ping", headers=version))[1], {"jsonrpc": "2.0", "id": 1, "result": {}})
        text = self.summary(token, test_mcp.legacy("tools/call", {"name": "board_summary", "arguments": {}}, version))
        self.assertIn("- An |", text)
        # the name the tool gave in initialize is on the row of its later call
        # cái tên công cụ xưng trong initialize nằm trên dòng của lần gọi sau đó
        row = stores.AUDIT_LOG.read_calls(self.month())[0]
        self.assertEqual((row["tv"], row["tool"], row["ok"], row["client"], row["protocol"]), ("Codex of Hoa", "board_summary", True, "codex-mcp-client/0.164.0", "legacy"))

    def test_each_tool_call_is_logged_apart_from_the_admin_log(self):
        token = self.pair("Log of Hoa", "people")
        before = len(stores.AUDIT_LOG.read_calls(self.month(), 10000))
        self.ask(token, test_mcp.modern("tools/list"))
        self.summary(token)
        self.assertEqual(self.ask(token, test_mcp.modern("tools/call", {"name": "delete_everything"}))[0], 200)
        calls = stores.AUDIT_LOG.read_calls(self.month(), 10000)
        self.assertEqual(len(calls) - before, 2)
        failed, done = calls[0], calls[1]
        self.assertEqual((done["action"], done["tv"], done["tool"], done["ok"], done["client"], done["protocol"], done["clientIp"]),
                         ("mcp-call", "Log of Hoa", "board_summary", True, "ExampleClient/1.0.0", "modern", "127.0.0.1"))
        self.assertEqual((failed["tool"], failed["ok"]), ("", False))
        # the admin's own log does not fill up with calls, and no key is ever written anywhere
        # nhật ký của quản trị không bị đầy vì các lần gọi, và không khoá nào bị ghi ra ở đâu
        self.assertNotIn("mcp-call", [x.get("action") for x in stores.AUDIT_LOG.read(self.month(), 10000)])
        self.assertIn("tv-joined", [x.get("action") for x in stores.AUDIT_LOG.read(self.month(), 10000) if x.get("kind") == "mcp"])
        self.assertNotIn(token, json.dumps(all_audit_rows()))
        self.assertNotIn(token, json.dumps(stores.TV.d))

    def test_the_key_opens_nothing_else_and_no_other_key_opens_the_endpoint(self):
        token = self.pair(scope="people")
        auth = {"Authorization": "Bearer " + token}
        for path in ("/ext/data", "/ext/state", "/ext/mini"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, **auth)[0], 401)
        for path, status in (("/data", 401), ("/history", 401), ("/mini/state", 401), ("/admin/data", 401), ("/static/ops.js", 401), ("/board", 200)):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, Cookie="session=" + token)[0], status)
        self.assertEqual(self.call("POST", "/ext/unpair", "", **auth)[0], 401)
        self.assertEqual(self.call("POST", "/ingest", "{}", **auth)[0], 401)
        self.assertIsNone(stores.TV.find(token, time.time()))
        self.assertIsNotNone(stores.TV.find(token, time.time(), side=settings.KIND_MCP))
        # a wall screen's key, an extension's or a plugin's key, the send key, an admin's session: none opens the endpoint
        # khoá của màn hình treo tường, của tiện ích hay plugin, mã gửi, phiên của quản trị: không cái nào mở được cổng
        tv_id, tv_token = stores.TV.create({"name": "Wall TV", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        ext_id, ext_token = stores.TV.create({"name": "Ext", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test", "kind": "extension"}, time.time())
        self.assertIsNone(stores.TV.find(tv_token, time.time(), side=settings.KIND_MCP))
        for other in (tv_token, ext_token, "mcp_" + tv_token[3:], "test", "tok-mcp-adm", ""):
            with self.subTest(other=other[:6]):
                status, body, r = self.ask(other, test_mcp.modern("tools/call", {"name": "board_summary"}))
                self.assertEqual(status, 401)
                self.assertEqual(r.getheader("WWW-Authenticate"), 'Bearer realm="AI Worker board"')
                self.assertNotIn("result", body)
        status, _, _ = self.ask("", test_mcp.modern("tools/call", {"name": "board_summary"}), Cookie="session=tok-mcp-adm")
        self.assertEqual(status, 401)
        status, _, _ = self.ask("", test_mcp.modern("tools/call", {"name": "board_summary"}), Cookie="session=" + token)
        self.assertEqual(status, 401)

    def test_only_post_is_served(self):
        token = self.pair()
        for method in ("GET", "DELETE"):
            with self.subTest(method=method):
                status, _, r = self.call(method, "/mcp", Authorization="Bearer " + token)
                self.assertEqual((status, r.getheader("Allow")), (405, "POST"))
                self.assertEqual(self.call(method, "/mcp")[0], 401)
        self.assertEqual(self.call("DELETE", "/data", Cookie="session=tok-mcp-adm")[0], 404)
        self.assertEqual(self.call("DELETE", "/admin/accounts", Cookie="session=tok-mcp-adm", Origin=self.origin)[0], 404)

    def test_a_web_page_on_another_site_is_refused_even_with_a_key(self):
        token = self.pair()
        request = test_mcp.modern("tools/list")
        for origin in ("https://evil.example.com", "null", "http://127.0.0.1:1"):
            with self.subTest(origin=origin):
                self.assertEqual(self.ask(token, request, Origin=origin)[0], 403)
        self.assertEqual(self.ask(token, request, Origin=self.origin)[0], 200)
        # a key is asked for by the board's own page only
        # chỉ trang của chính bảng mới xin được khoá
        for path in ("/mcp/request-code", "/mcp/poll"):
            self.assertEqual(self.call("POST", path, "")[0], 403)
            self.assertEqual(self.call("POST", path, "", Origin="https://evil.example.com")[0], 403)

    def test_revoking_stops_the_key_at_once_and_its_later_use_is_logged(self):
        token = self.pair("Gone of Hoa", "people")
        row = next(x for x in json.loads(self.call("GET", "/admin/data", Cookie="session=tok-mcp-adm")[1])["screens"] if x["name"] == "Gone of Hoa")
        self.assertEqual((row["kind"], row["scope"], row["upToDate"]), ("mcp", "people", None))
        # the admin sees the first characters of the key, enough to tell rows apart, and never the key
        # quản trị thấy vài ký tự đầu của khoá, đủ để phân biệt các dòng, và không bao giờ thấy cả khoá
        self.assertEqual(row["keyStart"], token[:12])
        self.assertNotIn(token, self.call("GET", "/admin/data", Cookie="session=tok-mcp-adm")[1].decode())
        self.assertNotIn("hash", row)
        self.summary(token)
        self.assertTrue(next(x for x in views.admin_data(time.time(), "", "")["screens"] if x["id"] == row["id"])["running"])
        # a viewer cannot approve or revoke a key
        # người chỉ xem không duyệt hay thu hồi được khoá
        self.assertEqual(self.call("POST", "/admin/tv-revoke", json.dumps({"id": row["id"]}), Cookie="session=tok-mcp-viewer", Origin=self.origin)[0], 403)
        self.assertEqual(self.admin("/admin/tv-revoke", {"id": row["id"]})[0], 200)
        self.assertEqual(self.ask(token, test_mcp.modern("tools/call", {"name": "board_summary"}))[0], 401)
        self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 401)
        used = [x for x in all_audit_rows() if x["action"] == "tv-revoked-key-used" and x["tv"] == "Gone of Hoa"]
        self.assertEqual((len(used), used[0]["kind"]), (1, "mcp"))

    def test_a_key_that_asks_too_often_is_slowed_down(self):
        token = self.pair("Busy of Hoa")
        w.MCP_LIMIT.__init__(3, 600)
        request = test_mcp.modern("tools/list")
        self.assertEqual([self.ask(token, request)[0] for _ in range(3)], [200, 200, 200])
        for _ in range(3):
            status, body, r = self.ask(token, request)
            self.assertEqual(status, 429)
            self.assertGreater(int(r.getheader("Retry-After")), 0)
        self.assertEqual(len([x for x in all_audit_rows() if x["action"] == "mcp-rate-limited" and x["tv"] == "Busy of Hoa"]), 1)
        # another key is not held back by this one, and being slowed down does not get the IP blocked
        # khoá khác không bị khoá này giữ lại, và bị làm chậm không khiến IP bị chặn
        other = self.pair("Calm of Hoa")
        self.assertEqual(self.ask(other, request)[0], 200)
        self.assertEqual(self.call("GET", "/")[0], 200)

    def test_wrong_keys_count_as_probing_but_a_paired_tool_does_not(self):
        token = self.pair()
        request = test_mcp.modern("subscriptions/listen")
        # a paired tool asking for what the server does not offer gets 404 many times and is never blocked
        # công cụ đã ghép hỏi thứ máy chủ không có thì nhận 404 nhiều lần và không bao giờ bị chặn
        self.assertEqual({self.ask(token, request)[0] for _ in range(security.BOT_ERRORS_PER_10_MIN + 5)}, {404})
        # nor does looking for OAuth settings, which some tools do after a 401
        # việc đi tìm cấu hình OAuth, điều vài công cụ làm sau khi nhận 401, cũng vậy
        for _ in range(4):
            for path in w.NO_OAUTH_PATHS:
                self.assertEqual(self.call("GET", path)[0], 404)
        self.assertEqual(self.call("GET", "/")[0], 200)
        security.BOT.__init__()
        for _ in range(security.BOT_ERRORS_PER_10_MIN):
            self.assertEqual(self.ask("mcp_" + "x" * 43, test_mcp.modern("tools/list"))[0], 401)
        self.assertEqual(self.ask("mcp_" + "x" * 43, test_mcp.modern("tools/list"))[0], 429)
        self.assertEqual(self.call("GET", "/")[0], 429)
        # the paired tool on the same IP still gets its answer
        # công cụ đã ghép trên cùng IP vẫn nhận được câu trả lời
        self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 200)

    def test_a_message_must_have_a_sane_size(self):
        token = self.pair()
        raw, headers = test_mcp.modern("tools/list")
        big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"pad": "x" * mcp.MAX_REQUEST_BYTES}}).encode()
        self.assertEqual(self.ask(token, (big, headers))[0], 413)
        self.assertEqual(self.ask(token, (b"", headers))[0], 413)
        status, body, _ = self.ask(token, (b"{", headers))
        self.assertEqual((status, body["error"]["code"]), (400, mcp.PARSE_ERROR))

    def test_mcp_keys_and_screens_have_their_own_limits(self):
        now = time.time()
        for i in range(settings.TV_MAX - stores.TV.count(now)):
            stores.TV.create({"name": "TV %d" % i, "approvedBy": "adm", "ip": IP_PUBLIC, "device": "t"}, now)
        with self.assertRaises(ValueError):
            stores.TV.create({"name": "one too many", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "t"}, now)
        # a full wall of screens does not stop an MCP key, and the other way round
        # đủ số màn hình không chặn được khoá MCP, và ngược lại
        token = self.pair("Still fits")
        self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 200)
        for i in range(settings.MCP_KEYS_MAX - stores.TV.count(now, settings.KIND_MCP)):
            stores.TV.create({"name": "Key %d" % i, "approvedBy": "adm", "ip": IP_PUBLIC, "device": "t", "kind": "mcp"}, now)
        with self.assertRaises(ValueError):
            stores.TV.create({"name": "one key too many", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "t", "kind": "mcp"}, now)
        status, b, _ = self.call("POST", "/mcp/request-code", "", Origin=self.origin)
        status, b, _ = self.admin("/admin/tv-approve", {"code": json.loads(b)["code"], "name": "Refused"})
        self.assertEqual(status, 400)
        self.assertIn("MCP", json.loads(b)["error"])
        self.assertEqual((stores.TV.count(now), stores.TV.count(now, settings.KIND_MCP)), (settings.TV_MAX, settings.MCP_KEYS_MAX))

    def test_a_key_replaces_only_another_key(self):
        token = self.pair("Old key", "people")
        old_id = stores.TV.id_of(token)
        tv_id, _ = stores.TV.create({"name": "A screen", "approvedBy": "adm", "ip": "127.0.0.1", "device": "t"}, time.time())
        d = json.loads(self.call("POST", "/mcp/request-code", "", Origin=self.origin)[1])
        # only keys are offered to be replaced, and a screen cannot be turned into a key
        # chỉ khoá mới được gợi ý để thay, và một màn hình không biến thành khoá được
        self.assertEqual(self.admin("/admin/tv-approve", {"code": d["code"], "name": "New key", "replaceId": tv_id})[0], 400)
        self.assertEqual(self.admin("/admin/tv-approve", {"code": d["code"], "name": "New key", "replaceId": old_id, "scope": "people"})[0], 200)
        done = json.loads(self.call("POST", "/mcp/poll", "", Origin=self.origin, Authorization="Bearer " + d["key"])[1])
        self.assertEqual(done["status"], "done")
        self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 401)
        self.assertEqual(self.ask(done["token"], test_mcp.modern("tools/list"))[0], 200)
        self.assertIn(tv_id, stores.TV.d)

    def test_mcp_off_takes_every_mcp_path_away(self):
        token = self.pair()
        settings.MCP_ENABLED = False
        try:
            self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 404)
            self.assertEqual(self.call("GET", "/mcp", Authorization="Bearer " + token)[0], 404)
            self.assertEqual(self.call("DELETE", "/mcp", Authorization="Bearer " + token)[0], 404)
            for path in ("/mcp/request-code", "/mcp/poll"):
                self.assertEqual(self.call("POST", path, "", Origin=self.origin)[0], 404)
            self.assertEqual(self.call("GET", w.NO_OAUTH_PATHS[0])[0], 404)
            # the rest of the board is as before
            # phần còn lại của bảng vẫn như trước
            self.assertEqual(self.call("GET", "/data", Cookie="session=tok-mcp-adm")[0], 200)
        finally:
            settings.MCP_ENABLED = True
        self.assertEqual(self.ask(token, test_mcp.modern("tools/list"))[0], 200)

    def test_the_connect_page_asks_for_a_code_and_keeps_the_key_out_of_storage(self):
        status, b, r = self.call("GET", "/mcp/connect")
        page = b.decode()
        self.assertEqual(status, 200)
        self.assertIn('<script src="/mcp-connect.js"></script>', page)
        self.assertIn("Connect an AI tool", page)
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        self.assertIsNone(r.getheader("Set-Cookie"))
        # nothing is asked of the server just by opening the page
        # chỉ mở trang thì chưa xin gì ở máy chủ
        self.assertEqual(stores.TV_PAIRING.pending, {})
        status, b, r = self.call("GET", "/mcp-connect.js")
        script = b.decode()
        self.assertEqual((status, r.getheader("Content-Type")), (200, "text/javascript; charset=utf-8"))
        for needed in ("/mcp/request-code", "/mcp/poll", "credentials: 'omit'", "claude mcp add --transport http", "codex mcp add", "--bearer-token-env-var", "gemini mcp add", "mcpServers"):
            self.assertIn(needed, script)
        # the key is put on the page as text and lives in a variable: no HTML built from it, no cookie, no browser storage, no address
        # khoá được đặt lên trang dưới dạng chữ và nằm trong một biến: không dựng HTML từ nó, không cookie, không kho lưu của trình duyệt, không địa chỉ
        for forbidden in ("innerHTML", "localStorage", "sessionStorage", "document.cookie = 'session", "location.hash", "console."):
            self.assertNotIn(forbidden, script)
        # the words follow the visitor's language
        # chữ theo ngôn ngữ của người xem
        page_vi = self.call("GET", "/mcp/connect", Accept_Language="vi")[1].decode()
        self.assertIn('lang="vi"', page_vi)
        self.assertNotIn("Connect an AI tool", page_vi)
        self.assertNotIn("Waiting for an admin to approve", self.call("GET", "/mcp-connect.js", Accept_Language="vi")[1].decode())
        settings.MCP_ENABLED = False
        try:
            self.assertEqual(self.call("GET", "/mcp/connect")[0], 404)
            self.assertEqual(self.call("GET", "/mcp-connect.js")[0], 404)
        finally:
            settings.MCP_ENABLED = True

    def test_the_admin_page_gets_the_calls_and_knows_the_kind(self):
        token = self.pair("Seen of Hoa", "people")
        self.summary(token)
        data = json.loads(self.call("GET", "/admin/data", Cookie="session=tok-mcp-adm")[1])
        self.assertEqual((data["mcpCalls"][0]["tv"], data["mcpCalls"][0]["ok"]), ("Seen of Hoa", True))
        self.assertNotIn("mcp-call", [x.get("action") for x in data["auditLog"]])
        self.assertNotIn(token, json.dumps(data))
        with open(os.path.join(os.path.dirname(w.__file__), "static", "admin.js"), encoding="utf-8") as f:
            admin_js = f.read()
        # the admin page names this kind, sends the scope the admin chose, and offers no reload for a key
        # trang quản trị gọi tên loại này, gửi phạm vi quản trị đã chọn, và không có nút tải lại cho khoá
        for needed in ("y.kind === 'mcp'", "scope: scope.value", "t.kind !== 'mcp'", "snapshot.mcpCalls"):
            self.assertIn(needed, admin_js)

    def test_the_board_points_to_the_connect_page_only_while_mcp_is_on(self):
        """Admins and view-only accounts find the way to /mcp/connect on /board and on the Admin page; a wall display does not,
        and with MCP=0 nothing points to a page that is not there.
        Quản trị và tài khoản chỉ xem thấy đường tới /mcp/connect ở /board và trang Quản trị; màn hình treo tường thì không,
        và khi MCP=0 thì không có gì trỏ tới một trang không có."""
        stores.ACCOUNTS.d["accounts"]["wall"] = {"role": security.WALL, "secret": ""}
        login.SESSIONS.sessions["tok-mcp-wall"] = ("wall", NOW + 3600)
        try:
            for cookie in ("session=tok-mcp-adm", "session=tok-mcp-viewer"):
                status, b, _ = self.call("GET", "/board", Cookie=cookie)
                self.assertEqual(status, 200)
                self.assertIn('<a href="/mcp/connect">Connect an AI tool</a>', b.decode())
            page_vi = self.call("GET", "/board", Cookie="session=tok-mcp-viewer", Accept_Language="vi")[1].decode()
            self.assertIn('<a href="/mcp/connect">', page_vi)
            self.assertNotIn("Connect an AI tool", page_vi)
            self.assertTrue(json.loads(self.call("GET", "/admin/data", Cookie="session=tok-mcp-adm")[1])["mcpOn"])
            # a wall display cannot open /board, its own page has no such link, and the board drawn for it would not have one either
            # màn hình treo tường không mở được /board, trang của nó không có link này, và bảng vẽ cho nó cũng không có
            self.assertNotEqual(self.call("GET", "/board", Cookie="session=tok-mcp-wall")[0], 200)
            self.assertNotIn("/mcp/connect", self.call("GET", "/", Cookie="session=tok-mcp-wall")[1].decode())
            self.assertNotIn("/mcp/connect", pages.page_board("wall", NOW, security.WALL).decode())
            settings.MCP_ENABLED = False
            try:
                for cookie in ("session=tok-mcp-adm", "session=tok-mcp-viewer"):
                    self.assertNotIn("/mcp/connect", self.call("GET", "/board", Cookie=cookie)[1].decode())
                self.assertFalse(json.loads(self.call("GET", "/admin/data", Cookie="session=tok-mcp-adm")[1])["mcpOn"])
            finally:
                settings.MCP_ENABLED = True
        finally:
            del stores.ACCOUNTS.d["accounts"]["wall"]
            del login.SESSIONS.sessions["tok-mcp-wall"]
        with open(os.path.join(os.path.dirname(w.__file__), "static", "admin.js"), encoding="utf-8") as f:
            admin_js = f.read()
        # the Admin page draws the link and its copy button only when the server says the gate is on
        # trang Quản trị chỉ vẽ link và nút chép khi máy chủ báo cổng đang bật
        for needed in ("if (!snapshot.mcpOn) return null", "location.origin + '/mcp/connect'", "tx('Copy link')"):
            self.assertIn(needed, admin_js)

    def test_old_call_rows_are_dropped_sooner_than_the_rest(self):
        folder = tempfile.mkdtemp(dir=TMP)
        log = stores.AuditLog(db.Database(os.path.join(folder, "board.db"), db.DATA_STEPS, "NORMAL"))
        now = datetime.now(settings.LOCAL_TZ)
        months = ["%04d-%02d" % ((now.year, now.month - back) if now.month - back > 0 else (now.year - 1, now.month - back + 12)) for back in (0, 2, 3, 4, 11)]
        with log.db.tx() as c:
            for month in months:
                for action in ("mcp-call", "login"):
                    c.execute("INSERT INTO audit (at, month, action, body) VALUES (?, ?, ?, ?)", (month + "-01T00:00:00+07:00", month, action, json.dumps({"action": action})))
        log.write(action="login")
        left = {(month, action) for month, action in log.db.rows("SELECT month, action FROM audit")}
        self.assertEqual({m for m, a in left if a == "mcp-call"}, set(months[:3]))
        self.assertEqual({m for m, a in left if a == "login"}, set(months))


class TelegramAsk(unittest.TestCase):
    """Asking the board from a Telegram chat. The bot process is played by these tests: it hands a message to /bot/telegram with its key
    and gets back what to send. A chat reads nothing until an admin approves its code, then reads the wall view within its scope.
    Hỏi bảng từ một chat Telegram. Các bài test này đóng vai tiến trình bot: nó đưa một tin tới /bot/telegram kèm khoá của nó
    và nhận lại thứ cần gửi. Chat không đọc được gì cho tới khi quản trị duyệt mã của nó, rồi đọc phần treo tường trong phạm vi của nó."""

    KEY = "bot-key-" + "k" * 40
    PRIVATE = ("@example.com", IP_LAN, IP_PUBLIC, NET_CUSTOM, "device-an", "device-binh")
    HOA, LAN = "700100200", "700100201"

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": "", "telegramId": cls.LAN, "telegramUser": "lan_kt"}}}
        login.SESSIONS.sessions["tok-tg-adm"] = ("adm", NOW + 3600)
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
        chat.LIMIT.__init__(settings.TELEGRAM_CALLS_PER_CHAT, settings.TELEGRAM_CALLS_WINDOW_SECONDS)
        chat.STRANGERS.__init__()
        stores.TELEGRAM_BOT.__init__()
        login.SESSIONS.confirmed_at["tok-tg-adm"] = time.time()
        self.rows_before = set(stores.TV.d)
        self.was = (settings.TELEGRAM_ASK_ENABLED, settings.TELEGRAM_ASK_KEY, chat.role_view)
        settings.TELEGRAM_ASK_ENABLED, settings.TELEGRAM_ASK_KEY = True, self.KEY
        # most tests read a board they know line by line; the real one is read in test_the_real_board_goes_out_without_private_fields
        # phần lớn bài test đọc một bảng mà chúng biết từng dòng; bảng thật được đọc ở test_the_real_board_goes_out_without_private_fields
        self.roles_asked = []
        chat.role_view = lambda role, now: self.roles_asked.append(role) or test_ask.WALL

    def tearDown(self):
        settings.TELEGRAM_ASK_ENABLED, settings.TELEGRAM_ASK_KEY, chat.role_view = self.was
        for tv_id in set(stores.TV.d) - self.rows_before:
            stores.TV.d.pop(tv_id, None)

    def call(self, method, path, body=None, **headers):
        headers = {k.replace("_", "-"): v for k, v in headers.items()}
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def bot(self, msg, key=None, **headers):
        """What the bot process does with one message. Returns (status, the parsed answer).
        Việc tiến trình bot làm với một tin nhắn. Trả (mã trạng thái, câu trả lời đã phân tích)."""
        raw = msg if isinstance(msg, (str, bytes)) else json.dumps(msg)
        status, b = self.call("POST", "/bot/telegram", raw, Authorization="Bearer " + (self.KEY if key is None else key), **headers)
        try:
            return status, json.loads(b)
        except ValueError:
            return status, None

    def say(self, text, who=None, **more):
        status, d = self.bot(dict({"from": who or self.HOA, "chat": "private", "username": "hoa_ql", "lang": "en", "text": text}, **more))
        self.assertEqual(status, 200)
        return d

    def admin(self, path, body):
        status, b = self.call("POST", path, json.dumps(body), Cookie="session=tok-tg-adm", Origin=self.origin)
        return status, json.loads(b)

    def code_for(self, who=None, **more) -> str:
        d = self.say("/start", who, **more)
        m = re.search(r"\b(\d{4})-(\d{4})\b", d["text"])
        self.assertIsNotNone(m, d)
        return m.group(1) + m.group(2)

    def pair(self, who=None, name="Hoa on Telegram", scope=None):
        code = self.code_for(who)
        self.assertEqual(self.admin("/admin/tv-approve", dict({"code": code, "name": name}, **({"scope": scope} if scope else {})))[0], 200)
        d = self.say("hello", who)
        self.assertIn("Connected to the board as: " + name, d["text"])
        return d

    def month(self):
        return datetime.now(settings.LOCAL_TZ).strftime("%Y-%m")

    def rows(self):
        return [v for k, v in stores.TV.d.items() if k not in self.rows_before]

    # who may call the path
    # ai được gọi đường này

    def test_off_means_the_path_is_gone(self):
        settings.TELEGRAM_ASK_ENABLED = False
        self.assertEqual(self.bot({"from": self.HOA, "chat": "private", "text": "/start"})[0], 404)

    def test_a_short_key_never_turns_it_on(self):
        for env, on in (({"TELEGRAM_ASK": "1", "TELEGRAM_ASK_KEY": "k" * 31}, False), ({"TELEGRAM_ASK": "1", "TELEGRAM_ASK_KEY": ""}, False),
                        ({"TELEGRAM_ASK": "", "TELEGRAM_ASK_KEY": "k" * 40}, False), ({"TELEGRAM_ASK": "0", "TELEGRAM_ASK_KEY": "k" * 40}, False),
                        ({"TELEGRAM_ASK": "true", "TELEGRAM_ASK_KEY": "k" * 40}, False), ({"TELEGRAM_ASK": "1", "TELEGRAM_ASK_KEY": "k" * 32}, True)):
            enabled = env["TELEGRAM_ASK"].strip() == "1" and len(env["TELEGRAM_ASK_KEY"].strip()) >= 32
            self.assertEqual(enabled, on, env)
        # the line above restates the rule; this one pins the rule in settings.py to it
        # dòng trên nhắc lại quy tắc; dòng này buộc quy tắc trong settings.py phải đúng như thế
        src = inspect.getsource(settings)
        self.assertIn('TELEGRAM_ASK_ENABLED = os.environ.get("TELEGRAM_ASK", "0").strip() == "1" and len(TELEGRAM_ASK_KEY) >= 32', src)

    def test_no_key_or_a_wrong_key_is_refused(self):
        tv_id, tv_token = stores.TV.create({"name": "Lobby TV tg", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        mcp_id, mcp_token = stores.TV.create({"name": "Key tg", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test", "kind": settings.KIND_MCP}, time.time())
        msg = {"from": self.HOA, "chat": "private", "text": "/start"}
        for key in ("", "wrong", self.KEY[:-1], self.KEY + "x", "test", tv_token, mcp_token, stores.chat_key(self.HOA)):
            status, d = self.bot(msg, key=key)
            self.assertEqual(status, 401, key)
            self.assertNotIn("text", d)
        self.assertEqual(self.call("POST", "/bot/telegram", json.dumps(msg))[0], 401)
        self.assertEqual(self.call("POST", "/bot/telegram", json.dumps(msg), Cookie="session=tok-tg-adm")[0], 401)
        self.assertEqual(stores.TV_PAIRING.pending, {})

    def test_a_request_that_came_through_a_proxy_is_told_the_path_does_not_exist(self):
        msg = {"from": self.HOA, "chat": "private", "text": "/start"}
        for header in w.FORWARDED_HEADERS:
            status, d = self.bot(msg, **{header: "203.0.113.9"})
            self.assertEqual(status, 404, header)
        self.assertEqual(self.bot(msg, Origin=self.origin)[0], 404)
        self.assertEqual(stores.TV_PAIRING.pending, {})
        self.assertEqual(self.bot(msg)[0], 200)

    def test_only_this_machine_counts_as_direct(self):
        class Fake:
            headers = {}
            from_this_machine = w.Handler.from_this_machine
        for address, direct in (("127.0.0.1", True), ("::1", True), ("192.168.77.5", False), ("203.0.113.9", False), ("::ffff:203.0.113.9", False)):
            fake = Fake()
            fake.client_address = (address, 5)
            self.assertEqual(fake.from_this_machine(), direct, address)

    def test_the_bot_with_its_key_is_not_stopped_as_a_prober(self):
        msg = {"from": self.HOA, "chat": "private", "text": "/start"}
        statuses = [self.bot(msg, key="wrong")[0] for _ in range(40)]
        self.assertIn(429, statuses)
        self.assertEqual(self.bot(msg)[0], 200)

    def test_only_post(self):
        self.assertEqual(self.call("GET", "/bot/telegram", Authorization="Bearer " + self.KEY)[0], 404)

    def test_what_is_not_a_message_is_refused(self):
        self.assertEqual(self.bot("not json")[0], 400)
        self.assertEqual(self.bot("[1, 2]")[0], 400)
        self.assertEqual(self.bot('{"from": NaN}')[0], 400)
        self.assertEqual(self.bot("")[0], 413)
        self.assertEqual(self.bot(json.dumps({"from": self.HOA, "chat": "private", "text": "x" * chat.MAX_MESSAGE_BYTES}))[0], 413)

    def test_a_message_with_no_usable_sender_gets_no_answer(self):
        for sender in (None, "", "12a", "-5", -5, True, 1.5, "1" * 21, ["1"], {"id": 1}):
            status, d = self.bot({"from": sender, "chat": "private", "text": "/start"})
            self.assertEqual((status, d), (200, {"text": ""}), repr(sender))
        self.assertEqual(self.bot({"chat": "private", "text": "/start"}), (200, {"text": ""}))
        self.assertEqual(stores.TV_PAIRING.pending, {})

    def test_the_sender_may_come_as_a_number(self):
        self.assertIn("Pairing code", self.say("/start", int(self.HOA))["text"])
        self.assertEqual([r["telegramId"] for r in stores.TV_PAIRING.pending.values()], [self.HOA])

    # a chat no admin approved
    # chat chưa được quản trị duyệt

    def test_a_stranger_reads_nothing_and_is_told_once(self):
        first = self.say("cost")
        self.assertEqual(first, {"text": "🔌 This chat is not connected to the board. Send /start to get a pairing code."})
        for text in ("cost", "/waiting", "/help", "/stop", "who is waiting", None):
            self.assertEqual(self.say(text), {"text": ""})
        self.assertEqual(self.roles_asked, [])
        self.assertEqual(self.say("cost", self.LAN)["text"], first["text"])
        self.assertEqual(self.rows(), [])

    def test_a_stranger_is_told_again_after_an_hour(self):
        self.assertTrue(chat.STRANGERS.may_tell("1", 1000.0))
        self.assertFalse(chat.STRANGERS.may_tell("1", 1000.0 + settings.TELEGRAM_STRANGER_SECONDS - 1))
        self.assertTrue(chat.STRANGERS.may_tell("2", 1000.0))
        self.assertTrue(chat.STRANGERS.may_tell("1", 1000.0 + settings.TELEGRAM_STRANGER_SECONDS))

    def test_start_gives_a_code_and_the_same_code_again(self):
        d = self.say("/start")
        self.assertEqual(d["text"].split("\n")[:2], ["📊 AI Worker", ""])
        self.assertRegex(d["text"].split("\n")[2], r"^🔑 Pairing code: \d{4}-\d{4} \(good for 10 min\)\.$")
        self.assertIn("never asks for a login code or a password", d["text"])
        self.assertNotIn("keyboard", d)
        self.assertEqual(self.say("/start"), d)
        self.assertEqual(self.say("/start@example_bot 12345"), d)
        self.assertEqual(len(stores.TV_PAIRING.pending), 1)
        self.assertEqual(self.rows(), [])
        # near the end of its time the code still says a whole minute, never zero
        # gần hết giờ mã vẫn ghi tròn một phút, không bao giờ ghi không
        code, = stores.TV_PAIRING.pending
        stores.TV_PAIRING.pending[code]["expiresAt"] = time.time() + 90
        self.assertIn("(good for 2 min)", self.say("/start")["text"])
        stores.TV_PAIRING.pending[code]["expiresAt"] = time.time() + 5
        self.assertIn("(good for 1 min)", self.say("/start")["text"])

    def test_a_new_code_is_logged_once(self):
        before = len([x for x in all_audit_rows() if x["action"] == "tv-request-code" and x.get("kind") == "telegram"])
        for _ in range(3):
            self.say("/start", "700999001", username="someone")
        rows = [x for x in all_audit_rows() if x["action"] == "tv-request-code" and x.get("kind") == "telegram"]
        self.assertEqual(len(rows) - before, 1)
        self.assertEqual((rows[-1]["telegramUser"], rows[-1]["telegramId"]), ("someone", "700999001"))

    def test_the_code_comes_in_the_language_of_the_person(self):
        d = self.say("/start", lang="vi")
        self.assertIn(lang.VI["Pairing code: {code} (good for {minutes} min)."].split("{code}")[0], d["text"])
        self.assertIn(lang.VI["Then send any message here. This bot never asks for a login code or a password."], d["text"])

    def test_waiting_chats_are_limited_and_do_not_take_a_tvs_place(self):
        for i in range(settings.TELEGRAM_PENDING_MAX):
            self.assertIn("Pairing code", self.say("/start", "7100%05d" % i)["text"])
        self.assertEqual(self.say("/start", "710099999"), {"text": "🚦 Too many chats are waiting for approval. Try again in a few minutes."})
        self.assertEqual(self.say("/start", "710099999"), {"text": ""})
        # the chats that wait still get their own code back
        # các chat đang chờ vẫn nhận lại đúng mã của mình
        self.assertIn("Pairing code", self.say("/start", "710000000")["text"])
        # screens are counted apart: a room full of waiting chats leaves every place for TVs
        # màn hình được đếm riêng: chat chờ đầy chỗ vẫn để nguyên chỗ cho TV
        for _ in range(settings.TV_PENDING_PER_IP):
            status, b = self.call("POST", "/tv/request-code", "")
            self.assertEqual(status, 200)
            self.assertIn("code", json.loads(b))

    # pairing
    # ghép

    def test_the_admin_sees_whose_telegram_it_is(self):
        status, view = self.admin("/admin/tv-view", {"code": self.code_for()})
        self.assertEqual(status, 200)
        self.assertEqual((view["kind"], view["telegramUser"], view["telegramId"], view["account"], view["device"], view["similar"]),
                         ("telegram", "hoa_ql", self.HOA, "", "Telegram", []))
        # a Telegram that is linked to a board account for logging in is named with that account
        # Telegram đã liên kết với một tài khoản bảng để đăng nhập thì được nêu kèm tài khoản đó
        view = self.admin("/admin/tv-view", {"code": self.code_for(self.LAN, username="lan_kt")})[1]
        self.assertEqual((view["telegramUser"], view["telegramId"], view["account"]), ("lan_kt", self.LAN, "viewer"))

    def test_a_username_with_other_characters_is_dropped(self):
        view = self.admin("/admin/tv-view", {"code": self.code_for(username="<b>x</b>")})[1]
        self.assertEqual(view["telegramUser"], "")
        view = self.admin("/admin/tv-view", {"code": self.code_for(self.LAN, username=5)})[1]
        self.assertEqual(view["telegramUser"], "")

    def test_an_approved_chat_is_welcomed_and_reads_totals_unless_the_admin_chose_people(self):
        d = self.pair()
        lines = d["text"].split("\n")
        self.assertEqual(lines[:6], ["📊 AI Worker", "", "✅ Connected to the board as: Hoa on Telegram", "🔒 This chat reads team and office totals only.",
                                     "🔐 This bot never asks for a login code or a password.", ""])
        self.assertIn("⏳ /waiting - Who is waiting for an answer, longest first", lines)
        self.assertEqual(d["keyboard"], ask.keyboard("en"))
        row, = self.rows()
        self.assertEqual((row["kind"], row["scope"], row["telegramId"], row["telegramUser"], row["name"], row["approvedBy"]),
                         ("telegram", "totals", self.HOA, "hoa_ql", "Hoa on Telegram", "adm"))
        self.assertNotIn("keyStart", row)
        self.assertEqual(stores.TV_PAIRING.pending, {})
        d = self.pair(self.LAN, "Lan on Telegram", "people")
        self.assertIn("This chat reads each person's numbers.", d["text"])
        self.assertEqual(sorted(r["scope"] for r in self.rows()), ["people", "totals"])

    def test_a_scope_that_is_not_people_is_totals(self):
        for i, scope in enumerate(("PEOPLE", "all", "", 5, ["people"])):
            code = self.code_for("72000000%d" % i)
            self.assertEqual(self.admin("/admin/tv-approve", {"code": code, "name": "Chat %d" % i, "scope": scope})[0], 200)
            self.say("hi", "72000000%d" % i)
        self.assertEqual({r["scope"] for r in self.rows()}, {"totals"})

    def test_until_approved_the_chat_still_reads_nothing(self):
        code = self.code_for()
        self.assertEqual(self.say("cost")["text"], "🔌 This chat is not connected to the board. Send /start to get a pairing code.")
        self.admin("/admin/tv-view", {"code": code})
        self.assertEqual(self.say("cost"), {"text": ""})
        self.assertEqual(self.roles_asked, [])
        self.assertEqual(self.admin("/admin/tv-approve", {"code": code, "name": "Hoa"})[0], 200)
        # the message that finishes the pairing gets the welcome, not numbers
        # tin nhắn hoàn tất việc ghép nhận lời chào, không nhận số liệu
        d = self.say("cost")
        self.assertIn("Connected to the board as: Hoa", d["text"])
        self.assertNotIn("$", d["text"])
        self.assertIn("Cost today: $16.25", self.say("cost")["text"])

    def test_a_code_that_was_not_approved_in_time_is_gone(self):
        code = self.code_for()
        stores.TV_PAIRING.pending[code]["expiresAt"] = time.time() - 1
        self.assertEqual(self.admin("/admin/tv-approve", {"code": code, "name": "Late"})[0], 400)
        self.assertNotEqual(self.code_for(), code)

    def test_the_approval_is_logged_with_the_kind(self):
        self.pair(name="Logged chat", scope="people")
        rows = all_audit_rows()
        approve = [x for x in rows if x["action"] == "tv-approve" and x.get("tv") == "Logged chat"][-1]
        self.assertEqual((approve["kind"], approve["scope"], approve["telegramUser"], approve["actor"]), ("telegram", "people", "hoa_ql", "adm"))
        joined = [x for x in rows if x["action"] == "tv-joined" and x.get("tv") == "Logged chat"][-1]
        self.assertEqual((joined["kind"], joined["approvedBy"], joined["telegramUser"]), ("telegram", "adm", "hoa_ql"))

    def test_a_chat_cannot_take_the_row_of_a_screen_or_of_a_key(self):
        tv_id, _ = stores.TV.create({"name": "Lobby TV chat", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, time.time())
        mcp_id, _ = stores.TV.create({"name": "Key chat", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test", "kind": settings.KIND_MCP}, time.time())
        self.pair(self.LAN, "Lan chat")
        chat_id = stores.TV.id_of(stores.chat_key(self.LAN))
        code = self.code_for()
        for replace_id in (tv_id, mcp_id, chat_id):
            status, d = self.admin("/admin/tv-approve", {"code": code, "name": "Taker", "replaceId": replace_id})
            self.assertEqual(status, 400, replace_id)
        self.assertEqual({stores.TV.d[i]["name"] for i in (tv_id, mcp_id, chat_id)}, {"Lobby TV chat", "Key chat", "Lan chat"})
        # and a screen cannot take a chat's row
        # và màn hình không lấy được dòng của chat
        status, b = self.call("POST", "/tv/request-code", "")
        self.assertEqual(self.admin("/admin/tv-approve", {"code": json.loads(b)["code"], "name": "TV taker", "replaceId": chat_id})[0], 400)

    def test_the_number_of_chats_is_limited_apart_from_screens_and_keys(self):
        before = (stores.TELEGRAM_CHATS_MAX, views.TELEGRAM_CHATS_MAX)
        stores.TELEGRAM_CHATS_MAX = views.TELEGRAM_CHATS_MAX = 1
        try:
            self.pair()
            now = time.time()
            self.assertEqual(stores.TV.count(now, settings.KIND_TELEGRAM), 1)
            code = self.code_for(self.LAN)
            status, d = self.admin("/admin/tv-approve", {"code": code, "name": "One too many"})
            self.assertEqual(status, 400)
            self.assertIn("Telegram chats", d["error"])
            # a screen and an MCP key still fit
            # màn hình và khoá MCP vẫn còn chỗ
            stores.TV.create({"name": "TV beside chats", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, now)
            stores.TV.create({"name": "Key beside chats", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test", "kind": settings.KIND_MCP}, now)
            # the limit holds in the store too, when two approvals race past the admin's check
            # giới hạn cũng được giữ trong kho, khi hai lần duyệt chạy đua qua bước kiểm của quản trị
            with self.assertRaises(ValueError):
                stores.TV.create({"name": "Raced", "approvedBy": "adm", "ip": "", "device": "Telegram", "kind": settings.KIND_TELEGRAM, "telegramId": "799"}, now)
        finally:
            stores.TELEGRAM_CHATS_MAX, views.TELEGRAM_CHATS_MAX = before

    # answers
    # câu trả lời

    def test_an_approved_chat_gets_the_answer_of_its_scope(self):
        self.pair(scope="people")
        self.pair(self.LAN, "Lan", None)
        now_ms = time.time() * 1000
        for command in ask.DATA_COMMANDS:
            if command == ask.WAITING:
                continue
            for who, scope in ((self.HOA, "people"), (self.LAN, "totals")):
                d = self.say("/" + command, who)
                self.assertEqual(d["text"], ask.answer(command, test_ask.WALL, scope, now_ms, "en"), (command, scope))
                self.assertEqual(d["keyboard"], ask.keyboard("en"))
        people, totals = self.say("/waiting")["text"], self.say("/waiting", self.LAN)["text"]
        self.assertIn("1. Dazed (Da Nang)", people)
        for name in test_ask.NAMES:
            self.assertNotIn(name, totals)
        self.assertIn("This chat reads totals only.", totals)

    def test_the_board_is_read_as_a_wall_screen_reads_it(self):
        self.pair(scope="people")
        for text in ("/cost", "/waiting", "team", "Offices"):
            self.say(text)
        self.assertEqual(self.roles_asked, [security.WALL] * 4)

    def test_the_real_board_goes_out_without_private_fields(self):
        chat.role_view = self.was[2]
        self.pair(scope="people")
        for command in ask.COMMANDS:
            if command == ask.STOP:
                continue
            text = self.say("/" + command)["text"]
            self.assertTrue(text.startswith("📊 AI Worker"), text)
            for private in self.PRIVATE:
                self.assertNotIn(private, text, command)
        team = self.say("/team")["text"]
        self.assertRegex(team, r"People in the team: [1-9]")
        # the person with a name is there; the one whose name is an email shows as a device, as on the wall
        # người có tên thì có mặt; người mà tên là email thì hiện thành một máy, như trên màn treo tường
        self.assertIn("Hanoi", self.say("/offices")["text"])

    def test_buttons_and_typed_questions_work_like_commands(self):
        self.pair(scope="people")
        cost = self.say("/cost")["text"]
        for text in ("Cost", "cost", "how much today?", "what did we spend"):
            self.assertEqual(self.say(text)["text"], cost, text)

    def test_the_answer_follows_the_language_of_the_message_then_of_the_app(self):
        self.pair(scope="people")
        en, vi = self.say("/cost"), self.say("/cost", lang="vi")
        self.assertIn("Cost today", en["text"])
        self.assertIn(lang.VI["US dollars at API prices, not an invoice."], vi["text"])
        self.assertEqual(vi["keyboard"], ask.keyboard("vi"))
        self.assertEqual(self.say("/chiphi"), vi)
        self.assertEqual(self.say(vi["keyboard"][0][1]), vi)
        self.assertEqual(self.say("/cost", lang="vi-VN"), vi)
        self.assertEqual(self.say("/cost", lang="de"), en)
        self.assertEqual(self.say("/cost", lang=None), en)

    def test_anything_else_gets_the_list_of_commands(self):
        self.pair()
        help_text = ask.answer(ask.HELP, None, "", 0, "en")
        for text in ("hello", "/help", "/nothing", None, "", 5):
            d = self.say(text)
            self.assertEqual((d["text"], d["keyboard"]), (help_text, ask.keyboard("en")), repr(text))
        again = self.say("/start")
        self.assertIn("This chat is already connected to the board.", again["text"])
        self.assertIn("This chat reads team and office totals only.", again["text"])
        self.assertEqual(len(self.rows()), 1)

    # log
    # nhật ký

    def test_each_answer_with_numbers_is_logged_without_the_words_typed(self):
        self.pair(name="Hoa log", scope="people")
        before = len(stores.AUDIT_LOG.read_calls(self.month(), 10000))
        self.say("/cost")
        self.say("how much did SECRETWORD spend")
        self.say("/help")
        self.say("hello SECRETWORD")
        calls = stores.AUDIT_LOG.read_calls(self.month(), 10000)
        self.assertEqual(len(calls) - before, 2)
        row = calls[0]
        self.assertEqual({k: v for k, v in row.items() if k != "at"},
                         {"action": "telegram-ask", "tv": "Hoa log", "id": stores.TV.id_of(stores.chat_key(self.HOA)), "tool": "cost", "ok": True, "client": "Telegram"})
        everything = json.dumps(all_audit_rows())
        self.assertNotIn("SECRETWORD", everything)
        self.assertNotIn("how much", everything)

    def test_answers_are_read_with_the_mcp_calls_and_not_in_the_admins_own_log(self):
        self.pair(name="Hoa reads", scope="people")
        self.say("/team")
        self.assertEqual(stores.AUDIT_LOG.read_calls(self.month(), 10000)[0]["tool"], "team")
        self.assertNotIn("telegram-ask", [x["action"] for x in stores.AUDIT_LOG.read(self.month(), 10000)])
        status, b = self.call("GET", "/admin/data", Cookie="session=tok-tg-adm")
        d = json.loads(b)
        self.assertEqual(d["mcpCalls"][0]["action"], "telegram-ask")
        self.assertNotIn("telegram-ask", [x["action"] for x in d["auditLog"]])

    def test_old_answers_leave_the_log_with_the_mcp_calls(self):
        self.assertEqual(stores.AUDIT_LOG.READ_ACTIONS, ("mcp-call", "telegram-ask"))
        with db.data_db().tx() as c:
            for action in ("telegram-ask", "mcp-call", "login"):
                c.execute("INSERT INTO audit (at, month, action, body) VALUES (?, ?, ?, ?)", ("2020-01-01T00:00:00", "2020-01", action, json.dumps({"action": action, "old": "tg-test"})))
            recent = (datetime.now(settings.LOCAL_TZ).replace(day=1) - timedelta(days=settings.MCP_CALL_KEEP_MONTHS * 31 + 5)).strftime("%Y-%m")
            for action in ("telegram-ask", "login"):
                c.execute("INSERT INTO audit (at, month, action, body) VALUES (?, ?, ?, ?)", (recent + "-01T00:00:00", recent, action, json.dumps({"action": action, "recent": "tg-test"})))
        stores.AUDIT_LOG.month = ""
        stores.AUDIT_LOG.write(action="noop-tg-test")
        left = [(x["action"], "old" in x) for x in all_audit_rows() if x.get("old") == "tg-test" or x.get("recent") == "tg-test"]
        self.assertEqual(left, [("login", False)])

    # limits, stopping, revoking
    # giới hạn, tự gỡ, thu hồi

    def test_a_chat_that_asks_too_often_is_told_once_then_gets_nothing(self):
        self.pair(name="Busy chat", scope="people")
        self.pair(self.LAN, "Calm chat")
        chat.LIMIT.__init__(settings.TELEGRAM_CALLS_PER_CHAT, settings.TELEGRAM_CALLS_WINDOW_SECONDS)
        for _ in range(settings.TELEGRAM_CALLS_PER_CHAT):
            self.assertIn("Cost today", self.say("/cost")["text"])
        self.assertEqual(self.say("/cost"), {"text": "🚦 This chat has asked too often. Try again in a few minutes."})
        for text in ("/cost", "/help", "hello"):
            self.assertEqual(self.say(text), {"text": ""})
        self.assertIn("Cost today", self.say("/cost", self.LAN)["text"])
        self.assertEqual(len([x for x in all_audit_rows() if x["action"] == "telegram-rate-limited" and x.get("tv") == "Busy chat"]), 1)
        # stopping still works when the chat is over its limit
        # tự gỡ vẫn chạy khi chat đã quá giới hạn
        self.assertIn("Disconnected", self.say("/stop")["text"])

    def test_stop_disconnects_the_chat(self):
        self.pair(name="Leaving chat", scope="people")
        chat_id = stores.TV.id_of(stores.chat_key(self.HOA))
        d = self.say("/stop")
        self.assertEqual(d, {"text": "👋 Disconnected: this chat no longer reads the board. Send /start to ask for a new code.", "removeKeyboard": True})
        self.assertEqual(self.rows(), [])
        stop = [x for x in all_audit_rows() if x["action"] == "telegram-stop"][-1]
        self.assertEqual((stop["tv"], stop["id"], stop["kind"]), ("Leaving chat", chat_id, "telegram"))
        self.assertEqual(self.say("/cost")["text"], "🔌 This chat is not connected to the board. Send /start to get a pairing code.")
        self.assertEqual(self.say("/cost"), {"text": ""})
        # it may pair again, and then has one row
        # nó ghép lại được, và khi đó có một dòng
        self.pair(name="Back again")
        self.assertEqual([r["name"] for r in self.rows()], ["Back again"])

    def test_an_admin_revokes_a_chat_at_once(self):
        self.pair(name="Revoked chat", scope="people")
        chat_id = stores.TV.id_of(stores.chat_key(self.HOA))
        self.assertIn("Cost today", self.say("/cost")["text"])
        status, b = self.call("GET", "/admin/data", Cookie="session=tok-tg-adm")
        screen = [x for x in json.loads(b)["screens"] if x["id"] == chat_id][0]
        self.assertEqual((screen["kind"], screen["scope"], screen["telegramUser"], screen["telegramId"], screen["name"]), ("telegram", "people", "hoa_ql", self.HOA, "Revoked chat"))
        self.assertNotIn("hash", screen)
        self.assertIsNone(screen["upToDate"])
        self.assertEqual(self.admin("/admin/tv-revoke", {"id": chat_id})[0], 200)
        revoke = [x for x in all_audit_rows() if x["action"] == "tv-revoke"][-1]
        self.assertEqual((revoke["tv"], revoke["kind"]), ("Revoked chat", "telegram"))
        self.roles_asked.clear()
        self.assertEqual(self.say("/cost")["text"], "🔌 This chat is not connected to the board. Send /start to get a pairing code.")
        self.assertEqual(self.roles_asked, [])

    def test_a_chat_not_used_for_a_long_time_is_a_stranger_again(self):
        self.pair(scope="people")
        chat_id = stores.TV.id_of(stores.chat_key(self.HOA))
        row = stores.TV.d[chat_id]
        self.assertAlmostEqual(row["expiresAt"] - row["createdAt"], settings.TV_SESSION_SECONDS, delta=5)
        self.assertAlmostEqual(row["ceilingAt"] - row["createdAt"], settings.TV_CEILING_SECONDS, delta=5)
        stores.TV.mutate(lambda d: d[chat_id].update(expiresAt=int(time.time()) - 1))
        self.assertEqual(self.say("/cost")["text"], "🔌 This chat is not connected to the board. Send /start to get a pairing code.")

    def test_using_the_chat_renews_it_and_shows_on_the_admin_page(self):
        self.pair(scope="people")
        chat_id = stores.TV.id_of(stores.chat_key(self.HOA))
        soon = int(time.time()) + settings.TV_RENEW_WHEN_LEFT - 60
        stores.TV.mutate(lambda d: d[chat_id].update(expiresAt=soon, lastUsedAt=1))
        self.say("/team")
        row = stores.TV.d[chat_id]
        self.assertGreater(row["expiresAt"], soon + 3600)
        self.assertAlmostEqual(row["lastUsedAt"], time.time(), delta=5)
        self.assertEqual(row["lastIp"], "")
        self.assertAlmostEqual(stores.TV_STATUS.read(chat_id)["seenAt"], time.time(), delta=5)

    # groups
    # nhóm

    def test_a_group_or_a_channel_gets_no_answer_and_the_bot_is_told_to_leave(self):
        self.pair(scope="people")
        self.roles_asked.clear()
        before = len(all_audit_rows())
        for kind in ("group", "supergroup", "channel", "", None, "PRIVATE", 5):
            for text in ("/cost", "/start", "/stop", "hello"):
                self.assertEqual(self.say(text, chat=kind), {"text": "", "leave": True}, (kind, text))
        status, d = self.bot({"from": self.HOA, "text": "/cost"})
        self.assertEqual(d, {"text": "", "leave": True})
        self.assertEqual(self.roles_asked, [])
        self.assertEqual(len(all_audit_rows()), before)
        self.assertEqual(len(self.rows()), 1)

    # the chat's number opens nothing else
    # số của chat không mở được gì khác

    def test_the_chats_number_is_no_key_anywhere_else(self):
        self.pair(scope="people")
        key = stores.chat_key(self.HOA)
        self.assertEqual(key, "tg_" + self.HOA)
        now = time.time()
        self.assertIsNotNone(stores.TV.find(key, now, settings.KIND_TELEGRAM))
        self.assertIsNone(stores.TV.find(key, now))
        self.assertIsNone(stores.TV.find(key, now, settings.KIND_MCP))
        self.assertEqual(login.SESSIONS.user_and_role("session=" + key, now), (None, None))
        self.assertEqual(self.call("GET", "/data", Cookie="session=" + key)[0], 401)
        self.assertEqual(self.call("GET", "/ext/data", Authorization="Bearer " + key)[0], 401)
        self.assertEqual(self.call("POST", "/mcp", "{}", Authorization="Bearer " + key)[0], 401)
        self.assertEqual(self.call("POST", "/ext/unpair", "", Authorization="Bearer " + key)[0], 401)
        self.assertEqual(stores.TV.exit_screen(key, now), "")
        self.assertEqual(len(self.rows()), 1)
        # and no other key stands for a chat
        # và không khoá nào khác đứng thay được cho một chat
        tv_id, tv_token = stores.TV.create({"name": "TV not a chat", "approvedBy": "adm", "ip": IP_PUBLIC, "device": "test"}, now)
        self.assertIsNone(stores.TV.find(tv_token, now, settings.KIND_TELEGRAM))

    def test_the_public_pairing_paths_cannot_take_or_cancel_a_chats_code(self):
        code = self.code_for()
        key = stores.chat_key(self.HOA)
        self.assertFalse(stores.TV_PAIRING.has_key(key))
        self.assertEqual(self.admin("/admin/tv-approve", {"code": code, "name": "Mine"})[0], 200)
        # someone who knows the number asks the public paths for the approved pairing: there is none for them
        # người biết con số này hỏi các đường công khai để lấy lần ghép đã duyệt: không có gì cho họ
        for path, headers in (("/ext/poll", {"Authorization": "Bearer " + key}), ("/mcp/poll", {"Authorization": "Bearer " + key, "Origin": self.origin}),
                              ("/tv/poll", {"Cookie": "tv-pending=" + key})):
            status, b = self.call("POST", path, "", **headers)
            self.assertEqual((status, json.loads(b)), (200, {"status": "expired"}), path)
        self.assertEqual(self.rows(), [])
        # nor can they cancel it by asking for a code of their own under the same key
        # họ cũng không huỷ được nó bằng cách xin một mã của riêng mình dưới cùng khoá đó
        self.assertEqual(self.call("POST", "/ext/request-code", "", Authorization="Bearer " + key)[0], 200)
        self.assertEqual(self.call("POST", "/tv/request-code", "", Cookie="tv-pending=" + key)[0], 200)
        self.assertIn("Connected to the board as: Mine", self.say("hi")["text"])

    def test_a_chats_request_is_seen_only_as_a_chats(self):
        pairing = stores.TvPairing()
        code, left, fresh = pairing.request_chat("555", "someone", 1000.0)
        self.assertEqual((left, fresh), (settings.TV_CODE_SECONDS, True))
        self.assertEqual(pairing.request_chat("555", "other_name", 1090.0), (code, settings.TV_CODE_SECONDS - 90, False))
        key = stores.chat_key("555")
        self.assertEqual(pairing.poll(key, 1001.0), "expired")
        self.assertEqual(pairing.poll(key, 1001.0, chat=True), "pending")
        self.assertEqual(pairing.kind_of(code, 1001.0), "telegram")
        with self.assertRaises(ValueError):
            pairing.self_approve(code, "viewer", "", 1001.0)
        pairing.approve(code, "Chat 555", "adm", 1002.0, scope="people")
        self.assertEqual(pairing.poll(key, 1003.0), "expired")
        r = pairing.poll(key, 1003.0, chat=True)
        self.assertEqual((r["name"], r["scope"], r["kind"], r["telegramId"], r["telegramUser"], r["ip"]), ("Chat 555", "people", "telegram", "555", "someone", ""))
        self.assertEqual(pairing.poll(key, 1004.0, chat=True), "expired")
        # a screen's request is not seen as a chat's
        # yêu cầu của màn hình không được thấy như của chat
        tv_code, tv_key = pairing.request_code("", IP_PUBLIC, "test", 1005.0)
        self.assertEqual(pairing.poll(tv_key, 1006.0, chat=True), "expired")
        self.assertEqual(pairing.poll(tv_key, 1006.0), "pending")
        # after its time, the code is gone and the chat gets a new one
        # hết giờ thì mã mất và chat nhận mã mới
        again = pairing.request_chat("555", "someone", 1010.0)
        self.assertTrue(again[2])
        later = pairing.request_chat("555", "someone", 1010.0 + settings.TV_CODE_SECONDS + 1)
        self.assertTrue(later[2])
        self.assertEqual(sum(1 for r in pairing.pending.values() if r.get("kind") == "telegram"), 1)

    # the bot process
    # tiến trình bot

    def test_the_bot_says_how_it_is_doing_and_gets_the_command_list(self):
        self.assertEqual(stores.TELEGRAM_BOT.read(), {"state": "", "bot": "", "seenAt": 0})
        status, d = self.bot({"report": "conflict", "bot": "example_ask_bot"})
        self.assertEqual(status, 200)
        self.assertEqual(d, {"ok": True, "commands": {"en": [list(row) for row in ask.menu("en")], "vi": [list(row) for row in ask.menu("vi")]}})
        seen = stores.TELEGRAM_BOT.read()
        self.assertEqual((seen["state"], seen["bot"]), ("conflict", "example_ask_bot"))
        self.assertAlmostEqual(seen["seenAt"] / 1000, time.time(), delta=5)
        for state in stores.TelegramBotStatus.STATES:
            self.bot({"report": state, "bot": "example_ask_bot"})
            self.assertEqual(stores.TELEGRAM_BOT.read()["state"], state)
        # what is reported is shown to an admin, so only the known words and a name that can be a bot's name are kept
        # điều được báo sẽ hiện cho quản trị, nên chỉ giữ các từ đã biết và một cái tên có thể là tên bot
        for state, name in (("<b>pwned</b>", "<script>"), (5, 5), (None, None), ("OK", "a b"), ("", "x" * 33)):
            self.bot({"report": state, "bot": name})
            seen = stores.TELEGRAM_BOT.read()
            self.assertEqual((seen["state"], seen["bot"]), ("", ""), (state, name))
        # a report is not a message: no chat is touched and nothing is logged
        # lời báo không phải tin nhắn: không chat nào bị đụng tới và không ghi nhật ký gì
        self.assertEqual(stores.TV_PAIRING.pending, {})
        self.assertEqual(self.roles_asked, [])

    def test_a_message_handed_over_means_the_bot_is_reading(self):
        self.bot({"report": "unreachable", "bot": "example_ask_bot"})
        self.say("hello")
        seen = stores.TELEGRAM_BOT.read()
        self.assertEqual((seen["state"], seen["bot"]), ("ok", "example_ask_bot"))

    def test_the_admin_page_is_told_whether_it_is_on_and_how_the_bot_is_doing(self):
        self.bot({"report": "ok", "bot": "example_ask_bot"})
        d = json.loads(self.call("GET", "/admin/data", Cookie="session=tok-tg-adm")[1])
        self.assertEqual({k: d["telegramAsk"][k] for k in ("on", "state", "bot")}, {"on": True, "state": "ok", "bot": "example_ask_bot"})
        settings.TELEGRAM_ASK_ENABLED = False
        stores.TELEGRAM_BOT.__init__()
        d = json.loads(self.call("GET", "/admin/data", Cookie="session=tok-tg-adm")[1])
        self.assertEqual(d["telegramAsk"], {"on": False, "app": False, "state": "", "bot": "", "seenAt": 0})

    def test_the_bot_process_between_a_fake_telegram_and_this_server(self):
        """The whole way: a person writes in Telegram (played by FakeTelegram), the real bot process reads it and asks this server,
        an admin approves the chat, and the answers go back out with what Telegram needs to protect and show them.
        Trọn đường: một người viết trong Telegram (FakeTelegram đóng vai), tiến trình bot thật đọc tin và hỏi máy chủ này,
        quản trị duyệt chat, và các câu trả lời đi ra kèm những gì Telegram cần để bảo vệ và hiển thị chúng."""
        chat.role_view = self.was[2]
        telegram = test_telegram_bot.FakeTelegram()
        self.addCleanup(telegram.close)
        lines = []
        bot = telegram_bot.Bot(test_telegram_bot.TOKEN, self.origin, self.KEY, telegram.url, sleep=lambda seconds: None, log=lines.append, poll_seconds=0)
        who = int(self.HOA)
        telegram.say("who is waiting?", who)
        telegram.say("/start", who)
        self.assertEqual(bot.step(), 0)
        self.assertEqual(stores.TELEGRAM_BOT.read()["bot"], "example_ask_bot")
        self.assertEqual(stores.TELEGRAM_BOT.read()["state"], "ok")
        commands = [body for method, body in telegram.calls if method == "setMyCommands"]
        self.assertEqual([c.get("language_code") for c in commands], [None, "vi"])
        self.assertEqual([c["command"] for c in commands[0]["commands"]], [name for name, _ in ask.menu("en")])
        self.assertEqual([c["command"] for c in commands[1]["commands"]], [name for name, _ in ask.menu("vi")])
        told, code_message = telegram.sent()
        self.assertEqual(told["text"], "🔌 This chat is not connected to the board. Send /start to get a pairing code.")
        code = "".join(re.search(r"\b(\d{4})-(\d{4})\b", code_message["text"]).groups())
        view = self.admin("/admin/tv-view", {"code": code})[1]
        self.assertEqual((view["kind"], view["telegramUser"], view["telegramId"]), ("telegram", "hoa_ql", self.HOA))
        self.assertEqual(self.admin("/admin/tv-approve", {"code": code, "name": "Hoa via the bot", "scope": "people"})[0], 200)
        telegram.say("hello", who)
        telegram.say("/team", who)
        telegram.say("/tongquan", who)
        telegram.say("/cost", who, chat="group", chat_id=-100200)
        self.assertEqual(bot.step(), 0)
        welcome, team, team_vi = telegram.sent()[2:]
        self.assertIn("Connected to the board as: Hoa via the bot", welcome["text"])
        self.assertEqual(welcome["reply_markup"]["keyboard"], [[{"text": label} for label in row] for row in ask.keyboard("en")])
        self.assertRegex(team["text"], r"^📊 AI Worker · \d\d:\d\d\n\n👥 People in the team: [1-9]")
        self.assertIn(lang.VI["People in the team: {n}"].split("{n}")[0], team_vi["text"])
        self.assertEqual(team_vi["reply_markup"]["keyboard"][0][0], {"text": ask.keyboard("vi")[0][0]})
        self.assertEqual([body for method, body in telegram.calls if method == "leaveChat"], [{"chat_id": -100200}])
        for message in telegram.sent():
            self.assertEqual(message["chat_id"], who)
            self.assertIs(message["protect_content"], True)
            self.assertEqual(message["link_preview_options"], {"is_disabled": True})
            self.assertNotIn("parse_mode", message)
            for private in self.PRIVATE:
                self.assertNotIn(private, message["text"])
        self.assertEqual(stores.AUDIT_LOG.read_calls(self.month(), 2)[0]["tool"], "team")
        telegram.say("/stop", who)
        bot.step()
        self.assertEqual(telegram.sent()[-1]["reply_markup"], {"remove_keyboard": True})
        self.assertEqual(self.rows(), [])
        # nothing of all this reached the bot process's log
        # không gì trong tất cả những điều này lọt vào nhật ký của tiến trình bot
        log = "\n".join(lines)
        for private in ("hoa_ql", self.HOA, "Hoa via the bot", code, test_telegram_bot.TOKEN, self.KEY) + self.PRIVATE:
            self.assertNotIn(private, log)
        # with the feature turned off on the server, the bot process stops instead of taking messages it cannot answer
        # khi tính năng bị tắt ở máy chủ, tiến trình bot dừng lại chứ không nhận những tin nó không trả lời được
        settings.TELEGRAM_ASK_ENABLED = False
        telegram.say("/team", who)
        with self.assertRaises(telegram_bot.Refused):
            bot.step()

    def test_the_three_sides_of_the_wall(self):
        self.assertEqual([stores.side_of(k) for k in ("mcp", "telegram", "", None, "extension", "plugin", "tv", "TELEGRAM")], ["mcp", "telegram", "", "", "", "", "", ""])


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
        views.INGEST_GATE.buckets, views.INGEST_GATE.new_devices = {}, {}
        self.keys = getattr(self, "keys", {})
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
        """Sends like the plugin: with the shared key until the server hands the computer its own key, then with that key.
        Gửi như plugin: bằng khoá chung cho tới khi máy chủ trao cho máy khoá riêng, rồi bằng khoá đó."""
        try:
            device = json.loads(raw).get("device")
        except (ValueError, AttributeError):
            device = None
        key = self.keys.get(device, "k" * 40)
        status, body = self.call("POST", "/ingest", raw, {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            given = json.loads(body).get("deviceKey")
        except (ValueError, AttributeError):
            given = None
        if given and device:
            self.keys[device] = given
        return status

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

    def test_records_of_work_handed_to_helpers_reach_the_audit_log_once_and_not_the_device_file(self):
        now_ms = int(time.time() * 1000)
        rid = "%024x" % random.getrandbits(96)
        record = {"id": rid, "at": now_ms - 1000, "tool": "ask_chatgpt", "via": "plugin", "promptChars": 30, "answerChars": 10,
                  "promptHash": "c" * 32, "outcome": "ok", "prompt": "never kept"}
        sent = json.dumps(self.report(device="device-dlg", delegations=[record]))
        self.assertEqual(self.ingest(sent), 200)
        self.assertEqual(self.ingest(sent), 200)
        status, body = self.call("GET", "/admin/data", None, {"Cookie": "session=tok-sec"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        mine = [r for r in data["delegations"] if r.get("id") == rid]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["name"], mine[0]["worker"], mine[0]["outcome"]), ("Sec", "chatgpt", "ok"))
        self.assertGreaterEqual(data["delegationTotals"]["chatgpt"], 1)
        self.assertNotIn("never kept", body.decode())
        self.assertNotIn("delegations", devices.read_device("device-dlg") or {})
        self.addCleanup(drop_device, "device-dlg")

    def test_the_plugin_makes_device_ids_the_server_takes(self):
        # 0.24 plugins made may-... ids and every send got 400: the id the plugin builds must pass the server's rule
        # plugin 0.24 tạo mã may-... và mọi lần gửi bị 400: mã plugin tạo ra phải qua được quy tắc của máy chủ
        # newDeviceId in hooks/team.ts: its prefix and length, the longest one included, must pass
        # newDeviceId trong hooks/team.ts: tiền tố và độ dài của nó, kể cả mã dài nhất, phải qua được
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "team.ts"), encoding="utf-8") as f:
            source = f.read()
        prefix = re.search(r"return '([a-z]+-)' \+ Array\.from", source).group(1)
        length = int(re.search(r"DEVICE_ID_LENGTH = (\d+)", source).group(1))
        made = prefix + ("a1b2c3d4" * 8)[:length]
        self.assertTrue(settings.DEVICE_NAME_RE.match(made), made)
        self.assertEqual(self.ingest(json.dumps(self.report(device=made))), 200)
        self.assertEqual(self.ingest(json.dumps(self.report(device="may-a1b2c3d4"))), 400)

    def test_the_device_limit_counts_the_database(self):
        self.assertEqual(self.ingest(json.dumps(self.report(device="device-lim1", name="Lim", account="lim@example.com"))), 200)
        saved = devices.MAX_DEVICES
        devices.MAX_DEVICES = db.data_db().rows("SELECT COUNT(*) FROM devices")[0][0]
        try:
            self.assertEqual(self.ingest(json.dumps(self.report(device="device-lim2", name="Lim2", account="lim2@example.com"))), 507)
            self.assertEqual(self.ingest(json.dumps(self.report(device="device-lim1", name="Lim", account="lim@example.com"))), 200)
        finally:
            devices.MAX_DEVICES = saved

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
        devices.DEVICES.forget()
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

    def test_a_connector_report_is_stored_with_its_tools(self):
        report = self.report(device="device-conn9", name="Conn", account="", tools={"codex": {"openSessions": 1, "working": 0, "waiting": 1}, "zed": {"openSessions": 3}})
        self.assertEqual(self.ingest(json.dumps(report)), 200)
        self.addCleanup(drop_device, "device-conn9")
        stored = stored_device("device-conn9")
        self.assertEqual(stored["tools"], {"codex": {"openSessions": 1, "working": 0, "waiting": 1}})
        self.assertEqual((stored["openSessions"], stored["waiting"]), (1, 1))
        self.pages_still_work()

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
            elif field == "ledger":
                # money is also kept as a whole number of millionths of a dollar
                # tiền còn được giữ thêm dưới dạng số nguyên phần triệu đô la
                self.assertEqual(stored[field], {hour: dict(value[hour], usdMicro=1_500_000)})
            else:
                self.assertEqual(stored[field], value, field)

    def test_a_subagent_is_listed_with_its_model(self):
        # the plugin names a subagent by its type and model; markup or a name too long is still dropped
        # plugin gọi trợ lý con theo loại và mô hình; mã HTML hay tên quá dài vẫn bị bỏ
        report = self.report(device="device-sub", name="Sub", account="sub@example.com", working=1, openSessions=1,
                             subagents={"Explore (Haiku 4.5)": 1, "Sonnet 5.5": 1, "<b>x</b>": 1, " lead": 1, "x" * 41: 1})
        self.assertEqual(self.ingest(json.dumps(report)), 200)
        cookie = {"Cookie": "session=tok-sec"}
        people = json.loads(self.call("GET", "/data", None, cookie)[1])["people"]
        sub = next(p for p in people if p["account"] == "sub@example.com")
        self.assertEqual(sub["subagents"], [{"name": "Explore (Haiku 4.5)", "count": 1}, {"name": "Sonnet 5.5", "count": 1}])

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


class TelegramLogin(unittest.TestCase):
    """Log in with Telegram: only a signature made with the bot token, fresh and used once, opens a session, and only for an account
    linked after entering the 6-digit code. Admin actions still ask for the code.
    Đăng nhập bằng Telegram: chỉ chữ ký làm bằng khoá bot, còn mới và dùng một lần, mới mở được phiên, và chỉ cho tài khoản
    đã liên kết sau khi nhập mã 6 số. Thao tác quản trị vẫn hỏi mã."""

    TOKEN = "123456:TEST-token-for-the-tests"

    @classmethod
    def setUpClass(cls):
        seed()
        cls.saved = (settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_BOT_NAME)
        settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_BOT_NAME = cls.TOKEN, "aiworker_test_bot"
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_BOT_NAME = cls.saved
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        security.BOT.__init__()
        login.SESSIONS.fails, login.SESSIONS.account_fails, login.SESSIONS.used_step = {}, {}, {}
        stores.ACCOUNTS.d = {"accounts": {}}
        self.secrets = {}
        for name, role in (("an", security.ADMIN), ("binh", security.VIEWER), ("tuong", security.WALL)):
            self.secrets[name] = base64.b32decode(stores.ACCOUNTS.create(name, role, "test"))

    def signed(self, telegram_id="777", when=None, **extra):
        # a different first name each time, so two logins in the same second are not the same signature (that one is refused as reused)
        # mỗi lần một tên khác, để hai lần đăng nhập trong cùng một giây không trùng chữ ký (chữ ký trùng bị từ chối vì dùng lại)
        TelegramLogin.serial = getattr(TelegramLogin, "serial", 0) + 1
        fields = {"id": telegram_id, "first_name": "An%d" % TelegramLogin.serial, "username": "an_tg", "auth_date": str(int(when or time.time())), **extra}
        data = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields))
        fields["hash"] = hmac.new(hashlib.sha256(self.TOKEN.encode()).digest(), data.encode(), hashlib.sha256).hexdigest()
        return fields

    def code(self, name, offset=0):
        return security.totp_code(self.secrets[name], int(time.time() // 30) + offset)

    def call(self, method, path, body=None, cookie="", **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            h = {k.replace("_", "-"): v for k, v in headers.items()}
            if cookie:
                h["Cookie"] = cookie
            if body is not None:
                h["Content-Type"] = "application/x-www-form-urlencoded"
            conn.request(method, path, body, h)
            r = conn.getresponse()
            return r.status, r.read().decode("utf-8", "replace"), r.getheader("Set-Cookie") or "", r.getheader("Content-Security-Policy") or ""
        finally:
            conn.close()

    def session_of(self, name):
        token = "tok-tg-" + name
        login.SESSIONS.sessions[token] = (name, time.time() + 3600)
        self.addCleanup(login.SESSIONS.sessions.pop, token, None)
        return "session=" + token

    def link(self, name, telegram_id="777"):
        cookie = self.session_of(name)
        status, page, _, csp = self.call("POST", "/telegram/start", "code=" + self.code(name), cookie)
        self.assertEqual(status, 200, page)
        self.assertNotIn("telegram.org", csp)
        n = re.search(r"/telegram/go\?n=([A-Za-z0-9_-]+)", page).group(1)
        return self.call("GET", "/telegram/link?n=%s&%s" % (n, urllib.parse.urlencode(self.signed(telegram_id))), cookie=cookie)

    def test_signature_rules(self):
        gate, now = w.TELEGRAM, time.time()
        q = lambda d: {k: [v] for k, v in d.items()}
        self.assertEqual(gate.verify(q(self.signed("9001")), now)["id"], "9001")
        # used once only
        # chỉ dùng được một lần
        good = self.signed("9002")
        self.assertTrue(gate.verify(q(good), now))
        self.assertIsNone(gate.verify(q(good), now))
        # changed after signing, signed with another token, too old, from the future
        # bị sửa sau khi ký, ký bằng khoá khác, quá cũ, ở tương lai
        self.assertIsNone(gate.verify(q(dict(self.signed("9003"), id="9004")), now))
        other = dict(self.signed("9005"))
        other["hash"] = hmac.new(hashlib.sha256(b"another:token").digest(), b"id=9005", hashlib.sha256).hexdigest()
        self.assertIsNone(gate.verify(q(other), now))
        self.assertIsNone(gate.verify(q(self.signed("9006", when=now - 301)), now))
        self.assertIsNone(gate.verify(q(self.signed("9007", when=now + 120)), now))
        # our own n is not part of the signature; a repeated or strange parameter is refused
        # n của mình không nằm trong chữ ký; tham số lặp lại hay lạ bị từ chối
        self.assertTrue(gate.verify(dict(q(self.signed("9008")), n=["x"]), now))
        self.assertIsNone(gate.verify(dict(q(self.signed("9009")), id=["9009", "1"]), now))
        self.assertIsNone(gate.verify(dict(q(self.signed("9010")), **{"ID": ["1"]}), now))
        saved = settings.TELEGRAM_BOT_TOKEN
        settings.TELEGRAM_BOT_TOKEN = ""
        try:
            self.assertIsNone(gate.verify(q(self.signed("9011")), now))
        finally:
            settings.TELEGRAM_BOT_TOKEN = saved

    def test_only_a_linked_account_logs_in(self):
        status, page, cookie, csp = self.call("GET", "/login/telegram?" + urllib.parse.urlencode(self.signed("555")))
        self.assertEqual(status, 401)
        self.assertNotIn("session=", cookie)
        self.assertNotIn("telegram.org", csp)
        status, page, _, _ = self.link("binh", "555")
        self.assertEqual(status, 200)
        # after linking, the page leads on to the dashboard by itself
        # liên kết xong, trang tự dẫn tiếp tới bảng điều khiển
        self.assertIn('http-equiv="refresh" content="3;url=/"', page)
        self.assertEqual(stores.ACCOUNTS.telegram_of("binh"), "@an_tg")
        status, _, cookie, _ = self.call("GET", "/login/telegram?" + urllib.parse.urlencode(self.signed("555")))
        self.assertEqual(status, 303)
        token = re.search(r"session=([^;]+)", cookie).group(1)
        self.assertEqual(login.SESSIONS.user_of("session=" + token, time.time()), "binh")
        # a bad signature counts toward the IP limit
        # chữ ký sai tính vào giới hạn theo IP
        bad = dict(self.signed("555"), first_name="X")
        self.assertEqual(self.call("GET", "/login/telegram?" + urllib.parse.urlencode(bad))[0], 401)
        self.assertTrue(login.SESSIONS.fails)

    def test_a_telegram_session_still_needs_the_code_for_admin_actions(self):
        self.assertEqual(self.link("an", "888")[0], 200)
        _, _, cookie, _ = self.call("GET", "/login/telegram?" + urllib.parse.urlencode(self.signed("888")))
        token = re.search(r"session=([^;]+)", cookie).group(1)
        host = "127.0.0.1:%d" % self.port
        status, body, _, _ = self.call("POST", "/admin/accounts", json.dumps({"action": "create", "name": "moi", "role": "viewer"}), "session=" + token,
                                       Origin="http://" + host, Host=host)
        self.assertEqual(status, 403)
        self.assertTrue(json.loads(body).get("needsConfirm"))

    def test_linking_needs_the_code_and_the_one_time_step(self):
        cookie = self.session_of("binh")
        self.assertEqual(self.call("POST", "/telegram/start", "code=000000", cookie)[0], 403)
        # without the step the code opened, a signed login cannot be linked (a link sent by someone else)
        # không có bước mà mã đã mở thì không liên kết được lần đăng nhập đã ký (đường dẫn người khác gửi)
        status = self.call("GET", "/telegram/link?n=guess&" + urllib.parse.urlencode(self.signed("321")), cookie=cookie)[0]
        self.assertEqual(status, 403)
        self.assertEqual(stores.ACCOUNTS.telegram_of("binh"), "")
        # the step belongs to the session that entered the code, and works once
        # bước liên kết thuộc về phiên đã nhập mã, và chỉ dùng một lần
        status, page, _, _ = self.call("POST", "/telegram/start", "code=" + self.code("binh"), cookie)
        n = re.search(r"/telegram/go\?n=([A-Za-z0-9_-]+)", page).group(1)
        other = self.session_of("an")
        self.assertEqual(self.call("GET", "/telegram/link?n=%s&%s" % (n, urllib.parse.urlencode(self.signed("321"))), cookie=other)[0], 403)
        self.assertEqual(stores.ACCOUNTS.telegram_of("an"), "")

    def test_one_telegram_for_one_account_and_not_for_a_wall(self):
        self.assertEqual(self.link("binh", "4242")[0], 200)
        login.SESSIONS.used_step = {}
        self.assertEqual(self.link("an", "4242")[0], 409)
        self.assertEqual(stores.ACCOUNTS.telegram_of("an"), "")
        with self.assertRaises(ValueError):
            stores.ACCOUNTS.link_telegram("tuong", "5151", "")
        # a wall display cannot even start
        # màn hình treo tường không bắt đầu được
        self.assertEqual(self.call("POST", "/telegram/start", "code=" + self.code("tuong"), self.session_of("tuong"))[0], 403)

    def test_reissue_role_change_and_unlink_drop_the_link(self):
        for job, extra in (("reissue", {}), ("role", {"role": security.WALL})):
            stores.ACCOUNTS.link_telegram("binh", "6060", "b")
            result = views.manage_account({"action": job, "name": "binh", **extra}, "an", "")[1]
            if "secret" in result:
                self.secrets["binh"] = base64.b32decode(result["secret"])
            self.assertEqual(stores.ACCOUNTS.telegram_of("binh"), "", job)
            stores.ACCOUNTS.change_role("binh", security.VIEWER)
        stores.ACCOUNTS.link_telegram("binh", "6060", "")
        self.assertEqual(stores.ACCOUNTS.telegram_of("binh"), "linked")
        views.manage_account({"action": "telegram-unlink", "name": "binh"}, "an", "")
        self.assertIsNone(stores.ACCOUNTS.find_by_telegram("6060"))
        with self.assertRaises(ValueError):
            views.manage_account({"action": "telegram-unlink", "name": "binh"}, "an", "")
        # the person unlinks with their own code
        # chính người đó gỡ bằng mã của mình
        stores.ACCOUNTS.link_telegram("binh", "6060", "")
        cookie = self.session_of("binh")
        self.assertEqual(self.call("POST", "/telegram/unlink", "code=000000", cookie)[0], 403)
        self.assertEqual(self.call("POST", "/telegram/unlink", "code=" + self.code("binh"), cookie)[0], 303)
        self.assertEqual(stores.ACCOUNTS.telegram_of("binh"), "")
        # back on /telegram, so a reload does not send the form again; the notice says what to do next
        # quay về /telegram, để tải lại trang không gửi lại biểu mẫu; lời báo nói bước tiếp theo
        status, page, _, _ = self.call("GET", "/telegram?done=unlinked", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("link again below", page)

    def go(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", path, headers={"Host": "board.example.com"})
            r = conn.getresponse()
            return r.status, r.getheader("Location") or ""
        finally:
            conn.close()

    def test_the_button_goes_to_telegram_and_comes_back(self):
        status, where = self.go("/telegram/go?n=abcdefghijklmnop")
        self.assertEqual(status, 303)
        self.assertTrue(where.startswith("https://oauth.telegram.org/auth?bot_id=123456&origin=http%3A%2F%2Fboard.example.com&return_to="), where)
        self.assertTrue(where.endswith(urllib.parse.quote("http://board.example.com/telegram/back?n=abcdefghijklmnop", safe="")), where)
        # a strange step code is dropped instead of being passed on
        # mã bước lạ bị bỏ thay vì chuyển tiếp
        status, where = self.go("/telegram/go?n=%3Cx%3E")
        self.assertTrue(where.endswith(urllib.parse.quote("http://board.example.com/telegram/back", safe="")), where)
        status, page, _, _ = self.call("GET", "/telegram/back")
        self.assertEqual(status, 200)
        self.assertIn("/login.js", page)

    def test_pages_without_the_button_keep_the_strict_policy(self):
        cookie = self.session_of("an")
        _, page, _, csp = self.call("GET", "/board", cookie=cookie)
        self.assertNotIn("telegram.org", csp)
        self.assertIn('href="/telegram"', page)
        _, page, _, csp = self.call("GET", "/")
        self.assertIn('href="/telegram/go"', page)
        self.assertNotIn("<iframe", page)
        # with Telegram on, the name box does not take focus, so the browser's saved-password list does not open over the page
        # khi bật Telegram, ô tên không tự nhận con trỏ, để danh sách mật khẩu đã lưu của trình duyệt không mở đè lên trang
        self.assertNotIn("autofocus", re.search(r'<input id="account"[^>]*>', page).group(0))
        # nothing from Telegram runs on the page, so the strict policy stays
        # không có gì của Telegram chạy trên trang, nên quy tắc chặt vẫn giữ
        self.assertNotIn("telegram.org", csp)


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

    def old_database(self) -> str:
        """A board.db as the version before daily totals left it: schema version 1, with one computer in it.
        Một board.db như bản trước khi có tổng theo ngày để lại: lược đồ phiên bản 1, có sẵn một máy."""
        path = os.path.join(self.folder(), "board.db")
        d = db.Database(path, db.DATA_STEPS[:1], "NORMAL")
        with d.tx() as c:
            c.execute("INSERT INTO devices VALUES (?, ?, ?, ?, ?)", ("device-old", "a@example.com", "An", 5, "{}"))
        d.conn.close()
        return path

    def test_an_older_database_is_backed_up_then_upgraded(self):
        path = self.old_database()
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            d = db.Database(path, db.DATA_STEPS, "NORMAL")
        self.addCleanup(d.conn.close)
        backup = path + ".schema-1.bak"
        self.assertIn("backed up %s (schema version 1) to %s before upgrading to schema version %d" % (path, backup, len(db.DATA_STEPS)), log.getvalue())
        self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)
        self.assertEqual([n for n in os.listdir(os.path.dirname(path)) if "partial" in n], [])
        # the upgraded database has the new table and still has its rows
        # cơ sở dữ liệu đã nâng có bảng mới và vẫn còn các dòng cũ
        self.assertEqual(d.rows("PRAGMA user_version"), [(len(db.DATA_STEPS),)])
        self.assertEqual(d.rows("SELECT COUNT(*) FROM daily"), [(0,)])
        self.assertEqual(d.rows("SELECT device FROM devices"), [("device-old",)])
        # the copy opens, is still the old schema and holds the same rows: it is the way back
        # bản sao mở được, vẫn là lược đồ cũ và giữ đúng các dòng đó: đây là đường lui
        copy = sqlite3.connect(backup)
        self.addCleanup(copy.close)
        self.assertEqual(copy.execute("PRAGMA user_version").fetchone(), (1,))
        self.assertEqual(copy.execute("SELECT device, name FROM devices").fetchall(), [("device-old", "An")])
        self.assertEqual(copy.execute("SELECT name FROM sqlite_master WHERE name = 'daily'").fetchall(), [])

    def test_going_back_the_older_program_refuses_the_new_file_and_runs_on_the_backup(self):
        path = self.old_database()
        with contextlib.redirect_stderr(io.StringIO()):
            db.Database(path, db.DATA_STEPS, "NORMAL").conn.close()
        with self.assertRaises(SystemExit):
            db.Database(path, db.DATA_STEPS[:1], "NORMAL")
        # the steps in OPERATIONS.md: drop the -wal and -shm files, put the backup in place of board.db, start the older program
        # các bước trong OPERATIONS.md: bỏ file -wal và -shm, đặt bản sao lưu vào chỗ board.db, bật chương trình cũ
        for leftover in (path + "-wal", path + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)
        shutil.copyfile(path + ".schema-1.bak", path)
        d = db.Database(path, db.DATA_STEPS[:1], "NORMAL")
        self.addCleanup(d.conn.close)
        self.assertEqual(d.rows("SELECT device FROM devices"), [("device-old",)])

    def test_a_new_or_current_database_makes_no_backup(self):
        path = os.path.join(self.folder(), "board.db")
        db.Database(path, db.DATA_STEPS, "NORMAL").conn.close()
        db.Database(path, db.DATA_STEPS, "NORMAL").conn.close()
        self.assertEqual(glob.glob(path + ".schema-*"), [])

    def test_no_backup_means_no_upgrade(self):
        path = self.old_database()
        # something in the way of the copy: the server must stop and leave the database as it was
        # có thứ chắn chỗ của bản sao: máy chủ phải dừng và để nguyên cơ sở dữ liệu
        os.mkdir(path + ".schema-1.bak.partial")
        with self.assertRaises(SystemExit) as stopped:
            db.Database(path, db.DATA_STEPS, "NORMAL")
        self.assertIn("Cannot back up", str(stopped.exception))
        self.assertIn("Nothing was changed", str(stopped.exception))
        conn = sqlite3.connect(path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone(), (1,))
        self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE name = 'daily'").fetchall(), [])
        self.assertFalse(os.path.exists(path + ".schema-1.bak"))

    def test_a_failed_copy_keeps_the_good_backup_of_an_earlier_try(self):
        path = self.old_database()
        self.write(path + ".schema-1.bak", "the copy of an earlier try")
        original = db.Database.backup
        db.Database.backup = lambda self, target: (_ for _ in ()).throw(sqlite3.OperationalError("disk is full"))
        try:
            with self.assertRaises(SystemExit):
                db.Database(path, db.DATA_STEPS, "NORMAL")
        finally:
            db.Database.backup = original
        with open(path + ".schema-1.bak", encoding="utf-8") as f:
            self.assertEqual(f.read(), "the copy of an earlier try")
        self.assertEqual([n for n in os.listdir(os.path.dirname(path)) if "partial" in n], [])

    def test_upgrade_backups_are_deleted_after_thirty_days(self):
        path = os.path.join(self.folder(), "board.db")
        d = db.Database(path, db.DATA_STEPS, "NORMAL")
        self.addCleanup(d.conn.close)
        now = time.time()
        self.write(path + ".schema-1.bak", "old", now - 31 * 86400)
        self.write(path + ".schema-2.bak", "recent", now - 29 * 86400)
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertEqual(d.drop_old_upgrade_backups(now), [path + ".schema-1.bak"])
        self.assertIn("deleted the upgrade backup", log.getvalue())
        self.assertEqual(sorted(n for n in os.listdir(os.path.dirname(path)) if n.endswith(".bak")), ["board.db.schema-2.bak"])

    def test_audit_keeps_twelve_months(self):
        with db.data_db().tx() as c:
            c.execute("INSERT INTO audit (at, month, action, body) VALUES ('x', '2000-01', 'old', '{}')")
        stores.AUDIT_LOG.month = ""
        stores.AUDIT_LOG.write(action="check")
        self.assertEqual(db.data_db().rows("SELECT COUNT(*) FROM audit WHERE month = '2000-01'"), [(0,)])
        self.assertEqual(stores.AUDIT_LOG.read(time.strftime("%Y-%m"), 1)[0]["action"], "check")


def local_hour(day: date, hour: int = 10) -> str:
    """The hour number a computer's ledger uses, for an hour of a day on the server's clock.
    Số giờ mà sổ theo giờ của máy dùng, cho một giờ của một ngày theo đồng hồ máy chủ."""
    return str(int(datetime(day.year, day.month, day.day, hour, tzinfo=settings.LOCAL_TZ).timestamp() // 3600))


def spending(device: str, name: str, account: str, usd_by_hour: dict, tasks_by_hour: dict = None) -> dict:
    """A computer's report with a ledger of {hour: dollars}; tokens follow the dollars so the sums are easy to read.
    Báo cáo của một máy với sổ {giờ: đô la}; token đi theo số đô la để tổng dễ đọc."""
    return {"v": 1, "device": device, "name": name, "account": account, "updatedAt": 1,
            "ledger": {h: {"usd": usd, "input": int(usd * 100), "cacheRead": int(usd * 10), "cacheWrite": int(usd), "output": int(usd * 1000)} for h, usd in usd_by_hour.items()},
            "tasks": tasks_by_hour or {}}


class DailyTotals(unittest.TestCase):
    """Use per person per day: counting the hours into days, writing them again without adding twice, how long they stay, and the weeks and months read back.
    Mức dùng từng người từng ngày: cộng giờ thành ngày, ghi lại mà không cộng trùng, giữ bao lâu, và các tuần, các tháng đọc ra."""

    # a Wednesday, at 15:00 on the server's clock
    # một ngày thứ Tư, lúc 15:00 theo đồng hồ máy chủ
    TODAY = date(2026, 11, 18)
    NOW = datetime(2026, 11, 18, 15, tzinfo=settings.LOCAL_TZ).timestamp()
    AN, BINH = "an@example.com|an", "binh@example.com|binh"

    def store(self):
        d = db.Database(os.path.join(tempfile.mkdtemp(dir=TMP), "board.db"), db.DATA_STEPS, "NORMAL")
        self.addCleanup(d.conn.close)
        return daily.DailyStore(d)

    def day(self, back: int) -> date:
        return self.TODAY - timedelta(days=back)

    def rows(self, store) -> dict:
        return {(r[0], r[1]): r[2:] for r in store.db.rows("SELECT " + daily.COLUMNS + " FROM daily ORDER BY day, person")}

    def put(self, store, day: date, person: str, usd: float, branch: str = "", branch_name: str = "") -> None:
        with store.db.tx() as c:
            c.execute("INSERT INTO daily (" + daily.COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (day.isoformat(), person, person.split("|")[1].capitalize(), person.split("|")[0], branch, branch_name, usd, int(usd * 100), int(usd * 1000), 1, 2, 3))

    def test_hours_of_every_computer_of_a_person_add_up_per_day(self):
        laptop = spending("device-a1", "An", "an@example.com", {local_hour(self.TODAY, 9): 1.5, local_hour(self.TODAY, 14): 0.5, local_hour(self.day(1), 23): 2},
                          {local_hour(self.TODAY, 9): {"gemini": 2, "chatgpt": 1}})
        desktop = spending("device-a2", "An", "an@example.com", {local_hour(self.TODAY, 0): 1}, {local_hour(self.TODAY, 11): {"gemma": 4, "gemini": 1}})
        other = spending("device-b1", "Binh", "binh@example.com", {local_hour(self.day(6), 8): 3})
        totals = daily.totals_by_day([laptop, desktop, other], self.NOW)
        self.assertEqual(sorted(totals), [self.day(6).isoformat(), self.day(1).isoformat(), self.TODAY.isoformat()])
        an = totals[self.TODAY.isoformat()][self.AN]
        self.assertEqual((an["name"], an["account"]), ("An", "an@example.com"))
        self.assertEqual((an["usd"], an["tokensIn"], an["tokensOut"]), (3.0, 150 + 15 + 1 + 50 + 5 + 0 + 100 + 10 + 1, 3000))
        self.assertEqual((an["gemini"], an["chatgpt"], an["gemma"]), (3, 1, 4))
        self.assertEqual(totals[self.day(1).isoformat()][self.AN]["usd"], 2)
        self.assertEqual(totals[self.day(6).isoformat()][self.BINH]["usd"], 3)

    def test_the_day_follows_the_servers_clock_not_utc(self):
        # 23:00 and 00:00 on the server's clock are one hour apart and belong to two days
        # 23:00 và 00:00 theo đồng hồ máy chủ cách nhau một giờ và thuộc hai ngày khác nhau
        m = spending("device-a1", "An", "an@example.com", {local_hour(self.day(1), 23): 1, local_hour(self.TODAY, 0): 2})
        totals = daily.totals_by_day([m], self.NOW)
        self.assertEqual(totals[self.day(1).isoformat()][self.AN]["usd"], 1)
        self.assertEqual(totals[self.TODAY.isoformat()][self.AN]["usd"], 2)

    def test_only_days_every_computer_still_holds_in_full_are_counted(self):
        m = spending("device-a1", "An", "an@example.com", {local_hour(self.day(7)): 9, local_hour(self.day(6)): 1, local_hour(self.TODAY + timedelta(days=1)): 9, "not-an-hour": 9})
        self.assertEqual(list(daily.totals_by_day([m], self.NOW)), [self.day(6).isoformat()])
        self.assertEqual(settings.DAILY_RECOUNT_DAYS, 7)

    def test_team_days_give_one_total_per_day_and_nothing_about_who(self):
        store = self.store()
        self.put(store, self.TODAY, self.AN, 1.25)
        self.put(store, self.TODAY, self.BINH, 2.5)
        self.put(store, self.day(3), self.AN, 4)
        self.put(store, self.day(9), self.BINH, 99)
        days = store.team_days(self.NOW, 7)
        self.assertEqual([d["day"] for d in days], [self.day(back).isoformat() for back in range(6, -1, -1)])
        self.assertEqual([d["usd"] for d in days], [0, 0, 0, 4, 0, 0, 3.75])
        self.assertEqual({k for d in days for k in d}, {"day", "usd"})

    def test_recording_again_writes_over_and_never_adds_twice(self):
        store = self.store()
        m = spending("device-a1", "An", "an@example.com", {local_hour(self.TODAY): 1.25, local_hour(self.day(2)): 4})
        offices = {self.AN: ("hn", "Hanoi")}
        self.assertEqual(store.record(daily.totals_by_day([m], self.NOW), offices, self.NOW), 2)
        first = self.rows(store)
        for _ in range(3):
            self.assertEqual(store.record(daily.totals_by_day([m], self.NOW), offices, self.NOW), 0)
        self.assertEqual(self.rows(store), first)
        self.assertEqual(first[(self.TODAY.isoformat(), self.AN)], ("An", "an@example.com", "hn", "Hanoi", 1.25, 138, 1250, 0, 0, 0))
        # the hour grows on the computer: the row takes the new total, it does not add it to the old one
        # giờ đó tăng thêm trên máy: dòng nhận tổng mới, không cộng nó vào tổng cũ
        m["ledger"][local_hour(self.TODAY)]["usd"] = 2
        self.assertEqual(store.record(daily.totals_by_day([m], self.NOW + 60), offices, self.NOW + 60), 1)
        self.assertEqual(self.rows(store)[(self.TODAY.isoformat(), self.AN)][4], 2)
        self.assertEqual(len(self.rows(store)), 2)

    def test_a_day_the_computers_no_longer_hold_is_left_as_written(self):
        store = self.store()
        m = spending("device-a1", "An", "an@example.com", {local_hour(self.TODAY): 5})
        store.record(daily.totals_by_day([m], self.NOW), {}, self.NOW)
        # ten days on the computer has dropped those hours, and one computer is gone altogether
        # mười ngày sau máy đã bỏ các giờ đó, và có máy đã biến mất hẳn
        later = self.NOW + 10 * 86400
        self.assertEqual(store.record(daily.totals_by_day([dict(m, ledger={})], later), {}, later), 0)
        self.assertEqual(store.record(daily.totals_by_day([], later), {}, later), 0)
        self.assertEqual(self.rows(store)[(self.TODAY.isoformat(), self.AN)][4], 5)

    def test_a_person_whose_key_changed_is_not_counted_twice(self):
        store = self.store()
        # a computer that has not given a name yet is told apart by its address; once the name comes, the same hours belong to the named person
        # máy chưa khai tên được phân biệt bằng địa chỉ; khi có tên rồi thì chính các giờ đó thuộc về người đã có tên
        nameless = dict(spending("device-a1", "", "an@example.com", {local_hour(self.TODAY): 2}), lanIp="192.168.5.9")
        store.record(daily.totals_by_day([nameless], self.NOW), {}, self.NOW)
        self.assertEqual(list(self.rows(store)), [(self.TODAY.isoformat(), "an@example.com|192.168.5.9")])
        store.record(daily.totals_by_day([dict(nameless, name="An")], self.NOW), {}, self.NOW)
        self.assertEqual(list(self.rows(store)), [(self.TODAY.isoformat(), self.AN)])

    def test_a_finished_day_keeps_the_office_it_closed_with(self):
        store = self.store()
        m = spending("device-a1", "An", "an@example.com", {local_hour(self.day(1)): 1, local_hour(self.TODAY): 1})
        yesterday = self.NOW - 86400
        store.record(daily.totals_by_day([m], yesterday), {self.AN: ("hn", "Hanoi")}, yesterday)
        store.record(daily.totals_by_day([m], self.NOW), {self.AN: ("dn", "Da Nang")}, self.NOW)
        rows = self.rows(store)
        self.assertEqual(rows[(self.day(1).isoformat(), self.AN)][2:4], ("hn", "Hanoi"))
        self.assertEqual(rows[(self.TODAY.isoformat(), self.AN)][2:4], ("dn", "Da Nang"))
        # a finished day that had no office yet takes the one found later
        # ngày đã qua mà lúc đó chưa có văn phòng thì nhận văn phòng tìm ra sau đó
        other = self.store()
        other.record(daily.totals_by_day([m], yesterday), {}, yesterday)
        other.record(daily.totals_by_day([m], self.NOW), {self.AN: ("dn", "Da Nang")}, self.NOW)
        self.assertEqual(self.rows(other)[(self.day(1).isoformat(), self.AN)][2:4], ("dn", "Da Nang"))

    def test_rows_are_kept_thirteen_months_then_deleted(self):
        self.assertEqual(settings.DAILY_KEEP_MONTHS, 13)
        self.assertEqual(daily.keep_from(date(2026, 11, 18)), date(2025, 11, 1))
        self.assertEqual(daily.keep_from(date(2026, 1, 31)), date(2025, 1, 1))
        self.assertEqual(daily.keep_from(date(2026, 12, 1)), date(2025, 12, 1))
        store = self.store()
        self.put(store, date(2025, 10, 31), self.AN, 1)
        self.put(store, date(2025, 11, 1), self.AN, 2)
        self.put(store, date(2026, 6, 1), self.AN, 3)
        store.record({}, {}, self.NOW)
        self.assertEqual([k[0] for k in self.rows(store)], ["2025-11-01", "2026-06-01"])

    def test_weeks_start_on_monday_and_spans_before_are_cut_to_the_same_days(self):
        spans = {p: (a.isoformat(), b.isoformat()) for p, (a, b) in daily.periods(self.TODAY).items()}
        self.assertEqual(set(spans), set(daily.PERIODS))
        self.assertEqual(spans["week"], ("2026-11-16", "2026-11-18"))
        self.assertEqual(spans["weekBefore"], ("2026-11-09", "2026-11-15"))
        self.assertEqual(spans["weekBeforeSameDays"], ("2026-11-09", "2026-11-11"))
        self.assertEqual(spans["month"], ("2026-11-01", "2026-11-18"))
        self.assertEqual(spans["monthBefore"], ("2026-10-01", "2026-10-31"))
        self.assertEqual(spans["monthBeforeSameDays"], ("2026-10-01", "2026-10-18"))
        self.assertEqual(spans["monthYearAgo"], ("2025-11-01", "2025-11-30"))
        # the 31st has no same day in February; January looks back to December of the year before
        # ngày 31 không có ngày tương ứng trong tháng Hai; tháng Một nhìn về tháng Mười Hai của năm trước
        march = daily.periods(date(2027, 3, 31))
        self.assertEqual(march["monthBeforeSameDays"], (date(2027, 2, 1), date(2027, 2, 28)))
        january = daily.periods(date(2027, 1, 5))
        self.assertEqual(january["monthBefore"], (date(2026, 12, 1), date(2026, 12, 31)))
        self.assertEqual(january["monthYearAgo"], (date(2026, 1, 1), date(2026, 1, 31)))
        self.assertEqual(daily.periods(date(2026, 12, 9))["monthYearAgo"], (date(2025, 12, 1), date(2025, 12, 31)))

    def started(self, day: date):
        """A store whose totals start on the given day: the first run counts from six days before the day it runs on.
        Một kho có các tổng bắt đầu từ ngày đã cho: lần chạy đầu đếm từ sáu ngày trước ngày nó chạy."""
        store = self.store()
        first_run = day + timedelta(days=settings.DAILY_RECOUNT_DAYS - 1)
        store.record({}, {}, datetime(first_run.year, first_run.month, first_run.day, 12, tzinfo=settings.LOCAL_TZ).timestamp())
        return store

    def filled(self):
        store = self.started(date(2025, 9, 1))
        self.put(store, date(2026, 11, 18), self.AN, 4, "hn", "Hanoi")
        self.put(store, date(2026, 11, 17), self.BINH, 2, "dn", "Da Nang")
        self.put(store, date(2026, 11, 10), self.AN, 1, "hn", "Hanoi")
        self.put(store, date(2026, 11, 14), self.AN, 8, "dn", "Da Nang")
        self.put(store, date(2026, 10, 5), self.BINH, 16, "dn", "Da Nang")
        self.put(store, date(2026, 10, 25), self.BINH, 32, "", "")
        self.put(store, date(2025, 11, 20), self.AN, 64, "hn", "Old name")
        self.put(store, date(2026, 9, 30), self.AN, 128, "hn", "Hanoi")
        return store

    def test_summary_adds_up_team_offices_and_people(self):
        d = self.filled().summary(self.NOW, {"hn": "Ha Noi office"})
        usd = lambda group: {p: group[p]["usd"] for p in daily.PERIODS}
        self.assertEqual(usd(d["team"]), {"week": 6, "weekBefore": 9, "weekBeforeSameDays": 1, "month": 15, "monthBefore": 48, "monthBeforeSameDays": 16, "monthYearAgo": 64})
        self.assertEqual(d["team"]["week"], {"usd": 6, "tokensIn": 600, "tokensOut": 6000, "gemini": 2, "chatgpt": 4, "gemma": 6})
        offices = {o["id"]: o for o in d["offices"]}
        # an office goes by the name it has now; one that is gone keeps the name written on its rows
        # văn phòng mang tên hiện nay của nó; văn phòng đã bị bỏ thì giữ tên ghi trên các dòng của nó
        self.assertEqual({k: o["name"] for k, o in offices.items()}, {"hn": "Ha Noi office", "dn": "Da Nang", "": ""})
        self.assertEqual(usd(offices["hn"])["month"], 5)
        self.assertEqual(usd(offices["dn"])["month"], 10)
        self.assertEqual((usd(offices["dn"])["monthBefore"], usd(offices[""])["monthBefore"]), (16, 32))
        self.assertEqual([o["id"] for o in d["offices"]], ["dn", "hn", ""])
        people = {r["name"]: r for r in d["people"]}
        self.assertEqual([r["name"] for r in d["people"]], ["An", "Binh"])
        self.assertEqual((usd(people["An"])["month"], usd(people["An"])["weekBefore"], usd(people["Binh"])["monthBefore"]), (13, 9, 48))
        self.assertEqual((people["An"]["account"], people["An"]["office"], people["Binh"]["office"]), ("an@example.com", "hn", "dn"))
        self.assertEqual({p: v["kept"] for p, v in d["periods"].items()}, dict.fromkeys(daily.PERIODS, "all"))
        # the totals started before the oldest day still kept, so they cover from that day
        # các tổng bắt đầu trước ngày cũ nhất còn giữ, nên chúng phủ từ ngày đó
        self.assertEqual((d["today"], d["since"]), ("2026-11-18", "2025-11-01"))

    def test_summary_says_how_much_of_each_span_the_stored_days_cover(self):
        store = self.store()
        self.assertEqual(store.summary(self.NOW, {})["since"], "")
        self.assertEqual({v["kept"] for v in store.summary(self.NOW, {})["periods"].values()}, {"none"})
        # the first run is today: it counts from six days back, and that day stays the start even when nobody used anything on it
        # lần chạy đầu là hôm nay: nó đếm từ sáu ngày trước, và ngày đó vẫn là điểm bắt đầu dù hôm đó không ai dùng gì
        store.record({}, {}, self.NOW)
        store.record({}, {}, self.NOW + 30 * 86400)
        self.assertEqual(store.summary(self.NOW, {})["since"], "2026-11-12")
        kept = {p: v["kept"] for p, v in store.summary(self.NOW, {})["periods"].items()}
        self.assertEqual(kept, {"week": "all", "weekBefore": "part", "weekBeforeSameDays": "none", "month": "part", "monthBefore": "none", "monthBeforeSameDays": "none", "monthYearAgo": "none"})

    def test_charts_get_the_last_twelve_weeks_and_every_month_still_kept(self):
        spans = daily.chart_spans(self.TODAY)
        weeks = [(a.isoformat(), b.isoformat()) for a, b, _ in spans["weeks"]]
        self.assertEqual(len(weeks), settings.DAILY_CHART_WEEKS)
        self.assertEqual((weeks[0], weeks[-2], weeks[-1]), (("2026-08-31", "2026-09-06"), ("2026-11-09", "2026-11-15"), ("2026-11-16", "2026-11-18")))
        months = [(a.isoformat(), b.isoformat()) for a, b, _ in spans["months"]]
        self.assertEqual(len(months), settings.DAILY_KEEP_MONTHS)
        self.assertEqual((months[0], months[1], months[-2], months[-1]), (("2025-11-01", "2025-11-30"), ("2025-12-01", "2025-12-31"), ("2026-10-01", "2026-10-31"), ("2026-11-01", "2026-11-18")))
        # a year with a February in it, and the last day of a month, when the current month is whole
        # một năm có tháng Hai trong đó, và ngày cuối tháng, khi tháng hiện tại đã trọn
        months = daily.chart_spans(date(2027, 3, 31))["months"]
        self.assertEqual(len(months), 13)
        self.assertEqual(months[-2][:2], (date(2027, 2, 1), date(2027, 2, 28)))
        self.assertEqual(months[-1], (date(2027, 3, 1), date(2027, 3, 31), date(2027, 3, 31)))

    def test_chart_series_add_up_weeks_months_and_offices(self):
        d = self.filled().summary(self.NOW, {})
        weeks = {s["from"]: s for s in d["weeks"]}
        self.assertEqual([s["from"] for s in d["weeks"]], sorted(weeks))
        self.assertEqual((weeks["2026-11-16"]["usd"], weeks["2026-11-09"]["usd"], weeks["2026-10-05"]["usd"], weeks["2026-09-28"]["usd"]), (6, 9, 16, 128))
        self.assertEqual(round(sum(s["usd"] for s in d["weeks"]), 4), 6 + 9 + 16 + 32 + 128)
        months = {s["from"]: s for s in d["months"]}
        self.assertEqual((months["2026-11-01"]["usd"], months["2026-10-01"]["usd"], months["2026-09-01"]["usd"], months["2025-11-01"]["usd"]), (15, 48, 128, 64))
        # only a week or month that is over and fully covered counts as whole; the current ones stop at today
        # chỉ tuần hay tháng đã qua và được phủ đủ mới tính là trọn; tuần và tháng hiện tại dừng ở hôm nay
        self.assertEqual([s["whole"] for s in d["weeks"]], [True] * 11 + [False])
        self.assertEqual([s["whole"] for s in d["months"]], [True] * 12 + [False])
        self.assertEqual((d["weeks"][-1]["to"], d["months"][-1]["to"]), ("2026-11-18", "2026-11-18"))
        offices = {o["id"]: o["weeks"] for o in d["offices"]}
        self.assertEqual({len(w) for w in offices.values()}, {settings.DAILY_CHART_WEEKS})
        self.assertEqual((offices["hn"][-1], offices["dn"][-1], offices["dn"][-2], offices["hn"][-2], offices[""][-5]), (4, 2, 8, 1, 32))
        for i, span in enumerate(d["weeks"]):
            self.assertEqual(round(sum(w[i] for w in offices.values()), 4), span["usd"])

    def test_chart_series_say_what_the_stored_days_cover(self):
        store = self.store()
        store.record({}, {}, self.NOW)
        d = store.summary(self.NOW, {})
        self.assertEqual([(s["from"], s["kept"], s["whole"]) for s in d["weeks"][-3:]],
                         [("2026-11-02", "none", False), ("2026-11-09", "part", False), ("2026-11-16", "all", False)])
        self.assertEqual([s["kept"] for s in d["months"]], ["none"] * 12 + ["part"])

    def test_one_persons_rows_can_be_deleted(self):
        store = self.filled()
        self.assertEqual(store.forget(""), 0)
        self.assertEqual(store.forget("nobody@example.com"), 0)
        self.assertEqual(store.forget(" AN@example.com "), 5)
        self.assertEqual({k[1] for k in self.rows(store)}, {self.BINH})
        self.assertEqual(store.forget("binh"), 3)


class UsageByRole(unittest.TestCase):
    """Who gets the use by week and month: an admin and a viewer, on /board only; the wall role and everything that reads as it get none of it.
    Ai nhận được mức dùng theo tuần và theo tháng: quản trị và người xem, chỉ trên /board; vai treo tường và mọi thứ đọc với vai đó không nhận gì."""

    @classmethod
    def setUpClass(cls):
        seed()
        cls.original = views.DAILY
        d = db.Database(os.path.join(tempfile.mkdtemp(dir=TMP), "board.db"), db.DATA_STEPS, "NORMAL")
        views.DAILY = daily.DailyStore(d)
        views.DAILY.record({}, {}, NOW - 100 * 86400)
        today = daily.local_day(NOW)
        with d.tx() as c:
            for back, usd in ((0, 3.5), (7, 2.0), (40, 9.0)):
                c.execute("INSERT INTO daily (" + daily.COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          ((today - timedelta(days=back)).isoformat(), EMAIL + "|usage person", "Usage Person", EMAIL, "", "", usd, 1000, 200, 1, 0, 2))
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}, "viewer": {"role": security.VIEWER, "secret": ""}, "wall": {"role": security.WALL, "secret": ""}}}
        for name in ("adm", "viewer", "wall"):
            login.SESSIONS.sessions["use-" + name] = (name, NOW + 3600)
        cls.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        views.DAILY.db.conn.close()
        views.DAILY = cls.original

    def get(self, path: str, token: str) -> tuple:
        security.BOT.__init__()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        try:
            conn.request("GET", path, headers={"Cookie": "session=" + token})
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()

    def test_admin_and_viewer_get_people_and_offices(self):
        for role in (security.ADMIN, security.VIEWER):
            d = views.usage_view(role, NOW)
            self.assertEqual(set(d), views.USAGE_FIELDS_ALL, role)
            self.assertEqual([(r["name"], r["account"]) for r in d["people"]], [("Usage Person", EMAIL)], role)
            self.assertEqual(d["team"]["week"]["usd"] >= 3.5, True, role)

    def test_wall_and_unknown_roles_get_nothing(self):
        for role in (security.WALL, "role-unknown", "", None):
            self.assertEqual(views.usage_view(role, NOW), {}, role)
            self.assertEqual(pages.usage_section(role, NOW), "", role)

    def test_new_field_must_be_classified(self):
        """Add a field to the usage numbers without declaring it for each role and this test goes red.
        Thêm trường vào số liệu mức dùng mà chưa khai cho từng vai thì test này đỏ."""
        raw = views._raw_usage(NOW)
        self.assertEqual(set(raw), views.USAGE_FIELDS_DECLARED)
        self.assertEqual(set(raw["offices"][0]), views.USAGE_OFFICE_FIELDS_DECLARED)
        self.assertEqual(set(raw["people"][0]), views.USAGE_PERSON_FIELDS_DECLARED)
        self.assertEqual(set(raw["team"]), set(daily.PERIODS))
        self.assertEqual(set(raw["team"]["week"]), views.USAGE_NUMBER_FIELDS)
        self.assertEqual(set(raw["weeks"][0]), views.USAGE_SPAN_FIELDS)
        self.assertEqual(set(raw["months"][0]), views.USAGE_SPAN_FIELDS)

    def test_unknown_field_does_not_leak(self):
        original = views._raw_usage

        def with_unknown_field(now):
            d = original(now)
            d["extra"] = "secret-value"
            for group in [d["team"]] + d["offices"] + d["people"]:
                group["extra"] = "secret-value"
                group["week"]["extra"] = "secret-value"
            for span in d["weeks"] + d["months"]:
                span["extra"] = "secret-value"
            for office in d["offices"]:
                office["weeks"].append("secret-value")
            return d
        views._raw_usage = with_unknown_field
        try:
            for role in (security.ADMIN, security.VIEWER, security.WALL):
                self.assertNotIn("secret-value", json.dumps(views.usage_view(role, NOW)), role)
        finally:
            views._raw_usage = original

    def test_the_board_page_shows_it_to_admin_and_viewer_only(self):
        for token in ("use-adm", "use-viewer"):
            status, page = self.get("/board", token)
            self.assertEqual(status, 200)
            self.assertIn("<h2>Use by week and month</h2>", page)
            self.assertIn("Usage Person", page)
            for label in ("This week", "Last week", "This month", "Last month", "Tokens (month)", "Delegated (month)"):
                self.assertIn("data-label='%s'" % label, page)
        self.assertEqual(self.get("/board", "use-wall")[0], 303)
        # with no role given the page leaves the part out, as for the role that sees least
        # không truyền vai thì trang bỏ phần đó, như với vai thấy ít nhất
        self.assertNotIn("Use by week and month", pages.page_board("adm", NOW).decode())
        self.assertNotIn("Use by week and month", pages.page_board("wall", NOW, security.WALL).decode())

    def test_the_page_is_in_vietnamese_too(self):
        lang.REQUEST.lang = "vi"
        try:
            page = pages.page_board("adm", NOW, security.ADMIN).decode()
        finally:
            del lang.REQUEST.lang
        self.assertIn("<h2>%s</h2>" % lang.VI["Use by week and month"], page)
        self.assertIn("data-label='%s'" % lang.VI["Last month"], page)
        self.assertNotIn("This week", page)

    def test_no_other_path_gives_the_daily_totals(self):
        """The numbers every wall reader gets (/data: TV, menu bar, extension, plugin, and the MCP endpoint built on it) hold no daily total.
        Số liệu mà mọi nơi đọc với vai treo tường nhận (/data: TV, thanh menu, tiện ích, plugin, và cổng MCP dựng trên đó) không có tổng theo ngày nào."""
        for token in ("use-wall", "use-viewer", "use-adm"):
            status, body = self.get("/data", token)
            self.assertEqual(status, 200)
            for word in ("Usage Person", "weekBefore", "monthBefore", "monthYearAgo"):
                self.assertNotIn(word, body, token)
        for role in (security.ADMIN, security.VIEWER, security.WALL):
            self.assertEqual(set(views.role_view(role, NOW)) & {"since", "periods", "team" if role == security.WALL else "periods", "offices"}, set())

    def test_every_role_gets_the_team_total_of_the_last_seven_days_only(self):
        """The one part of the daily totals the wall role may have: one team total per day, for the chart of the menu bar window.
        Phần duy nhất của tổng theo ngày mà vai treo tường được có: một tổng của cả team mỗi ngày, cho biểu đồ của khung thanh menu."""
        for role in (security.ADMIN, security.VIEWER, security.WALL):
            days = views.role_view(role, NOW)["teamDays"]
            self.assertEqual(len(days), views.TEAM_DAYS)
            self.assertEqual({k for d in days for k in d}, {"day", "usd"})
        status, body = self.get("/data", "use-wall")
        self.assertEqual(status, 200)
        self.assertIn('"teamDays"', body)

    def span(self, start: str, usd: float, kept: str = "all", whole: bool = True) -> dict:
        end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
        return {"from": start, "to": end, "kept": kept, "whole": whole, "usd": usd}

    def test_charts_are_on_the_page_as_plain_html(self):
        page = pages.page_board("adm", NOW, security.ADMIN).decode()
        for title in ("Cost per week", "Cost per month"):
            self.assertIn('<figure class="chart" role="group" aria-label="%s">' % title, page)
        # the week of today is drawn striped and carries its amount; the page still runs no script
        # tuần của hôm nay được vẽ sọc và có ghi số tiền; trang vẫn không chạy script nào
        self.assertIn('class="col part', page)
        self.assertIn('<span class="v">$3.50</span>', page)
        self.assertIn("(so far)", page)
        self.assertNotIn("<script", page)
        self.assertNotIn("class=\"chart", pages.page_board("adm", NOW).decode())

    def test_a_chart_labels_only_the_newest_and_the_highest_column(self):
        weeks = [self.span("2026-09-07", 40), self.span("2026-09-14", 90), self.span("2026-09-21", 20), self.span("2026-09-28", 30),
                 self.span("2026-10-05", 10), self.span("2026-10-12", 60), self.span("2026-10-19", 5, whole=False)]
        chart = pages.usage_chart(weeks, "weeks", "2026-01-01")
        self.assertEqual(re.findall(r'<span class="v">([^<]*)</span>', chart), ["$90", "$5"])
        self.assertEqual(len(re.findall(r'<div class="col[ "]', chart)), 7)
        self.assertEqual(chart.count('class="col part'), 1)
        # the axis stops at a round number above the highest column, and that column's height is its share of it
        # trục dừng ở một số tròn phía trên cột cao nhất, và chiều cao của cột đó là phần của nó trên số ấy
        self.assertEqual(re.findall(r'class="gl" style="bottom:([0-9.]+)%"><span>([^<]*)</span>', chart), [("0.00", "0"), ("50.00", "$50"), ("100.00", "$100")])
        self.assertIn('aria-label="Sep 14 – Sep 20, 2026: $90.00"', chart)
        self.assertIn('<i style="height:90.00%"></i>', chart)
        self.assertIn('aria-label="Oct 19 – Oct 25, 2026: $5.00 (so far)"', chart)

    def test_a_chart_leaves_weeks_without_numbers_empty_and_keeps_six_columns(self):
        weeks = [self.span("2026-08-%02d" % d, 0, "none", False) for d in (3, 10, 17, 24, 31)] + [self.span("2026-09-%02d" % d, 0, "none", False) for d in (7, 14, 21, 28)]
        weeks += [self.span("2026-10-05", 0, "none", False), self.span("2026-10-12", 8, "part", False), self.span("2026-10-19", 12, whole=False)]
        chart = pages.usage_chart(weeks, "weeks", "2026-10-14")
        self.assertEqual(len(re.findall(r'<div class="col[ "]', chart)), 6)
        self.assertEqual(chart.count('class="col none"'), 4)
        self.assertIn('aria-label="Oct 12 – Oct 18, 2026: $8.00 (from Oct 14, 2026)"', chart)
        self.assertEqual(pages.usage_chart([self.span("2026-10-05", 0, "none", False)], "weeks", ""), "")
        # nobody spent anything yet: the chart still stands, flat, and divides by nothing
        # chưa ai tiêu gì: biểu đồ vẫn hiện, phẳng, và không chia cho số không
        self.assertIn('<i style="height:0.00%"></i>', pages.usage_chart([self.span("2026-10-19", 0, whole=False)], "weeks", "2026-01-01"))

    def test_offices_share_one_scale_and_need_a_named_office(self):
        weeks = [self.span("2026-10-12", 0), self.span("2026-10-19", 0, whole=False)]
        offices = [{"id": "hn", "name": "Hanoi", "weeks": [40.0, 10.0]}, {"id": "dn", "name": "Da Nang", "weeks": [20.0, 0.0]}, {"id": "ct", "name": "Can Tho", "weeks": [0.0, 0.0]}]
        chart = pages.office_charts(offices, weeks, "2026-01-01")
        self.assertEqual(re.findall(r'<i(?: class="part")? style="height:([0-9.]+)%"', chart), ["100.00", "25.00", "50.00", "0.00"])
        self.assertIn("this week $10.00", chart)
        self.assertNotIn("Can Tho", chart)
        self.assertEqual(pages.office_charts([{"id": "", "name": "", "weeks": [40.0, 10.0]}], weeks, "2026-01-01"), "")

    def test_short_amounts_and_round_axis_steps(self):
        self.assertEqual([pages.compact_money(n) for n in (0, 0.5, 5, 9.5, 366, 1136.88, 12400, 1500000)], ["$0", "$0.50", "$5", "$9.50", "$366", "$1.1K", "$12.4K", "$1.5M"])
        lang.REQUEST.lang = "vi"
        try:
            rate = settings.USD_RATE
            self.assertEqual([pages.compact_money(n / rate) for n in (850000, 9511320, 150000000, 2500000000)], ["850k", "9,5 tr", "150 tr", "2,5 tỷ"])  # i18n-allow
        finally:
            del lang.REQUEST.lang
        self.assertEqual([pages.axis_step(n) for n in (0, 0.9, 90, 1089, 4205, 30000000)], [1.0, 0.5, 50, 500, 2000, 10000000])

    def test_change_is_measured_against_the_same_days_before(self):
        self.assertEqual(pages.usage_change(115, 100), "▲ 15%")
        self.assertEqual(pages.usage_change(46, 50), "▼ 8%")
        self.assertEqual(pages.usage_change(100.2, 100), "=")
        self.assertEqual(pages.usage_change(5, 0), "")
        self.assertEqual(pages.usage_change(5000, 1), "▲ >999%")


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
            "/admin/tv-approve": tv, "/admin/tv-reload": tv, "/admin/tv-rename": tv, "/admin/tv-revoke": tv, "/admin/tv-view": tv, "/admin/tv-app": tv,
            "/locations": body_reads(inspect.getsource(views.edit_location)),
            "/team-csv": body_reads(branch("/team-csv")),
            "/team-sale": body_reads(branch("/team-sale")),
            "/admin/project-key": body_reads(branch("/admin/project-key")),
            "/admin/project-prices": body_reads(branch("/admin/project-prices")),
            "/admin/project-delete": body_reads(branch("/admin/project-delete")),
            "/admin/device-revoke": body_reads(action.split('elif self.path in ("/admin/device-revoke", "/admin/device-forget"):')[1].split("elif self.path")[0]),
            "/admin/device-forget": body_reads(action.split('elif self.path in ("/admin/device-revoke", "/admin/device-forget"):')[1].split("elif self.path")[0]),
            "/admin/device-roam": body_reads(action.split('elif self.path == "/admin/device-roam":')[1].split("elif self.path")[0]),
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
        # the card of a Telegram chat has fields of its own, which a screen's card does not have
        # thẻ của chat Telegram có các trường riêng, thẻ của màn hình thì không có
        chat_code = stores.TV_PAIRING.request_chat("700300400", "doi_chieu", now)[0]
        self.addCleanup(stores.TV_PAIRING.pending.pop, chat_code, None)
        chat_view = views.tv_action("/admin/tv-view", {"code": chat_code}, "thu")[1]
        block = js_block(self.admin_js, "function tvSection")
        self.assert_subset(props(block, "y"), set(view) | set(chat_view) | {"code"}, "TV request card")
        self.assert_subset(props(block, "t"), screens[0], "TV list")
        self.assert_subset(props(js_block(self.admin_js, "function telegramBotLine"), "b"), views.admin_data(time.time(), "", "")["telegramAsk"], "Telegram bot line")
        self.assert_subset(props(js_block(self.admin_js, "function mcpCallsSection"), "x"), {"at", "tv", "client", "clientIp", "ok", "action", "tool"}, "reads list")

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


class TelegramApp(unittest.TestCase):
    """The board's window inside Telegram. These tests play Telegram, which signs a few fields for the window with a key derived from
    the bot's token, and the bot process, which pairs a chat on /bot/telegram. Only a chat an admin allowed, and that reads each person,
    gets a session; every later call finds the chat again, so revoking it ends the window at once.
    Khung bảng bên trong Telegram. Các bài test này đóng vai Telegram, bên ký vài trường cho khung bằng một khoá suy ra từ khoá bot,
    và vai tiến trình bot, bên ghép chat ở /bot/telegram. Chỉ chat được quản trị cho phép, và được đọc từng người, mới nhận phiên;
    mỗi lần gọi sau đó lại tìm chat, nên thu hồi chat là khung hết dùng được ngay."""

    KEY = TelegramAsk.KEY
    TOKEN = "123456789:" + "A" * 35
    URL = "https://board.example.com/tg/app"
    HOA, LAN = TelegramAsk.HOA, "700100299"
    setUpClass = classmethod(TelegramAsk.setUpClass.__func__)
    tearDownClass = classmethod(TelegramAsk.tearDownClass.__func__)
    call, bot, say, admin, code_for, pair = TelegramAsk.call, TelegramAsk.bot, TelegramAsk.say, TelegramAsk.admin, TelegramAsk.code_for, TelegramAsk.pair

    def setUp(self):
        TelegramAsk.setUp(self)
        from board import tgapp
        self.tgapp = tgapp
        tgapp.SESSIONS.__init__()
        tgapp.MENUS.__init__()
        for limit, args in ((tgapp.SESSION_LIMIT_IP, (10, 60)), (tgapp.SESSION_LIMIT_CHAT, (20, 600)), (tgapp.DATA_LIMIT, (60, 600))):
            limit.__init__(*args)
        self.app_was = (settings.TELEGRAM_APP_ENABLED, settings.TELEGRAM_APP_KEY, settings.TELEGRAM_APP_URL)
        settings.TELEGRAM_APP_ENABLED, settings.TELEGRAM_APP_KEY, settings.TELEGRAM_APP_URL = True, tgapp.app_key_from_token(self.TOKEN), self.URL

    def tearDown(self):
        settings.TELEGRAM_APP_ENABLED, settings.TELEGRAM_APP_KEY, settings.TELEGRAM_APP_URL = self.app_was
        TelegramAsk.tearDown(self)

    def signed(self, who=None, age=0, token=None, **fields):
        """The fields Telegram hands the window, signed by Telegram's rule with the bot's token.
        Các trường Telegram giao cho khung, ký theo quy tắc của Telegram bằng khoá bot."""
        data = dict({"auth_date": str(int(time.time() - age)), "query_id": "AAH-test", "user": json.dumps({"id": int(who or self.HOA), "first_name": "Hoa", "username": "hoa_ql"})}, **fields)
        check = "\n".join("%s=%s" % (k, data[k]) for k in sorted(data))
        secret = hmac.new(b"WebAppData", (token or self.TOKEN).encode(), hashlib.sha256).digest()
        data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urllib.parse.urlencode(data)

    def session(self, init_data, **headers):
        status, b = self.call("POST", "/tg/session", json.dumps({"initData": init_data}), **headers)
        return status, json.loads(b)

    def chat_row(self, who=None):
        return next((k, v) for k, v in stores.TV.d.items() if v.get("telegramId") == (who or self.HOA))

    def allowed(self, who=None, name="Hoa on Telegram"):
        """A chat that reads each person, paired and then allowed the window by an admin. Returns its row id.
        Một chat đọc từng người, đã ghép rồi được quản trị cho mở khung. Trả id dòng của nó."""
        self.pair(who, name=name, scope="people")
        tv_id = self.chat_row(who)[0]
        self.assertEqual(self.admin("/admin/tv-app", {"id": tv_id, "on": True})[0], 200)
        return tv_id

    def open_window(self, who=None):
        status, d = self.session(self.signed(who))
        self.assertEqual(status, 200, d)
        return d["token"]

    def test_a_chat_allowed_the_window_reads_the_wall_view(self):
        self.allowed()
        token = self.open_window()
        status, b = self.call("GET", "/tg/data", Authorization="Bearer " + token)
        self.assertEqual(status, 200)
        # the same view a wall screen and the browser extension read, nothing more
        # đúng phần màn hình treo tường và tiện ích trình duyệt đọc, không hơn
        d = json.loads(b)
        self.assertEqual(set(d), set(views.role_view(security.WALL, time.time())))
        for private in ("@example.com", IP_LAN, IP_PUBLIC, "device-an"):
            self.assertNotIn(private, b.decode())

    def test_the_page_has_no_numbers_and_loads_only_its_own_files(self):
        status, b = self.call("GET", "/tg/app?lang=vi")
        self.assertEqual(status, 200)
        page = b.decode()
        self.assertIn('src="/tg/app.js?v=', page)
        self.assertIn('src="/tg/mini.js?v=', page)
        self.assertIn('href="/tg/mini.css?v=', page)
        self.assertNotIn("/static/", page)
        self.assertNotIn('href="/board"', page)
        self.assertIn(lang.VI["Disconnect this chat"], page)
        # the chat's own alerts are set in the window: the row is shown, with words that say a message comes
        # tin báo của chính chat được đặt trong khung: dòng đó hiện, với chữ nói rằng sẽ có tin nhắn
        self.assertIn('<div class="row"><label><input type="checkbox" id="notify"> <span>' + lang.VI["Message me when a wait passes"], page)
        for name in ("Hoa", "@example.com", IP_LAN):
            self.assertNotIn(name, page)
        # every file exactly as the page asks for it, with its ?v=
        # mọi file đúng như trang gọi, kèm ?v=
        files = re.findall(r'(?:src|href)="(/tg/[^"]+)"', page)
        self.assertEqual(len(files), 3, files)
        for path in files:
            self.assertEqual(self.call("GET", path)[0], 200, path)

    def test_the_paths_are_gone_unless_it_is_turned_on(self):
        self.allowed()
        token = self.open_window()
        settings.TELEGRAM_APP_ENABLED = False
        for method, path in (("GET", "/tg/app"), ("GET", "/tg/app.js"), ("GET", "/tg/mini.js"), ("GET", "/tg/data"), ("POST", "/tg/session"), ("POST", "/tg/unpair")):
            self.assertEqual(self.call(method, path, "{}" if method == "POST" else None, Authorization="Bearer " + token)[0], 404, path)

    def test_no_session_for_a_chat_that_was_not_allowed(self):
        self.assertEqual(self.session(self.signed())[0], 403)
        self.pair(scope="people")
        self.assertEqual(self.session(self.signed())[0], 403)
        self.assertEqual(self.session(self.signed(self.LAN))[0], 403)

    def test_a_chat_that_reads_totals_only_gets_totals_and_no_person(self):
        self.pair()
        tv_id = self.chat_row()[0]
        self.assertEqual(self.admin("/admin/tv-app", {"id": tv_id, "on": True})[0], 200)
        token = self.open_window()
        status, b = self.call("GET", "/tg/data", Authorization="Bearer " + token)
        self.assertEqual(status, 200)
        d = json.loads(b)
        self.assertTrue(d["totalsOnly"])
        self.assertEqual(d["people"], [])
        self.assertEqual(set(d["totals"]), {"waiting", "working", "openSessions", "usdToday", "tokens"})
        wall = views.role_view(security.WALL, time.time())
        # no name, account or device of anyone on the board reaches the chat
        # không tên, tài khoản hay máy của ai trên bảng tới được chat
        for p in wall["people"]:
            for value in (p.get("name"), p.get("account")):
                if value:
                    self.assertNotIn(value, b.decode())
        for private in ("@example.com", IP_LAN, IP_PUBLIC, "device-an"):
            self.assertNotIn(private, b.decode())

    def test_fields_not_signed_by_telegram_are_refused(self):
        self.allowed()
        good = self.signed()
        bad = [
            self.signed(token="987654321:" + "B" * 35),
            good.replace("hash=", "hash=0")[:-1],
            re.sub(r"query_id=[^&]+", "query_id=other", good),
            good.replace("hoa_ql", "lan_kt"),
            self.signed(age=self.tgapp.INIT_DATA_SECONDS + 5),
            self.signed(age=-120),
            good + "&auth_date=1",
            "",
            "x" * 5000,
        ]
        for raw in bad:
            self.assertEqual(self.session(raw)[0], 401 if len(raw) < 4500 else 413, raw[:80])
        user_less = {"auth_date": str(int(time.time())), "query_id": "q"}
        check = "\n".join("%s=%s" % (k, user_less[k]) for k in sorted(user_less))
        user_less["hash"] = hmac.new(bytes.fromhex(settings.TELEGRAM_APP_KEY), check.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(self.session(urllib.parse.urlencode(user_less))[0], 401)
        self.tgapp.SESSION_LIMIT_IP.__init__(10, 60)
        security.BOT.__init__()
        self.assertEqual(self.session(good)[0], 200)

    def test_only_old_fields_are_answered_quietly(self):
        # a phone left open for an hour is not probing; a forged signature is
        # điện thoại để mở một giờ không phải đang dò; chữ ký giả thì là đang dò
        self.allowed()
        security.BOT.__init__()
        self.assertEqual(self.session(self.signed(age=3600))[0], 401)
        self.assertEqual(security.BOT.error, {})
        self.assertEqual(self.session(self.signed(token="987654321:" + "B" * 35))[0], 401)
        self.assertNotEqual(security.BOT.error, {})

    def test_revoking_the_chat_or_taking_the_window_away_ends_the_session_at_once(self):
        tv_id = self.allowed()
        token = self.open_window()
        self.assertEqual(self.admin("/admin/tv-app", {"id": tv_id, "on": False})[0], 200)
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token)[0], 401)
        self.assertEqual(self.admin("/admin/tv-app", {"id": tv_id, "on": True})[0], 200)
        token = self.open_window()
        self.assertEqual(self.admin("/admin/tv-revoke", {"id": tv_id})[0], 200)
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token)[0], 401)
        self.assertEqual(self.session(self.signed())[0], 403)

    def test_stop_in_the_chat_ends_the_window_too(self):
        self.allowed()
        token = self.open_window()
        self.say("/stop")
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token)[0], 401)

    def test_the_window_can_disconnect_its_own_chat(self):
        tv_id = self.allowed()
        token = self.open_window()
        status, b = self.call("POST", "/tg/unpair", "", Authorization="Bearer " + token)
        self.assertEqual(status, 200)
        self.assertNotIn(tv_id, stores.TV.d)
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token)[0], 401)
        self.assertIn("not connected", self.say("hello")["text"])

    def test_nothing_else_opens_the_window_and_the_session_opens_nothing_else(self):
        self.allowed()
        token = self.open_window()
        tv_key = "tv_" + "a" * 40
        for headers in ({}, {"Cookie": "session=tok-tg-adm"}, {"Authorization": "Bearer " + tv_key}, {"Authorization": "Bearer mcp_" + "a" * 40},
                        {"Authorization": "Bearer tg_" + self.HOA}, {"Authorization": "Bearer " + self.KEY}, {"Authorization": "Bearer tgs_" + "a" * 43}):
            self.assertEqual(self.call("GET", "/tg/data", **headers)[0], 401, headers)
        for method, path in (("GET", "/data"), ("GET", "/ext/data"), ("GET", "/admin/data"), ("POST", "/mcp"), ("POST", "/bot/telegram"), ("GET", "/history")):
            status = self.call(method, path, "{}" if method == "POST" else None, Authorization="Bearer " + token)[0]
            self.assertIn(status, (303, 401, 403, 404), path)
            self.assertNotEqual(status, 200, path)
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token, Origin="https://evil.example")[0], 403)

    def test_a_chat_keeps_three_sessions_at_most(self):
        self.allowed()
        tokens = [self.open_window() for _ in range(4)]
        self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + tokens[0])[0], 401)
        for token in tokens[1:]:
            self.assertEqual(self.call("GET", "/tg/data", Authorization="Bearer " + token)[0], 200)

    def test_sessions_and_reads_are_limited(self):
        self.allowed()
        statuses = [self.session(self.signed())[0] for _ in range(12)]
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10:], [429, 429])
        self.tgapp.SESSION_LIMIT_IP.__init__(10, 60)
        token = self.open_window()
        reads = [self.call("GET", "/tg/data", Authorization="Bearer " + token)[0] for _ in range(self.tgapp.DATA_LIMIT.per_window + 1)]
        self.assertEqual(reads[-1], 429)
        self.assertEqual(set(reads[:-1]), {200})

    def test_the_bot_is_told_which_menu_buttons_to_set(self):
        self.pair(scope="people")
        status, d = self.bot({"tick": True})
        self.assertEqual((status, d["menus"]), (200, [{"to": int(self.HOA), "url": None}]))
        self.assertEqual(self.bot({"tick": True})[1]["menus"], [])
        tv_id = self.chat_row()[0]
        self.admin("/admin/tv-app", {"id": tv_id, "on": True})
        self.assertEqual(self.bot({"tick": True})[1]["menus"], [{"to": int(self.HOA), "url": self.URL}])
        self.admin("/admin/tv-revoke", {"id": tv_id})
        self.assertEqual(self.bot({"tick": True})[1]["menus"], [{"to": int(self.HOA), "url": None}])
        self.assertEqual(self.bot({"tick": True}, key="wrong" + self.KEY)[0], 401)

    def test_opening_and_refusals_are_logged_without_the_signed_fields(self):
        self.allowed()
        raw = self.signed()
        self.assertEqual(self.session(raw)[0], 200)
        self.session(self.signed(token="987654321:" + "B" * 35))
        rows = stores.AUDIT_LOG.read(datetime.now(settings.LOCAL_TZ).strftime("%Y-%m"), 50)
        actions = [r.get("action") for r in rows]
        self.assertIn("telegram-app-open", actions)
        self.assertIn("telegram-app-on", actions)
        self.assertIn("telegram-app-refused", actions)
        logged = json.dumps(rows)
        self.assertNotIn(raw.split("hash=")[1], logged)
        self.assertNotIn("AAH-test", logged)

    def test_the_key_the_installer_writes_follows_telegrams_rule(self):
        self.assertEqual(self.tgapp.app_key_from_token(self.TOKEN), hmac.new(b"WebAppData", self.TOKEN.encode(), hashlib.sha256).hexdigest())
        src = read_text("install.sh")
        self.assertIn('hmac.new(b"WebAppData", sys.stdin.read().encode(), hashlib.sha256).hexdigest()', src)
        self.assertNotIn("TELEGRAM_APP_KEY=$APP_TOKEN", src)

    def test_turned_on_only_with_a_key_an_address_and_asking_from_telegram(self):
        src = read_text("board", "settings.py")
        self.assertIn('TELEGRAM_APP_ENABLED = (TELEGRAM_ASK_ENABLED and os.environ.get("TELEGRAM_APP", "0").strip() == "1"', src)
        self.assertIn('/tg/app", TELEGRAM_APP_URL)', src)


class AlertRules(unittest.TestCase):
    """The rules of the messages a chat gets when someone waits too long, without a server: board/alerts.py on a view the test writes.
    Quy tắc của tin báo một chat nhận khi có người chờ quá lâu, không cần máy chủ: board/alerts.py trên một phần treo tường do bài test viết."""

    def setUp(self):
        from board import alerts
        self.alerts = alerts
        self.a = alerts.Alerts()
        # 10:00 in the board's time zone, outside the quiet hours
        # 10 giờ sáng theo múi giờ của bảng, ngoài giờ im lặng
        self.now = datetime.now(settings.LOCAL_TZ).replace(hour=10, minute=0, second=0, microsecond=0).timestamp()
        self.chat = {"telegramId": "700100200", "notifyMinutes": 10, "scope": "people", "notifyLang": "en", "name": "Hoa"}

    def view(self, *people):
        """people: (name, minutes waiting) or (name, minutes, state).
        people: (tên, số phút chờ) hoặc (tên, số phút, trạng thái)."""
        return {"people": [{"name": p[0], "status": p[2] if len(p) > 2 else "waiting", "waitingSince": (self.now - p[1] * 60) * 1000} for p in people]}

    def due(self, view, chat=None, at=None):
        return self.a.due([chat or self.chat], view, self.now if at is None else at)

    def test_a_wait_past_the_line_is_told_once(self):
        self.assertEqual(self.due(self.view(("An", 9))), [])
        out = self.due(self.view(("An", 12), ("Binh", 3)))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["to"], 700100200)
        lines = out[0]["text"].split("\n")
        self.assertEqual(lines[0], "⏳ AI Worker · 1 waiting longer than 10 min")
        self.assertIn("• An: 12 min", lines)
        self.assertNotIn("Binh", out[0]["text"])
        # the same wait, still going an hour later
        # cùng lần chờ đó, một giờ sau vẫn còn
        self.assertEqual(self.due(self.view(("An", 12)), at=self.now + 3600), [])

    def test_the_first_line_names_nobody(self):
        out = self.due(self.view(("An", 12), ("Binh", 20)))
        self.assertNotIn("An", out[0]["text"].split("\n")[0].replace("AI Worker", ""))
        self.assertNotIn("Binh", out[0]["text"].split("\n")[0])
        # longest first
        # lâu nhất trước
        self.assertLess(out[0]["text"].index("Binh"), out[0]["text"].index("An:"))

    def test_a_chat_that_reads_totals_is_told_how_many_never_who(self):
        out = self.due(self.view(("An", 12), ("Binh", 20)), dict(self.chat, scope="totals"))
        self.assertIn("2 waiting longer than 10 min", out[0]["text"])
        for name in ("An", "Binh"):
            self.assertNotIn(name, out[0]["text"].replace("AI Worker", ""))

    def test_one_message_every_five_minutes_and_the_rest_waits_for_the_next(self):
        self.assertEqual(len(self.due(self.view(("An", 12)))), 1)
        # Binh passes the line two minutes later: held back until five minutes after the first message
        # Binh vượt mức hai phút sau: giữ lại tới năm phút sau tin đầu
        both = self.view(("An", 12), ("Binh", 9))
        self.assertEqual(self.due(both, at=self.now + 120), [])
        later = self.due(both, at=self.now + self.alerts.GAP_SECONDS)
        self.assertEqual(len(later), 1)
        self.assertIn("Binh", later[0]["text"])
        self.assertNotIn("An:", later[0]["text"])

    def test_at_most_six_an_hour(self):
        sent = 0
        for i in range(10):
            at = self.now + i * self.alerts.GAP_SECONDS
            sent += len(self.a.due([self.chat], {"people": [{"name": "P%d" % i, "status": "waiting", "waitingSince": (at - 11 * 60) * 1000}]}, at))
        self.assertEqual(sent, self.alerts.PER_HOUR)

    def test_nothing_at_night_and_not_the_next_morning_either(self):
        night = datetime.fromtimestamp(self.now, settings.LOCAL_TZ).replace(hour=22).timestamp()
        view = {"people": [{"name": "An", "status": "waiting", "waitingSince": (night - 12 * 60) * 1000}]}
        self.assertEqual(self.a.due([self.chat], view, night), [])
        self.assertEqual(self.a.due([self.chat], view, night + 9 * 3600), [])

    def test_a_session_left_open_or_a_person_gone_is_not_told(self):
        self.assertEqual(self.due(self.view(("An", self.alerts.STALE_MINUTES + 5))), [])
        self.assertEqual(self.due(self.view(("An", 30, "offline"), ("Binh", 30, "working"))), [])

    def test_a_new_wait_of_the_same_person_is_told_again(self):
        self.assertEqual(len(self.due(self.view(("An", 12)))), 1)
        self.assertEqual(len(self.a.due([self.chat], {"people": [{"name": "An", "status": "waiting", "waitingSince": (self.now + 3600 - 11 * 60) * 1000}]}, self.now + 3600)), 1)

    def test_the_language_and_the_minutes_of_the_chat(self):
        out = self.due(self.view(("An", 16)), dict(self.chat, notifyLang="vi", notifyMinutes=15))
        self.assertTrue(out[0]["text"].startswith("⏳ AI Worker · " + lang.VI["{n} waiting longer than {m} min"].format(n=1, m=15)))


class TelegramAlerts(unittest.TestCase):
    """A chat turns alerts on with /alerts or in the window, and the bot process is told what to send on its round.
    Một chat bật tin báo bằng /alerts hoặc trong khung, và tiến trình bot được báo cần gửi gì ở vòng hỏi của nó."""

    KEY = TelegramAsk.KEY
    HOA, LAN = TelegramAsk.HOA, TelegramApp.LAN
    setUpClass = classmethod(TelegramAsk.setUpClass.__func__)
    tearDownClass = classmethod(TelegramAsk.tearDownClass.__func__)
    call, bot, say, admin, code_for, pair = TelegramAsk.call, TelegramAsk.bot, TelegramAsk.say, TelegramAsk.admin, TelegramAsk.code_for, TelegramAsk.pair
    signed, session, chat_row, allowed, open_window = TelegramApp.signed, TelegramApp.session, TelegramApp.chat_row, TelegramApp.allowed, TelegramApp.open_window
    TOKEN, URL = TelegramApp.TOKEN, TelegramApp.URL

    def setUp(self):
        TelegramApp.setUp(self)
        from board import alerts
        self.alerts_mod = alerts
        alerts.ALERTS.__init__()
        self.quiet_was = (alerts.QUIET_FROM, alerts.QUIET_TO)
        alerts.QUIET_FROM = alerts.QUIET_TO = 0
        now = time.time()
        self.wall = {"people": [{"name": "An Nguyen", "status": "waiting", "waitingSince": (now - 12 * 60) * 1000, "email": "an@example.com"}]}
        chat.role_view = lambda role, now: self.roles_asked.append(role) or self.wall

    def tearDown(self):
        self.alerts_mod.QUIET_FROM, self.alerts_mod.QUIET_TO = self.quiet_was
        TelegramApp.tearDown(self)

    def tick(self):
        status, d = self.bot({"tick": True})
        self.assertEqual(status, 200)
        return d["send"]

    def test_off_until_the_chat_turns_it_on(self):
        self.pair(scope="people")
        self.assertEqual(self.tick(), [])
        d = self.say("/alerts 10")
        self.assertIn("Alerts are on", d["text"])
        self.assertTrue(d["text"].startswith("📊 AI Worker"))
        sent = self.tick()
        self.assertEqual([s["to"] for s in sent], [int(self.HOA)])
        self.assertIn("An Nguyen: 12 min", sent[0]["text"])
        self.assertNotIn("an@example.com", sent[0]["text"])
        self.assertIsNone(sent[0]["app"])
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.roles_asked[-1], security.WALL)

    def test_off_and_how_it_stands(self):
        self.pair(scope="people")
        self.say("/alerts on")
        self.assertIn("Alerts are on", self.say("/alerts")["text"])
        self.assertIn("Alerts are off", self.say("/alerts off")["text"])
        self.assertIn("Alerts are off", self.say("/alerts")["text"])
        self.assertEqual(self.tick(), [])
        self.assertIn(lang.VI["Alerts are off. Send /alerts 10 to get them again."], self.say("/baocho " + webhook_vi.ALERT_WORDS["off"][1], lang="vi")["text"])
        self.assertIn("Send /alerts 10", self.say("/alerts 7")["text"])

    def test_a_chat_that_may_open_the_window_gets_its_button(self):
        self.allowed()
        self.say("/alerts 10")
        sent = self.tick()
        self.assertEqual(sent[0]["app"], self.URL)
        settings.TELEGRAM_APP_ENABLED = False
        self.alerts_mod.ALERTS.__init__()
        self.assertIsNone(self.tick()[0]["app"])

    def test_the_window_reads_and_sets_the_chats_alerts(self):
        self.allowed()
        token = self.open_window()
        status, b = self.call("GET", "/tg/state", Authorization="Bearer " + token)
        self.assertEqual((status, json.loads(b)), (200, {"notify": False, "notifyMinutes": 10}))
        for bad in ({"notify": "yes", "notifyMinutes": 10}, {"notify": True, "notifyMinutes": 7}, {"notify": True, "notifyMinutes": True}):
            self.assertEqual(self.call("POST", "/tg/settings", json.dumps(bad), Authorization="Bearer " + token)[0], 400, bad)
        status, _ = self.call("POST", "/tg/settings", json.dumps({"notify": True, "notifyMinutes": 5, "lang": "vi"}), Authorization="Bearer " + token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.call("GET", "/tg/state", Authorization="Bearer " + token)[1]), {"notify": True, "notifyMinutes": 5})
        sent = self.tick()
        self.assertTrue(sent[0]["text"].startswith("⏳ AI Worker · " + lang.VI["{n} waiting longer than {m} min"].format(n=1, m=5)))

    def test_only_its_own_chat_and_never_without_a_session(self):
        self.allowed()
        for headers in ({}, {"Cookie": "session=tok-tg-adm"}, {"Authorization": "Bearer tg_" + self.HOA}):
            self.assertEqual(self.call("POST", "/tg/settings", json.dumps({"notify": True, "notifyMinutes": 5}), **headers)[0], 401, headers)
            self.assertEqual(self.call("GET", "/tg/state", **headers)[0], 401, headers)

    def test_each_message_is_logged_with_how_many_and_never_who(self):
        self.pair(scope="people")
        self.say("/alerts 10")
        self.tick()
        rows = [r for r in stores.AUDIT_LOG.read(datetime.now(settings.LOCAL_TZ).strftime("%Y-%m"), 50) if r.get("action") == "telegram-alert"]
        self.assertEqual(rows[0]["people"], 1)
        self.assertNotIn("An Nguyen", json.dumps(rows))


class UnusedKeys(unittest.TestCase):
    """A key for an AI tool nobody has used for a month is pointed out on the Admin page.
    Khoá cho công cụ AI không ai dùng suốt một tháng được chỉ ra trên trang Quản trị."""

    def test_idle_days(self):
        from board.views import idle_days
        now = 1_800_000_000
        self.assertEqual(idle_days({"createdAt": now - 40 * 86400, "lastUsedAt": now - 31 * 86400 - 5}, now), 31)
        self.assertEqual(idle_days({"createdAt": now - 3 * 86400, "lastUsedAt": 0}, now), 3)
        self.assertEqual(idle_days({"createdAt": now - 90 * 86400, "lastUsedAt": now - 3600}, now), 0)
        self.assertEqual(idle_days({}, now), 0)

    def test_page_points_out_unused_keys(self):
        page = open(os.path.join(os.path.dirname(__file__), "static", "admin.js"), encoding="utf-8").read()
        self.assertIn("t.idleDays >= idleLimit", page)
        self.assertIn("snapshot.mcpIdleDays", page)


class AuditChain(unittest.TestCase):
    """Each line of the audit log carries the fingerprint of the one before, so a line changed or taken out by hand shows.
    Mỗi dòng nhật ký mang dấu vân tay của dòng trước, nên một dòng bị sửa hay bị xoá bằng tay sẽ lộ ra."""

    def setUp(self):
        from board import db as dbm, stores
        self.tmp = tempfile.mkdtemp()
        self.db = dbm.Database(os.path.join(self.tmp, "t.db"), dbm.DATA_STEPS, "NORMAL")
        self.log = stores.AuditLog(self.db)
        for i in range(5):
            self.log.write(action="test", n=i)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unbroken(self):
        r = self.log.check(0)
        self.assertEqual((r["ok"], r["rows"]), (True, 5))
        self.assertEqual(len(r["head"]), 16)
        self.assertNotIn("hash", json.dumps(self.log.read(self.log.month)[0].get("n")))

    def test_a_changed_line_breaks_the_chain(self):
        rowid, body = self.db.rows("SELECT id, body FROM audit ORDER BY id LIMIT 1 OFFSET 2")[0]
        with self.db.tx() as c:
            c.execute("UPDATE audit SET body = ? WHERE id = ?", (body.replace('"n":2', '"n":9'), rowid))
        r = self.log.check(0)
        self.assertFalse(r["ok"])
        self.assertNotEqual(r["brokenAt"], "end")

    def test_a_line_taken_out_breaks_the_chain(self):
        with self.db.tx() as c:
            c.execute("DELETE FROM audit WHERE id = (SELECT id FROM audit ORDER BY id LIMIT 1 OFFSET 2)")
        self.assertFalse(self.log.check(0)["ok"])

    def test_the_newest_lines_taken_out_show(self):
        with self.db.tx() as c:
            c.execute("DELETE FROM audit WHERE id = (SELECT MAX(id) FROM audit)")
        self.assertEqual(self.log.check(0)["brokenAt"], "end")

    def test_old_lines_dropped_by_age_do_not_break_it(self):
        with self.db.tx() as c:
            c.execute("DELETE FROM audit WHERE id IN (SELECT id FROM audit ORDER BY id LIMIT 2)")
        r = self.log.check(0)
        self.assertEqual((r["ok"], r["rows"]), (True, 3))

    def test_a_field_named_hash_cannot_forge_a_line(self):
        self.log.write(action="test", hash="0" * 64, prev="x")
        self.assertTrue(self.log.check(0)["ok"])


class BlockCounts(unittest.TestCase):
    """What ai-worker stopped on each computer reaches the Admin page as team totals of a fixed list of kinds.
    Những gì ai-worker đã chặn trên từng máy tới trang Quản trị thành số tổng của cả team theo danh sách loại cố định."""

    def test_clean_and_add_up(self):
        from board import devices
        now = 1_800_000_000
        hour = str(int(now // 3600))
        old = str(int(now // 3600) - 8 * 24)
        sent = {"v": 1, "device": "device-d1", "updatedAt": now * 1000, "blocks": {hour: {"secret": 2, "risky": 1, "what": 5, "page": "x"}, old: {"commit": 4}, "bad": {"secret": 1}}}
        clean = devices.clean_payload(sent, now)
        self.assertEqual(clean["blocks"][hour], {"secret": 2, "risky": 1})
        other = {"blocks": {hour: {"secret": 1, "commit": 1}}}
        total = devices.blocks_since([clean, other, {"blocks": "no"}], int(now // 3600) - 7 * 24 + 1)
        self.assertEqual(total, {"secret": 3, "commit": 1, "risky": 1, "page": 0, "answer": 0})

    def test_only_admin_and_viewer_see_it(self):
        from board import views
        from board.security import ADMIN, VIEWER, WALL
        self.assertIn("blocked7d", views.COMMON_FIELDS_BY_ROLE[ADMIN])
        self.assertIn("blocked7d", views.COMMON_FIELDS_BY_ROLE[VIEWER])
        self.assertNotIn("blocked7d", views.COMMON_FIELDS_BY_ROLE[WALL])



class Delegations(unittest.TestCase):
    """Each piece of work a computer hands to ChatGPT, Gemini or Gemma becomes one line of the audit log, without its text.
    Mỗi việc một máy giao cho ChatGPT, Gemini hay Gemma thành một dòng nhật ký, không có chữ của nó."""

    NOW_MS = 1_800_000_000_000

    def record(self, **fields):
        base = {"id": "a" * 24, "at": self.NOW_MS - 60_000, "tool": "ask_gemini", "via": "ai-workers", "promptChars": 42, "answerChars": 900,
                "promptHash": "b" * 32, "outcome": "ok", "check": ["command"]}
        return dict(base, **fields)

    def setUp(self):
        from board import db as dbm, stores
        self.tmp = tempfile.mkdtemp()
        self.db = dbm.Database(os.path.join(self.tmp, "t.db"), dbm.DATA_STEPS, "NORMAL")
        self.log = stores.AuditLog(self.db)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_keeps_a_fixed_list_and_drops_text(self):
        from board.devices import clean_delegations
        sent = [
            self.record(prompt="the whole prompt", answer="the whole answer", check=["command", "what"], found=["GitHub token", "ghp_x$1"]),
            self.record(id="nothex", tool="ask_gemini"),
            self.record(id="c" * 24, tool="rm_rf"),
            self.record(id="d" * 24, at=self.NOW_MS - 4 * 86_400_000),
            self.record(id="e" * 24, outcome="hacked", via="elsewhere", promptHash="short", promptChars="x"),
            "not a record",
        ]
        out = clean_delegations(sent, self.NOW_MS)
        self.assertEqual([r["id"] for r in out], ["a" * 24, "e" * 24])
        self.assertEqual(out[0], {"id": "a" * 24, "at": self.NOW_MS - 60_000, "tool": "ask_gemini", "worker": "gemini", "via": "ai-workers", "promptChars": 42,
                                  "answerChars": 900, "promptHash": "b" * 32, "outcome": "ok", "check": ["command"], "found": ["GitHub token"]})
        self.assertEqual((out[1]["outcome"], out[1]["via"], out[1]["promptHash"], out[1]["promptChars"]), ("error", "plugin", "", 0))
        self.assertNotIn("the whole", json.dumps(out))
        self.assertEqual(clean_delegations("x", self.NOW_MS), [])

    def test_each_record_is_written_once_and_kept_apart_from_the_admin_log(self):
        from board.devices import clean_delegations
        records = clean_delegations([self.record(), self.record(id="f" * 24, tool="ask_chatgpt", outcome="refused", check=[], found=["AWS access key"])], self.NOW_MS)
        self.assertEqual(self.log.write_delegations("device-1", "An", "an@example.com", records), 2)
        self.assertEqual(self.log.write_delegations("device-1", "An", "an@example.com", records), 0)
        # the same id from another computer is another piece of work
        # cùng mã từ một máy khác là một việc khác
        self.assertEqual(self.log.write_delegations("device-2", "Binh", "binh@example.com", records[:1]), 1)
        self.log.write(action="login", actor="adm")
        month = datetime.now(stores_tz()).strftime("%Y-%m")
        rows = self.log.read_delegations(month)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["outcome"], "refused")
        self.assertEqual(rows[1]["found"], ["AWS access key"])
        self.assertNotIn("check", rows[1])
        self.assertEqual((rows[2]["name"], rows[2]["device"], rows[2]["worker"]), ("An", "device-1", "gemini"))
        self.assertEqual([r["action"] for r in self.log.read(month)], ["login"])
        self.assertEqual(self.log.delegation_totals(month), {"all": 3, "chatgpt": 1, "gemini": 2, "gemma": 0, "refused": 1, "flagged": 2})
        self.assertTrue(self.log.check(0)["ok"])


def stores_tz():
    from board.settings import LOCAL_TZ
    return LOCAL_TZ


class DeviceCacheAndViews(unittest.TestCase):
    """The devices kept in memory always match the table, and the board kept for a few seconds per role never gives one role another's fields.
    Các máy giữ trong bộ nhớ luôn khớp với bảng, và bảng giữ vài giây cho mỗi vai không bao giờ đưa cho vai này các trường của vai khác."""

    DEVICES = ("device-c1", "device-c2", "device-c3")

    @classmethod
    def setUpClass(cls):
        seed()

    def tearDown(self):
        for device in self.DEVICES:
            drop_device(device)
        os.environ["VIEW_CACHE_SECONDS"] = "0"

    def report(self, device, **fields):
        hour = str(int(time.time() // 3600))
        base = {"v": 1, "device": device, "name": "Cache", "account": "cache@example.com", "updatedAt": int(time.time() * 1000), "openSessions": 1,
                "working": 1, "ledger": {hour: {"usd": 1.5, "input": 10, "output": 2}}, "tasks": {hour: {"gemini": 1}},
                "quota": {"readAt": int(time.time() * 1000), "windows": [{"kind": "five_hour", "pct": 40, "resetsAt": int((time.time() + 3600) * 1000)}]}}
        return dict(base, **fields)

    def send(self, device, **fields):
        devices.save_ingest(devices.clean_payload(self.report(device, **fields), time.time()), time.time())

    def from_table(self) -> dict:
        out = {}
        for device, body in db.data_db().rows("SELECT device, body FROM devices"):
            try:
                cleaned = devices.clean_payload(json.loads(body), time.time())
            except ValueError:
                cleaned = None
            if cleaned:
                # the hour book is in rows of its own (schema version 6), not in what the cache keeps
                # sổ giờ nằm ở các dòng riêng (lược đồ phiên bản 6), không trong thứ bộ nhớ đệm giữ
                for kind in devices.HOUR_KINDS:
                    cleaned.pop(kind, None)
                out[device] = cleaned
        return out

    def in_memory(self) -> dict:
        return {m["device"]: m for m in devices.read_all_devices()}

    def test_cleaning_twice_changes_nothing(self):
        once = devices.clean_payload(self.report("device-c1", lanIp="10.0.0.1", subagents={"Explore": 1}), time.time())
        self.assertEqual(devices.clean_payload(json.loads(json.dumps(once)), time.time() + 3600), once)

    def test_the_cache_matches_the_table_after_many_sends(self):
        rnd = random.Random(5)
        for _ in range(60):
            self.send(rnd.choice(self.DEVICES), working=rnd.randint(0, 1), waiting=rnd.randint(0, 1), lanIp="10.0.0.%d" % rnd.randint(1, 5))
        self.assertEqual(self.in_memory(), self.from_table())
        before = self.in_memory()
        devices.DEVICES.forget()
        self.assertEqual(self.in_memory(), before)

    def test_a_write_by_another_program_is_seen(self):
        self.send("device-c1")
        self.assertIn("device-c1", self.in_memory())
        other = sqlite3.connect(db.data_db().path)
        try:
            other.execute("DELETE FROM devices WHERE device = 'device-c1'")
            other.commit()
        finally:
            other.close()
        self.assertNotIn("device-c1", self.in_memory())
        self.assertEqual(self.in_memory(), self.from_table())

    def test_a_device_past_its_days_leaves_both(self):
        old = int(time.time()) - (settings.KEEP_DAYS + 1) * 86400
        devices.DEVICES.save(devices.clean_payload(self.report("device-c1"), time.time()), old)
        self.assertNotIn("device-c1", self.in_memory())
        self.assertEqual(db.data_db().rows("SELECT COUNT(*) FROM devices WHERE device = 'device-c1'"), [(0,)])

    def test_the_count_includes_a_broken_row_as_the_table_does(self):
        self.send("device-c1")
        with db.data_db().tx() as c:
            c.execute("INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?, ?)", ("device-c2", "", "", int(time.time()), "{not json"))
        devices.DEVICES.forget()
        self.assertEqual(devices.DEVICES.count(), db.data_db().rows("SELECT COUNT(*) FROM devices")[0][0])
        self.assertNotIn("device-c2", self.in_memory())

    def test_one_persons_devices(self):
        self.send("device-c1")
        self.send("device-c2")
        self.send("device-c3", name="Other")
        key = devices.person_key(self.report("device-c1"))
        self.assertEqual([m["device"] for m in devices.DEVICES.of_person(key)], ["device-c1", "device-c2"])
        # a device that moves to another person leaves the first one
        # máy chuyển sang người khác thì rời khỏi người trước
        self.send("device-c2", name="Other")
        self.assertEqual([m["device"] for m in devices.DEVICES.of_person(key)], ["device-c1"])

    def test_a_send_that_changes_state_writes_history_at_once(self):
        key = devices.person_key(self.report("device-c1"))
        self.send("device-c1", working=1, waiting=0)
        views.record_history(key)
        self.send("device-c1", working=0, waiting=1)
        views.record_history(key)
        mine = [r for r in views.HISTORY.rows if r["name"] == "Cache"]
        self.assertEqual(mine[-1]["status"], "waiting")
        # the same state sent again adds no row
        # gửi lại đúng trạng thái đó thì không thêm dòng
        count = len(views.HISTORY.rows)
        self.send("device-c1", working=0, waiting=1)
        views.record_history(key)
        self.assertEqual(len(views.HISTORY.rows), count)

    def test_many_threads_sending_and_reading(self):
        errors = []

        def work(n):
            try:
                for i in range(25):
                    self.send(self.DEVICES[(n + i) % 3], working=i % 2)
                    devices.read_all_devices()
                    devices.DEVICES.count()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.in_memory(), self.from_table())

    def test_the_board_is_built_once_per_role_within_the_window(self):
        os.environ["VIEW_CACHE_SECONDS"] = "2"
        built = []
        original = views.role_view

        def counting(role, now, every_branch=False):
            built.append(role)
            return original(role, now, every_branch)

        views.role_view = counting
        try:
            t = time.time() + 1000
            views.VIEWS.json(security.WALL, t)
            views.VIEWS.json(security.WALL, t + 1)
            views.VIEWS.json("someone-unknown", t + 1)
            self.assertEqual(built, [security.WALL])
            views.VIEWS.json(security.ADMIN, t + 1)
            views.VIEWS.json(security.WALL, t + 2.5)
            self.assertEqual(built, [security.WALL, security.ADMIN, security.WALL])
            os.environ["VIEW_CACHE_SECONDS"] = "0"
            views.VIEWS.json(security.WALL, t + 2.6)
            views.VIEWS.json(security.WALL, t + 2.6)
            self.assertEqual(len(built), 5)
        finally:
            views.role_view = original

    def test_a_role_never_gets_another_roles_board(self):
        os.environ["VIEW_CACHE_SECONDS"] = "60"
        t = time.time() + 2000
        admin = views.VIEWS.json(security.ADMIN, t)
        self.assertIn(EMAIL.encode(), admin)
        for role in (security.WALL, "someone-unknown"):
            wall = views.VIEWS.json(role, t)
            self.assertNotIn(EMAIL.encode(), wall)
            self.assertEqual(json.loads(wall)["role"], security.WALL)
        viewer = json.loads(views.VIEWS.json(security.VIEWER, t))
        self.assertEqual(viewer["role"], security.VIEWER)
        # a copy given out may get a key of its own without touching what the next request gets
        # bản sao đưa ra được thêm khoá riêng mà không đụng tới thứ yêu cầu sau nhận
        views.VIEWS.view(security.WALL, t)["reload"] = True
        self.assertNotIn("reload", views.VIEWS.view(security.WALL, t))

    def test_with_the_receiver_one_build_serves_every_role_and_the_old_view_is_given_while_the_next_is_built(self):
        os.environ["VIEW_CACHE_SECONDS"] = ""
        built, real = [], views._raw_data

        def counting(now):
            built.append(now)
            return real(now)
        views._raw_data = counting
        was = settings.RECEIVER_ENABLED
        settings.RECEIVER_ENABLED = True
        try:
            cache = views.ViewCache()
            self.assertEqual(cache.seconds(), 5)
            t = time.time()
            first = {role: cache.json(role, t) for role in (security.ADMIN, security.VIEWER, security.WALL)}
            self.assertEqual(len(built), 1)
            self.assertIn(EMAIL.encode(), first[security.ADMIN])
            self.assertNotIn(EMAIL.encode(), first[security.WALL])
            self.assertEqual(cache.json(security.WALL, t + 4), first[security.WALL])
            self.assertEqual(len(built), 1)
            # past its time: the same bytes at once, and a thread builds the next view, with the JSON of every role asked before
            # quá hạn: trả ngay đúng chuỗi byte cũ, và một luồng dựng khung nhìn kế, kèm JSON của mọi vai đã được hỏi
            self.assertIs(cache.json(security.WALL, t + 6), first[security.WALL])
            for _ in range(200):
                if not cache.building:
                    break
                time.sleep(0.05)
            self.assertFalse(cache.building)
            self.assertEqual(len(built), 2)
            self.assertTrue(all(cache.kept["entries"][(role, False)]["json"] is not None for role in first))
            later = cache.json(security.WALL, cache.kept["at"])
            self.assertIsNot(later, first[security.WALL])
            self.assertEqual(json.loads(later)["role"], security.WALL)
            self.assertEqual(len(built), 2)
            # after a quiet while the old view is not given: the request builds a new one at once, as the first one did
            # sau một lúc yên ắng không trả khung nhìn cũ: yêu cầu dựng bản mới ngay, như yêu cầu đầu tiên
            quiet = cache.kept["at"] + 60
            fresh = cache.json(security.WALL, quiet)
            self.assertEqual(len(built), 3)
            self.assertEqual(built[-1], quiet)
            self.assertEqual(cache.kept["at"], quiet)
            self.assertFalse(cache.building)
            self.assertEqual(json.loads(fresh)["updatedAt"], int(quiet * 1000))
        finally:
            views._raw_data = real
            settings.RECEIVER_ENABLED = was

    def test_the_admin_page_says_when_the_receiver_is_behind(self):
        from board import receiver
        was = settings.RECEIVER_ENABLED
        settings.RECEIVER_ENABLED = True
        try:
            receiver.POLICY.waited = None
            now = time.time()
            self.assertIsNone(receiver.lag(now))
            batch = {"src": "go-lag", "boot": "b-%f" % now, "seq": 1, "rows": [], "waitMs": 4000}
            receiver.apply_rows(batch, now)
            self.assertEqual(receiver.lag(now), {"waitSeconds": 4, "behind": False})
            receiver.apply_rows(dict(batch, seq=2, waitMs=75_500), now)
            self.assertEqual(views.admin_data(now, "", "")["receiver"], {"waitSeconds": 75, "behind": True})
            # an old batch says nothing about now; a value that is not a whole number of milliseconds is left out
            # lô cũ không nói gì về lúc này; giá trị không phải số nguyên mili giây thì bỏ qua
            self.assertIsNone(receiver.lag(now + receiver.WAITED_KEEP_SECONDS + 1))
            receiver.apply_rows(dict(batch, seq=3, waitMs="lots"), now + 1)
            self.assertEqual(receiver.lag(now + 1)["waitSeconds"], 75)
            settings.RECEIVER_ENABLED = False
            self.assertIsNone(views.admin_data(now, "", "")["receiver"])
        finally:
            settings.RECEIVER_ENABLED = was
            receiver.POLICY.waited = None

    def test_the_people_split_by_branch_give_each_scope_as_the_filter_does(self):
        for device, name in zip(self.DEVICES, ("b Second", "A First", "c Third")):
            self.send(device, name=name, account=name.split()[1].lower() + "@example.com")
        d = views.role_view(security.ADMIN, time.time())
        index = views.by_branch(d["people"])
        for scope in ["org", "branch:"] + ["branch:" + b for b in index]:
            for page in (0, 1, 7):
                self.assertEqual(json.dumps(views.scoped_view(dict(d), scope, page, index)), json.dumps(views.scoped_view(dict(d), scope, page)), scope)


class BusyServer(unittest.TestCase):
    """A busy server answers sends and people who are not logged in with 503 at once, and still answers people looking at the board.
    Máy chủ đang bận trả ngay 503 cho lần gửi và người chưa đăng nhập, và vẫn trả lời những người đang xem bảng."""

    @classmethod
    def setUpClass(cls):
        seed()
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}}}
        login.SESSIONS.sessions["tok-busy"] = ("adm", NOW + 3600)
        cls.server = w.LimitedServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        security.BOT.__init__()
        self.saved = w.LOAD.limit
        # with a limit of 1, any other request being answered makes the server busy
        # với giới hạn 1, chỉ cần một yêu cầu khác đang được trả lời là máy chủ đã bận
        w.LOAD.limit = 1

    def tearDown(self):
        w.LOAD.limit = self.saved

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body, headers or {})
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()

    def while_busy(self, *call):
        # one request held open the whole time stands for the crowd
        # một yêu cầu được giữ suốt thời gian đó đứng thay cho đám đông
        with w.LOAD.request():
            return self.call(*call)

    def test_a_send_gets_503_with_retry_after(self):
        body = json.dumps({"v": 1, "device": "device-busy", "name": "Busy", "updatedAt": int(time.time() * 1000)})
        status, headers, _ = self.while_busy("POST", "/ingest", body, {"Authorization": "Bearer test", "Content-Type": "application/json"})
        self.assertEqual(status, 503)
        self.assertEqual(headers.get("Retry-After"), str(settings.BUSY_RETRY_SECONDS))
        self.assertIsNone(devices.read_device("device-busy"))

    def test_a_large_body_is_not_read_when_busy(self):
        # a body past BUSY_READ_BYTES is never sent in full: the server answers from the headers and closes
        # thân quá BUSY_READ_BYTES không bao giờ được gửi hết: máy chủ trả lời từ phần header rồi đóng
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            with w.LOAD.request():
                conn.sendall(b"POST /ingest HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test\r\nContent-Type: application/json\r\n"
                             b"Content-Length: %d\r\n\r\n" % (settings.BUSY_READ_BYTES * 8))
                answer = conn.recv(200)
        finally:
            conn.close()
        self.assertTrue(answer.startswith(b"HTTP/1.0 503") or answer.startswith(b"HTTP/1.1 503"), answer)

    def test_someone_not_logged_in_gets_503(self):
        self.assertEqual(self.while_busy("GET", "/data")[0], 503)
        self.assertEqual(self.while_busy("POST", "/login", "account=x&code=1", {"Content-Type": "application/x-www-form-urlencoded"})[0], 503)

    def test_people_logged_in_and_health_still_get_through(self):
        self.assertEqual(self.while_busy("GET", "/data", None, {"Cookie": "session=tok-busy"})[0], 200)
        self.assertEqual(self.while_busy("GET", "/health")[0], 200)

    def test_not_busy_answers_as_usual(self):
        self.assertEqual(self.call("GET", "/data")[0], 401)
        self.assertEqual(w.LOAD.active, 0)

    def test_the_log_says_it_once_a_minute(self):
        load = w.Load(1)
        written = io.StringIO()
        with contextlib.redirect_stderr(written):
            for t in (100.0, 101.0, 150.0, 161.0):
                load.note_shed(t)
        self.assertEqual(written.getvalue().count("busy:"), 2)
        self.assertIn(" 3 sends", written.getvalue())


class HoursAddedUpOnce(unittest.TestCase):
    """The hourly numbers added up once per send give the same board and the same daily totals as going through every hour each time.
    Số liệu theo giờ cộng một lần cho mỗi lần gửi cho ra cùng bảng và cùng tổng theo ngày như cách đi qua từng giờ mỗi lần."""

    def tearDown(self):
        for i in range(6):
            drop_device("device-hours%d" % i)

    def computers(self, now):
        rnd = random.Random(9)
        hour = int(now // 3600)
        out = []
        for i in range(6):
            ledger, tasks = {}, {}
            # 9 days back and up to a day ahead, as a computer with a wrong clock may send
            # lùi 9 ngày và tới một ngày sau, như máy lệch đồng hồ có thể gửi
            for back in range(-24, 9 * 24, rnd.choice((1, 2, 3))):
                usd = round(rnd.uniform(0, 3), 2)
                ledger[str(hour - back)] = {"usd": usd, "input": rnd.randint(0, 9000), "output": rnd.randint(0, 900), "cacheRead": rnd.randint(0, 50000), "cacheWrite": rnd.randint(0, 900)}
                if rnd.random() < 0.4:
                    tasks[str(hour - back)] = {"gemini": rnd.randint(0, 3), "chatgpt": rnd.randint(0, 2), "gemma": rnd.randint(0, 4)}
            # two people, three computers each, so rows add up several computers
            # hai người, mỗi người ba máy, để mỗi dòng cộng nhiều máy
            out.append({"v": 1, "device": "device-hours%d" % i, "name": "Hours%d" % (i % 2), "account": "hours@example.com", "updatedAt": int(now * 1000),
                        "openSessions": 1, "ledger": ledger, "tasks": tasks})
        return out

    @staticmethod
    def by_hand(devices_list, now):
        """Every hour, every time: the way the board added them up before.
        Từng giờ, mỗi lần: cách bảng đã cộng trước đây."""
        today = datetime.fromtimestamp(now, settings.LOCAL_TZ).date()
        people = {}
        for m in devices_list:
            r = people.setdefault(devices.person_key(m), {"usdToday": 0.0, "usd7d": 0.0, "tokensIn": 0, "tokensOut": 0, "tasks": [0, 0, 0], "costByHour": {}, "tasksByHour": {}})
            for hour, v in m["ledger"].items():
                day = datetime.fromtimestamp(int(hour) * 3600, settings.LOCAL_TZ).date()
                if day >= today - timedelta(days=6):
                    r["usd7d"] += v["usd"]
                if int(hour) * 3600 > now - 86400:
                    r["costByHour"][int(hour)] = r["costByHour"].get(int(hour), 0.0) + v["usd"]
                if day == today:
                    r["usdToday"] += v["usd"]
                    r["tokensIn"] += v["input"] + v["cacheRead"] + v["cacheWrite"]
                    r["tokensOut"] += v["output"]
            for hour, v in m["tasks"].items():
                if int(hour) * 3600 > now - 86400:
                    counts = r["tasksByHour"].setdefault(int(hour), [0, 0, 0])
                    for i, worker in enumerate(("gemini", "chatgpt", "gemma")):
                        counts[i] += v[worker]
                if datetime.fromtimestamp(int(hour) * 3600, settings.LOCAL_TZ).date() == today:
                    for i, worker in enumerate(("gemini", "chatgpt", "gemma")):
                        r["tasks"][i] += v[worker]
        return people

    def same(self, rows, expected):
        self.assertEqual({r["key"] for r in rows}, set(expected))
        for r in rows:
            e = expected[r["key"]]
            for field in ("usdToday", "usd7d"):
                self.assertAlmostEqual(r[field], e[field], places=9)
            self.assertEqual((r["tokensIn"], r["tokensOut"], r["tasks"], r["tasksByHour"]), (e["tokensIn"], e["tokensOut"], e["tasks"], e["tasksByHour"]))
            self.assertEqual(set(r["costByHour"]), set(e["costByHour"]))
            for hour, usd in e["costByHour"].items():
                self.assertAlmostEqual(r["costByHour"][hour], usd, places=9)

    def test_the_board_adds_up_as_before(self):
        now = time.time()
        raw = self.computers(now)
        expected = self.by_hand(raw, now)
        # dicts the cache does not hold, and the cleaned ones it does
        # các dict bộ nhớ đệm không giữ, và các dict đã làm sạch mà nó giữ
        self.same(devices.group_by_person(raw, now), expected)
        for m in raw:
            devices.save_device(m)
        kept = [m for m in devices.read_all_devices() if m["device"].startswith("device-hours")]
        self.assertTrue(all(devices.DEVICES.holds(m) for m in kept))
        self.same(devices.group_by_person(kept, now), expected)
        # the same summary is right an hour and a day later, since it does not depend on the time it was made
        # cùng bản cộng vẫn đúng sau một giờ và một ngày, vì nó không phụ thuộc lúc được làm
        for later in (now + 3600, now + 86400):
            self.same(devices.group_by_person(kept, later), self.by_hand(raw, later))

    def test_the_daily_totals_add_up_as_before(self):
        now = time.time()
        raw = self.computers(now)
        today = datetime.fromtimestamp(now, settings.LOCAL_TZ).date()
        first = today - timedelta(days=settings.DAILY_RECOUNT_DAYS - 1)
        expected = {}
        for m in raw:
            for field in ("ledger", "tasks"):
                for hour, v in m[field].items():
                    day = datetime.fromtimestamp(int(hour) * 3600, settings.LOCAL_TZ).date()
                    if not first <= day <= today:
                        continue
                    r = expected.setdefault(day.isoformat(), {}).setdefault(devices.person_key(m), dict.fromkeys(daily.NUMBERS, 0))
                    if field == "ledger":
                        r["usd"] += v["usd"]
                        r["tokensIn"] += v["input"] + v["cacheRead"] + v["cacheWrite"]
                        r["tokensOut"] += v["output"]
                    else:
                        for worker in daily.WORKERS:
                            r[worker] += v[worker]
        got = daily.totals_by_day(raw, now)
        self.assertEqual({d: set(p) for d, p in got.items()}, {d: set(p) for d, p in expected.items()})
        for day, people in expected.items():
            for key, numbers in people.items():
                for number, value in numbers.items():
                    self.assertAlmostEqual(got[day][key][number], value, places=9)

    def test_a_day_by_arithmetic_is_the_day_of_the_clock(self):
        for hour in (0, 1, 23, 24, 470000, 491234, 500017):
            self.assertEqual(devices.local_day_of_hour(hour), datetime.fromtimestamp(hour * 3600, settings.LOCAL_TZ).date())


class PersonRowsKept(unittest.TestCase):
    """A person's row kept between builds of the board is always the row a fresh count would give.
    Dòng của một người được giữ giữa các lần dựng bảng luôn đúng là dòng mà một lần đếm mới sẽ cho."""

    def tearDown(self):
        for device in ("device-kept1", "device-kept2", "device-kepttool"):
            drop_device(device)

    def fresh(self, now):
        # whole records read from the tables are not held by the cache, so they are always counted afresh, hour by hour
        # bản ghi đầy đủ đọc từ các bảng không nằm trong bộ nhớ đệm, nên luôn được đếm lại từ đầu, từng giờ một
        return devices.group_by_person([devices.read_device(m["device"]) for m in self.kept()], now)

    def kept(self):
        return [m for m in devices.read_all_devices() if m["device"].startswith("device-kept")]

    def check(self, now):
        self.assertEqual(devices.group_by_person(self.kept(), now), self.fresh(now))

    def test_kept_rows_match_a_fresh_count_over_time(self):
        now = time.time()
        hour = str(int(now // 3600))
        quota = {"readAt": int(now * 1000), "windows": [{"kind": "five_hour", "pct": 60, "resetsAt": int((now + 1800) * 1000)}]}
        devices.save_device({"v": 1, "device": "device-kept1", "name": "Kept", "account": "kept@example.com", "updatedAt": int(now * 1000), "openSessions": 1,
                             "working": 1, "ledger": {hour: {"usd": 2.0, "input": 5, "output": 1}}, "quota": quota})
        devices.save_device({"v": 1, "device": "device-kept2", "name": "Kept", "account": "kept@example.com", "updatedAt": int((now - 600) * 1000), "openSessions": 1})
        devices.save_device({"v": 1, "device": "device-kepttool", "name": "Kept", "account": "kept@example.com", "updatedAt": int(now * 1000),
                             "tools": {"codex": {"openSessions": 1, "working": 1, "waiting": 0}}})
        # past each moment that changes the row: a computer going quiet, the quota resetting, the connector's work going stale,
        # the next hour, the next day, a computer going quiet for good
        # qua từng thời điểm làm dòng đổi: một máy im, hạn mức làm mới, việc của bộ nối hết mới, giờ kế tiếp, ngày kế tiếp, máy im hẳn
        for later in (0, 1, 200, 1799, 1801, 1900, 3700, 7300, 86400 + 60):
            self.check(now + later)
        # a send replaces the device, so the next build counts that person again
        # lần gửi thay máy, nên lần dựng sau đếm lại người đó
        before = devices.group_by_person(self.kept(), now + 5)[0]["working"]
        devices.save_device({"v": 1, "device": "device-kept1", "name": "Kept", "account": "kept@example.com", "updatedAt": int((now + 6) * 1000), "openSessions": 1, "waiting": 1})
        after = devices.group_by_person(self.kept(), now + 7)[0]
        self.assertNotEqual((before, 0), (after["working"], after["waiting"]))
        self.check(now + 7)

    def test_a_row_given_out_can_be_written_without_touching_the_kept_one(self):
        now = time.time()
        devices.save_device({"v": 1, "device": "device-kept1", "name": "Kept", "account": "kept@example.com", "updatedAt": int(now * 1000), "openSessions": 1})
        devices.group_by_person(self.kept(), now)[0]["shared"] = "changed"
        self.assertIsNot(devices.group_by_person(self.kept(), now)[0]["shared"], "changed")


class SendsPerComputer(unittest.TestCase):
    """Sends are limited per computer, not per address: a whole office behind one address keeps sending, one computer that loops does not.
    Lần gửi bị giới hạn theo máy, không theo địa chỉ: cả văn phòng chung một địa chỉ vẫn gửi được, một máy chạy vòng lặp thì không."""

    def setUp(self):
        self.gate = devices.IngestGate(db.data_db())

    def send(self, device, at, ip="203.0.113.7"):
        return self.gate.check({"device": device, "account": device + "@example.com", "name": device}, ip, at, 0)

    def test_one_computer_that_loops_is_stopped_and_comes_back(self):
        at = 1_000_000.0
        answers = [self.send("device-loop", at) for _ in range(settings.INGEST_BURST + 1)]
        self.assertEqual(answers[:-1], [None] * settings.INGEST_BURST)
        self.assertEqual(answers[-1], (429, "too many submissions"))
        # a few seconds later its bucket has refilled a little
        # vài giây sau xô của nó đã đầy lại một ít
        self.assertIsNone(self.send("device-loop", at + 3 / settings.INGEST_PER_SECOND))

    def test_many_computers_behind_one_address_all_send(self):
        at = 2_000_000.0
        names = ["device-office%03d" % i for i in range(200)]
        # the computers were known before; only new ones are limited per address
        # các máy đã được biết từ trước; chỉ máy mới bị giới hạn theo địa chỉ
        for name in names:
            self.gate.identities[name] = [name + "@example.com", name]
        # every computer sends every 2 seconds for 10 minutes, all from the same address
        # mỗi máy gửi 2 giây một lần trong 10 phút, tất cả từ cùng một địa chỉ
        refused = sum(1 for step in range(300) for name in names if self.send(name, at + 2 * step) is not None)
        self.assertEqual(refused, 0)

    def test_new_computers_from_one_address_are_still_limited(self):
        at = 3_000_000.0
        answers = [self.send("device-new%02d" % i, at + i) for i in range(settings.NEW_DEVICES_PER_IP + 1)]
        self.assertEqual(answers[-1], (429, "too many new devices from one address"))
        for i in range(settings.NEW_DEVICES_PER_IP):
            self.gate.identities.pop("device-new%02d" % i, None)
            with db.data_db().tx() as c:
                c.execute("DELETE FROM identities WHERE device = ?", ("device-new%02d" % i,))


class DeviceKeys(unittest.TestCase):
    """Each computer gets a key of its own at its first send; from then on only that key sends for it, and an admin can cut it off.
    Mỗi máy nhận khoá riêng ở lần gửi đầu; từ đó chỉ khoá đó được gửi cho máy, và quản trị cắt được máy đó."""

    SHARED = "s" * 40

    @classmethod
    def setUpClass(cls):
        cls.saved_key = settings.INGEST_KEY
        settings.INGEST_KEY = cls.SHARED
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
        views.INGEST_GATE.buckets, views.INGEST_GATE.new_devices = {}, {}
        self.saved_mode = settings.SHARED_KEY_MODE
        self.saved_nets = settings.OFFICE_NETS
        self.devices = []

    def tearDown(self):
        settings.SHARED_KEY_MODE = self.saved_mode
        settings.OFFICE_NETS = self.saved_nets
        for device in self.devices:
            devicekeys.DEVICE_KEYS.forget(device)
            drop_device(device)
            views.INGEST_GATE.identities.pop(device, None)
            with db.data_db().tx() as c:
                c.execute("DELETE FROM identities WHERE device = ?", (device,))

    def send(self, device, key, ip=None, headers=None, **fields):
        if device not in self.devices:
            self.devices.append(device)
        body = json.dumps(dict({"v": 1, "device": device, "name": "Key " + device[-2:], "account": device + "@example.com", "updatedAt": int(time.time() * 1000)}, **fields))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        # ip: the address Caddy saw, put last in X-Forwarded-For as Caddy does
        # ip: địa chỉ Caddy đã thấy, đặt cuối X-Forwarded-For như Caddy làm
        extra = dict({"X-Forwarded-For": "198.51.100.9, " + ip} if ip else {}, **(headers or {}))
        try:
            conn.request("POST", "/ingest", body, dict({"Authorization": "Bearer " + key, "Content-Type": "application/json"}, **extra))
            r = conn.getresponse()
            return r.status, json.loads(r.read() or b"{}")
        finally:
            conn.close()

    def enrol(self, device):
        status, answer = self.send(device, self.SHARED, ip=self.OFFICE)
        self.assertEqual(status, 200)
        return answer["deviceKey"]

    def test_the_first_send_gets_a_key_and_then_only_that_key_sends(self):
        key = self.enrol("device-k01")
        parts = key.split(".")
        self.assertEqual((len(parts), parts[0], parts[5]), (8, "awd1", "device-k01"))
        # the key carries no email, name or address
        # khoá không mang email, tên hay địa chỉ
        self.assertNotIn("example.com", key)
        status, again = self.send("device-k01", key)
        self.assertEqual((status, again["ok"], "deviceKey" in again), (200, True, False))
        self.assertEqual(self.send("device-k01", self.SHARED), (401, {"error": "use this computer's own key"}))
        # only the time of the newest key is stored, never the key
        # chỉ lưu lúc cấp khoá mới nhất, không bao giờ lưu khoá
        rows = db.data_db().rows("SELECT * FROM device_keys WHERE device = 'device-k01'")
        self.assertEqual(len(rows[0]), 3)
        self.assertNotIn(key, json.dumps(rows))

    def test_a_plugin_that_throws_the_key_away_keeps_sending(self):
        """A plugin older than 0.50.0 does not read deviceKey: the key it was given binds nothing until a send uses it, so the computer is
        not shut out when the server is upgraded first (it was, in 0.50.0). Once a send uses the key, the shared key no longer sends for it.
        Plugin cũ hơn 0.50.0 không đọc deviceKey: khoá được cấp chưa ràng buộc gì cho tới khi một lần gửi dùng nó, nên máy không bị khoá
        ngoài khi máy chủ được nâng trước (0.50.0 thì bị). Một khi đã gửi bằng khoá đó, khoá chung không gửi thay máy được nữa."""
        first = self.enrol("device-k13")
        status, answer = self.send("device-k13", self.SHARED)
        self.assertEqual((status, answer["ok"]), (200, True))
        self.assertEqual(devicekeys.DEVICE_KEYS.state("device-k13", time.time()), "none")
        # the plugin is updated and keeps the key it gets next: both keys check, and the first one used binds the computer
        # plugin được nâng và giữ khoá nhận được lần sau: cả hai khoá đều kiểm được, và lần đầu dùng khoá thì máy bị ràng buộc
        self.assertEqual(self.send("device-k13", answer["deviceKey"])[0], 200)
        self.assertEqual(self.send("device-k13", first)[0], 200)
        self.assertEqual(self.send("device-k13", self.SHARED), (401, {"error": "use this computer's own key"}))
        self.assertEqual([c["state"] for c in devicekeys.DEVICE_KEYS.listing(time.time()) if c["device"] == "device-k13"], ["active"])

    def test_a_computer_given_a_key_it_never_used_can_still_be_revoked(self):
        self.enrol("device-k14")
        self.assertTrue(devicekeys.DEVICE_KEYS.revoke("device-k14", time.time()))
        self.assertEqual(self.send("device-k14", self.SHARED), (403, {"error": "device revoked"}))
        listed = [c for c in devicekeys.DEVICE_KEYS.listing(time.time()) if c["device"] == "device-k14"]
        self.assertEqual((listed[0]["state"], listed[0]["issuedAt"]), ("revoked", None))
        # a computer this server never enrolled is not written down
        # máy máy chủ chưa từng ghi danh thì không được ghi lại
        self.assertFalse(devicekeys.DEVICE_KEYS.revoke("device-k99", time.time()))

    def test_the_rows_written_by_0_50_0_are_dropped_once(self):
        keys = devicekeys.DEVICE_KEYS
        self.devices += ["device-k15", "device-k16"]
        with db.data_db().tx() as c:
            c.execute("INSERT INTO device_keys (device, iat, revoked_at) VALUES ('device-k15', ?, 0), ('device-k16', ?, ?)",
                      (int(time.time()), int(time.time()), int(time.time())))
        with db.keys_db().tx() as c:
            c.execute("DELETE FROM meta WHERE key = ?", (devicekeys.USED_ONLY_KEY,))
        keys.loaded_for = keys.rows_for = None
        # the computer given a key in 0.50.0 may enrol again; the one an admin revoked stays revoked
        # máy được cấp khoá ở 0.50.0 được ghi danh lại; máy quản trị đã thu hồi vẫn bị thu hồi
        self.assertEqual((keys.state("device-k15", time.time()), keys.state("device-k16", time.time())), ("none", "revoked"))
        keys.note_used("device-k15", int(time.time()), time.time())
        keys.loaded_for = keys.rows_for = None
        self.assertEqual(keys.state("device-k15", time.time()), "active")

    def test_a_key_sends_only_for_its_own_computer(self):
        key = self.enrol("device-k02")
        self.enrol("device-k03")
        self.assertEqual(self.send("device-k03", key), (403, {"error": "this key belongs to another computer"}))

    def test_a_changed_or_made_up_key_is_refused(self):
        key = self.enrol("device-k04")
        for bad in (key[:-2] + ("AA" if not key.endswith("AA") else "BB"), key.replace("device-k04", "device-k05"),
                    "awd1.x.y.z.w.device-k04.1795000000.sig", "awd1." + "a" * 300):
            status, answer = self.send("device-k04", bad)
            self.assertEqual(status, 401, bad)
        self.assertEqual(self.send("device-k04", key)[0], 200)

    def test_an_expired_key_is_refused_and_the_computer_can_enrol_again(self):
        old = devicekeys.DEVICE_KEYS.issue("device-k06", "device-k06@example.com", "Key 06", time.time() - (devicekeys.KEY_DAYS + 1) * 86400)
        self.devices.append("device-k06")
        self.assertEqual(self.send("device-k06", old), (401, {"error": "device key expired"}))
        # never sent with: the shared key may still enrol it
        # chưa từng gửi bằng khoá này: khoá chung vẫn ghi danh được máy
        self.assertEqual(devicekeys.DEVICE_KEYS.state("device-k06", time.time()), "none")
        # used, but too long ago: the same
        # đã dùng, nhưng quá lâu: cũng vậy
        devicekeys.DEVICE_KEYS.note_used("device-k06", int(old.split(".")[6]), time.time())
        self.assertEqual(devicekeys.DEVICE_KEYS.state("device-k06", time.time()), "expired")
        self.assertTrue(self.enrol("device-k06").startswith("awd1."))

    def test_an_old_key_gets_a_new_one_in_the_answer(self):
        old = devicekeys.DEVICE_KEYS.issue("device-k07", "device-k07@example.com", "Key 07", time.time() - (devicekeys.RENEW_AFTER_DAYS + 1) * 86400)
        self.devices.append("device-k07")
        status, answer = self.send("device-k07", old)
        self.assertEqual(status, 200)
        self.assertNotEqual(answer["deviceKey"], old)
        status, again = self.send("device-k07", answer["deviceKey"])
        self.assertEqual((status, again["ok"], "deviceKey" in again), (200, True, False))

    def test_a_revoked_computer_is_refused_whatever_it_carries_until_it_is_forgotten(self):
        key = self.enrol("device-k08")
        self.assertTrue(devicekeys.DEVICE_KEYS.revoke("device-k08", time.time()))
        self.assertEqual(self.send("device-k08", key), (401, {"error": "device revoked"}))
        self.assertEqual(self.send("device-k08", self.SHARED), (403, {"error": "device revoked"}))
        devicekeys.DEVICE_KEYS.forget("device-k08")
        self.assertTrue(self.enrol("device-k08").startswith("awd1."))

    def test_the_shared_key_can_be_narrowed_and_turned_off(self):
        self.enrol("device-k09")
        devicekeys.DEVICE_KEYS.forget("device-k09")
        settings.SHARED_KEY_MODE = "known-only"
        self.assertEqual(self.send("device-k10", self.SHARED), (401, {"error": "the shared key no longer adds computers"}))
        self.assertEqual(self.send("device-k09", self.SHARED)[0], 200)
        devicekeys.DEVICE_KEYS.forget("device-k09")
        settings.SHARED_KEY_MODE = "off"
        self.assertEqual(self.send("device-k09", self.SHARED), (401, {"error": "the shared key is turned off"}))

    def admin(self, path, body, confirmed=True):
        stores.ACCOUNTS.d = {"accounts": {"adm": {"role": security.ADMIN, "secret": ""}}}
        login.SESSIONS.sessions["tok-key-adm"] = ("adm", time.time() + 3600)
        if confirmed:
            login.SESSIONS.confirmed_at["tok-key-adm"] = time.time()
        else:
            login.SESSIONS.confirmed_at.pop("tok-key-adm", None)
        origin = "http://127.0.0.1:%d" % self.port
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", path, json.dumps(body), {"Cookie": "session=tok-key-adm", "Origin": origin, "Content-Type": "application/json"})
            r = conn.getresponse()
            return r.status, json.loads(r.read() or b"{}")
        finally:
            conn.close()

    def test_an_admin_revokes_a_computer_from_the_page_and_lets_it_back(self):
        key = self.enrol("device-k12")
        self.assertEqual(self.send("device-k12", key)[0], 200)
        listed = {c["device"]: c for c in views.computer_keys(time.time())["computers"]}
        self.assertEqual((listed["device-k12"]["state"], listed["device-k12"]["account"]), ("active", "device-k12@example.com"))
        # without the OTP typed again the action is refused
        # chưa nhập lại OTP thì thao tác bị từ chối
        self.assertNotEqual(self.admin("/admin/device-revoke", {"device": "device-k12"}, confirmed=False)[0], 200)
        self.assertEqual(self.send("device-k12", key)[0], 200)
        self.assertEqual(self.admin("/admin/device-revoke", {"device": "device-k12"})[0], 200)
        self.assertEqual(self.send("device-k12", key), (401, {"error": "device revoked"}))
        self.assertEqual(views.computer_keys(time.time())["revoked"] >= 1, True)
        self.assertEqual(all_audit_rows()[-1]["action"], "device-revoked")
        self.assertNotEqual(self.admin("/admin/device-revoke", {"device": "../etc"})[0], 200)
        self.assertEqual(self.admin("/admin/device-forget", {"device": "device-k12"})[0], 200)
        self.assertTrue(self.enrol("device-k12").startswith("awd1."))

    def release(self, token, ip=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/releases/latest.json", headers=dict({"Authorization": "Bearer " + token}, **({"X-Forwarded-For": ip} if ip else {})))
            r = conn.getresponse()
            return r.status, json.loads(r.read() or b"{}")
        finally:
            conn.close()

    OFFICE = "203.0.113.20"
    HOME = "192.0.2.77"

    def test_from_outside_the_office_only_a_computer_let_roam_sends_and_updates(self):
        settings.OFFICE_NETS = settings.parse_office_nets("203.0.113.0/24, 2001:db8:1::/48")
        roams, stays = self.enrol("device-k20"), self.enrol("device-k21")
        for key in (roams, stays):
            self.assertEqual(self.send(key.split(".")[5], key, ip=self.OFFICE)[0], 200)
            self.assertEqual(self.release(key, self.OFFICE)[0], 200)
        # in the office the shared key still sends and updates, as before
        # trong văn phòng khoá chung vẫn gửi và cập nhật được, như trước
        self.assertEqual(self.send("device-k22", self.SHARED, ip=self.OFFICE)[0], 200)
        self.assertEqual(self.release(self.SHARED, self.OFFICE)[0], 200)
        self.assertEqual(self.release(self.SHARED, "2001:db8:1::5")[0], 200)
        self.assertEqual(self.release(self.SHARED, "::ffff:203.0.113.8")[0], 200)
        # from home nobody is let through yet, and never with 401: the plugin would drop its own key
        # từ nhà chưa ai được qua, và không bao giờ bằng 401: plugin sẽ bỏ khoá riêng của nó
        self.assertEqual(self.send("device-k20", roams, ip=self.HOME), (403, {"error": "this computer may not send from outside the office"}))
        self.assertEqual(self.release(roams, self.HOME), (403, {"error": "this computer may not send from outside the office"}))
        self.assertEqual(self.send("device-k23", self.SHARED, ip=self.HOME), (403, {"error": "outside the office network"}))
        self.assertEqual(self.release(self.SHARED, self.HOME), (403, {"error": "outside the office network"}))
        self.assertTrue(devicekeys.DEVICE_KEYS.set_roaming("device-k20", True, "adm", time.time()))
        self.assertEqual(self.send("device-k20", roams, ip=self.HOME)[0], 200)
        self.assertEqual(self.release(roams, self.HOME)[0], 200)
        self.assertEqual(self.send("device-k21", stays, ip=self.HOME)[0], 403)
        # the roaming key still sends only for its own computer, and a key that does not check is still a 401
        # khoá được gửi từ mọi mạng vẫn chỉ gửi cho đúng máy của nó, và khoá kiểm không đạt vẫn là 401
        self.assertEqual(self.send("device-k21", roams, ip=self.HOME), (403, {"error": "this key belongs to another computer"}))
        self.assertEqual(self.send("device-k20", roams[:-2] + ("AA" if not roams.endswith("AA") else "BB"), ip=self.HOME)[0], 401)
        # the home address is what the board keeps, not what the sender put first in X-Forwarded-For
        # địa chỉ ở nhà là thứ bảng giữ, không phải thứ máy gửi đặt đầu X-Forwarded-For
        self.assertEqual(views.DEVICES.get("device-k20")["ip"], self.HOME)
        # revoked, it is cut off everywhere and loses the right: letting it back does not give the right back
        # bị thu hồi thì bị cắt ở mọi nơi và mất quyền: cho quay lại không trả quyền đó
        self.assertTrue(devicekeys.DEVICE_KEYS.revoke("device-k20", time.time()))
        self.assertEqual(self.send("device-k20", roams, ip=self.HOME)[0], 401)
        devicekeys.DEVICE_KEYS.forget("device-k20")
        self.assertFalse(devicekeys.DEVICE_KEYS.roams("device-k20"))
        self.assertEqual(self.send("device-k20", roams, ip=self.HOME)[0], 403)

    def test_forgetting_a_computer_takes_its_right_to_roam_away(self):
        settings.OFFICE_NETS = settings.parse_office_nets("203.0.113.0/24")
        key = self.enrol("device-k24")
        self.assertEqual(self.send("device-k24", key, ip=self.OFFICE)[0], 200)
        self.assertTrue(devicekeys.DEVICE_KEYS.set_roaming("device-k24", True, "adm", time.time()))
        devicekeys.DEVICE_KEYS.forget("device-k24")
        # its old key is good again, but no longer from outside
        # khoá cũ của nó lại dùng được, nhưng không còn từ bên ngoài
        self.assertEqual(self.send("device-k24", key, ip=self.HOME)[0], 403)
        self.assertEqual(self.send("device-k24", key, ip=self.OFFICE)[0], 200)

    def test_without_office_nets_the_address_is_not_looked_at_unless_caddy_marks_it(self):
        settings.OFFICE_NETS = ()
        key = self.enrol("device-k25")
        self.assertEqual(self.send("device-k25", key, ip=self.HOME)[0], 200)
        self.assertEqual(self.release(self.SHARED, self.HOME)[0], 200)
        # Caddy marks every request from outside its list: then the same rule holds without OFFICE_NETS
        # Caddy đánh dấu mọi yêu cầu ngoài danh sách của nó: khi đó luật vẫn giữ mà không cần OFFICE_NETS
        away = {"X-AiWorker-Away": "1"}
        self.assertEqual(self.send("device-k25", key, ip=self.HOME, headers=away)[0], 403)
        self.assertEqual(self.send("device-k26", self.SHARED, ip=self.HOME, headers=away), (403, {"error": "outside the office network"}))
        devicekeys.DEVICE_KEYS.set_roaming("device-k25", True, "adm", time.time())
        self.assertEqual(self.send("device-k25", key, ip=self.HOME, headers=away)[0], 200)

    def test_office_nets_never_reads_wider_than_written(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            nets = settings.parse_office_nets("203.0.113.0/24,not-a-range 0.0.0.0/0 ::/0  198.51.100.7")
        self.assertEqual([str(n) for n in nets], ["203.0.113.0/24", "198.51.100.7/32"])
        self.assertIn("not an IP range", err.getvalue())
        self.assertIn("holds every address", err.getvalue())
        self.assertFalse(security.in_networks("", nets))
        self.assertFalse(security.in_networks("unknown", nets))
        self.assertTrue(security.in_networks("::ffff:198.51.100.7", nets))
        self.assertFalse(security.in_networks("198.51.100.8", nets))

    def test_an_admin_lets_a_computer_roam_from_the_page(self):
        settings.OFFICE_NETS = settings.parse_office_nets("203.0.113.0/24")
        key = self.enrol("device-k27")
        self.assertEqual(self.send("device-k27", key, ip=self.OFFICE)[0], 200)
        # without the OTP typed again the action is refused
        # chưa nhập lại OTP thì thao tác bị từ chối
        self.assertNotEqual(self.admin("/admin/device-roam", {"device": "device-k27", "roaming": True}, confirmed=False)[0], 200)
        self.assertFalse(devicekeys.DEVICE_KEYS.roams("device-k27"))
        self.assertEqual(self.admin("/admin/device-roam", {"device": "device-k27", "roaming": True})[0], 200)
        self.assertEqual(all_audit_rows()[-1]["action"], "device-roaming-on")
        self.assertEqual(all_audit_rows()[-1]["device"], "device-k27")
        listed = {c["device"]: c for c in views.computer_keys(time.time())["computers"]}
        self.assertIsNotNone(listed["device-k27"]["roamingSince"])
        self.assertEqual(views.computer_keys(time.time())["officeNets"], 1)
        self.assertEqual(self.send("device-k27", key, ip=self.HOME)[0], 200)
        self.assertEqual(self.admin("/admin/device-roam", {"device": "device-k27", "roaming": False})[0], 200)
        self.assertEqual(all_audit_rows()[-1]["action"], "device-roaming-off")
        self.assertEqual(self.send("device-k27", key, ip=self.HOME)[0], 403)
        # a computer that has never sent with its own key, or a made-up id, cannot be let
        # máy chưa từng gửi bằng khoá riêng, hay mã máy bịa ra, không được cho
        self.send("device-k28", self.SHARED, ip=self.OFFICE)
        self.assertEqual(self.admin("/admin/device-roam", {"device": "device-k28", "roaming": True})[0], 400)
        self.assertNotEqual(self.admin("/admin/device-roam", {"device": "../etc", "roaming": True})[0], 200)

    def test_updates_still_download_with_either_key(self):
        key = self.enrol("device-k11")
        for token in (self.SHARED, key):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            try:
                conn.request("GET", "/releases/latest.json", headers={"Authorization": "Bearer " + token})
                self.assertEqual(conn.getresponse().status, 200)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
