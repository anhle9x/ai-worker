#!/usr/bin/env python3
"""The two ways a send is taken, side by side: straight on /ingest, and as a row of the Go receiver (board/receiver.py). For each outcome,
what each way does after the save: the records of work handed to helpers, the note that the computer used its own key, and the note that
tells the receiver to drop its book. Where the two differ on purpose the expected line says why; one line pins a difference that is not on
purpose, to be made the same later. python3 -m unittest test_two_paths (run in the server folder).
  Hai cách một lần gửi được nhận, đặt cạnh nhau: gửi thẳng trên /ingest, và thành một dòng của bộ nhận Go (board/receiver.py). Với từng
  kết quả, mỗi cách làm gì sau khi lưu: biên bản giao việc cho trợ lý, ghi nhận máy đã dùng khoá riêng, và ghi nhận báo bộ nhận bỏ sổ của
  nó. Chỗ hai cách khác nhau có chủ ý thì dòng mong đợi nói lý do; một dòng ghim một chỗ khác nhau không chủ ý, để sau này làm cho giống.
  python3 -m unittest test_two_paths (chạy trong thư mục server)."""
import secrets
import time
import unittest

import test_receiver as tr
from board import devicekeys, receiver, stores
from test_contract import drop_rows

DEVICE = "device-rcva"
# the history of the board is left out: a row of the receiver leaves it to history_loop with RECEIVER_FAST_APPLY (up to 30 s later)
# lịch sử của bảng không có ở đây: dòng của bộ nhận để nó cho history_loop khi có RECEIVER_FAST_APPLY (muộn tới 30 giây)
#   (way, outcome): (records written, own key noted, receiver told to drop its book)
EXPECTED = {
    ("straight", "saved"): (True, True, True),
    # the receiver wrote it itself, so it keeps its book
    # chính bộ nhận đã ghi nó, nên nó giữ sổ của nó
    ("row", "saved"): (True, True, False),
    ("straight", "need-full"): (True, True, False),
    ("row", "need-full"): (True, True, False),
}


class TwoPaths(unittest.TestCase):
    setUpClass = tr.Receiver.__dict__["setUpClass"]
    tearDownClass = tr.Receiver.__dict__["tearDownClass"]
    setUp = tr.Receiver.setUp
    tearDown = tr.Receiver.tearDown
    call = tr.Receiver.call
    internal = tr.Receiver.internal
    enrol = tr.Receiver.enrol
    row = tr.Receiver.row

    def record(self) -> dict:
        return {"id": secrets.token_hex(12), "tool": "ask_gemini", "at": int(time.time() * 1000) - 1000, "outcome": "ok"}

    def seen(self, rec: dict) -> bool:
        return bool(stores.AUDIT_LOG.db.rows("SELECT key FROM delegations_seen WHERE key = ?", ("%s|%s" % (DEVICE, rec["id"]),)))

    def used(self) -> bool:
        keys = devicekeys.DEVICE_KEYS
        with keys.lock:
            keys._rows()
            return DEVICE in keys.rows

    def told(self, before: list) -> bool:
        with receiver.POLICY.lock:
            return any(d == DEVICE for d in [d for _, d in receiver.POLICY.written][len(before):])

    def written_before(self) -> list:
        with receiver.POLICY.lock:
            return list(receiver.POLICY.written)

    def go(self, way: str, outcome: str) -> tuple:
        key = self.enrol(DEVICE)
        if outcome == "need-full":
            # the book is gone here (a lost or broken row): changed hours must ask for the whole book
            # sổ ở đây đã mất (dòng bị mất hay hỏng): các giờ đã đổi phải xin cả sổ
            drop_rows([DEVICE])
        self.assertFalse(self.used())
        rec, before = self.record(), self.written_before()
        h = str(int(time.time()) // 3600)
        if way == "straight":
            status, answer = self.call("POST", "/ingest", {"v": 2, "device": DEVICE, "updatedAt": int(time.time() * 1000),
                                                          "hours": {"ledger": {h: {"usdMicro": 5}}}, "delegations": [rec]},
                                       Authorization="Bearer " + key)
            self.assertEqual((status, answer["needFull"]), (200, outcome == "need-full"))
        else:
            row = self.row(DEVICE, {"ledger": {h: {"usdMicro": 5}}}, delegations=[rec])
            status, answer = self.internal("POST", "/internal/rows", {"src": "go-two", "boot": "b" + outcome, "seq": 1, "rows": [row]})
            self.assertEqual((status, answer["needFull"]), (200, [DEVICE] if outcome == "need-full" else []))
        return self.seen(rec), self.used(), self.told(before)

    def test_each_way_and_outcome_does_what_the_table_says(self):
        for (way, outcome), want in EXPECTED.items():
            with self.subTest(way=way, outcome=outcome):
                try:
                    self.assertEqual(self.go(way, outcome), want)
                finally:
                    self.tearDown()
                    devicekeys.DEVICE_KEYS.forget(DEVICE)
                    self.setUp()


if __name__ == "__main__":
    unittest.main()
