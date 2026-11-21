#!/usr/bin/env python3
"""Tests of the connector for Codex, Cursor and Gemini CLI: python3 tests/connectors/test_connectors.py
The hook is fed sample events and sends to a small server inside this test; the installer runs in a temporary home folder.
On macOS and Linux this tests the sh files, on Windows the PowerShell files. Nothing outside the temporary folder is touched.
  Test bộ nối cho Codex, Cursor và Gemini CLI: python3 tests/connectors/test_connectors.py
  Hook nhận các sự kiện mẫu và gửi tới một máy chủ nhỏ ngay trong bài test; bộ cài chạy trong một thư mục nhà tạm.
  Trên macOS và Linux bài này thử các file sh, trên Windows thử các file PowerShell. Không đụng tới gì ngoài thư mục tạm."""
import http.server
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONNECTORS = os.path.join(ROOT, "connectors")
WINDOWS = os.name == "nt"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
KEY = "test-send-key"
# words that sit in the sample events and must never be stored or sent
# các từ nằm trong sự kiện mẫu và không bao giờ được lưu hay gửi đi
PRIVATE = ("secret-project", "topsecret-prompt", "private-answer", "hidden-file.py", "someone@example.com")

TMP = tempfile.mkdtemp(prefix="test-connectors-")
os.environ.update(INGEST_KEY=KEY, DATA_DIR=os.path.join(TMP, "server-data"), KEYS_DIR=os.path.join(TMP, "server-keys"), OTP="")
os.makedirs(os.environ["DATA_DIR"])
sys.path.insert(0, os.path.join(ROOT, "server"))
from board import devices  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Board(http.server.BaseHTTPRequestHandler):
    """Stands in for the board: keeps every report it is sent and answers with the status the test asked for.
    Đóng vai bảng: giữ mọi báo cáo nhận được và trả lời bằng mã mà bài test yêu cầu."""

    reports = []
    status = 200
    answer = b"{}"

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Board.reports.append({"path": self.path, "key": self.headers.get("Authorization"), "body": body.decode("utf-8")})
        self.send_response(Board.status)
        self.send_header("Content-Length", str(len(Board.answer)))
        self.end_headers()
        self.wfile.write(Board.answer)

    def log_message(self, *args):
        pass


def setUpModule():
    global SERVER, URL
    SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Board)
    URL = "http://127.0.0.1:%d" % SERVER.server_address[1]
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()


def run_hook(folder: str, tool: str, event: str, payload: dict = None, env: dict = None) -> str:
    """Run the hook the way a tool does: the event as JSON on stdin; returns what the hook printed.
    Chạy hook đúng cách một công cụ chạy: sự kiện dạng JSON qua stdin; trả về thứ hook in ra."""
    if WINDOWS:
        command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(CONNECTORS, "ai-worker-hook.ps1"), tool, event]
    else:
        command = ["sh", os.path.join(CONNECTORS, "ai-worker-hook.sh"), tool, event]
    done = subprocess.run(command, input=json.dumps(payload or {}), capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, AI_WORKER_CONNECTOR_DIR=folder, **(env or {})))
    return done.stdout.strip()


def wait_for(condition, seconds: float = 15):
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = condition()
        if found:
            return found
        time.sleep(0.05)
    return condition()


class Hook(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="connector-", dir=TMP)
        with open(os.path.join(self.folder, "config"), "w", encoding="utf-8") as f:
            f.write("url=%s\nkey=%s\nname=Tool Person\naccount=tool@example.com\n" % (URL, KEY))
        Board.reports.clear()
        Board.status = 200
        Board.answer = b"{}"

    def event(self, tool: str, event: str, **fields) -> str:
        return run_hook(self.folder, tool, event, fields)

    def sessions(self) -> list:
        with open(os.path.join(self.folder, "sessions"), encoding="utf-8") as f:
            return [line.split()[:3] + line.split()[4:5] for line in f.read().splitlines() if line.strip()]

    def last_tools(self, expected: dict) -> dict:
        """Wait until the board has been sent these counts, and return that report.
        Chờ tới khi bảng nhận được đúng các số này, rồi trả về báo cáo đó."""
        def found():
            for r in reversed(Board.reports):
                report = json.loads(r["body"])
                if report["tools"] == expected:
                    return report
            return None
        report = wait_for(found)
        self.assertIsNotNone(report, "the board never received %r; it received %r" % (expected, [json.loads(r["body"])["tools"] for r in Board.reports]))
        return report

    def test_a_codex_session_goes_from_idle_to_working_to_waiting_to_closed(self):
        steps = (
            ("start", {"source": "startup", "cwd": "/Users/x/secret-project"}, "idle", {"openSessions": 1, "working": 0, "waiting": 0}),
            ("prompt", {"prompt": "topsecret-prompt in hidden-file.py?"}, "working", {"openSessions": 1, "working": 1, "waiting": 0}),
            ("ask", {"tool_name": "Bash", "tool_input": {"command": "cat hidden-file.py", "description": None}}, "waiting", {"openSessions": 1, "working": 0, "waiting": 1}),
            ("tool", {"tool_name": "Bash", "tool_response": "private-answer"}, "working", {"openSessions": 1, "working": 1, "waiting": 0}),
            ("stop", {"last_assistant_message": "Done. private-answer is in \"hidden-file.py\".\n"}, "idle", {"openSessions": 1, "working": 0, "waiting": 0}),
            ("prompt", {"prompt": "and now?"}, "working", {"openSessions": 1, "working": 1, "waiting": 0}),
            ("stop", {"last_assistant_message": "private-answer. Should I also **update the tests?**\n"}, "waiting", {"openSessions": 1, "working": 0, "waiting": 1}),
        )
        for event, fields, state, counts in steps:
            with self.subTest(event=event, state=state):
                self.assertEqual(self.event("codex", event, session_id="019a-one", hook_event_name="X", model="gpt-x", **fields), "")
                self.assertEqual(self.sessions(), [["codex", "019a-one", state] + self.sessions()[0][3:]])
                self.last_tools({"codex": counts})
        self.event("codex", "end", session_id="019a-one", reason="other")
        self.assertEqual(self.sessions(), [])
        report = self.last_tools({})
        self.assertEqual([report[k] for k in devices.SESSION_COUNTS], [0, 0, 0])

    def test_nothing_private_is_stored_or_sent(self):
        self.test_a_codex_session_goes_from_idle_to_working_to_waiting_to_closed()
        self.event("cursor", "start", conversation_id="c-1", workspace_roots=["/Users/x/secret-project"], user_email="someone@example.com")
        self.event("cursor", "reply", conversation_id="c-1", text="private-answer?")
        self.last_tools({"cursor": {"openSessions": 1, "working": 0, "waiting": 0}})
        kept = ""
        for name in os.listdir(self.folder):
            path = os.path.join(self.folder, name)
            if os.path.isfile(path) and name != "config":
                with open(path, encoding="utf-8", errors="replace") as f:
                    kept += f.read()
        sent = "".join(r["body"] for r in Board.reports)
        for word in PRIVATE:
            self.assertNotIn(word, kept)
            self.assertNotIn(word, sent)
        for r in Board.reports:
            self.assertEqual(set(json.loads(r["body"])), {"v", "device", "name", "account", "updatedAt", "openSessions", "working", "waiting", "tools"})

    def test_the_report_is_what_the_server_expects(self):
        self.event("codex", "prompt", session_id="s1")
        self.event("gemini", "start", session_id="g1")
        report = self.last_tools({"codex": {"openSessions": 1, "working": 1, "waiting": 0}, "gemini": {"openSessions": 1, "working": 0, "waiting": 0}})
        self.assertEqual((Board.reports[-1]["path"], Board.reports[-1]["key"]), ("/ingest", "Bearer " + KEY))
        clean = devices.clean_payload(report, time.time())
        self.assertEqual(clean["tools"], report["tools"])
        self.assertEqual((clean["name"], clean["account"], clean["device"]), ("Tool Person", "tool@example.com", report["device"]))
        self.assertTrue(devices.from_connector(clean))
        self.assertLess(abs(report["updatedAt"] / 1000 - time.time()), 60)
        person = devices.group_by_person([clean], time.time())[0]
        self.assertEqual((devices.status_of(person, time.time()), person["openSessions"], person["working"]), ("working", 2, 1))

    def test_each_tool_gets_the_answer_it_reads(self):
        self.assertEqual(self.event("codex", "prompt", session_id="s"), "")
        self.assertEqual(self.event("codex", "stop", session_id="s"), "")
        self.assertEqual(json.loads(self.event("cursor", "prompt", conversation_id="c")), {"continue": True})
        self.assertEqual(json.loads(self.event("cursor", "stop", conversation_id="c")), {})
        self.assertEqual(json.loads(self.event("gemini", "prompt", session_id="g")), {})
        self.assertEqual(json.loads(self.event("gemini", "stop", session_id="g")), {})

    def test_a_tool_is_answered_even_when_the_connector_is_not_set_up(self):
        empty = tempfile.mkdtemp(prefix="none-", dir=TMP)
        self.assertEqual(json.loads(run_hook(empty, "cursor", "prompt", {"conversation_id": "c"})), {"continue": True})
        self.assertEqual(run_hook(empty, "codex", "stop", {"session_id": "s"}), "")
        self.assertEqual(os.listdir(empty), [])
        self.assertEqual(Board.reports, [])

    def test_cursor_waits_when_the_reply_asked_something_and_gemini_when_it_wants_an_approval(self):
        self.event("cursor", "prompt", conversation_id="c-9", prompt="x")
        self.event("cursor", "reply", conversation_id="c-9", text="Renamed. Do you want me to run the tests?")
        self.assertEqual(self.sessions()[0][:3], ["cursor", "c-9", "working"])
        self.event("cursor", "stop", conversation_id="c-9", status="completed")
        self.assertEqual(self.sessions()[0][:3], ["cursor", "c-9", "waiting"])
        self.event("cursor", "prompt", conversation_id="c-9", prompt="yes")
        self.event("cursor", "reply", conversation_id="c-9", text="All 12 tests pass.")
        self.event("cursor", "stop", conversation_id="c-9", status="completed")
        self.assertEqual(self.sessions()[0][:3], ["cursor", "c-9", "idle"])
        run_hook(self.folder, "gemini", "prompt", {"prompt": "x"}, {"GEMINI_SESSION_ID": "g-7"})
        run_hook(self.folder, "gemini", "ask", {"notification_type": "ToolPermission"}, {"GEMINI_SESSION_ID": "g-7"})
        self.assertIn(["gemini", "g-7", "waiting", "2"], self.sessions())
        run_hook(self.folder, "gemini", "tool", {}, {"GEMINI_SESSION_ID": "g-7"})
        self.assertIn(["gemini", "g-7", "working", "0"], self.sessions())
        run_hook(self.folder, "gemini", "stop", {"prompt_response": "Which one do you prefer?"}, {"GEMINI_SESSION_ID": "g-7"})
        self.assertIn(["gemini", "g-7", "waiting", "0"], self.sessions())
        self.last_tools({"cursor": {"openSessions": 1, "working": 0, "waiting": 0}, "gemini": {"openSessions": 1, "working": 0, "waiting": 1}})

    def test_cutting_a_codex_turn_short_leaves_the_session_idle(self):
        # Codex sends Interrupt, not Stop, when the person presses Esc: the installer maps both to "stop"
        # Codex gửi Interrupt, không gửi Stop, khi người dùng bấm Esc: bộ cài gắn cả hai vào "stop"
        self.event("codex", "prompt", session_id="s", prompt="count slowly")
        self.event("codex", "stop", session_id="s", hook_event_name="Interrupt", turn_id="t", permission_mode="default")
        self.assertEqual(self.sessions()[0][:3], ["codex", "s", "idle"])

    def test_a_late_tool_event_does_not_wake_a_session_that_waits_on_a_question(self):
        self.event("codex", "prompt", session_id="s")
        self.event("codex", "stop", session_id="s", last_assistant_message="Shall I go on?")
        self.event("codex", "tool", session_id="s")
        self.assertEqual(self.sessions()[0][:3], ["codex", "s", "waiting"])

    def test_a_session_silent_for_two_hours_is_no_longer_counted(self):
        old = int(time.time()) - 7300
        with open(os.path.join(self.folder, "sessions"), "w", encoding="utf-8") as f:
            f.write("codex gone waiting %d 0\ncursor fresh working %d 0\n" % (old, int(time.time()) - 60))
        self.event("gemini", "start", session_id="g")
        self.assertEqual(sorted(s[1] for s in self.sessions()), ["fresh", "g"])
        self.last_tools({"cursor": {"openSessions": 1, "working": 1, "waiting": 0}, "gemini": {"openSessions": 1, "working": 0, "waiting": 0}})

    def test_a_refused_send_is_noted_and_sent_again_at_the_next_event(self):
        Board.status = 401
        self.event("codex", "prompt", session_id="s")
        error_file = os.path.join(self.folder, "last-error")
        self.assertTrue(wait_for(lambda: os.path.exists(error_file)))
        with open(error_file, encoding="utf-8") as f:
            self.assertIn("http=401", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.folder, "sent")))
        Board.status = 200
        Board.reports.clear()
        self.event("codex", "tool", session_id="s")
        self.last_tools({"codex": {"openSessions": 1, "working": 1, "waiting": 0}})
        self.assertTrue(wait_for(lambda: not os.path.exists(error_file)))

    def test_the_key_the_board_gives_is_kept_privately_used_next_and_dropped_when_refused(self):
        own = "awd1.kid1.org1.pid1.rk1.device-x.1795000000.sig1"
        Board.answer = json.dumps({"ok": True, "deviceKey": own}).encode()
        self.event("codex", "prompt", session_id="s")
        key_file = os.path.join(self.folder, "device-key")
        self.assertTrue(wait_for(lambda: os.path.exists(key_file)))
        with open(key_file, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), own)
        if not WINDOWS:
            self.assertEqual(os.stat(key_file).st_mode & 0o077, 0)
        self.assertEqual(Board.reports[-1]["key"], "Bearer " + KEY)
        Board.answer = b"{}"
        # a second session changes the counts, so the connector sends again
        # một phiên thứ hai làm đổi số, nên bộ nối gửi lại
        self.event("codex", "prompt", session_id="t")
        self.assertTrue(wait_for(lambda: Board.reports[-1]["key"] == "Bearer " + own))
        # the board refuses that key: it is dropped, and the next send goes with the package's key to get a new one
        # bảng từ chối khoá đó: nó bị bỏ, và lần gửi sau đi bằng khoá của gói để xin khoá mới
        Board.status = 401
        self.event("codex", "prompt", session_id="u")
        self.assertTrue(wait_for(lambda: not os.path.exists(key_file)))
        Board.status = 200
        self.event("codex", "prompt", session_id="v")
        self.assertTrue(wait_for(lambda: Board.reports[-1]["key"] == "Bearer " + KEY))

    def test_nothing_is_sent_again_while_nothing_changed(self):
        self.event("codex", "prompt", session_id="s")
        self.last_tools({"codex": {"openSessions": 1, "working": 1, "waiting": 0}})
        self.assertTrue(wait_for(lambda: os.path.exists(os.path.join(self.folder, "sent"))))
        before = len(Board.reports)
        for _ in range(3):
            self.event("codex", "tool", session_id="s")
        time.sleep(1)
        self.assertEqual(len(Board.reports), before)


def json_program() -> bool:
    """Whether this computer can run merge-hooks.js: macOS always can, elsewhere Node is needed. Windows merges in PowerShell itself.
    Máy này có chạy được merge-hooks.js không: macOS luôn chạy được, nơi khác cần Node. Windows tự gộp bằng PowerShell."""
    return WINDOWS or sys.platform == "darwin" or bool(shutil.which("node"))


class Installer(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="home-", dir=TMP)
        self.folder = os.path.join(self.home, ".local", "share", "ai-worker", "connector")
        Board.reports.clear()
        Board.status = 200

    def install(self, *args, connectors: str = CONNECTORS) -> subprocess.CompletedProcess:
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, AI_WORKER_LANG="en")
        for name in ("AI_WORKER_CONNECTOR_DIR", "CODEX_HOME", "AI_WORKER_URL", "AI_WORKER_KEY"):
            env.pop(name, None)
        if WINDOWS:
            command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(connectors, "install.ps1")]
            args = ["-" + a[2:].title().replace("-", "") if a.startswith("--") else a for a in args]
        else:
            command = ["bash", os.path.join(connectors, "install.sh")]
        return subprocess.run(command + list(args), input="", capture_output=True, text=True, timeout=120, env=env)

    def first_install(self, tools: str, *more, connectors: str = CONNECTORS) -> subprocess.CompletedProcess:
        return self.install("--server", URL + "/", "--key", KEY, "--name", 'Tool "Person"', "--account", "Tool@Example.com", "--tools", tools, *more, connectors=connectors)

    def write(self, relative: str, text: str) -> str:
        path = os.path.join(self.home, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def read(self, relative: str) -> str:
        with open(os.path.join(self.home, *relative.split("/")), encoding="utf-8-sig") as f:
            return f.read()

    def commands(self, relative: str) -> list:
        found = []

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("command"), str):
                    found.append(node["command"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(json.loads(self.read(relative)))
        return found

    def test_a_fresh_install_writes_the_hooks_the_settings_and_tells_the_board(self):
        done = self.first_install("codex,cursor,gemini", "--no-skills")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len([c for c in self.commands(".codex/hooks.json") if "ai-worker-hook" in c and " codex " in c]), 7)
        self.assertEqual(len([c for c in self.commands(".cursor/hooks.json") if "ai-worker-hook" in c and " cursor " in c]), 5)
        self.assertEqual(len([c for c in self.commands(".gemini/settings.json") if "ai-worker-hook" in c and " gemini " in c]), 6)
        self.assertEqual(json.loads(self.read(".cursor/hooks.json"))["version"], 1)
        config = dict(line.split("=", 1) for line in self.read(".local/share/ai-worker/connector/config").splitlines())
        self.assertEqual(config, {"url": URL, "key": KEY, "name": "Tool Person", "account": "tool@example.com"})
        if not WINDOWS:
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.folder, "config")).st_mode), 0o600)
        self.assertIn("received", done.stdout)
        report = json.loads(Board.reports[-1]["body"])
        self.assertEqual((report["name"], report["account"], report["tools"]), ("Tool Person", "tool@example.com", {}))
        self.assertRegex(report["device"], r"^device-[a-z0-9]{1,40}$")
        self.assertFalse(os.path.exists(os.path.join(self.home, ".agents")))
        self.assertNotIn(KEY, done.stdout + done.stderr)

    def test_the_installed_hook_runs_from_the_command_written_for_the_tool(self):
        self.first_install("cursor", "--no-skills")
        command = [c for c in self.commands(".cursor/hooks.json") if c.endswith(" cursor prompt")][0]
        done = subprocess.run(command, shell=True, input='{"conversation_id":"c"}', capture_output=True, text=True, timeout=60,
                              cwd=os.path.join(self.home, ".cursor"), env=dict(os.environ, HOME=self.home, USERPROFILE=self.home))
        self.assertEqual(json.loads(done.stdout), {"continue": True})
        self.assertTrue(wait_for(lambda: [r for r in Board.reports if json.loads(r["body"])["tools"].get("cursor", {}).get("working") == 1]))

    @unittest.skipUnless(json_program(), "needs osascript or node to merge JSON")
    def test_hooks_are_merged_into_settings_that_exist_and_come_out_again(self):
        gemini = {"security": {"auth": {"selectedType": "oauth-personal"}},
                  "hooks": {"BeforeTool": [{"matcher": "write_file", "hooks": [{"name": "mine", "type": "command", "command": "/usr/local/bin/my-check.sh"}]}],
                            "SessionStart": [{"hooks": [{"name": "hello", "type": "command", "command": "echo hi >&2"}]}]},
                  "ui": {"theme": "Dracula"}}
        cursor = {"version": 1, "hooks": {"afterFileEdit": [{"command": "./hooks/format.sh"}], "stop": [{"command": "./hooks/notify.sh"}]}}
        codex = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done", "timeout": 30}]}]}}
        for relative, data in ((".gemini/settings.json", gemini), (".cursor/hooks.json", cursor), (".codex/hooks.json", codex)):
            self.write(relative, json.dumps(data, indent=2))
        self.assertEqual(self.first_install("codex,cursor,gemini", "--no-skills").returncode, 0)
        merged = json.loads(self.read(".gemini/settings.json"))
        self.assertEqual(list(merged), list(gemini))
        self.assertEqual((merged["security"], merged["ui"], merged["hooks"]["BeforeTool"]), (gemini["security"], gemini["ui"], gemini["hooks"]["BeforeTool"]))
        self.assertEqual(merged["hooks"]["SessionStart"][0], gemini["hooks"]["SessionStart"][0])
        self.assertEqual(len(merged["hooks"]["SessionStart"]), 2)
        self.assertIn("./hooks/notify.sh", self.commands(".cursor/hooks.json"))
        self.assertIn("say done", self.commands(".codex/hooks.json"))
        once = {name: self.read(name) for name in (".gemini/settings.json", ".cursor/hooks.json", ".codex/hooks.json")}
        # a second run changes nothing: no hook is added twice
        # chạy lần hai không đổi gì: không hook nào bị thêm hai lần
        self.assertEqual(self.install("--tools", "codex,cursor,gemini", "--no-skills").returncode, 0)
        for name, text in once.items():
            self.assertEqual(json.loads(self.read(name)), json.loads(text))
        self.assertEqual(self.install("--uninstall").returncode, 0)
        for relative, data in ((".gemini/settings.json", gemini), (".cursor/hooks.json", cursor), (".codex/hooks.json", codex)):
            self.assertEqual(json.loads(self.read(relative)), data)
            self.assertEqual(json.loads(self.read(relative + ".ai-worker-backup")), data)
        self.assertFalse(os.path.exists(self.folder))

    def test_choosing_fewer_tools_later_takes_the_others_out_and_uninstall_leaves_nothing(self):
        self.first_install("codex,cursor,gemini", "--no-skills")
        self.assertEqual(self.install("--tools", "cursor", "--no-skills").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".codex", "hooks.json")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".gemini", "settings.json")))
        self.assertTrue(os.path.exists(os.path.join(self.home, ".cursor", "hooks.json")))
        Board.reports.clear()
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".cursor", "hooks.json")))
        self.assertFalse(os.path.exists(self.folder))
        # the last thing the board hears is that no session is open here
        # điều cuối cùng bảng nghe được là ở đây không còn phiên nào mở
        self.assertEqual(json.loads(Board.reports[-1]["body"])["tools"], {})

    def test_codex_hooks_go_into_config_toml_when_hooks_already_live_there(self):
        original = 'model = "gpt-x"\n\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "say done"\n\n[projects."/Users/x/p"]\ntrust_level = "trusted"\n'
        self.write(".codex/config.toml", original)
        self.assertEqual(self.first_install("codex", "--no-skills").returncode, 0)
        self.assertEqual(self.install("--tools", "codex", "--no-skills").returncode, 0)
        text = self.read(".codex/config.toml")
        self.assertTrue(text.replace("\r\n", "\n").startswith(original))
        self.assertEqual(text.count("ai-worker-hook"), 7)
        self.assertEqual(text.count("timeout = 3"), 2)
        self.assertEqual(text.count("[[hooks.SessionEnd]]"), 1)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".codex", "hooks.json")))
        if sys.version_info >= (3, 11):
            import tomllib
            parsed = tomllib.loads(text)
            self.assertEqual(len(parsed["hooks"]["Stop"]), 2)
            self.assertEqual(parsed["projects"]["/Users/x/p"]["trust_level"], "trusted")
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.read(".codex/config.toml").replace("\r\n", "\n"), original)

    @unittest.skipUnless(json_program(), "needs osascript or node to merge JSON")
    def test_settings_that_are_not_plain_json_are_left_alone(self):
        text = '// my notes\n{ "ui": { "theme": "x" } }\n'
        self.write(".gemini/settings.json", text)
        done = self.first_install("gemini", "--no-skills")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.read(".gemini/settings.json"), text)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".gemini", "settings.json.ai-worker-backup")))
        self.assertIn("by hand", done.stdout)
        self.assertIn("ai-worker-hook", done.stdout)

    def test_skills_are_copied_only_when_asked_and_never_over_someone_elses_folder(self):
        mine = self.write(".agents/skills/tdd/SKILL.md", "my own skill\n")
        self.assertEqual(self.first_install("codex", "--skills").returncode, 0)
        skills = os.path.join(self.home, ".agents", "skills")
        self.assertTrue(os.path.isfile(os.path.join(skills, "grilling", "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(skills, "security-audit", "SKILL.md")))
        # these two lean on Claude Code, so they are not copied
        # hai skill này dựa vào Claude Code nên không được chép
        self.assertFalse(os.path.exists(os.path.join(skills, "make-skill")))
        self.assertFalse(os.path.exists(os.path.join(skills, "improve-codebase-architecture")))
        with open(mine, encoding="utf-8") as f:
            self.assertEqual(f.read(), "my own skill\n")
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(os.listdir(skills), ["tdd"])
        with open(mine, encoding="utf-8") as f:
            self.assertEqual(f.read(), "my own skill\n")

    def package(self, *skills) -> str:
        """A small package of its own: the connector and a few skills, so a test can change what the package ships.
        Một gói nhỏ riêng: bộ nối và vài skill, để bài test đổi được thứ mà gói mang theo."""
        folder = tempfile.mkdtemp(prefix="package-", dir=TMP)
        shutil.copytree(CONNECTORS, os.path.join(folder, "connectors"))
        for skill in skills:
            shutil.copytree(os.path.join(ROOT, "skills", skill), os.path.join(folder, "skills", skill))
        return folder

    def new_version_of(self, package: str, skill: str, text: str) -> None:
        with open(os.path.join(package, "skills", skill, "SKILL.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + text + "\n")

    def skill_text(self, skill: str) -> str:
        with open(os.path.join(self.home, ".agents", "skills", skill, "SKILL.md"), encoding="utf-8") as f:
            return f.read()

    def test_a_skill_the_person_changed_is_kept_and_the_others_get_the_new_version(self):
        package = self.package("grilling", "tdd", "handoff")
        connectors = os.path.join(package, "connectors")
        self.assertEqual(self.first_install("codex", "--skills", connectors=connectors).returncode, 0)
        skills = os.path.join(self.home, ".agents", "skills")
        self.assertEqual(sorted(os.listdir(skills)), ["grilling", "handoff", "tdd"])
        with open(os.path.join(skills, "grilling", "SKILL.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\nmy own extra rule\n")
        # a file the system drops into a folder by itself is not a change by the person
        # file hệ thống tự thả vào thư mục không phải là thay đổi của người dùng
        with open(os.path.join(skills, "handoff", ".DS_Store"), "w", encoding="utf-8") as f:
            f.write("x")
        for skill in ("grilling", "tdd", "handoff"):
            self.new_version_of(package, skill, "second version of the package")
        done = self.install("--tools", "codex", "--skills", connectors=connectors)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("my own extra rule", self.skill_text("grilling"))
        self.assertNotIn("second version", self.skill_text("grilling"))
        self.assertIn("grilling: changed on this computer", done.stdout)
        self.assertIn("second version", self.skill_text("tdd"))
        self.assertIn("second version", self.skill_text("handoff"))
        self.assertNotIn("tdd: changed", done.stdout)
        self.assertNotIn("handoff: changed", done.stdout)
        # a run with nothing new changes nothing and still keeps the changed skill
        # chạy lại khi không có gì mới thì không đổi gì và vẫn giữ skill đã sửa
        again = self.install("--tools", "codex", "--skills", connectors=connectors)
        self.assertIn("my own extra rule", self.skill_text("grilling"))
        self.assertIn("grilling: changed on this computer", again.stdout)
        done = self.install("--uninstall", connectors=connectors)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(os.listdir(skills), ["grilling"])
        self.assertIn("my own extra rule", self.skill_text("grilling"))
        self.assertIn("grilling: changed on this computer", done.stdout)

    def test_skills_put_there_by_the_first_release_carry_no_mark(self):
        package = self.package("grilling", "tdd")
        connectors = os.path.join(package, "connectors")
        self.assertEqual(self.first_install("codex", "--skills", connectors=connectors).returncode, 0)
        # 0.32.0 wrote the names alone, so nothing says whether such a skill was changed since
        # bản 0.32.0 chỉ ghi tên, nên không có gì cho biết skill như vậy đã bị sửa từ đó hay chưa
        with open(os.path.join(self.folder, "skills-installed"), "w", encoding="utf-8", newline="\n") as f:
            f.write("grilling\ntdd\n")
        self.new_version_of(package, "tdd", "second version of the package")
        done = self.install("--tools", "codex", "--skills", connectors=connectors)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        # it differs from the package and may hold the person's work: it is kept, and the person is told
        # nó khác với gói và có thể chứa công sức của người dùng: được giữ lại, và người dùng được báo
        self.assertNotIn("second version", self.skill_text("tdd"))
        self.assertIn("tdd: changed on this computer", done.stdout)
        self.assertNotIn("grilling: changed", done.stdout)
        # removing still takes them out, as that release promised
        # khi gỡ thì vẫn gỡ chúng, đúng như bản đó đã hứa
        self.assertEqual(self.install("--uninstall", connectors=connectors).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".agents")))

    def test_every_skill_in_the_plugin_is_either_copied_or_left_out_on_purpose(self):
        import re
        with open(os.path.join(CONNECTORS, "install.ps1" if WINDOWS else "install.sh"), encoding="utf-8-sig") as f:
            copied = re.search(r"""PORTABLE_?SKILLS\s*=\s*["']([^"']+)["']""", f.read(), re.I).group(1).split()
        shipped = sorted(name for name in os.listdir(os.path.join(ROOT, "skills")) if os.path.isfile(os.path.join(ROOT, "skills", name, "SKILL.md")))
        self.assertEqual(sorted(copied + ["make-skill", "improve-codebase-architecture"]), shipped)

    def test_a_refused_key_is_reported_in_plain_words(self):
        Board.status = 401
        done = self.first_install("codex", "--no-skills")
        self.assertIn("401", done.stdout)
        self.assertNotIn("received.", done.stdout)


class BothInstallersAgree(unittest.TestCase):
    """The sh and the PowerShell installer write the same events for each tool.
    Bộ cài sh và bộ cài PowerShell ghi cùng các sự kiện cho từng công cụ."""

    def test_the_same_events_in_both(self):
        import re
        with open(os.path.join(CONNECTORS, "install.sh"), encoding="utf-8") as f:
            sh = f.read()
        with open(os.path.join(CONNECTORS, "install.ps1"), encoding="utf-8-sig") as f:
            ps = f.read()
        for tool in ("codex", "gemini", "cursor"):
            in_sh = re.search(r'%s\) echo "([^"]+)"' % tool, sh).group(1).split()
            in_ps = re.search(r"%s\s*=\s*'([^']+=[^']+)'" % tool, ps).group(1).split()
            self.assertEqual(in_sh, in_ps, tool)


if __name__ == "__main__":
    unittest.main()
