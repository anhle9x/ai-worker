"""Use per person per day, kept for months: built from the hourly numbers each computer sends, read back as weeks and months.
Mức dùng của từng người theo từng ngày, giữ nhiều tháng: dựng từ số liệu theo giờ mỗi máy gửi, đọc ra theo tuần và theo tháng."""

import threading
from datetime import date, datetime, timedelta

from board.devices import person_key, person_name
from board.settings import DAILY_CHART_WEEKS, DAILY_KEEP_MONTHS, DAILY_RECOUNT_DAYS, LOCAL_TZ

WORKERS = ("gemini", "chatgpt", "gemma")
# the numbers of one row, in the order of the table's columns
# các con số của một dòng, theo đúng thứ tự cột của bảng
NUMBERS = ("usd", "tokensIn", "tokensOut") + WORKERS
COLUMNS = "day, person, name, account, branch, branch_name, usd, tokens_in, tokens_out, gemini, chatgpt, gemma"
# the spans the board compares; "SameDays" is the start of the span before, cut to as many days as the current span has so far
# các khoảng mà bảng đem so; "SameDays" là phần đầu của khoảng trước, cắt cho bằng số ngày khoảng hiện tại đã có
PERIODS = ("week", "weekBefore", "weekBeforeSameDays", "month", "monthBefore", "monthBeforeSameDays", "monthYearAgo")
# the row of the meta table that holds the first day ever counted on this server
# dòng của bảng meta giữ ngày đầu tiên từng được đếm trên máy chủ này
SINCE_KEY = "daily_since"


def local_day(now: float) -> date:
    return datetime.fromtimestamp(now, LOCAL_TZ).date()


def totals_by_day(devices: list, now: float) -> dict:
    """Add up the hourly numbers of every computer into {day: {person: numbers}}, for today and the days before it that every computer still
    holds in full. A computer keeps 8 days of hours, so the last DAILY_RECOUNT_DAYS days are whole; an older day would come out short.
    Cộng số liệu theo giờ của mọi máy thành {ngày: {người: các con số}}, cho hôm nay và những ngày trước đó mà máy nào cũng còn giữ đủ.
    Mỗi máy giữ 8 ngày theo giờ, nên DAILY_RECOUNT_DAYS ngày gần nhất là trọn vẹn; ngày cũ hơn sẽ bị thiếu."""
    today = local_day(now)
    first = today - timedelta(days=DAILY_RECOUNT_DAYS - 1)
    out = {}
    for m in devices:
        if not isinstance(m, dict) or m.get("v") != 1:
            continue
        key = person_key(m)
        for field in ("ledger", "tasks"):
            table = m.get(field)
            for hour, v in (table.items() if isinstance(table, dict) else ()):
                try:
                    day = datetime.fromtimestamp(int(hour) * 3600, LOCAL_TZ).date()
                except (ValueError, OverflowError, OSError):
                    continue
                if not first <= day <= today or not isinstance(v, dict):
                    continue
                r = out.setdefault(day.isoformat(), {}).setdefault(key, {"name": person_name(m), "account": str(m.get("account") or ""), **dict.fromkeys(NUMBERS, 0)})
                if field == "ledger":
                    r["usd"] += float(v.get("usd") or 0)
                    r["tokensIn"] += int(v.get("input") or 0) + int(v.get("cacheRead") or 0) + int(v.get("cacheWrite") or 0)
                    r["tokensOut"] += int(v.get("output") or 0)
                else:
                    for worker in WORKERS:
                        r[worker] += int(v.get(worker) or 0)
    return out


def keep_from(today: date) -> date:
    """The oldest day still kept: the first day of the month DAILY_KEEP_MONTHS - 1 months before this one, so the same month of last year is whole.
    Ngày cũ nhất còn giữ: ngày đầu của tháng cách tháng này DAILY_KEEP_MONTHS - 1 tháng, để tháng cùng kỳ năm trước còn trọn vẹn."""
    n = today.year * 12 + today.month - 1 - (DAILY_KEEP_MONTHS - 1)
    return date(n // 12, n % 12 + 1, 1)


def periods(today: date) -> dict:
    """First and last day of each span in PERIODS. A week starts on Monday.
    Ngày đầu và ngày cuối của từng khoảng trong PERIODS. Tuần bắt đầu từ thứ Hai."""
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    month_before_end = month - timedelta(days=1)
    month_before = month_before_end.replace(day=1)
    year_ago = date(month.year - 1, month.month, 1)
    year_ago_end = date(year_ago.year + (year_ago.month == 12), year_ago.month % 12 + 1, 1) - timedelta(days=1)
    return {
        "week": (week, today),
        "weekBefore": (week - timedelta(days=7), week - timedelta(days=1)),
        "weekBeforeSameDays": (week - timedelta(days=7), today - timedelta(days=7)),
        "month": (month, today),
        "monthBefore": (month_before, month_before_end),
        "monthBeforeSameDays": (month_before, min(month_before_end, month_before + timedelta(days=today.day - 1))),
        "monthYearAgo": (year_ago, year_ago_end),
    }


def chart_spans(today: date) -> dict:
    """The weeks and the months the charts show, oldest first, as (first day, last day, day the span really ends): the last DAILY_CHART_WEEKS
    weeks and every month still kept. The current week and month stop at today, so their last day is before their real end.
    Các tuần và các tháng mà biểu đồ hiện, cũ trước, dạng (ngày đầu, ngày cuối, ngày khoảng đó thật sự kết thúc): DAILY_CHART_WEEKS tuần
    gần nhất và mọi tháng còn được giữ. Tuần và tháng hiện tại dừng ở hôm nay, nên ngày cuối của chúng đứng trước ngày kết thúc thật."""
    week = today - timedelta(days=today.weekday())
    weeks = []
    for back in range(DAILY_CHART_WEEKS - 1, -1, -1):
        start = week - timedelta(days=7 * back)
        weeks.append((start, min(today, start + timedelta(days=6)), start + timedelta(days=6)))
    months, start = [], keep_from(today)
    while start <= today:
        following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        months.append((start, min(today, following - timedelta(days=1)), following - timedelta(days=1)))
        start = following
    return {"weeks": weeks, "months": months}


def chart_series(day_rows: list, today: date, since: str) -> dict:
    """Cost per week and per month for the charts, from rows of (day, office id, dollars). Each span says how much of it the stored days
    cover (kept) and whether it is a whole week or month (whole); officeWeeks holds each office's dollars for the same weeks.
    Chi phí theo tuần và theo tháng cho biểu đồ, từ các dòng (ngày, mã văn phòng, đô la). Mỗi khoảng cho biết các ngày đã lưu phủ được
    bao nhiêu (kept) và nó có phải một tuần hay một tháng trọn vẹn không (whole); officeWeeks giữ số đô la của từng văn phòng cho đúng các tuần đó."""
    out = {}
    for kind, spans in chart_spans(today).items():
        series = []
        for a, b, end in spans:
            a, b = a.isoformat(), b.isoformat()
            kept = "none" if not since or since > b else "all" if since <= a else "part"
            series.append({"from": a, "to": b, "kept": kept, "whole": kept == "all" and end <= today, "usd": 0.0})
        out[kind] = series
    office_weeks = {}
    for day, branch, usd in day_rows:
        for kind in ("weeks", "months"):
            for i, span in enumerate(out[kind]):
                if span["from"] <= day <= span["to"]:
                    span["usd"] += usd
                    if kind == "weeks":
                        office_weeks.setdefault(branch, [0.0] * len(out[kind]))[i] += usd
                    break
    for kind in ("weeks", "months"):
        for span in out[kind]:
            span["usd"] = round(span["usd"], 4)
    out["officeWeeks"] = {branch: [round(n, 4) for n in numbers] for branch, numbers in office_weeks.items()}
    return out


def summarize(rows: list, today: date, since: str, office_names: dict) -> dict:
    """Turn daily rows (in COLUMNS order, oldest first) into totals per span for the team, each office and each person.
    An office's total follows the office written on each day's row, so a person who moved counts for both offices, each for its days.
    Biến các dòng theo ngày (theo thứ tự COLUMNS, cũ trước) thành tổng theo từng khoảng cho cả đội, từng văn phòng và từng người.
    Tổng của văn phòng đi theo văn phòng ghi trên dòng của từng ngày, nên người đã chuyển chỗ được tính cho cả hai nơi, mỗi nơi theo số ngày của nó."""
    spans = {p: (a.isoformat(), b.isoformat()) for p, (a, b) in periods(today).items()}

    def blank() -> dict:
        return {p: dict.fromkeys(NUMBERS, 0) for p in PERIODS}

    team, offices, people = blank(), {}, {}
    for day, person, name, account, branch, branch_name, *numbers in rows:
        inside = [p for p, (a, b) in spans.items() if a <= day <= b]
        if not inside:
            continue
        office = offices.setdefault(branch, dict(blank(), id=branch, name=""))
        # the newest row names the office and the person
        # dòng mới nhất quyết định tên văn phòng và tên người
        office["name"] = branch_name or office["name"]
        who = people.setdefault(person, blank())
        who.update(name=name, account=account, office=branch)
        for p in inside:
            for target in (team[p], office[p], who[p]):
                for k, n in zip(NUMBERS, numbers):
                    target[k] += n
    for group in [team] + list(offices.values()) + list(people.values()):
        for p in PERIODS:
            group[p]["usd"] = round(group[p]["usd"], 4)
    for office in offices.values():
        office["name"] = office_names.get(office["id"]) or office["name"]

    def kept(a: str, b: str) -> str:
        """Whether the stored days cover a span: all of it, part of it, or none.
        Các ngày đã lưu có phủ một khoảng hay không: cả khoảng, một phần, hay không có."""
        return "none" if not since or since > b else "all" if since <= a else "part"

    return {"today": today.isoformat(), "since": since, "team": team,
            "periods": {p: {"from": a, "to": b, "kept": kept(a, b)} for p, (a, b) in spans.items()},
            "offices": sorted(offices.values(), key=lambda o: (-o["month"]["usd"], o["name"].lower())),
            "people": sorted(people.values(), key=lambda r: (-r["month"]["usd"], r["name"].lower()))}


class DailyStore:
    """The table of daily totals. Recording can run any number of times: each run counts the last DAILY_RECOUNT_DAYS days again
    and writes over what is there, so nothing is added twice. Days older than that are never touched, only deleted when they expire.
    Bảng tổng theo ngày. Việc ghi chạy bao nhiêu lần cũng được: mỗi lần đếm lại DAILY_RECOUNT_DAYS ngày gần nhất
    và ghi đè lên dòng đang có, nên không có gì bị cộng hai lần. Ngày cũ hơn thì không bao giờ bị đụng tới, chỉ bị xoá khi hết hạn."""

    def __init__(self, database):
        self.db = database
        self.lock = threading.Lock()

    def record(self, totals: dict, offices: dict, now: float) -> int:
        """Write totals_by_day() into the table; offices is {person: (office id, office name)} as of now. Returns how many rows changed.
        A day that is over keeps the office it was closed with; only today follows where the person is now.
        Ghi kết quả của totals_by_day() vào bảng; offices là {người: (mã văn phòng, tên văn phòng)} tính tới lúc này. Trả về số dòng đã đổi.
        Ngày đã qua giữ văn phòng lúc nó được chốt; chỉ hôm nay mới đi theo nơi người đó đang ở."""
        today = local_day(now)
        first, last = (today - timedelta(days=DAILY_RECOUNT_DAYS - 1)).isoformat(), today.isoformat()
        with self.lock:
            # the first run fixes the day the totals start from; a day with no use has no row, so the rows alone cannot tell
            # lần chạy đầu chốt ngày mà các tổng bắt đầu; ngày không ai dùng thì không có dòng, nên chỉ nhìn các dòng thì không biết được
            if not self.db.get_meta(SINCE_KEY):
                with self.db.tx() as c:
                    c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (SINCE_KEY, first))
            old = {(r[0], r[1]): r for r in self.db.rows("SELECT " + COLUMNS + " FROM daily WHERE day >= ? AND day <= ?", (first, last))}
            new = {}
            for day, by_person in totals.items():
                if not first <= day <= last:
                    continue
                for person, t in by_person.items():
                    numbers = (round(t["usd"], 4),) + tuple(int(t[k]) for k in NUMBERS[1:])
                    if not any(numbers):
                        continue
                    office = offices.get(person, ("", ""))
                    before = old.get((day, person))
                    if before and before[4] and day != last:
                        office = (before[4], before[5])
                    new[(day, person)] = (day, person, t["name"], t["account"], office[0], office[1]) + numbers
            gone = [k for k in old if k not in new]
            changed = [r for k, r in new.items() if old.get(k) != r]
            cutoff = keep_from(today).isoformat()
            expired = bool(self.db.rows("SELECT 1 FROM daily WHERE day < ? LIMIT 1", (cutoff,)))
            if gone or changed or expired:
                with self.db.tx() as c:
                    for day, person in gone:
                        c.execute("DELETE FROM daily WHERE day = ? AND person = ?", (day, person))
                    for r in changed:
                        c.execute("INSERT OR REPLACE INTO daily (" + COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r)
                    if expired:
                        c.execute("DELETE FROM daily WHERE day < ?", (cutoff,))
            return len(gone) + len(changed)

    def summary(self, now: float, office_names: dict) -> dict:
        """Totals of this week and this month against the spans before them, and cost per week and per month for the charts.
        Tổng của tuần này và tháng này so với các khoảng trước đó, và chi phí theo tuần, theo tháng cho biểu đồ."""
        today = local_day(now)
        spans = periods(today)
        recent = min(spans["weekBefore"][0], spans["monthBefore"][0]).isoformat()
        year_ago = tuple(d.isoformat() for d in spans["monthYearAgo"])
        rows = self.db.rows("SELECT " + COLUMNS + " FROM daily WHERE (day >= ? AND day <= ?) OR (day >= ? AND day <= ?) ORDER BY day",
                            (recent, today.isoformat()) + year_ago)
        d = summarize(rows, today, self.since(today), office_names)
        # the charts need every day still kept, but only one sum per day and office: the database adds them up
        # biểu đồ cần mọi ngày còn giữ, nhưng chỉ cần một tổng cho mỗi ngày và mỗi văn phòng: để cơ sở dữ liệu cộng
        day_rows = self.db.rows("SELECT day, branch, SUM(usd) FROM daily WHERE day >= ? AND day <= ? GROUP BY day, branch ORDER BY day",
                                (keep_from(today).isoformat(), today.isoformat()))
        series = chart_series(day_rows, today, d["since"])
        d.update(weeks=series["weeks"], months=series["months"])
        for office in d["offices"]:
            office["weeks"] = series["officeWeeks"].get(office["id"], [0.0] * len(series["weeks"]))
        return d

    def since(self, today: date) -> str:
        """The oldest day the totals cover: the first day ever counted, or the oldest day still kept once rows have started to expire. Empty before the first run.
        Ngày cũ nhất mà các tổng phủ tới: ngày đầu tiên từng được đếm, hoặc ngày cũ nhất còn giữ khi đã có dòng hết hạn. Để trống trước lần chạy đầu."""
        first = self.db.get_meta(SINCE_KEY)
        return max(first, keep_from(today).isoformat()) if first else ""

    def forget(self, who: str) -> int:
        """Delete every daily row of one person, named by account email or by name (letter case ignored). Returns how many rows went.
        Xoá mọi dòng theo ngày của một người, chỉ ra bằng email tài khoản hoặc bằng tên (không phân biệt hoa thường). Trả về số dòng đã xoá."""
        who = who.strip().lower()
        with self.lock:
            keys = [person for person, name, account in self.db.rows("SELECT DISTINCT person, name, account FROM daily") if who and who in (name.lower(), account.lower())]
            removed = 0
            with self.db.tx() as c:
                for person in keys:
                    removed += c.execute("DELETE FROM daily WHERE person = ?", (person,)).rowcount
            return removed
