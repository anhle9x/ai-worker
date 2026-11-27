"""Which send of a computer an hour keeps: each hour keeps the time of the send that wrote it (device_hours.sent_at, schema version 8),
and a send older than that does not write over it, however late it arrives: a send the computer gave up waiting for that the server still
took, or a row of the Go receiver written after a restart of this server. A computer's hour only grows, so a newer send with the same value
needs no new stamp. The time of a send is its seq when the plugin numbers its sends (hooks/sendv2.ts), else its updatedAt; a row of the
receiver that put several sends together brings the time of each hour (proto 3). Counts the hours left as they were, said in the log at
most once a minute.
  Một giờ của một máy giữ lần gửi nào: mỗi giờ giữ thời điểm của lần gửi đã ghi nó (device_hours.sent_at, lược đồ phiên bản 8), và lần
  gửi cũ hơn thế không ghi đè nó, dù tới muộn bao nhiêu: lần gửi máy đã thôi chờ mà máy chủ vẫn nhận, hay dòng của bộ nhận Go được ghi
  sau khi máy chủ này khởi động lại. Giờ của một máy chỉ tăng, nên lần gửi mới hơn mang cùng giá trị không cần mốc mới. Thời điểm của
  một lần gửi là seq khi plugin đánh số các lần gửi (hooks/sendv2.ts), không thì updatedAt; dòng của bộ nhận gộp nhiều lần gửi thì mang
  thời điểm của từng giờ (proto 3). Đếm các giờ được giữ nguyên, báo vào nhật ký nhiều nhất mỗi phút một lần."""
import sys
import threading
import time

# the most computers the count remembers: past that only the hours are counted on
# số máy nhiều nhất bộ đếm nhớ: quá mức đó chỉ còn đếm tiếp số giờ
DEVICES_KEEP = 100_000

_lock = threading.Lock()
_older = 0
_devices = set()
_said = (0, 0.0)


class Stamps:
    """The times a send writes its hours with: base for every hour, and hours, {(kind, hour): time}, for the hours with a time of their own,
    there or gone from the send (a row of the receiver that put several sends together).
    Các thời điểm một lần gửi dùng để ghi các giờ của nó: base cho mọi giờ, và hours, {(loại, giờ): thời điểm}, cho các giờ có thời điểm
    riêng, có mặt hay đã vắng trong lần gửi (dòng của bộ nhận gộp nhiều lần gửi)."""

    __slots__ = ("base", "hours")

    def __init__(self, base: int, hours: dict = None):
        self.base, self.hours = base, hours or {}

    def of(self, kind: str, hour: int) -> int:
        return self.hours.get((kind, hour), self.base)


def stamp_of(d: dict) -> int:
    """The time a cleaned send is ordered by: its seq when the plugin numbers its sends, else its updatedAt.
    Thời điểm dùng để xếp thứ tự một lần gửi đã làm sạch: seq khi plugin đánh số các lần gửi, không thì updatedAt."""
    return int(d["seq"]) if "seq" in d else int(d["updatedAt"])


def wins(stamp, kept) -> bool:
    """Whether a send stamped stamp writes an hour kept with the stamp kept (None: no such hour).
    Lần gửi có mốc stamp có được ghi một giờ đang giữ mốc kept không (None: chưa có giờ đó)."""
    return kept is None or stamp >= kept


class Plan:
    """What to do with the hours of one computer for a send (plan): put, [((kind, hour), body, stamp)] to write, in the order sent; drop,
    [(kind, hour)] to remove; lost, how many hours of the send stayed as they were, older than the ones kept; after, for a whole book, the
    hours held once it is written {(kind, hour): body}, else None.
    Việc phải làm với các giờ của một máy cho một lần gửi (plan): put, [((loại, giờ), nội dung, mốc)] cần ghi, theo thứ tự gửi; drop,
    [(loại, giờ)] cần xoá; lost, số giờ của lần gửi bị giữ nguyên vì cũ hơn giờ đang giữ; after, với một sổ đủ, các giờ đang giữ sau khi
    ghi {(loại, giờ): nội dung}, không thì None."""

    __slots__ = ("put", "drop", "lost", "after")

    def __init__(self, put: list, drop: list, lost: int, after=None):
        self.put, self.drop, self.lost, self.after = put, drop, lost, after


def plan(sent: dict, stored: dict, kept: dict, stamps, whole: bool) -> Plan:
    """Which hours of a send are written, which stay as they were and which are removed: the rule of this module in one place, with no
    database, for write_book (a whole book) and DeviceCache.merge (changed hours, one kind at a time). sent is {(kind, hour): body}, the
    bodies already encoded; with changed hours a body None is an empty table, which removes the hour. stored is the bodies held of those
    hours (of every hour for a whole book), kept their stamps; an hour with no stamp kept is written by any send. stamps is the send's
    Stamps, or None to write the hours exactly (the upgrade to schema version 6, a record replaced by hand), with no stamp on them.
    A whole book replaces the book: an hour held and not in it is removed unless a newer send wrote it, and a losing hour of the book
    counts only when an hour is held there. With changed hours every losing hour counts, and an hour not sent is left alone.
    Giờ nào của một lần gửi được ghi, giờ nào giữ nguyên và giờ nào bị xoá: luật của module này ở một chỗ, không có cơ sở dữ liệu, cho
    write_book (một sổ đủ) và DeviceCache.merge (các giờ đã đổi, từng loại một). sent là {(loại, giờ): nội dung}, nội dung đã mã hoá; với
    các giờ đã đổi, nội dung None là bảng rỗng, xoá giờ đó. stored là nội dung đang giữ của các giờ đó (của mọi giờ với một sổ đủ), kept
    là mốc của chúng; giờ chưa có mốc thì lần gửi nào cũng ghi. stamps là Stamps của lần gửi, hoặc None để ghi đúng các giờ (lần nâng lên
    lược đồ phiên bản 6, bản ghi thay bằng tay), không kèm mốc. Một sổ đủ thay cả sổ: giờ đang giữ mà không có trong nó thì bị xoá, trừ
    khi một lần gửi mới hơn đã ghi giờ đó, và một giờ thua của sổ chỉ được đếm khi đang có giờ ở đó. Với các giờ đã đổi, mọi giờ thua đều
    được đếm, và giờ không gửi thì để nguyên."""
    def stamp(key):
        return stamps.of(*key) if stamps is not None else None

    def loses(key) -> bool:
        return stamps is not None and not wins(stamps.of(*key), kept.get(key))

    if whole:
        after, lost = {}, 0
        for key, body in sent.items():
            if not loses(key):
                after[key] = body
            elif key in stored:
                after[key], lost = stored[key], lost + 1
        for key, body in stored.items():
            if key not in after and loses(key):
                after[key], lost = body, lost + 1
        put = [(key, body, stamp(key)) for key, body in after.items() if stored.get(key) != body]
        return Plan(put, [key for key in stored if key not in after], lost, after)
    put, drop, lost = [], [], 0
    for key, body in sent.items():
        if loses(key):
            lost += 1
        elif body is not None:
            if stored.get(key) != body:
                put.append((key, body, stamp(key)))
        elif key in stored:
            drop.append(key)
    return Plan(put, drop, lost)


def note_older(n: int, device: str = "") -> None:
    """n hours of a send of that computer were left as they were, older than what is kept.
    n giờ của một lần gửi của máy đó được giữ nguyên, vì cũ hơn thứ đang giữ."""
    global _older, _said
    if n <= 0:
        return
    now = time.time()
    with _lock:
        _older += n
        if device and len(_devices) < DEVICES_KEEP:
            _devices.add(device)
        said, at = _said
        due = now - at >= 60
        if due:
            _said = (_older, now)
        total = _older
    if due:
        sys.stderr.write("hours left as they were, older than the ones kept: %d (%d in all)\n" % (total - said, total))


def older() -> int:
    """How many hours were left as they were since this server started.
    Đã có bao nhiêu giờ được giữ nguyên kể từ khi máy chủ này khởi động."""
    with _lock:
        return _older


def counts() -> dict:
    """For the Admin page: the hours left as they were since this server started, and from how many computers.
    Cho trang Quản trị: số giờ được giữ nguyên kể từ khi máy chủ này khởi động, và từ bao nhiêu máy."""
    with _lock:
        return {"hours": _older, "computers": len(_devices)}


def reset() -> None:
    """Forget the counts (tests).
    Quên các số đếm (cho test)."""
    global _older, _devices, _said
    with _lock:
        _older, _devices, _said = 0, set(), (0, 0.0)
