"""A key of its own for each computer that sends numbers, so the send key every install package carries (INGEST_KEY) stops being
  enough to send as someone else's computer, and one computer can be cut off without reinstalling everyone.

  Format, dot-separated text that Python and Go read the same way (docs: OCN design v2, section 14):
    awd1.<kid>.<org>.<pid>.<rk>.<device>.<iat>.<signature>
  kid: which signing secret; org: this install; pid: the person, from account and name; rk: the routing key, from the account;
  device: the computer's id; iat: when it was issued (server clock, seconds); signature: HMAC-SHA256 of everything before it.
  No office, branch or IP goes into a key, since those change.

  A key is checked on its own (signature, kid, age), so any process that holds the secret can check it without a lookup. Two small
  tables say which computers have used a key and which were revoked: a computer that has sent with its own key may no longer send with
  the shared key, and a revoked one is refused until an admin forgets it. A key only issued binds nothing yet, so a plugin too old to keep
  it, or an answer lost on the way, never shuts a computer out.

  Một khoá riêng cho mỗi máy gửi số liệu, để khoá gửi mà mọi gói cài đều mang (INGEST_KEY) không còn đủ để gửi thay máy của người khác,
  và cắt được một máy mà không phải cài lại cho mọi người.

  Định dạng là chữ cách nhau bằng dấu chấm, Python và Go đọc như nhau (tài liệu: bản thiết kế v2 của OCN, mục 14):
    awd1.<kid>.<org>.<pid>.<rk>.<device>.<iat>.<chữ ký>
  kid: bí mật ký nào; org: lần cài này; pid: người, suy từ tài khoản và tên; rk: khoá định tuyến, suy từ tài khoản;
  device: mã máy; iat: lúc cấp (đồng hồ máy chủ, giây); chữ ký: HMAC-SHA256 của mọi thứ đứng trước.
  Không đưa văn phòng, chi nhánh hay IP vào khoá, vì chúng đổi.

  Khoá được kiểm tự thân (chữ ký, kid, tuổi), nên tiến trình nào giữ bí mật cũng kiểm được mà không cần tra. Hai bảng nhỏ ghi máy nào
  đã dùng khoá và máy nào bị thu hồi: máy đã gửi bằng khoá riêng không được gửi bằng khoá chung nữa, và máy bị thu hồi bị từ chối cho tới
  khi quản trị quên nó đi. Khoá mới chỉ được cấp thì chưa ràng buộc gì, nên plugin quá cũ không giữ được khoá, hay câu trả lời bị rơi dọc
  đường, không bao giờ làm máy bị khoá ngoài.
  """
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
from typing import Optional

from board.db import data_db, keys_db

PREFIX = "awd1"
# a key lives this long; one older than RENEW_AFTER_DAYS gets a new one in the answer to its next send
# một khoá sống chừng này; khoá cũ hơn RENEW_AFTER_DAYS được cấp khoá mới trong câu trả lời của lần gửi kế tiếp
KEY_DAYS = 90
RENEW_AFTER_DAYS = 30
DEVICE_RE = re.compile(r"device-[a-z0-9]{1,40}")
PART_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
SECRETS_KEY = "device_signing_secrets"
ORG_KEY = "device_key_org"
ID_SALT_KEY = "device_key_id_salt"
# the secret the wall display's codes for an email are made with: kept, so a person keeps the same code after a restart and in every process
# bí mật dùng làm mã thay email trên màn treo tường: được giữ lại, để một người giữ cùng mã sau khi khởi động lại và ở mọi tiến trình
ALIAS_KEY = "wall_alias_secret"
# a key issued before this moment (seconds) gets a new one at its next send, as one older than RENEW_AFTER_DAYS does: --rotate-device-secret
# khoá cấp trước thời điểm này (giây) được cấp khoá mới ở lần gửi kế tiếp, như khoá cũ hơn RENEW_AFTER_DAYS: --rotate-device-secret
RENEW_BEFORE_KEY = "device_key_renew_before"
# the code the Go receiver shows on this machine's internal paths (board/receiver.py); it lives in the receiver's file of secrets too
# mã bộ nhận Go trình ở các đường nội bộ của máy này (board/receiver.py); nó cũng nằm trong file bí mật của bộ nhận
INTERNAL_KEY = "receiver_internal_secret"
# the secret the tickets of the board's live feed are signed with (board/receiver.py, Tickets): a secret of its own, never a device's, so a
# ticket cannot be made into a key or a key into a ticket; it lives in the receiver's file of secrets too, which checks the tickets
# bí mật dùng ký vé của luồng số trực tiếp của bảng (board/receiver.py, Tickets): một bí mật riêng, không bao giờ là bí mật của máy, để vé
# không thể thành khoá hay khoá thành vé; nó cũng nằm trong file bí mật của bộ nhận, nơi kiểm vé
TICKET_KEY = "live_ticket_secret"
# set once the rows of device_keys are written only for keys a computer has used (0.50.1): before, issuing a key wrote the row, so a
# plugin too old to keep its key was refused for ever; the rows of that time that are not revoked are dropped once
# đặt một lần khi các dòng device_keys chỉ được ghi cho khoá mà máy đã dùng (0.50.1): trước đó, cấp khoá là ghi dòng, nên plugin cũ không
# giữ được khoá bị từ chối mãi; các dòng của thời đó chưa bị thu hồi được bỏ một lần
USED_ONLY_KEY = "device_keys_used_only"
# how many codes of rows on the board are kept made (row_code); past that they are made again
# giữ sẵn bao nhiêu mã dòng của bảng (row_code); quá mức đó thì làm lại
ROW_CODES_MAX = 200_000


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class DeviceKeys:
    """Issues and checks computer keys; the signing secrets and the org live in the keys database, the table of issued and revoked
    computers in the data database (device_keys).
    Cấp và kiểm khoá máy; các bí mật ký và mã tổ chức nằm trong cơ sở dữ liệu khoá, bảng máy đã cấp và đã thu hồi nằm trong cơ sở
    dữ liệu số liệu (device_keys)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.loaded_for = None
        self.signing = []
        self.org = ""
        self.id_salt = b""
        self.alias_secret = b""
        # the signing secrets as stored: [{kid, secret, since}], newest first; since is when it was made (seconds, 0 for the first ones)
        # các bí mật ký như đang lưu: [{kid, secret, since}], mới nhất trước; since là lúc tạo (giây, 0 với các bí mật đầu tiên)
        self.stored = []
        self.renew_before = 0
        self.internal = ""
        self.ticket = ""
        # device -> (iat of the newest key it has sent with, revoked_at or 0); a key issued and never used has no row
        # máy -> (iat của khoá mới nhất nó đã dùng để gửi, revoked_at hoặc 0); khoá đã cấp mà chưa dùng thì không có dòng
        self.rows = {}
        self.rows_for = None
        # device -> (since, admin) for the computers that may send from any network (device_roaming)
        # máy -> (từ lúc, quản trị) cho các máy được gửi từ mọi mạng (device_roaming)
        self.roaming = {}
        self.used_only = False
        # person_key -> the code of their row on the board, for the keys database it was made with
        # person_key -> mã dòng của người đó trên bảng, cho cơ sở dữ liệu khoá đã dùng để làm nó
        self.row_codes = {}
        self.row_codes_for = None

    def _secrets(self):
        """The signing secrets (newest first), the org and the id salt, made once and kept in the keys database.
        Các bí mật ký (mới nhất trước), mã tổ chức và muối của mã người, tạo một lần và giữ trong cơ sở dữ liệu khoá."""
        db = keys_db()
        if self.loaded_for is db:
            return
        with db.tx() as c:
            def meta(key):
                r = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
                return r[0] if r else ""

            stored = meta(SECRETS_KEY)
            if not stored:
                secret = secrets.token_bytes(32)
                stored = json.dumps([{"kid": _b64(hashlib.sha256(secret).digest())[:8], "secret": _b64(secret)}])
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (SECRETS_KEY, stored))
            org = meta(ORG_KEY) or _b64(secrets.token_bytes(6))
            salt = meta(ID_SALT_KEY) or _b64(secrets.token_bytes(16))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ORG_KEY, org))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ID_SALT_KEY, salt))
            alias_secret = meta(ALIAS_KEY) or _b64(secrets.token_bytes(32))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ALIAS_KEY, alias_secret))
            internal = meta(INTERNAL_KEY) or _b64(secrets.token_bytes(32))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (INTERNAL_KEY, internal))
            ticket = meta(TICKET_KEY) or _b64(secrets.token_bytes(32))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (TICKET_KEY, ticket))
            renew_before = meta(RENEW_BEFORE_KEY)
            used_only = meta(USED_ONLY_KEY)
        self.used_only = used_only == "1"
        self.stored = json.loads(stored)
        self.signing = [(e["kid"], base64.urlsafe_b64decode(e["secret"] + "=" * (-len(e["secret"]) % 4))) for e in self.stored]
        self.internal = internal
        self.ticket = ticket
        self.renew_before = int(renew_before) if renew_before.isdigit() else 0
        self.org, self.id_salt, self.alias_secret, self.loaded_for = org, salt.encode(), alias_secret.encode(), db

    def _rows(self):
        db = data_db()
        if self.rows_for is not db:
            self._secrets()
            if not self.used_only:
                # rows written by 0.50.0 when a key was issued, maybe to a plugin that threw it away: dropped once, so those computers
                # enrol again; a computer that keeps its key writes its row back at its next send
                # dòng do 0.50.0 ghi lúc cấp khoá, có thể cho một plugin đã vứt khoá đi: bỏ một lần, để các máy đó ghi danh lại;
                # máy giữ khoá thì ghi lại dòng của nó ở lần gửi kế tiếp
                with db.tx() as c:
                    c.execute("DELETE FROM device_keys WHERE revoked_at = 0")
                with keys_db().tx() as c:
                    c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (USED_ONLY_KEY, "1"))
                self.used_only = True
            self.rows = {d: (iat, revoked) for d, iat, revoked in db.rows("SELECT device, iat, revoked_at FROM device_keys")}
            self.roaming = {d: (since, by) for d, since, by in db.rows("SELECT device, since, by FROM device_roaming")}
            self.rows_for = db
        return db

    def _id(self, label: str, text: str) -> str:
        return _b64(hmac.new(self.id_salt, (label + "|" + text).encode(), hashlib.sha256).digest())[:12]

    def alias(self, text: str) -> str:
        """A code for an email or a name that cannot be read back without the keys database, the same in every process and after a restart.
        Mã cho một email hay một tên, không đọc ngược được nếu không có cơ sở dữ liệu khoá, như nhau ở mọi tiến trình và sau khi khởi động lại."""
        if not text:
            return ""
        with self.lock:
            self._secrets()
            secret = self.alias_secret
        return hmac.new(secret, ("alias|" + text).encode(), hashlib.sha256).hexdigest()[:10]

    def row_code(self, person: str) -> str:
        """The code of a person's row on the board (person_key in board/devices.py), on which a live feed joins its numbers: made with the
        same secret as alias but another label, so it cannot be read back to an email or a name and is not the code alias gives; the same
        in every process and after a restart. Kept, since every build of the board asks again.
        Mã dòng của một người trên bảng (person_key trong board/devices.py), thứ luồng số trực tiếp dùng để ghép số: làm bằng cùng bí mật
        với alias nhưng nhãn khác, nên không đọc ngược ra email hay tên và không trùng mã alias cho; như nhau ở mọi tiến trình và sau khi
        khởi động lại. Được giữ lại, vì lần dựng bảng nào cũng hỏi lại."""
        with self.lock:
            self._secrets()
            if self.row_codes_for is not self.loaded_for or len(self.row_codes) > ROW_CODES_MAX:
                self.row_codes, self.row_codes_for = {}, self.loaded_for
            code = self.row_codes.get(person)
            if code is None:
                code = hmac.new(self.alias_secret, ("row|" + person).encode(), hashlib.sha256).hexdigest()[:12]
                self.row_codes[person] = code
        return code

    def issue(self, device: str, account: str, name: str, now: float) -> str:
        """A new key for this computer, written down as its newest; account and name are the ones the server tied the computer to.
        Một khoá mới cho máy này, ghi lại là khoá mới nhất của nó; tài khoản và tên là những gì máy chủ đã gắn với máy."""
        with self.lock:
            self._secrets()
            iat = int(now)
            kid, secret = self.signing[0]
            person = (account or "").strip().lower() + "|" + (name or "").strip().lower()
            body = ".".join((PREFIX, kid, self.org, self._id("pid", person), self._id("rk", (account or "").strip().lower() or person), device, str(iat)))
            # nothing is written yet: the computer has a key it must use only once it has sent with it (note_used), so a plugin too old
            # to keep the key, or an answer lost on the way, never shuts the computer out
            # chưa ghi gì: máy chỉ bị buộc dùng khoá riêng khi nó đã gửi bằng khoá đó (note_used), nên plugin quá cũ không giữ được khoá,
            # hay câu trả lời bị rơi dọc đường, không bao giờ làm máy bị khoá ngoài
            return body + "." + _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())

    def note_used(self, device: str, iat: Optional[int], now: float) -> None:
        """A computer has just sent with a key of its own: from now on the shared key no longer sends for it. iat is the key's, or None
        when the Go receiver checked the key and did not say which one.
        Một máy vừa gửi bằng khoá riêng: từ giờ khoá chung không gửi thay nó được nữa. iat là của khoá đó, hoặc None khi bộ nhận Go đã
        kiểm khoá mà không nói là khoá nào."""
        with self.lock:
            db = self._rows()
            row = self.rows.get(device)
            if row and (row[1] or iat is None or row[0] >= iat):
                return
            at = int(now) if iat is None else int(iat)
            with db.tx() as c:
                c.execute("INSERT INTO device_keys (device, iat, revoked_at) VALUES (?, ?, 0) "
                          "ON CONFLICT(device) DO UPDATE SET iat = MAX(iat, excluded.iat) WHERE revoked_at = 0", (device, at))
            self.rows[device] = (max(at, row[0] if row else 0), 0)

    def check(self, token: str, now: float):
        """The key's fields when it is well formed, signed by a known secret, not too old and not revoked; else (None, reason).
        Các trường của khoá khi nó đúng dạng, được ký bằng một bí mật đã biết, chưa quá hạn và chưa bị thu hồi; nếu không thì (None, lý do)."""
        parts = token.split(".")
        if len(parts) != 8 or parts[0] != PREFIX or not all(PART_RE.fullmatch(p) for p in parts[1:]) or not DEVICE_RE.fullmatch(parts[5]):
            return None, "not a device key"
        with self.lock:
            self._secrets()
            self._rows()
            secret = dict(self.signing).get(parts[1])
            if secret is None or parts[2] != self.org:
                return None, "unknown signing key"
            body = ".".join(parts[:7])
            if not hmac.compare_digest(parts[7], _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())):
                return None, "bad signature"
            iat = int(parts[6]) if parts[6].isdigit() else -1
            if iat < 0 or iat > now + 300 or now - iat > KEY_DAYS * 86400:
                return None, "device key expired"
            _, revoked = self.rows.get(parts[5], (0, 0))
            if revoked:
                return None, "device revoked"
        return {"kid": parts[1], "pid": parts[3], "rk": parts[4], "device": parts[5], "iat": iat}, ""

    def state(self, device: str, now: float) -> str:
        """none: no key yet; active: it has a key it must use; expired: its newest key is too old, so the shared key may enrol it again;
        revoked: cut off until an admin forgets it.
        none: chưa có khoá; active: đã có khoá và phải dùng nó; expired: khoá mới nhất đã quá cũ, nên khoá chung được ghi danh lại;
        revoked: bị cắt cho tới khi quản trị quên nó đi."""
        with self.lock:
            self._rows()
            row = self.rows.get(device)
        if not row:
            return "none"
        if row[1]:
            return "revoked"
        return "expired" if now - row[0] > KEY_DAYS * 86400 else "active"

    def needs_renewal(self, claims: dict, now: float) -> bool:
        with self.lock:
            self._secrets()
            renew_before = self.renew_before
        return now - claims["iat"] > RENEW_AFTER_DAYS * 86400 or claims["iat"] < renew_before

    def receiver_secrets(self, now: float) -> list:
        """What the Go receiver needs to check keys and to call this machine's internal paths: each signing secret with the org,
        then the internal code. A secret made more than KEY_DAYS after a newer one can no longer have signed a living key, so it is left out.
        Những gì bộ nhận Go cần để kiểm khoá và gọi các đường nội bộ của máy này: từng bí mật ký kèm mã tổ chức,
        rồi mã nội bộ. Bí mật đã có bí mật mới hơn quá KEY_DAYS thì không thể còn ký một khoá đang sống, nên bị bỏ ra."""
        with self.lock:
            self._secrets()
            out = [{"kid": e["kid"], "alg": "HS256", "org": self.org, "secret": e["secret"], "since": int(e.get("since") or 0)}
                   for i, e in enumerate(self.stored) if i == 0 or now - int(self.stored[i - 1].get("since") or 0) <= KEY_DAYS * 86400]
            return out + [{"kid": "internal", "alg": "internal", "secret": self.internal},
                          {"kid": _b64(hashlib.sha256(self.ticket.encode()).digest())[:8], "alg": "ticket", "secret": self.ticket}]

    def ticket_secret(self):
        """(kid, secret) the tickets of the live feed are signed with; the kid is made from the secret, so a new secret has a new kid.
        (kid, bí mật) dùng ký vé của luồng số trực tiếp; kid làm từ bí mật, nên bí mật mới có kid mới."""
        with self.lock:
            self._secrets()
            return _b64(hashlib.sha256(self.ticket.encode()).digest())[:8], base64.urlsafe_b64decode(self.ticket + "=" * (-len(self.ticket) % 4))

    def internal_code(self) -> str:
        with self.lock:
            self._secrets()
            return self.internal

    def renewal_moment(self) -> int:
        with self.lock:
            self._secrets()
            return self.renew_before

    def rotate(self, now: float, drop_old: bool = False) -> str:
        """A new signing secret, first in the list, and every key issued before now gets a new one at its next send. The older secrets
        still check keys until KEY_DAYS have passed (receiver_secrets); with drop_old they go at once and every computer enrols again
        with the shared key (for a file of secrets that leaked). Returns the new kid. Run it with the webhook stopped.
        Một bí mật ký mới, đứng đầu danh sách, và mọi khoá cấp trước lúc này được cấp khoá mới ở lần gửi kế tiếp. Các bí mật cũ
        vẫn kiểm khoá cho tới khi qua KEY_DAYS (receiver_secrets); với drop_old chúng bị bỏ ngay và mọi máy ghi danh lại
        bằng khoá chung (khi file bí mật bị lộ). Trả về kid mới. Chạy khi webhook đã dừng."""
        with self.lock:
            self._secrets()
            secret = secrets.token_bytes(32)
            entry = {"kid": _b64(hashlib.sha256(secret).digest())[:8], "secret": _b64(secret), "since": int(now)}
            # an older secret is kept while the one made after it is younger than KEY_DAYS: a key it signed may still be alive
            # bí mật cũ được giữ khi bí mật tạo sau nó chưa quá KEY_DAYS: khoá nó đã ký có thể vẫn còn sống
            kept = [] if drop_old else self.stored[:1] + [e for i, e in enumerate(self.stored[1:], 1)
                                                         if now - int(self.stored[i - 1].get("since") or 0) <= KEY_DAYS * 86400]
            with keys_db().tx() as c:
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (SECRETS_KEY, json.dumps([entry] + kept)))
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (RENEW_BEFORE_KEY, str(int(now))))
                # the tickets' secret is turned too: it is in the same file, and a ticket lives only minutes, so none is missed for long
                # bí mật của vé cũng được xoay: nó ở cùng file, và vé chỉ sống vài phút, nên không vé nào thiếu lâu
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (TICKET_KEY, _b64(secrets.token_bytes(32))))
            if drop_old:
                # every computer's newest key is now too old, so the shared key may enrol it again; revoked ones stay revoked
                # khoá mới nhất của mọi máy giờ đã quá cũ, nên khoá chung được ghi danh lại nó; máy bị thu hồi vẫn bị thu hồi
                with data_db().tx() as c:
                    c.execute("UPDATE device_keys SET iat = 0")
            self.loaded_for = self.rows_for = None
            return entry["kid"]

    def revoked(self) -> list:
        with self.lock:
            self._rows()
            return sorted(d for d, (_, r) in self.rows.items() if r)

    def revoke(self, device: str, now: float) -> bool:
        """Cuts a computer off. One the server has enrolled is revoked even before it has used its key, which may already be out.
        Cắt một máy. Máy máy chủ đã ghi danh bị thu hồi cả khi chưa dùng khoá của nó, vì khoá có thể đã được cấp ra."""
        with self.lock:
            db = self._rows()
            with db.tx() as c:
                changed = c.execute("UPDATE device_keys SET revoked_at = ? WHERE device = ? AND revoked_at = 0", (int(now), device)).rowcount
                if not changed and device not in self.rows and c.execute("SELECT 1 FROM identities WHERE device = ?", (device,)).fetchone():
                    changed = c.execute("INSERT INTO device_keys (device, iat, revoked_at) VALUES (?, 0, ?)", (device, int(now))).rowcount
                # a revoked computer loses the right to send from outside too: letting it back does not give that back
                # máy bị thu hồi cũng mất quyền gửi từ ngoài: cho nó quay lại không trả quyền đó
                c.execute("DELETE FROM device_roaming WHERE device = ?", (device,))
            self.roaming.pop(device, None)
            if changed:
                self.rows[device] = (self.rows.get(device, (0, 0))[0], int(now))
            return bool(changed)

    def forget(self, device: str) -> bool:
        with self.lock:
            db = self._rows()
            with db.tx() as c:
                gone = c.execute("DELETE FROM device_keys WHERE device = ?", (device,)).rowcount
                # a forgotten computer's old key is good again until it expires, so it must not still reach the server from anywhere
                # khoá cũ của máy đã quên lại dùng được tới khi hết hạn, nên nó không được còn tới máy chủ từ mọi nơi
                c.execute("DELETE FROM device_roaming WHERE device = ?", (device,))
            self.rows.pop(device, None)
            self.roaming.pop(device, None)
            return bool(gone)

    def listing(self, now: float) -> list:
        """Every computer that has sent with a key of its own, or was revoked: its id, when the newest key it used was issued (None when
        unknown) and when it was revoked (ms), and its state.
        Mọi máy đã gửi bằng khoá riêng, hoặc đã bị thu hồi: mã máy, lúc cấp khoá mới nhất nó đã dùng (None khi không rõ) và lúc bị thu hồi
        (ms), và trạng thái.
        """
        with self.lock:
            self._rows()
            rows, roaming = dict(self.rows), dict(self.roaming)
        return [{"device": d, "issuedAt": iat * 1000 if iat else None, "revokedAt": revoked * 1000 if revoked else None,
                 "state": "revoked" if revoked else "expired" if now - iat > KEY_DAYS * 86400 else "active",
                 "roamingSince": roaming[d][0] * 1000 if d in roaming else None} for d, (iat, revoked) in rows.items()]

    def roams(self, device: str) -> bool:
        """True when an admin let this computer send and fetch updates from any network.
        True khi quản trị đã cho máy này gửi và tải bản cập nhật từ mọi mạng."""
        with self.lock:
            self._rows()
            return device in self.roaming

    def set_roaming(self, device: str, on: bool, by: str, now: float) -> bool:
        """Lets a computer send from any network, or takes that back. Only a computer that is sending with its own key now can be let:
        a revoked one, or one whose key is too old, would have to come to the office first anyway. True when something changed.
        Cho một máy gửi từ mọi mạng, hoặc thôi cho. Chỉ máy đang gửi bằng khoá riêng mới được cho: máy bị thu hồi, hay có khoá quá cũ,
        đằng nào cũng phải về văn phòng trước. True khi có gì đó đổi."""
        with self.lock:
            db = self._rows()
            row = self.rows.get(device)
            if on and (not row or row[1] or now - row[0] > KEY_DAYS * 86400):
                return False
            with db.tx() as c:
                if on:
                    changed = c.execute("INSERT OR IGNORE INTO device_roaming (device, since, by) VALUES (?, ?, ?)", (device, int(now), by[:60])).rowcount
                else:
                    changed = c.execute("DELETE FROM device_roaming WHERE device = ?", (device,)).rowcount
            if on and changed:
                self.roaming[device] = (int(now), by[:60])
            elif not on:
                self.roaming.pop(device, None)
            return bool(changed)

    def counts(self) -> dict:
        with self.lock:
            self._rows()
            return {"withKey": sum(1 for _, r in self.rows.values() if not r), "revoked": sum(1 for _, r in self.rows.values() if r)}

    def reload(self) -> None:
        """Read both databases again at the next use: after another program or a test changed them.
        Đọc lại cả hai cơ sở dữ liệu ở lần dùng sau: sau khi chương trình khác hay một bài test đã đổi chúng."""
        with self.lock:
            self.loaded_for = self.rows_for = None


DEVICE_KEYS = DeviceKeys()
