"""What the optional Go receiver (receiver/, docs/RECEIVER.md) needs from this server, on paths only a program on this machine reaches.
The receiver checks a computer's own key, cleans the send, keeps the hour books and answers the computer; this server stays the record:
it writes the rows the receiver sends in batches, hands over the books when the receiver starts, and says in a numbered policy which
computers were revoked or written here directly. Python and Go read the same file of secrets, written here.
  Những gì bộ nhận Go tuỳ chọn (receiver/, docs/RECEIVER.vi.md) cần ở máy chủ này, trên các đường chỉ chương trình trên máy này tới được.
  Bộ nhận kiểm khoá riêng của máy, làm sạch lần gửi, giữ sổ giờ và trả lời máy; máy chủ này vẫn là bản gốc: nó ghi các dòng bộ nhận gửi
  theo lô, trao sổ giờ khi bộ nhận khởi động, và cho biết trong một tài liệu chính sách có số thứ tự máy nào đã bị thu hồi hay vừa được
  ghi thẳng ở đây. Python và Go đọc cùng một file bí mật, do máy chủ này ghi.

A batch, POST /internal/rows:  {"src": receiver, "boot": its start, "seq": n, "rows": [row, ...]}
  row: {"k": ["m", device], "at": ms the receiver took it, "kind": "v1", "hours" or "full", "ip": address, "v": the cleaned send, in the
        format it came in,
        "raw": the send as it came (only for RECEIVER_CHECK_PERCENT of them)}
  kind "delegations": only the records of work handed to helpers, of a send whose numbers were not written (out of order, or no book)
  answer: {"ok": true, "seq": n, "needFull": [devices this server has no book for], "unknown": [devices it never enrolled],
           "incomplete": [devices whose person has no email or no name yet], "bad": [devices whose row failed and was left out]}
  Một lô, POST /internal/rows:  {"src": bộ nhận, "boot": lần khởi động của nó, "seq": n, "rows": [dòng, ...]}
    dòng: {"k": ["m", mã máy], "at": ms lúc bộ nhận nhận, "kind": "v1", "hours" hoặc "full", "ip": địa chỉ, "v": lần gửi đã làm sạch,
           theo định dạng nó tới,
           "raw": lần gửi nguyên văn (chỉ với RECEIVER_CHECK_PERCENT số dòng)}
    kind "delegations": chỉ biên bản giao việc, của lần gửi mà số liệu không được ghi (tới sai thứ tự, hoặc không có sổ)
    trả lời: {"ok": true, "seq": n, "needFull": [các máy máy chủ này không có sổ], "unknown": [các máy nó chưa từng ghi danh],
              "incomplete": [các máy mà người của nó chưa có email hay tên], "bad": [các máy có dòng hỏng, bị bỏ ra]}

The table of people, GET /internal/people?since=: each computer's row code on the board and its branch, the changes only (People below).
  Bảng người, GET /internal/people?since=: mã dòng trên bảng và chi nhánh của mỗi máy, chỉ phần đổi (People bên dưới).

A ticket for the board's live feed, POST /sse/ticket (Tickets below): awt1.<kid>.<role>.<scope>.<sid>.<expiry>.<signature>, checked by the
receiver on /live and /live/snap; the policy names the sessions logged out since (endedSessions), whose feeds the receiver ends.
  Vé cho luồng số trực tiếp của bảng, POST /sse/ticket (Tickets bên dưới): awt1.<kid>.<vai>.<phạm vi>.<sid>.<hết hạn>.<chữ ký>, bộ nhận
  kiểm ở /live và /live/snap; chính sách nêu các phiên đã đăng xuất từ đó (endedSessions), và bộ nhận cắt luồng của chúng.
"""
import base64
import hashlib
import hmac
import bisect
import json
import os
import random
import sys
import threading
import time
from collections import deque

from board import order, settings
from board.devicekeys import DEVICE_KEYS
from board.login import SESSIONS
from board.devices import (
    BOOT_ID,
    DEVICES,
    HOUR_KINDS,
    NEED_FULL,
    SAVED,
    STALE,
    clean_delegations,
    clean_payload,
    branch_facts,
    person_key,
    read_all_devices,
    save_ingest,
    today_first_hour,
)

# how many computers written here directly the policy remembers; a receiver further behind than that drops every book it holds
# chính sách nhớ bao nhiêu máy được ghi thẳng ở đây; bộ nhận chậm hơn mức đó thì bỏ mọi sổ nó đang giữ
WRITTEN_KEEP = 20_000
DEVICES_PAGE_MAX = 2000
# the most hours one row of the receiver may say it left out: 3 kinds of hours for 8 days, for many sends, with room to spare
# số giờ nhiều nhất một dòng của bộ nhận được báo đã để ra ngoài: 3 loại giờ cho 8 ngày, của nhiều lần gửi, còn dư
OLDER_MAX = 100_000
# the version of the internal protocol between the receiver and this server, in every policy document
# phiên bản giao thức nội bộ giữa bộ nhận và máy chủ này, có trong mọi tài liệu chính sách
PROTO = 3
PEOPLE_PAGE_MAX = 5000
# how many computers gone the table of people remembers, for a receiver fallen behind
# bảng người nhớ bao nhiêu máy đã mất, cho bộ nhận đang tụt lại
PEOPLE_GONE_MAX = 100_000
# what the receiver keeps of a computer's state besides its hours, to put its status on the live numbers (receiver/internal/live): the
# session counts, the tasks being handed to helpers, and the connector's counts per tool. No name, no email, no address.
# thứ bộ nhận giữ về trạng thái của một máy ngoài các giờ, để đưa trạng thái lên số trực tiếp (receiver/internal/live): số phiên, số việc
# đang giao cho trợ lý, và số theo từng công cụ của bộ nối. Không tên, không email, không địa chỉ.
STATE_FIELDS = ("openSessions", "working", "waiting", "delegating", "tools")


def ingest_route(device: str):
    """Where this computer sends from now on, when the receiver takes its sends: {"ingestUrls": [...], "ingestTtlMs": n}, or None when it
    is not chosen (RECEIVER off, no address, or not in RECEIVER_INGEST_DEVICES nor in RECEIVER_INGEST_PERCENT). The share is decided by a
    stable hash of the id, so a computer stays in or out while the percentage stays the same, and raising it only adds computers.
    Máy này gửi tới đâu từ giờ, khi bộ nhận nhận các lần gửi của nó: {"ingestUrls": [...], "ingestTtlMs": n}, hoặc None khi nó không
    được chọn (RECEIVER tắt, không có địa chỉ, hoặc không nằm trong RECEIVER_INGEST_DEVICES lẫn RECEIVER_INGEST_PERCENT). Phần trăm được
    quyết bằng băm ổn định của mã máy, nên một máy ở yên trong hay ngoài khi phần trăm không đổi, và tăng phần trăm chỉ thêm máy."""
    if not (settings.RECEIVER_ENABLED and settings.RECEIVER_INGEST_URLS and isinstance(device, str) and device):
        return None
    bucket = int.from_bytes(hashlib.sha256(device.encode("utf-8")).digest()[:4], "big") % 10000
    if device not in settings.RECEIVER_INGEST_DEVICES and bucket >= settings.RECEIVER_INGEST_PERCENT * 100:
        return None
    # the receiver does not know which computers may send only from the office (Office only on the Admin page): where that rule can
    # apply (OFFICE_NETS, or Caddy in front that marks a send from outside), a computer kept to the office stays on this server, which
    # checks where it sends from; only one an admin let send from any network goes to the receiver
    # bộ nhận không biết máy nào chỉ được gửi từ văn phòng (Chỉ văn phòng trên trang Quản trị): ở nơi luật đó có thể áp (OFFICE_NETS,
    # hay Caddy đứng trước đánh dấu lần gửi từ bên ngoài), máy bị giữ trong văn phòng ở lại máy chủ này, nơi kiểm nó gửi từ đâu; chỉ máy
    # quản trị đã cho gửi từ mọi mạng mới đi tới bộ nhận
    if (settings.OFFICE_NETS or settings.TRUST_PROXY) and not DEVICE_KEYS.roams(device):
        return None
    return {"ingestUrls": list(settings.RECEIVER_INGEST_URLS), "ingestTtlMs": settings.RECEIVER_INGEST_TTL_SECONDS * 1000}


def write_secrets(now: float) -> str:
    """Write the receiver's file of secrets, readable by this account only: written to a temporary file and renamed, so the receiver never
    reads half a file. Returns the path. Who holds this file can make keys for any computer and send numbers as it, but reads no data.
    Ghi file bí mật của bộ nhận, chỉ tài khoản này đọc được: ghi ra file tạm rồi đổi tên, để bộ nhận không bao giờ đọc nửa file.
    Trả về đường dẫn. Ai giữ file này làm được khoá cho mọi máy và gửi số thay nó, nhưng không đọc được dữ liệu nào."""
    path = settings.RECEIVER_SECRETS_FILE
    body = json.dumps(DEVICE_KEYS.receiver_secrets(now), indent=1) + "\n"
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, mode=0o700, exist_ok=True)
    temp = os.path.join(folder, ".%s.%d.tmp" % (os.path.basename(path), os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise
    return path


class Policy:
    """The numbered policy the receiver asks for every 15 seconds: which computers are revoked, from when keys must be renewed, the pace
    the computers are told, and which computers were written here directly since a number, so the receiver drops the book it holds for them.
    Tài liệu chính sách có số thứ tự mà bộ nhận hỏi mỗi 15 giây: máy nào bị thu hồi, khoá phải gia hạn từ mốc nào, nhịp gửi dặn các máy,
    và máy nào vừa được ghi thẳng ở đây kể từ một số thứ tự, để bộ nhận bỏ sổ nó đang giữ cho các máy đó."""

    def __init__(self):
        self.lock = threading.Lock()
        self.seq = 0
        self.written = deque(maxlen=WRITTEN_KEEP)
        # (src, boot) of a receiver -> the newest batch written, so a batch sent again is answered without being written twice
        # (src, boot) của một bộ nhận -> lô mới nhất đã ghi, để lô gửi lại được trả lời mà không ghi hai lần
        self.batches = {}
        # (src, boot) -> (seq, answer) of the newest batch written: a batch sent again because its answer was lost gets that answer, so the
        # receiver still learns which computers need their whole book or were left out
        # (src, boot) -> (seq, câu trả lời) của lô mới nhất đã ghi: lô gửi lại vì mất câu trả lời nhận lại đúng câu trả lời đó, để bộ nhận
        # vẫn biết máy nào cần cả sổ hay bị bỏ ra
        self.answers = {}
        # rows the third check found cleaned differently by the receiver, since this server started
        # các dòng mà lớp đối chiếu thứ ba thấy bộ nhận làm sạch khác, kể từ khi máy chủ này khởi động
        self.mismatches = 0
        self.checked = 0
        # (seconds the oldest row of the last batch waited at the receiver, when that batch came), for the Admin page (lag)
        # (số giây dòng chờ lâu nhất của lô gần nhất đã chờ ở bộ nhận, lúc lô đó tới), cho trang Quản trị (lag)
        self.waited = None

    def note_written(self, device: str) -> None:
        if not settings.RECEIVER_ENABLED:
            return
        with self.lock:
            self.seq += 1
            self.written.append((self.seq, device))

    def document(self, since: int, boot: str) -> dict:
        """The policy, plus how many rows the third check compared and found cleaned differently since this server started.
        Tài liệu chính sách, cộng số dòng lớp đối chiếu thứ ba đã so và thấy làm sạch khác kể từ khi máy chủ này khởi động."""
        with self.lock:
            seq = self.seq
            oldest = self.written[0][0] if self.written else seq + 1
            # another start of this server, or further behind than the list reaches: start again from nothing
            # một lần khởi động khác của máy chủ này, hoặc chậm hơn chỗ danh sách còn nhớ: bắt đầu lại từ đầu
            reset = boot != BOOT_ID or since > seq or (since < oldest - 1 and since < seq)
            written = [] if reset else sorted({d for s, d in self.written if s > since})
        # proto 2: one row per computer per batch, the books it loads hold only today's hours, the third check comes in rows of its own;
        # proto 3: a row and a book bring the time of the send that wrote each hour (row_stamps), so an hour of an older send never
        # writes over a newer one
        # proto 2: mỗi máy một dòng mỗi lô, sổ nó nạp chỉ có các giờ của hôm nay, lớp đối chiếu thứ ba đến bằng các dòng riêng; proto 3:
        # dòng và sổ mang thời điểm của lần gửi đã ghi từng giờ (row_stamps), để giờ của lần gửi cũ hơn không bao giờ đè giờ mới hơn
        return {"proto": PROTO, "seq": seq, "boot": BOOT_ID, "reset": reset, "written": written, "revoked": DEVICE_KEYS.revoked(),
                "renewBefore": DEVICE_KEYS.renewal_moment(), "sharedKeyMode": settings.SHARED_KEY_MODE,
                "minGapMs": settings.INGEST_MIN_GAP_MS, "stateGapMs": settings.INGEST_STATE_GAP_MS, "maxGapMs": settings.INGEST_MAX_GAP_MS,
                "ingestBurst": settings.INGEST_BURST, "ingestPerSecond": settings.INGEST_PER_SECOND, "maxBodyBytes": settings.MAX_BODY_BYTES,
                "checkPercent": settings.RECEIVER_CHECK_PERCENT, "tzHours": settings.LOCAL_TZ.utcoffset(None).total_seconds() / 3600,
                "checked": self.checked, "mismatches": self.mismatches,
                # the live feed: the only page allowed to open it, and the sessions given a ticket that still lives but are no longer open
                # luồng số trực tiếp: trang duy nhất được mở nó, và các phiên đã được cấp vé còn sống nhưng không còn mở nữa
                "boardOrigins": [settings.RECEIVER_BOARD_ORIGIN] if settings.live_enabled() else [],
                "endedSessions": TICKETS.ended(time.time())}


POLICY = Policy()

TICKET_PREFIX = "awt1"
# a scope written into a ticket is at most this long, once in base64
# phạm vi ghi trong vé dài nhiều nhất chừng này, sau khi đổi sang base64
TICKET_SCOPE_MAX = 200


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_ticket(kid: str, secret: bytes, role: str, scope: str, sid: str, expires: int) -> str:
    """A ticket: awt1.<kid>.<role>.<scope in base64url>.<sid>.<expiry in seconds>.<HMAC-SHA256 of the six parts before it, base64url>.
    The receiver checks it exactly so (receiver/internal/feed); tests/contract/ticket/cases.json holds the two to it.
    Một vé: awt1.<kid>.<vai>.<phạm vi dạng base64url>.<sid>.<hết hạn tính bằng giây>.<HMAC-SHA256 của sáu phần trước nó, base64url>.
    Bộ nhận kiểm đúng như vậy (receiver/internal/feed); tests/contract/ticket/cases.json giữ hai bên khớp nhau."""
    body = ".".join((TICKET_PREFIX, kid, role, _b64(scope.encode()), sid, str(int(expires))))
    return body + "." + _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())


class Tickets:
    """The tickets of the board's live feed: a logged-in page asks one for a scope, and opens the feed on the receiver with it. A ticket
    lives TICKET_SECONDS and the feed it opened ends with it. It carries no name: only the role, the scope, and the sid, a code made
    from the session that cannot be turned back into it. Each sid given a ticket is kept until its ticket ends, so the policy can name the
    ones whose session closed meanwhile (logged out, expired, its account or TV screen removed, its role changed): the receiver ends
    their feeds when it next asks for the policy, within about 20 seconds.
    Vé của luồng số trực tiếp của bảng: một trang đã đăng nhập xin một vé cho một phạm vi, và mở luồng ở bộ nhận bằng vé đó. Vé sống
    TICKET_SECONDS và luồng nó mở kết thúc cùng nó. Vé không mang tên: chỉ vai, phạm vi, và sid, một mã làm từ phiên mà không lần ngược
    lại được. Mỗi sid đã được cấp vé được giữ tới khi vé của nó hết hạn, để chính sách nêu được những sid có phiên đã đóng trong lúc đó
    (đăng xuất, hết hạn, tài khoản hay màn hình TV bị bỏ, đổi vai): bộ nhận cắt luồng của chúng ở lần hỏi chính sách kế tiếp, trong
    khoảng 20 giây."""

    def __init__(self):
        self.lock = threading.Lock()
        # sid -> (session token, role, expiry of its newest ticket); in memory only, like the sessions themselves
        # sid -> (mã phiên, vai, hạn của vé mới nhất của nó); chỉ trong bộ nhớ, như chính các phiên
        self.issued = {}

    @staticmethod
    def sid_of(token: str, secret: bytes) -> str:
        return _b64(hmac.new(secret, b"sid|" + token.encode(), hashlib.sha256).digest())[:16]

    def issue(self, token: str, role: str, scope: str, now: float):
        """A ticket for the session token with its role and a scope already checked (views.parse_scope); None when the scope is too long
        to go in one.
        Một vé cho mã phiên với vai của nó và một phạm vi đã kiểm (views.parse_scope); None khi phạm vi quá dài để nằm trong vé."""
        if len(_b64(scope.encode())) > TICKET_SCOPE_MAX:
            return None
        kid, secret = DEVICE_KEYS.ticket_secret()
        sid, expires = self.sid_of(token, secret), int(now) + settings.TICKET_SECONDS
        with self.lock:
            self.issued = {k: v for k, v in self.issued.items() if v[2] > now} if len(self.issued) > 1000 else self.issued
            self.issued[sid] = (token, role, expires)
        return {"ticket": make_ticket(kid, secret, role, scope, sid, expires), "scope": scope, "expiresAt": expires * 1000,
                "live": settings.RECEIVER_LIVE_URL + "/live", "snap": settings.RECEIVER_LIVE_URL + "/live/snap"}

    def ended(self, now: float) -> list:
        """The sids whose ticket still lives but whose session is closed or has another role now.
        Các sid có vé còn sống nhưng phiên đã đóng hoặc nay mang vai khác."""
        with self.lock:
            self.issued = {k: v for k, v in self.issued.items() if v[2] > now}
            living = list(self.issued.items())
        return sorted(sid for sid, (token, role, _) in living if SESSIONS.role_of_token(token, now) != role)


TICKETS = Tickets()


def book_for_receiver(device: str, whole: bool = False):
    """One computer's record as the receiver loads it: {device, updatedAt, seq?, the STATE_FIELDS it has, ledger, tasks, blocks?, stamps} with
    the hours of today and later only (the receiver keeps no more), or the whole book; stamps is the time of the send that wrote each hour,
    {kind: {hour: time}} (proto 3). None if there is none.
    Bản ghi của một máy như bộ nhận nạp: {device, updatedAt, seq?, các trường STATE_FIELDS nó có, ledger, tasks, blocks?, stamps} chỉ với các
    giờ từ hôm nay trở đi (bộ nhận không giữ hơn), hoặc cả sổ; stamps là thời điểm của lần gửi đã ghi từng giờ, {loại: {giờ: thời điểm}}
    (proto 3). None nếu không có."""
    stamps = {}
    with DEVICES.lock:
        m = DEVICES.get(device)
        book = DEVICES.book(device, None if whole else today_first_hour(time.time()), stamps) if m else None
    if not m:
        return None
    state = {k: m[k] for k in STATE_FIELDS if k in m}
    # seq: the number of its last send, which the receiver's window of a minute compares (clean.Decide)
    # seq: số của lần gửi cuối, thứ cửa sổ một phút của bộ nhận đem so (clean.Decide)
    number = {"seq": m["seq"]} if "seq" in m else {}
    return dict({"device": device, "updatedAt": m["updatedAt"]}, **number, **state, **(book or {}), stamps=stamps)


def devices_page(after: str, limit: int, device: str = "", whole: bool = False) -> dict:
    """The hours of today the receiver loads when it starts, a page at a time in the order of the device id; or one computer's, its whole
    book with whole (for the tests that compare the receiver with this server).
    Các giờ hôm nay bộ nhận nạp khi khởi động, từng trang theo thứ tự mã máy; hoặc của một máy, cả sổ khi có whole (cho các bài test
    so bộ nhận với máy chủ này)."""
    if device:
        one = book_for_receiver(device, whole)
        return {"devices": [one] if one else [], "next": None}
    limit = min(max(1, limit), DEVICES_PAGE_MAX)
    # the lock of the devices for the whole page, as a batch holds it for the whole batch (apply_rows): a batch is never written between two
    # books of a page. Without it (cee1e81) a batch written while a slow page was read left that page's older books in the receiver, and
    # money was lost after a kill -9 (run C48)
    # khoá các máy giữ cả trang, như một lô giữ nó cả lô (apply_rows): không lô nào được ghi xen giữa hai sổ của một trang. Bỏ khoá này
    # (cee1e81) thì một lô ghi trong lúc trang chậm đang đọc để lại các sổ cũ của trang đó ở bộ nhận, và mất tiền sau kill -9 (lượt C48)
    with DEVICES.exclusive():
        ids = DEVICES.ids_after(after, limit + 1)
        page = [book for book in (book_for_receiver(k) for k in ids[:limit]) if book]
    return {"devices": page, "next": ids[limit - 1] if len(ids) > limit else None}


def cleaned_parts(m: dict) -> dict:
    """A cleaned send without what the receiver leaves out or this server writes itself, for the third check.
    Một lần gửi đã làm sạch, bỏ những gì bộ nhận bỏ ra hay máy chủ này tự ghi, cho lớp đối chiếu thứ ba."""
    return {k: v for k, v in m.items() if k not in ("name", "account", "ip", "ipHistory")}


def apply_rows(batch, now: float):
    """Write one batch of rows from the receiver in one transaction and say which computers need their whole book; None if it is not a batch.
    Each row is cleaned again here, so the cleaning stays the boundary it is for every send (clean_payload); the name and the account come
    from identities, never from the computer; the IP history, the records of work handed to helpers and the history rows are kept as for
    a send on /ingest.
    Ghi một lô dòng của bộ nhận trong một giao dịch và cho biết máy nào cần cả sổ; None nếu không phải một lô.
    Mỗi dòng được làm sạch lại ở đây, nên bước làm sạch vẫn là ranh giới như với mọi lần gửi (clean_payload); tên và tài khoản lấy từ
    identities, không bao giờ từ máy gửi; lịch sử IP, biên bản giao việc và các dòng lịch sử được giữ như với một lần gửi ở /ingest."""
    from board.stores import AUDIT_LOG
    from board.views import INGEST_GATE, record_history

    if not (isinstance(batch, dict) and isinstance(batch.get("src"), str) and isinstance(batch.get("boot"), str)
            and isinstance(batch.get("seq"), int) and not isinstance(batch.get("seq"), bool) and isinstance(batch.get("rows"), list)):
        return None
    source, seq = (batch["src"][:64], batch["boot"][:64]), batch["seq"]
    wait = batch.get("waitMs")
    with POLICY.lock:
        if isinstance(wait, int) and not isinstance(wait, bool) and 0 <= wait < 10 ** 10:
            POLICY.waited = (wait / 1000, now)
        done = POLICY.batches.get(source, -1)
        last = POLICY.answers.get(source)
    if seq <= done:
        return dict(last[1]) if last and last[0] == seq else {"ok": True, "seq": seq, "needFull": [], "unknown": [], "incomplete": [], "bad": []}
    # the builds of the board rest while the batch is written (board/turns.py)
    # các lần dựng bảng nghỉ trong lúc lô được ghi
    job = _Batch(now, INGEST_GATE.identities)
    job.out["bad"] = DEVICES.write_batch(batch["rows"], job, settings.RECEIVER_FAST_APPLY)
    out, people, delegations = job.out, job.people, job.delegations
    with POLICY.lock:
        POLICY.batches[source] = max(seq, POLICY.batches.get(source, -1))
    # the receiver takes only sends made with a computer's own key: each computer written here has used it
    # bộ nhận chỉ nhận lần gửi bằng khoá riêng của máy: mỗi máy được ghi ở đây đều đã dùng khoá đó
    skipped = set(out["unknown"]) | set(out["bad"])
    used = []
    for row in batch["rows"]:
        k = row.get("k") if isinstance(row, dict) else None
        if isinstance(k, list) and row.get("kind") in ("v1", "hours", "full") and len(k) == 2 and k[0] == "m" and isinstance(k[1], str) \
                and k[1] in INGEST_GATE.identities and k[1] not in skipped:
            used.append(k[1])
            # the hours the receiver left out when it put several sends together, older than what the row holds (proto 3): counted as
            # the ones this server leaves out itself, since they never come here
            # các giờ bộ nhận để ra ngoài khi gộp nhiều lần gửi, cũ hơn thứ dòng đang giữ (proto 3): đếm như các giờ máy chủ này tự để
            # ra ngoài, vì chúng không bao giờ tới đây
            n = row.get("older")
            if isinstance(n, int) and not isinstance(n, bool) and 0 < n <= OLDER_MAX:
                order.note_older(n, k[1])
    DEVICE_KEYS.note_used_many(used, None, now)
    for d, records in delegations:
        AUDIT_LOG.write_delegations(d["device"], d.get("name", ""), d.get("account", ""), records)
    # the history of the board: with RECEIVER_FAST_APPLY it is left to history_loop, which looks at everyone every 30 seconds, so a
    # batch no longer builds again the row of each person it wrote; a change comes into the history up to 30 seconds later, and a
    # state that lasts less than that may not come in at all
    # lịch sử của bảng: với RECEIVER_FAST_APPLY việc này để cho history_loop, vòng xem mọi người mỗi 30 giây, nên một lô không còn
    # dựng lại dòng của từng người nó vừa ghi; một thay đổi vào lịch sử muộn tới 30 giây, và trạng thái kéo dài ngắn hơn thế có thể
    # không vào lịch sử
    if not settings.RECEIVER_FAST_APPLY:
        for person in people:
            record_history(person)
    answer = dict({"ok": True, "seq": seq}, **{k: sorted(set(v)) for k, v in out.items()})
    with POLICY.lock:
        if POLICY.batches.get(source) == seq:
            POLICY.answers[source] = (seq, answer)
    return answer


class _Batch:
    """The receiver's side of a batch for DEVICES.write_batch: each row is written by apply_row into out, people and delegations, which
    begin() empties for each try; a fast try given up also takes back the counts of the third check it made (check_row).
    Phía bộ nhận của một lô cho DEVICES.write_batch: mỗi dòng được apply_row ghi vào out, people và delegations, begin() làm rỗng chúng cho
    mỗi lần thử; lần thử nhanh bị bỏ cũng rút lại các số đếm của lớp đối chiếu thứ ba nó đã làm (check_row)."""

    def __init__(self, now: float, identities: dict):
        self.now, self.identities, self.counts = now, identities, None

    def begin(self) -> None:
        self.out = {"needFull": [], "unknown": [], "incomplete": [], "bad": []}
        self.people, self.delegations = set(), []
        if self.counts is None:
            with POLICY.lock:
                self.counts = POLICY.checked, POLICY.mismatches

    def write(self, row) -> None:
        apply_row(row, self.now, self.identities, self.out, self.people, self.delegations)

    def undo(self) -> None:
        with POLICY.lock:
            POLICY.checked, POLICY.mismatches = self.counts

    @staticmethod
    def device_of(row):
        k = row.get("k") if isinstance(row, dict) else None
        return k[1] if isinstance(k, list) and len(k) == 2 and isinstance(k[1], str) else None


# past this many seconds of waiting at the receiver, the Admin page says the receiver is behind (its /health says so too)
# chờ ở bộ nhận quá bấy nhiêu giây thì trang Quản trị báo bộ nhận đang chậm (/health của nó cũng báo)
BEHIND_SECONDS = 60
# a batch older than this says nothing any more about now: no computer sent since, or the receiver is stopped
# lô cũ hơn mức này không còn nói gì về lúc này: không máy nào gửi từ đó, hoặc bộ nhận đã dừng
WAITED_KEEP_SECONDS = 300


def lag(now: float):
    """For the Admin page with the receiver: how long the oldest row of the last batch waited at the receiver, and whether that is past
    BEHIND_SECONDS; None without the receiver or without a batch in the last WAITED_KEEP_SECONDS.
    Cho trang Quản trị khi có bộ nhận: dòng chờ lâu nhất của lô gần nhất đã chờ ở bộ nhận bao lâu, và đã quá BEHIND_SECONDS chưa;
    None khi không có bộ nhận hoặc không có lô nào trong WAITED_KEEP_SECONDS gần nhất."""
    if not settings.RECEIVER_ENABLED:
        return None
    with POLICY.lock:
        waited = POLICY.waited
    if waited is None or not 0 <= now - waited[1] < WAITED_KEEP_SECONDS:
        return None
    return {"waitSeconds": int(waited[0]), "behind": waited[0] > BEHIND_SECONDS}


def apply_row(row, now: float, identities: dict, out: dict, people: set, delegations: list) -> None:
    """One row of a batch, inside the batch's transaction: what it changed goes into out, people and delegations.
    Một dòng của lô, bên trong giao dịch của lô: những gì nó làm đổi được ghi vào out, people và delegations."""
    if not isinstance(row, dict) or not isinstance(row.get("v"), dict) or row.get("kind") not in ("v1", "hours", "full", "delegations", "check"):
        return
    at = row.get("at")
    at = at / 1000 if isinstance(at, (int, float)) and not isinstance(at, bool) and 0 < at < 1e15 else now
    if row["kind"] == "check":
        # one send as it came and as the receiver cleaned it, apart from the rows it put together: compared, never written
        # một lần gửi nguyên văn và như bộ nhận đã làm sạch, tách khỏi các dòng nó đã gộp: chỉ so, không bao giờ ghi
        if "raw" in row and settings.RECEIVER_CHECK_PERCENT > 0:
            check_row(row, at)
        return
    d = clean_payload(row["v"], at)
    if not d or row.get("k") != ["m", d["device"]]:
        return
    known = identities.get(d["device"])
    if known is None:
        # a computer this server never enrolled cannot have a key of its own: nothing is written for it
        # máy chưa từng được máy chủ này ghi danh thì không thể có khoá riêng: không ghi gì cho nó
        sys.stderr.write("receiver: row for an unknown computer %s\n" % d["device"])
        out["unknown"].append(d["device"])
        return
    # a person known without an email or a name: the receiver passes on this computer's next send that carries one, so it is filled in
    # người được biết mà thiếu email hay tên: bộ nhận chuyển cho máy chủ này lần gửi kế tiếp của máy có mang chúng, để chúng được điền
    if not known[0] or not known[1]:
        out["incomplete"].append(d["device"])
    d.pop("name", None)
    d.pop("account", None)
    for field, v in zip(("account", "name"), known):
        if v:
            d[field] = v
    if isinstance(row.get("ip"), str) and row["ip"]:
        d["ip"] = row["ip"][:45]
    if row["kind"] == "delegations":
        delegations.append((d, clean_delegations(row["v"].get("delegations"), at * 1000)))
        return
    # an hour the computer sent straight here after the receiver took this row is newer than the row's: it stays (board/order.py), even
    # after a restart of this server, and the row's other hours are written
    # giờ máy gửi thẳng tới đây sau khi bộ nhận nhận dòng này thì mới hơn giờ của dòng: nó được giữ (board/order.py), kể cả sau khi máy
    # chủ này khởi động lại, và các giờ khác của dòng vẫn được ghi
    outcome = save_ingest(d, now, row["kind"], decided=True, stamp=row_stamps(row, d))
    if outcome == NEED_FULL:
        out["needFull"].append(d["device"])
    elif outcome == SAVED:
        people.add(person_key(d))
        delegations.append((d, clean_delegations(row["v"].get("delegations"), at * 1000)))
    elif outcome == STALE:
        # its numbers are older than the book here, but its records of work handed to helpers still go to the audit log, once each
        # số của nó cũ hơn sổ ở đây, nhưng biên bản giao việc của nó vẫn vào nhật ký, mỗi cái một lần
        delegations.append((d, clean_delegations(row["v"].get("delegations"), at * 1000)))
    if "raw" in row and settings.RECEIVER_CHECK_PERCENT > 0:
        check_row(row, at)


def _time(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10 ** 15


def row_stamps(row: dict, d: dict):
    """The times a row of the receiver writes its hours with (order.Stamps): proto 3 brings stamp, the time of the row's whole book or of
    its newest send, and stamps, the time of each hour it put together from several sends, there or gone ({kind: {hour: time}}); a row of
    proto 2 has neither, and every hour takes the time of its send.
    Các thời điểm một dòng của bộ nhận dùng để ghi các giờ (order.Stamps): proto 3 mang stamp, thời điểm của sổ đủ trong dòng hoặc của
    lần gửi mới nhất, và stamps, thời điểm của từng giờ nó gộp từ nhiều lần gửi, có mặt hay đã vắng ({loại: {giờ: thời điểm}}); dòng proto
    2 không có cả hai, và mọi giờ lấy thời điểm của lần gửi đó."""
    base = row.get("stamp")
    if not _time(base):
        return order.Stamps(order.stamp_of(d))
    hours, given = {}, row.get("stamps")
    for kind in HOUR_KINDS:
        table = given.get(kind) if isinstance(given, dict) else None
        for hour, at in (table.items() if isinstance(table, dict) else ()):
            if isinstance(hour, str) and hour.isdigit() and len(hour) < 12 and _time(at):
                hours[(kind, int(hour))] = at
    return order.Stamps(base, hours)


def check_row(row: dict, at: float) -> None:
    """The third check: clean the send as it came and compare it with what the receiver cleaned; a difference is counted and logged.
    Lớp đối chiếu thứ ba: làm sạch lần gửi nguyên văn và so với thứ bộ nhận đã làm sạch; khác nhau thì đếm và ghi nhật ký."""
    try:
        mine = clean_payload(row["raw"], at)
        theirs = clean_payload(row["v"], at)
    except (ValueError, RecursionError, TypeError):
        mine, theirs = None, {}
    with POLICY.lock:
        POLICY.checked += 1
        same = mine is not None and theirs is not None and cleaned_parts(mine) == cleaned_parts(theirs)
        if not same:
            POLICY.mismatches += 1
    if not same:
        sys.stderr.write("receiver: cleaned differently for %s\n" % (row.get("k"),))


def sample(percent: float) -> bool:
    return random.random() * 100 < percent


def started(now: float = None) -> None:
    """At the start of the webhook with RECEIVER=1: write the file of secrets the receiver reads.
    Khi webhook khởi động với RECEIVER=1: ghi file bí mật bộ nhận đọc."""
    if settings.RECEIVER_ENABLED:
        path = write_secrets(time.time() if now is None else now)
        print("Go receiver: secrets written to %s" % path, flush=True)


class People:
    """The table the receiver puts its live numbers together with: each computer -> (the code of its person's row on the board, the scope
    that row is in, which is the id of its branch or "" for none). Every change has a number of its own, so the receiver asks only for
    what changed since the number it holds (/internal/people?since=). Built from what the board shows, at most every
    RECEIVER_PEOPLE_SECONDS, when the receiver asks; it holds no name, no email and no address.
    Bảng bộ nhận dùng để ghép số trực tiếp: mỗi máy -> (mã dòng của người của nó trên bảng, phạm vi dòng đó thuộc về, tức mã chi nhánh
    hoặc "" nếu chưa có). Mỗi thay đổi có một số thứ tự riêng, nên bộ nhận chỉ hỏi phần đổi kể từ số nó đang giữ (/internal/people?since=).
    Dựng từ thứ bảng đang hiện, nhiều nhất mỗi RECEIVER_PEOPLE_SECONDS một lần, khi bộ nhận hỏi; không chứa tên, email hay địa chỉ nào."""

    def __init__(self):
        self.lock = threading.Lock()
        self.seq = 0
        # device -> (row, scope, seq); row is None for a computer gone, kept so a receiver behind learns it went
        # máy -> (mã dòng, phạm vi, seq); mã dòng là None với máy đã mất, giữ lại để bộ nhận đang chậm biết nó đã mất
        self.rows = {}
        self.gone = 0
        # (seq, device) in the order of seq; an older pair of a device changed again is skipped when read
        # (seq, máy) theo thứ tự seq; cặp cũ của một máy đã đổi lại thì bị bỏ qua khi đọc
        self.log = []
        # past PEOPLE_GONE_MAX computers gone, the oldest are forgotten: a receiver that holds a number below this may have missed one,
        # and starts again from nothing
        # quá PEOPLE_GONE_MAX máy đã mất thì quên các máy cũ nhất: bộ nhận giữ số thấp hơn mức này có thể đã lỡ một máy, và bắt đầu lại
        self.floor = 0
        self.built_at = None

    def rebuild(self, now: float) -> None:
        from board.views import all_branches, branch_of, row_code

        with self.lock:
            if self.built_at is not None and 0 <= now - self.built_at < settings.RECEIVER_PEOPLE_SECONDS:
                return
            self.built_at = now
        devices = read_all_devices()
        branches = all_branches()
        # the same people and the same branches as the board (board/views.py, _raw_data)
        # cùng những người và cùng các chi nhánh như bảng (board/views.py, _raw_data)
        scope_of = {key: branch_of(r, branches) for key, r in branch_facts(devices).items()}
        table = {}
        for m in devices:
            key = person_key(m)
            if key in scope_of:
                table[m["device"]] = (row_code(key), scope_of[key])
        with self.lock:
            for device, (row, scope) in table.items():
                old = self.rows.get(device)
                if old is None or old[:2] != (row, scope):
                    if old is not None and old[0] is None:
                        self.gone -= 1
                    self._note(device, row, scope)
            for device in [d for d, v in self.rows.items() if v[0] is not None and d not in table]:
                self.gone += 1
                self._note(device, None, None)
            if self.gone > PEOPLE_GONE_MAX:
                oldest = sorted((v[2], d) for d, v in self.rows.items() if v[0] is None)[:self.gone - PEOPLE_GONE_MAX]
                self.floor = max(self.floor, oldest[-1][0])
                for _, d in oldest:
                    del self.rows[d]
                self.gone -= len(oldest)
            # the log grows with every change: past twice the table, it keeps one pair per computer
            # nhật ký lớn lên theo mỗi thay đổi: quá hai lần bảng thì giữ mỗi máy một cặp
            if len(self.log) > 2 * len(self.rows) + 1000:
                self.log = sorted((v[2], d) for d, v in self.rows.items())

    def _note(self, device: str, row, scope) -> None:
        self.seq += 1
        self.rows[device] = (row, scope, self.seq)
        self.log.append((self.seq, device))

    def page(self, since: int, boot: str, limit: int, now: float, loading: bool = False) -> dict:
        """The changes after since, at most limit, in the order of their numbers: {boot, reset, seq, more, people: [{device, row, scope}],
        gone: [devices]}. reset: another start of this server, or since is not a number this table can answer from; the answer then starts
        from nothing (every computer, none gone) and the receiver drops the table it holds. While more is true, ask again with since=seq,
        and with loading after a reset, so a page of the whole table is not taken for a receiver fallen behind; those pages may name
        computers gone, which the receiver may not hold.
        Các thay đổi sau since, nhiều nhất limit, theo thứ tự số: {boot, reset, seq, more, people: [{device, row, scope}], gone: [máy]}.
        reset: một lần khởi động khác của máy chủ này, hoặc since không phải số bảng này trả lời được; khi đó câu trả lời bắt đầu từ đầu
        (mọi máy, không máy nào mất) và bộ nhận bỏ bảng nó đang giữ. Khi more còn đúng, hỏi lại với since=seq, và với loading sau một
        reset, để một trang của cả bảng không bị coi là bộ nhận đã tụt lại; các trang đó có thể nêu máy đã mất mà bộ nhận không giữ."""
        self.rebuild(now)
        limit = min(max(1, limit), PEOPLE_PAGE_MAX)
        with self.lock:
            reset = boot != BOOT_ID or since > self.seq or (not loading and 0 < since < self.floor)
            start = 0 if reset else since
            people, gone, last = [], [], start
            i = bisect.bisect_right(self.log, (start, "\uffff"))
            while i < len(self.log) and len(people) + len(gone) < limit:
                seq, device = self.log[i]
                i += 1
                row, scope, at = self.rows.get(device, (None, None, -1))
                if at != seq:
                    continue
                last = seq
                if row is not None:
                    people.append({"device": device, "row": row, "scope": scope})
                elif start:
                    gone.append(device)
            # stopped at the limit with pairs left: the next page starts after the last one given
            # dừng ở mức trần mà còn cặp: trang kế bắt đầu sau cặp cuối đã đưa
            more = i < len(self.log)
            return {"boot": BOOT_ID, "reset": reset, "seq": last if more else self.seq, "more": more, "people": people, "gone": gone}


PEOPLE = People()
