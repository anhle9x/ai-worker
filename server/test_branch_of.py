"""branch_of with its index of names and emails gives what going through every branch gave: the first branch that declares the account or
the name, then the first whose IP range holds the address, for random people and branches that declare some people twice.
  branch_of có chỉ mục tên và email cho cùng kết quả như duyệt mọi chi nhánh: chi nhánh đầu tiên khai báo tài khoản hoặc tên, sau đó
  chi nhánh đầu tiên có dải IP chứa địa chỉ, với người và chi nhánh ngẫu nhiên, có người được khai báo ở hai chi nhánh."""
import ipaddress
import random
import unittest

# temporary DATA_DIR and KEYS_DIR first
# DATA_DIR và KEYS_DIR tạm trước
import test_webhook as tw  # noqa: F401
from board import views


def branch_by_walking(r: dict, branches: list) -> str:
    """branch_of as it was before the index, the judge.
      branch_of như trước khi có chỉ mục, làm trọng tài."""
    person_keys = {str(r.get("account") or "").lower(), str(r.get("name") or "").lower()}
    for b in branches:
        if b["people"] & person_keys:
            return b["id"]
    for text in [r["latestIp"]] if r.get("latestIp") else r.get("ip") or []:
        try:
            ip = ipaddress.ip_address(text)
        except ValueError:
            continue
        for b in branches:
            if any(ip in m for m in b["networks"]):
                return b["id"]
    return ""


class BranchOf(unittest.TestCase):
    def test_the_same_as_walking_every_branch(self):
        rng = random.Random(5)
        names = ["p%02d@example.com" % i for i in range(40)] + ["person %02d" % i for i in range(40)] + [""]
        for round_ in range(30):
            branches = []
            for b in range(rng.randint(0, 6)):
                branches.append({"id": "b%d" % b, "people": set(rng.sample(names, rng.randint(0, 12))),
                                 "networks": [ipaddress.ip_network("10.%d.0.0/16" % rng.randint(0, 3))] if rng.random() < 0.6 else []})
            for _ in range(60):
                r = {"account": rng.choice(names).upper() if rng.random() < 0.3 else rng.choice(names), "name": rng.choice(names)}
                if rng.random() < 0.5:
                    r["latestIp"] = "10.%d.1.2" % rng.randint(0, 4)
                elif rng.random() < 0.5:
                    r["ip"] = ["not an address", "10.%d.9.9" % rng.randint(0, 4)]
                self.assertEqual(views.branch_of(r, branches), branch_by_walking(r, branches), (round_, r, branches))
            # a list changed in place would keep an old index: the board always makes a new one, and so does this test
            # danh sách bị sửa tại chỗ sẽ giữ chỉ mục cũ: bảng luôn tạo danh sách mới, và bài test này cũng vậy

    def test_several_lists_at_once(self):
        a = [{"id": "a", "people": {"an@example.com"}, "networks": []}]
        b = [{"id": "b", "people": {"an@example.com"}, "networks": []}]
        for _ in range(3):
            self.assertEqual(views.branch_of({"account": "An@Example.com"}, a), "a")
            self.assertEqual(views.branch_of({"account": "an@example.com"}, b), "b")


if __name__ == "__main__":
    unittest.main()
