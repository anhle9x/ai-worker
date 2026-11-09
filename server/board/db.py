"""SQLite storage of the board server: two files, the schema and its upgrades, moving the old JSON files in, exporting back to JSON.
Lưu trữ SQLite của máy chủ bảng tổng: hai file, lược đồ và các bước nâng cấp, chuyển file JSON cũ vào, xuất ngược ra JSON."""

import contextlib
import glob
import json
import os
import shutil
import sqlite3
import sys
import threading
import time

from board.settings import DATA_DIR, KEYS_DIR

DATA_DB_NAME = "board.db"
KEYS_DB_NAME = "accounts.db"
# where the old JSON files go after they are moved into the database; they are kept, never deleted
# nơi đặt file JSON cũ sau khi đã chuyển vào cơ sở dữ liệu; giữ lại, không xoá
LEGACY_DIR_NAME = "legacy-json"

# Each step upgrades the schema by one version, in one transaction. Never change a step that has shipped: add a new one.
# Mỗi bước nâng lược đồ lên một phiên bản, trong một giao dịch. Không sửa bước đã phát hành: thêm bước mới.
DATA_STEPS = [
    [
        "CREATE TABLE devices (device TEXT PRIMARY KEY, account TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', seen_at INTEGER NOT NULL, body TEXT NOT NULL)",
        "CREATE INDEX devices_seen_at ON devices (seen_at)",
        "CREATE TABLE identities (device TEXT PRIMARY KEY, account TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '')",
        "CREATE TABLE history (id INTEGER PRIMARY KEY, at INTEGER NOT NULL, name TEXT NOT NULL, account TEXT NOT NULL DEFAULT '', status TEXT, delegating TEXT)",
        "CREATE INDEX history_at ON history (at)",
        "CREATE TABLE audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, month TEXT NOT NULL, action TEXT, body TEXT NOT NULL)",
        "CREATE INDEX audit_month ON audit (month, id)",
        "CREATE TABLE screens (id TEXT PRIMARY KEY, hash TEXT, name TEXT, owner TEXT, kind TEXT, expires_at INTEGER, body TEXT NOT NULL)",
        "CREATE INDEX screens_hash ON screens (hash)",
        "CREATE TABLE revoked (hash TEXT PRIMARY KEY, name TEXT, kind TEXT, revoked_at INTEGER, body TEXT NOT NULL)",
        "CREATE TABLE documents (name TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at INTEGER)",
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)",
    ],
]
KEYS_STEPS = [
    [
        "CREATE TABLE accounts (name TEXT PRIMARY KEY, role TEXT NOT NULL, secret TEXT NOT NULL, created_at INTEGER, created_by TEXT, last_login_at INTEGER, body TEXT NOT NULL)",
        "CREATE TABLE imported (name TEXT PRIMARY KEY)",
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)",
    ],
]


class Database:
    """One SQLite file with one connection shared by all threads behind a lock; every write goes through tx().
    Một file SQLite, một kết nối dùng chung cho mọi luồng sau một khoá; mọi lần ghi đi qua tx()."""

    def __init__(self, path: str, steps: list, synchronous: str):
        self.path = path
        self.lock = threading.RLock()
        self.depth = 0
        folder = os.path.dirname(path)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        # create the file readable by its owner only; SQLite gives the -wal and -shm files the same mode
        # tạo file chỉ chủ sở hữu đọc được; SQLite cho file -wal và -shm cùng quyền đó
        if not os.path.exists(path):
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA synchronous=" + synchronous)
        self._upgrade(steps)

    def _upgrade(self, steps: list) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > len(steps):
            # an older program on a newer database would lose data: refuse to start
            # chương trình cũ chạy trên cơ sở dữ liệu mới sẽ làm mất dữ liệu: không cho chạy
            sys.exit("%s has schema version %d, newer than this program (%d). Install the newer version again." % (self.path, version, len(steps)))
        for n in range(version, len(steps)):
            with self.tx() as c:
                for sql in steps[n]:
                    c.execute(sql)
                c.execute("PRAGMA user_version=%d" % (n + 1))

    @contextlib.contextmanager
    def tx(self):
        """A write transaction; nested calls join the outer one.
        Một giao dịch ghi; gọi lồng nhau thì nhập vào giao dịch ngoài."""
        with self.lock:
            if self.depth:
                self.depth += 1
                try:
                    yield self.conn
                finally:
                    self.depth -= 1
                return
            self.conn.execute("BEGIN IMMEDIATE")
            self.depth = 1
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")
            finally:
                self.depth = 0

    def rows(self, sql: str, args=()) -> list:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def get_meta(self, key: str) -> str:
        r = self.rows("SELECT value FROM meta WHERE key = ?", (key,))
        return r[0][0] if r else ""

    def backup(self, path: str) -> None:
        """Copy the database while the server runs; a plain file copy could catch a half-written WAL.
        Chép cơ sở dữ liệu khi máy chủ đang chạy; chép file thường có thể dính WAL đang ghi dở."""
        target = sqlite3.connect(path)
        try:
            with self.lock:
                self.conn.backup(target)
        finally:
            target.close()


_OPEN = {}
_OPEN_LOCK = threading.Lock()


def data_db() -> Database:
    """The numbers database in DATA_DIR, opened once; old JSON files there are moved in the first time.
    Cơ sở dữ liệu số liệu trong DATA_DIR, mở một lần; file JSON cũ ở đó được chuyển vào ở lần đầu."""
    with _OPEN_LOCK:
        if "data" not in _OPEN:
            db = Database(os.path.join(DATA_DIR, DATA_DB_NAME), DATA_STEPS, "NORMAL")
            migrate_data_json(db, DATA_DIR)
            _OPEN["data"] = db
        return _OPEN["data"]


def keys_db() -> Database:
    """The accounts database in KEYS_DIR, apart from the numbers so a backup of DATA_DIR carries no OTP secret.
    Cơ sở dữ liệu tài khoản trong KEYS_DIR, tách khỏi số liệu để bản sao lưu DATA_DIR không mang mã bí mật OTP."""
    with _OPEN_LOCK:
        if "keys" not in _OPEN:
            db = Database(os.path.join(KEYS_DIR, KEYS_DB_NAME), KEYS_STEPS, "FULL")
            migrate_keys_json(db, KEYS_DIR)
            _OPEN["keys"] = db
        return _OPEN["keys"]


def dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _load_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, RecursionError) as e:
        sys.stderr.write("migrate: skipped %s (%s)\n" % (os.path.basename(path), e))
        return None


def _jsonl(path: str) -> list:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
    except OSError as e:
        sys.stderr.write("migrate: skipped %s (%s)\n" % (os.path.basename(path), e))
    return out


def _move_to_legacy(folder: str, paths: list) -> None:
    legacy = os.path.join(folder, LEGACY_DIR_NAME)
    os.makedirs(legacy, mode=0o700, exist_ok=True)
    for p in paths:
        shutil.move(p, os.path.join(legacy, os.path.basename(p)))


def screen_row(k: str, v: dict) -> tuple:
    return (k, v.get("hash"), v.get("name"), v.get("owner", ""), v.get("kind", ""), v.get("expiresAt"), dumps(v))


def revoked_row(k: str, v: dict) -> tuple:
    return (k, v.get("name"), v.get("kind", ""), v.get("revokedAt"), dumps(v))


def account_row(k: str, v: dict) -> tuple:
    return (k, v.get("role", ""), v.get("secret", ""), v.get("createdAt"), v.get("createdBy"), v.get("lastLoginAt"), dumps(v))


def device_row(d: dict, seen_at: int) -> tuple:
    return (d["device"], str(d.get("account") or ""), str(d.get("name") or ""), seen_at, dumps(d))


def migrate_data_json(db: Database, folder: str) -> dict:
    """Move the old JSON files of DATA_DIR into the database once: rows already there win, broken files are skipped,
    the files go to legacy-json/. Returns how many rows of each kind were moved.
    Chuyển file JSON cũ trong DATA_DIR vào cơ sở dữ liệu một lần: dòng đã có thì giữ, file hỏng thì bỏ qua,
    file được dời sang legacy-json/. Trả về số dòng đã chuyển của từng loại."""
    names = ("identities.json", "history.jsonl", "tv.json", "tv-revoked.json", "locations.json", "team-csv.json")
    paths = [os.path.join(folder, n) for n in names if os.path.isfile(os.path.join(folder, n))]
    paths += sorted(glob.glob(os.path.join(folder, "device-*.json")) + glob.glob(os.path.join(folder, "audit-*.jsonl")))
    if not paths:
        return {}
    counts = {}
    with db.tx() as c:
        for p in paths:
            name = os.path.basename(p)
            if name == "identities.json":
                d = _load_json(p)
                for k, v in (d.items() if isinstance(d, dict) else []):
                    if isinstance(v, list) and len(v) == 2:
                        c.execute("INSERT OR IGNORE INTO identities VALUES (?, ?, ?)", (k, str(v[0] or ""), str(v[1] or "")))
                        counts["identities"] = counts.get("identities", 0) + 1
            elif name.startswith("device-"):
                d = _load_json(p)
                if isinstance(d, dict) and d.get("device") == name[:-5]:
                    c.execute("INSERT OR IGNORE INTO devices VALUES (?, ?, ?, ?, ?)", device_row(d, int(os.path.getmtime(p))))
                    counts["devices"] = counts.get("devices", 0) + 1
            elif name == "history.jsonl":
                for d in _jsonl(p):
                    if isinstance(d.get("at"), int) and isinstance(d.get("name"), str):
                        c.execute("INSERT INTO history (at, name, account, status, delegating) VALUES (?, ?, ?, ?, ?)",
                                  (d["at"], d["name"], d.get("account", ""), d.get("status"), dumps(d.get("delegating"))))
                        counts["history"] = counts.get("history", 0) + 1
            elif name in ("tv.json", "tv-revoked.json"):
                d = _load_json(p)
                table, row = ("screens", screen_row) if name == "tv.json" else ("revoked", revoked_row)
                for k, v in (d.items() if isinstance(d, dict) else []):
                    if isinstance(v, dict):
                        r = row(k, v)
                        c.execute("INSERT OR IGNORE INTO %s VALUES (%s)" % (table, ", ".join("?" * len(r))), r)
                        counts[table] = counts.get(table, 0) + 1
            elif name in ("locations.json", "team-csv.json"):
                d = _load_json(p)
                if isinstance(d, dict):
                    c.execute("INSERT OR IGNORE INTO documents VALUES (?, ?, ?)", (name[:-5], dumps(d), int(time.time() * 1000)))
                    counts["documents"] = counts.get("documents", 0) + 1
            elif name.startswith("audit-"):
                month = name[len("audit-"):-len(".jsonl")]
                for d in _jsonl(p):
                    c.execute("INSERT INTO audit (at, month, action, body) VALUES (?, ?, ?, ?)", (str(d.get("at", "")), month, d.get("action"), dumps(d)))
                    counts["audit"] = counts.get("audit", 0) + 1
        c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_from_json_at', ?)", (str(int(time.time())),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_counts', ?)", (dumps(counts),))
    _move_to_legacy(folder, paths)
    sys.stderr.write("migrated JSON files into %s: %s\n" % (db.path, dumps(counts)))
    return counts


def migrate_keys_json(db: Database, folder: str) -> int:
    """Move keys/accounts.json into the accounts database once, then to keys/legacy-json/.
    Chuyển keys/accounts.json vào cơ sở dữ liệu tài khoản một lần, rồi dời sang keys/legacy-json/."""
    path = os.path.join(folder, "accounts.json")
    if not os.path.isfile(path):
        return 0
    d = _load_json(path)
    d = d if isinstance(d, dict) else {}
    n = 0
    with db.tx() as c:
        for k, v in (d.get("accounts") or {}).items():
            if isinstance(v, dict) and v.get("role") and isinstance(v.get("secret"), str):
                c.execute("INSERT OR IGNORE INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)", account_row(k, v))
                n += 1
        for k in d.get("imported") or []:
            if isinstance(k, str):
                c.execute("INSERT OR IGNORE INTO imported VALUES (?)", (k,))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_from_json_at', ?)", (str(int(time.time())),))
    _move_to_legacy(folder, [path])
    sys.stderr.write("migrated %d accounts into %s\n" % (n, db.path))
    return n


def export_json(out_dir: str) -> list:
    """Write the databases back as the old JSON files, to go back to a version before SQLite without losing data.
    Ghi cơ sở dữ liệu ngược ra file JSON cũ, để quay về bản trước SQLite mà không mất dữ liệu."""
    data, keys = data_db(), keys_db()
    os.makedirs(os.path.join(out_dir, "data"), mode=0o700, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "keys"), mode=0o700, exist_ok=True)
    written = []

    def write(rel: str, text: str) -> None:
        path = os.path.join(out_dir, rel)
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(text)
        written.append(rel)

    for device, seen_at, body in data.rows("SELECT device, seen_at, body FROM devices"):
        write("data/%s.json" % device, body)
        os.utime(os.path.join(out_dir, "data", device + ".json"), (seen_at, seen_at))
    write("data/identities.json", dumps({k: [a, n] for k, a, n in data.rows("SELECT device, account, name FROM identities")}))
    write("data/history.jsonl", "".join(dumps({"at": at, "name": n, "account": a, "status": s, "delegating": json.loads(g) if g else None}) + "\n"
                                        for at, n, a, s, g in data.rows("SELECT at, name, account, status, delegating FROM history ORDER BY id")))
    write("data/tv.json", dumps({k: json.loads(b) for k, b in data.rows("SELECT id, body FROM screens")}))
    write("data/tv-revoked.json", dumps({k: json.loads(b) for k, b in data.rows("SELECT hash, body FROM revoked")}))
    for name, body in data.rows("SELECT name, body FROM documents"):
        write("data/%s.json" % name, body)
    months = {}
    for month, body in data.rows("SELECT month, body FROM audit ORDER BY id"):
        months.setdefault(month, []).append(body + "\n")
    for month, lines in months.items():
        write("data/audit-%s.jsonl" % month, "".join(lines))
    write("keys/accounts.json", dumps({"accounts": {k: json.loads(b) for k, b in keys.rows("SELECT name, body FROM accounts")},
                                       "imported": [r[0] for r in keys.rows("SELECT name FROM imported ORDER BY name")]}))
    return written
