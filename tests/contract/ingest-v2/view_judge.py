#!/usr/bin/env python3
"""The judge of the Go receiver's live numbers (receiver/internal/live): it runs the real webhook server (server/webhook.py, its settings
from the environment as for python3 webhook.py) in a thread of this process, and, for each line {"now": seconds} on its input, prints one
line with what role_view of the admin role says at that second, from the same memory that server answers from: of each person the fields
the live numbers carry, and the totals of each branch as /data?scope=org gives them. The Go test sends through the receiver to this server
and must say the same. python3 -I tests/contract/ingest-v2/view_judge.py. Standard library only.
  Trọng tài của số trực tiếp trong bộ nhận Go (receiver/internal/live): nó chạy máy chủ webhook thật (server/webhook.py, thiết lập lấy
  từ biến môi trường như python3 webhook.py) trong một luồng của tiến trình này, và với mỗi dòng {"now": giây} ở đầu vào, in một dòng
  gồm thứ role_view của vai quản trị nói ở giây đó, từ đúng bộ nhớ mà máy chủ đó trả lời: của mỗi người là các trường số trực tiếp mang,
  và tổng của từng chi nhánh như /data?scope=org cho. Bài test Go gửi qua bộ nhận tới máy chủ này và phải nói giống hệt. Chỉ thư viện
  chuẩn."""

import json
import os
import sys
import threading

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "server")
sys.path.insert(0, SERVER)

import webhook  # noqa: E402
from board import receiver  # noqa: E402
from board.security import ADMIN  # noqa: E402
from board.views import branch_totals, role_view  # noqa: E402

# the fields of a person the live numbers carry (receiver/internal/live, Row)
# các trường của một người mà số trực tiếp mang (receiver/internal/live, Row)
LIVE_FIELDS = ("row", "branch", "status", "openSessions", "working", "waiting", "delegating", "tools", "usdToday", "tokensIn", "tokensOut",
               "tasks", "updatedAt")


def main() -> None:
    # the output carries the answers only: what the server prints goes with its log
    # đầu ra chỉ mang các câu trả lời: thứ máy chủ in ra đi cùng nhật ký của nó
    answers, sys.stdout = sys.stdout, sys.stderr
    # what python3 webhook.py does before it listens, for the parts the receiver uses
    # những gì python3 webhook.py làm trước khi nghe, với các phần bộ nhận dùng
    os.umask(0o077)
    receiver.started()
    server = webhook.LimitedServer((webhook.BIND_ADDR, webhook.PORT), webhook.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for line in sys.stdin:
        now = json.loads(line)["now"]
        d = role_view(ADMIN, now)
        people = [{k: p[k] for k in LIVE_FIELDS} for p in d["people"]]
        answers.write(json.dumps({"people": people, "branchTotals": branch_totals(d)}) + "\n")
        answers.flush()


if __name__ == "__main__":
    main()
