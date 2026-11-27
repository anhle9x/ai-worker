#!/usr/bin/env python3
"""board/order.py plan: which hours of a send are written, which stay as they were, which are removed, and how many lost, for a whole book
and for changed hours. Compared, on many random cases, with the rule as write_book and DeviceCache.merge wrote it before (kept here as the
reference). python3 -m unittest test_order (run in the server folder).
  board/order.py plan: giờ nào của một lần gửi được ghi, giờ nào giữ nguyên, giờ nào bị xoá, và bao nhiêu giờ thua, cho một sổ đủ và cho
  các giờ đã đổi. Được so, trên nhiều trường hợp ngẫu nhiên, với luật như write_book và DeviceCache.merge đã viết trước đây (giữ ở đây làm
  bản mẫu). python3 -m unittest test_order (chạy trong thư mục server)."""
import random
import unittest

# temporary DATA_DIR and KEYS_DIR first
# DATA_DIR và KEYS_DIR tạm trước
import test_webhook as tw  # noqa: F401
from board import order
from board.order import Stamps

KINDS = ("ledger", "tasks", "blocks")


def whole_before(sent: dict, stored: dict, kept: dict, stamps) -> tuple:
    """write_book as it was (0.50.26), without the database: (put [(key, body, stamp)], drop [key], lost, after {key: body}).
    write_book như trước đây (0.50.26), không có cơ sở dữ liệu."""
    new, older = {}, 0
    for key, body in sent.items():
        if order.wins(stamps.of(*key), kept.get(key)) if stamps is not None else True:
            new[key] = body
        elif key in stored:
            new[key], older = stored[key], older + 1
    for key, body in stored.items():
        if key not in new and stamps is not None and not order.wins(stamps.of(*key), kept.get(key)):
            new[key], older = body, older + 1
    put = [(key, body, stamps.of(*key) if stamps is not None else None) for key, body in new.items() if stored.get(key) != body]
    drop = [key for key in stored if key not in new]
    return put, drop, older, new


def changed_before(sent: dict, stored: dict, kept: dict, stamps) -> tuple:
    """The hours of one kind in DeviceCache.merge as it was (0.50.26): (put, drop, lost); a body None is an empty table (removes the hour).
    Các giờ của một loại trong DeviceCache.merge như trước đây (0.50.26); nội dung None là bảng rỗng (xoá giờ đó)."""
    these = dict(sent)
    older = set()
    if stamps is not None:
        older = {key for key in these if not order.wins(stamps.of(*key), kept.get(key))}
        these = {key: b for key, b in these.items() if key not in older}
    put, drop = [], []
    for key, body in these.items():
        if body is not None:
            if stored.get(key) != body:
                put.append((key, body, stamps.of(*key) if stamps is not None else None))
        elif key in stored:
            drop.append(key)
    return put, drop, len(older)


def case(rng: random.Random, one_kind: str = None) -> tuple:
    """A random computer: hours stored with their stamps, a send of some of them and of new ones, and the stamps of that send.
    Một máy ngẫu nhiên: các giờ đang lưu kèm mốc, một lần gửi một số giờ đó và giờ mới, và các mốc của lần gửi đó."""
    kinds = (one_kind,) if one_kind else KINDS
    hours = range(1000, 1000 + rng.randint(1, 12))
    stored, kept = {}, {}
    for kind in kinds:
        for h in hours:
            if rng.random() < 0.6:
                stored[(kind, h)] = '{"v": %d}' % rng.randint(1, 3)
                kept[(kind, h)] = rng.choice((0, 100, 200, 300))
    sent = {}
    for kind in kinds:
        for h in range(990, 1000 + len(hours) + 3):
            if rng.random() < 0.5:
                sent[(kind, h)] = None if (one_kind and rng.random() < 0.2) else '{"v": %d}' % rng.randint(1, 3)
    if rng.random() < 0.15:
        stamps = None
    else:
        apart = {key: rng.choice((50, 150, 250, 350)) for key in list(sent) + list(stored) if rng.random() < 0.3}
        stamps = Stamps(rng.choice((50, 100, 150, 200, 250, 300, 350)), apart)
    return sent, stored, kept, stamps


class Plan(unittest.TestCase):
    def test_a_whole_book_is_planned_as_write_book_wrote_it(self):
        rng = random.Random(20261127)
        for _ in range(3000):
            sent, stored, kept, stamps = case(rng)
            put, drop, lost, after = whole_before(sent, stored, kept, stamps)
            got = order.plan(sent, stored, kept, stamps, whole=True)
            self.assertEqual((got.put, got.drop, got.lost, list(got.after.items())), (put, drop, lost, list(after.items())))

    def test_changed_hours_are_planned_as_merge_wrote_them(self):
        rng = random.Random(1127)
        for _ in range(3000):
            sent, stored, kept, stamps = case(rng, rng.choice(KINDS))
            put, drop, lost = changed_before(sent, stored, kept, stamps)
            got = order.plan(sent, stored, kept, stamps, whole=False)
            self.assertEqual((got.put, got.drop, got.lost, got.after), (put, drop, lost, None))

    def test_the_rule_in_a_few_words(self):
        # the same stamp wins; an older send leaves a newer hour as it is; a hour with no stamp kept is written by any send; a winning hour
        # with the same body is not written again, so its stamp does not move
        # mốc bằng nhau thì thắng; lần gửi cũ hơn để nguyên giờ mới hơn; giờ chưa có mốc thì lần gửi nào cũng ghi; giờ thắng mà nội dung
        # không đổi thì không ghi lại, nên mốc của nó không tăng
        stored, kept = {("ledger", 1): "a", ("ledger", 2): "b"}, {("ledger", 1): 200, ("ledger", 2): 100}
        got = order.plan({("ledger", 1): "x", ("ledger", 2): "b", ("ledger", 3): "c"}, stored, kept, Stamps(200), whole=False)
        self.assertEqual(got.put, [(("ledger", 1), "x", 200), (("ledger", 3), "c", 200)])
        got = order.plan({("ledger", 1): "x", ("ledger", 3): "c"}, stored, kept, Stamps(150), whole=False)
        self.assertEqual((got.put, got.lost), ([(("ledger", 3), "c", 150)], 1))
        # a whole book older than an hour it leaves out keeps that hour; without stamps (an upgrade) the book is written exactly
        # một sổ đủ cũ hơn một giờ nó không có thì giữ giờ đó; không có mốc (lần nâng cấp) thì ghi đúng sổ
        got = order.plan({("ledger", 1): "x"}, stored, kept, Stamps(150), whole=True)
        self.assertEqual((got.drop, got.lost, got.after), ([("ledger", 2)], 1, {("ledger", 1): "a"}))
        got = order.plan({("ledger", 1): "x"}, stored, kept, None, whole=True)
        self.assertEqual((got.put, got.drop, got.lost), ([(("ledger", 1), "x", None)], [("ledger", 2)], 0))


if __name__ == "__main__":
    unittest.main()
