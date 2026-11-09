# A board server with made-up people for the browser extension test, on 127.0.0.1 only. Never run on a real server.
# Commands on stdin, one per line: approve, revoke, wait NAME, stop NAME, audit. Each answers one line on stdout.
# Máy chủ bảng với người giả cho bài thử tiện ích trình duyệt, chỉ trên 127.0.0.1. Không bao giờ chạy trên máy chủ thật.
# Lệnh qua stdin, mỗi dòng một lệnh: approve, revoke, wait TÊN, stop TÊN, audit. Mỗi lệnh trả một dòng ra stdout.
import json
import os
import sys
import tempfile
import threading
import time

TMP = tempfile.mkdtemp(prefix="extension-test-")
os.environ.update(DATA_DIR=os.path.join(TMP, "data"), KEYS_DIR=os.path.join(TMP, "keys"), INGEST_KEY="test", OTP="",
                  BRANCHES_FILE=os.path.join(TMP, "none.json"))
os.makedirs(os.environ["DATA_DIR"])
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server"))
import webhook as w  # noqa: E402
from board import db, devices, settings, stores  # noqa: E402

PEOPLE = {"Ann": (0, 1, 0), "Ben": (1, 1, 0), "Cat": (2, 0, 1)}


def send(name, waiting, working):
    i = PEOPLE[name][0]
    now = time.time()
    devices.save_ingest(devices.clean_payload({"v": 1, "device": "device-fake%d" % i, "name": name, "account": "p%d@example.com" % i, "lanIp": "10.0.0.%d" % (i + 2),
                                   "updatedAt": int(now * 1000), "openSessions": 1, "waiting": waiting, "working": working}, now), now)


for person, (_, waiting, working) in PEOPLE.items():
    send(person, waiting, working)


def command(line):
    parts = line.split()
    if not parts:
        return "?"
    if parts[0] == "approve":
        for code, r in list(stores.TV_PAIRING.pending.items()):
            if not r["name"]:
                stores.TV_PAIRING.approve(code, "Test laptop", "adm", time.time())
                return "approved " + r.get("kind", "")
        return "none"
    if parts[0] == "revoke":
        ids = [x["id"] for x in stores.TV.list_screens(time.time()) if x["kind"] == settings.KIND_EXTENSION]
        for tv_id in ids:
            stores.AUDIT_LOG.write(action="tv-revoke", tv=stores.TV.revoke(tv_id), id=tv_id, kind=settings.KIND_EXTENSION)
        return "revoked %d" % len(ids)
    if parts[0] in ("wait", "stop"):
        send(parts[1], 1 if parts[0] == "wait" else 0, 0)
        return "ok"
    if parts[0] == "audit":
        rows = [json.loads(b) for (b,) in db.data_db().rows("SELECT body FROM audit ORDER BY id")]
        return " ".join(x["action"] + ":" + x.get("kind", "") for x in rows)
    return "?"


server = w.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 0), w.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print("ready on %d" % server.server_address[1], flush=True)
for line in sys.stdin:
    print(command(line.strip()), flush=True)
