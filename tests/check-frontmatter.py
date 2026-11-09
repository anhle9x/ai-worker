#!/usr/bin/env python3
# The front matter of every skill and agent must be valid YAML: GitHub and other tools refuse a plain value holding ": " or " #".
# Phần đầu YAML của mọi skill và trợ lý phải hợp lệ: GitHub và công cụ khác từ chối giá trị không ngoặc có ": " hay " #".
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
files = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True).stdout.split()
bad = []
for name in files:
    text = (ROOT / name).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        continue
    for n, line in enumerate(text[4:text.find("\n---", 4)].split("\n"), 2):
        m = re.match(r"^([A-Za-z_-]+):\s+(.*)$", line)
        if not m or m.group(2)[:1] in ('"', "'", "|", ">", "[", "{"):
            continue
        if ": " in m.group(2) or " #" in m.group(2) or m.group(2).endswith(":"):
            bad.append("%s:%d %s needs quotes" % (name, n, m.group(1)))
print("\n".join(bad) or "Front matter OK")
sys.exit(1 if bad else 0)
