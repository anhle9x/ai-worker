#!/usr/bin/env python3
"""Load test and benchmark of the board server: python3 tests/load/load_test.py [--quick] [--seconds 60] [--json out.json]
  Đo chịu tải và benchmark máy chủ bảng: python3 tests/load/load_test.py [--quick] [--seconds 60] [--json out.json]

  Starts the real server (server/webhook.py) on 127.0.0.1 in a temporary folder, as its own process, then plays computers that send
  their numbers and people who keep the board open, and measures how long each answer takes, how many fail, and how much CPU and memory
  the server uses. It never talks to any other address, so it cannot be pointed at a real board by mistake. Needs only Python 3.8+.
  Bật đúng máy chủ thật (server/webhook.py) trên 127.0.0.1 trong một thư mục tạm, chạy thành tiến trình riêng, rồi đóng vai các máy gửi
  số và những người đang mở bảng, đo mỗi câu trả lời mất bao lâu, bao nhiêu lần lỗi, và máy chủ tốn bao nhiêu CPU và bộ nhớ.
  Nó không bao giờ nói chuyện với địa chỉ nào khác, nên không thể lỡ trỏ vào bảng thật. Chỉ cần Python 3.8+.

  Kinds of run / Các kiểu chạy:
  office  every computer sends every 10 seconds (three times the most the plugin did when this was written) or every 60 seconds (an ordinary day), and every open board reads every
          10 seconds, at 20, 50, 150 and 300 computers by default (--levels for more)
          mỗi máy gửi mỗi 10 giây (gấp ba mức nhiều nhất của plugin lúc viết bài đo) hoặc mỗi 60 giây (ngày thường), và mỗi bảng đang mở đọc mỗi 10 giây,
          mặc định ở 20, 50, 150 và 300 máy (--levels để nhiều hơn)
  scale   past 300 computers (--scale), the time one send and one read take, from the server's own code in this process
          vượt 300 máy (--scale), thời gian một lần gửi và một lần đọc mất, từ chính mã của máy chủ trong tiến trình này
  ceiling --ceiling: the HTTP layer alone (/health), sends and reads, with more and more clients, to find what one server process answers
          --ceiling: riêng tầng HTTP (/health), lần gửi và lần đọc, với số client tăng dần, để tìm một tiến trình máy chủ trả lời được bao nhiêu
  The load comes from --processes separate processes, each playing many computers from a pool of threads.
  Tải đến từ --processes tiến trình riêng, mỗi tiến trình đóng vai nhiều máy từ một nhóm luồng.
  stress  with 300 computers known, a fixed number of clients send, or read, again as soon as they get an answer, to find the ceiling
          khi đã có 300 máy, một số client cố định gửi, hoặc đọc, lại ngay khi nhận câu trả lời, để tìm mức trần
"""
import argparse
import base64
import concurrent.futures
import heapq
import multiprocessing
import queue
import hashlib
import hmac
import http.client
import json
import os
import random
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_DIR = os.path.join(ROOT, "server")
sys.path.insert(0, SERVER_DIR)
# the sample hours of the demo give each computer a ledger of real size
# giờ mẫu của bản thử cho mỗi máy một sổ theo giờ đúng cỡ thật
import demo  # noqa: E402

ACCOUNT = "loadtest"
# the board in the browser asked for new numbers every 10 seconds when this test was written; on screen it now asks every second
# (server/static/page.js), and the runs keep 10 seconds so their numbers can be compared with docs/BENCHMARK.md
# bảng trên trình duyệt hỏi số mới mỗi 10 giây lúc bài đo này được viết; nay khi đang hiện trên màn hình nó hỏi mỗi giây
# (server/static/page.js), và các lượt chạy giữ 10 giây để số đo so được với docs/BENCHMARK.vi.md
VIEW_SECONDS = 10
# seconds a closed connection holds its local port (TIME_WAIT is twice the longest a packet may live: 30 s on macOS, 60 s on Linux)
# số giây một kết nối đã đóng còn giữ cổng cục bộ (TIME_WAIT gấp đôi thời gian sống lâu nhất của gói tin: 30 giây trên macOS, 60 giây trên Linux)
PORT_REST_SECONDS = 65
# when this test was written the plugin sent from its heartbeat, at most every 30 seconds: every 10 seconds was three times that,
# for headroom, every 60 seconds an ordinary day. The plugin now sends a second after a change, at most once every 2 seconds
# (hooks/team.ts), and the runs keep these paces so their numbers can be compared with docs/BENCHMARK.md
# lúc bài đo này được viết, plugin gửi theo nhịp tim, nhiều nhất 30 giây một lần: mỗi 10 giây là gấp ba mức đó, để có biên,
# mỗi 60 giây là ngày thường. Nay plugin gửi một giây sau một thay đổi, nhiều nhất 2 giây một lần (hooks/team.ts), và các lượt
# chạy giữ các nhịp này để số đo so được với docs/BENCHMARK.vi.md
SEND_SECONDS = (10, 60)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def totp(secret: bytes, now: float) -> str:
    """The 6-digit code an authenticator app would show now (RFC 6238).
    Mã 6 số mà ứng dụng xác thực sẽ hiện lúc này (RFC 6238)."""
    h = hmac.new(secret, struct.pack(">Q", int(now // 30)), hashlib.sha1).digest()
    o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def machine_ip(i: int) -> str:
    """A made-up address in 10.0.0.0/8 for computer i: the server sees it as the address Caddy passed on, so each computer counts on its own.
    Một địa chỉ bịa trong 10.0.0.0/8 cho máy i: máy chủ coi đó là địa chỉ Caddy chuyển tới, nên mỗi máy được đếm riêng."""
    return "10.%d.%d.%d" % (1 + i // 65025, (i // 255) % 255, 1 + i % 255)


def machine_report(i: int, now: float, rnd: random.Random) -> dict:
    """What one computer sends, in the same shape and size as the plugin: 8 days of cost per hour, quota, what the person is doing.
    Thứ một máy gửi, đúng dạng và cỡ của plugin: chi phí theo giờ của 8 ngày, hạn mức, người đó đang làm gì."""
    ledger, tasks = demo.sample_hours(rnd, int(now // 3600), demo.LEDGER_HOURS, demo.busy_of(i))
    state = rnd.choice(("working", "working", "waiting", "idle"))
    return {"v": 1, "device": "device-load%04d" % i, "name": "Person %d" % i, "account": "person%04d@example.com" % i, "updatedAt": int(now * 1000),
            "openSessions": rnd.randint(1, 3), "working": int(state == "working"), "waiting": int(state == "waiting"),
            "models": {"claude-sonnet-5-5": rnd.randint(1, 9)}, "ledger": ledger, "tasks": tasks, "pluginVersion": "1.0.0",
            "lanIp": "192.168.%d.%d" % (1 + i % 4, 20 + i % 200),
            "quota": {"readAt": int(now * 1000), "windows": [{"kind": "five_hour", "pct": rnd.randint(0, 99), "resetsAt": int((now + 9000) * 1000)},
                                                              {"kind": "seven_day", "pct": rnd.randint(0, 99), "resetsAt": int((now + 259200) * 1000)}]}}


class Server:
    """The real board server in its own process and temporary folder; removed with everything in it when stopped.
    Máy chủ bảng thật trong tiến trình và thư mục tạm riêng; dừng thì xoá cùng mọi thứ trong đó."""

    def __init__(self, unlimited: bool = False):
        """unlimited: lift the limit of sends per computer, for the runs that look for the ceiling of the server itself.
        unlimited: bỏ giới hạn số lần gửi mỗi máy, cho các lượt tìm mức trần của chính máy chủ."""
        self.folder = tempfile.mkdtemp(prefix="ai-worker-load-")
        self.port = free_port()
        self.secret = os.urandom(20)
        self.ingest_key = base64.b32encode(os.urandom(20)).decode()
        env = {k: v for k, v in os.environ.items() if k not in demo.REAL_SETTINGS and k not in ("OTP", "OTP_ADMINS", "INGEST_KEY")}
        env.update(BIND_ADDR="127.0.0.1", PORT=str(self.port), TRUST_PROXY="1", DATA_DIR=os.path.join(self.folder, "data"),
                   KEYS_DIR=os.path.join(self.folder, "keys"), RELEASES_DIR=os.path.join(self.folder, "releases"),
                   INGEST_KEY=self.ingest_key, OTP="%s:%s" % (ACCOUNT, base64.b32encode(self.secret).decode()), PYTHONUNBUFFERED="1",
                   # the test server takes as many computers as a run asks for; a real board keeps its own MAX_DEVICES
                   # máy chủ thử nhận đủ số máy một lượt cần; bảng thật giữ MAX_DEVICES của nó
                   MAX_DEVICES="200000", **({"INGEST_BURST": "1000000", "INGEST_PER_SECOND": "1000000"} if unlimited else {}))
        for name in ("DATA_DIR", "KEYS_DIR", "RELEASES_DIR"):
            os.makedirs(env[name])
        self.log = open(os.path.join(self.folder, "server.log"), "w")
        self.proc = subprocess.Popen([sys.executable, os.path.join(SERVER_DIR, "webhook.py")], cwd=SERVER_DIR, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if request(self.port, "GET", "/health")[0] == 200:
                    return
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise SystemExit("The server did not start; see its log above.")

    def cpu_seconds(self) -> float:
        """CPU time the server process has used so far, from ps (works on macOS and Linux).
        Thời gian CPU tiến trình máy chủ đã dùng tới giờ, lấy từ ps (chạy được trên macOS và Linux)."""
        out = subprocess.run(["ps", "-o", "time=", "-p", str(self.proc.pid)], capture_output=True, text=True).stdout.strip()
        days, _, clock = out.rpartition("-")
        total = 0.0
        for part in clock.split(":"):
            total = total * 60 + float(part)
        return total + (int(days) * 86400 if days else 0)

    def rss_mb(self) -> float:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(self.proc.pid)], capture_output=True, text=True).stdout.strip()
        return int(out or 0) / 1024.0

    def data_mb(self) -> float:
        folder = os.path.join(self.folder, "data")
        return sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)) / 1048576.0

    def login(self) -> str:
        """Log in once as a view-only account, the way the login form does; every reader shares the session.
        Đăng nhập một lần bằng tài khoản chỉ xem, đúng như form đăng nhập; mọi người đọc dùng chung phiên."""
        body = urlencode({"account": ACCOUNT, "code": totp(self.secret, time.time())}).encode()
        status, headers, _ = request(self.port, "POST", "/login", body, {"Content-Type": "application/x-www-form-urlencoded"})
        cookie = headers.get("set-cookie", "").split(";", 1)[0]
        if status != 303 or not cookie.startswith("session="):
            raise SystemExit("Login failed (%s)." % status)
        return cookie

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()
        shutil.rmtree(self.folder, ignore_errors=True)


def request(port: int, method: str, path: str, body: bytes = b"", headers: dict = None):
    """One request on a new connection, as the plugin and the browser behind Caddy make them. Returns (status, headers, body length).
    Một yêu cầu trên một kết nối mới, như plugin và trình duyệt sau Caddy gửi. Trả về (mã, header, độ dài nội dung)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request(method, path, body or None, headers or {})
        r = conn.getresponse()
        data = r.read()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, len(data)
    finally:
        conn.close()


class Tally:
    """Times and outcomes of every request of one kind, kept under a lock because many threads add to it.
    Thời gian và kết quả của mọi yêu cầu cùng loại, giữ dưới khoá vì nhiều luồng cùng ghi vào."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ms, self.errors, self.statuses, self.late, self.bytes = [], 0, {}, 0, 0

    def add(self, ms: float, status, size: int = 0) -> None:
        with self.lock:
            self.ms.append(ms)
            self.bytes += size
            self.statuses[status] = self.statuses.get(status, 0) + 1
            if status not in (200, 303):
                self.errors += 1

    def merge(self, part: dict) -> None:
        """Add what one load process measured (see _run_plan) to this tally.
        Cộng thứ một tiến trình phát tải đã đo (xem _run_plan) vào bảng đếm này."""
        with self.lock:
            self.ms.extend(part["ms"])
            self.bytes += part["bytes"]
            self.late += part["late"]
            for status, n in part["statuses"].items():
                status = int(status) if str(status).isdigit() else status
                self.statuses[status] = self.statuses.get(status, 0) + n
                if status not in (200, 303):
                    self.errors += n

    def summary(self, seconds: float, sent: list = None) -> dict:
        """sent: the bodies the computers send, whose size is shown instead of the size of the short answer.
        sent: nội dung các máy gửi, hiện cỡ của chúng thay cho cỡ của câu trả lời ngắn."""
        ms = sorted(self.ms)
        n = len(ms)

        def pct(p):
            # nearest-rank percentile, the same rule the AI cost report uses
            # phân vị nearest-rank, cùng quy tắc với báo cáo chi phí AI
            return round(ms[max(0, min(n - 1, int(-(-p * n // 100)) - 1))], 1) if n else None

        return {"requests": n, "perSecond": round(n / seconds, 1) if seconds else 0, "errors": self.errors,
                "errorPct": round(100.0 * self.errors / n, 2) if n else 0, "statuses": {str(k): v for k, v in sorted(self.statuses.items(), key=str)},
                "p50": pct(50), "p95": pct(95), "p99": pct(99), "max": round(ms[-1], 1) if n else None,
                "mean": round(statistics.mean(ms), 1) if n else None, "late": self.late, "avgKB": round(sum(map(len, sent)) / len(sent) / 1024, 1) if sent else (round(self.bytes / n / 1024, 1) if n else 0)}


def timed(tally: Tally, port: int, method: str, path: str, body: bytes, headers: dict) -> None:
    started = time.perf_counter()
    try:
        status, _, size = request(port, method, path, body, headers)
    except OSError as e:
        status, size = type(e).__name__, 0
    tally.add((time.perf_counter() - started) * 1000, status, size)


def warm_up(server: Server, machines: int, rnd: random.Random) -> list:
    """Every computer sends once, so the server knows them all; returns the body each one sends from then on.
    Mỗi máy gửi một lần để máy chủ biết hết; trả về nội dung mỗi máy sẽ gửi từ đó về sau."""
    now = time.time()
    bodies = [json.dumps(machine_report(i, now, rnd)).encode() for i in range(machines)]

    # each computer enrols with the shared key and gets a key of its own, used for every send after this one, as the plugin does
    # mỗi máy ghi danh bằng khoá chung và nhận khoá riêng, dùng cho mọi lần gửi sau lần này, như plugin làm
    server.keys = [""] * machines

    def join(i):
        for _ in range(20):
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
            try:
                conn.request("POST", "/ingest", bodies[i], ingest_headers(server, machine_ip(i)))
                r = conn.getresponse()
                status, answer = r.status, r.read()
            finally:
                conn.close()
            if status == 200:
                server.keys[i] = json.loads(answer or b"{}").get("deviceKey", "")
            # a busy server says so with 503: wait a moment and send again, as the plugin does at its next round
            # máy chủ bận thì báo 503: chờ một chút rồi gửi lại, như plugin làm ở vòng sau
            if status != 503:
                break
            time.sleep(0.2)
        if status != 200:
            raise SystemExit("Computer %d could not join (%s)." % (i, status))

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        list(pool.map(join, range(machines)))
    return bodies


def ingest_headers(server: Server, ip: str, i: int = -1) -> dict:
    """The headers of a send: computer i's own key once it has one, else the shared key.
    Header của một lần gửi: khoá riêng của máy i khi đã có, nếu không thì khoá chung."""
    keys = getattr(server, "keys", [])
    key = keys[i] if 0 <= i < len(keys) and keys[i] else server.ingest_key
    return {"Content-Type": "application/json", "Authorization": "Bearer " + key, "X-Forwarded-For": ip}


def _empty_part() -> dict:
    return {"ms": [], "statuses": {}, "late": 0, "bytes": 0}


def _timed_into(part: dict, lock, port: int, method: str, path: str, body: bytes, headers: dict) -> float:
    started = time.perf_counter()
    try:
        status, _, size = request(port, method, path, body, headers)
    except OSError as e:
        status, size = type(e).__name__, 0
    done = time.perf_counter()
    with lock:
        part["ms"].append((done - started) * 1000)
        part["bytes"] += size
        part["statuses"][str(status)] = part["statuses"].get(str(status), 0) + 1
    return done


def _run_plan(job: dict) -> dict:
    """One load process: each item (a computer or an open board) asks on its own clock, from a pool of threads, so one process plays
    thousands of computers without a thread for each. Runs in a separate process, so the load does not share one Python with the test.
    Một tiến trình phát tải: mỗi mục (một máy hay một bảng đang mở) hỏi theo nhịp riêng, từ một nhóm luồng, nên một tiến trình đóng vai
    hàng nghìn máy mà không cần mỗi máy một luồng. Chạy trong tiến trình riêng, để tải không dùng chung một Python với bài đo."""
    parts = {"send": _empty_part(), "read": _empty_part()}
    lock = threading.Lock()
    work = queue.Queue()
    stop_at = time.perf_counter() + job["seconds"]
    items = job["items"]
    due = [(time.perf_counter() + item["offset"], n) for n, item in enumerate(items)]
    heapq.heapify(due)

    def worker():
        while True:
            task = work.get()
            if task is None:
                return
            at, item = task
            done = _timed_into(parts[item["kind"]], lock, job["port"], item["method"], item["path"], item["body"], item["headers"])
            # an answer that came after the item's next turn: a real computer would have been late too
            # câu trả lời tới sau lượt kế tiếp của mục đó: máy thật cũng sẽ bị trễ
            if done > at + item["every"]:
                with lock:
                    parts[item["kind"]]["late"] += 1

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(job["threads"])]
    for t in threads:
        t.start()
    while due and due[0][0] < stop_at:
        at, n = heapq.heappop(due)
        wait = at - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        work.put((at, items[n]))
        heapq.heappush(due, (at + items[n]["every"], n))
    for _ in threads:
        work.put(None)
    for t in threads:
        t.join()
    return parts


def _hammer(job: dict) -> dict:
    """One load process for the ceiling: its clients ask again as soon as they get an answer.
    Một tiến trình phát tải cho mức trần: các client của nó hỏi lại ngay khi có câu trả lời."""
    part, lock = _empty_part(), threading.Lock()
    stop_at = time.perf_counter() + job["seconds"]
    counter, counter_lock = [job["first"]], threading.Lock()

    def client():
        while time.perf_counter() < stop_at:
            with counter_lock:
                counter[0] += 1
                n = counter[0]
            if job["what"] == "send":
                i = n % len(job["bodies"])
                headers = dict(job["headers"], **{"X-Forwarded-For": machine_ip(n), "Authorization": "Bearer " + job["keys"][i]})
                _timed_into(part, lock, job["port"], "POST", "/ingest", job["bodies"][i], headers)
            elif job["what"] == "read":
                _timed_into(part, lock, job["port"], "GET", "/data?ui=1", b"", job["headers"])
            else:
                _timed_into(part, lock, job["port"], "GET", "/health", b"", {})

    threads = [threading.Thread(target=client, daemon=True) for _ in range(job["clients"])]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return part


def _in_processes(server: Server, fn, jobs: list) -> tuple:
    """Run the jobs in their own processes while sampling the server's CPU and memory; returns (results, seconds, CPU %, peak MB).
    Chạy các việc trong tiến trình riêng trong lúc lấy mẫu CPU và bộ nhớ của máy chủ; trả về (kết quả, số giây, % CPU, MB cao nhất)."""
    cpu0, t0, rss = server.cpu_seconds(), time.perf_counter(), [server.rss_mb()]
    with concurrent.futures.ProcessPoolExecutor(len(jobs), mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(fn, job) for job in jobs]
        while not all(f.done() for f in futures):
            rss.append(server.rss_mb())
            time.sleep(1)
        results = [f.result() for f in futures]
    wall = time.perf_counter() - t0
    return results, wall, round(100 * (server.cpu_seconds() - cpu0) / wall, 1), round(max(rss), 1)


def run_office(server: Server, cookie: str, machines: int, viewers: int, every: float, seconds: float, rnd: random.Random, processes: int) -> dict:
    """A day at the office: each computer and each open board on its own clock, starting at a random moment so they do not all ask at once,
    spread over several load processes.
    Một ngày ở văn phòng: mỗi máy và mỗi bảng đang mở chạy theo nhịp riêng, bắt đầu ở một lúc ngẫu nhiên để không cùng hỏi một lúc,
    chia cho nhiều tiến trình phát tải."""
    bodies = warm_up(server, machines, rnd)
    items = [{"kind": "send", "method": "POST", "path": "/ingest", "body": bodies[i], "headers": ingest_headers(server, machine_ip(i), i),
              "every": every, "offset": rnd.uniform(0, every)} for i in range(machines)]
    items += [{"kind": "read", "method": "GET", "path": "/data?ui=1", "body": b"", "headers": {"Cookie": cookie},
               "every": VIEW_SECONDS, "offset": rnd.uniform(0, VIEW_SECONDS)} for _ in range(viewers)]
    rnd.shuffle(items)
    processes = max(1, min(processes, len(items)))
    jobs = [{"port": server.port, "items": items[n::processes], "seconds": seconds, "threads": 32} for n in range(processes)]
    parts, wall, cpu, rss = _in_processes(server, _run_plan, jobs)
    sends, reads = Tally(), Tally()
    for part in parts:
        sends.merge(part["send"])
        reads.merge(part["read"])
    return {"kind": "office every %ds" % every, "machines": machines, "viewers": viewers, "seconds": round(wall, 1), "send": sends.summary(wall, bodies),
            "read": reads.summary(wall), "cpuPct": cpu, "rssMB": rss, "dataMB": round(server.data_mb(), 1)}


def run_stress(server: Server, cookie: str, what: str, clients: int, seconds: float, bodies: list, processes: int = 1) -> dict:
    """Clients that ask again as soon as they get an answer, spread over several processes: the answers per second are the ceiling.
    what is send, read, or health (the HTTP layer alone, with nothing of the board behind it). Each send comes from a different made-up
    address, so the limit of sends per address does not hide the ceiling.
    Các client hỏi lại ngay khi có câu trả lời, chia cho nhiều tiến trình: số câu trả lời mỗi giây là mức trần.
    what là send, read, hay health (chỉ tầng HTTP, không có gì của bảng phía sau). Mỗi lần gửi đến từ một địa chỉ bịa khác,
    để giới hạn số lần gửi theo địa chỉ không che mất mức trần."""
    headers = ingest_headers(server, "") if what == "send" else {"Cookie": cookie}
    jobs = [{"port": server.port, "what": what, "clients": max(1, clients // processes), "seconds": seconds, "headers": headers,
             "bodies": bodies if what == "send" else [], "keys": getattr(server, "keys", []) if what == "send" else [],
             "first": 10 ** 6 * (n + 1)} for n in range(processes)]
    parts, wall, cpu, rss = _in_processes(server, _hammer, jobs)
    tally = Tally()
    for part in parts:
        tally.merge(part)
    return {"kind": "stress-" + what, "machines": len(bodies), "clients": clients, "processes": processes, "seconds": round(wall, 1),
            what: tally.summary(wall, bodies if what == "send" else None), "cpuPct": cpu, "rssMB": rss}


def run_scale(sizes: list) -> list:
    """Past the server's 300 computers: the time one send and one board read take as the number of known computers grows, measured
    by calling the server's own code in this process, since the server refuses computer 301 over HTTP.
    Vượt 300 máy của máy chủ: thời gian một lần gửi và một lần đọc bảng mất khi số máy đã biết tăng lên, đo bằng cách gọi đúng
    mã của máy chủ trong tiến trình này, vì máy chủ từ chối máy thứ 301 qua HTTP."""
    folder = tempfile.mkdtemp(prefix="ai-worker-scale-")
    for name in ("data", "keys", "releases"):
        os.makedirs(os.path.join(folder, name))
    for name in demo.REAL_SETTINGS:
        os.environ.pop(name, None)
    # every path is set before the server code is loaded, so this run cannot touch a real board's files
    # mọi đường dẫn đặt trước khi nạp mã máy chủ, để lượt này không thể đụng vào file của bảng thật
    os.environ.update(BIND_ADDR="127.0.0.1", DATA_DIR=os.path.join(folder, "data"), KEYS_DIR=os.path.join(folder, "keys"),
                      RELEASES_DIR=os.path.join(folder, "releases"), INGEST_KEY="x" * 32, OTP="%s:%s" % (ACCOUNT, base64.b32encode(os.urandom(20)).decode()))
    from board import devices, views
    rnd, now, have, out = random.Random(1), time.time(), 0, []
    try:
        for size in sizes:
            while have < size:
                devices.save_ingest(devices.clean_payload(machine_report(have, now, rnd), now), now)
                have += 1
            body = json.dumps(machine_report(0, now, rnd)).encode()
            rounds = 5 if size <= 1000 else 2

            def send(body=body):
                # what Handler.ingest does after the checks: read, clean, save, then the history of the person who sent
                # thứ Handler.ingest làm sau các bước kiểm: đọc, làm sạch, lưu, rồi lịch sử của người vừa gửi
                d = devices.clean_payload(json.loads(body), time.time())
                devices.save_ingest(d, time.time())
                views.record_history(devices.person_key(d))

            started = time.perf_counter()
            for _ in range(rounds):
                send()
            send_ms = (time.perf_counter() - started) / rounds * 1000
            # a build of the board, as when its kept copy is too old, and a read that finds the kept copy
            # một lần dựng bảng, như khi bản đang giữ đã quá cũ, và một lần đọc gặp bản đang giữ
            # the first build after the sends counts everyone again; the next ones count only the people who changed since
            # lần dựng đầu sau các lần gửi đếm lại mọi người; các lần sau chỉ đếm những người đã đổi từ đó
            started = time.perf_counter()
            json.dumps(views.role_view("viewer", time.time()), ensure_ascii=False)
            cold_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            for _ in range(rounds):
                json.dumps(views.role_view("viewer", time.time()), ensure_ascii=False)
            read_ms = (time.perf_counter() - started) / rounds * 1000
            os.environ["VIEW_CACHE_SECONDS"] = "60"
            views.VIEWS.json("viewer", time.time())
            started = time.perf_counter()
            for _ in range(rounds * 20):
                views.VIEWS.json("viewer", time.time())
            kept_ms = (time.perf_counter() - started) / (rounds * 20) * 1000
            os.environ.pop("VIEW_CACHE_SECONDS", None)
            # what a restart costs: every computer loaded again from the table and cleaned once; and the memory this process holds now
            # một lần khởi động lại tốn bao nhiêu: mọi máy được nạp lại từ bảng và làm sạch một lần; và bộ nhớ tiến trình này đang giữ
            devices.DEVICES.forget()
            started = time.perf_counter()
            devices.DEVICES.count()
            load_s = time.perf_counter() - started
            rss = int(subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip() or 0) / 1024.0
            out.append({"machines": size, "sendMs": round(send_ms, 2), "coldMs": round(cold_ms), "readMs": round(read_ms), "keptReadMs": round(kept_ms, 3),
                        "sendsPerSecond": round(1000 / send_ms, 1), "loadSeconds": round(load_s, 1), "rssMB": round(rss)})
            print("scale: %d computers, one send %.2f ms, first build %.0f ms, next builds %.0f ms, one kept read %.3f ms, start %.1f s, memory %d MB"
                  % (size, send_ms, cold_ms, read_ms, kept_ms, load_s, rss), flush=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return out


def table(results: list) -> str:
    rows = ["| Run | Computers | Readers or clients | Kind | Requests/s | p50 ms | p95 ms | p99 ms | Max ms | Errors | Late | Avg KB | Server CPU % | Server RAM MB |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        for kind in ("send", "read", "health"):
            s = r.get(kind)
            if not s:
                continue
            rows.append("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %d (%s%%) | %d | %s | %s | %s |" % (
                r["kind"], r["machines"], r.get("viewers", r.get("clients", 0)), kind, s["perSecond"], s["p50"], s["p95"], s["p99"], s["max"],
                s["errors"], s["errorPct"], s["late"], s["avgKB"], r["cpuPct"], r["rssMB"]))
    return "\n".join(rows)


def run_ceiling(machines: int, seconds: float, processes: int, json_path: str) -> int:
    """The most one server process answers: the HTTP layer alone (/health), sends, and reads of the board, each with more and more
    clients spread over the load processes, with this many computers known. 503 in the results is the server saying it is busy.
    Mức nhiều nhất một tiến trình máy chủ trả lời được: riêng tầng HTTP (/health), lần gửi, và lần đọc bảng, mỗi thứ với số client
    tăng dần chia cho các tiến trình phát tải, khi máy chủ đã biết chừng này máy. 503 trong kết quả là máy chủ báo đang bận."""
    print("Machine: %s" % machine_info(), flush=True)
    rnd, results = random.Random(42), []
    server = Server(unlimited=True)
    try:
        cookie = server.login()
        print("ceiling: %d computers joining ..." % machines, flush=True)
        bodies = warm_up(server, machines, rnd)
        for what in ("health", "send", "read"):
            for clients in (processes, 4 * processes, 16 * processes):
                # every request is a new connection, so thousands a second use up this computer's local ports for a while (TIME_WAIT):
                # wait for them to come back between runs, so a run measures the server and not the ports left over from the last one
                # mỗi yêu cầu là một kết nối mới, nên hàng nghìn yêu cầu mỗi giây làm cạn cổng cục bộ của máy này một lúc (TIME_WAIT):
                # chờ chúng trở lại giữa các lượt, để một lượt đo máy chủ chứ không đo số cổng lượt trước để lại
                time.sleep(PORT_REST_SECONDS)
                print("ceiling %s: %d clients in %d processes, %d s ..." % (what, clients, processes, seconds), flush=True)
                results.append(run_stress(server, cookie, what, clients, seconds, bodies, processes))
    finally:
        server.stop()
    print()
    print(table(results))
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"machine": machine_info(), "at": time.strftime("%Y-%m-%d %H:%M"), "results": results}, f, indent=2)
    return 0


def machine_info() -> str:
    import platform
    return "%s %s, %s, %d CPU, Python %s" % (platform.system(), platform.release(), platform.machine(), os.cpu_count() or 0, platform.python_version())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Load test of the AI Worker board server on this computer. Talks only to 127.0.0.1.")
    parser.add_argument("--quick", action="store_true", help="a short run to check the test itself works (about 30 seconds)")
    parser.add_argument("--seconds", type=float, default=60, help="length of each run in seconds (default 60)")
    parser.add_argument("--levels", default="20,50,150,300", help="numbers of computers for the office runs (default 20,50,150,300)")
    parser.add_argument("--processes", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)), help="load processes (default half the cores, at most 8)")
    parser.add_argument("--ceiling", action="store_true", help="only find the ceiling: the HTTP layer alone, sends and reads, with --levels' largest number of computers known")
    parser.add_argument("--scale", help="only measure one send and one read at these numbers of computers, past 300 too (for example 300,1000,3000)")
    parser.add_argument("--json", help="also write every number to this file")
    args = parser.parse_args(argv)
    if args.scale:
        print("Machine: %s" % machine_info(), flush=True)
        scale = run_scale([int(x) for x in args.scale.split(",") if x.strip()])
        print("\n| Computers | One send ms | First build ms | Next builds ms | One kept read ms | Start s | Memory MB |\n|---|---|---|---|---|---|---|")
        for r in scale:
            print("| %d | %s | %d | %d | %s | %s | %d |" % (r["machines"], r["sendMs"], r["coldMs"], r["readMs"], r["keptReadMs"], r["loadSeconds"], r["rssMB"]))
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"machine": machine_info(), "at": time.strftime("%Y-%m-%d %H:%M"), "scale": scale}, f, indent=2)
        return 0
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    if args.ceiling:
        return run_ceiling(max(levels), args.seconds, args.processes, args.json)
    seconds = args.seconds
    stress_clients = (4, 16, 32)
    if args.quick:
        levels, seconds, stress_clients = [20], 6, (4,)
    rnd = random.Random(42)
    results = []
    print("Machine: %s" % machine_info(), flush=True)
    for every in ((10,) if args.quick else SEND_SECONDS):
        for machines in levels:
            # each office run gets a fresh server, so the numbers of one do not weigh on the next;
            # a run lasts at least two rounds of sending, so every computer sends at least twice
            # mỗi lượt office có máy chủ mới, để số của lượt này không đè lên lượt sau;
            # một lượt dài ít nhất hai vòng gửi, để máy nào cũng gửi ít nhất hai lần
            server = Server()
            try:
                cookie = server.login()
                viewers = max(5, machines // 10)
                length = seconds if args.quick else max(seconds, 2 * every)
                print("office: %d computers sending every %d s, %d open boards, %d s ..." % (machines, every, viewers, length), flush=True)
                results.append(run_office(server, cookie, machines, viewers, every, length, rnd, args.processes))
            finally:
                server.stop()
    server = Server(unlimited=True)
    try:
        cookie = server.login()
        bodies = warm_up(server, max(levels), rnd)
        for what in ("send", "read"):
            for clients in stress_clients:
                print("stress %s: %d clients, %d s ..." % (what, clients, seconds / 2), flush=True)
                results.append(run_stress(server, cookie, what, clients, seconds / 2, bodies, min(args.processes, clients)))
    finally:
        server.stop()
    print()
    print(table(results))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"machine": machine_info(), "at": time.strftime("%Y-%m-%d %H:%M"), "sendSeconds": list(SEND_SECONDS), "viewSeconds": VIEW_SECONDS,
                       "results": results}, f, indent=2)
    failed = [r for r in results if r["kind"].startswith("office") and (r["send"]["errors"] or r["read"]["errors"])]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
