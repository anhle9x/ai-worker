#!/usr/bin/env python3
"""Sealing of the OTP secrets (board/sealing.py, Accounts in board/stores.py, the accounts database in board/db.py).
All the keys and secrets here are made up in the test and kept in a temporary folder.
  Niêm phong khoá OTP (board/sealing.py, Accounts trong board/stores.py, cơ sở dữ liệu tài khoản trong board/db.py).
Mọi khoá và mã bí mật ở đây do test tự tạo và nằm trong thư mục tạm."""
import base64
import contextlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
import unittest

import test_webhook as tw  # noqa: F401  (sets the temporary folders before the board is imported)
from board import db, sealing, stores


def b32() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


class Seal(unittest.TestCase):
    def setUp(self):
        self.key = sealing.parse_key(sealing.new_key_text())

    def test_a_sealed_secret_opens_only_with_its_key_and_its_name(self):
        secret = b32()
        sealed = sealing.seal(secret, "an", self.key)
        self.assertTrue(sealed.startswith("sealed1:"))
        self.assertNotIn(secret, sealed)
        self.assertEqual(sealing.unseal(sealed, "an", self.key), secret)
        # a new nonce each time: the same secret never looks the same twice
        # mỗi lần một nonce mới: cùng một khoá không bao giờ trông giống nhau hai lần
        self.assertNotEqual(sealing.seal(secret, "an", self.key), sealed)
        other = sealing.parse_key(sealing.new_key_text())
        for value, name, key in ((sealed, "binh", self.key), (sealed, "an", other)):
            with self.assertRaises(ValueError):
                sealing.unseal(value, name, key)
        raw = bytearray(base64.urlsafe_b64decode(sealed[len(sealing.PREFIX):]))
        raw[sealing.NONCE_BYTES] ^= 1
        with self.assertRaises(ValueError):
            sealing.unseal(sealing.PREFIX + base64.urlsafe_b64encode(bytes(raw)).decode(), "an", self.key)
        for broken in ("sealed1:", "sealed1:!!", "sealed1:" + base64.urlsafe_b64encode(b"x" * 40).decode(), secret):
            with self.assertRaises(ValueError):
                sealing.unseal(broken, "an", self.key)

    def test_plain_and_stored_follow_whether_there_is_a_key(self):
        secret = b32()
        self.assertEqual(sealing.stored(secret, "an", None), secret)
        self.assertEqual(sealing.plain(secret, "an", None), secret)
        sealed = sealing.stored(secret, "an", self.key)
        self.assertEqual(sealing.plain(sealed, "an", self.key), secret)
        self.assertIsNone(sealing.plain(sealed, "an", None))
        self.assertIsNone(sealing.plain(sealed, "binh", self.key))

    def test_the_key_file_must_hold_64_hex_digits(self):
        self.assertEqual(len(sealing.parse_key(sealing.new_key_text())), 32)
        for bad in ("", "abc", "g" * 64, "0" * 63, "0" * 65):
            with self.assertRaises(ValueError):
                sealing.parse_key(bad)
        self.assertEqual(sealing.key_id(self.key), sealing.key_id(bytes(self.key)))
        self.assertEqual(len(sealing.key_id(self.key)), 16)


class AccountsSealed(unittest.TestCase):
    """An accounts database of its own in a temporary folder, with or without a key file.
    Một cơ sở dữ liệu tài khoản riêng trong thư mục tạm, có hoặc không có file khoá."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="test-sealing-")
        self.key_file = os.path.join(self.dir, "otp.key")
        self.path = os.path.join(self.dir, "accounts.db")
        self.saved = {k: os.environ.get(k) for k in ("OTP_KEY_FILE", "CREDENTIALS_DIRECTORY", "OTP", "OTP_ADMINS")}
        os.environ.pop("CREDENTIALS_DIRECTORY", None)
        os.environ["OTP_KEY_FILE"] = self.key_file

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_key(self) -> bytes:
        text = sealing.new_key_text()
        with open(self.key_file, "w") as f:
            f.write(text)
        return sealing.parse_key(text)

    def accounts(self) -> stores.Accounts:
        return stores.Accounts(db.Database(self.path, db.KEYS_STEPS, "FULL", backup_keep_days=db.KEYS_BACKUP_KEEP_DAYS, secure_delete=True))

    def stored_values(self) -> list:
        conn = sqlite3.connect(self.path)
        try:
            return [(s, json.loads(b)["secret"]) for s, b in conn.execute("SELECT secret, body FROM accounts")]
        finally:
            conn.close()

    def file_bytes(self) -> bytes:
        out = b""
        for suffix in ("", "-wal"):
            if os.path.exists(self.path + suffix):
                with open(self.path + suffix, "rb") as f:
                    out += f.read()
        return out

    def test_with_a_key_a_new_secret_is_sealed_in_the_column_and_in_the_body(self):
        self.write_key()
        a = self.accounts()
        secret = a.create("an", "admin", "test")
        [(column, body)] = self.stored_values()
        self.assertTrue(sealing.is_sealed(column) and sealing.is_sealed(body))
        self.assertEqual(a.secrets_by_name(), {"an": base64.b32decode(secret)})
        again = a.reissue("an")
        self.assertEqual(a.secrets_by_name(), {"an": base64.b32decode(again)})
        self.assertNotIn(again.encode(), self.file_bytes())
        self.assertEqual(a.sealing_problem(), "")

    def test_without_a_key_nothing_changes(self):
        a = self.accounts()
        secret = a.create("an", "admin", "test")
        self.assertEqual(self.stored_values(), [(secret, secret)])
        self.assertEqual(a.seal_all(), 0)
        self.assertEqual(a.sealing_problem(), "")
        self.assertEqual(a.secrets_by_name(), {"an": base64.b32decode(secret)})

    def test_secrets_stored_before_are_sealed_at_start_and_no_plain_copy_stays_in_the_file(self):
        a = self.accounts()
        plain = [a.create(n, "admin", "test") for n in ("an", "binh")]
        a.db.conn.close()
        self.write_key()
        a = self.accounts()
        self.assertEqual(a.sealing_problem(), "")
        self.assertEqual(a.seal_all(), 2)
        self.assertTrue(all(sealing.is_sealed(c) and sealing.is_sealed(b) for c, b in self.stored_values()))
        data = self.file_bytes()
        for secret in plain:
            self.assertNotIn(secret.encode(), data)
        self.assertEqual(a.secrets_by_name(), {"an": base64.b32decode(plain[0]), "binh": base64.b32decode(plain[1])})
        self.assertEqual(a.db.get_meta("otp_key_id"), sealing.key_id(a.key))
        self.assertEqual(a.seal_all(), 0)

    def test_sealed_secrets_with_no_key_or_another_key_stop_the_webhook(self):
        self.write_key()
        a = self.accounts()
        a.create("an", "admin", "test")
        a.seal_all()
        a.db.conn.close()
        os.remove(self.key_file)
        a = self.accounts()
        self.assertIn("cannot be read", a.sealing_problem())
        self.assertEqual(a.secrets_by_name(), {})
        a.db.conn.close()
        self.write_key()
        a = self.accounts()
        self.assertIn("not the key they were sealed with", a.sealing_problem())
        self.assertEqual(a.secrets_by_name(), {})

    def test_the_credential_from_systemd_comes_before_the_key_file(self):
        creds = os.path.join(self.dir, "creds")
        os.mkdir(creds)
        text = sealing.new_key_text()
        with open(os.path.join(creds, sealing.CREDENTIAL_NAME), "w") as f:
            f.write(text)
        self.write_key()
        os.environ["CREDENTIALS_DIRECTORY"] = creds
        self.assertEqual(sealing.load_key(), sealing.parse_key(text))
        os.environ.pop("CREDENTIALS_DIRECTORY")
        os.remove(self.key_file)
        self.assertIsNone(sealing.load_key())

    def test_an_imported_account_is_sealed_too(self):
        self.write_key()
        secret = b32()
        os.environ.update(OTP="an:" + secret, OTP_ADMINS="an")
        a = self.accounts()
        self.assertEqual(a.import_from_env(), 1)
        [(column, _)] = self.stored_values()
        self.assertTrue(sealing.is_sealed(column))
        self.assertEqual(a.secrets_by_name(), {"an": base64.b32decode(secret)})


class KeysDatabase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="test-keysdb-")
        self.path = os.path.join(self.dir, "accounts.db")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_version_2_is_reached_from_version_1_with_a_copy_kept_7_days(self):
        first = db.Database(self.path, db.KEYS_STEPS[:1], "FULL")
        first.conn.execute("INSERT INTO accounts VALUES ('an', 'admin', 'X', 0, 'test', NULL, '{}')")
        first.conn.close()
        with contextlib.redirect_stderr(io.StringIO()):
            k = db.Database(self.path, db.KEYS_STEPS, "FULL", backup_keep_days=db.KEYS_BACKUP_KEEP_DAYS, secure_delete=True)
        self.assertEqual(k.rows("PRAGMA user_version"), [(2,)])
        self.assertEqual(k.rows("PRAGMA secure_delete"), [(1,)])
        backup = self.path + ".schema-1.bak"
        self.assertTrue(os.path.exists(backup))
        old = time.time() - 8 * 86400
        os.utime(backup, (old, old))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(k.drop_old_upgrade_backups(time.time()), [backup])
        # an older program refuses the sealed file rather than read its secrets as base32
        # chương trình cũ từ chối file đã niêm phong chứ không đọc khoá của nó như base32
        k.conn.close()
        with self.assertRaises(SystemExit):
            db.Database(self.path, db.KEYS_STEPS[:1], "FULL")

    def test_the_accounts_before_sqlite_are_deleted_30_days_after_they_moved_in(self):
        k = db.Database(self.path, db.KEYS_STEPS, "FULL")
        legacy = os.path.join(self.dir, db.LEGACY_DIR_NAME)
        os.mkdir(legacy)
        path = os.path.join(legacy, "accounts.json")
        with open(path, "w") as f:
            f.write("{}")
        now = time.time()
        self.assertFalse(db.drop_old_legacy_accounts(k, self.dir, now))
        with k.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_from_json_at', ?)", (str(int(now - 10 * 86400)),))
        self.assertFalse(db.drop_old_legacy_accounts(k, self.dir, now))
        self.assertTrue(os.path.exists(path))
        with k.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_from_json_at', ?)", (str(int(now - 31 * 86400)),))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(db.drop_old_legacy_accounts(k, self.dir, now))
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
