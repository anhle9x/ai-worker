"""The SQL of the computers' records in one place: devices (what each computer is doing), device_hours (its hour book, one row per hour
and kind) and device_days (its totals per local day). board/devices.py keeps them in memory and decides what to write; only this file
knows the tables, so another database can take their place later without rewriting the code that uses them. Plain SQL that SQLite and
PostgreSQL both run: values only as parameters, INSERT ... ON CONFLICT ... DO UPDATE (never INSERT OR REPLACE; see UPSERT), no JSON
function of the database; the JSON is read and written by Python. Tables: docs/DATA-MODEL.md, schema version 8.
  SQL của bản ghi các máy ở một chỗ: devices (mỗi máy đang làm gì), device_hours (sổ giờ của máy, mỗi giờ mỗi loại một dòng) và
  device_days (tổng của máy theo từng ngày địa phương). board/devices.py giữ chúng trong bộ nhớ và quyết định ghi gì; chỉ file này
  biết các bảng, để sau này cơ sở dữ liệu khác thay được mà không phải viết lại mã dùng chúng. SQL thường mà SQLite và PostgreSQL
  đều chạy: giá trị chỉ qua tham số, INSERT ... ON CONFLICT ... DO UPDATE (không bao giờ INSERT OR REPLACE), không dùng hàm JSON của
  cơ sở dữ liệu; JSON do Python đọc và ghi. Các bảng: docs/DATA-MODEL.vi.md, lược đồ phiên bản 8."""

import sqlite3

# INSERT ... ON CONFLICT ... DO UPDATE came in SQLite 3.24 (2018); with an older one, as on older Linux, the same is done as an UPDATE,
# then an INSERT when no row was there
# INSERT ... ON CONFLICT ... DO UPDATE có từ SQLite 3.24 (2018); với bản cũ hơn, như trên Linux đời cũ, việc đó được làm bằng một UPDATE,
# rồi một INSERT khi chưa có dòng nào
UPSERT = sqlite3.sqlite_version_info >= (3, 24, 0)

# the numbers of one computer on one day, in the order of the columns of device_days
# các con số của một máy trong một ngày, theo thứ tự các cột của device_days
DAY_COLUMNS = ("usd_micro", "tokens_in", "tokens_out", "gemini", "chatgpt", "gemma")
# the meta row that says which offset from UTC, in seconds, device_days counted its days in
# dòng meta cho biết device_days đã đếm ngày theo độ lệch nào so với UTC, tính bằng giây
DAYS_ZONE_KEY = "device_days_tz"
# the most values in one IN (...): SQLite allows 999 parameters in older versions
# nhiều nhất bấy nhiêu giá trị trong một IN (...): SQLite bản cũ cho 999 tham số
_CHUNK = 500
_FAR = 1 << 62


def _upsert(c, table: str, keys: tuple, values: tuple, rows: list) -> None:
    """Write rows (the key columns, then the value columns), each over the row with the same key. The names are this file's own,
    never a value.
    Ghi các dòng (các cột khoá, rồi các cột giá trị), mỗi dòng đè lên dòng cùng khoá. Các tên là của chính file này, không bao giờ
    là một giá trị."""
    if UPSERT:
        c.executemany("INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (%s) DO UPDATE SET %s" % (
            table, ", ".join(keys + values), ", ".join("?" * len(keys + values)), ", ".join(keys), ", ".join("%s = excluded.%s" % (v, v) for v in values)), rows)
        return
    update = "UPDATE %s SET %s WHERE %s" % (table, ", ".join("%s = ?" % v for v in values), " AND ".join("%s = ?" % k for k in keys))
    insert = "INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(keys + values), ", ".join("?" * len(keys + values)))
    for r in rows:
        if c.execute(update, tuple(r[len(keys):]) + tuple(r[:len(keys)])).rowcount == 0:
            c.execute(insert, r)


# writes held for a batch, by connection: see held()
# các lệnh ghi đang giữ cho một lô, theo kết nối: xem held()
_HELD = {}


class Held:
    """The writes of one batch of the receiver, held to be written together, one executemany per kind of write, before the batch's
    transaction ends. A read of a computer that has writes held of what it reads writes everything held first, so a read always sees
    what was written before it. The writes of one computer keep their order; between computers it does not matter, their rows never
    meet. A computer written again in a later row of the batch writes what is held first, so the order of kinds below holds.
    Các lệnh ghi của một lô của bộ nhận, được giữ để ghi chung, mỗi loại lệnh một executemany, trước khi giao dịch của lô kết thúc.
    Đọc một máy đang có lệnh ghi được giữ cho thứ nó đọc thì ghi hết những gì đang giữ trước, nên lần đọc luôn thấy những gì đã ghi
    trước nó. Các lệnh ghi của một máy giữ thứ tự; giữa các máy thì không quan trọng, dòng của chúng không bao giờ chạm nhau. Máy được
    ghi lại ở một dòng sau trong lô thì ghi những gì đang giữ trước, để thứ tự các loại bên dưới luôn đúng."""

    # the order the kinds are written in: within one row of a batch, every write of one computer comes in this order
    # thứ tự ghi các loại: trong một dòng của lô, mọi lệnh ghi của một máy đều đến theo thứ tự này
    ORDER = ("state", "days_of", "hours", "hours_drop", "days", "days_drop")

    def __init__(self, c):
        self.c = c
        self.rows = {k: [] for k in self.ORDER}
        # (device, what) with writes held: what is "devices", "days" or "hours:" and a kind
        # (máy, thứ) đang có lệnh ghi được giữ: thứ là "devices", "days" hoặc "hours:" kèm một loại
        self.touched = set()
        # the devices written by the rows before the one being written
        # các máy được ghi bởi những dòng trước dòng đang ghi
        self.before, self.now = set(), set()

    def next_row(self) -> None:
        self.before |= self.now
        self.now = set()

    def hold(self, what: str, rows: list, touched: set) -> None:
        devices = {d for d, _ in touched}
        if devices & self.before:
            self.write()
        self.rows[what].extend(rows)
        self.touched |= touched
        self.now |= devices

    def write(self) -> None:
        """Write everything held, in the order of ORDER.
        Ghi mọi thứ đang giữ, theo thứ tự của ORDER."""
        c, rows = self.c, self.rows
        if rows["state"]:
            _upsert(c, "devices", ("device",), ("account", "name", "seen_at", "body"), rows["state"])
        if rows["days_of"]:
            c.executemany("DELETE FROM device_days WHERE device = ?", rows["days_of"])
        if rows["hours"]:
            _put_hours(c, rows["hours"])
        if rows["hours_drop"]:
            c.executemany("DELETE FROM device_hours WHERE hour = ? AND kind = ? AND device = ?", rows["hours_drop"])
        if rows["days"]:
            _upsert(c, "device_days", ("day", "device"), DAY_COLUMNS, rows["days"])
        if rows["days_drop"]:
            c.executemany("DELETE FROM device_days WHERE day = ? AND device = ?", rows["days_drop"])
        self.rows = {k: [] for k in self.ORDER}
        self.touched = set()
        self.before = set()


class held:
    """Hold the writes made through this file on connection c until the block ends, then write them together (see Held). If the block
    raises, what is held is dropped: the caller's transaction is taken back anyway.
    Giữ các lệnh ghi qua file này trên kết nối c tới hết khối, rồi ghi chung (xem Held). Nếu khối báo lỗi, những gì đang giữ bị bỏ:
    giao dịch của bên gọi đằng nào cũng bị rút lại."""

    def __init__(self, c):
        self.held = Held(c)

    def __enter__(self) -> Held:
        _HELD[id(self.held.c)] = self.held
        return self.held

    def __exit__(self, kind, value, trace) -> None:
        _HELD.pop(id(self.held.c), None)
        if kind is None:
            self.held.write()


def _hold(c, what: str, rows: list, touched: set) -> bool:
    h = _HELD.get(id(c))
    if h is None:
        return False
    if rows:
        h.hold(what, rows, touched)
    return True


def _before_read(c, device: str = None, *what) -> None:
    """Write what is held before a read of what of device (of everything when device is None).
    Ghi những gì đang giữ trước khi đọc thứ what của device (của mọi thứ khi device là None)."""
    h = _HELD.get(id(c))
    if h is not None and h.touched and (device is None or any((device, w) in h.touched for w in what)):
        h.write()


def _chunks(items: list):
    for i in range(0, len(items), _CHUNK):
        yield items[i:i + _CHUNK]


def states(c) -> list:
    _before_read(c)
    return c.execute("SELECT device, seen_at, body FROM devices").fetchall()


def state(c, device: str):
    _before_read(c, device, "devices")
    return c.execute("SELECT device, seen_at, body FROM devices WHERE device = ?", (device,)).fetchone()


def put_state(c, device: str, account: str, name: str, seen_at: int, body: str) -> None:
    rows = [(device, account, name, seen_at, body)]
    if not _hold(c, "state", rows, {(device, "devices")}):
        _upsert(c, "devices", ("device",), ("account", "name", "seen_at", "body"), rows)


def set_body(c, device: str, body: str) -> None:
    _before_read(c)
    c.execute("UPDATE devices SET body = ? WHERE device = ?", (body, device))


def drop_devices(c, names: list) -> None:
    """Delete computers with their hours and their days.
    Xoá các máy cùng các giờ và các ngày của chúng."""
    _before_read(c)
    for part in _chunks(list(names)):
        marks = ", ".join("?" * len(part))
        for table in ("devices", "device_hours", "device_days"):
            c.execute("DELETE FROM %s WHERE device IN (%s)" % (table, marks), part)


def hours(c, device: str, kinds: tuple, lo: int = -_FAR, hi: int = _FAR, stamped: bool = False) -> list:
    """One computer's rows (kind, hour, body) of these kinds with lo <= hour < hi, oldest first; with stamped, (kind, hour, body, sent_at).
    Các dòng (loại, giờ, nội dung) của một máy thuộc các loại này với lo <= giờ < hi, cũ trước mới sau; với stamped, (loại, giờ, nội
    dung, sent_at)."""
    _before_read(c, device, *("hours:" + k for k in kinds))
    out = []
    for kind in kinds:
        out += c.execute("SELECT kind, hour, body%s FROM device_hours WHERE device = ? AND kind = ? AND hour >= ? AND hour < ? ORDER BY hour"
                         % (", sent_at" if stamped else ""), (device, kind, lo, hi)).fetchall()
    return out


def hour_numbers(c, device: str, kind: str) -> list:
    """The hours one computer has of one kind, newest first, without their bodies.
    Các giờ một máy có của một loại, mới trước cũ sau, không kèm nội dung."""
    _before_read(c, device, "hours:" + kind)
    return [h for (h,) in c.execute("SELECT hour FROM device_hours WHERE device = ? AND kind = ? ORDER BY hour DESC", (device, kind))]


def recent(c, lo: int) -> list:
    """Every computer's ledger and tasks rows (device, kind, hour, body) from hour lo on: the key starts with the hour, so this reads
    only the end of the table.
    Các dòng ledger và tasks (máy, loại, giờ, nội dung) của mọi máy từ giờ lo trở đi: khoá bắt đầu bằng giờ, nên chỉ đọc phần cuối bảng."""
    _before_read(c)
    return c.execute("SELECT device, kind, hour, body FROM device_hours WHERE hour >= ? AND kind IN ('ledger', 'tasks')", (lo,)).fetchall()


def recent_blocks(c, lo: int) -> list:
    """Every computer's blocks rows (device, hour, body) from hour lo on, through their own small index.
    Các dòng blocks (máy, giờ, nội dung) của mọi máy từ giờ lo trở đi, qua chỉ mục nhỏ riêng của chúng."""
    _before_read(c)
    return c.execute("SELECT device, hour, body FROM device_hours WHERE kind = 'blocks' AND hour >= ?", (lo,)).fetchall()


def all_hours(c) -> list:
    _before_read(c)
    return c.execute("SELECT device, kind, hour, body FROM device_hours WHERE kind IN ('ledger', 'tasks') ORDER BY device").fetchall()


def stamps(c, device: str, kinds: tuple, lo: int = -_FAR, hi: int = _FAR) -> dict:
    """The sent_at of one computer's hours of these kinds with lo <= hour < hi: {(kind, hour): the time of the send that wrote it}.
    sent_at của các giờ của một máy thuộc các loại này với lo <= giờ < hi: {(loại, giờ): thời điểm của lần gửi đã ghi nó}."""
    _before_read(c, device, *("hours:" + k for k in kinds))
    out = {}
    for kind in kinds:
        for hour, sent_at in c.execute("SELECT hour, sent_at FROM device_hours WHERE device = ? AND kind = ? AND hour >= ? AND hour < ?",
                                       (device, kind, lo, hi)):
            out[(kind, hour)] = sent_at
    return out


def _put_hours(c, rows: list) -> None:
    # rows of (hour, kind, device, body, sent_at); of (hour, kind, device, body) only in the upgrade to version 6, before sent_at exists
    # các dòng (giờ, loại, máy, nội dung, sent_at); dạng (giờ, loại, máy, nội dung) chỉ trong lần nâng lên phiên bản 6, khi chưa có sent_at
    four = [r for r in rows if len(r) == 4]
    five = [r for r in rows if len(r) == 5]
    if four:
        _upsert(c, "device_hours", ("hour", "kind", "device"), ("body",), four)
    if five:
        _upsert(c, "device_hours", ("hour", "kind", "device"), ("body", "sent_at"), five)


def put_hours(c, rows: list) -> None:
    """Write rows (hour, kind, device, body, sent_at), each over the one with the same key.
    Ghi các dòng (giờ, loại, máy, nội dung, sent_at), mỗi dòng đè lên dòng cùng khoá."""
    if not _hold(c, "hours", rows, {(r[2], "hours:" + r[1]) for r in rows}):
        _put_hours(c, rows)


def drop_hours(c, keys: list) -> None:
    if not _hold(c, "hours_drop", keys, {(k[2], "hours:" + k[1]) for k in keys}):
        c.executemany("DELETE FROM device_hours WHERE hour = ? AND kind = ? AND device = ?", keys)


def days(c, device: str = None) -> list:
    """Rows (day, device, usd_micro, tokens_in, tokens_out, gemini, chatgpt, gemma) of one computer, or of all of them.
    Các dòng (ngày, máy, usd_micro, tokens_in, tokens_out, gemini, chatgpt, gemma) của một máy, hoặc của mọi máy."""
    _before_read(c, device, "days")
    sql = "SELECT day, device, %s FROM device_days" % ", ".join(DAY_COLUMNS)
    if device is None:
        return c.execute(sql).fetchall()
    return c.execute(sql + " WHERE device = ?", (device,)).fetchall()


def put_days(c, rows: list) -> None:
    """Write rows (day, device, then the numbers in DAY_COLUMNS order), each over the one of the same day and computer.
    Ghi các dòng (ngày, máy, rồi các con số theo thứ tự DAY_COLUMNS), mỗi dòng đè lên dòng cùng ngày cùng máy."""
    if not _hold(c, "days", rows, {(r[1], "days") for r in rows}):
        _upsert(c, "device_days", ("day", "device"), DAY_COLUMNS, rows)


def drop_days(c, keys: list) -> None:
    if not _hold(c, "days_drop", keys, {(k[1], "days") for k in keys}):
        c.executemany("DELETE FROM device_days WHERE day = ? AND device = ?", keys)


def drop_days_of(c, device: str) -> None:
    if not _hold(c, "days_of", [(device,)], {(device, "days")}):
        c.execute("DELETE FROM device_days WHERE device = ?", (device,))


def clear_days(c) -> None:
    _before_read(c)
    c.execute("DELETE FROM device_days")


def days_zone(c) -> str:
    _before_read(c)
    r = c.execute("SELECT value FROM meta WHERE key = ?", (DAYS_ZONE_KEY,)).fetchone()
    return r[0] if r else ""


def set_days_zone(c, seconds: int) -> None:
    _before_read(c)
    _upsert(c, "meta", ("key",), ("value",), [(DAYS_ZONE_KEY, str(seconds))])
