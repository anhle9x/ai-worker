#!/usr/bin/env python3
"""Build the shared sample of /ingest formats v: 1 and v: 2 (cases.json): the same activity of a few computers, written as the sends a v: 1
plugin and a v: 2 plugin would make, with the hour book and the totals per day each computer must end with.
The expected results come from the pretend plugin below (its own book, added up in whole usdMicro), never from the server's code, so the
Python server (server/test_contract.py) and the Go receiver are both checked against the same independent answer.
Run it again after changing a case: python3 tests/contract/ingest-v2/make_cases.py. Standard library only.
  Dựng bộ dữ liệu mẫu chung cho định dạng /ingest v: 1 và v: 2 (cases.json): cùng một chuỗi hoạt động của vài máy, viết thành các lần gửi
  mà plugin v: 1 và plugin v: 2 sẽ gửi, kèm sổ giờ và tổng theo ngày mà mỗi máy phải có lúc cuối.
  Kết quả chuẩn lấy từ plugin giả lập dưới đây (sổ riêng của nó, cộng bằng số nguyên usdMicro), không bao giờ lấy từ mã máy chủ, nên
  máy chủ Python (server/test_contract.py) và bộ nhận Go đều được đối chiếu với cùng một đáp án độc lập.
  Chạy lại sau khi sửa một ca: python3 tests/contract/ingest-v2/make_cases.py. Chỉ thư viện chuẩn."""

import json
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cases.json")
# the time zone the totals per day are counted in (TZ_OFFSET of the server)
# múi giờ dùng để đếm tổng theo ngày (TZ_OFFSET của máy chủ)
TZ_HOURS = 7
TZ = timezone(timedelta(hours=TZ_HOURS))
# how many hours the plugin keeps (hooks/edits.ts, LEDGER_HOURS)
# plugin giữ bao nhiêu giờ (hooks/edits.ts, LEDGER_HOURS)
LEDGER_HOURS = 8 * 24
# in the past, so no hour is ever ahead of the clock of the computer running the test
# ở quá khứ, để không giờ nào sớm hơn đồng hồ của máy chạy test
START = int(datetime(2026, 10, 5, 9, 0, tzinfo=TZ).timestamp())
KINDS = ("ledger", "tasks", "blocks")
SPEND_FIELDS = ("input", "output", "cacheRead", "cacheWrite")


class Plugin:
    """A pretend plugin on one computer: its hour book, its state, and what it last had accepted by the server, per hour.
    Plugin giả lập trên một máy: sổ giờ, trạng thái, và bản cuối của từng giờ mà máy chủ đã nhận."""

    def __init__(self, device: str, name: str, account: str, clock_ms: int = 0, numbered: bool = False):
        self.device, self.name, self.account, self.clock_ms = device, name, account, clock_ms
        # numbered: the plugin numbers its sends, seq = max(clock, last seq + 1) (hooks/sendv2.ts, nextSeq)
        # numbered: plugin đánh số các lần gửi, seq = max(đồng hồ, seq trước + 1) (hooks/sendv2.ts, nextSeq)
        self.numbered, self.seq = numbered, 0
        self.book = {kind: {} for kind in KINDS}
        self.state = {"openSessions": 1, "working": 1, "waiting": 0}
        self.accepted = None
        # the dollars a v: 1 plugin holds: added up in floating point turn by turn, as hooks/edits.ts does
        # số đô la plugin v: 1 giữ: cộng bằng số thực từng lượt, như hooks/edits.ts làm
        self.dollars = {}

    def hour(self, at: int) -> str:
        return str((at * 1000 + self.clock_ms) // 3_600_000)

    def spend(self, at: int, micro: int, tokens: int) -> None:
        h = self.hour(at)
        was = self.book["ledger"].get(h, dict({"usdMicro": 0}, **dict.fromkeys(SPEND_FIELDS, 0)))
        self.book["ledger"][h] = dict(was, usdMicro=was["usdMicro"] + micro, input=was["input"] + tokens, output=was["output"] + tokens // 5,
                                      cacheRead=was["cacheRead"] + tokens * 3, cacheWrite=was["cacheWrite"] + tokens // 2)
        self.dollars[h] = self.dollars.get(h, 0.0) + micro / 1_000_000
        self.trim(int(h))

    def task(self, at: int, worker: str) -> None:
        h = self.hour(at)
        was = self.book["tasks"].get(h, {"gemini": 0, "chatgpt": 0, "gemma": 0})
        self.book["tasks"][h] = dict(was, **{worker: was[worker] + 1})

    def block(self, at: int, kind: str, n: int) -> None:
        h = self.hour(at)
        table = dict(self.book["blocks"].get(h, {}))
        if n:
            table[kind] = n
        else:
            table.pop(kind, None)
        if table:
            self.book["blocks"][h] = table
        else:
            self.book["blocks"].pop(h, None)

    def trim(self, hour: int) -> None:
        for kind in KINDS:
            self.book[kind] = {h: v for h, v in self.book[kind].items() if int(h) > hour - LEDGER_HOURS}

    def base(self, at: int, v: int) -> dict:
        out = dict({"v": v, "device": self.device, "name": self.name, "account": self.account, "updatedAt": at * 1000 + self.clock_ms,
                    "pluginVersion": "0.50.0"}, **self.state)
        if self.numbered:
            self.seq = max(out["updatedAt"], self.seq + 1)
            out["seq"] = self.seq
        return out

    def send_v1(self, at: int) -> dict:
        """The whole book at the top, money in dollars as a v: 1 plugin sends it.
        Cả sổ ở ngoài cùng, tiền bằng đô la như plugin v: 1 gửi."""
        out = self.base(at, 1)
        out["ledger"] = {h: dict({k: v[k] for k in SPEND_FIELDS}, usd=self.dollars[h]) for h, v in self.book["ledger"].items()}
        out["tasks"] = {h: dict(v) for h, v in self.book["tasks"].items()}
        if self.book["blocks"]:
            out["blocks"] = {h: dict(v) for h, v in self.book["blocks"].items()}
        return out

    def send_v2(self, at: int, full: bool = False) -> dict:
        """Only the hours that differ from what the server last accepted, an hour gone from the book as an empty table; everything when
        nothing was accepted yet or the server asked for it.
        Chỉ các giờ khác với bản máy chủ nhận lần cuối, giờ đã rời sổ là bảng rỗng; gửi tất cả khi chưa có gì được nhận hoặc máy chủ xin."""
        out = self.base(at, 2)
        full = full or self.accepted is None
        hours = {}
        for kind in KINDS:
            mine, theirs = self.book[kind], {} if full else self.accepted[kind]
            changed = {h: dict(v) for h, v in mine.items() if theirs.get(h) != v}
            changed.update({h: {} for h in theirs if h not in mine})
            hours[kind] = dict(sorted(changed.items(), key=lambda x: int(x[0])))
        out["full"], out["hours"] = full, hours
        return out

    def accept(self) -> None:
        self.accepted = json.loads(json.dumps(self.book))

    def expected_book(self) -> dict:
        """The book the server must hold: usdMicro, and usd worked out from it; blocks only when there are some.
        Sổ máy chủ phải giữ: usdMicro, và usd tính từ nó; blocks chỉ khi có."""
        out = {"ledger": {h: dict(v, usd=v["usdMicro"] / 1_000_000) for h, v in sorted(self.book["ledger"].items(), key=lambda x: int(x[0]))},
               "tasks": dict(sorted(self.book["tasks"].items(), key=lambda x: int(x[0])))}
        if self.book["blocks"]:
            out["blocks"] = dict(sorted(self.book["blocks"].items(), key=lambda x: int(x[0])))
        return out

    def expected_days(self) -> dict:
        """Totals per local day, added up in whole numbers.
        Tổng theo từng ngày địa phương, cộng bằng số nguyên."""
        days = {}
        for kind in ("ledger", "tasks"):
            for h, v in self.book[kind].items():
                day = datetime.fromtimestamp(int(h) * 3600, TZ).date().isoformat()
                r = days.setdefault(day, {"usdMicro": 0, "tokensIn": 0, "tokensOut": 0, "gemini": 0, "chatgpt": 0, "gemma": 0})
                if kind == "ledger":
                    r["usdMicro"] += v["usdMicro"]
                    r["tokensIn"] += v["input"] + v["cacheRead"] + v["cacheWrite"]
                    r["tokensOut"] += v["output"]
                else:
                    for worker in ("gemini", "chatgpt", "gemma"):
                        r[worker] += v[worker]
        return dict(sorted(days.items()))


class Case:
    """One case: its steps, each a list of sends in both formats, then what the server must hold.
    Một ca: các bước, mỗi bước là danh sách lần gửi ở cả hai định dạng, rồi thứ máy chủ phải giữ."""

    def __init__(self, name: str, about: str, v2_only: bool = False):
        self.name, self.about, self.v2_only = name, about, v2_only
        self.steps, self.plugins = [], {}

    def plugin(self, *args, **kw) -> Plugin:
        p = Plugin(*args, **kw)
        self.plugins[p.device] = p
        return p

    def send(self, at: int, p: Plugin, delivered: bool = True, full: bool = False, expect: str = "saved", compare: bool = True,
             drop_row_first: bool = False, straight: bool = False) -> None:
        """One send of the same moment in both formats. delivered=False: lost on the way, the server never sees it. straight=True: with
        the Go receiver, the send goes straight to the Python server while the rows of the receiver wait (its address had run out).
        Một lần gửi của cùng một thời điểm ở cả hai định dạng. delivered=False: mất trên đường, máy chủ không bao giờ thấy. straight=True:
        khi có bộ nhận Go, lần gửi đi thẳng tới máy chủ Python trong lúc các dòng của bộ nhận đang chờ (địa chỉ bộ nhận đã hết hạn)."""
        step = {"at": at, "device": p.device, "v1": p.send_v1(at), "v2": p.send_v2(at, full), "delivered": delivered,
                "expectV2": expect, "compare": compare and delivered}
        if drop_row_first:
            step["dropRowFirst"] = True
        if straight:
            step["straight"] = True
        if delivered and expect == "saved":
            p.accept()
        if expect == "need-full":
            # the server asked for the whole book: forget what it had, the next v: 2 send is full
            # máy chủ xin cả sổ: quên những gì nó từng có, lần gửi v: 2 sau là gửi đủ
            p.accepted = None
        self.steps.append(step)

    def to_json(self) -> dict:
        return {"name": self.name, "about": self.about, "v2Only": self.v2_only, "steps": self.steps,
                "expect": {d: {"book": p.expected_book(), "days": p.expected_days()} for d, p in self.plugins.items()}}


def cases() -> list:
    out = []

    c = Case("steady-day", "A day of work: a first full send, spend and tasks in the same hour, a send with nothing new, "
                           "the next hour, waiting on and off, work stopped.")
    a = c.plugin("device-ctra", "Contract A", "contract-a@example.com")
    t = START
    a.spend(t, 123_456, 1000)
    c.send(t, a)
    a.spend(t + 2, 654_321, 2000)
    a.task(t + 2, "gemini")
    c.send(t + 2, a)
    c.send(t + 4, a)
    c.send(t + 4, a)
    a.spend(t + 3600, 1, 3)
    a.task(t + 3600, "gemma")
    c.send(t + 3600, a)
    a.state.update(waiting=1)
    c.send(t + 3602, a)
    a.state.update(waiting=0, working=0)
    c.send(t + 3610, a)
    out.append(c)

    c = Case("two-computers-one-person", "Two computers of the same person, each with its own book, interleaved.")
    a = c.plugin("device-ctrb1", "Contract B", "contract-b@example.com")
    b = c.plugin("device-ctrb2", "Contract B", "contract-b@example.com")
    t = START
    for i in range(6):
        p = a if i % 2 == 0 else b
        p.spend(t + i * 600, 100_000 + i, 500)
        p.task(t + i * 600, "chatgpt")
        c.send(t + i * 600, p)
    out.append(c)

    c = Case("midnight", "Spend just before and just after local midnight lands on two days.")
    a = c.plugin("device-ctrc", "Contract C", "contract-c@example.com")
    midnight = int(datetime(2026, 10, 6, 0, 0, tzinfo=TZ).timestamp())
    a.spend(midnight - 2, 999_999, 100)
    c.send(midnight - 2, a)
    a.spend(midnight + 1, 1_000_001, 100)
    c.send(midnight + 1, a)
    out.append(c)

    c = Case("lost-send", "A send lost on the way: the next one carries the hours of both.")
    a = c.plugin("device-ctrd", "Contract D", "contract-d@example.com")
    t = START
    a.spend(t, 10_000, 10)
    c.send(t, a)
    a.spend(t + 3600, 20_000, 10)
    c.send(t + 3600, a, delivered=False)
    a.spend(t + 7200, 30_000, 10)
    c.send(t + 7200, a)
    out.append(c)

    c = Case("server-lost-the-row", "The server lost a computer's row (a restore from an old backup): a v: 2 send of changed hours only "
                                    "is answered needFull and nothing is kept; the full send that follows puts the whole book back.")
    a = c.plugin("device-ctre", "Contract E", "contract-e@example.com")
    t = START
    a.spend(t, 50_000, 10)
    c.send(t, a)
    a.spend(t + 3600, 60_000, 10)
    c.send(t + 3600, a, drop_row_first=True, expect="need-full", compare=False)
    c.send(t + 3602, a)
    out.append(c)

    c = Case("hours-leave-the-book", "Over eight days the plugin drops its oldest hours; v: 2 sends them as empty tables and the server drops them too. "
                                     "A blocks hour set then cleared goes the same way.")
    a = c.plugin("device-ctrf", "Contract F", "contract-f@example.com")
    t = START
    a.spend(t, 70_000, 10)
    a.block(t, "secret", 2)
    c.send(t, a)
    a.block(t + 60, "secret", 0)
    c.send(t + 60, a)
    for day in range(1, 10):
        a.spend(t + day * 86400, 80_000 + day, 10)
        c.send(t + day * 86400, a)
    out.append(c)

    c = Case("money-in-dollars", "Dollar amounts a v: 1 plugin adds up in floating point turn into exactly the same usdMicro.")
    a = c.plugin("device-ctrg", "Contract G", "contract-g@example.com")
    t = START
    for i, micro in enumerate((100_000, 200_000, 300_000, 1, 999_999, 33_333_333)):
        a.spend(t + i * 2, micro, 7)
        c.send(t + i * 2, a)
    out.append(c)

    c = Case("clock-ahead", "A computer whose clock is 25 minutes ahead: its hours follow its own clock.")
    a = c.plugin("device-ctrh", "Contract H", "contract-h@example.com", clock_ms=25 * 60_000)
    t = START + 40 * 60
    a.spend(t, 40_000, 10)
    c.send(t, a)
    a.spend(t + 10 * 60, 50_000, 10)
    c.send(t + 10 * 60, a)
    out.append(c)

    c = Case("full-again-soon", "A second full send within the hour (a new Claude Code session) is merged hour by hour: the book is the same.")
    a = c.plugin("device-ctri", "Contract I", "contract-i@example.com")
    t = START
    a.spend(t, 11_000, 10)
    c.send(t, a)
    a.spend(t + 1800, 12_000, 10)
    c.send(t + 1800, a, full=True)
    out.append(c)

    c = Case("out-of-order", "Two v: 2 sends of one computer arrive in the wrong order (two sessions on one computer): the older one is "
                             "dropped as stale and the newer book stays. v: 1 has no such guard, so this case is for v: 2 only.", v2_only=True)
    a = c.plugin("device-ctrj", "Contract J", "contract-j@example.com")
    t = START
    a.spend(t, 10_000, 10)
    c.send(t, a)
    a.spend(t + 2, 5_000, 10)
    older = a.send_v2(t + 2)
    a.spend(t + 4, 5_000, 10)
    c.send(t + 4, a)
    c.steps.append({"at": t + 5, "device": a.device, "v1": None, "v2": older, "delivered": True, "expectV2": "stale", "compare": True})
    out.append(c)

    c = Case("clock-back-with-seq", "The clock of a computer that numbers its sends goes back 30 seconds: its next send is stamped older "
                                    "by updatedAt, but its seq is newer, so it is written, not dropped as out of order. Without seq the "
                                    "window of a minute dropped it. v: 1 has no window, so this case is for v: 2 only.", v2_only=True)
    a = c.plugin("device-ctrl", "Contract L", "contract-l@example.com", numbered=True)
    t = START + 600
    a.spend(t, 10_000, 10)
    c.send(t, a)
    a.clock_ms = -30_000
    a.spend(t + 10, 4_000, 10)
    c.send(t + 10, a)
    out.append(c)

    c = Case("receiver-row-around-a-straight-send", "Through the Go receiver, a send waits with an hour; a newer send of that hour goes "
                                                   "straight to the server; a later send through the receiver joins the row waiting with "
                                                   "another hour only. The hour of the older send in that row must not write over the "
                                                   "straight one (each hour keeps the time of its send, proto 3).")
    a = c.plugin("device-ctrk", "Contract K", "contract-k@example.com")
    t = START
    a.spend(t, 10_000, 10)
    c.send(t, a)
    a.spend(t + 3600, 20_000, 10)
    c.send(t + 3600, a)
    a.spend(t + 3602, 5_000, 10)
    a.task(t + 3602, "gemini")
    c.send(t + 3602, a, straight=True)
    a.spend(t + 7200, 7_000, 10)
    c.send(t + 7200, a)
    out.append(c)
    return out


def build() -> dict:
    return {"about": "Shared sample of /ingest formats v: 1 and v: 2. Made by make_cases.py; see docs/DATA-MODEL.md, \"Format v: 2\".",
            "tzHours": TZ_HOURS, "cases": [c.to_json() for c in cases()]}


def text() -> str:
    return json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text())
    print("wrote %s" % OUT)
