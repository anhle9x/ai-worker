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
