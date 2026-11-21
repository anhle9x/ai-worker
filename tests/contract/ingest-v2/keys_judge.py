#!/usr/bin/env python3
"""The judge of the Go receiver's key check (receiver/internal/devicekey): in an empty folder, the server's own code issues computer keys
and writes the receiver's file of secrets, then prints keys good and bad with what Python's check says of each, and tickets of the live
feed. The Go tests read that file and must say the same, and take the tickets. python3 tests/contract/ingest-v2/keys_judge.py <folder>. Standard library only.
  Trọng tài của bước kiểm khoá trong bộ nhận Go (receiver/internal/devicekey): trong một thư mục rỗng, chính mã của máy chủ cấp khoá máy
  và ghi file bí mật của bộ nhận, rồi in các khoá tốt và xấu kèm điều bước kiểm của Python nói về từng khoá, và các vé của luồng số trực
  tiếp. Các bài test Go đọc file đó và phải nói giống hệt, và nhận các vé. Chỉ thư viện chuẩn."""

import json
import os
import sys

FOLDER = os.path.abspath(sys.argv[1])
os.environ.update(DATA_DIR=FOLDER, KEYS_DIR=FOLDER, RECEIVER_SECRETS_FILE=os.path.join(FOLDER, "receiver-secrets.json"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "server"))

from board import receiver  # noqa: E402
from board.devicekeys import DEVICE_KEYS  # noqa: E402

NOW = 1795200000.0


def main() -> None:
    good = DEVICE_KEYS.issue("device-judge1", "judge@example.com", "Judge", NOW - 100)
    old = DEVICE_KEYS.issue("device-judge2", "judge@example.com", "Judge", NOW - 91 * 86400)
    renew = DEVICE_KEYS.issue("device-judge3", "judge@example.com", "Judge", NOW - 31 * 86400)
    head, sig = good.rsplit(".", 1)
    tokens = [good, old, renew, head + "." + ("A" if sig[0] != "A" else "B") + sig[1:], good.replace("awd1.", "awd2.", 1), good + ".x",
              good.replace(".device-judge1.", ".device-judge9.", 1), good.replace("." + DEVICE_KEYS.org + ".", ".otherorg.", 1),
              "awd1.nokid." + ".".join(good.split(".")[2:]), "awd1.a.b.c.d.device-x.1.sig", "awd1.a.b.c.d.Device-X.1.sig", "",
              DEVICE_KEYS.issue("device-judge4", "judge@example.com", "Judge", NOW + 1000)]
    cases = []
    for token in tokens:
        claims, reason = DEVICE_KEYS.check(token, NOW)
        cases.append({"token": token, "claims": claims, "reason": reason,
                      "renew": DEVICE_KEYS.needs_renewal(claims, NOW) if claims else None})
    path = receiver.write_secrets(NOW)
    # a ticket of the live feed as POST /sse/ticket gives it, checked by receiver/internal/feed with the same file
    # một vé của luồng số trực tiếp như POST /sse/ticket cấp, receiver/internal/feed kiểm bằng cùng file
    tickets = [dict(receiver.TICKETS.issue("judge-session-" + scope, role, scope, NOW), role=role) for role, scope in (("wall", "org"), ("admin", "branch:hn"))]
    print(json.dumps({"now": NOW, "secrets": path, "cases": cases, "tickets": tickets}))


if __name__ == "__main__":
    main()
