"""Writes first, builds of the board after: while the Go receiver's rows are being written (writing()), the threads that build the board,
the history or the table of people stop for a moment at points where they hold no lock (rest()), so the writes get the interpreter instead
of sharing it with a build of every person. A rest is short and bounded, so a build is slowed, never stopped.
  Ghi trước, dựng bảng sau: trong lúc các dòng của bộ nhận Go đang được ghi (writing()), các luồng dựng bảng, lịch sử hay bảng người dừng một
  chút ở những điểm chúng không giữ khoá nào (rest()), để việc ghi có trình thông dịch thay vì chia nó với một lần dựng mọi người. Mỗi lần
  nghỉ ngắn và có giới hạn, nên một lần dựng chỉ chậm đi, không bao giờ dừng hẳn."""
import contextlib
import threading

# how long a build waits at most at one rest, in seconds, and how many items it goes through between two rests
# một lần dựng chờ lâu nhất bao lâu ở một lần nghỉ, tính bằng giây, và đi qua bao nhiêu mục giữa hai lần nghỉ
REST_SECONDS = 0.05
EVERY = 500

_lock = threading.Lock()
_writers = 0
_idle = threading.Event()
_idle.set()


@contextlib.contextmanager
def writing():
    """Around a write of the receiver's rows: the builds rest while it runs.
    Bọc một lần ghi các dòng của bộ nhận: các lần dựng nghỉ trong lúc nó chạy."""
    global _writers
    with _lock:
        _writers += 1
        _idle.clear()
    try:
        yield
    finally:
        with _lock:
            _writers -= 1
            if _writers == 0:
                _idle.set()


def rest(i: int = 0) -> None:
    """Called by a build at a point where it holds no lock, with the number of items it has gone through: every EVERY items, while a write
    runs, it waits for it to end, at most REST_SECONDS.
    Một lần dựng gọi ở điểm nó không giữ khoá nào, kèm số mục đã đi qua: cứ mỗi EVERY mục, nếu đang có lần ghi, nó chờ lần ghi xong, tối đa
    REST_SECONDS."""
    if i % EVERY == 0 and not _idle.is_set():
        _idle.wait(REST_SECONDS)


def writers() -> int:
    """How many writes run now (for the tests).
    Đang có bao nhiêu lần ghi (cho các bài kiểm)."""
    return _writers
