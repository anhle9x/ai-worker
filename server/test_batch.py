#!/usr/bin/env python3
"""board/devices.py DeviceCache.write_batch and exclusive, through their interface: the devices are held, in the right order, for the whole
batch; a fast try that fails is taken back and the batch written again row by row, a bad row named alone. python3 -m unittest test_batch
(run in the server folder).
  board/devices.py DeviceCache.write_batch và exclusive, qua interface của chúng: các máy được giữ, đúng thứ tự, suốt cả lô; lần thử nhanh
  hỏng được rút lại và lô được ghi lại từng dòng, dòng hỏng được nêu tên riêng. python3 -m unittest test_batch (chạy trong thư mục server)."""
import threading
import unittest

# temporary DATA_DIR and KEYS_DIR first
# DATA_DIR và KEYS_DIR tạm trước
import test_webhook as tw  # noqa: F401
from board import turns
from board.devices import DEVICES


class Job:
    """A job that writes nothing: it notes what it was asked, whether the devices were held while it wrote, and fails where told.
    Một job không ghi gì: nó ghi lại việc được nhờ, các máy có đang bị giữ lúc nó ghi không, và hỏng ở chỗ được bảo."""

    def __init__(self, fail=()):
        self.fail, self.calls, self.held = set(fail), [], []

    def begin(self):
        self.calls.append("begin")
        self.written = []

    def write(self, row):
        other = []
        t = threading.Thread(target=lambda: other.append(DEVICES.lock.acquire(timeout=0.2) and DEVICES.lock.release() is None))
        t.start()
        t.join()
        self.held.append((turns.writers() > 0, not other[0]))
        if row in self.fail:
            raise ValueError(row)
        self.written.append(row)

    def undo(self):
        self.calls.append("undo")

    @staticmethod
    def device_of(row):
        return row if isinstance(row, str) else None


class WriteBatch(unittest.TestCase):
    def test_the_devices_are_held_for_every_row_both_ways(self):
        # the builds rest and no other thread takes the lock while any row is written, fast or row by row
        # các lần dựng nghỉ và không luồng nào khác lấy được khoá trong lúc ghi bất kỳ dòng nào, nhanh hay từng dòng
        for fast in (True, False):
            job = Job()
            self.assertEqual(DEVICES.write_batch(["device-b1", "device-b2"], job, fast), [])
            self.assertEqual(job.written, ["device-b1", "device-b2"])
            self.assertEqual(job.calls, ["begin"])
            self.assertTrue(job.held and all(a and b for a, b in job.held), job.held)
        self.assertEqual(turns.writers(), 0)

    def test_a_fast_try_that_fails_is_taken_back_and_the_bad_row_named_alone(self):
        job = Job(fail={"device-b2"})
        self.assertEqual(DEVICES.write_batch(["device-b1", "device-b2", 7, "device-b3"], job, True), ["device-b2"])
        # tried fast, taken back, begun again, then every row but the bad one written
        # thử nhanh, bị rút lại, bắt đầu lại, rồi mọi dòng trừ dòng hỏng được ghi
        self.assertEqual(job.calls, ["begin", "undo", "begin"])
        self.assertEqual(job.written, ["device-b1", 7, "device-b3"])
        # row by row from the start: no undo, and a bad row with no device is taken back but not named
        # từng dòng ngay từ đầu: không có undo, và dòng hỏng không có máy được rút lại nhưng không nêu tên
        job = Job(fail={"device-b1", 7})
        self.assertEqual(DEVICES.write_batch(["device-b1", 7, "device-b3"], job, False), ["device-b1"])
        self.assertEqual(job.calls, ["begin"])
        self.assertEqual(turns.writers(), 0)

    def test_exclusive_rests_the_builds_then_takes_the_lock(self):
        with DEVICES.exclusive():
            self.assertGreater(turns.writers(), 0)
            got = []
            t = threading.Thread(target=lambda: got.append(DEVICES.lock.acquire(timeout=0.2)))
            t.start()
            t.join()
            self.assertEqual(got, [False])
        self.assertEqual(turns.writers(), 0)


if __name__ == "__main__":
    unittest.main()
