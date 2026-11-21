"""The SQL of the computers' records in one place: devices (what each computer is doing), device_hours (its hour book, one row per hour
and kind) and device_days (its totals per local day). board/devices.py keeps them in memory and decides what to write; only this file
knows the tables, so another database can take their place later without rewriting the code that uses them. Plain SQL that SQLite and
PostgreSQL both run: values only as parameters, INSERT ... ON CONFLICT ... DO UPDATE (never INSERT OR REPLACE; see UPSERT), no JSON
function of the database; the JSON is read and written by Python. Tables: docs/DATA-MODEL.md, schema version 6.
  SQL của bản ghi các máy ở một chỗ: devices (mỗi máy đang làm gì), device_hours (sổ giờ của máy, mỗi giờ mỗi loại một dòng) và
  device_days (tổng của máy theo từng ngày địa phương). board/devices.py giữ chúng trong bộ nhớ và quyết định ghi gì; chỉ file này
  biết các bảng, để sau này cơ sở dữ liệu khác thay được mà không phải viết lại mã dùng chúng. SQL thường mà SQLite và PostgreSQL
  đều chạy: giá trị chỉ qua tham số, INSERT ... ON CONFLICT ... DO UPDATE (không bao giờ INSERT OR REPLACE), không dùng hàm JSON của
  cơ sở dữ liệu; JSON do Python đọc và ghi. Các bảng: docs/DATA-MODEL.vi.md, lược đồ phiên bản 6."""

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


def _chunks(items: list):
    for i in range(0, len(items), _CHUNK):
        yield items[i:i + _CHUNK]


def states(c) -> list:
    return c.execute("SELECT device, seen_at, body FROM devices").fetchall()


def state(c, device: str):
    return c.execute("SELECT device, seen_at, body FROM devices WHERE device = ?", (device,)).fetchone()


def put_state(c, device: str, account: str, name: str, seen_at: int, body: str) -> None:
    _upsert(c, "devices", ("device",), ("account", "name", "seen_at", "body"), [(device, account, name, seen_at, body)])


def set_body(c, device: str, body: str) -> None:
    c.execute("UPDATE devices SET body = ? WHERE device = ?", (body, device))


def drop_devices(c, names: list) -> None:
    """Delete computers with their hours and their days.
    Xoá các máy cùng các giờ và các ngày của chúng."""
    for part in _chunks(list(names)):
        marks = ", ".join("?" * len(part))
        for table in ("devices", "device_hours", "device_days"):
            c.execute("DELETE FROM %s WHERE device IN (%s)" % (table, marks), part)


def hours(c, device: str, kinds: tuple, lo: int = -_FAR, hi: int = _FAR) -> list:
    """One computer's rows (kind, hour, body) of these kinds with lo <= hour < hi, oldest first.
    Các dòng (loại, giờ, nội dung) của một máy thuộc các loại này với lo <= giờ < hi, cũ trước mới sau."""
    out = []
    for kind in kinds:
        out += c.execute("SELECT kind, hour, body FROM device_hours WHERE device = ? AND kind = ? AND hour >= ? AND hour < ? ORDER BY hour",
                         (device, kind, lo, hi)).fetchall()
    return out


def hour_numbers(c, device: str, kind: str) -> list:
    """The hours one computer has of one kind, newest first, without their bodies.
    Các giờ một máy có của một loại, mới trước cũ sau, không kèm nội dung."""
    return [h for (h,) in c.execute("SELECT hour FROM device_hours WHERE device = ? AND kind = ? ORDER BY hour DESC", (device, kind))]


def recent(c, lo: int) -> list:
    """Every computer's ledger and tasks rows (device, kind, hour, body) from hour lo on: the key starts with the hour, so this reads
    only the end of the table.
    Các dòng ledger và tasks (máy, loại, giờ, nội dung) của mọi máy từ giờ lo trở đi: khoá bắt đầu bằng giờ, nên chỉ đọc phần cuối bảng."""
    return c.execute("SELECT device, kind, hour, body FROM device_hours WHERE hour >= ? AND kind IN ('ledger', 'tasks')", (lo,)).fetchall()


def recent_blocks(c, lo: int) -> list:
    """Every computer's blocks rows (device, hour, body) from hour lo on, through their own small index.
    Các dòng blocks (máy, giờ, nội dung) của mọi máy từ giờ lo trở đi, qua chỉ mục nhỏ riêng của chúng."""
    return c.execute("SELECT device, hour, body FROM device_hours WHERE kind = 'blocks' AND hour >= ?", (lo,)).fetchall()


def all_hours(c) -> list:
    return c.execute("SELECT device, kind, hour, body FROM device_hours WHERE kind IN ('ledger', 'tasks') ORDER BY device").fetchall()


def put_hours(c, rows: list) -> None:
    """Write rows (hour, kind, device, body), each over the one with the same key.
    Ghi các dòng (giờ, loại, máy, nội dung), mỗi dòng đè lên dòng cùng khoá."""
    _upsert(c, "device_hours", ("hour", "kind", "device"), ("body",), rows)


def drop_hours(c, keys: list) -> None:
    c.executemany("DELETE FROM device_hours WHERE hour = ? AND kind = ? AND device = ?", keys)


def days(c, device: str = None) -> list:
    """Rows (day, device, usd_micro, tokens_in, tokens_out, gemini, chatgpt, gemma) of one computer, or of all of them.
    Các dòng (ngày, máy, usd_micro, tokens_in, tokens_out, gemini, chatgpt, gemma) của một máy, hoặc của mọi máy."""
    sql = "SELECT day, device, %s FROM device_days" % ", ".join(DAY_COLUMNS)
    if device is None:
        return c.execute(sql).fetchall()
    return c.execute(sql + " WHERE device = ?", (device,)).fetchall()


def put_days(c, rows: list) -> None:
    """Write rows (day, device, then the numbers in DAY_COLUMNS order), each over the one of the same day and computer.
    Ghi các dòng (ngày, máy, rồi các con số theo thứ tự DAY_COLUMNS), mỗi dòng đè lên dòng cùng ngày cùng máy."""
    _upsert(c, "device_days", ("day", "device"), DAY_COLUMNS, rows)


def drop_days(c, keys: list) -> None:
    c.executemany("DELETE FROM device_days WHERE day = ? AND device = ?", keys)


def drop_days_of(c, device: str) -> None:
    c.execute("DELETE FROM device_days WHERE device = ?", (device,))


def clear_days(c) -> None:
    c.execute("DELETE FROM device_days")


def days_zone(c) -> str:
    r = c.execute("SELECT value FROM meta WHERE key = ?", (DAYS_ZONE_KEY,)).fetchone()
    return r[0] if r else ""


def set_days_zone(c, seconds: int) -> None:
    _upsert(c, "meta", ("key",), ("value",), [(DAYS_ZONE_KEY, str(seconds))])
