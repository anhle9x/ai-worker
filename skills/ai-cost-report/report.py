#!/usr/bin/env python3
"""Turns the JSON lines an AI project or application wrote (FORMAT.md) into a cost and speed report: one HTML page that prints to PDF, and one CSV.
  Biến các dòng JSON một dự án hay ứng dụng AI đã ghi (FORMAT.md) thành báo cáo chi phí và tốc độ: một trang HTML in ra PDF được, và một file CSV.

Python 3.8+, standard library only. Usage:
  Python 3.8+, chỉ thư viện chuẩn. Cách dùng:
    python3 report.py ai-meter.jsonl [more.jsonl ...] [--out DIR] [--lang en|vi] [--env prod|test|all]
                      [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--compare MODEL ...] [--prices prices.json] [--add-prices mine.json ...] [--title TEXT]
"""
import argparse
import csv
import html
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,31}$")
# Providers that run on the team's own machines: no API bill, tokens and time still shown. A price file can add more
# Các hãng chạy trên máy của chính nhóm: không có tiền API, vẫn hiện token và thời gian. File giá có thể thêm
LOCAL_PROVIDERS = ("local", "ollama", "vllm", "llamacpp", "lmstudio", "localai", "tgi", "sglang")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$")
TURN_RE = re.compile(r"^[0-9a-f]{16,64}$")
COUNTS = ("input", "output", "cacheRead", "cacheWrite", "cacheWriteLong")
TOKENS = ("input", "output", "cacheRead", "cacheWrite")
TALLIES = ("calls", "errors", "retries", "unmeasured")
PICO = 10 ** 12
MAX_LINE = 64 * 1024
MAX_MODELS = 50


def _int(v, allow_none=False):
    if v is None and allow_none:
        return True
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10 ** 15


def parse_time(s):
    if not isinstance(s, str) or len(s) > 40:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def clean_line(raw):
    """Keeps only the known fields of one line, or returns None when the line breaks FORMAT.md. Unknown fields are dropped unread.
    Chỉ giữ các trường đã biết của một dòng, hoặc trả None khi dòng sai FORMAT.md. Trường lạ bị bỏ, không đọc."""
    if not isinstance(raw, dict) or raw.get("v") != 1:
        return None
    tid, at = raw.get("turnId"), parse_time(raw.get("at"))
    dur, ttft = raw.get("durationMs"), raw.get("ttftMs")
    if not isinstance(tid, str) or not TURN_RE.match(tid) or at is None or not _int(dur):
        return None
    if ttft is not None and (not _int(ttft) or ttft > dur):
        return None
    if raw.get("outcome") not in ("ok", "error", "timeout") or raw.get("env") not in ("prod", "test"):
        return None
    models = raw.get("models")
    if not isinstance(models, list) or len(models) > MAX_MODELS:
        return None
    out = []
    for m in models:
        if not isinstance(m, dict) or not isinstance(m.get("provider"), str) or not PROVIDER_RE.match(m["provider"]):
            return None
        if not isinstance(m.get("model"), str) or not MODEL_RE.match(m["model"]):
            return None
        row = {"provider": m["provider"], "model": m["model"]}
        for k in TALLIES:
            v = m.get(k, 0)
            if not _int(v):
                return None
            row[k] = v
        # input and output are a number or null together; a missing cache field is 0; with null tokens the cache fields mean nothing
        # input và output cùng là số hoặc cùng null; trường cache vắng là 0; khi token là null thì trường cache không có nghĩa
        for k in COUNTS:
            if not _int(m.get(k), allow_none=True):
                return None
        if m.get("input") is None and m.get("output") is None:
            row["measured"] = False
            for k in COUNTS:
                row[k] = 0
        elif m.get("input") is None or m.get("output") is None or any(k in m and m[k] is None for k in COUNTS[2:]):
            return None
        else:
            row["measured"] = row["unmeasured"] == 0
            for k in COUNTS:
                row[k] = m.get(k) or 0
        if row["errors"] > row["calls"] or row["retries"] > row["calls"] or row["unmeasured"] > row["calls"] or row["cacheWriteLong"] > row["cacheWrite"]:
            return None
        out.append(row)
    return {"turnId": tid, "at": at, "durationMs": dur, "ttftMs": ttft, "outcome": raw["outcome"], "env": raw["env"], "models": out}


def read_lines(paths):
    turns, seen, skipped, dupes = [], set(), 0, 0
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            for raw in f:
                if not raw.strip():
                    continue
                if len(raw) > MAX_LINE:
                    skipped += 1
                    continue
                try:
                    t = clean_line(json.loads(raw))
                except ValueError:
                    t = None
                if t is None:
                    skipped += 1
                elif t["turnId"] in seen:
                    dupes += 1
                else:
                    seen.add(t["turnId"])
                    turns.append(t)
    turns.sort(key=lambda t: t["at"])
    return turns, skipped, dupes


def price_keys(model):
    # The names a model may be priced under: as written, without a "vendor/" or cloud prefix, without a date or version tail
    # Các tên mà một model có thể có giá: như đã ghi, bỏ tiền tố "hãng/" hay của cloud, bỏ đuôi ngày hay phiên bản
    names = [model, model.split("/")[-1]]
    out = []
    for n in names:
        n2 = re.sub(r"^(?:[a-z]{2,6}\.)?(?:anthropic|google|openai)\.", "", n)
        for cand in (n, n2):
            c = re.sub(r"(-v\d+(:\d+)?|@\d{8}|-\d{8}|-\d{4}-\d{2}-\d{2}|-\d{3}|-latest)$", "", cand)
            for x in (cand, c):
                if x not in out:
                    out.append(x)
    return out


ZERO = {k: 0 for k in COUNTS}


class Prices:
    """The price file of the skill, with the user's own files on top: their models replace ours, their providers are added.
    File giá của skill, cùng các file riêng của người dùng đè lên: model của họ thay model của skill, hãng của họ được thêm vào."""

    def __init__(self, path, extra=()):
        with open(path, encoding="utf-8") as f:
            self.doc = json.load(f)
        self.by_model = {}
        for m in self.doc.get("models", []):
            for name in [m["model"]] + list(m.get("aliases") or []):
                self.by_model.setdefault(name, m)
        self.local = set(LOCAL_PROVIDERS) | set(self.doc.get("localProviders", []))
        self.yours = []
        for p in extra:
            # a file of the user's own, or the same shape already read (the board keeps the prices an admin pasted)
            # một file riêng của người dùng, hoặc cùng dạng đó đã đọc sẵn (bảng giữ giá mà quản trị đã dán)
            if isinstance(p, dict):
                doc, name = p, str(p.get("name") or "prices")
            else:
                with open(p, encoding="utf-8") as f:
                    doc = json.load(f)
                name = os.path.basename(p)
            self.yours.append(name)
            for prov, info in (doc.get("providers") or {}).items():
                self.doc["providers"][prov] = dict(info, source=info.get("source") or name, checked=info.get("checked") or "-", yours=name)
            for m in doc.get("models") or []:
                if isinstance(m, dict) and isinstance(m.get("model"), str) and isinstance(m.get("prices", []), list):
                    self.by_model[m["model"]] = dict(m, prices=m.get("prices") or [], yours=name)
            self.local |= {x for x in doc.get("localProviders") or [] if isinstance(x, str)}

    def entry(self, model):
        for k in price_keys(model):
            if k in self.by_model:
                return self.by_model[k]
        return None

    def is_local(self, provider, model):
        # Runs on the team's machine: marked so in a price file, or a local provider with no price of its own
        # Chạy trên máy của nhóm: file giá ghi như vậy, hoặc là hãng chạy trên máy mà không có giá riêng
        e = self.entry(model)
        return bool(e and e.get("local")) or (provider in self.local and e is None)

    def at(self, model, day):
        # The price row in force on that day (UTC), or None
        # Dòng giá áp dụng ngày đó (UTC), hoặc None
        e = self.entry(model)
        if e is None:
            return None
        chosen = None
        for row in e["prices"]:
            if row.get("from") is None or row["from"] <= day:
                chosen = row
        return chosen

    def cost(self, row, price):
        """Cost in millionths of a millionth of a dollar (exact integer), or None when a needed price is unknown.
        Chi phí theo phần triệu của phần triệu đô la (số nguyên chính xác), hoặc None khi thiếu giá cần dùng."""
        if price is None:
            return None
        short = row["cacheWrite"] - row["cacheWriteLong"]
        parts = ((row["input"], "input"), (row["output"], "output"), (row["cacheRead"], "cacheRead"),
                 (short, "cacheWrite"), (row["cacheWriteLong"], "cacheWriteLong"))
        total = 0
        for n, k in parts:
            if n == 0:
                continue
            p = price.get(k)
            if p is None:
                return None
            total += n * p
        return total


def p95(values):
    # Nearest-rank on the raw values: the smallest value with at least 95% of the values at or below it
    # Nearest-rank trên dữ liệu thô: giá trị nhỏ nhất mà ít nhất 95% giá trị nằm ở hoặc dưới nó
    if not values:
        return None
    s = sorted(values)
    rank = -(-95 * len(s) // 100)
    return s[max(rank, 1) - 1]


def avg(values):
    return sum(values) / len(values) if values else None


def analyse(turns, prices, compare=()):
    models, days = {}, {}
    measured, priced = [], []
    unpriced_models = set()
    for t in turns:
        day = t["at"].strftime("%Y-%m-%d")
        t_ok = all(m["measured"] for m in t["models"])
        t_cost = 0
        for m in t["models"]:
            key = (m["provider"], m["model"])
            a = models.setdefault(key, dict({k: 0 for k in TALLIES + COUNTS}, turns=0, cost=0, costTurns=0, unpricedTurns=0, unmeasuredTurns=0, entry=prices.entry(m["model"])))
            a["turns"] += 1
            for k in TALLIES + COUNTS:
                a[k] += m[k]
            if not m["measured"]:
                a["unmeasuredTurns"] += 1
                t_cost = None
                continue
            if prices.is_local(m["provider"], m["model"]):
                a["local"] = True
                a["costTurns"] += 1
                continue
            c = prices.cost(m, prices.at(m["model"], day))
            if c is None:
                a["unpricedTurns"] += 1
                unpriced_models.add(m["model"])
                t_cost = None
            else:
                a["cost"] += c
                a["costTurns"] += 1
                if t_cost is not None:
                    t_cost += c
        d = days.setdefault(day, {"turns": 0, "errors": 0, "cost": 0, "costTurns": 0, "ms": []})
        d["turns"] += 1
        d["errors"] += t["outcome"] != "ok"
        if t["outcome"] == "ok":
            d["ms"].append(t["durationMs"])
        if t_ok:
            measured.append(t)
            if t_cost is not None:
                priced.append((t, t_cost))
                d["cost"] += t_cost
                d["costTurns"] += 1
    ok_ms = [t["durationMs"] for t in turns if t["outcome"] == "ok"]
    ttft = [t["ttftMs"] for t in turns if t["outcome"] == "ok" and t["ttftMs"] is not None]
    tok = {k: avg([sum(m[k] for m in t["models"]) for t in measured]) for k in TOKENS}
    cost_turn = avg([c for _, c in priced])
    alt = []
    for target in compare:
        costs = []
        for t, _ in priced:
            day = t["at"].strftime("%Y-%m-%d")
            sumrow = {k: sum(m[k] for m in t["models"]) for k in COUNTS}
            costs.append(prices.cost(sumrow, prices.at(target, day)))
        known = [c for c in costs if c is not None]
        alt.append({"model": target, "known": prices.entry(target) is not None, "costTurn": avg(known) if len(known) == len(costs) else None})
    return {
        "turns": len(turns),
        "first": turns[0]["at"] if turns else None,
        "last": turns[-1]["at"] if turns else None,
        "outcomes": {o: sum(1 for t in turns if t["outcome"] == o) for o in ("ok", "error", "timeout")},
        "callsTurn": avg([sum(m["calls"] for m in t["models"]) for t in turns]),
        "retries": sum(m["retries"] for t in turns for m in t["models"]),
        "measured": len(measured),
        "priced": len(priced),
        "tokTurn": tok,
        "costTurn": cost_turn,
        "costTotal": sum(c for _, c in priced),
        "ms": {"avg": avg(ok_ms), "p95": p95(ok_ms), "max": max(ok_ms) if ok_ms else None, "n": len(ok_ms)},
        "ttft": {"avg": avg(ttft), "p95": p95(ttft), "n": len(ttft)},
        "models": models,
        "days": days,
        "unpriced": sorted(unpriced_models),
        "local": sorted(m for (_, m), a in models.items() if a.get("local")),
        "long": sorted({"%s (%s)" % (m, "{:,}".format(a["entry"]["higherPriceAbove"])) for (_, m), a in models.items() if a["entry"] and a["entry"].get("higherPriceAbove")}),
        "alt": alt,
    }


def usd(pico, digits=None):
    if pico is None:
        return None
    v = pico / PICO
    if digits is None:
        digits = 2 if abs(v) >= 100 else 4 if abs(v) >= 1 else 6
    return "$%.*f" % (digits, v)


def num(v, digits=0):
    if v is None:
        return "-"
    return "{:,.{d}f}".format(v, d=digits)


DAY_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def show_dates(text, L):
    """Every day written YYYY-MM-DD in a text, the way the report's language writes it: DD/MM/YYYY in Vietnamese, as it is in English.
    Only what people read changes; the CSV, the file names and --from/--to keep YYYY-MM-DD.
    Mọi ngày viết YYYY-MM-DD trong một đoạn chữ, theo cách ngôn ngữ của báo cáo viết: DD/MM/YYYY trong tiếng Việt, giữ nguyên trong tiếng Anh.
    Chỉ đổi chỗ người đọc; CSV, tên file và --from/--to vẫn giữ YYYY-MM-DD."""
    return DAY_RE.sub(r"\3/\2/\1", text) if L.get("lang") == "vi" else text


def load_labels(lang):
    with open(os.path.join(HERE, "labels.json"), encoding="utf-8") as f:
        labels = json.load(f)
    base = labels["en"]
    base.update(labels.get(lang, {}))
    return base


CSS = """
:root{color-scheme:light dark;--bg:#f4f7f8;--glow:none;--card:#fff;--fg:#14232b;--muted:#566a73;--line:#d8e2e6;--soft:#edf3f5;
--accent:#0b7a83;--on-accent:#fff;--info:rgba(11,122,131,.08);--warn:#9a5b00;--warn-bg:#fff5e3}
@media (prefers-color-scheme:dark){:root{--bg:#060e14;--glow:radial-gradient(ellipse at 50% -10%,#0d2230 0,rgba(6,14,20,0) 60%);--card:#0b1922;
--fg:#d6eef2;--muted:#82a0ab;--line:#17303b;--soft:#0e2029;--accent:#5ee6f0;--on-accent:#04232a;--info:rgba(94,230,240,.06);--warn:#ffc24b;--warn-bg:rgba(255,194,75,.08)}}
*{box-sizing:border-box}body{margin:0;background:var(--glow) no-repeat,var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:28px 16px 56px}h1{font-size:24px;line-height:1.3;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:16px;margin:32px 0 10px;color:var(--fg)}h2::before{content:"";display:inline-block;width:4px;height:14px;margin-right:8px;border-radius:2px;background:var(--accent);vertical-align:-1px}
.sub{color:var(--muted);margin:0 0 16px;font-size:14px}
.note{border:1px solid var(--line);border-left:3px solid var(--accent);background:var(--info);border-radius:8px;padding:9px 14px;margin:10px 0;font-size:14px}
.note.warn{border-left-color:var(--warn);background:var(--warn-bg)}
.empty{border:1px dashed var(--line);border-radius:12px;padding:28px 20px;margin:16px 0;text-align:center;color:var(--muted);background:var(--card)}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
.card b{display:block;font-size:22px;line-height:1.25;font-weight:650;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.card span{display:block;margin-top:4px;color:var(--muted);font-size:13px;line-height:1.35}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{padding:9px 14px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{background:var(--soft);color:var(--muted);font-size:13px;font-weight:600}tr:last-child td{border-bottom:0}
tr:hover td{background:var(--info)}ul{padding-left:20px}li{overflow-wrap:anywhere;margin:2px 0}
footer{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
@media (max-width:760px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:560px){h1{font-size:20px}.cards{gap:8px}.card{padding:12px}.card b{font-size:18px}}
@media print{:root{--bg:#fff;--glow:none;--card:#fff;--fg:#000;--muted:#444;--line:#bbb;--soft:#f2f2f2;--info:#fff;--warn-bg:#fff}
body{background:#fff}main{max-width:none;padding:0}.wrap{overflow:visible}h2{break-after:avoid}table{break-inside:auto}tr{break-inside:avoid}}
"""

# The file people download and print: always white, A4 portrait, nothing cut at the edge, the page number at the foot of each page
# File người ta tải về và in: luôn nền trắng, khổ A4 dọc, không gì bị cắt mép, số trang ở chân mỗi trang
PAPER_CSS = """
:root{color-scheme:light;--card:#fff;--fg:#14232b;--muted:#4f626b;--line:#cfd9dd;--soft:#eef3f5;--accent:#0b7a83;--info:#f1f8f8;--warn:#8a5200;--warn-bg:#fff6e5;
--body:15px;--small:13.5px;--tiny:12.5px;--table:13px;--th:12.5px;--h1:26px;--h2:17px;--value:20px;--gap:10px}
@page{size:A4 portrait;margin:14mm 12mm 16mm;@bottom-left{content:"%(foot)s";font:8pt system-ui,sans-serif;color:#5b6b72}
@bottom-right{content:counter(page) " / " counter(pages);font:8pt system-ui,sans-serif;color:#5b6b72}}
*{box-sizing:border-box}html{background:#e4eaed}
body{margin:0;color:var(--fg);font:var(--body)/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact;-webkit-text-size-adjust:100%%}
main{width:980px;max-width:calc(100%% - 32px);margin:16px auto 32px;padding:40px 44px;background:#fff;border-radius:6px;box-shadow:0 2px 16px rgba(0,0,0,.12)}
.hint{width:980px;max-width:calc(100%% - 32px);margin:16px auto 0;padding:9px 14px;border-radius:6px;background:#14232b;color:#fff;font-size:var(--small);line-height:1.5}
.doc{border-bottom:2px solid var(--accent);padding-bottom:10px;margin-bottom:12px}
.kicker{margin:0;font-size:var(--tiny);letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:var(--h1);line-height:1.25;margin:2px 0 10px}
.meta{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;margin:0;font-size:var(--small)}.meta dt{color:var(--muted)}.meta dd{margin:0;min-width:0;overflow-wrap:anywhere}
.note{border:1px solid var(--line);border-left:3px solid var(--accent);background:var(--info);border-radius:6px;padding:8px 12px;margin:8px 0;font-size:var(--small);break-inside:avoid}
.note.lead{border-left-width:5px;font-weight:600}.note.warn{border-left-color:var(--warn);background:var(--warn-bg)}
.empty{border:1px dashed var(--line);border-radius:6px;padding:22px;margin:14px 0;text-align:center;color:var(--muted)}
h2{font-size:var(--h2);margin:24px 0 8px;break-after:avoid;break-inside:avoid}h2::before{content:"";display:inline-block;width:3px;height:.85em;margin-right:7px;background:var(--accent);vertical-align:-1px}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--gap);margin:12px 0;break-inside:avoid}
.card{border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.card b{display:block;font-size:var(--value);line-height:1.3;font-weight:650;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.card span{display:block;color:var(--muted);font-size:var(--tiny);line-height:1.35}
.wrap{border:1px solid var(--line);border-radius:8px;overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-size:var(--table);line-height:1.4;font-variant-numeric:tabular-nums}thead{display:table-header-group}
th,td{padding:6px 9px;text-align:right;vertical-align:top;border-bottom:1px solid var(--line)}th{background:var(--soft);color:var(--muted);font-size:var(--th);font-weight:600}
td{white-space:nowrap}.models td:first-child{white-space:normal;overflow-wrap:break-word;min-width:37mm}td.t{white-space:normal;min-width:24mm}
th:first-child,td:first-child,.models td:nth-child(2),.models th:nth-child(2){text-align:left}tbody tr:last-child td{border-bottom:0}tr{break-inside:avoid}
ul{padding-left:20px;margin:6px 0;font-size:var(--small)}li{overflow-wrap:anywhere}
footer{margin-top:14px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:var(--tiny);line-height:1.45}a{color:var(--accent)}.end{break-inside:avoid}
@media screen and (max-width:700px){:root{--body:15px;--h1:22px;--value:18px;--table:11.5px;--th:11px}th,td{padding:5px 3px}th:first-child,td:first-child{padding-left:6px}th:last-child,td:last-child{padding-right:6px}
.hint,main{max-width:none;width:auto;margin:0;border-radius:0}main{padding:18px 12px 28px;box-shadow:none}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
@media print{:root{--body:10.5pt;--small:9.5pt;--tiny:8.5pt;--table:8.5pt;--th:8pt;--h1:17pt;--h2:12pt;--value:13pt;--gap:6px}
html{background:none}main{width:auto;max-width:none;margin:0;padding:0;border-radius:0;box-shadow:none}.hint{display:none}.wrap{overflow:visible}
h2{margin:16px 0 6px}h2::after{content:"";display:block;height:30mm;margin-bottom:-30mm}.card{padding:6px 9px;border-radius:6px}th,td{padding:3px 6px}
.note{padding:5px 10px;margin:6px 0}footer{margin-top:10px;padding-top:6px}a{color:var(--fg);text-decoration:none}}
"""


def table(rows, kind=""):
    """A table whose first row is its heading, repeated at the top of each printed page.
    Một bảng có hàng đầu là tiêu đề, lặp lại ở đầu mỗi trang khi in."""
    return '<div class="wrap"><table%s><thead>%s</thead><tbody>%s</tbody></table></div>' % (' class="%s"' % kind if kind else "", rows[0], "".join(rows[1:]))


def render_html(r, L, prices, title, env, period, screen=False):
    """The report as one HTML page: by default the paper version, to print or save as PDF; screen=True is the version a page shows.
    Báo cáo dạng một trang HTML: mặc định là bản giấy, để in hay lưu PDF; screen=True là bản để một trang web hiện."""
    e = html.escape
    made = show_dates(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), L)
    if screen:
        style = CSS
    else:
        # the title goes into the CSS of the page's foot: nothing in it may end the string or the style
        # tiêu đề nằm trong CSS của chân trang: không gì trong đó được làm hết chuỗi hay hết khối style
        foot = "".join("\\%x " % ord(c) if c in '\\"<>\n\r' else c for c in title)
        style = PAPER_CSS % {"foot": foot}
    out = ['<!doctype html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' % e(L["lang"]),
           "<title>%s</title><style>%s</style></head><body>" % (e(title), style)]
    first = show_dates(r["first"].strftime("%Y-%m-%d %H:%M"), L) if r["first"] else "-"
    last = show_dates(r["last"].strftime("%Y-%m-%d %H:%M"), L) if r["last"] else "-"
    period = show_dates(period, L)
    if screen:
        out.append("<main><h1>%s</h1>" % e(title))
        span = "%s: %s → %s UTC · " % (e(L["period"]), first, last) if r["first"] else ""
        out.append('<p class="sub">%s%s: %s%s</p>' % (span, e(L["env"]), e(env), (" · " + e(period)) if period else ""))
        out.append('<p class="note">%s</p>' % e(L["selfReported"]))
    else:
        # "Report title · project" reads as a small line with the report's kind and the project's name in large letters
        # "Tên báo cáo · dự án" thành một dòng nhỏ ghi loại báo cáo, và tên dự án chữ lớn
        kicker, name = (L["title"], title[len(L["title"]) + 3:]) if title.startswith(L["title"] + " · ") else ("", title)
        out.append('<p class="hint">%s</p><main><header class="doc">%s<h1>%s</h1><dl class="meta">' % (
            e(L["printHint"]), '<p class="kicker">%s</p>' % e(kicker) if kicker else "", e(name)))
        if r["first"]:
            out.append("<dt>%s</dt><dd>%s → %s UTC</dd>" % (e(L["period"]), first, last))
        out.append("<dt>%s</dt><dd>%s</dd>" % (e(L["env"]), e(env)))
        if period:
            out.append("<dt>%s</dt><dd>%s</dd>" % (e(L["filter"]), e(period.split(" ", 1)[-1] if period.startswith(L["filter"]) else period)))
        out.append("<dt>%s</dt><dd>%s</dd></dl></header>" % (e(L["made"]), made))
        out.append('<p class="note lead">%s</p>' % e(L["selfReported"]))
    if not r["turns"]:
        # nothing measured: one plain line instead of cards and tables full of dashes
        # chưa đo được gì: một dòng rõ ràng thay cho các ô và bảng toàn dấu gạch
        out.append('<p class="empty">%s</p>' % e(L["noTurns"]))
        return "".join(out + sources(prices, L, e))

    def card(value, label):
        return '<div class="card"><b>%s</b><span>%s</span></div>' % (e(value), e(label))

    o = r["outcomes"]
    cards = [
        card(num(r["turns"]), L["turns"]),
        card("%s / %s" % (num(o["error"]), num(o["timeout"])), L["errorsTimeouts"]),
        card(num(r["callsTurn"], 2), L["callsTurn"]),
        card(usd(r["costTurn"]) or L["noPrice"], L["costTurn"]),
        card(usd(r["costTurn"] * 1000 if r["costTurn"] is not None else None, 2) or L["noPrice"], L["cost1000"]),
        card(num(r["ms"]["avg"]) + " ms", L["avgMs"]),
        card(num(r["ms"]["p95"]) + " ms", L["p95Ms"]),
        card(num(r["ms"]["max"]) + " ms", L["maxMs"]),
    ]
    if r["ttft"]["n"]:
        cards.append(card(num(r["ttft"]["avg"]) + " / " + num(r["ttft"]["p95"]) + " ms", L["ttft"]))
    out.append('<div class="cards">%s</div>' % "".join(cards))
    # what leaves numbers out of the report stands out; what only explains it does not
    # điều làm báo cáo thiếu số thì nổi bật; điều chỉ giải thích thì không
    notes = [("", L["msNote"] % {"n": r["ms"]["n"]})]
    if r["measured"] < r["turns"]:
        notes.append((" warn", L["unmeasuredNote"] % {"n": r["turns"] - r["measured"]}))
    if r["priced"] < r["measured"]:
        notes.append((" warn", L["unpricedNote"] % {"n": r["measured"] - r["priced"], "models": ", ".join(r["unpriced"])}))
    if r["local"]:
        notes.append(("", L["localNote"] % {"models": ", ".join(r["local"])}))
    if r["long"]:
        notes.append((" warn", L["longNote"] % {"models": ", ".join(r["long"])}))
    if r["retries"]:
        notes.append(("", L["retriesNote"] % {"n": r["retries"]}))
    for kind, n in notes:
        out.append('<p class="note%s">%s</p>' % (kind, e(n)))

    out.append("<h2>%s</h2>" % e(L["tokensTurn"]))
    out.append(table(["<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>" % (e(L["input"]), e(L["output"]), e(L["cacheRead"]), e(L["cacheWrite"])),
                      "<tr>%s</tr>" % "".join("<td>%s</td>" % num(r["tokTurn"][k]) for k in TOKENS)]))

    out.append("<h2>%s</h2>" % e(L["byModel"]))
    rows = ["<tr><th>%s</th>%s</tr>" % (e(L["model"]), "".join("<th>%s</th>" % e(L[k]) for k in ("provider", "turns", "calls", "errors", "retries", "input", "output", "cacheRead", "cacheWrite", "cost", "priceDate")))]
    for (prov, model), a in sorted(r["models"].items(), key=lambda kv: -kv[1]["calls"]):
        ent = a["entry"]
        if a.get("local"):
            pdate = "-"
        elif ent and ent.get("yours"):
            pdate = ent["yours"]
        else:
            pdate = prices.doc["providers"].get(ent["provider"], {}).get("checked", "-") if ent else L["noPrice"]
        if a["unmeasuredTurns"] == a["turns"]:
            toks = ["<td>%s</td>" % e(L["notMeasured"])] * 4
        else:
            toks = ["<td>%s</td>" % num(a[k]) for k in TOKENS]
        cost = L["localCost"] if a.get("local") else usd(a["cost"]) if a["costTurns"] else L["noPrice"] if a["unpricedTurns"] else "-"
        if a["costTurns"] and a["unpricedTurns"]:
            cost += " *"
        rows.append('<tr><td>%s</td><td>%s</td>%s%s<td class="t">%s</td><td>%s</td></tr>' % (
            e(model), e(prov), "".join("<td>%s</td>" % num(a[k]) for k in ("turns", "calls", "errors", "retries")), "".join(toks), e(cost), e(show_dates(pdate, L))))
    out.append(table(rows, "models"))

    if r["alt"]:
        out.append("<h2>%s</h2>" % e(L["altTitle"]))
        out.append('<p class="note">%s</p>' % e(L["altNote"]))
        rows = ["<tr><th>%s</th><th>%s</th><th>%s</th></tr>" % (e(L["model"]), e(L["costTurn"]), e(L["cost1000"]))]
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(L["current"]), e(usd(r["costTurn"]) or L["noPrice"]), e(usd(r["costTurn"] * 1000, 2) if r["costTurn"] is not None else L["noPrice"])))
        for a in r["alt"]:
            c = a["costTurn"]
            rows.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(a["model"]), e(usd(c) if c is not None else L["noPrice"]), e(usd(c * 1000, 2) if c is not None else L["noPrice"])))
        out.append(table(rows))

    out.append("<h2>%s</h2>" % e(L["byDay"]))
    rows = ["<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>" % tuple(e(L[k]) for k in ("day", "turns", "errorsTimeouts", "avgMs", "p95Ms", "cost"))]
    for day, d in sorted(r["days"].items()):
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            show_dates(day, L), num(d["turns"]), num(d["errors"]), num(avg(d["ms"])), num(p95(d["ms"])), e(usd(d["cost"]) if d["costTurns"] else "-")))
    out.append(table(rows))

    return "".join(out + sources(prices, L, e))


def sources(prices, L, e):
    """The end of the report: where each price comes from, and when the report was made.
    Phần cuối báo cáo: mỗi giá lấy từ đâu, và báo cáo làm lúc nào."""
    out = ['<section class="end"><h2>%s</h2><ul>' % e(L["sources"])]
    for prov, p in sorted(prices.doc.get("providers", {}).items()):
        if p.get("yours") or not str(p.get("source", "")).startswith("https://"):
            continue
        out.append('<li>%s: <a href="%s">%s</a> (%s %s)</li>' % (e(prov), e(p["source"]), e(p["source"]), e(L["checked"]), e(show_dates(p["checked"], L))))
    for name in prices.yours:
        out.append("<li>%s</li>" % e(L["yourPrices"] % {"file": name}))
    out.append("</ul>")
    out.append("<footer>%s</footer></section></main></body></html>" % e(L["footer"] % {"made": show_dates(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), L)}))
    return out


def _blank(v):
    return "" if v is None else v


def write_csv(path, r):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_text(r))


def csv_text(r):
    """The CSV of the report, as text.
    CSV của báo cáo, dạng chữ."""
    f = io.StringIO()
    fields = ["scope", "name", "provider", "turns", "calls", "errors", "retries", "input", "output", "cacheRead", "cacheWrite", "costUSD", "avgMs", "p95Ms", "maxMs", "priceNote"]
    w = csv.writer(f, lineterminator="\n")
    w.writerow(fields)

    def money(p):
        return "" if p is None else "%.9f" % (p / PICO)
    tok = r["tokTurn"]
    w.writerow(["perTurnAverage", "all", "", r["turns"], "%.3f" % (r["callsTurn"] or 0), "", "", *("" if tok[k] is None else "%.1f" % tok[k] for k in TOKENS),
                money(r["costTurn"]), "" if r["ms"]["avg"] is None else "%.1f" % r["ms"]["avg"], _blank(r["ms"]["p95"]), _blank(r["ms"]["max"])])
    w.writerow(["per1000Turns", "all", "", 1000, "", "", "", "", "", "", "", money(r["costTurn"] * 1000 if r["costTurn"] is not None else None), "", "", ""])
    for (prov, model), a in sorted(r["models"].items()):
        none = a["unmeasuredTurns"] == a["turns"]
        w.writerow(["modelTotal", model, prov, a["turns"], a["calls"], a["errors"], a["retries"],
                    *("" if none else a[k] for k in TOKENS), money(a["cost"]) if a["costTurns"] else "", "", "", "",
                    "local" if a.get("local") else "noPrice" if a["unpricedTurns"] else ""])
    for day, d in sorted(r["days"].items()):
        w.writerow(["dayTotal", day, "", d["turns"], "", d["errors"], "", "", "", "", "", money(d["cost"]) if d["costTurns"] else "",
                    "" if not d["ms"] else "%.1f" % avg(d["ms"]), _blank(p95(d["ms"])), max(d["ms"]) if d["ms"] else ""])
    for a in r["alt"]:
        w.writerow(["estimateSameTokens", a["model"], "", "", "", "", "", "", "", "", "", money(a["costTurn"]), "", "", ""])
    return f.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cost and speed report from ai-meter JSON lines")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=".")
    ap.add_argument("--lang", default="en", choices=("en", "vi"))
    ap.add_argument("--env", default="prod", choices=("prod", "test", "all"))
    ap.add_argument("--from", dest="since")
    ap.add_argument("--to", dest="until")
    ap.add_argument("--compare", nargs="*", default=[])
    ap.add_argument("--prices", default=os.path.join(HERE, "prices.json"))
    ap.add_argument("--add-prices", action="append", default=[], help="your own price file, on top of --prices; can be given more than once")
    ap.add_argument("--title")
    a = ap.parse_args(argv)
    L = load_labels(a.lang)
    prices = Prices(a.prices, a.add_prices)
    turns, skipped, dupes = read_lines(a.files)
    if a.env != "all":
        turns = [t for t in turns if t["env"] == a.env]
    if a.since:
        turns = [t for t in turns if t["at"].strftime("%Y-%m-%d") >= a.since]
    if a.until:
        turns = [t for t in turns if t["at"].strftime("%Y-%m-%d") <= a.until]
    r = analyse(turns, prices, a.compare)
    os.makedirs(a.out, exist_ok=True)
    period = ""
    if a.since or a.until:
        period = "%s %s → %s" % (L["filter"], a.since or "…", a.until or "…")
    title = a.title or L["title"]
    with open(os.path.join(a.out, "ai-cost-report.html"), "w", encoding="utf-8") as f:
        f.write(render_html(r, L, prices, title, a.env, period))
    write_csv(os.path.join(a.out, "ai-cost-report.csv"), r)
    summary = {"turns": r["turns"], "measured": r["measured"], "priced": r["priced"], "skippedLines": skipped, "duplicateLines": dupes,
               "unpricedModels": r["unpriced"], "costPerTurnUSD": None if r["costTurn"] is None else r["costTurn"] / PICO,
               "p95Ms": r["ms"]["p95"], "html": os.path.join(a.out, "ai-cost-report.html"), "csv": os.path.join(a.out, "ai-cost-report.csv")}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
