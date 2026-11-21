# A board server with sample people for the menu bar tests: it approves every pairing code by itself. Never run on a real server.
# Máy chủ bảng với người giả cho bài thử thanh menu: tự duyệt mọi mã ghép. Không bao giờ chạy trên máy chủ thật.
import os
import sys
import tempfile
import threading
import time

TMP = tempfile.mkdtemp(prefix="menubar-test-")
os.environ.update(DATA_DIR=os.path.join(TMP, "data"), KEYS_DIR=os.path.join(TMP, "keys"), INGEST_KEY="test", OTP="",
                  BRANCHES_FILE=os.path.join(TMP, "none.json"))
os.makedirs(os.environ["DATA_DIR"])
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server"))
import webhook as w  # noqa: E402
from board import devices, stores  # noqa: E402

now = time.time()
hour = str(int(now // 3600))
for i, (name, waiting, minutes) in enumerate([("Ann", 1, 14), ("Ben", 1, 3), ("Cat", 0, 0)]):
    # Cat is working on Opus; everyone has a quota reading and some cost today, so every section of the menu has rows
    # Cat đang làm bằng Opus; ai cũng có số hạn mức và chi phí hôm nay, để mọi mục của menu đều có dòng
    devices.save_ingest(devices.clean_payload({"v": 1, "device": "device-fake%d" % i, "name": name, "account": "p%d@example.com" % i,
                                   "updatedAt": int(now * 1000), "openSessions": 1, "waiting": waiting, "working": 1 - waiting,
                                   "models": {"claude-opus-4-1": 3}, "ledger": {hour: {"usd": 1.25 * (i + 1), "input": 1000, "output": 200}},
                                   "quota": {"readAt": int(now * 1000), "windows": [{"kind": "five_hour", "pct": 30 + 25 * i}]}}, now), now)
    if waiting:
        stores.WAIT_TRACKER.since["p%d@example.com|%s" % (i, name)] = int((now - minutes * 60) * 1000)


def approve():
    while True:
        for code, r in list(stores.TV_PAIRING.pending.items()):
            if not r["name"]:
                stores.TV_PAIRING.approve(code, "Menu bar test", "adm", time.time())
        time.sleep(0.5)


threading.Thread(target=approve, daemon=True).start()
# while the file named in MENUBAR_TEST_HOSTILE exists, the window code is one a hostile server would send: a menu line and a shell command inside it
# khi file ghi trong MENUBAR_TEST_HOSTILE còn tồn tại, mã mở khung là mã một máy chủ xấu sẽ gửi: có dòng menu và câu lệnh shell bên trong
HOSTILE = os.environ.get("MENUBAR_TEST_HOSTILE", "")
HOSTILE_CODE = "abc' ; touch %s.pwned ; echo ' bash=/usr/bin/touch param1=%s.pwned terminal=false" % (HOSTILE, HOSTILE)
plain_issue = stores.MINI_HANDOFF.issue
stores.MINI_HANDOFF.issue = lambda token, now: HOSTILE_CODE if HOSTILE and os.path.exists(HOSTILE) else plain_issue(token, now)
# while the file named in MENUBAR_TEST_BLOCKED exists, every request gets the plain 403 page a proxy in front of the board sends to a network
# it does not allow (Caddy's "Forbidden"), not an answer of the board
# khi file ghi trong MENUBAR_TEST_BLOCKED còn tồn tại, mọi yêu cầu nhận trang 403 chữ thường mà proxy đứng trước bảng gửi cho mạng nó
# không cho phép ("Forbidden" của Caddy), không phải câu trả lời của bảng
BLOCKED = os.environ.get("MENUBAR_TEST_BLOCKED", "")


class Handler(w.Handler):
    def handle_one_request(self):
        if BLOCKED and os.path.exists(BLOCKED):
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline or not self.parse_request():
                return
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "9")
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return
        super().handle_one_request()


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8781
print("ready on %d" % port, flush=True)
w.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
