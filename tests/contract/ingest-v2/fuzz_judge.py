#!/usr/bin/env python3
"""The judge of the random test of the Go receiver (receiver/internal/clean/fuzz_test.go): makes random sends from a seed, cleans them with
the server's own code and prints, one JSON line per case, what Python made of each. The Go test cleans the same bytes and must get the same.
python3 tests/contract/ingest-v2/fuzz_judge.py <seed> <count>. Standard library only; it reads no database and writes nothing.
  Trọng tài của bài thử ngẫu nhiên cho bộ nhận Go (receiver/internal/clean/fuzz_test.go): tạo các lần gửi ngẫu nhiên từ một hạt giống,
  làm sạch chúng bằng chính mã của máy chủ và in ra, mỗi ca một dòng JSON, thứ Python làm ra từ mỗi lần gửi. Bài test Go làm sạch cùng
  các byte đó và phải ra cùng kết quả. Chỉ thư viện chuẩn; không đọc cơ sở dữ liệu nào và không ghi gì."""

import json
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "..", "..", "server")
# the server's settings read these at import: point them at an empty folder, so nothing real is ever opened
# cấu hình của máy chủ đọc các biến này lúc nhập: trỏ chúng vào một thư mục rỗng, để không bao giờ mở thứ gì thật
EMPTY = tempfile.mkdtemp(prefix="fuzz-judge-")
os.environ.update(DATA_DIR=EMPTY, KEYS_DIR=EMPTY, TZ_OFFSET="7", BRANCHES_FILE=os.path.join(EMPTY, "none.json"))
sys.path.insert(0, SERVER)

from board import devices  # noqa: E402

NOW = 1795200000.0
FIELDS = ("v", "device", "updatedAt", "seq", "name", "account", "enteredAccount", "lanIp", "ip", "pluginVersion", "openSessions", "working",
          "waiting", "tools", "hardwareMark", "ipHistory", "delegating", "models", "subagents", "ledger", "tasks", "blocks", "hours", "full",
          "assistants", "quota", "delegations")
INNER = ("usd", "usdMicro", "input", "output", "cacheRead", "cacheWrite", "gemini", "chatgpt", "gemma", "secret", "commit", "risky", "page",
         "answer", "codex", "cursor", "openSessions", "working", "waiting", "chatgptModel", "geminiModel", "kind", "pct", "resetsAt", "readAt",
         "windows", "ip", "from", "to", "id", "tool", "at", "via", "promptChars", "answerChars", "promptHash", "outcome", "check", "found")


class Gen:
    def __init__(self, rng: random.Random):
        self.r = rng

    def number(self) -> str:
        r = self.r
        pick = r.random()
        if pick < 0.25:
            return str(r.randint(0, 100))
        if pick < 0.4:
            return str(r.choice([0, 1, 2, 100000, 100001, 999, 1000, 10 ** 15, 10 ** 15 + 1, -1, 2 ** 53 + 1, 2 ** 63, 10 ** 22, 10 ** 30]))
        if pick < 0.55:
            return repr(r.choice([0.5, 1.5, 2.5, 0.1, 1e-06, 1.0, 2.0, -0.0, 1e15, 1e16, 999.9, 123456.789, 0.0000015, 1e-7]))
        if pick < 0.65:
            return r.choice(["1e5", "1E2", "2.50", "1e400", "-1e400", "1e-400", "0.0", "-0", "1.0e0", "4.5e-07"])
        if pick < 0.8:
            return repr(r.uniform(0, 5))
        if pick < 0.9:
            return str(int(NOW * 1000) + r.randint(-10 ** 9, 2 * 86_400_000))
        return repr(r.uniform(0, 2e9) * 1000)

    def text(self) -> str:
        r = self.r
        pieces = ["a", "Z", " ", ".", "\u00e9", "\u0100", "\U0001f600", "\x00", "\x1f", "\x7f", "\t", "\n", "device-", "0", "9", "f", "x", "\"", "\\", "/", " "]
        s = "".join(r.choice(pieces) for _ in range(r.choice([0, 1, 2, 5, 10, 24, 25, 32, 40, 79, 80, 130])))
        if r.random() < 0.2:
            s = r.choice(["device-" + "".join(r.choice("abc019") for _ in range(r.randint(0, 42))), "".join(r.choice("0123456789abcdef") for _ in range(r.choice([24, 32, 31]))),
                          "ask_gemini", "ask_chatgpt", "generate_image", "ask_local", "plugin", "ai-workers", "ok", "refused", "secret", "aimed",
                          "GitHub token", "x", "AWS key.", "chatgpt", "gemini", "gemma", "codex"])
        return json.dumps(s, ensure_ascii=self.r.random() < 0.5)

    def hour_key(self) -> str:
        r = self.r
        h = int(NOW // 3600)
        return json.dumps(r.choice([str(h - r.randint(0, 300)), str(h + r.randint(0, 30)), "00" + str(h), "x1", "", "123456789", str(h)]))

    def value(self, depth: int) -> str:
        r = self.r
        pick = r.random()
        if depth > 3 or pick < 0.35:
            return self.number()
        if pick < 0.5:
            return self.text()
        if pick < 0.58:
            return r.choice(["true", "false", "null"])
        if pick < 0.7:
            return "[" + ", ".join(self.value(depth + 1) for _ in range(r.randint(0, 4))) + "]"
        return self.table(depth + 1)

    def table(self, depth: int, keys=None) -> str:
        r = self.r
        parts = []
        for _ in range(r.randint(0, 6)):
            if r.random() < 0.35:
                k = self.hour_key()
            else:
                k = json.dumps(r.choice(INNER) if r.random() < 0.8 else json.loads(self.text()))
            parts.append(k + ": " + self.value(depth))
        # a key that comes twice: Python keeps its first place and its last value
        # một khoá tới hai lần: Python giữ chỗ đầu và giá trị cuối
        if parts and r.random() < 0.2:
            parts.append(parts[0].split(": ", 1)[0] + ": " + self.value(depth))
        return "{" + ", ".join(parts) + "}"

    def delegation(self) -> str:
        """A record of work handed to a helper, mostly well formed, with a field or two wrong now and then.
        Một biên bản giao việc, phần lớn đúng dạng, thỉnh thoảng sai một hai trường."""
        r = self.r
        d = {"id": json.dumps("".join(r.choice("0123456789abcdef") for _ in range(24))), "tool": json.dumps(r.choice(["ask_gemini", "ask_chatgpt", "ask_local", "generate_image"])),
             "at": str(int(NOW * 1000) + r.randint(-4 * 86_400_000, 2 * 86_400_000)), "via": json.dumps(r.choice(["plugin", "ai-workers", "other"])),
             "promptChars": self.number(), "answerChars": self.number(), "promptHash": json.dumps("".join(r.choice("0123456789abcdef") for _ in range(32))),
             "outcome": json.dumps(r.choice(["ok", "error", "refused", "declined", "odd"])), "check": json.dumps(r.sample(["secret", "aimed", "command", "x"], r.randint(0, 4))),
             "found": json.dumps(r.sample(["GitHub token", "AWS key", "a", "Bad1", "Zz.", "GitHub token", "OpenAI key", "\u00e9 key", "x" * 41], r.randint(0, 9)))}
        for k in r.sample(list(d), r.randint(0, 2)):
            d[k] = self.value(2)
        return "{" + ", ".join(json.dumps(k) + ": " + v for k, v in d.items()) + "}"

    def send(self) -> str:
        r = self.r
        parts = []
        v = r.choice(["1", "2", "2", "1.0", "2.0", "true", "3", "\"2\""])
        parts.append('"v": ' + v)
        parts.append('"device": ' + (json.dumps("device-" + "".join(r.choice("abc0129") for _ in range(r.randint(1, 16)))) if r.random() < 0.9 else self.text()))
        parts.append('"updatedAt": ' + (self.number() if r.random() < 0.95 else "true"))
        for name in r.sample(FIELDS[3:], r.randint(3, len(FIELDS) - 3)):
            if name in ("ledger", "tasks", "blocks"):
                body = "{" + ", ".join(self.hour_key() + ": " + self.table(2) for _ in range(r.randint(0, 6))) + "}"
            elif name == "hours":
                body = "{" + ", ".join('"%s": {' % kind + ", ".join(self.hour_key() + ": " + self.table(2) for _ in range(r.randint(0, 5))) + "}"
                                       for kind in r.sample(["ledger", "tasks", "blocks"], r.randint(0, 3))) + "}"
            elif name == "delegations":
                body = "[" + ", ".join(self.delegation() if r.random() < 0.8 else self.value(2) for _ in range(r.randint(0, 6))) + "]"
            elif name == "ipHistory":
                body = "[" + ", ".join(self.table(2) for _ in range(r.randint(0, 5))) + "]"
            elif name == "quota":
                body = '{"readAt": %s, "windows": [%s]}' % (self.number(), ", ".join(self.table(2) for _ in range(r.randint(0, 7))))
            elif name == "full":
                body = r.choice(["true", "false", "1", "null"])
            else:
                body = self.value(1)
            parts.append(json.dumps(name) + ": " + body)
        r.shuffle(parts)
        return "{" + ", ".join(parts) + "}"


def main() -> None:
    seed, count = int(sys.argv[1]), int(sys.argv[2])
    gen = Gen(random.Random(seed))
    out = sys.stdout
    for _ in range(count):
        now = NOW + gen.r.uniform(-3600, 3600)
        raw_text = gen.send()
        try:
            raw = json.loads(raw_text, parse_constant=devices.refuse_constant)
            cleaned = devices.clean_payload(raw, now)
        except (ValueError, RecursionError):
            raw, cleaned = None, None
        line = {"now": now, "raw": raw_text, "parsed": raw is not None, "clean": cleaned}
        if isinstance(raw, dict):
            line["delegations"] = devices.clean_delegations(raw.get("delegations"), now * 1000)
            line["kind"] = devices.send_kind(raw)
        if cleaned:
            second_text = gen.send()
            try:
                second = devices.clean_payload(json.loads(second_text), now)
            except ValueError:
                second = None
            if second:
                line["second"] = second_text
                line["merged"] = devices.merge_hours(cleaned, second)
                line["days"] = {day.isoformat(): {k: v[k] for k in ("usdMicro", "tokensIn", "tokensOut", "gemini", "chatgpt", "gemma")}
                                for day, v in sorted(devices.add_up_hours(cleaned)["days"].items())}
        out.write(json.dumps(line, allow_nan=True) + "\n")


if __name__ == "__main__":
    main()
