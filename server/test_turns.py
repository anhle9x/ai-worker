#!/usr/bin/env python3
"""board/turns.py: a build rests only while a write runs, only every EVERY items, never longer than REST_SECONDS, and a write that fails
still ends. python3 -m unittest test_turns (run in the server folder).
  board/turns.py: một lần dựng chỉ nghỉ khi đang có lần ghi, chỉ mỗi EVERY mục, không bao giờ lâu hơn REST_SECONDS, và lần ghi hỏng vẫn kết
  thúc. python3 -m unittest test_turns (chạy trong thư mục server)."""
import threading
import time
import unittest

# temporary DATA_DIR and KEYS_DIR first
# DATA_DIR và KEYS_DIR tạm trước
import test_webhook as tw  # noqa: F401
from board import turns


class Turns(unittest.TestCase):
    def timed(self, i: int) -> float:
        t = time.perf_counter()
        turns.rest(i)
        return time.perf_counter() - t

    def test_no_write_no_rest(self):
        self.assertEqual(turns.writers(), 0)
        self.assertLess(self.timed(0), 0.01)

    def test_a_build_rests_while_a_write_runs_but_not_for_long(self):
        started, done = threading.Event(), threading.Event()

        def write():
            with turns.writing():
                started.set()
                done.wait(5)
        t = threading.Thread(target=write)
        t.start()
        started.wait(5)
        try:
            self.assertEqual(turns.writers(), 1)
            waited = self.timed(0)
            self.assertGreaterEqual(waited, turns.REST_SECONDS * 0.8)
            self.assertLess(waited, turns.REST_SECONDS + 0.2)
            # between two rests a build goes on at once
            # giữa hai lần nghỉ, lần dựng chạy tiếp ngay
            self.assertLess(self.timed(1), 0.01)
        finally:
            done.set()
            t.join(5)
        self.assertEqual(turns.writers(), 0)
        self.assertLess(self.timed(0), 0.01)

    def test_a_write_that_fails_still_ends_and_writes_nest(self):
        with turns.writing():
            with self.assertRaises(ValueError):
                with turns.writing():
                    raise ValueError("a batch that failed")
            self.assertEqual(turns.writers(), 1)
        self.assertEqual(turns.writers(), 0)
        self.assertLess(self.timed(0), 0.01)


if __name__ == "__main__":
    unittest.main()
