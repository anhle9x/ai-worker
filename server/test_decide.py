#!/usr/bin/env python3
"""board/devices.py decide: what a send becomes before anything is written, the same choices as clean.Decide in the Go receiver. Through
its arguments only: no database, no module state. python3 -m unittest test_decide (run in the server folder).
  board/devices.py decide: một lần gửi sẽ thành gì trước khi ghi bất cứ gì, cùng các lựa chọn như clean.Decide trong bộ nhận Go. Chỉ qua
  các tham số của nó: không cơ sở dữ liệu, không trạng thái của module. python3 -m unittest test_decide (chạy trong thư mục server)."""
import unittest

# temporary DATA_DIR and KEYS_DIR first
# DATA_DIR và KEYS_DIR tạm trước
import test_webhook as tw  # noqa: F401
from board import settings
from board.devices import NEED_FULL, SAVED, STALE, decide

NOW = 1_800_000_000.0
T = 1_791_165_600_000
W = settings.REORDER_WINDOW_MS
F = settings.FULL_BOOK_SECONDS


def send(at: int, seq: int = None) -> dict:
    return dict({"device": "device-d1", "updatedAt": at}, **({"seq": seq} if seq is not None else {}))


class Decide(unittest.TestCase):
    def test_changed_hours_with_no_book_ask_for_the_whole_book(self):
        self.assertEqual(decide(None, send(T), NOW, "hours"), (NEED_FULL, "hours"))
        # a whole book or an old v1 send needs nothing kept
        # một sổ đủ hay gói v1 cũ không cần gì đang giữ
        self.assertEqual(decide(None, send(T), NOW, "full"), (SAVED, "full"))
        self.assertEqual(decide(None, send(T), NOW, "v1"), (SAVED, "v1"))

    def test_a_send_a_little_older_than_the_record_is_dropped_but_not_a_v1_or_a_much_older_one(self):
        kept = send(T)
        self.assertEqual(decide(kept, send(T - 1), NOW, "hours"), (STALE, "hours"))
        self.assertEqual(decide(kept, send(T - W), NOW, "full", None), (STALE, "full"))
        # just past the window, the same time, or newer: written (the hours keep their own times, board/order.py)
        # vừa quá cửa sổ, cùng thời điểm, hoặc mới hơn: được ghi (các giờ giữ thời điểm riêng, board/order.py)
        self.assertEqual(decide(kept, send(T - W - 1), NOW, "hours"), (SAVED, "hours"))
        self.assertEqual(decide(kept, send(T), NOW, "hours"), (SAVED, "hours"))
        self.assertEqual(decide(kept, send(T + 1), NOW, "hours"), (SAVED, "hours"))
        self.assertEqual(decide(kept, send(T - 1), NOW, "v1"), (SAVED, "v1"))

    def test_seq_orders_the_sends_so_a_clock_that_went_back_is_not_out_of_order(self):
        kept = send(T, seq=T)
        self.assertEqual(decide(kept, send(T - 30_000, seq=T + 1), NOW, "hours"), (SAVED, "hours"))
        self.assertEqual(decide(kept, send(T + 30_000, seq=T - 1), NOW, "hours"), (STALE, "hours"))

    def test_a_whole_book_again_too_soon_is_merged_hour_by_hour(self):
        kept = send(T)
        self.assertEqual(decide(kept, send(T + 1), NOW, "full", NOW - F + 1), (SAVED, "hours"))
        self.assertEqual(decide(kept, send(T + 1), NOW, "full", NOW - F), (SAVED, "full"))
        self.assertEqual(decide(kept, send(T + 1), NOW, "full", None), (SAVED, "full"))
        # with no book kept, a whole book is never merged
        # không có sổ đang giữ thì sổ đủ không bao giờ bị ghép
        self.assertEqual(decide(None, send(T + 1), NOW, "full", NOW), (SAVED, "full"))


if __name__ == "__main__":
    unittest.main()
