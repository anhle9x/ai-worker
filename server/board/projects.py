"""AI projects and applications that measure their own cost and speed (skills/ai-cost-report) and send it to the board.
  Dự án hay ứng dụng AI tự đo chi phí và tốc độ của mình (skills/ai-cost-report) rồi gửi lên bảng.

A project sends turns in the meter's line format with a key an admin made; each turn is cleaned by the same code the report
uses (costreport.py, a copy of skills/ai-cost-report/report.py), so an unknown field is dropped and a bad line is refused.
  Dự án gửi các lượt theo định dạng dòng của bộ đo, bằng khoá do quản trị tạo; mỗi lượt được làm sạch bằng đúng code mà
  báo cáo dùng (costreport.py, bản sao của skills/ai-cost-report/report.py), nên trường lạ bị bỏ và dòng sai bị từ chối.
Money is never stored: it is worked out from the tokens and the price file each time someone looks.
  Không bao giờ lưu tiền: tiền được tính từ token và bảng giá mỗi lần có người xem.
"""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

from board import costreport
from board.daily import keep_from
from board.db import data_db, dumps
from board.settings import KIND_PROJECT, PROJECT_SEND_MAX_TURNS, PROJECT_TURN_KEEP_DAYS, PROJECT_TURNS_PER_DAY
from board.stores import DocumentStore

COUNTS = ("calls", "errors", "retries", "unmeasured", "input", "output", "cacheRead", "cacheWrite", "cacheWriteLong")
COLUMNS = ("calls", "errors", "retries", "unmeasured", "input", "output", "cache_read", "cache_write", "cache_write_long")
# prices an admin pasted on the Admin page, in the shape of skills/ai-cost-report/my-prices.example.json; they go on top of prices.json
# giá quản trị dán trên trang Quản trị, theo dạng của skills/ai-cost-report/my-prices.example.json; đè lên prices.json
PRICES = DocumentStore(data_db(), "project-prices")
PRICES_MAX_BYTES = 64 * 1024
PRICES_MAX_MODELS = 500


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def stored_turn(t: dict, raw: dict) -> dict:
    """A turn cleaned by costreport.clean_line, back in the line format with only the known fields.
    Một lượt đã làm sạch bằng costreport.clean_line, trở lại định dạng dòng với đúng các trường đã biết."""
    line = {"v": 1, "turnId": t["turnId"], "at": t["at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "durationMs": t["durationMs"], "outcome": t["outcome"], "env": t["env"], "models": []}
    if t["ttftMs"] is not None:
        line["ttftMs"] = t["ttftMs"]
    for m, sent in zip(t["models"], raw["models"]):
        row = {"provider": m["provider"], "model": m["model"]}
        row.update({k: m[k] for k in COUNTS})
        if sent.get("input") is None and sent.get("output") is None:
            # every answered call lacked usage: the tokens are unknown, not zero
            # mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
            row.update({k: None for k in costreport.COUNTS})
        line["models"].append(row)
    return line


def clean_batch(body, now: float) -> tuple:
    """The turns of one send that may be kept, and how many were refused. A turn older than the days kept, or more than a day ahead, is refused.
    Các lượt của một lần gửi được giữ, và số lượt bị từ chối. Lượt cũ hơn số ngày giữ, hoặc sớm hơn một ngày, bị từ chối."""
    if not isinstance(body, dict) or not isinstance(body.get("turns"), list) or len(body["turns"]) > PROJECT_SEND_MAX_TURNS:
        return None, 0
    keep, refused = [], 0
    oldest, newest = now - PROJECT_TURN_KEEP_DAYS * 86400, now + 86400
    for raw in body["turns"]:
        t = costreport.clean_line(raw)
        if t is None or not oldest <= t["at"].timestamp() <= newest:
            refused += 1
            continue
        keep.append(stored_turn(t, raw))
    return keep, refused


class ProjectStore:
    """The turns and the daily totals of every project, in the data database. The project is the id of its key.
    Các lượt và tổng theo ngày của mọi dự án, trong cơ sở dữ liệu số liệu. Dự án là id của khoá."""

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()
        # turns taken per project on the current UTC day, whatever day the turns say they are from; in memory, so a restart starts it again
        # số lượt đã nhận của mỗi dự án trong ngày UTC hiện tại, bất kể lượt tự ghi là ngày nào; trong bộ nhớ, nên khởi động lại thì đếm lại
        self.received = {}

    def add(self, project: str, name: str, turns: list, now: float) -> dict:
        """Keep the turns not seen before, up to the day's limit; add each to the daily totals once.
        Giữ các lượt chưa thấy, tới giới hạn của ngày; cộng mỗi lượt vào tổng theo ngày đúng một lần."""
        accepted = duplicates = over = 0
        today = utc_day(now)
        with self.lock, self.db.tx() as c:
            if any(day != today for _, day in self.received):
                self.received = {k: v for k, v in self.received.items() if k[1] == today}
            room = PROJECT_TURNS_PER_DAY - self.received.get((project, today), 0)
            for line in turns:
                if accepted >= room:
                    over += 1
                    continue
                at = costreport.parse_time(line["at"]).timestamp()
                cur = c.execute("INSERT OR IGNORE INTO project_turns VALUES (?, ?, ?, ?, ?, ?)",
                                (project, line["turnId"], int(at * 1000), utc_day(at), line["env"], dumps(line)))
                if cur.rowcount != 1:
                    duplicates += 1
                    continue
                accepted += 1
                # every turn adds one to the row with no provider and no model, so a day's turns are counted once even when a turn used
                # several models (or none); each model's row counts the turns that used it and its calls and tokens
                # mỗi lượt cộng một vào dòng không hãng, không model, để số lượt của ngày chỉ đếm một lần dù lượt dùng nhiều model
                # (hay không model nào); dòng của từng model đếm số lượt đã dùng nó cùng số lần gọi và token
                for m in [{"provider": "", "model": ""}] + line["models"]:
                    numbers = [int(m.get(k) or 0) for k in COUNTS]
                    c.execute("INSERT OR IGNORE INTO project_daily (project, name, day, env, provider, model) VALUES (?, ?, ?, ?, ?, ?)",
                              (project, name, utc_day(at), line["env"], m["provider"], m["model"]))
                    c.execute("UPDATE project_daily SET name = ?, turns = turns + 1, " + ", ".join("%s = %s + ?" % (k, k) for k in COLUMNS) +
                              " WHERE project = ? AND day = ? AND env = ? AND provider = ? AND model = ?",
                              [name, *numbers, project, utc_day(at), line["env"], m["provider"], m["model"]])
            self.received[(project, today)] = self.received.get((project, today), 0) + accepted
        return {"accepted": accepted, "duplicates": duplicates, "overDailyLimit": over}

    def sweep(self, now: float) -> None:
        """Turns go after PROJECT_TURN_KEEP_DAYS; daily totals when the people's daily totals go.
        Lượt bị xoá sau PROJECT_TURN_KEEP_DAYS ngày; tổng theo ngày bị xoá cùng lúc với tổng theo ngày của từng người."""
        cutoff = int((now - PROJECT_TURN_KEEP_DAYS * 86400) * 1000)
        first_day = keep_from(datetime.fromtimestamp(now, timezone.utc).date()).isoformat()
        with self.lock, self.db.tx() as c:
            c.execute("DELETE FROM project_turns WHERE at < ?", (cutoff,))
            c.execute("DELETE FROM project_daily WHERE day < ?", (first_day,))

    def names(self) -> dict:
        """{project id: the name it last had}, for every project that has numbers, live key or not.
        {id dự án: tên gần nhất}, cho mọi dự án có số liệu, khoá còn hay không."""
        return {r[0]: r[1] for r in self.db.rows("SELECT project, name FROM project_daily GROUP BY project")}

    def turns(self, project: str, first: str, last: str, env: str) -> list:
        """The kept turns of one project between two UTC days, as the report reads them.
        Các lượt còn giữ của một dự án giữa hai ngày UTC, đúng dạng báo cáo đọc."""
        args = [project, first, last] + ([env] if env != "all" else [])
        out = []
        for (body,) in self.db.rows("SELECT body FROM project_turns WHERE project = ? AND day >= ? AND day <= ?" +
                                    (" AND env = ?" if env != "all" else "") + " ORDER BY at", args):
            t = costreport.clean_line(json.loads(body))
            if t:
                out.append(t)
        return out

    def days(self, project: str, first: str, last: str, env: str) -> list:
        """The daily totals of one project: [{day, turns, calls, errors, input, output, ...}], one row per day and model.
        Tổng theo ngày của một dự án: [{day, turns, calls, errors, input, output, ...}], mỗi ngày và model một dòng."""
        args = [project, first, last] + ([env] if env != "all" else [])
        cols = ("day", "provider", "model", "turns") + COLUMNS
        rows = self.db.rows("SELECT day, provider, model, SUM(turns), " + ", ".join("SUM(%s)" % k for k in COLUMNS) +
                            " FROM project_daily WHERE project = ? AND day >= ? AND day <= ?" + (" AND env = ?" if env != "all" else "") +
                            " GROUP BY day, provider, model ORDER BY day", args)
        return [dict(zip(cols, r)) for r in rows]


PROJECTS = ProjectStore(data_db())


def known(now: float) -> dict:
    """{project id: name}: every live key, then every project that still has numbers after its key went.
    {id dự án: tên}: mọi khoá còn hạn, rồi mọi dự án còn số liệu sau khi khoá đã bị thu hồi."""
    from board.stores import TV
    out = {x["id"]: x["name"] for x in TV.list_screens(now) if x["kind"] == KIND_PROJECT}
    for k, v in PROJECTS.names().items():
        out.setdefault(k, v)
    return out


def daily_rows(project: str, first: str, last: str, env: str) -> list:
    """One row per day from the totals kept 13 months: turns, calls, tokens, and the cost at that day's prices.
    Mỗi ngày một dòng từ các tổng giữ 13 tháng: số lượt, lần gọi, token, và tiền theo giá của ngày đó."""
    p, out = prices(), {}
    for r in PROJECTS.days(project, first, last, env):
        d = out.setdefault(r["day"], {"day": r["day"], "turns": 0, "calls": 0, "errors": 0, "input": 0, "output": 0, "cost": 0, "noPrice": False, "unmeasured": 0})
        if not r["provider"] and not r["model"]:
            d["turns"] += r["turns"]
            continue
        row = {"input": r["input"], "output": r["output"], "cacheRead": r["cache_read"], "cacheWrite": r["cache_write"], "cacheWriteLong": r["cache_write_long"]}
        for k in ("calls", "errors", "unmeasured"):
            d[k] += r[k]
        d["input"] += r["input"] + r["cache_read"] + r["cache_write"]
        d["output"] += r["output"]
        if p.is_local(r["provider"], r["model"]):
            continue
        c = p.cost(row, p.at(r["model"], r["day"]))
        if c is None:
            d["noPrice"] = True
        else:
            d["cost"] += c
    return [out[k] for k in sorted(out)]


def clean_prices(doc) -> dict:
    """An admin's price file, kept only in the shape the report reads: names checked, prices whole numbers or null.
    File giá của quản trị, chỉ giữ đúng dạng báo cáo đọc: kiểm tên, giá là số nguyên hoặc null."""
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    out = {"name": "admin", "providers": {}, "localProviders": [], "models": []}
    for prov, info in (doc.get("providers") or {}).items():
        if isinstance(prov, str) and costreport.PROVIDER_RE.match(prov) and isinstance(info, dict):
            source = str(info.get("source") or "")[:200]
            checked = str(info.get("checked") or "")
            out["providers"][prov] = {"source": source if source.startswith("https://") else "", "checked": checked if len(checked) == 10 else ""}
    out["localProviders"] = [p for p in doc.get("localProviders") or [] if isinstance(p, str) and costreport.PROVIDER_RE.match(p)][:50]
    models = doc.get("models") or []
    if not isinstance(models, list) or len(models) > PRICES_MAX_MODELS:
        raise ValueError("models")
    for m in models:
        if not isinstance(m, dict) or not isinstance(m.get("model"), str) or not costreport.MODEL_RE.match(m["model"]):
            raise ValueError("model name")
        prov = str(m.get("provider") or "other")
        if not costreport.PROVIDER_RE.match(prov):
            raise ValueError("provider name")
        rows = []
        for r in m.get("prices") or []:
            if not isinstance(r, dict):
                raise ValueError("price row")
            frm = r.get("from")
            if frm is not None and not (isinstance(frm, str) and len(frm) == 10 and frm[4] == "-" and frm[7] == "-"):
                raise ValueError("from")
            row = {"from": frm}
            for k in costreport.COUNTS:
                v = r.get(k)
                if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 10 ** 12):
                    raise ValueError("price")
                row[k] = v
            rows.append(row)
        out["models"].append({"provider": prov, "model": m["model"], "prices": rows, **({"local": True} if m.get("local") is True else {})})
    return out


def prices() -> "costreport.Prices":
    extra = PRICES.read()
    return costreport.Prices(os.path.join(costreport.HERE, "prices.json"), [extra] if extra else [])


def span(first: str, last: str, now: float) -> tuple:
    """Two UTC days from the page, checked; by default the last 7 days.
    Hai ngày UTC từ trang, đã kiểm; mặc định 7 ngày gần nhất."""
    today = datetime.fromtimestamp(now, timezone.utc).date()
    try:
        a = datetime.strptime(first, "%Y-%m-%d").date() if first else today - timedelta(days=6)
        b = datetime.strptime(last, "%Y-%m-%d").date() if last else today
    except ValueError:
        a, b = today - timedelta(days=6), today
    if a > b:
        a, b = b, a
    return a.isoformat(), b.isoformat()


def report(project: str, name: str, first: str, last: str, env: str, lang: str, now: float) -> tuple:
    """The report of one project for some days: (the analysis, the labels, the prices, whether turns before the kept days were asked for).
    Báo cáo của một dự án trong vài ngày: (phân tích, nhãn, bảng giá, có hỏi các lượt trước số ngày còn giữ không)."""
    p = prices()
    r = costreport.analyse(PROJECTS.turns(project, first, last, env), p)
    oldest = utc_day(now - PROJECT_TURN_KEEP_DAYS * 86400)
    return r, costreport.load_labels(lang), p, first < oldest


def report_html(project: str, name: str, first: str, last: str, env: str, lang: str, now: float) -> str:
    r, labels, p, cut = report(project, name, first, last, env, lang, now)
    title = "%s · %s" % (labels["title"], name)
    period = "%s %s → %s" % (labels["filter"], first, last)
    return costreport.render_html(r, labels, p, title, env, period)


def report_csv(project: str, name: str, first: str, last: str, env: str, lang: str, now: float) -> str:
    r = report(project, name, first, last, env, lang, now)[0]
    return costreport.csv_text(r)
