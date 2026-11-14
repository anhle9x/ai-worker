#!/usr/bin/env python3
"""Try the board on your own computer, with sample people: python3 server/demo.py [--port 8799]  (Windows: py server\\demo.py)

Starts the real board server on 127.0.0.1 with 12 made-up people in 4 offices, prints the address, the account name and
the 6-digit code to log in with. Needs only Python 3.8+: no server, no install, no account anywhere.

Everything lives in a temporary folder that is deleted when the demo stops. It never reads or writes the data of a real
board, it listens only inside this computer, and it sends nothing out.

  Thử bảng ngay trên máy mình, với dữ liệu giả lập: python3 server/demo.py [--port 8799]  (Windows: py server\\demo.py)

  Bật đúng máy chủ bảng tổng trên 127.0.0.1 với 12 nhân viên giả lập ở 4 văn phòng, in ra địa chỉ, tên tài khoản và mã 6 số để
  đăng nhập. Chỉ cần Python 3.8+: không cần máy chủ, không cài gì, không cần tài khoản ở đâu.

  Mọi thứ nằm trong một thư mục tạm, xoá khi bản thử dừng. Bản thử không bao giờ đọc hay ghi dữ liệu của bảng thật,
  chỉ nghe bên trong máy này, và không gửi gì ra ngoài.
"""
import argparse
import base64
import json
import os
import random
import shutil
import signal
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNT = "demo"
DEFAULT_PORT = 8799
REFRESH_SECONDS = 20
# settings of a real board that must not leak into the demo when it is started from a shell that has them
# cấu hình của bảng thật không được lọt vào bản thử khi chạy từ một cửa sổ lệnh đang có sẵn chúng
REAL_SETTINGS = ("OTP_WALL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_NAME", "TRUST_PROXY", "MENUBAR_ICON_DIR", "MENUBAR_MAC_APP", "MAX_CONNECTIONS", "OTP_LABEL")

OFFICES = (("hcm", "Head office", 10.78, 106.70), ("hn", "Hanoi", 21.03, 105.85), ("dn", "Da Nang", 16.05, 108.20), ("ct", "Can Tho", 10.03, 105.78))
# name, office, state, model, minutes already waiting, 5-hour quota %, 7-day quota %
# tên, văn phòng, trạng thái, mô hình, số phút đã chờ, % hạn mức 5 giờ, % hạn mức 7 ngày
PEOPLE = (
    ("An", "hcm", "working", "claude-fable-5-2", 0, 22, 31),
    ("Bình", "hcm", "working", "claude-opus-5-5", 0, 41, 52),  # i18n-allow
    ("Chi", "hcm", "waiting", "claude-sonnet-5-5", 12, 58, 44),
    ("Dũng", "hcm", "working", "claude-fable-5-2", 0, 87, 68),  # i18n-allow
    ("Giang", "hcm", "idle", "claude-sonnet-5-5", 0, 12, 20),
    ("Hà", "hn", "working", "claude-opus-5-5", 0, 64, 59),  # i18n-allow
    ("Khoa", "hn", "waiting", "claude-fable-5-2", 4, 35, 27),
    ("Lan", "hn", "idle", "claude-sonnet-5-5", 0, 9, 14),
    ("Minh", "dn", "working", "claude-sonnet-5-5", 0, 73, 80),
    ("Nga", "dn", "waiting", "claude-opus-5-5", 27, 96, 71),
    ("Phúc", "ct", "working", "claude-fable-5-2", 0, 48, 39),  # i18n-allow
    ("Quỳnh", "ct", "offline", "claude-sonnet-5-5", 0, 5, 11),  # i18n-allow
)


def email_of(i: int) -> str:
    return "person%02d@example.com" % (i + 1)


def sample_branches() -> dict:
    """The four offices in the shape of the branches file, each with the emails of its sample people.
    Bốn văn phòng theo đúng dạng file chi nhánh, mỗi nơi kèm email của các nhân viên giả lập ở đó."""
    return {"branches": [{"id": key, "name": name, "lat": lat, "lon": lon, "isHq": key == "hcm", "ip": [],
                          "people": [email_of(i) for i, p in enumerate(PEOPLE) if p[1] == key]} for key, name, lat, lon in OFFICES]}


def sample_reports(now: float, plugin_version: str = "1.0.0", seed: int = 7) -> list:
    """One report per sample person, in the shape a real computer sends: the last 30 hours of cost, tasks handed to the
    helper assistants, quota, and what the person is doing now. The same seed gives the same numbers.
    Mỗi nhân viên giả lập một bản báo cáo, đúng dạng một máy thật gửi: chi phí 30 giờ qua, việc đã giao cho trợ lý phụ,
    hạn mức, và người đó đang làm gì. Cùng seed thì ra cùng số liệu."""
    rnd = random.Random(seed)
    hour = int(now // 3600)
    reports = []
    for i, (name, office, state, model, _minutes, five_hour, seven_day) in enumerate(PEOPLE):
        busy = 0.4 + (i * 37 % 10) / 8.0
        ledger, tasks = {}, {}
        for back in range(30):
            hour_of_day = time.localtime((hour - back) * 3600).tm_hour
            office_hours = 1.0 if 8 <= hour_of_day <= 18 else (0.25 if 19 <= hour_of_day <= 22 else 0.03)
            if rnd.random() < 0.15 + 0.8 * office_hours:
                usd = round(busy * office_hours * rnd.uniform(0.4, 3.2), 2)
                ledger[str(hour - back)] = {"usd": usd, "input": int(usd * 9000), "output": int(usd * 1700), "cacheRead": int(usd * 240000), "cacheWrite": int(usd * 21000)}
                if rnd.random() < 0.55:
                    tasks[str(hour - back)] = {"gemini": rnd.randint(0, 3), "chatgpt": rnd.randint(0, 2), "gemma": rnd.randint(0, 4)}
        last_seen = now - 26 * 3600 if state == "offline" else now
        reports.append({
            "v": 1, "device": "device-demo%02d" % i, "name": name, "account": email_of(i), "updatedAt": int(last_seen * 1000),
            "openSessions": 0 if state == "offline" else rnd.randint(1, 3), "working": 1 if state == "working" else 0, "waiting": 1 if state == "waiting" else 0,
            "models": {model: rnd.randint(2, 9)}, "ledger": ledger, "tasks": tasks,
            # one person is a version behind, so the board shows how an old plugin looks
            # một người chậm một phiên bản, để bảng cho thấy plugin cũ hiện ra sao
            "pluginVersion": "0.9.0" if i == 7 else plugin_version,
            "lanIp": "192.168.%d.%d" % ([o[0] for o in OFFICES].index(office) + 1, 20 + i),
            "delegating": {"gemini": 1} if i in (0, 5) else ({"gemma": 1} if i == 3 else ({"chatgpt": 1} if i == 8 else {})),
            "subagents": {"Explore": 1} if i in (1, 10) else {},
            "assistants": {"chatgpt": i % 2 == 0, "gemini": i % 3 != 1, "gemma": "gemma4:26b" if i % 4 != 2 else ""},
            "quota": {"readAt": int(now * 1000), "windows": [{"kind": "five_hour", "pct": five_hour, "resetsAt": int((now + 3600 * 2.5) * 1000)},
                                                              {"kind": "seven_day", "pct": seven_day, "resetsAt": int((now + 86400 * 3) * 1000)}]},
        })
    return reports


def refresh_reports(reports: list, now: float, rnd: random.Random) -> None:
    """Move the sample forward one step, as if every computer had just sent again: people who are online are seen now,
    working people spend a little, and now and then one person changes between working, waiting and idle.
    Đưa dữ liệu mẫu đi tiếp một bước, như thể mọi máy vừa gửi lại: người đang trực tuyến được thấy ngay lúc này,
    người đang làm tiêu thêm một chút, và thỉnh thoảng một người đổi giữa đang làm, đang chờ và rảnh."""
    hour = str(int(now // 3600))
    online = [r for r in reports if r["openSessions"] > 0]
    for r in online:
        r["updatedAt"] = int(now * 1000)
        r["quota"]["readAt"] = int(now * 1000)
        if r["working"]:
            spent = r["ledger"].setdefault(hour, {"usd": 0, "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0})
            usd = round(rnd.uniform(0.01, 0.06), 2)
            spent.update(usd=round(spent["usd"] + usd, 2), input=spent["input"] + int(usd * 9000), output=spent["output"] + int(usd * 1700),
                         cacheRead=spent["cacheRead"] + int(usd * 240000), cacheWrite=spent["cacheWrite"] + int(usd * 21000))
    if online and rnd.random() < 0.3:
        r = rnd.choice(online)
        state = rnd.choice(("working", "waiting", "idle"))
        r["working"], r["waiting"] = (1 if state == "working" else 0), (1 if state == "waiting" else 0)


def plugin_version() -> str:
    """The version of this checkout, so the sample people run the same plugin as the code being tried.
    Phiên bản của bản mã này, để nhân viên giả lập chạy cùng plugin với bản mã đang được thử."""
    try:
        with open(os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return str(json.load(f)["version"])
    except (OSError, ValueError, KeyError):
        return "1.0.0"


def show_codes(secret: bytes, totp_code, stop: threading.Event) -> None:
    """Keep the current login code on screen: one line that updates in a terminal, one new line per code elsewhere.
    Giữ mã đăng nhập hiện tại trên màn hình: một dòng tự cập nhật trong cửa sổ lệnh, nơi khác thì mỗi mã một dòng mới."""
    live = sys.stdout.isatty()
    shown = None
    while not stop.is_set():
        now = time.time()
        step = int(now // 30)
        if live:
            sys.stdout.write("\rCode      %s   (next code in %2d s) " % (totp_code(secret, step), 30 - int(now % 30)))
            sys.stdout.flush()
        elif step != shown:
            print("Code      %s" % totp_code(secret, step), flush=True)
        shown = step
        stop.wait(1)


def close_databases() -> None:
    """Close the demo's two databases before its folder is removed: Windows will not delete a file that is still open.
    Each lock is taken and kept, so a worker thread waits instead of using a closed database in the moment before the program ends.
    Đóng hai cơ sở dữ liệu của bản thử trước khi xoá thư mục của nó: Windows không xoá file còn đang mở.
    Mỗi khoá được lấy và giữ luôn, để luồng phụ đứng chờ thay vì dùng cơ sở dữ liệu đã đóng trong khoảnh khắc trước khi chương trình kết thúc."""
    opened = getattr(sys.modules.get("board.db"), "_OPEN", {})
    for database in list(opened.values()):
        database.lock.acquire()
        database.conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Try the AI Worker board on this computer with sample people. Nothing is sent out.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port on 127.0.0.1 (default %d; 0 picks a free one)" % DEFAULT_PORT)
    args = parser.parse_args(argv)

    def stop_like_ctrl_c(*_):
        raise KeyboardInterrupt

    # a plain "kill" or a closed terminal window ends the demo the same way as Ctrl+C, so the temporary folder is always removed
    # lệnh "kill" thường hay việc đóng cửa sổ lệnh cũng kết thúc bản thử như Ctrl+C, để thư mục tạm luôn được xoá
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_like_ctrl_c)
    os.umask(0o077)
    folder = tempfile.mkdtemp(prefix="ai-worker-demo-")
    stop = threading.Event()
    try:
        secret = os.urandom(20)
        branches_file = os.path.join(folder, "branches.json")
        with open(branches_file, "w", encoding="utf-8") as f:
            json.dump(sample_branches(), f)
        for name in REAL_SETTINGS:
            os.environ.pop(name, None)
        # every path and key is set here, before the server code is loaded, so the demo cannot touch a real board's files
        # mọi đường dẫn và khoá đặt ở đây, trước khi nạp mã máy chủ, để bản thử không thể đụng vào file của bảng thật
        os.environ.update(
            BIND_ADDR="127.0.0.1", PORT=str(args.port), DATA_DIR=os.path.join(folder, "data"), KEYS_DIR=os.path.join(folder, "keys"),
            RELEASES_DIR=os.path.join(folder, "releases"), BRANCHES_FILE=branches_file, INGEST_KEY=base64.b32encode(os.urandom(20)).decode(),
            OTP="%s:%s" % (ACCOUNT, base64.b32encode(secret).decode()), OTP_ADMINS=ACCOUNT)
        for name in ("DATA_DIR", "KEYS_DIR", "RELEASES_DIR"):
            os.makedirs(os.environ[name])
        sys.path.insert(0, HERE)
        import webhook as w
        from board import devices, security, stores

        w.ACCOUNTS.import_from_env()
        now = time.time()
        reports = sample_reports(now, plugin_version())
        waiting_since = {r["account"] + "|" + r["name"]: int((now - p[4] * 60) * 1000) for r, p in zip(reports, PEOPLE) if p[2] == "waiting"}

        def send_all(at: float) -> None:
            for r in reports:
                devices.save_ingest(devices.clean_payload(r, at), at)

        send_all(now)
        # the people who start out waiting have already waited a while, so the board has waiting times to show
        # những người lúc đầu đang chờ đã chờ sẵn một lúc, để bảng có thời gian chờ mà hiện
        stores.WAIT_TRACKER.since.update(waiting_since)

        def keep_alive() -> None:
            rnd = random.Random(11)
            while not stop.wait(REFRESH_SECONDS):
                at = time.time()
                refresh_reports(reports, at, rnd)
                send_all(at)

        server = w.LimitedServer(("127.0.0.1", args.port), w.Handler)
        print("AI Worker demo: %d sample people in %d offices. Nothing leaves this computer." % (len(PEOPLE), len(OFFICES)))
        print("Open      http://127.0.0.1:%d" % server.server_address[1])
        print("Account   %s" % ACCOUNT)
        print("Stop      Ctrl+C (the sample data is deleted)", flush=True)
        for target in (w.history_loop, keep_alive, lambda: show_codes(secret, security.totp_code, stop)):
            threading.Thread(target=target, daemon=True).start()
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        close_databases()
        shutil.rmtree(folder, ignore_errors=True)
        if os.path.exists(folder):
            print("\nDemo stopped. The sample data could not be deleted: remove the folder %s yourself." % folder, flush=True)
        else:
            print("\nDemo stopped, sample data deleted.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
