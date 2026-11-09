#!/usr/bin/env python3
"""Proves a comment-only edit changed no code. Usage: same-code.py save <dir> <files...>, then same-code.py check <dir>
  Chứng minh việc chỉ sửa chú thích không đổi mã. Cách dùng: same-code.py save <thư mục> <các file>, rồi same-code.py check <thư mục>
"""
import os
import re
import shutil
import sys

MARKERS = {".js": "//", ".ts": "//", ".tsx": "//", ".py": "#", ".sh": "#", ".command": "#", ".ps1": "#", ".caddy": "#", ".yml": "#", ".bat": "::"}


def code_lines(path):
    marker = MARKERS.get(os.path.splitext(path)[1])
    out = []
    in_doc = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if path.endswith(".py"):
                n = s.count('"""')
                if in_doc or n:
                    if n % 2 == 1:
                        in_doc = not in_doc
                    continue
            if not s or (marker and s.startswith(marker)):
                continue
            if path.endswith((".css", ".html")) and (s.startswith("/*") or s.startswith("<!--")):
                continue
            if marker:
                s = re.sub(r"\s+" + re.escape(marker) + r"\s.*$", "", s)
            out.append(s)
    return out


def main():
    mode, folder = sys.argv[1], sys.argv[2]
    if mode == "save":
        for p in sys.argv[3:]:
            dest = os.path.join(folder, p)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(p, dest)
        return 0
    bad = 0
    for base, _, names in os.walk(folder):
        for name in names:
            saved = os.path.join(base, name)
            now = os.path.relpath(saved, folder)
            a, b = code_lines(saved), code_lines(now)
            if a != b:
                bad += 1
                first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                print("CHANGED %s near code line %d:\n  before: %s\n  after:  %s" % (now, first, a[first][:110] if first < len(a) else "", b[first][:110] if first < len(b) else ""))
    print("OK" if not bad else "%d file(s) changed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
